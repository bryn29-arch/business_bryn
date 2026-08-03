import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber
import io
from itertools import combinations

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
# FUNCIONES AUXILIARES DE EXTRACCIÓN Y LIMPIEZA
# ---------------------------------------------------------

def limpiar_texto_para_match(texto):
    if not isinstance(texto, str) or not texto.strip():
        return ""
    t = texto.upper()
    siglas = [r'\bS\.?A\.?\b', r'\bS\.?P\.?A\.?\b', r'\bLTDA\.?\b', r'\bLIMITADA\b', r'\bE\.?I\.?R\.?L\.?\b']
    for sigla in siglas:
        t = re.sub(sigla, '', t)
    t = re.sub(r'[^A-Z0-9]', '', t)
    return t.strip()


def extraer_rut_o_nombre(texto):
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
        
    return "NO_DETECTADO"


def extraer_monto_chileno_estricto(texto_o_celda):
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


def buscar_combinacion_facturas(df_cliente, monto_pago, max_facturas=3):
    """Busca súper rápido si la suma de hasta 3 facturas cuadra exacto."""
    if df_cliente.empty:
        return pd.DataFrame()
        
    folios = df_cliente['Folio'].tolist()
    montos = df_cliente['Monto Total'].tolist()
    n = len(montos)
    
    if n > 10:
        folios = folios[:10]
        montos = montos[:10]
        n = 10

    for r in range(2, min(n + 1, max_facturas + 1)):
        for indices in combinations(range(n), r):
            suma_grupo = sum(montos[i] for i in indices)
            if abs(suma_grupo - monto_pago) < 1.0:
                folios_matcheados = [folios[i] for i in indices]
                return df_cliente[df_cliente['Folio'].isin(folios_matcheados)]
                
    return pd.DataFrame()


# ---------------------------------------------------------
# PROCESAMIENTO Y CRUCE CON CACHÉ DE STREAMLIT
# ---------------------------------------------------------

@st.cache_data(show_spinner=False)
def normalizar_cartola_cached(file_bytes, nombre_archivo):
    registros_ok = []
    registros_dudosos = []

    palabras_cabecera_estricta = [
        'saldo inicial', 'saldo final', 'cartola de cuenta', 
        'canal o sucursal', 'nro. docto', 'abonos (clp)', 
        'monto abono', 'fecha descripción', 'movimientos', 'encabezado de cuenta'
    ]

    try:
        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
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

                        if fecha and monto_encontrado and identificador != "NO_DETECTADO":
                            registros_ok.append({
                                'Fecha': fecha,
                                'Identificador / Cliente': identificador,
                                'Monto Pago': monto_encontrado,
                                'Descripción Glosa': texto_fila[:120]
                            })
                        else:
                            if len(texto_fila) > 15 and has_fecha and not es_cabecera:
                                motivo = []
                                if not monto_encontrado: motivo.append("Monto no detectado")
                                if identificador == "NO_DETECTADO": motivo.append("Cliente no identificado")

                                registros_dudosos.append({
                                    'Página': num_pag,
                                    'Fecha': fecha,
                                    'Glosa Capturada': texto_fila[:100],
                                    'Motivo Revisión': ", ".join(motivo)
                                })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(io.BytesIO(file_bytes)) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(io.BytesIO(file_bytes))
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                m = extraer_monto_chileno_estricto(texto_fila)
                identificador = extraer_rut_o_nombre(texto_fila)
                match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                fecha = match_fecha.group(0) if match_fecha else "VER_EXCEL"

                if m is not None and identificador != "NO_DETECTADO":
                    registros_ok.append({
                        'Fecha': fecha,
                        'Identificador / Cliente': identificador,
                        'Monto Pago': m,
                        'Descripción Glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).reset_index(drop=True) if registros_ok else pd.DataFrame(columns=['Fecha', 'Identificador / Cliente', 'Monto Pago', 'Descripción Glosa'])
        df_dudosos = pd.DataFrame(registros_dudosos).reset_index(drop=True) if registros_dudosos else pd.DataFrame(columns=['Página', 'Fecha', 'Glosa Capturada', 'Motivo Revisión'])

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Error al procesar cartola: {str(e)}"


@st.cache_data(show_spinner=False)
def normalizar_ventas_cached(file_bytes, nombre_archivo):
    try:
        if nombre_archivo.endswith(('.xlsx', '.xls')):
            df_raw = pd.read_excel(io.BytesIO(file_bytes))
        elif nombre_archivo.endswith('.csv'):
            try:
                df_raw = pd.read_csv(io.BytesIO(file_bytes))
            except Exception:
                df_raw = pd.read_csv(io.BytesIO(file_bytes), sep=';', encoding='latin1')
        else:
            return None, "Formato de archivo no soportado."

        if df_raw.empty:
            return None, "El archivo seleccionado está vacío."

        header_row_idx = None
        for idx in range(min(12, len(df_raw))):
            row_str = " ".join([str(val).lower() for val in df_raw.iloc[idx].values if pd.notna(val)])
            if any(k in row_str for k in ['deudor', 'clte', 'cliente', 'receptor', 'nro.docto', 'v. docto.', 'folio', 'rut', 'razon social']):
                header_row_idx = idx
                break

        if header_row_idx is not None and header_row_idx > 0:
            new_headers = df_raw.iloc[header_row_idx].values
            df_raw = df_raw.iloc[header_row_idx + 1:].copy()
            df_raw.columns = new_headers

        cols_clean = {c: str(c).strip() for c in df_raw.columns if pd.notna(c)}
        df_raw = df_raw.rename(columns=cols_clean)

        col_folio = None
        palabras_exclusion = [
            'tipo', 'especie', 'descripcion', 'descrip', 'monto', 'total', 
            'saldo', 'rut', 'nombre', 'razon', 'fecha', 'emision', 'venc', 
            'deudor', 'cliente', 'receptor', 'emisor', 'sucursal'
        ]

        candidatos_primarios = [
            c for c in df_raw.columns 
            if any(k in c.lower() for k in ['folio', 'nro.docto', 'nro_docto', 'nro. docto', 'nro factura', 'nro_factura', 'num_docto', 'num. docto'])
            and not any(ex in c.lower() for ex in palabras_exclusion)
        ]

        if candidatos_primarios:
            col_folio = candidatos_primarios[0]
        else:
            candidatos_secundarios = [
                c for c in df_raw.columns 
                if any(k in c.lower() for k in ['nro', 'num', 'docto', 'documento', 'factura'])
                and not any(ex in c.lower() for ex in palabras_exclusion)
            ]
            for cand in candidatos_secundarios:
                muestra = df_raw[cand].dropna().astype(str).head(10)
                numericos = [s for s in muestra if re.search(r'\b\d+\b', s.split('.')[0])]
                if len(numericos) >= len(muestra) * 0.5:
                    col_folio = cand
                    break

        col_monto = next((c for c in df_raw.columns if any(k in c.lower() for k in [
            'v. docto.', 'v_docto', 'v. docto', 'v.adeudado', 'monto_total', 'total', 'monto', 'saldo', 'monto total'
        ])), None)

        rut_cols = [c for c in df_raw.columns if 'rut' in c.lower()]
        nom_cols = [c for c in df_raw.columns if any(k in c.lower() for k in ['nombre', 'razon', 'razón', 'social', 'cliente', 'deudor', 'receptor', 'emisor', 'pagador']) and c not in rut_cols]

        df_final = pd.DataFrame()

        def extraer_numero_folio(val):
            if pd.isna(val):
                return ""
            val_str = str(val).strip()
            val_limpio = val_str.split('.')[0] if '.' in val_str else val_str
            numeros = re.findall(r'\d+', val_limpio)
            if numeros:
                return "".join(numeros)
            return val_str

        if col_folio:
            df_final['Folio'] = df_raw[col_folio].apply(extraer_numero_folio)
        else:
            df_final['Folio'] = [f"{i+1}" for i in range(len(df_raw))]

        if len(rut_cols) >= 1:
            df_final['RUT 1'] = df_raw[rut_cols[0]].astype(str).apply(lambda x: extraer_rut_o_nombre(x) if 'NO_DETECTADO' not in extraer_rut_o_nombre(x) else str(x).strip().upper())
        else:
            df_final['RUT 1'] = "S/RUT"

        if len(nom_cols) >= 1:
            df_final['Nombre 1'] = df_raw[nom_cols[0]].astype(str).str.strip().str.upper()
        else:
            df_final['Nombre 1'] = "N/A"

        if len(rut_cols) >= 2:
            df_final['RUT 2'] = df_raw[rut_cols[1]].astype(str).apply(lambda x: extraer_rut_o_nombre(x) if 'NO_DETECTADO' not in extraer_rut_o_nombre(x) else str(x).strip().upper())
            df_final['Nombre 2'] = df_raw[nom_cols[1]].astype(str).str.strip().str.upper() if len(nom_cols) >= 2 else "N/A"
            cols_ordenadas = ['Folio', 'RUT 1', 'Nombre 1', 'RUT 2', 'Nombre 2', 'Monto Total']
        else:
            cols_ordenadas = ['Folio', 'RUT 1', 'Nombre 1', 'Monto Total']

        df_final['Monto Total'] = df_raw[col_monto].apply(lambda x: extraer_monto_chileno_estricto(x) or 0) if col_monto else 0

        # Pre-calculo de nombres limpios para optimizar velocidad de cruce
        df_final['Nombre1_Limpio'] = df_final['Nombre 1'].apply(limpiar_texto_para_match)

        return df_final[cols_ordenadas + ['Nombre1_Limpio']].reset_index(drop=True), "OK"

    except Exception as e:
        return None, f"Error al procesar ventas: {str(e)}"


# CRUCE CON CACHÉ PARA EJECUCIÓN ULTRARRÁPIDA
@st.cache_data(show_spinner=False)
def conciliar_informacion_cached(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    facturas_usadas = set()

    for idx_c, row_c in df_cartola.iterrows():
        id_cartola = str(row_c['Identificador / Cliente']).strip().upper()
        id_cartola_limpio = limpiar_texto_para_match(id_cartola)
        monto_pago = float(row_c['Monto Pago'])
        
        ventas_disponibles = df_ventas[~df_ventas['Folio'].isin(facturas_usadas)]
        
        candidatos_cliente = pd.DataFrame()
        criterio_cliente = ""

        # Matching por RUT
        if 'RUT 1' in ventas_disponibles.columns:
            m1 = ventas_disponibles[ventas_disponibles['RUT 1'] == id_cartola]
            if not m1.empty:
                candidatos_cliente = m1
                criterio_cliente = "RUT 1"

        if candidatos_cliente.empty and 'RUT 2' in ventas_disponibles.columns:
            m2 = ventas_disponibles[ventas_disponibles['RUT 2'] == id_cartola]
            if not m2.empty:
                candidatos_cliente = m2
                criterio_cliente = "RUT 2"

        # Matching por Nombre
        if candidatos_cliente.empty and len(id_cartola_limpio) >= 3:
            mask_n1 = ventas_disponibles['Nombre1_Limpio'].str.contains(id_cartola_limpio, regex=False, na=False)
            if mask_n1.any():
                candidatos_cliente = ventas_disponibles[mask_n1]
                criterio_cliente = "Nombre 1 (Flex)"

        match_encontrado = False

        if not candidatos_cliente.empty:
            match_exacto_1a1 = candidatos_cliente[candidatos_cliente['Monto Total'] == monto_pago]
            
            if not match_exacto_1a1.empty:
                f_row = match_exacto_1a1.iloc[0]
                facturas_usadas.add(f_row['Folio'])
                cruce_list.append({
                    'Fecha Banco': row_c['Fecha'],
                    'Identificador Cartola': id_cartola,
                    'Monto Banco ($)': monto_pago,
                    'Folios Factura(s)': f_row['Folio'],
                    'Entidad Matcheada': f_row.get('Nombre 1', 'N/A'),
                    'Match Por': f"{criterio_cliente} (Exacto 1:1)",
                    'Monto Factura ($)': f_row['Monto Total'],
                    'Diferencia ($)': 0,
                    'Estado Conciliación': '🟢 Conciliado Exacto'
                })
                match_encontrado = True

            else:
                match_agrupado = buscar_combinacion_facturas(candidatos_cliente, monto_pago)
                if not match_agrupado.empty:
                    folios_agrupados = ", ".join(match_agrupado['Folio'].astype(str).tolist())
                    for f_id in match_agrupado['Folio']:
                        facturas_usadas.add(f_id)
                        
                    monto_total_facturas = match_agrupado['Monto Total'].sum()
                    f_row = match_agrupado.iloc[0]
                    cruce_list.append({
                        'Fecha Banco': row_c['Fecha'],
                        'Identificador Cartola': id_cartola,
                        'Monto Banco ($)': monto_pago,
                        'Folios Factura(s)': folios_agrupados,
                        'Entidad Matcheada': f_row.get('Nombre 1', 'N/A'),
                        'Match Por': f"{criterio_cliente} (Pago Agrupado 1:N - {len(match_agrupado)} Facturas)",
                        'Monto Factura ($)': monto_total_facturas,
                        'Diferencia ($)': 0,
                        'Estado Conciliación': '🟢 Conciliado Agrupado (1:N)'
                    })
                    match_encontrado = True

        if not match_encontrado:
            if not candidatos_cliente.empty:
                f_row = candidatos_cliente.iloc[0]
                facturas_usadas.add(f_row['Folio'])
                dif = monto_pago - f_row['Monto Total']
                cruce_list.append({
                    'Fecha Banco': row_c['Fecha'],
                    'Identificador Cartola': id_cartola,
                    'Monto Banco ($)': monto_pago,
                    'Folios Factura(s)': f_row['Folio'],
                    'Entidad Matcheada': f_row.get('Nombre 1', 'N/A'),
                    'Match Por': criterio_cliente,
                    'Monto Factura ($)': f_row['Monto Total'],
                    'Diferencia ($)': dif,
                    'Estado Conciliación': '🟡 Diferencia en Monto'
                })
            else:
                cruce_list.append({
                    'Fecha Banco': row_c['Fecha'],
                    'Identificador Cartola': id_cartola,
                    'Monto Banco ($)': monto_pago,
                    'Folios Factura(s)': 'N/A',
                    'Entidad Matcheada': 'NO ENCONTRADO',
                    'Match Por': 'Sin Coincidencia',
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
            df_ventas.drop(columns=['Nombre1_Limpio'], errors='ignore').to_excel(writer, sheet_name='Registro Ventas', index=False)
        if df_incompletos is not None and not df_incompletos.empty:
            df_incompletos.to_excel(writer, sheet_name='Revisiones Pendientes', index=False)

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
        file_bytes = archivo_cartola.getvalue()
        df_cartola_global, df_incompletos_global, estado_cartola = normalizar_cartola_cached(file_bytes, archivo_cartola.name.lower())
        
        if estado_cartola == "OK":
            total_ingresos = df_cartola_global['Monto Pago'].sum() if not df_cartola_global.empty else 0
            
            col_kpi, col_info = st.columns([1, 2])
            with col_kpi:
                st.metric("Total Ingresos Confirmados", f"$ {total_ingresos:,.0f}".replace(",", "."))
            with col_info:
                st.success(f"¡Cartola procesada! Se identificaron **{len(df_cartola_global)}** abonos válidos.")

            st.divider()
            
            if not df_cartola_global.empty:
                st.dataframe(
                    df_cartola_global.style.format({'Monto Pago': '$ {:,.0f}'}), 
                    use_container_width=True, hide_index=True, height=400
                )

            if df_incompletos_global is not None and not df_incompletos_global.empty:
                st.warning(f"⚠️ **Atención:** Se detectaron **{len(df_incompletos_global)}** fila(s) incompletas o ambiguas.")
                with st.expander("🔍 Ver filas incompletas o ambiguas para revisión manual", expanded=False):
                    st.dataframe(df_incompletos_global, use_container_width=True, hide_index=True)
        else:
            st.error(f"Error: {estado_cartola}")
    else:
        st.info("Sube la cartola bancaria en la sección superior para visualizar los datos.")

with tab2:
    if archivo_ventas is not None:
        file_bytes_v = archivo_ventas.getvalue()
        df_ventas_global, estado_ventas = normalizar_ventas_cached(file_bytes_v, archivo_ventas.name.lower())
        
        if estado_ventas == "OK" and df_ventas_global is not None:
            total_ventas = df_ventas_global['Monto Total'].sum() if not df_ventas_global.empty else 0
            
            col_kpi_v, col_info_v = st.columns([1, 2])
            with col_kpi_v:
                st.metric("Total Ventas / Cartera", f"$ {total_ventas:,.0f}".replace(",", "."))
            with col_info_v:
                st.success(f"¡Documentos procesados! Se cargaron **{len(df_ventas_global)}** registros de forma limpia.")

            st.divider()

            if not df_ventas_global.empty:
                df_mostrar = df_ventas_global.drop(columns=['Nombre1_Limpio'], errors='ignore')
                st.dataframe(
                    df_mostrar.style.format({'Monto Total': '$ {:,.0f}'}), 
                    use_container_width=True, hide_index=True, height=400
                )
        else:
            st.error(f"Error: {estado_ventas}")
    else:
        st.info("Sube el registro de ventas o cartera de documentos en la sección superior.")

# TAB 3: CRUCE
df_cruce_global = pd.DataFrame()
df_pendientes_global = pd.DataFrame()

with tab3:
    if not df_cartola_global.empty and df_ventas_global is not None and not df_ventas_global.empty:
        # Se ejecuta mediante la función en caché para evitar lentitud
        df_cruce_global, df_pendientes_global = conciliar_informacion_cached(df_cartola_global, df_ventas_global)

        col_m1, col_m2, col_m3 = st.columns(3)
        conciliados_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'].str.contains('🟢')])
        diferencias_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'].str.contains('🟡')])
        no_id_count = len(df_cruce_global[df_cruce_global['Estado Conciliación'].str.contains('🔴')])

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
            df_pend_mostrar = df_pendientes_global.drop(columns=['Nombre1_Limpio'], errors='ignore')
            st.dataframe(
                df_pend_mostrar.style.format({'Monto Total': '$ {:,.0f}'}),
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

