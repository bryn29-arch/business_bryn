import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
from difflib import SequenceMatcher
import io

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Conciliación Bancaria Avanzada - Sumas Agrupadas PRO",
    page_icon="📊",
    layout="wide"
)

# -----------------------------------------------------------------------------
# FUNCIONES DE NORMALIZACIÓN Y PARSEO
# -----------------------------------------------------------------------------
ABREVIATURAS = {
    'CORP': 'CORPORACION', 'EDUC': 'EDUCACION', 'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC', 'ANONIMA': 'SA', 'HERMANOS': 'HROS',
    'EIRL': '', 'SPA': '', 'S': 'SPA', 'EXP': 'EXPORTACION', 
    'ING': 'INGENIERIA', 'SERV': 'SERVICIOS'
}

def extraer_rut(texto):
    """Extrae RUT normalizado (solo números y K) eliminando puntos, guiones y ceros iniciales."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    match = re.search(r'\b(\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK])\b', str(texto))
    if match:
        rut_limpio = re.sub(r'[^0-9K]', '', match.group(1).upper())
        return rut_limpio.lstrip('0')
    return ""

def expandir_y_limpiar_texto(texto):
    """Normaliza texto, remueve acentos y estandariza abreviaturas."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    texto = re.sub(r'[^A-Z0-9\s]', ' ', texto)
    palabras = texto.split()
    palabras_norm = [ABREVIATURAS.get(p, p) for p in palabras]
    return re.sub(r'\s+', ' ', " ".join(palabras_norm)).strip()

def limpiar_monto_entero(val, solo_positivos=True):
    """Convierte celdas de moneda/texto a número entero."""
    if pd.isna(val):
        return 0
    if isinstance(val, (int, float)):
        res = int(round(val))
        return abs(res) if solo_positivos else res
        
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' in val_str:
        if val_str.rfind('.') < val_str.rfind(','):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
        
    val_str = re.sub(r'[^0-9.-]', '', val_str)
    try:
        res = int(round(float(val_str)))
        return abs(res) if solo_positivos else res
    except ValueError:
        return 0

# -----------------------------------------------------------------------------
# ALGORITMO SUBSET SUM OPTIMIZADO (O(1) SUFFIX LOOKUP)
# -----------------------------------------------------------------------------
def buscar_combinacion_exacta(df_candidatos, monto_objetivo, col_monto='Monto_Real', max_docs=25):
    """
    Encuentra un subconjunto de facturas cuya suma iguale exactamente el monto objetivo.
    Optimizado con Suffix Sums para evitar recalculado recurrente de arrays.
    """
    if df_candidatos.empty or monto_objetivo <= 0:
        return []

    cand = df_candidatos[df_candidatos[col_monto] <= monto_objetivo].copy()
    if cand.empty:
        return []

    cand = cand.sort_values(by=col_monto, ascending=False)
    items = list(zip(cand.index, cand[col_monto]))
    n = len(items)

    # Precálculo de Sumas Sufijas para poda instantánea O(1)
    suffix_sums = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix_sums[i] = suffix_sums[i + 1] + items[i][1]

    resultado = []

    def backtrack(idx, acumulado, combo):
        nonlocal resultado
        if resultado:
            return

        if acumulado == monto_objetivo:
            resultado = list(combo)
            return

        if acumulado > monto_objetivo or idx >= n or len(combo) >= max_docs:
            return

        # Poda ultra-rápida en O(1)
        if acumulado + suffix_sums[idx] < monto_objetivo:
            return

        # Incluir elemento actual
        i_orig, m_val = items[idx]
        combo.append(i_orig)
        backtrack(idx + 1, acumulado + m_val, combo)
        combo.pop()

        # Excluir elemento actual
        backtrack(idx + 1, acumulado, combo)

    backtrack(0, 0, [])
    return resultado

# -----------------------------------------------------------------------------
# NÚCLEO DE CONCILIACIÓN
# -----------------------------------------------------------------------------
@st.cache_data
def conciliar_informacion(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_ventas_prep = df_ventas.copy()
    
    # Identificación automática de columnas
    col_monto_v = next((c for c in ['Monto tot', 'Monto Total', 'Monto', 'Total', 'Saldo', 'VALOR'] if c in df_ventas_prep.columns), None)
    col_folio_v = next((c for c in ['Documento', 'Folio', 'N° Factura', 'Numero', 'Factura', 'ID', 'FOLIO'] if c in df_ventas_prep.columns), None)
    col_cliente_v = next((c for c in ['Deudor', 'Nombre 2', 'Nombre Cliente', 'Cliente', 'Razon Social', 'NOMBRE'] if c in df_ventas_prep.columns), df_ventas_prep.columns[0])
    col_monto_c = next((c for c in ['Abono', 'Monto', 'Crédito', 'Credito', 'Deposito', 'DEPOSITO'] if c in df_cartola.columns), None)

    # Preprocesar textos, RUTs y montos en cartera
    df_ventas_prep['Fila_Texto'] = df_ventas_prep.apply(lambda r: " ".join([str(v) for v in r.values if pd.notna(v)]), axis=1)
    df_ventas_prep['Fila_Texto_Norm'] = df_ventas_prep['Fila_Texto'].apply(expandir_y_limpiar_texto)
    df_ventas_prep['Cliente_Norm'] = df_ventas_prep[col_cliente_v].apply(expandir_y_limpiar_texto)
    df_ventas_prep['RUT_Norm'] = df_ventas_prep['Fila_Texto'].apply(extraer_rut)
    
    if col_monto_v:
        df_ventas_prep['Monto_Real'] = df_ventas_prep[col_monto_v].apply(limpiar_monto_entero)
    else:
        df_ventas_prep['Monto_Real'] = df_ventas_prep.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    for idx_c, row_c in df_cartola.iterrows():
        texto_c_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        texto_c_norm = expandir_y_limpiar_texto(texto_c_raw)
        rut_c = extraer_rut(texto_c_raw)
        
        monto_banco = limpiar_monto_entero(row_c[col_monto_c]) if col_monto_c else max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"

        ventas_disponibles = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)]

        # ---------------------------------------------------------------------
        # CAPA 1: BÚSQUEDA STRICTA POR RUT
        # ---------------------------------------------------------------------
        if rut_c and monto_banco > 0:
            cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
            
            if not cand_rut.empty:
                # Caso A: Factura única con monto exacto
                exacto_1a1 = cand_rut[cand_rut['Monto_Real'] == monto_banco]
                if not exacto_1a1.empty:
                    match_indices = [exacto_1a1.index[0]]
                    tipo_match = "RUT Exacto (1:1)"
                else:
                    # Caso B: Suma de TODAS las facturas pendientes de este RUT
                    if cand_rut['Monto_Real'].sum() == monto_banco:
                        match_indices = cand_rut.index.tolist()
                        tipo_match = f"RUT Todas las Facturas (1:{len(match_indices)})"
                    else:
                        # Caso C: Buscar combinación específica (Subset Sum)
                        combo = buscar_combinacion_exacta(cand_rut, monto_banco, col_monto='Monto_Real')
                        if combo:
                            match_indices = combo
                            tipo_match = f"RUT Pago Agrupado (1:{len(combo)})"

        # ---------------------------------------------------------------------
        # CAPA 2: BÚSQUEDA AGRUPADA POR NOMBRE DE CLIENTE / TEXTO (UMBRAL MÁS ESTRICTO)
        # ---------------------------------------------------------------------
        if not match_indices and monto_banco > 0:
            indices_cand_nombre = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                # Comparar prioritariamente con el nombre del cliente (más preciso que la fila entera)
                similitud_cliente = SequenceMatcher(None, texto_c_norm, row_v['Cliente_Norm']).ratio()
                similitud_texto = SequenceMatcher(None, texto_c_norm, row_v['Fila_Texto_Norm']).ratio()
                
                if max(similitud_cliente, similitud_texto) >= 0.65:
                    indices_cand_nombre.append(idx_v)

            if indices_cand_nombre:
                cand_nom = ventas_disponibles.loc[indices_cand_nombre]
                
                # Caso A: Factura única por el monto
                exacto_nom = cand_nom[cand_nom['Monto_Real'] == monto_banco]
                if not exacto_nom.empty:
                    match_indices = [exacto_nom.index[0]]
                    tipo_match = "Nombre Exacto (1:1)"
                else:
                    # Caso B: Combinación de facturas
                    combo_nom = buscar_combinacion_exacta(cand_nom, monto_banco, col_monto='Monto_Real')
                    if combo_nom:
                        match_indices = combo_nom
                        tipo_match = f"Nombre Agrupado (1:{len(combo_nom)})"

        # ---------------------------------------------------------------------
        # CAPA 3: MONTO ÚNICO GLOBAL (SÓLO SI NO HAY AMBIGÜEDAD)
        # ---------------------------------------------------------------------
        if not match_indices and monto_banco > 0:
            cand_monto_unico = ventas_disponibles[ventas_disponibles['Monto_Real'] == monto_banco]
            if len(cand_monto_unico) == 1:
                match_indices = [cand_monto_unico.index[0]]
                tipo_match = "Monto Unico Coincidente"

        # ---------------------------------------------------------------------
        # GENERACIÓN DEL REGISTRO
        # ---------------------------------------------------------------------
        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
                
            rows_matched = df_ventas_prep.loc[match_indices]
            folios = ", ".join([str(r[col_folio_v]) if col_folio_v else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            entidad = rows_matched.iloc[0][col_cliente_v]
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = monto_banco - monto_ventas_tot

            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': folios,
                'Entidad Matcheada': entidad,
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_ventas_tot,
                'Diferencia ($)': dif,
                'Estado Conciliación': '🟢 Conciliado Exacto' if dif == 0 else '🟡 Diferencia en Monto'
            })
        else:
            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': 'N/A',
                'Entidad Matcheada': 'NO ENCONTRADO',
                'Tipo Coincidencia': 'Sin Coincidencia',
                'Monto Ventas ($)': 0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, ventas_pendientes

# -----------------------------------------------------------------------------
# INTERFAZ STREAMLIT CON MANEJO DE ESTADO
# -----------------------------------------------------------------------------
st.title("🏦 Sistema de Conciliación Bancaria Inteligente")
st.markdown("Cruce estructurado por **Agrupación de RUT** y **Algoritmo de Sumas Exactas (1 a N)**.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Cartola Bancaria")
    file_cartola = st.file_uploader("Subir Cartola (Excel / CSV)", type=["xlsx", "xls", "csv"], key="cartola")

with col2:
    st.subheader("2. Registro de Ventas / Cartera")
    file_ventas = st.file_uploader("Subir Cartera / Ventas (Excel / CSV)", type=["xlsx", "xls", "csv"], key="ventas")

if file_cartola and file_ventas:
    try:
        df_cartola = pd.read_csv(file_cartola) if file_cartola.name.endswith('.csv') else pd.read_excel(file_cartola)
        df_ventas = pd.read_csv(file_ventas) if file_ventas.name.endswith('.csv') else pd.read_excel(file_ventas)

        st.success("Archivos cargados correctamente.")

        if st.button("🚀 Ejecutar Conciliación Inteligente", type="primary"):
            with st.spinner("Procesando cruce agrupado..."):
                df_cruce, df_pendientes = conciliar_informacion(df_cartola, df_ventas)
                # Persistir resultados en Session State
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        # Renderizar si existen datos procesados en memoria
        if 'df_cruce' in st.session_state and not st.session_state['df_cruce'].empty:
            df_cruce = st.session_state['df_cruce']
            df_pendientes = st.session_state['df_pendientes']

            st.divider()
            st.subheader("📊 Resumen de Resultados")

            m1, m2, m3, m4 = st.columns(4)
            tot_exactos = len(df_cruce[df_cruce['Estado Conciliación'] == '🟢 Conciliado Exacto'])
            tot_diferencias = len(df_cruce[df_cruce['Estado Conciliación'] == '🟡 Diferencia en Monto'])
            tot_no_encontrados = len(df_cruce[df_cruce['Estado Conciliación'] == '🔴 Abono No Identificado'])
            monto_no_ident = df_cruce[df_cruce['Estado Conciliación'] == '🔴 Abono No Identificado']['Monto Banco ($)'].sum()

            m1.metric("🟢 Conciliados Exactos", tot_exactos)
            m2.metric("🟡 Dif. en Monto", tot_diferencias)
            m3.metric("🔴 No Identificados", tot_no_encontrados)
            m4.metric("💰 Mto. No Identificado", f"${monto_no_ident:,.0f}")

            st.subheader("📋 Matriz de Cruce de Cartola")
            st.dataframe(df_cruce, use_container_width=True)

            if not df_pendientes.empty:
                st.subheader("⏳ Facturas / Documentos Pendientes de Pago")
                st.dataframe(df_pendientes, use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_cruce.to_excel(writer, sheet_name='Cartola_Conciliada', index=False)
                if not df_pendientes.empty:
                    df_pendientes.to_excel(writer, sheet_name='Facturas_Pendientes', index=False)
            
            st.download_button(
                label="📥 Descargar Informe en Excel",
                data=output.getvalue(),
                file_name="Conciliacion_Bancaria_Resultados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error al procesar los archivos: {str(e)}")
else:
    st.info("👆 Sube ambos archivos para realizar el cruce.")
