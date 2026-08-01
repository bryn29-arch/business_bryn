import streamlit as st
import pandas as pd
import numpy as np
import re
import pdfplumber

# ---------------------------------------------------------
# 1. FUNCIONES MOTORAS DE PROCESAMIENTO (BACK-END)
# ---------------------------------------------------------

def extraer_rut_o_nombre(texto):
    """Busca RUT chileno o extrae el nombre de la persona/empresa en la glosa."""
    if not isinstance(texto, str):
        return "NO_DETECTADO"
    
    # Buscar RUT explícito
    patron_rut = r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b'
    match = re.search(patron_rut, texto)
    if match:
        rut_raw = match.group(0)
        rut_limpio = rut_raw.replace('.', '').upper()
        if '-' not in rut_limpio:
            rut_limpio = rut_limpio[:-1] + '-' + rut_limpio[-1]
        return rut_limpio
    
    # Extraer nombre si es traspaso BCI
    match_nombre = re.search(r'(?:Traspaso De:|Pago:)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip()
        nombre = re.sub(r'\s+(Internet|Cta|Cuenta|Transferencia).*$', '', nombre, flags=re.IGNORECASE)
        return f"NOMBRE: {nombre[:30]}"
        
    return "NO_DETECTADO"


def normalizar_cartola(archivo_subido):
    """Lee la cartola y clasifica transacciones procesadas vs. filas incompletas/dudosas."""
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
                            
                            # Omitir encabezados explícitos o saldos totales
                            if not any(f_clean) or any(x in texto_fila.lower() for x in ['saldo inicial', 'saldo final', 'cartola de cuenta']):
                                continue
                            
                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            if not match_fecha:
                                continue
                            fecha = match_fecha.group(0)
                            
                            # Extraer montos
                            monto_encontrado = None
                            for celda in reversed(f_clean):
                                match_monto = re.search(r'^\$? \s*(\d{1,3}(?:\.\d{3})+)\b', celda) or re.search(r'\b(\d{1,3}(?:\.\d{3})+)\b', celda)
                                if match_monto:
                                    val = int(match_monto.group(1).replace('.', ''))
                                    if val > 1000:
                                        monto_encontrado = val
                                        break
                            
                            identificador = extraer_rut_o_nombre(texto_fila)
                            glosa_limpia = texto_fila.replace(fecha, '').strip()
                            glosa_limpia = re.sub(r'\b\d{1,3}(?:\.\d{3})+\b', '', glosa_limpia).strip()

                            # SI la fila tiene fecha pero le falta un monto claro o está recortada -> Alerta de Dudosa
                            if not monto_encontrado or ("Traspaso" in texto_fila and identificador == "NO_DETECTADO"):
                                registros_dudosos.append({
                                    'pagina': num_pag,
                                    'fecha': fecha,
                                    'contenido_capturado': texto_fila[:100],
                                    'observacion': 'Monto o Identificador incompleto/ilegible'
                                })
                            else:
                                registros_ok.append({
                                    'fecha': fecha,
                                    'identificador_cliente': identificador,
                                    'monto_pago': monto_encontrado,
                                    'descripcion_glosa': glosa_limpia[:120]
                                })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                montos = re.findall(r'\b\d{3,}\b', texto_fila)
                if montos:
                    registros_ok.append({
                        'fecha': 'VER_EXCEL',
                        'identificador_cliente': extraer_rut_o_nombre(texto_fila),
                        'monto_pago': int(montos[-1]),
                        'descripcion_glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).drop_duplicates().reset_index(drop=True) if registros_ok else pd.DataFrame()
        df_dudosos = pd.DataFrame(registros_dudosos).drop_duplicates().reset_index(drop=True) if registros_dudosos else pd.DataFrame()

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return None, None, f"Error al procesar: {str(e)}"


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

        cols_finales = ['folio', 'rut_cliente', 'razon_social', 'monto_total']
        return df[cols_finales].reset_index(drop=True), "OK"

    except Exception as e:
        return None, f"Error al procesar ventas: {str(e)}"


# ---------------------------------------------------------
# 2. INTERFAZ GRÁFICA DE USUARIO (FRONT-END)
# ---------------------------------------------------------

st.set_page_config(
    page_title="FinanSmart | Plataforma de Conciliación",
    page_icon="💼",
    layout="wide"
)

with st.sidebar:
    st.title("💼 FinanSmart")
    st.caption("Plataforma Inteligente de Gestión Financiera")
    st.divider()
    empresa = st.text_input("Nombre de la Empresa / Cliente", value="PyME Ejemplo SpA")
    periodo = st.date_input("Mes de Conciliación", value=pd.to_datetime("2026-08-01"))
    st.divider()
    st.info("💡 **Tip para el cliente:** Sube tu cartola original y registro de ventas sin hacerles cambios.")

st.title("📊 Panel de Conciliación y Control de Cuentas")
st.write(f"Gestionando información para: **{empresa}** | Período: **{periodo.strftime('%m/%Y')}**")
st.divider()

st.subheader("1. Carga de Documentos Crudos")

archivo_cartola = st.file_uploader(
    "🏛️ Sube la cartola bancaria descargada del banco (PDF / Excel)",
    type=["pdf", "xlsx", "xls", "csv"],
    key="cartola_input"
)

archivo_ventas = st.file_uploader(
    "📄 Sube el registro de ventas emitidas (Excel / CSV)",
    type=["xlsx", "xls", "csv"],
    key="ventas_input"
)

st.divider()

if archivo_cartola is not None:
    st.subheader("2. Cartola Bancaria Normalizada")
    df_cartola, df_incompletos, msg = normalizar_cartola(archivo_cartola)
    
    if df_cartola is not None and not df_cartola.empty:
        st.success(f"¡Cartola procesada! **{len(df_cartola)}** abonos completos identificados.")
        st.metric("Total Ingresos Confirmados", f"$ {df_cartola['monto_pago'].sum():,.0f}".replace(",", "."))
        
        st.dataframe(
            df_cartola.style.format({'monto_pago': '$ {:,.0f}'}), 
            use_container_width=True,
            height=400
        )

        # MOSTRAR ALERTA Y TABLA DE REVISIÓN MANUAL SI HAY FILAS INCOMPLETAS
        if df_incompletos is not None and not df_incompletos.empty:
            st.warning(f"⚠️ **ATENCIÓN:** Se han detectado **{len(df_incompletos)}** fila(s) incompleta(s) o recortada(s) en la cartola que requieren revisión manual.")
            with st.expander("🔍 Ver filas incompletas / pendientes de revisión", expanded=True):
                st.write("Revisa estas líneas directamente en tu PDF original:")
                st.dataframe(df_incompletos, use_container_width=True)

    else:
        st.error(f"Cartola: {msg}")

if archivo_ventas is not None:
    st.subheader("3. Registro de Ventas Normalizado")
    df_ventas, msg_v = normalizar_ventas(archivo_ventas)
    if df_ventas is not None and not df_ventas.empty:
        st.success(f"¡Ventas listas! **{len(df_ventas)}** facturas cargadas.")
        st.metric("Total Ventas Emitidas", f"$ {df_ventas['monto_total'].sum():,.0f}".replace(",", "."))
        
        st.dataframe(
            df_ventas.style.format({'monto_total': '$ {:,.0f}'}), 
            use_container_width=True,
            height=400
        )
    else:
        st.error(f"Ventas: {msg_v}")
