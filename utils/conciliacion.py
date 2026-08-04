import pandas as pd
from utils.limpieza import limpiar_monto_entero, extraer_rut, expandir_y_limpiar_texto

def conciliar_cartera_y_cartola(df_cartola, df_ventas):
    """
    Núcleo de cruce y emparejamiento inteligente entre la cartola bancaria y la cartera.
    Busca coincidencias por RUT y montos con tolerancia.
    """
    if df_cartola is None or df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_v = df_ventas.copy()

    # Identificar columnas clave en la cartera de ventas de forma segura
    cols_v = df_v.columns
    col_cliente = next((c for c in cols_v if 'CLIENTE' in str(c).upper() or 'DEUDOR' in str(c).upper()), cols_v[0])
    col_rut = next((c for c in cols_v if 'RUT' in str(c).upper()), None)
    col_monto_v = next((c for c in cols_v if 'MONTO' in str(c).upper() or 'SALDO' in str(c).upper() or 'ADEUDADO' in str(c).upper()), None)
    col_folio = next((c for c in cols_v if 'FOLIO' in str(c).upper() or 'FACTURA' in str(c).upper() or 'DOC' in str(c).upper()), None)

    # Identificar columnas clave en la cartola
    cols_c = df_cartola.columns
    col_monto_c = next((c for c in cols_c if 'ABONO' in str(c).upper() or 'DEPOSITO' in str(c).upper() or 'CREDITO' in str(c).upper() or 'MONTO' in str(c).upper()), cols_c[-1])

    # Preparar datos en la cartera
    df_v['RUT_Norm'] = df_v[col_rut].apply(extraer_rut) if col_rut else df_v.apply(lambda r: extraer_rut(" ".join(str(v) for v in r.values)), axis=1)
    df_v['Monto_Real'] = df_v[col_monto_v].apply(limpiar_monto_entero) if col_monto_v else df_v.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    # Recorrer cada movimiento de la cartola bancaria
    for idx_c, row_c in df_cartola.iterrows():
        texto_c_raw = " ".join([str(v) for v in row_c.values if pd.notna(v)])
        rut_c = extraer_rut(texto_c_raw)
        monto_banco = limpiar_monto_entero(row_c[col_monto_c]) if col_monto_c in row_c else max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"
        ventas_disponibles = df_v[~df_v.index.isin(indices_ventas_usados)]

        if rut_c and monto_banco > 0:
            cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
            if not cand_rut.empty:
                # Coincidencia exacta 1 a 1 (con tolerancia de $2 por comisiones)
                exacto_1a1 = cand_rut[abs(cand_rut['Monto_Real'] - monto_banco) <= 2]
                if not exacto_1a1.empty:
                    match_indices = [exacto_1a1.index[0]]
                    tipo_match = "🟢 RUT y Monto Exacto (1:1)"
                else:
                    match_indices = cand_rut.index.tolist()
                    tipo_match = "🟡 RUT Coincide (Diferencia en Monto)"

        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
            rows_matched = df_v.loc[match_indices]
            folios = ", ".join([str(r[col_folio]) if col_folio and col_folio in r else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = monto_banco - monto_ventas_tot
            estado = '🟢 Conciliado Exacto' if abs(dif) <= 2 else '🟡 Diferencia en Monto'

            cruce_list.append({
                'Texto Cartola': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': folios,
                'Entidad': rows_matched.iloc[0][col_cliente] if col_cliente in rows_matched.columns else 'N/A',
                'Tipo Coincidencia': tipo_match,
                'Monto Cartera ($)': monto_ventas_tot,
                'Diferencia ($)': dif,
                'Estado Conciliación': estado
            })
        else:
            cruce_list.append({
                'Texto Cartola': texto_c_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': 'N/A',
                'Entidad': 'NO ENCONTRADO',
                'Tipo Coincidencia': 'Sin Coincidencia',
                'Monto Cartera ($)': 0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': '🔴 Abono No Identificado'
            })

    df_cruce = pd.DataFrame(cruce_list)
    df_pendientes = df_v[~df_v.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, df_pendientes
