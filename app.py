import streamlit as st
import pandas as pd
import io
from utils.procesadores import leer_archivo_subido
from utils.conciliacion import conciliar_cartera_y_cartola

st.set_page_config(page_title="Conciliación Bancaria Inteligente", page_icon="🏦", layout="wide")

st.title("🏦 Sistema de Conciliación Bancaria y Factoring")
st.markdown("Herramienta automatizada con selección manual de columnas para la cartera.")

# 1. Zona de Carga de Archivos
col1, col2 = st.columns(2)
with col1:
    file_cartola = st.file_uploader("1️⃣ Cartola Bancaria (PDF o Excel)", type=["xlsx", "xls", "csv", "pdf"], key="cartola")
with col2:
    file_ventas = st.file_uploader("2️⃣ Cartera de Ventas / Factoring (Excel / CSV)", type=["xlsx", "xls", "csv"], key="ventas")

if file_cartola and file_ventas:
    try:
        # Leemos la cartola (la dejamos intacta tal como me pediste)
        df_cartola = leer_archivo_subido(file_cartola)
        
        # Leemos la cartera de ventas en bruto para extraer sus encabezados
        nombre_v = file_ventas.name.lower()
        if nombre_v.endswith('.csv'):
            try:
                df_ventas_raw = pd.read_csv(file_ventas, sep=';', encoding='utf-8')
            except:
                df_ventas_raw = pd.read_csv(file_ventas, sep=',', encoding='utf-8')
        else:
            df_ventas_raw = pd.read_excel(file_ventas, sheet_name=0)

        st.success("✨ ¡Archivos cargados con éxito!")

        # 2. PANEL DE SELECCIÓN MANUAL DE COLUMNAS PARA LA CARTERA
        st.subheader("⚙️ Mapeo Manual de Columnas de la Planilla de Cartera")
        st.markdown("Indica qué columna de tu archivo Excel corresponde a cada campo para asegurar un match perfecto:")
        
        columnas_disponibles = list(df_ventas_raw.columns)

        # Funciones auxiliares para pre-seleccionar inteligentemente si existen nombres parecidos
        def buscar_indice_defecto(lista, opciones):
            for op in opciones:
                for idx, col in enumerate(lista):
                    if op in str(col).upper():
                        return idx
            return 0

        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            col_sel_rut = st.selectbox("📌 Columna de RUT", columnas_disponibles, index=buscar_indice_defecto(columnas_disponibles, ['RUT']))
        with c2:
            col_sel_monto = st.selectbox("💰 Columna de Monto", columnas_disponibles, index=buscar_indice_defecto(columnas_disponibles, ['MONTO', 'SALDO', 'TOTAL', 'ADEUDADO']))
        with c3:
            col_sel_folio = st.selectbox("📄 Columna de Folio / Doc", columnas_disponibles, index=buscar_indice_defecto(columnas_disponibles, ['FOLIO', 'DOC', 'FACTURA', 'NUMERO']))
        with c4:
            col_sel_cliente = st.selectbox("🏢 Columna de Cliente / Deudor", columnas_disponibles, index=buscar_indice_defecto(columnas_disponibles, ['CLIENTE', 'DEUDOR', 'EMPRESA', 'RAZON']))

        # Normalizamos el DataFrame de ventas renombrando las columnas según la selección del usuario
        df_ventas = df_ventas_raw.rename(columns={
            col_sel_rut: 'RUT_DEUDOR_MAP',
            col_sel_monto: 'MONTO_MAP',
            col_sel_folio: 'FOLIO_MAP',
            col_sel_cliente: 'CLIENTE_MAP'
        })

        st.divider()

        # 3. Vista previa de la cartola y cartera configurada
        with st.expander("👁️ Ver Vista Previa de Datos Procesados"):
            tab1, tab2 = st.tabs(["Cartola Bancaria", "Cartera de Ventas Configurada"])
            with tab1:
                st.dataframe(df_cartola, use_container_width=True)
            with tab2:
                st.dataframe(df_ventas, use_container_width=True)

        # 4. Botón para ejecutar el motor de emparejamiento inteligente
        if st.button("🚀 Ejecutar Conciliación Inteligente", type="primary"):
            with st.spinner("Cruzando cartola con la cartera de ventas configurada..."):
                df_cruce, df_pendientes = conciliar_cartera_y_cartola(df_cartola, df_ventas)
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        # 5. Mostrar resultados si ya se ejecutó
        if 'df_cruce' in st.session_state and not st.session_state['df_cruce'].empty:
            df_cruce = st.session_state['df_cruce']
            df_pendientes = st.session_state['df_pendientes']

            st.subheader("📊 Resumen del Análisis")
            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 Conciliados Exactos", len(df_cruce[df_cruce['Estado Conciliación'] == '🟢 Conciliado Exacto']))
            m2.metric("🟡 Con Observaciones", len(df_cruce[df_cruce['Estado Conciliación'] == '🟡 Con Observación']))
            m3.metric("🔴 No Identificados", len(df_cruce[df_cruce['Estado Conciliación'] == '🔴 Abono No Identificado']))

            st.subheader("📋 Matriz de Cruce Detallada")
            st.dataframe(df_cruce, use_container_width=True)

            # Botón de descarga en Excel
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
    st.info("👈 Sube tu cartola bancaria y tu cartera de ventas para habilitar la selección manual de columnas.")rtera de ventas en Excel para iniciar el cruce.")
