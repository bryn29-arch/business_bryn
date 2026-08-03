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
# DICCIONARIOS Y FUNCIONES DE TEXTO Y MONTO
# -----------------------------------------------------------------------------
ABREVIATURAS = {
    'CORP': 'CORPORACION', 'EDUC': 'EDUCACION', 'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC', 'ANONIMA': 'SA', 'HERMANOS': 'HROS',
    'EIRL': '', 'SPA': '', 'S': 'SPA', 'EXP': 'EXPORTACION', 
    'ING': 'INGENIERIA', 'SERV': 'SERVICIOS'
}

def extraer_rut(texto):
    """Extrae RUT sin puntos ni guion para cruces exactos (ej: 76334370K o 93546000K)."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    match = re.search(r'\b(\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK])\b', str(texto))
    if match:
        return re.sub(r'[^0-9K]', '', match.group(1).upper())
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

def extraer_tokens_clave(texto_fila):
    """Extrae palabras relevantes de 2 o más caracteres."""
    texto_clean = expandir_y_limpiar_texto(texto_fila)
    palabras = set(re.findall(r'\b[A-Z0-9]{2,}\b', texto_clean))
    stopwords = {
        'TRASPASO', 'TRANSFERENCIA', 'BANCO', 'PAGO', 'DEBITO', 'CREDITO', 
        'INTERNET', 'VALE', 'VISTA', 'CHILE', 'CANAL', 'INFORMACION', 'TEF', 
        'ABONO', 'CARGO', 'LTDA', 'SOC', 'SA', 'SPA'
    }
    return palabras - stopwords

def calcular_similitud_textual(texto1, texto2):
    """Evalúa coincidencia borrosa entre cadenas de texto."""
    if not texto1 or not texto2:
        return 0.0
    t1 = expandir_y_limpiar_texto(texto1)
    t2 = expandir_y_limpiar_texto(texto2)
    if not t1 or not t2:
        return 0.0
    if len(t1) >= 4 and len(t2) >= 4 and (t1 in t2 or t2 in t1):
        return 0.95
    tokens1 = extraer_tokens_clave(t1)
    tokens2 = extraer_tokens_clave(t2)
    if tokens1 and tokens2:
        interseccion = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        ratio = len(interseccion) / len(union) if union else 0.0
        if len(interseccion) >= 2:
            return max(0.85, ratio)
        if len(interseccion) == 1 and len(list(interseccion)[0]) >= 4:
            return max(0.75, ratio)
    return SequenceMatcher(None, t1, t2).ratio()

def limpiar_monto_celda(val):
    """Convierte un valor numérico/moneda a flotante limpio."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return abs(float(val))
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
        return abs(float(val_str))
    except ValueError:
        return 0.0

# -----------------------------------------------------------------------------
# ALGORITMO SUBSET SUM REFORZADO (BRANCH AND BOUND)
# -----------------------------------------------------------------------------

def buscar_combinacion_subconjunto(df_candidatos, monto_objetivo, col_monto='Monto_Real', max_docs=40):
    """
    Busca de manera ultra rápida un grupo de facturas que sumen exactamente el monto del banco.
    """
    if df_candidatos.empty or monto_objetivo <= 0:
        return []

    # Se consideran candidatas facturas que no superen por sí solas el abono (+10 para tolerancia de redondeos)
    candidatos_df = df_candidatos[df_candidatos[col_monto] <= (monto_objetivo + 10.0)].copy()
    if candidatos_df.empty:
        return []

    # Ordenar de mayor a menor para podar ramas rápidamente
    candidatos_df = candidatos_df.sort_values(by=col_monto, ascending=False)
    items = list(zip(candidatos_df.index, candidatos_df[col_monto]))
    
    resultado_indices = []

    def backtrack(index, suma_actual, combo_actual):
        nonlocal resultado_indices
        if resultado_indices:
            return

        # Tolerancia estricta de $2 para diferencias menores/redondeos
        if abs(suma_actual - monto_objetivo) <= 2.0:
            resultado_indices = list(combo_actual)
            return

        if suma_actual > (monto_objetivo + 2.0) or index >= len(items) or len(combo_actual) >= max_docs:
            return

        # Poda: Si lo que queda no alcanza para el objetivo
        suma_restante = sum(m for _, m in items[index:])
        if (suma_actual + suma_restante) < (monto_objetivo - 2.0):
            return

        # Incluir elemento
        idx_orig, monto = items[index]
        combo_actual.append(idx_orig)
        backtrack(index + 1, suma_actual + monto, combo_actual)
        combo_actual.pop()

        # Omitir elemento
        backtrack(index + 1, suma_actual, combo_actual)

    backtrack(0, 0.0, [])
    return resultado_indices


# -----------------------------------------------------------------------------
# ALGORITMO DE CONCILIACIÓN CON BÚSQUEDA OPTIMIZADA
# -----------------------------------------------------------------------------

@st.cache_data
def conciliar_informacion_flexible(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()

    # Preprocesamiento de Ventas
    df_ventas_prep = df_ventas.copy()
    
    # Mapeo Inteligente de Columnas Clave
    col_monto_v = next((c for c in ['Monto tot', 'Monto Total', 'Monto', 'Total', 'Saldo', 'VALOR'] if c in df_ventas_prep.columns), None)
    col_folio_v = next((c for c in ['Documento', 'Folio', 'N° Factura', 'Numero', 'Factura', 'ID', 'FOLIO'] if c in df_ventas_prep.columns), None)
    col_cliente_v = next((c for c in ['Deudor', 'Nombre 2', 'Nombre Cliente', 'Cliente', 'Razon Social', 'NOMBRE'] if c in df_ventas_prep.columns), df_ventas_prep.columns[0])

    col_monto_c = next((c for c in ['Abono', 'Monto', 'Crédito', 'Credito', 'Deposito', 'DEPOSITO'] if c in df_cartola.columns), None)

    df_ventas_prep['Fila_Texto'] = df_ventas_prep.apply(lambda r: " ".join([str(v) for v in r.values if pd.notna(v)]), axis=1)
    df_ventas_prep['Fila_Texto_Norm'] = df_ventas_prep['Fila_Texto'].apply(expandir_y_limpiar_texto)
    df_ventas_prep['RUT_Norm'] = df_ventas_prep['Fila_Texto'].apply(extraer_rut)
    
    if col_monto_v:
        df_ventas_prep['Monto_Real'] = df_ventas_prep[col_monto_v].apply(limpiar_monto_celda)
    else:
        df_ventas_prep['Monto_Real'] = df_ventas_prep.apply(lambda r: max([limpiar_monto_celda(v) for v in r.values] + [0.0]), axis=1)

    for idx_c, row_c in df_cartola.iterrows():
        texto_c_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        texto_c_norm = expandir_y_limpiar_texto(texto_c_raw)
        rut_c = extraer_rut(texto_c_raw)
        
        if col_monto_c:
            monto_banco = limpiar_monto_celda(row_c[col_monto_c])
        else:
            monto_banco = max([limpiar_monto_celda(v) for v in row_c.values] + [0.0])

        match_indices = []
        tipo_match = "Sin Coincidencia"

        ventas_disponibles = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)]

        # =====================================================================
        # ESTRATEGIA 0: BÚSQUEDA OBLIGATORIA DE SUMA EXACTA POR RUT (1 a N)
        # =====================================================================
        if rut_c and monto_banco > 0:
            cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
            
            if not cand_rut.empty:
                # 1. ¿Existe 1 sola factura por el monto exacto?
                exacto_1a1 = cand_rut[abs(cand_rut['Monto_Real'] - monto_banco) <= 2.0]
                if not exacto_1a1.empty:
                    match_indices = [exacto_1a1.index[0]]
                    tipo_match = "RUT Exacto (1:1)"
                else:
                    # 2. ¿La suma de TODAS las facturas de este RUT da exacto el abono?
                    suma_total_rut = cand_rut['Monto_Real'].sum()
                    if abs(suma_total_rut - monto_banco) <= 2.0:
                        match_indices = cand_rut.index.tolist()
                        tipo_match = f"RUT Todas las Facturas (1:{len(match_indices)})"
                    else:
                        # 3. Buscar subconjunto exacto mediante Branch & Bound
                        combo = buscar_combinacion_subconjunto(cand_rut, monto_banco, col_monto='Monto_Real')
                        if combo:
                            match_indices = combo
                            tipo_match = f"RUT Pago Agrupado (1:{len(combo)})"

        # =====================================================================
        # ESTRATEGIA 1: SUMA AGRUPADA POR NOMBRE DE CLIENTE (SI NO HAY RUT O FALLÓ)
        # =====================================================================
        if not match_indices and monto_banco > 0:
            indices_cand_nombre = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                similitud = calcular_similitud_textual(texto_c_norm, row_v['Fila_Texto_Norm'])
                if similitud >= 0.45:
                    indices_cand_nombre.append(idx_v)

            if indices_cand_nombre:
                cand_nombre = ventas_disponibles.loc[indices_cand_nombre]
                
                # 1. Evaluar si 1 sola factura coincide exactamente
                exacto_nom = cand_nombre[abs(cand_nombre['Monto_Real'] - monto_banco) <= 2.0]
                if not exacto_nom.empty:
                    match_indices = [exacto_nom.index[0]]
                    tipo_match = "Nombre Exacto (1:1)"
                else:
                    # 2. Buscar combinación que sume exacto
                    combo_nom = buscar_combinacion_subconjunto(cand_nombre, monto_banco, col_monto='Monto_Real')
                    if combo_nom:
                        match_indices = combo_nom
                        tipo_match = f"Nombre Agrupado (1:{len(combo_nom)})"

        # =====================================================================
        # ESTRATEGIA 2: FALLBACK ÚLTIMO RECURSO POR MONTO EXACTO (SÓLO SI ES IDÉNTICO)
        # =====================================================================
        if not match_indices and monto_banco > 0:
            cand_monto_unico = ventas_disponibles[abs(ventas_disponibles['Monto_Real'] - monto_banco) <= 2.0]
            if len(cand_monto_unico) == 1:
                match_indices = [cand_monto_unico.index[0]]
                tipo_match = "Monto Unico Coincidente"

        # =====================================================================
        # REGISTRO DE RESULTADOS
        # =====================================================================
        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
                
            rows_matched = df_ventas_prep.loc[match_indices]
            
            folios = ", ".join([str(r[col_folio_v]) if col_folio_v else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            entidad = rows_matched.iloc[0][col_cliente_v]
            monto_factura_total = rows_matched['Monto_Real'].sum()
            
            dif = monto_banco - monto_factura_total

            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': folios,
                'Entidad Matcheada': entidad,
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_factura_total,
                'Diferencia ($)': dif,
                'Estado Conciliación': '🟢 Conciliado Exacto' if abs(dif) <= 2.0 else '🟡 Diferencia en Monto'
            })
        else:
            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': 'N/A',
                'Entidad Matcheada': 'NO ENCONTRADO',
                'Tipo Coincidencia': 'Sin Coincidencia',
                'Monto Ventas ($)': 0.0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, ventas_pendientes

# -----------------------------------------------------------------------------
# INTERFAZ STREAMLIT
# -----------------------------------------------------------------------------

st.title("🏦 Sistema de Conciliación Bancaria Inteligente")
st.markdown("Cruce avanzado con **coincidencia textual reforzada** y **agrupación de facturas (1 a N)**.")

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
            with st.spinner("Ejecutando cruce optimizado por RUT y montos..."):
                df_cruce, df_pendientes = conciliar_informacion_flexible(df_cartola, df_ventas)

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
    st.info("👆 Por favor sube ambos archivos para iniciar el cruce de información.")
