import pandas as pd
import itertools
from utils.limpieza import limpiar_monto_entero, extraer_rut, expandir_y_limpiar_texto

def encontrar_columna(columnas, palabras_clave):
    """Busca de forma inteligente una columna que contenga alguna de las palabras clave."""
    cols_limpias = {col: str(col).strip().upper() for col in columnas}
    for palabra in palabras_clave:
        for col_orig, col_limpia in cols_limpias.items():
            if palabra in col_limpia:
                return col_orig
    return None

def buscar_combinacion_robusta(df_candidatos, monto_objetivo, col_monto='Monto_Real', tolerancia=0):
    """
    Busca de manera eficiente qué combinación de documentos suma exactamente el monto objetivo del banco.
    """
    if df_candidatos.empty or monto_objetivo <= 0:
        return []
        
    cand = df_candidatos[df_candidatos[col_monto] <= (monto_objetivo + tolerancia)].copy()
    if cand.empty:
        return []
        
    cand = cand.sort_values(by=col_monto, ascending=False)
    items = list(cand.index)
    montos = list(cand[col_monto])
    
    resultado_combo = []
    encontrado = False

    def dfs(index, suma_actual, combo_actual):
        nonlocal encontrado
        if encontrado:
            return
        if abs(suma_actual - monto_objetivo) <= tolerancia:
            resultado_combo.extend(combo_actual)
            encontrado = True
            return
        if suma_actual > monto_objetivo + tolerancia or index == len(montos):
            return
        
        dfs(index + 1, suma_actual + montos[index], combo_actual + [items[index]])
        if encontrado:
            return
        dfs(index + 1, suma_actual, combo_actual)

    dfs(0, 0, [])
    return resultado_combo

def conciliar_cartera_y_cartola(df_cartola, df_ventas):
    """
    Núcleo de cruce inteligente con validación estricta de diferencia cero y control de duplicidad.
    """
    if df_cartola is None or df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_v = df_ventas.copy()

    col_cliente = encontrar_columna(df_v.columns, ['CLIENTE', 'DEUDOR', 'EMPRESA', 'RAZON']) or df_v.columns[0]
    col_rut = encontrar_columna(df_v.columns, ['RUT DEUDOR', 'RUT. DEUDOR', 'RUT_DEUDOR', 'RUT DEU', 'RUT'])
    col_monto_v = encontrar_columna(df_v.columns, ['ADEUDADO', 'MONTO TOT', 'MONTO', 'SALDO'])
    col_folio = encontrar_columna(df_v.columns, ['DOC', 'FOLIO', 'FACTURA', 'NUMERO'])

    col_desc_c = encontrar_columna(df_cartola.columns, ['DESCRIPCION', 'DETALLE', 'GLOSA', 'MOVIMIENTO']) or df_cartola.columns[1] if len(df_cartola.columns) > 1 else df_cartola.columns[0]
    col_monto_c = encontrar_columna(df_cartola.columns, ['MONTO', 'ABONOS', 'CREDITO'])

    df_v['RUT_Norm'] = df_v[col_rut].apply(extraer_rut) if col_rut else df_v.apply(lambda r: extraer_rut(" ".join(str(v) for v in r.values)), axis=1)
    
    if col_monto_v:
        df_v['Monto_Real'] = df_v[col_monto_v].apply(limpiar_monto_entero)
    else:
        df_v['Monto_Real'] = df_v.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    for idx_c, row_c in df_cartola.iterrows():
        texto_desc_raw = str(row_c[col_desc_c]) if col_desc_c in row_c else " ".join([str(v) for v in row_c.values if pd.notna(v)])
        rut_c = extraer_rut(texto_desc_raw)
        
        if col_monto_c and col_monto_c in row_c:
            monto_banco = limpiar_monto_entero(row_c[col_monto_c])
        else:
            monto_banco = max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"
        observacion_detalle = "Sin observaciones"
        ventas_disponibles = df_v[~df_v.index.isin(indices_ventas_usados)]

        if monto_banco > 0:
            if rut_c:
                cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
                if not cand_rut.empty:
                    # 1. Buscar match exacto 1 a 1
                    exacto_1a1 = cand_rut[cand_rut['Monto_Real'] == monto_banco]
                    if not exacto_1a1.empty:
                        match_indices = [exacto_1a1.index[0]]
                        tipo_match = "🟢 RUT y Monto Exacto (1:1)"
                    else:
                        # 2. Buscar combinación exacta de suma (1:N)
                        combo = buscar_combinacion_robusta(cand_rut, monto_banco, col_monto='Monto_Real', tolerancia=0)
                        if combo:
                            match_indices = combo
                            tipo_match = f"🟢 RUT Pago Agrupado (1:{len(combo)})"

            # 3. Si no hay match por RUT, buscar por monto exacto global
            if not match_indices:
                exacto_monto = ventas_disponibles[ventas_disponibles['Monto_Real'] == monto_banco]
                if not exacto_monto.empty:
                    match_indices = [exacto_monto.index[0]]
                    tipo_match = "🟡 Coincidencia por Monto (Verificar Glosa)"

        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
            rows_matched = df_v.loc[match_indices]
            
            folios = ", ".join([str(r[col_folio]) if col_folio and col_folio in r else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = monto_banco - monto_ventas_tot

            # Comprobar duplicidad de monto dentro de los candidatos del RUT
            tiene_duplicidad = False
            if rut_c and 'cand_rut' in locals() and not cand_rut.empty:
                mismos_montos = cand_rut[cand_rut['Monto_Real'] == monto_banco]
                if len(mismos_montos) > 1:
                    tiene_duplicidad = True

            # REGLA ESTRICTA: La diferencia debe ser exactamente 0 para considerarse conciliado con éxito
            if dif == 0:
                if tiene_duplicidad:
                    estado = '🟡 Con Observación'
                    observacion_detalle = f'⚠️ Duplicidad: Existen {len(mismos_montos)} documentos con este mismo monto'
                else:
                    estado = '🟢 Conciliado Exacto'
                    observacion_detalle = 'Monto y documentos cuadrados sin observaciones'
            else:
                # Si hay cualquier diferencia, se marca como CON OBSERVACION
                estado = '🟡 Con Observación'
                if tiene_duplicidad:
                    observacion_detalle = f'⚠️ Diferencia de ${dif:,.0f} y existen {len(mismos_montos)} documentos duplicados'
                else:
                    observacion_detalle = f'⚠️ Diferencia de ${dif:,.0f} respecto a cartera'

            cruce_list.append({
                'Descripción Cartola': texto_desc_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': folios,
                'Entidad / Deudor': rows_matched.iloc[0][col_cliente] if col_cliente in rows_matched.columns else 'N/A',
                'Tipo Coincidencia': tipo_match,
                'Monto Cartera ($)': monto_ventas_tot,
                'Diferencia ($)': dif,
                'Estado Conciliación': estado,
                'Detalle / Advertencia': observacion_detalle
            })
        else:
            cruce_list.append({
                'Descripción Cartola': texto_desc_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': 'N/A',
                'Entidad / Deudor': 'NO IDENTIFICADO',
                'Tipo Coincidencia': 'Sin Coincidencia',
                'Monto Cartera ($)': 0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': '🔴 Abono No Identificado',
                'Detalle / Advertencia': 'Sin documentos coincidentes'
            })

    df_cruce = pd.DataFrame(cruce_list)
    df_pendientes = df_v[~df_v.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, df_pendientes

