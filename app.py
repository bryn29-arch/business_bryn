import streamlit as st
import pandas as pd
import io
from utils.procesadores import leer_archivo_subido
from utils.conciliacion import conciliar_cartera_y_cartola

st.set_page_config(page_title="Conciliación Bancaria Inteligente", page_icon="🏦", layout="wide")

st.title("🏦 Sistema de Conciliación Bancaria y Factoring")
st.markdown("Herramienta automatizada de cruce financiero para PyMEs y Factoring.")

col1, col2 = st.columns(2)
with col1:
    file_cartola = st.file_uploader("1️⃣ Cartola Bancaria (PDF o Excel)", type=["xlsx", "xls", "csv", "pdf"], key="cartola")
with col2:
    file_ventas = st.file_uploader("2️⃣ Cartera de Ventas / Factoring (Excel)", type=["xlsx", "xls", "csv"], key="ventas")

if file_cartola and file_ventas:
    try:
        # 1. Leemos y estandarizamos la cartola y la cartera usando nuestros bloques
        df_cartola = leer_archivo_subido(file_cartola)
        df_ventas = leer_archivo_subido(file_ventas)

        st.success("✨ ¡Archivos leídos y estructurados correctamente!")

        # 2. Vista previa limpia de la cartola con sus columnas formateadas
        st.subheader("📄 Vista Previa de la Cartola Estructurada")
        st.dataframe(df_cartola, use_container_width=True)

        st.divider()

        # 3. Botón para ejecutar el motor de emparejamiento inteligente
        if st.button("🚀 Ejecutar Conciliación Inteligente", type="primary"):
            with st.spinner("Cruzando cartola con la cartera de ventas (por RUT, Monto y Glosa)..."):
                df_cruce, df_pendientes = conciliar_cartera_y_cartola(df_cartola, df_ventas)
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        # 4. Mostrar tablero de resultados si ya se ejecutó el análisis
        if 'df_cruce' in st.session_state and not st.session_state['df_cruce'].empty:
            df_cruce = st.session_state['df_cruce']
            df_pendientes = st.session_state['df_pendientes']

            st.subheader("📊 Resumen del Análisis")
            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 Conciliados Exactos", len(df_cruce[df_cruce['Estado Conciliación'].str.contains('Conciliado|Exacto', na=False)]))
            m2.metric("🟡 Con Diferencias", len(df_cruce[df_cruce['Estado Conciliación'].str.contains('Diferencia', na=False)]))
            m3.metric("🔴 No Identificados", len(df_cruce[df_cruce['Estado Conciliación'].str.contains('No Identificado', na=False)]))

            st.subheader("📋 Matriz de Cruce Detallada")
            st.dataframe(df_cruce, use_container_width=True)

            # Botón de descarga en Excel con pestañas separadas
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_cruce.to_excel(writer, sheet_name='Cartola_Conciliada', index=False)
                if not df_pendientes.empty:
                    df_pendientes.to_excel(writer, sheet_name='Documentos_Pendientes', index=False)

            st.download_button(
                "📥 Descargar Informe Completo en Excel",
                data=output.getvalue(),
                file_name="Informe_Conciliacion_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Ocurrió un error al procesar la información: {str(e)}")
else:
    st.info("👈 Sube tu cartola bancaria y tu cartera de ventas en Excel para iniciar el cruce.")
