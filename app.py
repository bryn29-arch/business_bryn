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
    """
    Normaliza y comprime cadenas eliminando acentos, espacios, puntos y caracteres especiales.
    """
    if not isinstance(texto, str) or pd.isna(texto):
        return ""
    # Quitar acentos / diacríticos
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8")
    # Convertir a mayúsculas y dejar solo letras y números
    texto = re.sub(r'[^A-Z0-9]', '', texto.upper())
    return texto

def obtener_palabras_clave(texto):
    """Extrae palabras de más de 2 caracteres para cruce por tokens."""
    if not isinstance(texto, str) or pd.isna(texto):
        return set()
    texto_norm = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    palabras = re.findall(r'\b[A-Z0-9]{3,}\b', texto_norm)
    # Filtrar palabras comunes de transferencias que generan falsos positivos
    stopwords = {'TRASPASO', 'TRANSFERENCIA', 'BANCO', 'PAGO', 'DEBITO', 'CREDITO', 'VALE', 'VISTA', 'INVERSIONES', 'CHILE'}
    return set(p for p in palabras if p not in stopwords)

def limpiar_monto(val):
    """Convierte cualquier formato monetario (str, int, float) a float limpio."""
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
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
        return float(val_str)
    except ValueError:
        return 0.0

def calcular_similitud(s1, s2):
    """Retorna porcentaje de similitud entre dos cadenas (0.0 a 1.0)."""
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()

import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import re
from difflib import SequenceMatcher
import io

# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE FILA Y MONTO
# -----------------------------------------------------------------------------

def aplanar_y_limpiar_fila(row):
    """
    Concatena todas las celdas de una fila en un solo texto en mayúsculas,
    sin acentos ni caracteres especiales.
    """
    texto_unido = " ".join([str(val) for val in row.values if pd.notna(val)])
    # Quitar acentos
    texto_unido = unicodedata.normalize('NFD', texto_unido).encode('ascii', 'ignore').decode("utf-8")
    # Convertir a mayúsculas y dejar solo letras, números y espacios
    texto_limpio = re.sub(r'[^A-Z0-9\s]', ' ', texto_unido.upper())
    # Colapsar múltiples espacios
    return re.sub(r'\s+', ' ', texto_limpio).strip()

def extraer_montos_de_fila(row):
    """
    Extrae todos los números/montos válidos de las celdas de una fila.
    """
    montos = []
    for val in row.values:
        if pd.isna(val):
            continue
        if isinstance(val, (int, float)):
            if abs(val) > 0:
                montos.append(abs(float(val)))
        else:
            # Limpieza de cadenas numéricas estilo $ 4,046,000 o 4.046.000
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

def extraer_tokens_clave(texto_fila):
    """Extrae palabras relevantes de más de 3 letras excluyendo términos bancarios comunes."""
    palabras = set(re.findall(r'\b[A-Z0-9]{3,}\b', texto_fila))
    stopwords = {'TRASPASO', 'TRANSFERENCIA', 'BANCO', 'PAGO', 'DEBITO', 'CREDITO', 'INTERNET', 'VALE', 'VISTA', 'CHILE', 'SUL', 'CANAL'}
    return palabras - stopwords

# -----------------------------------------------------------------------------
# ALGORITMO DE CONCILIACIÓN POR FILAS
# -----------------------------------------------------------------------------

@st.cache_data
def conciliar_informacion_flexible(df_cartola, df_ventas):
    if df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()

    # Preprocesar Ventas por Fila Completa
    df_ventas_prep = df_ventas.copy()
    df_ventas_prep['Fila_Texto'] = df_ventas_prep.apply(aplanar_y_limpiar_fila, axis=1)
    df_ventas_prep['Fila_Montos'] = df_ventas_prep.apply(extraer_montos_de_fila, axis=1)
    df_ventas_prep['Fila_Tokens'] = df_ventas_prep['Fila_Texto'].apply(extraer_tokens_clave)
    
    # Intentar obtener un identificador visible para el reporte final
    col_folio_v = next((c for c in ['Folio', 'N° Factura', 'Numero', 'Factura', 'ID'] if c in df_ventas_prep.columns), None)
    col_cliente_v = next((c for c in ['Nombre 2', 'Nombre Cliente', 'Cliente', 'Razon Social'] if c in df_ventas_prep.columns), df_ventas_prep.columns[0])

    # Iterar Fila por Fila en Cartola
    for idx_c, row_c in df_cartola.iterrows():
        texto_c = aplanar_y_limpiar_fila(row_c)
        montos_c = extraer_montos_de_fila(row_c)
        tokens_c = extraer_tokens_clave(texto_c)
        
        monto_banco = montos_c[0] if montos_c else 0.0

        match_idx = None
        tipo_match = "Sin Coincidencia"

        # Filtrar solo las ventas no asignadas aún
        ventas_disponibles = df_ventas_prep[~df_ventas_prep.index.isin(indices_ventas_usados)]

        # --- ESTRATEGIA 1: Coincidencia de Nombre/Tokens + Monto Exacto en Fila ---
        for idx_v, row_v in ventas_disponibles.iterrows():
            texto_v = row_v['Fila_Texto']
            montos_v = row_v['Fila_Montos']
            tokens_v = row_v['Fila_Tokens']

            # Validar si comparten tokens del cliente (ej. PRODRILLING)
            coincide_cliente = bool(tokens_c.intersection(tokens_v))
            
            # Validar si el monto de la cartola está en los montos de la fila de ventas
            coincide_monto = any(abs(monto_banco - mv) < 1.0 for mv in montos_v)

            if coincide_cliente and coincide_monto:
                match_idx = idx_v
                tipo_match = "Fila Completa: Cliente + Monto Exacto"
                break

        # --- ESTRATEGIA 2: Monto Exacto en Fila (Si hay varias, se toma la que tenga coincidencia de palabras) ---
        if match_idx is None and monto_banco > 0:
            candidatos_monto = []
            for idx_v, row_v in ventas_disponibles.iterrows():
                if any(abs(monto_banco - mv) < 1.0 for mv in row_v['Fila_Montos']):
                    # Calcular cuántas palabras comparten
                    coincidencias = len(tokens_c.intersection(row_v['Fila_Tokens']))
                    candidatos_monto.append((idx_v, coincidencias, row_v))
            
            if candidatos_monto:
                # Ordenar por el que tenga más palabras en común
                candidatos_monto.sort(key=lambda x: x[1], reverse=True)
                match_idx = candidatos_monto[0][0]
                tipo_match = "Fila Completa: Monto Exacto"

        # --- ESTRATEGIA 3: Cliente Coincide en Fila (Diferencia de Monto) ---
        if match_idx is None and tokens_c:
            for idx_v, row_v in ventas_disponibles.iterrows():
                if tokens_c.intersection(row_v['Fila_Tokens']):
                    match_idx = idx_v
                    tipo_match = "Fila Completa: Cliente Coincide (Dif. Monto)"
                    break

        # --- REGISTRO DE RESULTADOS ---
        if match_idx is not None:
            indices_ventas_usados.add(match_idx)
            row_match = df_ventas_prep.loc[match_idx]
            
            monto_factura = row_match['Fila_Montos'][0] if row_match['Fila_Montos'] else 0.0
            dif = monto_banco - monto_factura
            folio_doc = row_match[col_folio_v] if col_folio_v else f"FILA-{match_idx + 1}"
            entidad_doc = row_match[col_cliente_v]

            cruce_list.append({
                'Texto Cartola (Fila)': texto_c,
                'Monto Banco ($)': monto_banco,
                'Folio / ID Ventas': folio_doc,
                'Entidad Matcheada': entidad_doc,
                'Tipo Coincidencia': tipo_match,
                'Monto Ventas ($)': monto_factura,
                'Diferencia ($)': dif,
                'Estado Conciliación': '🟢 Conciliado Exacto' if abs(dif) < 1.0 else '🟡 Diferencia en Monto'
            })
        else:
            cruce_list.append({
                'Texto Cartola (Fila)': texto_c,
                'Monto Banco ($)': monto_banco,
                'Folio / ID Ventas': 'N/A',
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
st.markdown("Carga tus archivos de **Cartola Bancaria** y **Registro de Ventas/Cobranzas** para ejecutar el cruce automático.")

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
