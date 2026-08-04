import streamlit as st
import pandas as pd
import io
from utils.procesadores import leer_archivo_subido
from utils.detectores import limpiar_y_encontrar_encabezados
from utils.validadores import detectar_duplicados_cartera
from utils.conciliacion import conciliar_cartera_y_cartola

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Conciliación Bancaria - PyMEs & Factoring", 
    page_icon="🏦", 
    layout="wide"
)

st.title("🏦 Sistema de Conciliación Bancaria Inteligente")
st.markdown("Herramienta automatizada para la gestión financiera de PyMEs y Factoring en Chile.")

# -----------------------------------------------------------------------------
# INTERFAZ DE CARGA DE ARCHIVOS
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
    st.subheader("2️⃣ Cartera de Ventas / Factoring")
    file_ventas = st.file_uploader(
        "Sube tu cartera (Con deudores y múltiples RUTs)", 
        type=["xlsx", "xls", "csv"], 
        key="ventas"
    )

# -----------------------------------------------------------------------------
# PROCESAMIENTO Y EJECUCIÓN
# -----------------------------------------------------------------------------
if file_cartola and file_ventas:
    try:
        with st.spinner("Analizando y adaptando estructuras automáticamente..."):
            # Lectura multiformato
            df_cartola_raw = leer_archivo_subido(file_cartola)
            df_ventas_raw = leer_archivo_subido(file_ventas)

            # Limpieza y detección inteligente de encabezados
            df_cartola = limpiar_y_encontrar_encabezados(df_cartola_raw)
            df_ventas = limpiar_y_encontrar_encabezados(df_ventas_raw)

            # Validar duplicados en cartera
            df_ventas, alertas_duplicados = detectar_duplicados_cartera(df_ventas)

        st.success("✨ **¡Aprendí algo nuevo y me ajusté a tu formato! Vamos creciendo juntos.**")

        # Mostrar alertas de duplicados si las hay
        if alertas_duplicados:
            for alerta in alertas_duplicados:
                st.warning(alerta)

        # Vistas previas optimizadas: solo cartola completa para verificación y ahorro de memoria
        st.subheader("📄 Cartola Bancaria Procesada")
        st.dataframe(df_cartola, use_container_width=True) # Muestra toda la cartola sin cortes
        
        st.info("💡 Cartera de ventas cargada exitosamente en memoria y lista para el cruce masivo (sin previsualización pesada para mantener la app rápida).")

        # Botón para ejecutar el núcleo de conciliación (Fase 3)
        if st.button("🚀 Ejecutar Conciliación Inteligente", type="primary"):
            with st.spinner("Cruzando cartola con cartera de ventas..."):
                df_cruce, df_pendientes = conciliar_cartera_y_cartola(df_cartola, df_ventas)
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        # Mostrar resultados si ya se ejecutó
        if 'df_cruce' in st.session_state and not st.session_state['df_cruce'].empty:
            df_cruce = st.session_state['df_cruce']
            df_pendientes = st.session_state['df_pendientes']

            st.subheader("📊 Resumen de Resultados")
            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 Conciliados Exactos", len(df_cruce[df_cruce['Estado Conciliación'] == '🟢 Conciliado Exacto']))
            m2.metric("🟡 Diferencias", len(df_cruce[df_cruce['Estado Conciliación'] == '🟡 Diferencia en Monto']))
            m3.metric("🔴 No Identificados", len(df_cruce[df_cruce['Estado Conciliación'] == '🔴 Abono No Identificado']))

            st.subheader("📋 Matriz de Cruce Detallada")
            st.dataframe(df_cruce, use_container_width=True)

            # Botón de descarga en Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_cruce.to_excel(writer, sheet_name='Cartola_Conciliada', index=False)
                if not df_pendientes.empty:
                    df_pendientes.to_excel(writer, sheet_name='Facturas_Pendientes', index=False)

            st.download_button(
                "📥 Descargar Informe Completo en Excel", 
                data=output.getvalue(), 
                file_name="Informe_Conciliacion.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar la información: {str(e)}")
else:
    st.info("👈 Sube tu cartola bancaria y tu cartera de ventas o factoring para iniciar el proceso.")
