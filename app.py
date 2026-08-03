import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber
import io

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
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
    }
    
    div[data-testid="stFileUploader"] button, .stButton > button, div[data-testid="stDownloadButton"] > button {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important;
        color: #ffffff !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 10px 22px !important;
    }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #4f46e5;
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
# FUNCIONES AUXILIARES Y EXTRACTION DE TEXTO
# ---------------------------------------------------------

def extraer_rut_o_nombre(texto):
    """Detecta RUTs o Nombres/Razones Sociales en glosas bancarias."""
    if not isinstance(texto, str) or not texto.strip():
        return "NO_DETECTADO"

    match_prov = re.search(r'Pago:\s*Proveedores\s+0?(\d{7,8})([\dkK])\b', texto, re.IGNORECASE)
    if match_prov:
        body, dv = match_prov.group(1), match_prov.group(2).upper()
        return f"{int(body)}-{dv}"

    match_std = re.search(r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b', texto)
    if match_std:
        rut_raw = match_std.group(0).replace('.', '').upper()
        if '-' not in rut_raw:
            rut_raw = rut_raw[:-1] + '-' + rut_raw[-1]
        return rut_raw

    match_continuo = re.search(r'\b0?(\d{7,8}[\dkK])\b', texto)
    if match_continuo:
        raw = match_continuo.group(1).upper()
        return f"{int(raw[:-1])}-{raw[-1]}"

    match_nombre = re.search(r'(?:Traspaso De:|Pago:|Transferencia de:)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip()
        nombre = re.sub(r'\s+(Internet|Cta|Cuenta|Transferencia|Oficina|Central).*$', '', nombre, flags=re.IGNORECASE)
        return nombre[:35].strip()
        
    return texto.strip()[:35]


def extraer_monto_chileno_estricto(texto_o_celda):
    """Extrae montos numéricos limpios descartando RUTs o folios."""
    if pd.isna(texto_o_celda) or str(texto_o_celda).strip() in ['', 'None', 'nan', '0']:
        return None

    if isinstance(texto_o_celda, (int, float)):
        val = int(round(float(texto_o_celda)))
        return val if val > 0 else None

    texto = str(texto_o_celda).strip()
    texto_limpio = re.sub(r'\b\d{7,8}-[\dkK]\b', '', texto)
    texto_limpio = re.sub(r'Pago:\s*Proveedores\s+\d+[\dkK]?', '', texto_limpio, flags=re.IGNORECASE)

    coincidencias = re.findall(r'\b\d{1,3}(?:[.,]\d{3})+\b', texto_limpio)
    if coincidencias:
        monto_str = coincidencias[-1].replace('.', '').replace(',', '')
        try:
            val = int(monto_str)
            if 0 < val < 500000000:
                return val
        except ValueError:
            pass

    match_pesos = re.search(r'\$\s*([\d\.,]+)', texto_limpio)
    if match_pesos:
        monto_str = match_pesos.group(1).replace('.', '').replace(',', '')
        try:
            val = int(monto_str)
            if 0 < val < 500000000:
                return val
        except ValueError:
            pass

    match_entero = re.search(r'\b(\d{5,9})\b', texto_limpio)
    if match_entero:
        try:
            val = int(match_entero.group(1))
            if 1000 < val < 500000000:
                return val
        except ValueError:
            pass

    return None


# ---------------------------------------------------------
# PROCESAMIENTO DE CARTOLA BANCARIA
# ---------------------------------------------------------

def normalizar_cartola(archivo_subido):
    nombre_archivo = archivo_subido.name.lower()
    registros_ok = []
    registros_dudosos = []

    palabras_cabecera_estricta = [
        'saldo inicial', 'saldo final', 'cartola de cuenta', 
        'canal o sucursal', 'nro. docto', 'abonos (clp)', 
        'monto abono', 'fecha descripción', 'movimientos', 'encabezado de cuenta'
    ]

    try:
        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for num_pag, pagina in enumerate(pdf.pages, start=1):
                    texto_pag = pagina.extract_text() or ""
                    lineas_texto = [l.strip() for l in texto_pag.split('\n') if l.strip()]

                    tablas = pagina.extract_tables()
                    lineas_tabla = []
                    for tabla in tablas:
                        for fila in tabla:
                            if fila:
                                f_clean = [str(c).strip().replace('\n', ' ') for c in fila if c is not None and str(c).strip() != '']
                                if f_clean:
                                    lineas_tabla.append(" ".join(f_clean))

                    lineas_a_procesar = lineas_texto if len(lineas_texto) >= len(lineas_tabla) else lineas_tabla

                    for texto_fila in lineas_a_procesar:
                        texto_lower = texto_fila.lower()
                        es_cabecera = any(cabe in texto_lower for cabe in palabras_cabecera_estricta)
                        has_fecha = bool(re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila))

                        if es_cabecera and not has_fecha:
                            continue

                        match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                        fecha = match_fecha.group(0) if match_fecha else None
                        identificador = extraer_rut_o_nombre(texto_fila)
                        monto_encontrado = extraer_monto_chileno_estricto(texto_fila)

                        if fecha and monto_encontrado:
                            registros_ok.append({
                                'Fecha': fecha,
                                'Identificador / Cliente': identificador,
                                'Monto Pago': monto_encontrado,
                                'Descripción Glosa': texto_fila[:120]
                            })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                m = extraer_monto_chileno_estricto(texto_fila)
                identificador = extraer_rut_o_nombre(texto_fila)
                match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                fecha = match_fecha.group(0) if match_fecha else "VER_EXCEL"

                if m is not None:
                    registros_ok.append({
                        'Fecha': fecha,
                        'Identificador / Cliente': identificador,
                        'Monto Pago': m,
                        'Descripción Glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).reset_index(drop=True) if registros_ok else pd.DataFrame()
        df_dudosos = pd.DataFrame(registros_dudosos).reset_index(drop=True) if registros_dudosos else pd.DataFrame()

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Error al procesar cartola: {str(e)}"


# ---------------------------------------------------------
# PROCESAMIENTO DE REGISTRO DE VENTAS
# ---------------------------------------------------------

def normalizar_ventas(archivo_subido):
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
            return None, "Formato de archivo no soportado."

        if df_raw.empty:
            return None, "El archivo está vacío."

        # Detectar la fila que contiene los encabezados reales
        header_row_idx = None
        for idx in range(min(12, len(df_raw))):
            row_str = " ".join([str(val).lower() for val in df_raw.iloc[idx].values if pd.notna(val)])
            if any(k in row_str for k in ['deudor', 'clte', 'cliente', 'receptor', 'nro.docto', 'folio', 'rut', 'razon social']):
                header_row_idx = idx
                break

        if header_row_idx is not None and header_row_idx > 0:
            new_headers = df_raw.iloc[header_row_idx].values
            df_raw = df_raw.iloc[header_row_idx + 1:].copy()
            df_raw.columns = new_headers

        cols_clean = {c: str(c).strip() for c in df_raw.columns if pd.notna(c)}
        df_raw = df_raw.rename(columns=cols_clean)

        col_folio = next((c for c in df_raw.columns if any(k in c.lower() for k in ['folio', 'nro.docto', 'nro_docto', 'nro factura', 'num_docto'])), None)
        col_monto = next((c for c in df_raw.columns if any(k in c.lower() for k in ['monto total', 'v. docto.', 'v_docto', 'v.adeudado', 'total', 'monto'])), None)

        df_final = pd.DataFrame()
        df_final['Folio'] = df_raw[col_folio].astype(str).str.split('.').str[0] if col_folio else [f"{i+1}" for i in range(len(df_raw))]
        df_final['Monto Total'] = df_raw[col_monto].apply(lambda x: extraer_monto_chileno_estricto(x) or 0) if col_monto else 0

        # Guardar la fila completa como texto plano para búsquedas globales
        def construir_texto_consolidado(row):
            return " ".join([str(val) for val in row.values if pd.notna(val)])

        df_final['Texto_Fila_Completo'] = df_raw.apply(construir_texto_consolidado, axis=1)

        # Nombre visual de referencia
        nom_cols = [c for c in df_raw.columns if any(k in c.lower() for k in ['nombre', 'razon', 'cliente', 'deudor', 'receptor'])]
        if nom_cols:
            df_final['Nombre Cliente'] = df_raw[nom_cols[-1]].astype(str).str.strip().str.upper()
        else:
            df_final['Nombre Cliente'] = "CLIENTE DETECTADO"

        return df_final, "OK"

    except Exception as e:
        return None, f"Error al procesar ventas: {str(e)}"


# ---------------------------------------------------------
# MOTOR DE CONCILIACIÓN POR FUERZA BRUTA DE TOKENS
# ---------------------------------------------------------

def conciliar_informacion_flexible(df_cartola, df_ventas):
    """
    Motor de coincidencia directa buscando palabras clave de la glosa 
    dentro del texto completo de cada fila del Excel de ventas.
    """
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    facturas_usadas = set()

    # Palabras a ignorar para no confundir términos bancarios con empresas
    palabras_ignorar = {
        'TRASPASO', 'TRANSFERENCIA', 'PAGO', 'PROVEEDORES', 'INTERNET', 
        'BANCO', 'DE', 'DEL', 'POR', 'CTA', 'CUENTA', 'OFICINA', 'CENTRAL',
        'ABONO', 'CARGO', 'CHILE', 'SANTANDER', 'ESTADO', 'BCI'
    }

    for idx_c, row_c in df_cartola.iterrows():
        glosa_raw = str(row_c['Descripción Glosa']).upper()
        identificador_raw = str(row_c['Identificador / Cliente']).upper()
        monto_pago = float(row_c['Monto Pago'])

        # Extraer palabras relevantes de la glosa bancaria
        tokens_glosa = [
            p for p in re.findall(r'[A-Z0-9]+', glosa_raw) 
            if len(p) >= 3 and p not in palabras_ignorar
        ]

        ventas_disponibles = df_ventas[~df_ventas['Folio'].isin(facturas_usadas)].copy()
        match_final = pd.DataFrame()

        # 1. BÚSQUEDA DE PALABRAS EN EL TEXTO COMPLETO DE LA FILA DEL EXCEL
        indices_coincidentes = []
        for idx_v, row_v in ventas_disponibles.iterrows():
            texto_fila_v = str(row_v['Texto_Fila_Completo']).upper()
            
            # Verificar si alguna palabra clave (ej. PRODRILLING) existe en la fila
            for token in tokens_glosa:
                if token in texto_fila_v:
                    indices_coincidentes.append(idx_v)
                    break

        coincidencias_cliente = ventas_disponibles.loc[indices_coincidentes] if indices_coincidentes else pd.DataFrame()

        # 2. EVALUACIÓN DE MONTO
        if not coincidencias_cliente.empty:
            match_exacto = coincidencias_cliente[coincidencias_cliente['Monto Total'] == monto_pago]
            if not match_exacto.empty:
                match_final = match_exacto.head(1)
            else:
                # Si no hay monto exacto, tomar la factura de ese cliente con la menor diferencia
                coincidencias_cliente = coincidencias_cliente.copy()
                coincidencias_cliente['dif_abs'] = (coincidencias_cliente['Monto Total'] - monto_pago).abs()
                match_final = coincidencias_cliente.sort_values(by='dif_abs').head(1)
        else:
            # RESCATE GLOBAL: Si el nombre venía distorsionado, buscar por MONTO EXACTO
            match_monto = ventas_disponibles[ventas_disponibles['Monto Total'] == monto_pago]
            if not match_monto.empty:
                match_final = match_monto.head(1)

        # 3. REGISTRO DEL RESULTADO
        if not match_final.empty:
            f_row = match_final.iloc[0]
            facturas_usadas.add(f_row['Folio'])
            dif = monto_pago - f_row['Monto Total']
            estado = '🟢 Conciliado Exacto' if abs(dif) < 0.01 else '🟡 Diferencia en Monto'
            
            cruce_list.append({
                'Fecha Banco': row_c['Fecha'],
                'Identificador Cartola': identificador_raw,
                'Monto Banco ($)': monto_pago,
                'Folio Factura': f_row['Folio'],
                'Entidad Matcheada': f_row.get('Nombre Cliente', 'CLIENTE ENCONTRADO'),
                'Monto Factura ($)': f_row['Monto Total'],
                'Diferencia ($)': dif,
                'Estado Conciliación': estado
            })
        else:
            cruce_list.append({
                'Fecha Banco': row_c['Fecha'],
                'Identificador Cartola': identificador_raw,
                'Monto Banco ($)': monto_pago,
                'Folio Factura': 'N/A',
                'Entidad Matcheada': 'NO ENCONTRADO',
                'Monto Factura ($)': 0,
                'Diferencia ($)': monto_pago,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_ventas[~df_ventas['Folio'].isin(facturas_usadas)].copy()
    if not ventas_pendientes.empty:
        ventas_pendientes['Estado'] = '🔵 Documento Pendiente de Pago'

    return df_cruce, ventas_pendientes


def generar_excel_descarga(df_cartola, df_incompletos, df_ventas, df_cruce, df_pendientes, empresa, periodo_str):
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

    return output.getvalue()


# ---------------------------------------------------------
# INTERFAZ GRÁFICA DE USUARIO
# ---------------------------------------------------------

with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestión Financiera")
    st.divider()
    empresa = st.text_input("Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    periodo_fmt = periodo.strftime('%m/%Y')
    st.divider()

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
        if estado_cartola == "OK" and not df_cartola_global.empty:
            total_ingresos = df_cartola_global['Monto Pago'].sum()
            
            col_kpi, col_info = st.columns([1, 2])
            with col_kpi:
                st.metric("Total Ingresos Confirmados", f"$ {total_ingresos:,.0f}".replace(",", "."))
            with col_info:
                st.success(f"¡Cartola procesada! Se identificaron **{len(df_cartola_global)}** abonos válidos.")

            st.divider()
            st.dataframe(
                df_cartola_global.style.format({'Monto Pago': '$ {:,.0f}'}), 
                use_container_width=True, hide_index=True, height=400
            )
        else:
            st.error("No se detectaron movimientos en la cartola.")
    else:
        st.info("Sube la cartola bancaria en la sección superior para visualizar los datos.")

with tab2:
    if archivo_ventas is not None:
        df_ventas_global, estado_ventas = normalizar_ventas(archivo_ventas)
        if estado_ventas == "OK" and df_ventas_global is not None:
            total_ventas = df_ventas_global['Monto Total'].sum()
            
            col_kpi_v, col_info_v = st.columns([1, 2])
            with col_kpi_v:
                st.metric("Total Ventas / Cartera", f"$ {total_ventas:,.0f}".replace(",", "."))
            with col_info_v:
                st.success(f"¡Documentos procesados! Se cargaron **{len(df_ventas_global)}** registros de forma limpia.")

            st.divider()
            st.dataframe(
                df_ventas_global[['Folio', 'Nombre Cliente', 'Monto Total']].style.format({'Monto Total': '$ {:,.0f}'}), 
                use_container_width=True, hide_index=True, height=400
            )
        else:
            st.error(f"Error: {estado_ventas}")
    else:
        st.info("Sube el registro de ventas o cartera de documentos en la sección superior.")

# TAB 3: CRUCE Y CONCILIACIÓN
df_cruce_global = pd.DataFrame()
df_pendientes_global = pd.DataFrame()

with tab3:
    if not df_cartola_global.empty and df_ventas_global is not None and not df_ventas_global.empty:
        df_cruce_global, df_pendientes_global = conciliar_informacion_flexible(df_cartola_global, df_ventas_global)

        col_m1, col_m2, col_m3 = st.columns(3)
        conciliados_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🟢 Conciliado Exacto'])
        diferencias_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🟡 Diferencia en Monto'])
        no_id_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'] == '🔴 Abono No Identificado'])

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
                df_pendientes_global[['Folio', 'Nombre Cliente', 'Monto Total', 'Estado']].style.format({'Monto Total': '$ {:,.0f}'}),
                use_container_width=True,
                hide_index=True
            )
    else:
        st.info("⚠️ Sube la Cartola Bancaria y el Registro de Ventas para ver el cruce automático.")

# EXPORTACIÓN
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

