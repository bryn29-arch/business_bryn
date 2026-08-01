import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y CSS LUXURY ENTERPRISE
# ---------------------------------------------------------
st.set_page_config(
    page_title="FinanSmart | Plataforma de Conciliación",
    page_icon="💼",
    layout="wide"
)

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    div[data-testid="stFileUploader"] {
        background: #ffffff;
        border: 1.5px solid #e2e8f0;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.05);
        transition: all 0.35s ease;
    }
    
    div[data-testid="stFileUploader"]:hover {
        border-color: #6366f1;
        box-shadow: 0 15px 30px -10px rgba(99, 102, 241, 0.15);
    }
    
    div[data-testid="stFileUploader"] button, .stButton > button {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important;
        color: #ffffff !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 10px 22px !important;
        box-shadow: 0 4px 14px 0 rgba(15, 23, 42, 0.35) !important;
    }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.03);
        border-left: 5px solid #4f46e5;
    }
    
    div[data-testid="stMetricLabel"] {
        font-weight: 600;
        color: #64748b;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    div[data-testid="stMetricValue"] {
        color: #0f172a;
        font-weight: 700;
        font-size: 2rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border-radius: 10px 10px 0px 0px;
        padding: 12px 24px;
        border: 1px solid #e2e8f0;
        font-weight: 600;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1e293b !important;
        color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 1. FUNCIONES MOTORAS DE PROCESAMIENTO (MEJORADAS)
# ---------------------------------------------------------

def extraer_rut_o_nombre(texto):
    """Detecta RUTs con o sin formato (ej. 0969023903, 96.902.390-3) o razos sociales."""
    if not isinstance(texto, str):
        return "NO_DETECTADO"
    
    # 1. Buscar RUT estándar con guión
    match_std = re.search(r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b', texto)
    if match_std:
        rut_raw = match_std.group(0).replace('.', '').upper()
        if '-' not in rut_raw:
            rut_raw = rut_raw[:-1] + '-' + rut_raw[-1]
        return rut_raw

    # 2. Buscar RUT continuo de 8 o 9 dígitos (ej: 0969023903 -> 96902390-3)
    match_continuo = re.search(r'\b0?(\d{7,8}[\dkK])\b', texto)
    if match_continuo:
        raw = match_continuo.group(1).upper()
        return f"{raw[:-1]}-{raw[-1]}"

    # 3. Buscar Nombre / Razón social si existe patrón explícito
    match_nombre = re.search(r'(?:Traspaso De:|Pago:|Workmate|Proveedores)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(0).strip()
        nombre = re.sub(r'\s+(Internet|Cta|Cuenta|Transferencia|Oficina).*$', '', nombre, flags=re.IGNORECASE)
        return nombre[:35]
        
    return "NO_DETECTADO"


def extraer_monto_chileno(texto_o_celda):
    """Extrae montos numéricos con formato de miles por punto (.) o por coma (,)."""
    if not isinstance(texto_o_celda, str):
        texto_o_celda = str(texto_o_celda)
    
    # Busca patrones tipo: 3,998,400 o 3.998.400 o 47,600
    coincidencias = re.findall(r'\b\d{1,3}(?:[.,]\d{3})+\b', texto_o_celda)
    if coincidencias:
        # Tomamos el último monto que suele corresponder al abono o valor final
        monto_str = coincidencias[-1].replace('.', '').replace(',', '')
        try:
            val = int(monto_str)
            if val > 500: # Ignorar montos insignificantes o códigos
                return val
        except ValueError:
            pass
            
    # Búsqueda secundaria de enteros simples
    enteros = re.findall(r'\b\d{4,9}\b', texto_o_celda)
    if enteros:
        return int(enteros[-1])
        
    return None


def normalizar_cartola(archivo_subido):
    """Lee la cartola en PDF/Excel y procesa montos y clientes sin enviarlos a dudosos por formato."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        registros_ok = []
        registros_dudosos = []

        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for num_pag, pagina in enumerate(pdf.pages, start=1):
                    tablas = pagina.extract_tables()
                    for tabla in tablas:
                        for fila in tabla:
                            if not fila:
                                continue
                            
                            f_clean = [str(c).strip().replace('\n', ' ') if c else "" for c in fila]
                            texto_fila = " ".join(f_clean)
                            
                            if not any(f_clean) or any(x in texto_fila.lower() for x in ['saldo inicial', 'saldo final', 'cartola de cuenta']):
                                continue
                            
                            # Extraer Monto
                            monto_encontrado = None
                            for celda in reversed(f_clean):
                                m = extraer_monto_chileno(celda)
                                if m:
                                    monto_encontrado = m
                                    break
                            
                            if not monto_encontrado:
                                monto_encontrado = extraer_monto_chileno(texto_fila)

                            # Extraer Fecha
                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            fecha = match_fecha.group(0) if match_fecha else "S/F"
                            
                            identificador = extraer_rut_o_nombre(texto_fila)
                            glosa_limpia = re.sub(r'\b\d{1,3}(?:[.,]\d{3})+\b', '', texto_fila).strip()

                            if monto_encontrado:
                                registros_ok.append({
                                    'Fecha': fecha,
                                    'Identificador / Cliente': identificador,
                                    'Monto Pago': monto_encontrado,
                                    'Descripción Glosa': glosa_limpia[:120]
                                })
                            else:
                                registros_dudosos.append({
                                    'Página': num_pag,
                                    'Fecha': fecha,
                                    'Glosa Capturada': texto_fila[:100],
                                    'Observación': 'No se detectó un monto numérico válido'
                                })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                m = extraer_monto_chileno(texto_fila)
                if m:
                    registros_ok.append({
                        'Fecha': 'VER_EXCEL',
                        'Identificador / Cliente': extraer_rut_o_nombre(texto_fila),
                        'Monto Pago': m,
                        'Descripción Glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).drop_duplicates().reset_index(drop=True) if registros_ok else pd.DataFrame(columns=['Fecha', 'Identificador / Cliente', 'Monto Pago', 'Descripción Glosa'])
        df_dudosos = pd.DataFrame(registros_dudosos).drop_duplicates().reset_index(drop=True) if registros_dudosos else pd.DataFrame(columns=['Página', 'Fecha', 'Glosa Capturada', 'Observación'])

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Error al procesar: {str(e)}"


def normalizar_ventas(archivo_subido):
    """Lee y estandariza el Registro de Ventas (Excel/CSV)."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        if nombre_archivo.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(archivo_subido)
        elif nombre_archivo.endswith('.csv'):
            df_raw = pd.read_csv(archivo_subido)
        else:
            return None, "Formato no soportado para ventas."

        if df_raw.empty:
            return None, "El archivo de ventas está vacío."

        mapa_cols = {
            'folio': ['folio', 'nro_factura', 'numero', 'número', 'nro', 'factura', 'doc_num'],
            'rut': ['rut', 'rut_cliente', 'rut cliente', 'rut emisor', 'rut_receptor', 'rut receptor'],
            'razon_social': ['razon_social', 'razon social', 'razón social', 'cliente', 'nombre_cliente', 'receptor'],
            'monto_total': ['monto_total', 'total', 'monto total', 'monto', 'valor_total', 'total_con_iva']
        }

        col_map = {}
        for col_std, sinonimos in mapa_cols.items():
            for c in df_raw.columns:
                if str(c).lower().strip() in sinonimos:
                    col_map[c] = col_std
                    break

        df = df_raw.rename(columns=col_map)

        if 'folio' not in df.columns:
            df['folio'] = [f"F-{i+1}" for i in range(len(df))]
        if 'rut' not in df.columns:
            df['rut'] = "S/RUT"
        if 'razon_social' not in df.columns:
            df['razon_social'] = "CLIENTE DESCONOCIDO"

        if 'monto_total' in df.columns:
            df['monto_total'] = (
                df['monto_total'].astype(str)
                .str.replace(r'[^\d,-]', '', regex=True)
                .str.replace('.', '', regex=False)
                .str.replace(',', '.', regex=False)
            )
            df['monto_total'] = pd.to_numeric(df['monto_total'], errors='coerce').fillna(0)
        else:
            for c in df.columns:
                s = pd.to_numeric(df[c].astype(str).str.replace(r'[^\d]', '', regex=True), errors='coerce')
                if s.sum() > 0:
                    df['monto_total'] = s.fillna(0)
                    break

        df['rut_cliente'] = df['rut'].astype(str).apply(lambda x: extraer_rut_o_nombre(x) if 'NO_DETECTADO' not in extraer_rut_o_nombre(x) else x.replace('.', '').upper())

        df_final = df.rename(columns={
            'folio': 'Folio',
            'rut_cliente': 'RUT Cliente',
            'razon_social': 'Razón Social',
            'monto_total': 'Monto Total'
        })

        cols_finales = ['Folio', 'RUT Cliente', 'Razón Social', 'Monto Total']
        return df_final[cols_finales].reset_index(drop=True), "OK"

    except Exception as e:
        return None, f"Error al procesar ventas: {str(e)}"


# ---------------------------------------------------------
# 2. INTERFAZ GRÁFICA DE USUARIO (FRONT-END)
# ---------------------------------------------------------

with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestión Financiera")
    st.divider()
    empresa = st.text_input("Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    st.divider()
    st.info("💡 **Automatización:** Sube la cartola bancaria y el registro de ventas para conciliar de forma automática.")

st.title("📊 Panel de Conciliación y Control de Cuentas")
st.markdown(f"**Cliente:** `{empresa}` | **Período:** `{periodo.strftime('%m/%Y')}`")
st.divider()

st.subheader("1. Carga de Documentos Fuente")

col_cartola, col_ventas = st.columns(2)

with col_cartola:
    st.markdown("##### 🏛️ Cartola Bancaria (Ingresos)")
    archivo_cartola = st.file_uploader(
        "Arrastra o selecciona el PDF / Excel del banco",
        type=["pdf", "xlsx", "xls", "csv"],
        key="cartola_input"
    )

with col_ventas:
    st.markdown("##### 📄 Registro de Ventas (SII / ERP)")
    archivo_ventas = st.file_uploader(
        "Arrastra o selecciona el Excel de ventas emitidas",
        type=["xlsx", "xls", "csv"],
        key="ventas_input"
    )

st.divider()

tab1, tab2 = st.tabs(["🏛️ Cartola Bancaria Normalizada", "📄 Registro de Ventas Normalizado"])

with tab1:
    if archivo_cartola is not None:
        df_cartola, df_incompletos, estado_cartola = normalizar_cartola(archivo_cartola)
        
        if estado_cartola == "OK":
            total_ingresos = df_cartola['Monto Pago'].sum() if not df_cartola.empty and 'Monto Pago' in df_cartola.columns else 0
            
            col_kpi, col_info = st.columns([1, 2])
            with col_kpi:
                st.metric("Total Ingresos Confirmados", f"$ {total_ingresos:,.0f}".replace(",", "."))
            with col_info:
                st.success(f"¡Cartola procesada correctamente! Se identificaron **{len(df_cartola)}** abonos válidos.")

            st.divider()
            
            if not df_cartola.empty:
                st.markdown("##### 📋 Listado Completo de Transacciones Procesadas")
                st.dataframe(
                    df_cartola.style.format({'Monto Pago': '$ {:,.0f}'}), 
                    use_container_width=True,
                    hide_index=True,
                    height=450
                )

            if df_incompletos is not None and not df_incompletos.empty:
                st.warning(f"⚠️ **Atención:** Se detectaron **{len(df_incompletos)}** fila(s) pendientes o que requieren revisión manual.")
                with st.expander("🔍 Ver transacciones para revisión manual", expanded=False):
                    st.dataframe(df_incompletos, use_container_width=True, hide_index=True)
        else:
            st.error(f"Error al leer Cartola: {estado_cartola}")
    else:
        st.info("Sube un archivo de cartola bancaria en la sección superior para visualizar los datos.")

with tab2:
    if archivo_ventas is not None:
        df_ventas, estado_ventas = normalizar_ventas(archivo_ventas)
        if estado_ventas == "OK" and df_ventas is not None:
            total_ventas = df_ventas['Monto Total'].sum() if not df_ventas.empty and 'Monto Total' in df_ventas.columns else 0
            
            col_kpi_v, col_info_v = st.columns([1, 2])
            with col_kpi_v:
                st.metric("Total Ventas Emitidas", f"$ {total_ventas:,.0f}".replace(",", "."))
            with col_info_v:
                st.success(f"¡Ventas procesadas correctamente! Se cargaron **{len(df_ventas)}** facturas.")

            st.divider()

            if not df_ventas.empty:
                st.markdown("##### 📋 Registro de Ventas Normalizado")
                st.dataframe(
                    df_ventas.style.format({'Monto Total': '$ {:,.0f}'}), 
                    use_container_width=True,
                    hide_index=True,
                    height=450
                )
        else:
            st.error(f"Error al leer Ventas: {estado_ventas}")
    else:
        st.info("Sube un archivo de registro de ventas en la sección superior para visualizar los datos.")
