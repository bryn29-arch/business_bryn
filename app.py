import streamlit as st
import pandas as pd
from utils.procesadores import leer_archivo_subido

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Conciliación Bancaria - PyMEs", 
    page_icon="🏦", 
    layout="wide"
)

st.title("🏦 Sistema de Conciliación Bancaria")
st.markdown("Herramienta inteligente y rápida para ordenar las finanzas de tu emprendimiento.")

# -----------------------------------------------------------------------------
# INTERFAZ DE CARGA DE ARCHIVOS (FASE 1)
# -----------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("1️⃣ Cartola Bancaria")
    file_cartola = st.file_uploader(
        "Sube tu cartola (Excel, CSV o PDF)", 
        type=["xlsx", "xls", "csv", "pdf"], 
        key="cartola"
    )

with col2:
    st.subheader("2️⃣ Cartera de Ventas / Facturas")
    file_ventas = st.file_uploader(
        "Sube tus ventas o cobros pendientes (Excel o CSV)", 
        type=["xlsx", "xls", "csv"], 
        key="ventas"
    )

# -----------------------------------------------------------------------------
# PROCESAMIENTO INICIAL
# -----------------------------------------------------------------------------
if file_cartola and file_ventas:
    try:
        with st.spinner("Leyendo y procesando archivos de forma segura..."):
            # Usamos nuestro módulo procesador para leer cualquier formato
            df_cartola = leer_archivo_subido(file_cartola)
            df_ventas = leer_archivo_subido(file_ventas)

        st.success("¡Archivos cargados y leídos exitosamente!")

        # Mostrar vistas previas para verificar que los datos llegaron bien
        tab1, tab2 = st.tabs(["📄 Vista Previa: Cartola", "📄 Vista Previa: Ventas"])
        
        with tab1:
            st.dataframe(df_cartola.head(5), use_container_width=True)
            
        with tab2:
            st.dataframe(df_ventas.head(5), use_container_width=True)

    except Exception as e:
        st.error(f"Ocurrió un error al procesar los archivos: {str(e)}")
else:
    st.info("👈 Por favor, sube ambos archivos (Cartola y Cartera de Ventas) para comenzar la Fase 1.")
