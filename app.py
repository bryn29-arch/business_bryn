import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber

# ---------------------------------------------------------
# 1. FUNCIONES MOTORAS DE PROCESAMIENTO (BACK-END)
# ---------------------------------------------------------

def extraer_rut_o_nombre(texto):
    """Busca RUT chileno o extrae el nombre de la persona/empresa en la glosa."""
    if not isinstance(texto, str):
        return "NO_DETECTADO"
    
    # 1. Buscar RUT explícito (ej: 76.123.456-7)
    patron_rut = r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b'
    match = re.search(patron_rut, texto)
    if match:
        rut_raw = match.group(0)
        rut_limpio = rut_raw.replace('.', '').upper()
        if '-' not in rut_limpio:
            rut_limpio = rut_limpio[:-1] + '-' + rut_limpio[-1]
        return rut_limpio
    
    # 2. Si es un Traspaso/Pago de BCI, extraer el nombre del emisor
    match_nombre = re.search(r'(?:Traspaso De:|Pago:)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip()
        # Retornar los primeros 25 caracteres del nombre encontrado
        return f"NOMBRE: {nombre[:25]}"
        
    return "NO_DETECTADO"


def normalizar_cartola(archivo_subido):
    """Lee el archivo (PDF, Excel o CSV) y devuelve una tabla estandarizada con abonos."""
    nombre_archivo = archivo_subido.name.lower()
    
    try:
        registros = []

        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    tablas = pagina.extract_tables()
                    for tabla in tablas:
                        for fila in tabla:
                            if not fila:
                                continue
                            # Limpiar celdas de la fila
                            f_clean = [str(c).strip().replace('\n', ' ') if c else "" for c in fila]
                            texto_fila = " ".join(f_clean)
                            
                            # Omitir encabezados o líneas vacías
                            if not any(f_clean) or 'saldo' in texto_fila.lower():
                                continue
                            
                            # Buscar fecha (dd/mm/yyyy o dd/mm/yy)
                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            if not match_fecha:
                                continue
                            fecha = match_fecha.group(0)
                            
                            # Buscar montos numéricos (evitando tomar el número de la fecha)
                            # Eliminamos la fecha del texto para buscar los montos
                            texto_sin_fecha = texto_fila.replace(fecha, '')
                            
                            # Buscar números con formato de miles o mayores a 100
                            montos_encontrados = re.findall(r'\b\$?\s*(\d{1,3}(?:\.\d{3})+|\d{3,})\b', texto_sin_fecha)
                            
                            if montos_encontrados:
                                values = []
                                for m in montos_encontrados:
                                    num = int(m.replace('.', '').replace('$', '').strip())
                                    if num > 100:  # Filtrar números pequeños que sean días o códigos
                                        values.append(num)
                                
                                if values:
                                    # El abono suele ser el último o primer valor relevante
                                    monto_pago = values[-1]
                                    identificador = extraer_rut_o_nombre(texto_fila)
                                    
                                    registros.append({
                                        'fecha': fecha,
                                        'identificador_cliente': identificador,
                                        'monto_pago': monto_pago,
                                        'descripcion_glosa': texto_fila[:100]
                                    })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            # Procesamiento básico para planillas
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                montos = re.findall(r'\b\d{3,}\b', texto_fila)
                if montos:
                    registros.append({
                        'fecha': 'VER_EXCEL',
                        'identificador_cliente': extraer_rut_o_nombre(texto_fila),
                        'monto_pago': int(montos[-1]),
                        'descripcion_glosa': texto_fila[:100]
                    })

        if not registros:
            return None, "No se identificaron montos de abono superiores a $100."

        df_final = pd.DataFrame(registros).drop_duplicates().reset_index(drop=True)
        return df_final, "OK"

    except Exception as e:
        return None, f"Error al procesar: {str(e)}"


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

if archivo_cartola is not None:
    st.subheader("2. Cartola Bancaria Normalizada")
    
    with st.spinner("Procesando movimientos y montos de la cartola..."):
        df_cartola, mensaje = normalizar_cartola(archivo_cartola)
        
    if df_cartola is not None and not df_cartola.empty:
        st.success(f"¡Cartola procesada! Se identificaron **{len(df_cartola)}** abonos válidos.")
        
        m1, m2 = st.columns(2)
        m1.metric("Total Ingresos Detectados", f"$ {df_cartola['monto_pago'].sum():,.0f}".replace(",", "."))
        m2.metric("Clientes / RUTs Identificados", f"{(df_cartola['identificador_cliente'] != 'NO_DETECTADO').sum()} de {len(df_cartola)}")

        st.dataframe(
            df_cartola.style.format({'monto_pago': '$ {:,.0f}'}),
            use_container_width=True
        )
    else:
        st.error(f"Detalle de lectura: {mensaje}")
