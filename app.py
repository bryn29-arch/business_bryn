import streamlit as st
import pandas as pd
import numpy as np

# 1. Configuración de Marca y Layout de la Página
st.set_page_config(
    page_title="FinanSmart | Plataforma de Conciliación",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo personalizado minimalista mediante CSS
st.markdown("""
    <style>
    .main { padding-top: 1rem; }
    .stMetric {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e9ecef;
    }
    </style>
""", unsafe_allow_html=True)

# 2. Barra Lateral (Sidebar) - Identidad Comercial
with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestíon Financiera")
    st.divider()
    
    st.subheader("Configuración de Proceso")
    empresa = st.text_input("Nombre de la Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    
    st.divider()
    st.info("💡 **Tip para el cliente:** No necesitas modificar tus archivos originales. El sistema procesa los formatos nativos del banco.")

# 3. Encabezado Principal
st.title("📊 Panel de Conciliación y Control de Cuentas")
st.write(f"Gestionando información para: **{empresa}** | Período: **{periodo.strftime('%m/%Y')}**")

st.divider()

# 4. Zonas de Carga de Archivos (Drag & Drop)
st.subheader("1. Carga de Documentos Crudos")
col_cartola, col_ventas = st.columns(2)

with col_cartola:
    st.markdown("##### 🏛️ Cartola Bancaria (Ingresos)")
    archivo_cartola = st.file_uploader(
        "Sube la cartola descargada del banco",
        type=["pdf", "xlsx", "xls", "csv"],
        help="Soporta cartolas en PDF o Excel de Banco de Chile, Santander, BCI, BancoEstado, etc.",
        key="cartola_input"
    )

with col_ventas:
    st.markdown("##### 📄 Registro de Ventas (Facturación)")
    archivo_ventas = st.file_uploader(
        "Sube el archivo de ventas emitidas",
        type=["xlsx", "xls", "csv"],
        help="Carga el archivo interno de ventas o exportación del SII/ERP.",
        key="ventas_input"
    )

st.divider()

# 5. Demostración del Panel Operativo
# Si hay archivos subidos (o para la demo visual):
if archivo_cartola is not None or st.checkbox("Mostrar vista previa interactiva (Modo Demo)", value=True):
    
    st.subheader("2. Resumen Ejecutivo de Cobranza")
    
    # Datos de ejemplo para la presentación comercial
    total_facturado = 1055000
    total_cobrado = 670000
    total_pendiente = 385000
    efectividad = (total_cobrado / total_facturado) * 100

    # Tarjetas de Métricas (KPIs)
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Facturado", f"$ {total_facturado:,.0f}".replace(",", "."))
    kpi2.metric("Total Conciliado / Pagado", f"$ {total_cobrado:,.0f}".replace(",", "."))
    kpi3.metric("Saldo Pendiente de Cobro", f"$ {total_pendiente:,.0f}".replace(",", "."), delta="-Pendiente", delta_color="inverse")
    kpi4.metric("Efectividad de Cobro", f"{efectividad:.1f}%")

    st.write("")
    
    # Pestañas de Navegación del Reporte
    tab_detalle, tab_alertas, tab_exportar = st.tabs(["📋 Detalle por Factura", "⚠️ Alertas e Inconsistencias", "🚀 Exportación y Sincronización"])
    
    # TAB 1: Detalle por Factura
    with tab_detalle:
        st.write("Estado consolidado línea por línea:")
        df_demo = pd.DataFrame({
            'Folio': ['1001', '1002', '1003', '1004'],
            'RUT Cliente': ['76.123.456-7', '76.987.654-3', '65.111.222-K', '76.123.456-7'],
            'Monto Emitido': [150000, 320000, 85000, 500000],
            'Monto Pagado': [150000, 200000, 0, 320000],
            'Saldo Pendiente': [0, 120000, 85000, 180000],
            'Estado': ['CONCILIADO', 'ABONADO (PARCIAL)', 'PENDIENTE', 'ABONADO (PARCIAL)']
        })
        
        # Tabla interactiva con resaltado de estados
        st.dataframe(
            df_demo.style.format({'Monto Emitido': '$ {:,.0f}', 'Monto Pagado': '$ {:,.0f}', 'Saldo Pendiente': '$ {:,.0f}'}),
            use_container_width=True
        )

    # TAB 2: Alertas
    with tab_alertas:
        st.warning("⚠️ **Inconsistencia Detectada:** El pago recibido por $200.000 del RUT 76.987.654-3 no especifica folio en la glosa bancaria. Asignado preliminarmente a la factura N° 1002.")
        st.error("🔴 **Cuenta Morosa:** La factura N° 1003 ($85.000) suma más de 30 días sin abonos registrados.")

    # TAB 3: Exportación
    with tab_exportar:
        st.write("Sincroniza el resultado directamente con la infraestructura de tu cliente:")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.button("🟢 Sincronizar con Google Sheets del Cliente", use_container_width=True)
        with col_exp2:
            st.download_button(
                label="📥 Descargar Informe en Excel Formateado",
                data=df_demo.to_csv(index=False).encode('utf-8'),
                file_name=f"Reporte_Conciliacion_{empresa}.csv",
                mime="text/csv",
                use_container_width=True
            )

