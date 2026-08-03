import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
from difflib import SequenceMatcher
import io

# Configuración de la página
st.set_page_config(
    page_title="Conciliación Bancaria Inteligente",
    page_icon="📊",
    layout="wide"
)

# -----------------------------------------------------------------------------
# FUNCIONES DE LIMPIEZA Y COINCIDENCIA AVANZADA
# -----------------------------------------------------------------------------

def super_limpiar(texto):
    """Normaliza y comprime cadenas eliminando acentos, espacios y caracteres especiales."""
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8")
    texto = re.sub(r'[^A-Z0-9]', '', texto.upper())
    return texto

def limpiar_monto(val):
    """Convierte cualquier formato monetario (str, int, float) a float limpio."""
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    # Limpiar cadenas con formato $ X.XXX.XXX,XX o $ X,XXX,XXX.XX
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' in val_str:
        # Asume punto de miles y coma decimal
        if val_str.rfind('.') < val_str.rfind(','):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    
    val_str = re.sub(r'[^0-9.-]', '', val_str)
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def calcular_similitud(s1, s2):
    """Retorna un porcentaje de similitud entre dos cadenas superlimpias."""
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()

# -----------------------------------------------------------------------------
# ALGORITMO DE CONCILIACIÓN
# -----------------------------------------------------------------------------

@st.cache_data
def conciliar_informacion_flexible(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    facturas_usadas = set()

    df_ventas_prep = df_ventas.copy()
    
    # Detección dinámica de columna de cliente
    col_cliente_ventas = next((col for col in ['Nombre 2', 'Nombre Cliente', 'Cliente', 'Razon Social'] if col in df_ventas_prep.columns), df_ventas_prep.columns[0])
    
    # Detección dinámica de columna de monto en ventas
    col_monto_ventas = next((col for col in ['Monto Total', 'Monto', 'Total'] if col in df_ventas_prep.columns), None)
    
    # Detección dinámica de Folio
    col_folio_ventas = next((col for col in ['Folio', 'N° Factura', 'Numero', 'Factura'] if col in df_ventas_prep.columns), None)
    if not col_folio_ventas:
        df_ventas_prep['Folio_Auto'] = df_ventas_prep.index + 1
        col_folio_ventas = 'Folio_Auto'

    # Crear columna combinada si existe
    if 'Texto_Fila_Completo' not in df_ventas_prep.columns:
        df_ventas_prep['Texto_Fila_Completo'] = df_ventas_prep.astype(str).agg(' '.join, axis=1)

    df_ventas_prep['Texto_Super_Limpio'] = df_ventas_prep['Texto_Fila_Completo'].apply(super_limpiar)
    df_ventas_prep['Nombre_Super_Limpio'] = df_ventas_prep[col_cliente_ventas].apply(super_limpiar)
    df_ventas_prep['Monto_Limpio'] = df_ventas_prep[col_monto_ventas].apply(limpiar_monto)

    # Identificar columnas de Cartola
    col_glosa_cartola = next((col for col in ['Descripción Glosa', 'Descripción', 'Descripcion', 'Glosa', 'Detalle'] if col in df_cartola.columns), df_cartola.columns[0])
    col_monto_cartola = next((col for col in ['Monto Pago', 'Monto', 'Abono', 'Monto Banco ($)'] if col in df_cartola.columns), None)

    for idx_c, row_c in df_cartola.iterrows():
        glosa_raw = str(row_c.get(col_glosa_cartola, ''))
        identificador_raw = str(row_c.get('Identificador / Cliente', glosa_raw))
        monto_pago = limpiar_monto(row_c.get(col_monto_cartola, 0.0))

        glosa_clean = super_limpiar(glosa_raw)
        identificador_clean = super_limpiar(identificador_raw)

        ventas_disponibles = df_ventas_prep[~df_ventas_prep[col_folio_ventas].isin(facturas_usadas)].copy()

        match_encontrado = None
        tipo_match = "Sin Coincidencia"

        # ESTRATEGIA 1: Cliente/Glosa Coincide + Monto Exacto
        for idx_v, row_v in ventas_disponibles.iterrows():
            nombre_v_clean = row_v['Nombre_Super_Limpio']
            texto_v_clean = row_v['Texto_Super_Limpio']
            monto_v = row_v['Monto_Limpio']

            coincide_nombre = (
                (identificador_clean and identificador_clean in texto_v_clean) or
                (nombre_v_clean and nombre_v_clean in glosa_clean) or
                (identificador_clean and nombre_v_clean and identificador_clean in nombre_v_clean) or
                (nombre_v_clean and identificador_clean and nombre_v_clean in identificador_clean) or
                calcular_similitud(identificador_clean, nombre_v_clean) > 0.70
            )

            if coincide_nombre and abs(monto_pago - monto_v) < 1.0:
                match_encontrado = row_v
                tipo_match = "Cliente + Monto Exacto"
                break

        # ESTRATEGIA 2: Monto Exacto (Ranking por Nombre)
        if match_encontrado is None:
            match_monto = ventas_disponibles[abs(ventas_disponibles['Monto_Limpio'] - monto_pago) < 1.0]
            if not match_monto.empty:
                match_monto = match_monto.copy()
                match_monto['similitud'] = match_monto['Nombre_Super_Limpio'].apply(
                    lambda x: calcular_similitud(identificador_clean, x)
                )
                match_encontrado = match_monto.sort_values(by='similitud', ascending=False).iloc[0]
                tipo_match = "Monto Exacto (Revisar Nombre)"

        # ESTRATEGIA 3: Cliente Coincide pero con Diferencia de Monto
        if match_encontrado is None:
            candidatos_nombre = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                nombre_v_clean = row_v['Nombre_Super_Limpio']
                texto_v_clean = row_v['Texto_Super_Limpio']

                if (identificador_clean and identificador_clean in texto_v_clean) or \
                   (nombre_v_clean and nombre_v_clean in glosa_clean) or \
                   calcular_similitud(identificador_clean, nombre_v_clean) > 0.70:
                    candidatos_nombre.append(row_v)

            if candidatos_nombre:
                df_cand = pd.DataFrame(candidatos_nombre)
                df_cand['dif_abs'] = (df_cand['Monto_Limpio'] - monto_pago).abs()
                match_encontrado = df_cand.sort_values(by='dif_abs').iloc[0]
                tipo_match = "Cliente Coincide (Diferencia Monto)"

        # REGISTRO DE RESULTADOS
        if match_encontrado is not None:
            facturas_usadas.add(match_encontrado[col_folio_ventas])
            monto_factura = float(match_encontrado['Monto_Limpio'])
            dif = monto_pago - monto_factura

            if abs(dif) < 1.0:
                estado = '🟢 Conciliado Exacto'
            else:
                estado = '🟡 Diferencia en Monto'

            cruce_list.append({
                'Identificador Cartola': identificador_raw,
                'Monto Banco ($)': monto_pago,
                'Folios Factura(s)': match_encontrado[col_folio_ventas],
                'Entidad Matcheada': match_encontrado[col_cliente_ventas],
                'Match Por': tipo_match,
                'Monto Factura ($)': monto_factura,
                'Diferencia ($)': dif,
                'Estado Conciliación': estado
            })
        else:
            cruce_list.append({
                'Identificador Cartola': identificador_raw,
                'Monto Banco ($)': monto_pago,
                'Folios Factura(s)': 'N/A',
                'Entidad Matcheada': 'NO ENCONTRADO',
                'Match Por': 'Sin Coincidencia',
                'Monto Factura ($)': 0.0,
                'Diferencia ($)': monto_pago,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    ventas_pendientes = df_ventas_prep[~df_ventas_prep[col_folio_ventas].isin(facturas_usadas)].copy()
    if not ventas_pendientes.empty:
        ventas_pendientes['Estado'] = '🔵 Documento Pendiente de Pago'

    return df_cruce, ventas_pendientes

# -----------------------------------------------------------------------------
# INTERFAZ STREAMLIT
# -----------------------------------------------------------------------------

st.title("🏦 Sistema de Conciliación Bancaria Inteligente")
st.markdown("Carga tus archivos de **Cartola Bancaria** y **Registro de Ventas/Cobranzas** para ejecutar el cruce automático con coincidencia flexible.")

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
            with st.spinner("Procesando cruce de información..."):
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
