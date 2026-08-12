import pandas as pd
from utils.limpieza import limpiar_monto_entero, extraer_rut, expandir_y_limpiar_texto

def encontrar_columna(columnas, palabras_clave):
    """Busca de forma inteligente una columna que contenga alguna de las palabras clave."""
    cols_limpias = {col: str(col).strip().upper() for col in columnas}
    for palabra in palabras_clave:
        for col_orig, col_limpia in cols_limpias.items():
            if palabra in col_limpia:
                return col_orig
    return None

def conciliar_cartera_y_cartola(df_cartola, df_ventas):
    """
    Núcleo de cruce inteligente: Relaciona la cartola (PDF o Excel) con la cartera de ventas 
    cruzando por RUT, Montos y texto de la Descripción / Glosa.
    """
    if df_cartola is None or df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_v = df_ventas.copy()

    # Identificar columnas clave en la cartera de ventas de forma flexible
    col_cliente = encontrar_columna(df_v.columns, ['CLIENTE', 'DEUDOR', 'EMPRESA', 'RAZON']) or df_v.columns[0]
    col_rut = encontrar_columna(df_v.columns, ['RUT', 'IDENTIFICACION'])
    col_monto_v = encontrar_columna(df_v.columns, ['MONTO', 'SALDO', 'ADEUDADO', 'TOTAL', 'VALOR'])
    col_folio = encontrar_columna(df_v.columns, ['FOLIO', 'FACTURA', 'DOC', 'NUMERO'])

    # Identificar columnas clave en la cartola unificada
    col_desc_c = encontrar_columna(df_cartola.columns, ['DESCRIPCION', 'DETALLE', 'GLOSA', 'MOVIMIENTO']) or df_cartola.columns[1] if len(df_cartola.columns) > 1 else df_cartola.columns[0]
    col_monto_c = encontrar_columna(df_cartola.columns, ['MONTO', 'ABONOS', 'CREDITO'])

    # Preparar datos normalizados en la cartera de ventas
    df_v['Cliente_Norm'] = df_v[col_cliente].apply(expandir_y_limpiar_texto) if col_cliente in df_v.columns else ""
    df_v['RUT_Norm'] = df_v[col_rut].apply(extraer_rut) if col_rut else df_v.apply(lambda r: extraer_rut(" ".join(str(v) for v in r.values)), axis=1)
    
    if col_monto_v:
        df_v['Monto_Real'] = df_v[col_monto_v].apply(limpiar_monto_entero)
    else:
        df_v['Monto_Real'] = df_v.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    # Recorrer cada movimiento de la cartola
    for idx_c, row_c in df_cartola.iterrows():
        texto_desc_raw = str(row_c[col_desc_c]) if col_desc_c in row_c else " ".join([str(v) for v in row_c.values if pd.notna(v)])
        texto_desc_norm = expandir_y_limpiar_texto(texto_desc_raw)
        rut_c = extraer_rut(texto_desc_raw)
        
        if col_monto_c and col_monto_c in row_c:
            monto_banco = limpiar_monto_entero(row_c[col_monto_c])
        else:
            monto_banco = max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"
        ventas_disponibles = df_v[~df_v.index.isin(indices_ventas_usados)]

        if monto_banco != 0:
            # PRIORIDAD 1: Match por RUT encontrado en el texto de la descripción
            if rut_c:
                cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
                if not cand_rut.empty:
                    exacto_1a1 = cand_rut[abs(cand_rut['Monto_Real'] - abs(monto_banco)) <= 2]
                    if not exacto_1a1.empty:
                        match_indices = [exacto_1a1.index[0]]
                        tipo_match = "🟢 RUT y Monto Exacto (1:1)"
                    else:
                        match_indices = cand_rut.index.tolist()
                        tipo_match = "🟡 RUT Coincide (Diferencia en Monto)"

            # PRIORIDAD 2: Match por Nombre/Cliente mencionado en la descripción
            if not match_indices and not ventas_disponibles.empty:
                for idx_v, row_v in ventas_disponibles.iterrows():
                    nombre_cliente = row_v['Cliente_Norm']
                    if nombre_cliente and len(nombre_cliente) > 4 and nombre_cliente in texto_desc_norm:
                        if abs(row_v['Monto_Real'] - abs(monto_banco)) <= 2:
                            match_indices = [idx_v]
                            tipo_match = "🟢 Cliente y Monto Coincidente por Glosa"
                            break

            # PRIORIDAD 3: Match directo por Monto Exacto si no hay indicios claros pero el monto es único
            if not match_indices:
                exacto_monto = ventas_disponibles[abs(ventas_disponibles['Monto_Real'] - abs(monto_banco)) <= 2]
                if not exacto_monto.empty:
                    match_indices = [exacto_monto.index[0]]
                    tipo_match = "🟡 Coincidencia por Monto (Verificar Glosa)"

        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
            rows_matched = df_v.loc[match_indices]
            
            folios = ", ".join([str(r[col_folio]) if col_folio and col_folio in r else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = abs(monto_banco) - monto_ventas_tot
            estado = '🟢 Conciliado' if abs(dif) <= 2 else '🟡 Diferencia en Monto'

            cruce_list.append({
                'Descripción Cartola': texto_desc_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': folios,
                'Entidad / Deudor': rows_matched.iloc[0][col_cliente] if col_cliente in rows_matched.columns else 'N/A',
                'Tipo Coincidencia': tipo_match,
                'Monto Cartera ($)': monto_ventas_tot,
                'Diferencia ($)': dif,
                'Estado Conciliación': estado
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
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    df_pendientes = df_v[~df_v.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, df_pendientes
