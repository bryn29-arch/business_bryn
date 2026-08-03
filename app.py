import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
import itertools
import io
from difflib import SequenceMatcher

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Conciliación Bancaria - Modo Blindado", page_icon="🛡️", layout="wide")

ABREVIATURAS = {
    'CORP': 'CORPORACION', 'EDUC': 'EDUCACION', 'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC', 'ANONIMA': 'SA', 'HERMANOS': 'HROS',
    'EIRL': '', 'SPA': '', 'S': 'SPA', 'EXP': 'EXPORTACION', 
    'ING': 'INGENIERIA', 'SERV': 'SERVICIOS'
}

def extraer_rut(texto):
    if not isinstance(texto, str) or pd.isna(texto): return ""
    match = re.search(r'\b(0*\d{1,3}\.?\d{3}\.?\d{3}-?[\dkK])\b', str(texto))
    if match:
        return re.sub(r'[^0-9K]', '', match.group(1).upper()).lstrip('0')
    return ""

def expandir_y_limpiar_texto(texto):
    if not isinstance(texto, str) or pd.isna(texto): return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    texto = re.sub(r'[^A-Z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', " ".join([ABREVIATURAS.get(p, p) for p in texto.split()])).strip()

def limpiar_monto_entero(val):
    if pd.isna(val): return 0
    if isinstance(val, (int, float)): return int(round(abs(val)))
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' in val_str:
        if val_str.rfind('.') < val_str.rfind(','): val_str = val_str.replace('.', '').replace(',', '.')
        else: val_str = val_str.replace(',', '')
    elif ',' in val_str: val_str = val_str.replace(',', '.')
    val_str = re.sub(r'[^0-9.-]', '', val_str)
    try: return int(round(abs(float(val_str))))
    except: return 0

def encontrar_columna(columnas, palabras_clave):
    cols_limpias = {col: str(col).strip().upper() for col in columnas}
    for palabra in palabras_clave:
        for col_orig, col_limpia in cols_limpias.items():
            if palabra in col_limpia: return col_orig
    return None

# -----------------------------------------------------------------------------
# ALGORITMO FUERZA BRUTA (CON TOLERANCIA)
# -----------------------------------------------------------------------------
def buscar_combinacion_robusta(df_candidatos, monto_objetivo, col_monto='Monto_Real', tolerancia=2):
    """Prueba TODAS las combinaciones posibles si hay <= 18 facturas. Inmune a errores de orden."""
    if df_candidatos.empty or monto_objetivo <= 0: return []
    
    cand = df_candidatos[df_candidatos[col_monto] <= (monto_objetivo + tolerancia)].copy()
    if cand.empty: return []

    items = list(cand.index)
    montos = list(cand[col_monto])
    
    # 1. Validar suma total primero (El caso más común si pagan todo)
    if abs(sum(montos) - monto_objetivo) <= tolerancia:
        return items

    # 2. Fuerza bruta absoluta (Matemáticamente infalible para grupos pequeños)
    n = len(items)
    if n <= 18:
        for r in range(1, n + 1):
            for combo_indices in itertools.combinations(range(n), r):
                if abs(sum(montos[i] for i in combo_indices) - monto_objetivo) <= tolerancia:
                    return [items[i] for i in combo_indices]
    else:
        # 3. Método codicioso (Fallback si un cliente tiene demasiadas facturas para no congelar la app)
        cand = cand.sort_values(by=col_monto, ascending=False)
        items_sort, montos_sort = list(cand.index), list(cand[col_monto])
        acumulado, combo = 0, []
        for idx, m in zip(items_sort, montos_sort):
            if acumulado + m <= monto_objetivo + tolerancia:
                acumulado += m
                combo.append(idx)
                if abs(acumulado - monto_objetivo) <= tolerancia:
                    return combo
    return []

# -----------------------------------------------------------------------------
# NÚCLEO DE CONCILIACIÓN (SIN CACHÉ PARA FORZAR LIMPIEZA)
# -----------------------------------------------------------------------------
def conciliar_informacion(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_ventas_prep = df_ventas.copy()
    
    col_cliente_v = encontrar_columna(df_ventas_prep.columns, ['DEUDOR', 'CLIENTE', 'RAZON']) or df_ventas_prep.columns[0]
    col_rut_v = encontrar_columna(df_ventas_prep.columns, ['RUT DEUDOR', 'RUT. DEUDOR', 'RUT_DEUDOR', 'RUT DEU', 'RUT'])
    col_monto_v = encontrar_columna(df_ventas_prep.columns, ['ADEUDADO', 'MONTO TOT', 'MONTO', 'SALDO'])
    col_folio_v = encontrar_columna(df_ventas_prep.columns, ['DOC', 'FOLIO', 'FACTURA', 'NUMERO'])
    col_monto_c = encontrar_columna(df_cartola.columns, ['ABONO', 'DEPOSITO', 'CREDITO', 'MONTO'])

    df_ventas_prep['Fila_Texto'] = df_ventas_prep.apply(lambda r: " ".join([str(v) for v in r.values if pd.notna(v)]), axis=1)
    df_ventas_prep['Fila_Texto_Norm'] = df_ventas_prep['Fila_Texto'].apply(expandir_y_limpiar_texto)
    df_ventas_prep['Cliente_Norm'] = df_ventas_prep[col_cliente_v].apply(expandir_y_limpiar_texto)
    df_ventas_prep['RUT_Norm'] = df_ventas_prep[col_rut_v].apply(extraer_rut) if col_rut_v else df_ventas_prep['Fila_Texto'].apply(extraer_rut)
    df_ventas_prep['Monto_Real'] = df_ventas_prep[col_monto_v].apply(limpiar_monto_entero) if col_monto_v else df_ventas_prep.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    for idx_c, row_c in df_cartola.iterrows():
        texto_c_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        texto_c_norm = expandir_y_limpiar_texto(texto_c_raw)
        rut_c = extraer_rut(texto_c_raw)
        monto_banco = limpiar_monto_entero(row_c[col_monto_c]) if col_monto_c else max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"
        log_busqueda = "Inicio."

        ventas_disponibles = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)]

        if rut_c and monto_banco > 0:
            cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
            if not cand_rut.empty:
                log_busqueda = f"RUT encontrado con {len(cand_rut)} facturas (Suma total: {cand_rut['Monto_Real'].sum()}). "
                
                exacto_1a1 = cand_rut[abs(cand_rut['Monto_Real'] - monto_banco) <= 2]
                if not exacto_1a1.empty:
                    match_indices = [exacto_1a1.index[0]]
                    tipo_match = "🟢 RUT Exacto (1:1)"
                    log_busqueda += "Monto exacto en 1 factura."
                else:
                    combo = buscar_combinacion_robusta(cand_rut, monto_banco, col_monto='Monto_Real')
                    if combo:
                        match_indices = combo
                        tipo_match = f"🟢 RUT Pago Agrupado Exacto (1:{len(combo)})"
                        log_busqueda += "Combinación exacta encontrada."
                    else:
                        cand_ordenado = cand_rut.sort_values(by='Monto_Real', ascending=False)
                        match_indices = [cand_ordenado.index[0]]
                        tipo_match = "🔴 Diferencia Inexplicable (Asignación Forzada)"
                        log_busqueda += "Fuerza bruta falló. No suman el abono. Se asignó la factura mayor."

        # GENERACIÓN DEL REGISTRO
        if match_indices:
            for i in match_indices: indices_ventas_usados.add(i)
            rows_matched = df_ventas_prep.loc[match_indices]
            folios = ", ".join([str(r[col_folio_v]) if col_folio_v else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = monto_banco - monto_ventas_tot
            
            estado = '🟢 Conciliado Exacto' if abs(dif) <= 2 else '🟡 Diferencia en Monto'

            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': folios,
                'Entidad Matcheada': rows_matched.iloc[0][col_cliente_v],
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_ventas_tot,
                'Diferencia ($)': dif,
                'Estado Conciliación': estado,
                'Log de Búsqueda': log_busqueda
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
                'Estado Conciliación': '🔴 Abono No Identificado',
                'Log de Búsqueda': 'No se detectó RUT en la fila o no existe en cartera.'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)].copy()
    
    cols_a_eliminar = ['Fila_Texto', 'Fila_Texto_Norm', 'Cliente_Norm', 'RUT_Norm', 'Monto_Real']
    ventas_pendientes = ventas_pendientes.drop(columns=[c for c in cols_a_eliminar if c in ventas_pendientes.columns])
    
    return df_cruce, ventas_pendientes

# -----------------------------------------------------------------------------
# INTERFAZ STREAMLIT
# -----------------------------------------------------------------------------
st.title("🏦 Sistema de Conciliación Bancaria - Modo Blindado")
st.markdown("Algoritmo de **Fuerza Bruta Matemática** con tolerancia de $2 pesos y sin caché.")

col1, col2 = st.columns(2)
with col1: file_cartola = st.file_uploader("Subir Cartola", type=["xlsx", "xls", "csv"], key="cartola")
with col2: file_ventas = st.file_uploader("Subir Cartera", type=["xlsx", "xls", "csv"], key="ventas")

if file_cartola and file_ventas:
    try:
        df_cartola = pd.read_csv(file_cartola) if file_cartola.name.endswith('.csv') else pd.read_excel(file_cartola)
        df_ventas = pd.read_csv(file_ventas) if file_ventas.name.endswith('.csv') else pd.read_excel(file_ventas)

        if st.button("🚀 Ejecutar Conciliación Blindada", type="primary"):
            with st.spinner("Ejecutando fuerza bruta en combinaciones..."):
                df_cruce, df_pendientes = conciliar_informacion(df_cartola, df_ventas)
                st.session_state['df_cruce'] = df_cruce
                st.session_state['df_pendientes'] = df_pendientes

        if 'df_cruce' in st.session_state and not st.session_state['df_cruce'].empty:
            df_cruce = st.session_state['df_cruce']
            df_pendientes = st.session_state['df_pendientes']

            st.divider()
            st.subheader("📊 Resumen de Resultados")

            m1, m2, m3 = st.columns(3)
            tot_exactos = len(df_cruce[df_cruce['Estado Conciliación'] == '🟢 Conciliado Exacto'])
            tot_diferencias = len(df_cruce[df_cruce['Estado Conciliación'] == '🟡 Diferencia en Monto'])
            tot_no_encontrados = len(df_cruce[df_cruce['Estado Conciliación'] == '🔴 Abono No Identificado'])

            m1.metric("🟢 Conciliados Exactos", tot_exactos)
            m2.metric("🟡 Diferencias", tot_diferencias)
            m3.metric("🔴 No Identificados", tot_no_encontrados)

            st.subheader("📋 Matriz de Cruce de Cartola")
            st.dataframe(df_cruce, use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_cruce.to_excel(writer, sheet_name='Cartola_Conciliada', index=False)
                if not df_pendientes.empty: df_pendientes.to_excel(writer, sheet_name='Facturas_Pendientes', index=False)
            
            st.download_button("📥 Descargar Informe en Excel", data=output.getvalue(), file_name="Conciliacion_Resultados.xlsx")

    except Exception as e:
        st.error(f"Error al procesar: {str(e)}")
