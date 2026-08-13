import pandas as pd
import itertools
from utils.limpieza import limpiar_monto_entero, extraer_rut, expandir_y_limpiar_texto

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


def _seleccionar_documento_por_duplicidad(df_duplicados, col_fecha='FECHA DE EMISION'):
    """
    Cuando hay múltiples documentos con el MISMO deudor y MISMO monto,
    elige el más antiguo (que lleva más tiempo sin pagar).
    
    Si la columna de fecha no existe, devuelve el primer índice.
    """
    if df_duplicados.empty:
        return None
    
    # Intentar ordenar por fecha si existe
    if col_fecha in df_duplicados.columns:
        try:
            df_dup_copy = df_duplicados.copy()
            # Convertir a datetime (maneja formatos variados)
            df_dup_copy[col_fecha] = pd.to_datetime(
                df_dup_copy[col_fecha], 
                errors='coerce'
            )
            # Ordenar ascendente: la más antigua primero
            df_dup_copy = df_dup_copy.sort_values(by=col_fecha, na_position='last')
            return df_dup_copy.index[0]
        except Exception:
            # Si la conversión falla, retorna el primero
            return df_duplicados.index[0]
    else:
        # Si no existe fecha, devuelve el primero (mejor que nada)
        return df_duplicados.index[0]


def conciliar_cartera_y_cartola(df_cartola, df_ventas):
    """
    Núcleo de cruce inteligente utilizando las columnas mapeadas manualmente por el usuario.
    
    MEJORAS:
    - Cuando hay múltiples documentos del mismo deudor + mismo monto,
      elige el más antiguo (desempate por fecha de emisión).
    - Detecta y alerta claramente cuando hay ambigüedad.
    """
    if df_cartola is None or df_cartola.empty or df_ventas is None or df_ventas.empty:
        return pd.DataFrame(), pd.DataFrame()

    cruce_list = []
    indices_ventas_usados = set()
    df_v = df_ventas.copy()

    # Mapeo directo de las columnas seleccionadas en la interfaz de Streamlit
    col_cliente = 'CLIENTE_MAP' if 'CLIENTE_MAP' in df_v.columns else df_v.columns[0]
    col_rut = 'RUT_DEUDOR_MAP' if 'RUT_DEUDOR_MAP' in df_v.columns else None
    col_monto_v = 'MONTO_MAP' if 'MONTO_MAP' in df_v.columns else None
    col_folio = 'FOLIO_MAP' if 'FOLIO_MAP' in df_v.columns else None

    # Identificar columnas clave en la cartola
    col_desc_c = 'DESCRIPCION' if 'DESCRIPCION' in df_cartola.columns else (df_cartola.columns[1] if len(df_cartola.columns) > 1 else df_cartola.columns[0])
    col_monto_c = 'MONTO' if 'MONTO' in df_cartola.columns else None

    # Normalizar datos de la cartera
    df_v['RUT_Norm'] = df_v[col_rut].apply(extraer_rut) if col_rut else df_v.apply(lambda r: extraer_rut(" ".join(str(v) for v in r.values)), axis=1)
    
    if col_monto_v:
        df_v['Monto_Real'] = df_v[col_monto_v].apply(limpiar_monto_entero)
    else:
        df_v['Monto_Real'] = df_v.apply(lambda r: max([limpiar_monto_entero(v) for v in r.values] + [0]), axis=1)

    # Recorrer cada movimiento de la cartola
    for idx_c, row_c in df_cartola.iterrows():
        texto_desc_raw = str(row_c[col_desc_c]) if col_desc_c in row_c else " ".join([str(v) for v in row_c.values if pd.notna(v)])
        rut_c = extraer_rut(texto_desc_raw)
        
        if col_monto_c and col_monto_c in row_c:
            monto_banco = limpiar_monto_entero(row_c[col_monto_c])
        else:
            monto_banco = max([limpiar_monto_entero(v) for v in row_c.values] + [0])

        match_indices = []
        tipo_match = "Sin Coincidencia"
        observacion_detalle = "Sin documentos coincidentes"
        ventas_disponibles = df_v[~df_v.index.isin(indices_ventas_usados)]

        if monto_banco > 0:
            if rut_c:
                cand_rut = ventas_disponibles[ventas_disponibles['RUT_Norm'] == rut_c]
                if not cand_rut.empty:
                    # 1. Buscar match exacto 1 a 1 para ese RUT
                    exacto_1a1 = cand_rut[cand_rut['Monto_Real'] == monto_banco]
                    if not exacto_1a1.empty:
                        # 🛠️ MEJORA: Si hay múltiples con el mismo monto, elige el más antiguo
                        if len(exacto_1a1) > 1:
                            idx_seleccionado = _seleccionar_documento_por_duplicidad(
                                exacto_1a1,
                                col_fecha='FECHA DE EMISION'
                            )
                            match_indices = [idx_seleccionado]
                            tipo_match = f"🟢 RUT y Monto Exacto (Más Antiguo de {len(exacto_1a1)})"
                        else:
                            match_indices = [exacto_1a1.index[0]]
                            tipo_match = "🟢 RUT y Monto Exacto (1:1)"
                    else:
                        # 2. Buscar combinación exacta de suma (1:N) para ese RUT
                        combo = buscar_combinacion_robusta(cand_rut, monto_banco, col_monto='Monto_Real', tolerancia=0)
                        if combo:
                            match_indices = combo
                            tipo_match = f"🟢 RUT Pago Agrupado (1:{len(combo)})"

            # 3. Si no hay match por RUT, buscar por monto exacto global en toda la cartera
            if not match_indices:
                exacto_monto = ventas_disponibles[ventas_disponibles['Monto_Real'] == monto_banco]
                if not exacto_monto.empty:
                    # 🛠️ MEJORA: Si hay múltiples con el mismo monto (SIN filtro de RUT),
                    # elige el más antiguo para reducir ambigüedad
                    if len(exacto_monto) > 1:
                        idx_seleccionado = _seleccionar_documento_por_duplicidad(
                            exacto_monto,
                            col_fecha='FECHA DE EMISION'
                        )
                        match_indices = [idx_seleccionado]
                        tipo_match = f"🟡 Coincidencia por Monto ({len(exacto_monto)} opciones, Elegido más antiguo)"
                    else:
                        match_indices = [exacto_monto.index[0]]
                        tipo_match = "🟡 Coincidencia por Monto (Verificar Glosa)"

        if match_indices:
            for i in match_indices:
                indices_ventas_usados.add(i)
            rows_matched = df_v.loc[match_indices]
            
            folios = ", ".join([str(r[col_folio]) if col_folio and col_folio in r else f"FILA-{i+1}" for i, r in rows_matched.iterrows()])
            monto_ventas_tot = rows_matched['Monto_Real'].sum()
            dif = monto_banco - monto_ventas_tot

            # Validar si el RUT de la cartola difiere del documento matcheado
            ruts_en_match = set(rows_matched['RUT_Norm'].dropna().unique())
            rut_discrepancia = False
            if rut_c and ruts_en_match and rut_c not in ruts_en_match:
                rut_discrepancia = True

            tiene_duplicidad = False
            mismos_montos = pd.DataFrame()
            if rut_c and 'cand_rut' in locals() and not cand_rut.empty:
                mismos_montos = cand_rut[cand_rut['Monto_Real'] == monto_banco]
                if len(mismos_montos) > 1:
                    tiene_duplicidad = True

            # REGLA ESTRICTA: Diferencia cero para éxito limpio
            if dif == 0 and not rut_discrepancia:
                if tiene_duplicidad:
                    estado = '🟡 Con Observación'
                    observacion_detalle = f'⚠️ Duplicidad resuelta: Se seleccionó el documento más antiguo de {len(mismos_montos)} opciones con este monto'
                else:
                    estado = '🟢 Conciliado Exacto'
                    observacion_detalle = 'Monto y documentos cuadrados sin observaciones'
            else:
                estado = '🟡 Con Observación'
                observaciones_lista = []
                if rut_discrepancia:
                    observaciones_lista.append(f'⚠️ RUT de cartola ({rut_c}) difiere del documento matcheado ({", ".join(ruts_en_match)})')
                if tiene_duplicidad:
                    observaciones_lista.append(f'⚠️ Existen {len(mismos_montos)} documentos duplicados con este monto (se eligió el más antiguo)')
                if dif != 0:
                    observaciones_lista.append(f'⚠️ Diferencia de ${dif:,.0f} respecto a cartera')
                
                observacion_detalle = " | ".join(observaciones_lista) if observaciones_lista else f'⚠️ Diferencia de ${dif:,.0f}'

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
            entidad_identificada = 'NO IDENTIFICADO'
            tipo_match_parcial = 'Sin Coincidencia'
            estado_parcial = '🔴 Abono No Identificado'
            
            if rut_c:
                cand_rut_global = df_v[df_v['RUT_Norm'] == rut_c]
                if not cand_rut_global.empty:
                    entidad_identificada = cand_rut_global.iloc[0][col_cliente] if col_cliente in cand_rut_global.columns else 'N/A'
                    tipo_match_parcial = '🟡 RUT Identificado (Monto No Cuadra)'
                    estado_parcial = '🟡 Con Observación'
                    observacion_detalle = 'El RUT de la glosa existe en cartera, pero el monto no coincide con documentos'
            
            cruce_list.append({
                'Descripción Cartola': texto_desc_raw,
                'Monto Banco ($)': monto_banco,
                'Folio(s) Matcheado(s)': 'N/A',
                'Entidad / Deudor': entidad_identificada,
                'Tipo Coincidencia': tipo_match_parcial,
                'Monto Cartera ($)': 0,
                'Diferencia ($)': monto_banco,
                'Estado Conciliación': estado_parcial,
                'Detalle / Advertencia': observacion_detalle
            })

    df_cruce = pd.DataFrame(cruce_list)
    df_pendientes = df_v[~df_v.index.isin(indices_ventas_usados)].copy()
    
    return df_cruce, df_pendientes
