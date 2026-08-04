import streamlit as st
import pandas as pd
from utils.procesadores import leer_archivo_subido
from utils.detectores import limpiar_y_encontrar_encabezados

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Conciliación Bancaria - PyMEs & Factoring", 
    page_icon="🏦", 
    layout="wide"
)

st.title("🏦 Sistema de Conciliación Bancaria Inteligente")
st.markdown("Automatización avanzada para PyMEs y empresas de factoring en Chile.")

# -----------------------------------------------------------------------------
# INTERFAZ DE CARGA DE ARCHIVOS (FASE 1 Y 2)
# -----------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("1️⃣ Cartola Bancaria")
    file_cartola = st.file_uploader(
        "Sube tu cartola (Excel, CSV o PDF multihabla)", 
        type=["xlsx", "xls", "csv", "pdf"], 
        key="cartola"
    )

with col2:
    st.subheader("2️⃣ Cartera de Ventas / Factoring")
    file_ventas = st.file_uploader(
        "Sube tu cartera (Con deudores y múltiples RUTs)", 
        type=["xlsx", "xls", "csv"], 
        key="ventas"
    )

# -----------------------------------------------------------------------------
# PROCESAMIENTO Y ADAPTACIÓN AUTOMÁTICA
# -----------------------------------------------------------------------------
if file_cartola and file_ventas:
    try:
        with st.spinner("Analizando estructuras y optimizando datos..."):
            # 1. Lectura multiformato
            df_cartola_raw = leer_archivo_subido(file_cartola)
            df_ventas_raw = leer_archivo_subido(file_ventas)

            # 2. Detección inteligente de encabezados y adaptación bancaria/factoring
            df_cartola = limpiar_y_encontrar_encabezados(df_cartola_raw)
            df_ventas = limpiar_y_encontrar_encabezados(df_ventas_raw)

        # Experiencia de usuario basada en crecimiento conjunto
        st.success("✨ **¡Aprendí algo nuevo y me ajusté a tu formato! Vamos creciendo juntos.**")

        # Guardar en la memoria temporal de Streamlit
        st.session_state['df_cartola'] = df_cartola
        st.session_state['df_ventas'] = df_ventas

        # Mostrar vistas previas con columnas estandarizadas
        tab1, tab2 = st.tabs(["📄 Cartola Adaptada", "📄 Cartera de Ventas / Factoring Adaptada"])
        
        with tab1:
            st.dataframe(df_cartola.head(6), use_container_width=True)
            
        with tab2:
            st.dataframe(df_ventas.head(6), use_container_width=True)

    except Exception as e:
        st.error(f"Ocurrió un error al procesar los archivos: {str(e)}")
else:
    st.info("👈 Sube ambos archivos para activar el motor de adaptación automática.")
