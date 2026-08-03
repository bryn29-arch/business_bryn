import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
from itertools import combinations
from difflib import SequenceMatcher
import io

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Conciliación Bancaria Avanzada",
    page_icon="📊",
    layout="wide"
)

# -----------------------------------------------------------------------------
# DICCIONARIOS Y FUNCIONES DE TEXTO Y MONTO
# -----------------------------------------------------------------------------
ABREVIATURAS = {
    'CORP': 'CORPORACION',
    'EDUC': 'EDUCACION',
    'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC',
    'ANONIMA': 'SA',
    'HERMANOS': 'HROS',
    'EIRL': '',
    'SPA': ''
}

def expandir_y_limpiar_texto(texto):
    """Normaliza texto, remueve acentos y estandariza abreviaturas frecuentes."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    texto = re.sub(r'[^A-Z0-9\s]', ' ', texto)
    
    palabras = texto.split()
    palabras_norm = [ABREVIATURAS.get(p, p) for p in palabras]
    return " ".join(palabras_norm)

def extraer_tokens_clave(texto_fila):
    """Extrae palabras de más de 2 letras excluyendo palabras vacías bancarias."""
    texto_clean = expandir_y_limpiar_texto(texto_fila)
    palabras = set(re.findall(r'\b[A-Z0-9]{3,}\b', texto_clean))
    stopwords = {'TRASPASO', 'TRANSFERENCIA', 'BANCO', 'PAGO', 'DEBITO', 'CREDITO', 'INTERNET', 'VALE', 'VISTA', 'CHILE', 'CANAL', 'INFORMACION'}
    return palabras - stopwords

def calcular_similitud_textual(texto1, texto2):
    """Evalúa coincidencia combinando contención directa, Jaccard por tokens y Fuzzy Ratio."""
    if not texto1 or not texto2:
        return 0.0
    
    t1 = expandir_y_limpiar_texto(texto1)
    t2 = expandir_y_limpiar_texto(texto2)
    
    # Contención directa
    if len(t1) > 4 and len(t2) > 4:
        if t1 in t2 or t2 in t1:
            return 1.0
            
    # Coincidencia por tokens
    tokens1 = extraer_tokens_clave(t1)
    tokens2 = extraer_tokens_clave(t2)
    
    if tokens1 and tokens2:
        interseccion = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        ratio_jaccard = len(interseccion) / len(union) if union else 0.0
        
        if len(interseccion) >= 2:
            return max(0.85, ratio_jaccard)
        if len(interseccion) == 1 and ratio_jaccard > 0.4:
            return 0.75
            
    # Respaldo con Fuzzy SequenceMatcher
    return SequenceMatcher(None, t1, t2).ratio()

def extraer_montos_de_fila(row):
    """Extrae todos los números/montos válidos de las celdas de una fila."""
    montos = []
    for val in row.values:
        if pd.isna(val):
            continue
        if isinstance(val, (int, float)):
            if abs(val) > 0:
                montos.append(abs(float(val)))
        else:
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
                num = float(val_str)
                if abs(num) > 0:
                    montos.append(abs(num))
            except ValueError:
                pass
    return montos

# -----------------------------------------------------------------------------
# ALGORITMO DE CONCILIACIÓN
# -----------------------------------------------------------------------------

@st.cache_data
def conciliar_informacion_flexible(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()

    # Preprocesamiento de Ventas
    df_ventas_prep = df_ventas.copy()
    df_ventas_prep['Fila_Texto'] = df_ventas_prep.apply(lambda r: " ".join([str(v) for v in r.values if pd.notna(v)]), axis=1)
    df_ventas_prep['Fila_Texto_Norm'] = df_ventas_prep['Fila_Texto'].apply(expandir_y_limpiar_texto)
    df_ventas_prep['Fila_Montos'] = df_ventas_prep.apply(extraer_montos_de_fila, axis=1)
    
    col_folio_v = next((c for c in ['Folio', 'N° Factura', 'Numero', 'Factura', 'ID'] if c in df_ventas_prep.columns), None)
    col_cliente_v = next((c for c in ['Nombre 2', 'Nombre Cliente', 'Cliente', 'Razon Social'] if c in df_ventas_prep.columns), df_ventas_prep.columns[0])

    for idx_c, row_c in df_cartola.iterrows():
        texto_c_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        texto_c_norm = expandir_y_limpiar_texto(texto_c_raw)
        montos_c = extraer_montos_de_fila(row_c)
        monto_banco = montos_c[0] if montos_c else 0.0

        match_indices = []
        tipo_match = "Sin Coincidencia"

        ventas_disponibles = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)]

        # --- ESTRATEGIA 1: Texto Reforzado + Monto Exacto (1 a 1) ---
        for idx_v, row_v in ventas_disponibles.iterrows():
            similitud_texto = calcular_similitud_textual(texto_c_norm, row_v['Fila_Texto_Norm'])
            coincide_monto = any(abs(monto_banco - mv) < 1.0 for mv in row_v['Fila_Montos'])

            if similitud_texto >= 0.70 and coincide_monto:
                match_indices = [idx_v]
                tipo_match = f"1 a 1: Texto ({int(similitud_texto*100)}%) + Monto Exacto"
                break

        # --- ESTRATEGIA 2: Texto Reforzado + Suma Agrupada de Facturas (1 a N) ---
        if not match_indices and monto_banco > 0:
            candidatos_cliente = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                similitud = calcular_similitud_textual(texto_c_norm, row_v['Fila_Texto_Norm'])
                if similitud >= 0.65:
                    candidatos_cliente.append((idx_v, row_v))

            if candidatos_cliente:
                encontrado_grupo = False
                indices_cand = [c[0] for c in candidatos_cliente]
                
                for r in range(2, min(6, len(indices_cand) + 1)):
                    for combo in combinations(indices_cand, r):
                        suma_combo = sum(
                            df_ventas_prep.loc[i, 'Fila_Montos'][0] 
                            for i in combo if df_ventas_prep.loc[i, 'Fila_Montos']
                        )
                        if abs(monto_banco - suma_combo) < 1.0:
                            match_indices = list(combo)
                            tipo_match = f"Agrupado (1 a {len(combo)}): Suma Facturas Cliente Matcheado"
                            encontrado_grupo = True
                            break
                    if encontrado_grupo:
                        break

        # --- ESTRATEGIA 3: Fallback por Monto Exacto (Evaluando Similitud Texto) ---
        if not match_indices and monto_banco > 0:
            candidatos_monto = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                if any(abs(monto_banco - mv) < 1.0 for mv in row_v['Fila_Montos']):
                    similitud = calcular_similitud_textual(texto_c_norm, row_v['Fila_Texto_Norm'])
                    candidatos_monto.append((idx_v, similitud))

            if candidatos_monto:
                candidatos_monto.sort(key=lambda x: x[1], reverse=True)
                best_idx, best_sim = candidatos_monto[0]
                match_indices = [best_idx]
                tipo_match = f"Monto Exacto (Similitud Texto: {int(best_sim*100)}%)"

        # --- REGISTRO DE RESULTADOS ---
        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
                
            rows_matched = df_ventas_prep.loc[match_indices]
            
            folios = ", ".join([str(r[col_folio_v]) if col_folio_v else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            entidad = rows_matched.iloc[0][col_cliente_v]
            monto_factura_total = sum([r['Fila_Montos'][0] for _, r in rows_matched.iterrows() if r['Fila_Montos']])
            
            dif = monto_banco - monto_factura_total

            cruce_list.append({
                'Texto Cartola (Fila)': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': folios,
                'Entidad Matcheada': entidad,
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_factura_total,
                'Diferencia ($)': dif,
                'Estado Conciliación': '🟢 Conciliado Exacto' if abs(dif) < 1.0 else '🟡 Diferencia en Monto'
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
            with st.spinner("Ejecutando cruce textual avanzado..."):
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
