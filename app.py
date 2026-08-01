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
    """Lee y estandariza la cartola bancaria limpiando basura de pie de página."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        registros = []
        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    tablas = pagina.extract_tables()
                    for tabla in tablas:
                        for fila in tabla:
                            if not fila:
                                continue
                            
                            f_clean = [str(c).strip().replace('\n', ' ') if c else "" for c in fila]
                            texto_fila = " ".join(f_clean)
                            
                            # Ignorar encabezados, pies de página y saldos
                            if not any(f_clean) or any(x in texto_fila.lower() for x in ['saldo', 'cartola', 'página', 'hoja', 'rut:']):
                                continue
                            
                            # Debe contener una fecha válida al inicio o dentro de la celda
                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            if not match_fecha:
                                continue
                            fecha = match_fecha.group(0)
                            
                            # Buscar celdas específicas que contengan un monto (formato chileno)
                            monto_encontrado = None
                            for celda in reversed(f_clean):
                                match_monto = re.search(r'^\$? \s*(\d{1,3}(?:\.\d{3})+)\b', celda) or re.search(r'\b(\d{1,3}(?:\.\d{3})+)\b', celda)
                                if match_monto:
                                    val = int(match_monto.group(1).replace('.', ''))
                                    if val > 1000:
                                        monto_encontrado = val
                                        break
                            
                            # Filtro estricto: Debe haber un monto real y no solo una fecha o código
                            if monto_encontrado and ("Traspaso" in texto_fila or "Pago" in texto_fila or "Transferencia" in texto_fila or "$" in texto_fila):
                                identificador = extraer_rut_o_nombre(texto_fila)
                                
                                # Limpiar la glosa de la fecha y del monto
                                glosa_limpia = texto_fila.replace(fecha, '').strip()
                                glosa_limpia = re.sub(r'\b\d{1,3}(?:\.\d{3})+\b', '', glosa_limpia).strip()
                                
                                registros.append({
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
                    registros.append({
                        'fecha': 'VER_EXCEL',
                        'identificador_cliente': extraer_rut_o_nombre(texto_fila),
                        'monto_pago': int(montos[-1]),
                        'descripcion_glosa': texto_fila[:100]
                    })

        if not registros:
            return None, "No se identificaron montos procesables."

        df_final = pd.DataFrame(registros).drop_duplicates().reset_index(drop=True)
        return df_final, "OK"

    except Exception as e:
        return None, f"Error al procesar: {str(e)}"


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

# Ajuste de layout general
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
    df_cartola, msg = normalizar_cartola(archivo_cartola)
    if df_cartola is not None and not df_cartola.empty:
        st.success(f"¡Cartola procesada correctamente! **{len(df_cartola)}** abonos reales detectados.")
        st.metric("Total Ingresos", f"$ {df_cartola['monto_pago'].sum():,.0f}".replace(",", "."))
        
        # Muestra la tabla a todo el ancho disponible
        st.dataframe(
            df_cartola.style.format({'monto_pago': '$ {:,.0f}'}), 
            use_container_width=True,
            height=450
        )
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
            height=450
        )
    else:
        st.error(f"Ventas: {msg_v}")

