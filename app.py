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


def procesar_cartola_pdf(archivo_pdf):
    """Extrae texto y tablas de un archivo PDF bancario."""
    filas_extraidas = []
    
    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            tablas = pagina.extract_tables()
            for tabla in tablas:
                for fila in tabla:
                    # Limpiar elementos nulos de la fila
                    fila_limpia = [str(cell).strip() if cell else "" for cell in fila]
                    if any(fila_limpia):
                        filas_extraidas.append(fila_limpia)
                        
    if not filas_extraidas:
        return pd.DataFrame()
        
    df_raw = pd.DataFrame(filas_extraidas)
    return df_raw


def normalizar_cartola(archivo_subido):
    """Lee el archivo (PDF, Excel o CSV) y devuelve una tabla estandarizada."""
    nombre_archivo = archivo_subido.name.lower()
    
    try:
        # Carga según el formato del archivo
        if nombre_archivo.endswith('.pdf'):
            df_raw = procesar_cartola_pdf(archivo_subido)
        elif nombre_archivo.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(archivo_subido)
        elif nombre_archivo.endswith('.csv'):
            df_raw = pd.read_csv(archivo_subido)
        else:
            return None, "Formato no soportado."

        if df_raw.empty:
            return None, "No se pudieron extraer datos del archivo."

        # Identificar columnas por sinónimos
        mapa_cols = {
            'fecha': ['fecha', 'fec', 'fecha mov', 'f. proceso'],
            'glosa': ['glosa', 'concepto', 'detalle', 'descripcion', 'descripción', 'observaciones'],
            'abono': ['abono', 'abonos', 'credito', 'crédito', 'monto_abono', 'deposito', 'depósito', 'monto']
        }

        col_map = {}
        for col_std, sinonimos in mapa_cols.items():
            for c in df_raw.columns:
                if str(c).lower().strip() in sinonimos:
                    col_map[c] = col_std
                    break
        
        df = df_raw.rename(columns=col_map)

        # Si no mapeó automáticamente por encabezados, asignamos por posición como respaldo
        if 'abono' not in df.columns:
            # Buscar la primera columna que contenga números/montos
            for col in df.columns:
                serie_num = df[col].astype(str).str.replace(r'[^\d]', '', regex=True)
                if pd.to_numeric(serie_num, errors='coerce').sum() > 0:
                    df = df.rename(columns={col: 'abono'})
                    break

        if 'glosa' not in df.columns:
            # Asignar la columna con texto más largo como glosa
            df['glosa'] = df.apply(lambda x: " ".join(x.dropna().astype(str)), axis=1)

        # Limpieza de montos de abono
        df['monto_pago'] = (
            df['abono'].astype(str)
            .str.replace(r'[^\d,-]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
        )
        df['monto_pago'] = pd.to_numeric(df['monto_pago'], errors='coerce').fillna(0)
        
        # Quedarse solo con ingresos positivos
        df = df[df['monto_pago'] > 0].copy()

        # Extraer RUT desde la glosa
        df['descripcion_glosa'] = df['glosa'].astype(str)
        df['rut_detectado'] = df['descripcion_glosa'].apply(extraer_rut_de_texto)
        df['fecha'] = df['fecha'].astype(str) if 'fecha' in df.columns else 'S/F'

        cols_finales = ['fecha', 'rut_detectado', 'monto_pago', 'descripcion_glosa']
        return df[cols_finales].reset_index(drop=True), "OK"

    except Exception as e:
        return None, f"Error al procesar la cartola: {str(e)}"


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
    
    with st.spinner("Leyendo y extrayendo RUTs de la cartola bancaria..."):
        df_cartola, mensaje = normalizar_cartola(archivo_cartola)
        
    if df_cartola is not None and not df_cartola.empty:
        st.success(f"¡Cartola procesada con éxito! Se detectaron **{len(df_cartola)}** movimientos de ingreso.")
        
        # Métricas de la cartola
        m1, m2 = st.columns(2)
        m1.metric("Total Ingresos Detectados", f"$ {df_cartola['monto_pago'].sum():,.0f}".replace(",", "."))
        m2.metric("RUTs Identificados en Glosa", f"{(df_cartola['rut_detectado'] != 'NO_DETECTADO').sum()} de {len(df_cartola)}")

        # Tabla interactiva
        st.dataframe(
            df_cartola.style.format({'monto_pago': '$ {:,.0f}'}),
            use_container_width=True
        )
    else:
        st.error(f"No se pudieron extraer abonos válidos. Detalle: {mensaje}")
