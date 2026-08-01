import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber
import io

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
    
    div[data-testid="stFileUploader"] button, .stButton > button, div[data-testid="stDownloadButton"] > button {
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
# 1. FUNCIONES MOTORAS DE EXTRACCIÓN Y NORMALIZACIÓN
# ---------------------------------------------------------

def extraer_rut_o_nombre(texto):
    """Detecta RUTs o razón social en textos y glosas."""
    if not isinstance(texto, str):
        return "NO_DETECTADO"
    
    match_std = re.search(r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b', texto)
    if match_std:
        rut_raw = match_std.group(0).replace('.', '').upper()
        if '-' not in rut_raw:
            rut_raw = rut_raw[:-1] + '-' + rut_raw[-1]
        return rut_raw

    match_continuo = re.search(r'\b0?(\d{7,8}[\dkK])\b', texto)
    if match_continuo:
        raw = match_continuo.group(1).upper()
        return f"{raw[:-1]}-{raw[-1]}"

    match_nombre = re.search(r'(?:Traspaso De:|Pago:)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip()
        nombre = re.sub(r'\s+(Internet|Cta|Cuenta|Transferencia|Oficina).*$', '', nombre, flags=re.IGNORECASE)
        return nombre[:35]
        
    return "NO_DETECTADO"


def extraer_monto_chileno(texto_o_celda):
    """Extrae y convierte cualquier formato de monto a un entero limpio."""
    if pd.isna(texto_o_celda) or str(texto_o_celda).strip() in ['', 'None', 'nan', '0']:
        return 0

    if isinstance(texto_o_celda, (int, float)):
        return int(round(float(texto_o_celda)))

    texto = str(texto_o_celda).strip()
    texto_limpio = re.sub(r'[,.]00$', '', texto)
    
    coincidencias = re.findall(r'\b\d{1,3}(?:[.,]\d{3})+\b', texto_limpio)
    if coincidencias:
        monto_str = coincidencias[-1].replace('.', '').replace(',', '')
        try:
            return int(monto_str)
        except ValueError:
            pass

    enteros = re.findall(r'\b\d{1,10}\b', texto_limpio)
    if enteros:
        try:
            return int(enteros[-1])
        except ValueError:
            pass
        
    return 0


def normalizar_cartola(archivo_subido):
    """Lee y estandariza la cartola bancaria en PDF, Excel o CSV."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        registros_ok = []
        registros_dudosos = []

        palabras_ignorar = [
            'saldo inicial', 'saldo final', 'cartola de cuenta', 
            'canal o sucursal', 'nro. docto', 'abonos (clp)', 
            'monto abono', 'fecha descripción', 'movimientos'
        ]

        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for num_pag, pagina in enumerate(pdf.pages, start=1):
                    tablas = pagina.extract_tables()
                    for tabla in tablas:
                        for fila in tabla:
                            if not fila:
                                continue
                            
                            f_clean = [str(c).strip().replace('\n', ' ') for c in fila if c is not None and str(c).strip() != '']
                            texto_fila = " ".join(f_clean)
                            texto_lower = texto_fila.lower()
                            
                            if not f_clean or any(p in texto_lower for p in palabras_ignorar):
                                continue
                            
                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            fecha = match_fecha.group(0) if match_fecha else "S/F"
                            
                            monto_encontrado = None
                            for celda in reversed(f_clean):
                                m = extraer_monto_chileno(celda)
                                if m > 0:
                                    monto_encontrado = m
                                    break
                            
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
                                if len(texto_fila) > 10:
                                    registros_dudosos.append({
                                        'Página': num_pag,
                                        'Fecha': fecha,
                                        'Glosa Capturada': texto_fila[:100],
                                        'Observación': 'Fila incompleta o monto no detectado'
                                    })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                m = extraer_monto_chileno(texto_fila)
                if m > 0:
                    registros_ok.append({
                        'Fecha': 'VER_EXCEL',
                        'Identificador / Cliente': extraer_rut_o_nombre(texto_fila),
                        'Monto Pago': m,
                        'Descripción Glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).reset_index(drop=True) if registros_ok else pd.DataFrame(columns=['Fecha', 'Identificador / Cliente', 'Monto Pago', 'Descripción Glosa'])
        df_dudosos = pd.DataFrame(registros_dudosos).reset_index(drop=True) if registros_dudosos else pd.DataFrame(columns=['Página', 'Fecha', 'Glosa Capturada', 'Observación'])

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Error al procesar cartola: {str(e)}"


def normalizar_ventas(archivo_subido):
    """Lee y estandariza dinámicamente cualquier Registro de Ventas o Cartera de Documentos."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        if nombre_archivo.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(archivo_subido)
        elif nombre_archivo.endswith('.csv'):
            try:
                df_raw = pd.read_csv(archivo_subido)
            except Exception:
                df_raw = pd.read_csv(archivo_subido, sep=';', encoding='latin1')
        else:
            return None, "Formato no soportado para el registro de ventas."

        if df_raw.empty:
            return None, "El archivo de ventas está vacío."

        # Detectar la fila de encabezados si hay filas vacías o con títulos institucionales arriba
        header_row_idx = None
        for idx in range(min(10, len(df_raw))):
            row_str = " ".join([str(val).lower() for val in df_raw.iloc[idx].values if pd.notna(val)])
            if any(k in row_str for k in ['rut', 'cliente', 'deudor', 'docto', 'factura', 'monto', 'total', 'v. docto']):
                header_row_idx = idx
                break

        if header_row_idx is not None and header_row_idx > 0:
            new_headers = df_raw.iloc[header_row_idx].values
            df_raw = df_raw.iloc[header_row_idx + 1:].copy()
            df_raw.columns = new_headers

        # Diccionario ampliado de sinónimos para detectar columnas de SII, ERPs y Factoring/Cartera
        mapa_cols = {
            'folio': [
                'nro.docto', 'nro.docto.', 'nro_docto', 'nro.op.', 'folio', 'nro_factura', 
                'numero', 'número', 'nro', 'factura', 'doc_num', 'docto', 'comprobante'
            ],
            'rut': [
                'rut. deudor', 'rut_deudor', 'rut deudor', 'rut. clte', 'rut_clte', 'rut clte',
                'rut', 'rut_cliente', 'rut cliente', 'rut emisor', 'rut_receptor', 'rut receptor'
            ],
            'razon_social': [
                'nombre deudor', 'nombre_deudor', 'deudor', 'nombre cliente', 'nombre_cliente', 
                'razon_social', 'razon social', 'razón social', 'cliente', 'receptor'
            ],
            'monto_total': [
                'v. docto.', 'v_docto', 'v. docto', 'v.adeudado', 'v_adeudado', 'mto.abono',
                'monto_total', 'total', 'monto total', 'monto', 'valor_total', 'total_con_iva'
            ]
        }

        col_map = {}
        for col_std, sinonimos in mapa_cols.items():
            for c in df_raw.columns:
                c_clean = str(c).lower().strip().replace('\n', ' ')
                if c_clean in sinonimos and c not in col_map:
                    col_map[c] = col_std
                    break

        df = df_raw.rename(columns=col_map)

        # Asignar valores por defecto si alguna columna no estuvo en el archivo
        if 'folio' not in df.columns:
            df['folio'] = [f"F-{i+1}" for i in range(len(df))]
        if 'rut' not in df.columns:
            df['rut'] = "S/RUT"
        if 'razon_social' not in df.columns:
            df['razon_social'] = "CLIENTE DESCONOCIDO"
        if 'monto_total' not in df.columns:
            df['monto_total'] = 0

        # Limpiar y convertir montos
        df['monto_total'] = df['monto_total'].apply(extraer_monto_chileno)

        # Normalizar el formato del RUT y nombres
        df['rut_cliente'] = df['rut'].astype(str).apply(
            lambda x: extraer_rut_o_nombre(x) if 'NO_DETECTADO' not in extraer_rut_o_nombre(x) else x.replace('.', '').upper().strip()
        )
        df['razon_social'] = df['razon_social'].astype(str).str.strip()

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


def conciliar_informacion(df_cartola, df_ventas):
    """Realiza el cruce automático entre la cartola y las facturas de venta."""
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    facturas_usadas = set()

    for idx_c, row_c in df_cartola.iterrows():
        id_cliente = str(row_c['Identificador / Cliente']).strip().upper()
        monto_pago = float(row_c['Monto Pago'])
        
        coincidencias = df_ventas[
            (df_ventas['RUT Cliente'].str.upper() == id_cliente) | 
            (df_ventas['Razón Social'].str.upper().str.contains(id_cliente, regex=False, na=False))
        ]

        if not coincidencias.empty:
            match_exacto = coincidencias[coincidencias['Monto Total'] == monto_pago]
            if not match_exacto.empty:
                f_row = match_exacto.iloc[0]
                facturas_usadas.add(f_row['Folio'])
                cruce_list.append({
                    'Fecha Banco': row_c['Fecha'],
                    'Cliente / RUT Cartola': id_cliente,
                    'Monto Banco ($)': monto_pago,
                    'Folio Factura': f_row['Folio'],
                    'Monto Factura ($)': f_row['Monto Total'],
                    'Diferencia ($)': 0,
                    'Estado Conciliación': '🟢 Conciliado Exacto'
                })
            else:
                f_row = coincidencias.iloc[0]
                facturas_usadas.add(f_row['Folio'])
                dif = monto_pago - f_row['Monto Total']
                cruce_list.append({
                    'Fecha Banco': row_c['Fecha'],
                    'Cliente / RUT Cartola': id_cliente,
                    'Monto Banco ($)': monto_pago,
                    'Folio Factura': f_row['Folio'],
                    'Monto Factura ($)': f_row['Monto Total'],
                    'Diferencia ($)': dif,
                    'Estado Conciliación': '🟡 Diferencia en Monto'
                })
        else:
            cruce_list.append({
                'Fecha Banco': row_c['Fecha'],
                'Cliente / RUT Cartola': id_cliente,
                'Monto Banco ($)': monto_pago,
                'Folio Factura': 'N/A',
                'Monto Factura ($)': 0,
                'Diferencia ($)': monto_pago,
                'Estado Conciliación': '🔴 Abono No Identificado en Ventas'
            })

    df_cruce = pd.DataFrame(cruce_list)

    # Facturas pendientes de pago
    ventas_pendientes = df_ventas[~df_ventas['Folio'].isin(facturas_usadas)].copy()
    if not ventas_pendientes.empty:
        ventas_pendientes['Estado'] = '🔵 Factura Pendiente de Pago'

    return df_cruce, ventas_pendientes


def generar_excel_descarga(df_cartola, df_incompletos, df_ventas, df_cruce, df_pendientes, empresa, periodo_str):
    """Genera el reporte de Excel completo con los resultados del cruce."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not df_cruce.empty:
            df_cruce.to_excel(writer, sheet_name='Detalle Cruce Conciliación', index=False)
            
        if not df_pendientes.empty:
            df_pendientes.to_excel(writer, sheet_name='Ventas Pendientes Cobro', index=False)

        if not df_cartola.empty:
            df_cartola.to_excel(writer, sheet_name='Cartola Bancaria', index=False)

        if df_ventas is not None and not df_ventas.empty:
            df_ventas.to_excel(writer, sheet_name='Registro Ventas', index=False)

        if df_incompletos is not None and not df_incompletos.empty:
            df_incompletos.to_excel(writer, sheet_name='Revisiones Pendientes', index=False)

    return output.getvalue()


# ---------------------------------------------------------
# 2. INTERFAZ GRÁFICA DE USUARIO (STREAMLIT)
# ---------------------------------------------------------

with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestión Financiera")
    st.divider()
    empresa = st.text_input("Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    periodo_fmt = periodo.strftime('%m/%Y')
    st.divider()
    st.info("💡 **Sistema Adaptativo:** Soporta formatos de SII, ERPs, bancos y carteras de facturas.")

st.title("📊 Panel de Conciliación y Control de Cuentas")
st.markdown(f"**Cliente:** `{empresa}` | **Período:** `{periodo_fmt}`")
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
    st.markdown("##### 📄 Registro de Ventas (SII / ERP / Cartera)")
    archivo_ventas = st.file_uploader(
        "Arrastra o selecciona el Excel o CSV de ventas / cartera",
        type=["xlsx", "xls", "csv"],
        key="ventas_input"
    )

st.divider()

df_cartola_global = pd.DataFrame()
df_incompletos_global = pd.DataFrame()
df_ventas_global = None

tab1, tab2, tab3 = st.tabs([
    "🏛️ Cartola Bancaria Normalizada", 
    "📄 Registro de Ventas Normalizado", 
    "🔀 Cruce y Conciliación Automática"
])

with tab1:
    if archivo_cartola is not None:
        df_cartola_global, df_incompletos_global, estado_cartola = normalizar_cartola(archivo_cartola)
        if estado_cartola == "OK":
            total_ingresos = df_cartola_global['Monto Pago'].sum() if not df_cartola_global.empty else 0
            
            col_kpi, col_info = st.columns([1, 2])
            with col_kpi:
                st.metric("Total Ingresos Confirmados", f"$ {total_ingresos:,.0f}".replace(",", "."))
            with col_info:
                st.success(f"¡Cartola procesada correctamente! Se identificaron **{len(df_cartola_global)}** abonos válidos.")

            st.divider()
            
            if not df_cartola_global.empty:
                st.dataframe(
                    df_cartola_global.style.format({'Monto Pago': '$ {:,.0f}'}), 
                    use_container_width=True, hide_index=True, height=400
                )

            if df_incompletos_global is not None and not df_incompletos_global.empty:
                st.warning(f"⚠️ **Atención:** Se detectaron **{len(df_incompletos_global)}** fila(s) para revisión manual.")
                with st.expander("🔍 Ver transacciones para revisión manual", expanded=False):
                    st.dataframe(df_incompletos_global, use_container_width=True, hide_index=True)
        else:
            st.error(f"Error: {estado_cartola}")
    else:
        st.info("Sube la cartola bancaria en la sección superior para visualizar los datos.")

with tab2:
    if archivo_ventas is not None:
        df_ventas_global, estado_ventas = normalizar_ventas(archivo_ventas)
        if estado_ventas == "OK" and df_ventas_global is not None:
            total_ventas = df_ventas_global['Monto Total'].sum() if not df_ventas_global.empty else 0
            
            col_kpi_v, col_info_v = st.columns([1, 2])
            with col_kpi_v:
                st.metric("Total Ventas / Cartera", f"$ {total_ventas:,.0f}".replace(",", "."))
            with col_info_v:
                st.success(f"¡Documentos procesados correctamente! Se cargaron **{len(df_ventas_global)}** registros.")

            st.divider()

            if not df_ventas_global.empty:
                st.dataframe(
                    df_ventas_global.style.format({'Monto Total': '$ {:,.0f}'}), 
                    use_container_width=True, hide_index=True, height=400
                )
        else:
            st.error(f"Error: {estado_ventas}")
    else:
        st.info("Sube el registro de ventas o cartera de documentos en la sección superior.")

# ---------------------------------------------------------
# TAB 3: CRUCE Y CONCILIACIÓN
# ---------------------------------------------------------
df_cruce_global = pd.DataFrame()
df_pendientes_global = pd.DataFrame()

with tab3:
    if not df_cartola_global.empty and df_ventas_global is not None and not df_ventas_global.empty:
        df_cruce_global, df_pendientes_global = conciliar_informacion(df_cartola_global, df_ventas_global)

        col_m1, col_m2, col_m3 = st.columns(3)
        conciliados_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🟢 Conciliado Exacto'])
        diferencias_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🟡 Diferencia en Monto'])
        no_id_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🔴 Abono No Identificado en Ventas'])

        with col_m1:
            st.metric("🟢 Pagos Conciliados", f"{conciliados_count} transacciones")
        with col_m2:
            st.metric("🟡 Con Diferencia de Monto", f"{diferencias_count} transacciones")
        with col_m3:
            st.metric("🔴 Abonos No Identificados", f"{no_id_count} transacciones")

        st.divider()

        st.markdown("##### 🔍 Detalle del Cruce (Cartola vs Facturas)")
        st.dataframe(
            df_cruce_global.style.format({
                'Monto Banco ($)': '$ {:,.0f}',
                'Monto Factura ($)': '$ {:,.0f}',
                'Diferencia ($)': '$ {:,.0f}'
            }),
            use_container_width=True,
            hide_index=True,
            height=400
        )

        if not df_pendientes_global.empty:
            st.markdown("##### 📄 Facturas Emitidas Pendientes de Pago")
            st.dataframe(
                df_pendientes_global.style.format({'Monto Total': '$ {:,.0f}'}),
                use_container_width=True,
                hide_index=True
            )

    else:
        st.info("⚠️ Para ejecutar el cruce automático, debes subir **ambos archivos**: la Cartola Bancaria y el Registro de Ventas.")

# ---------------------------------------------------------
# 3. SECCIÓN DE EXPORTACIÓN
# ---------------------------------------------------------
if not df_cartola_global.empty or df_ventas_global is not None:
    st.divider()
    st.subheader("📥 Exportar Informe Completo")
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        excel_bytes = generar_excel_descarga(
            df_cartola_global, df_incompletos_global, df_ventas_global, 
            df_cruce_global, df_pendientes_global, empresa, periodo_fmt
        )
        st.download_button(
            label="📊 Descargar Informe de Conciliación en Excel (.xlsx)",
            data=excel_bytes,
            file_name=f"Conciliacion_Completa_{empresa.replace(' ', '_')}_{periodo.strftime('%Y%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
    with col_exp2:
        if not df_cruce_global.empty:
            csv_bytes = df_cruce_global.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📄 Descargar Cruce de Datos en CSV",
                data=csv_bytes,
                file_name=f"Cruce_Conciliacion_{periodo.strftime('%Y%m')}.csv",
                mime="text/csv",
                use_container_width=True
            )

