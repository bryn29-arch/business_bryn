import streamlit as st
import pandas as pd
import io
from utils.procesadores import leer_archivo_subido
from utils.conciliacion import conciliar_cartera_y_cartola

st.set_page_config(page_title="Conciliación Bancaria", page_icon="🏦", layout="wide")

st.title("🏦 Sistema de Conciliación Bancaria Inteligente")

col1, col2 = st.columns(2)
with col1:
    file_cartola = st.file_uploader("1️⃣ Cartola Bancaria", type=["xlsx", "xls", "csv", "pdf"], key="cartola")
with col2:
    file_ventas = st.file_uploader("2️⃣ Cartera de Ventas", type=["xlsx", "xls", "csv"], key="ventas")

if file_cartola and file_ventas:
    try:
        # Lectura directa sin bucles ni recargas infinitas en el estado
        df_cartola = leer_archivo_subido(file_cartola)
        df_ventas = leer_archivo_subido(file_ventas)

        st.success("✨ ¡Archivos leídos correctamente!")

        st.subheader("📄 Vista Previa de la Cartola")
        st.dataframe(df_cartola, use_container_width=True)

        if st.button("🚀 Ejecutar Conciliación Inteligente", type="primary"):
            with st.spinner("Procesando cruce..."):
                df_cruce, df_pendientes = conciliar_cartera_y_cartola(df_cartola, df_ventas)
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        if 'df_cruce' in st.session_state:
            st.subheader("📊 Resultados de la Conciliación")
            st.dataframe(st.session_state['df_cruce'], use_container_width=True)

    except Exception as e:
        st.error(f"Ocurrió un error al procesar los archivos: {str(e)}")
else:
    st.info("👈 Sube tu cartola y tu cartera de ventas para comenzar.")
