import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber

# ---------------------------------------------------------
# 1. FUNCIONES MOTORAS DE PROCESAMIENTO (BACK-END)
# ---------------------------------------------------------

def extraer_rut_de_texto(texto):
    """Busca patrones de RUT chileno dentro del detalle/glosa."""
    if not isinstance(texto, str):
        return "NO_DETECTADO"
    
    patron = r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b'
    match = re.search(patron, texto)
    
    if match:
        rut_raw = match.group(0)
        rut_limpio = rut_raw.replace('.', '').upper()
        if '-' not in rut_limpio:
            rut_limpio = rut_limpio[:-1] + '-' + rut_limpio[-1]
        return rut_limpio
    return "NO_DETECTADO"


def extraer_filas_pdf(archivo_pdf):
    """Extrae líneas de texto y celdas estructuradas de cualquier PDF bancario."""
    filas = []
    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            # Intento 1: Extraer como tabla estructurada
            tablas = pagina.extract_tables()
            for tabla in tablas:
                for f in tabla:
                    if f:
                        f_clean = [str(c).strip() if c is not None else "" for c in f]
                        if any(f_clean):
                            filas.append(f_clean)
            
            # Intento 2: Si no detectó tablas, extraer línea por línea de texto
            if not filas:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        partes = linea.split()
                        if len(partes) >= 2:
                            filas.append(partes)
    return filas


def normalizar_cartola(archivo_subido):
    """Lee el archivo (PDF, Excel o CSV) y devuelve una tabla estandarizada con abonos."""
    nombre_archivo = archivo_subido.name.lower()
    
    try:
        if nombre_archivo.endswith('.pdf'):
            filas_raw = extraer_filas_pdf(archivo_subido)
            if not filas_raw:
                return None, "El PDF no contiene texto legible ni tablas."
            df_raw = pd.DataFrame(filas_raw)
        elif nombre_archivo.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(archivo_subido)
        elif nombre_archivo.endswith('.csv'):
            df_raw = pd.read_csv(archivo_subido)
        else:
            return None, "Formato no soportado."

        if df_raw.empty:
            return None, "El archivo no contiene filas procesables."

        registros = []
        
        for idx, row in df_raw.iterrows():
            texto_fila = " ".join([str(val) for val in row.values if pd.notna(val) and str(val).strip() != ""])
            
            # Omitir encabezados conocidos
            if any(palabra in texto_fila.lower() for palabra in ['saldo final', 'cartola de cuentas', 'saldo inicial', 'movimiento']):
                if not any(char.isdigit() for char in texto_fila):
                    continue

            # Buscar montos numéricos en la fila
            montos = re.findall(r'\b\$?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?\b', texto_fila)
            
            if montos:
                montos_num = []
                for m in montos:
                    val = int(m.replace('.', '').replace('$', '').strip())
                    if val > 0:
                        montos_num.append(val)
                
                if montos_num:
                    monto_final = montos_num[-1] if len(montos_num) == 1 else montos_num[0]
                    
                    match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                    fecha = match_fecha.group(0) if match_fecha else "S/F"
                    
                    rut = extraer_rut_de_texto(texto_fila)
                    
                    if monto_final > 0:
                        registros.append({
                            'fecha': fecha,
                            'rut_detectado': rut,
                            'monto_pago': monto_final,
                            'descripcion_glosa': texto_fila[:120]
                        })

        if not registros:
            return None, "No se identificaron montos de abono numéricos en el documento."

        df_final = pd.DataFrame(registros)
        df_final = df_final.drop_duplicates().reset_index(drop=True)
        
        return df_final, "OK"

    except Exception as e:
        return None, f"Error interno al procesar cartola: {str(e)}"


# ---------------------------------------------------------
# 2. INTERFAZ GRÁFICA DE USUARIO (FRONT-END)
# ---------------------------------------------------------

st.set_page_config(
    page_title="FinanSmart | Plataforma de Conciliación",
    page_icon="💼",
    layout="wide"
)

with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestión Financiera")
    st.divider()
    empresa = st.text_input("Nombre de la Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    st.divider()
    st.info("💡 **Tip para el cliente:** Sube tu cartola original en PDF o Excel sin hacerle cambios.")

st.title("📊 Panel de Conciliación y Control de Cuentas")
st.write(f"Gestionando información para: **{empresa}** | Período: **{periodo.strftime('%m/%Y')}**")
st.divider()

st.subheader("1. Carga de Documentos Crudos")
col_cartola, col_ventas = st.columns(2)

with col_cartola:
    st.markdown("##### 🏛️ Cartola Bancaria (Ingresos)")
    archivo_cartola = st.file_uploader(
        "Sube la cartola descargada del banco",
        type=["pdf", "xlsx", "xls", "csv"],
        key="cartola_input"
    )

with col_ventas:
    st.markdown("##### 📄 Registro de Ventas (Facturación)")
    archivo_ventas = st.file_uploader(
        "Sube el archivo de ventas emitidas",
        type=["xlsx", "xls", "csv"],
        key="ventas_input"
    )

st.divider()

# PROCESAMIENTO DE CARTOLA EN TIEMPO REAL
if archivo_cartola is not None:
    st.subheader("2. Cartola Bancaria Normalizada")
    
    with st.spinner("Leyendo y extrayendo movimientos de la cartola bancaria..."):
        df_cartola, mensaje = normalizar_cartola(archivo_cartola)
        
    if df_cartola is not None and not df_cartola.empty:
        st.success(f"¡Cartola procesada con éxito! Se detectaron **{len(df_cartola)}** movimientos.")
        
        m1, m2 = st.columns(2)
        m1.metric("Total Ingresos Detectados", f"$ {df_cartola['monto_pago'].sum():,.0f}".replace(",", "."))
        m2.metric("RUTs Identificados en Glosa", f"{(df_cartola['rut_detectado'] != 'NO_DETECTADO').sum()} de {len(df_cartola)}")

        st.dataframe(
            df_cartola.style.format({'monto_pago': '$ {:,.0f}'}),
            use_container_width=True
        )
    else:
        st.error(f"Detalle de lectura: {mensaje}")

