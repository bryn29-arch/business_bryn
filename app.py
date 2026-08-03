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
    page_title="Conciliación Bancaria Avanzada Definitiva",
    page_icon="📊",
    layout="wide"
)

# -----------------------------------------------------------------------------
# FUNCIONES DE NORMALIZACIÓN
# -----------------------------------------------------------------------------
ABREVIATURAS = {
    'CORP': 'CORPORACION', 'EDUC': 'EDUCACION', 'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC', 'ANONIMA': 'SA', 'HERMANOS': 'HROS',
    'EIRL': '', 'SPA': '', 'S': 'SPA', 'EXP': 'EXPORTACION',
    'ING': 'INGENIERIA', 'SERV': 'SERVICIOS', 'SER': 'SERVICIOS',
    'ADM': 'ADMINISTRADORA', 'TRANSPORTE': 'TRANSPORTES'
}

def limpiar_rut(texto):
    """Extrae RUTs garantizando formato limpio sin puntos ni guion (ej: 76334370K)."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    match = re.search(r'\b(\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK])\b', str(texto))
    if match:
        return re.sub(r'[^0-9K]', '', match.group(1).upper())
    return ""

def expandir_y_limpiar_texto(texto):
    """Limpia tildes, caracteres especiales y expande siglas."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    texto = re.sub(r'[^A-Z0-9\s]', ' ', texto)
    
    palabras = texto.split()
    palabras_norm = [ABREVIATURAS.get(p, p) for p in palabras]
    return " ".join(palabras_norm).strip()

def convertir_monto_limpio(val):
    """Transforma montos con puntos/comas/caracteres a un numero flotante puro."""
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

def calcular_similitud_textual(t1, t2):
    """Evalúa coincidencia por coincidencia de inicio (truncados de banco) y fuzzy."""
    if not t1 or not t2:
        return 0.0
    t1_c = expandir_y_limpiar_texto(t1)
    t2_c = expandir_y_limpiar_texto(t2)
    
    if not t1_c or not t2_c:
        return 0.0

    # Coincidencia por inicio de texto (para nombres truncados por el banco)
    min_l = min(len(t1_c), len(t2_c))
    if min_l >= 6 and (t1_c[:min_l] == t2_c[:min_l] or t1_c in t2_c or t2_c in t1_c):
        return 0.95

    return SequenceMatcher(None, t1_c, t2_c).ratio()

# -----------------------------------------------------------------------------
# ALGORITMO DE CONCILIACIÓN ESTRUCTURADO
# -----------------------------------------------------------------------------

def conciliar_informacion_flexible(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()

    # Identificación Inteligente de Columnas Clave en Ventas
    col_v_rut = next((c for c in df_ventas.columns if 'RUT' in c.upper()), None)
    col_v_cliente = next((c for c in df_ventas.columns if any(x in c.upper() for x in ['DEUDOR', 'CLIENTE', 'RAZON', 'NOMBRE'])), df_ventas.columns[0])
    col_v_monto = next((c for c in df_ventas.columns if any(x in c.upper() for x in ['MONTO', 'TOTAL', 'VALOR', 'SALDO'])), None)
    col_v_folio = next((c for c in df_ventas.columns if any(x in c.upper() for x in ['DOC', 'FOLIO', 'FACTURA', 'N°'])), None)

    # Identificación Inteligente de Columnas Clave en Cartola
    col_c_monto = next((c for c in df_cartola.columns if any(x in c.upper() for x in ['ABONO', 'CREDITO', 'MONTO', 'DEPOSITO'])), df_cartola.columns[-1])
    col_c_desc = next((c for c in df_cartola.columns if any(x in c.upper() for x in ['DESCRIPCION', 'CONCEPTO', 'DETALLE', 'GLOSA', 'NOMBRE'])), df_cartola.columns[0])

    # Preprocesamiento Aislado por Columna
    df_v = df_ventas.copy()
    df_v['V_Monto'] = df_v[col_v_monto].apply(convertir_monto_limpio) if col_v_monto else 0.0
    df_v['V_RUT'] = df_v[col_v_rut].apply(limpiar_rut) if col_v_rut else df_v.apply(lambda r: limpiar_rut(str(r.values)), axis=1)
    df_v['V_Cliente'] = df_v[col_v_cliente].astype(str).apply(expandir_y_limpiar_texto)
    df_v['V_Folio'] = df_v[col_v_folio].astype(str) if col_v_folio else df_v.index.astype(str)

    for idx_c, row_c in df_cartola.iterrows():
        texto_cartola_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        desc_banco = str(row_c[col_c_desc]) if col_c_desc else texto_cartola_raw
        monto_banco = convertir_monto_limpio(row_c[col_c_monto])
        rut_banco = limpiar_rut(texto_cartola_raw)

        if monto_banco <= 0:
            continue

        match_indices = []
        tipo_match = "Sin Coincidencia"

        ventas_disp = df_v[~df_v.index.isin(indices_ventas_usados)].copy()

        # =====================================================================
        # PASO 1: EVALUACIÓN POR RUT (PRIORIDAD EN SUMAS 1:N Y MATCH EXACTO)
        # =====================================================================
        if rut_banco:
            cand_rut = ventas_disp[ventas_disp['V_RUT'] == rut_banco]
            
            if not cand_rut.empty:
                indices_cand_rut = cand_rut.index.tolist()
                
                # Probar primero si combinaciones de 1 a N facturas suman EXACTO el abono bancario
                encontrado_rut = False
                for r in range(1, min(12, len(indices_cand_rut) + 1)):
                    for combo in combinations(indices_cand_rut, r):
                        suma_combo = sum(ventas_disp.loc[i, 'V_Monto'] for i in combo)
                        if abs(monto_banco - suma_combo) < 1.0:
                            match_indices = list(combo)
                            tipo_match = f"RUT 1 (Pago Agrupado 1:{len(combo)})" if len(combo) > 1 else "RUT 1 (Exacto 1:1)"
                            encontrado_rut = True
                            break
                    if encontrado_rut:
                        break

        # =====================================================================
        # PASO 2: EVALUACIÓN POR NOMBRE / TEXTO FLEXIBLE
        # =====================================================================
        if not match_indices:
            # 2.1 Match 1 a 1 (Nombre Flex + Monto Exacto)
            for idx_v, row_v in ventas_disp.iterrows():
                sim = calcular_similitud_textual(desc_banco, row_v['V_Cliente'])
                if sim >= 0.40 and abs(monto_banco - row_v['V_Monto']) < 1.0:
                    match_indices = [idx_v]
                    tipo_match = f"Nombre 1 (Flex) (Exacto 1:1)"
                    break

            # 2.2 Suma Agrupada 1 a N por Nombre
            if not match_indices:
                cand_nom = [i for i, r in ventas_disp.iterrows() if calcular_similitud_textual(desc_banco, r['V_Cliente']) >= 0.35]
                
                if len(cand_nom) >= 2:
                    encontrado_nom = False
                    for r in range(2, min(8, len(cand_nom) + 1)):
                        for combo in combinations(cand_nom, r):
                            suma_combo = sum(ventas_disp.loc[i, 'V_Monto'] for i in combo)
                            if abs(monto_banco - suma_combo) < 1.0:
                                match_indices = list(combo)
                                tipo_match = f"Agrupado (1 a {len(combo)}): Suma Facturas Cuadrada"
                                encontrado_nom = True
                                break
                        if encontrado_nom:
                            break

        # =====================================================================
        # PASO 3: RESCATE POR MONTO ÚNICO EXACTO
        # =====================================================================
        if not match_indices:
            cand_monto = ventas_disp[abs(ventas_disp['V_Monto'] - monto_banco) < 1.0]
            if len(cand_monto) == 1:
                best_idx = cand_monto.index[0]
                sim = calcular_similitud_textual(desc_banco, cand_monto.loc[best_idx, 'V_Cliente'])
                match_indices = [best_idx]
                tipo_match = f"Monto Exacto Flex (Similitud: {int(sim*100)}%)"

        # =====================================================================
        # REGISTRO DE RESULTADOS
        # =====================================================================
        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
                
            rows_matched = df_v.loc[match_indices]
            folios = ", ".join(rows_matched['V_Folio'].tolist())
            entidad = rows_matched['V_Cliente'].iloc[0]
            monto_ventas_total = rows_matched['V_Monto'].sum()
            dif = monto_banco - monto_ventas_total

            cruce_list.append({
                'Texto Cartola (Fila)': desc_banco,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': folios,
                'Entidad Matcheada': entidad,
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_ventas_total,
                'Diferencia ($)': dif,
                'Estado Conciliación': '🟢 Conciliado Exacto' if abs(dif) < 1.0 else '🟡 Diferencia en Monto'
            })
        else:
            cruce_list.append({
                'Texto Cartola (Fila)': desc_banco,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Ventas Matcheado(s)': 'N/A',
                'Entidad Matcheada': 'NO ENCONTRADO',
                'Tipo Coincidencia': 'Sin Coincidencia',
                'Monto Ventas ($)': 0.0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_v[~df_v.index.isin(indices_ventas_usados)].copy()
    
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
            with st.spinner("Ejecutando cruce estructurado por columnas..."):
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
