import pandas as pd
import re

def validar_rut_chileno(rut_str):
    """
    Valida matemáticamente el RUT chileno mediante el algoritmo Módulo 11 
    y estandariza el formato quitando puntos, guiones y ceros a la izquierda.
    """
    if not isinstance(rut_str, str) or pd.isna(rut_str):
        return "", False

    rut_limpio = re.sub(r'[^0-9K]', '', str(rut_str).upper())
    if len(rut_limpio) < 2:
        return "", False

    cuerpo = rut_limpio[:-1].lstrip('0')
    dv = rut_limpio[-1]

    try:
        suma = 0
        multiplo = 2
        for char in reversed(cuerpo):
            suma += int(char) * multiplo
            multiplo += 1
            if multiplo > 7:
                multiplo = 2

        esperado = 11 - (suma % 11)
        if esperado == 11:
            dv_calculado = '0'
        elif esperado == 10:
            dv_calculado = 'K'
        else:
            dv_calculado = str(esperado)

        es_valido = (dv == dv_calculado)
        return f"{cuerpo}-{dv}", es_valido
    except:
        return rut_limpio, False

def detectar_duplicados_cartera(df_ventas):
    """
    Analiza la cartera y detecta duplicados reales basándose estrictamente en RUT y Folio/Documento.
    """
    if df_ventas is None or df_ventas.empty:
        return df_ventas, []

    cols = df_ventas.columns
    col_rut = next((c for c in cols if 'RUT' in str(c).upper()), None)
    col_folio = next((c for c in cols if 'FOLIO' in str(c).upper() or 'DOCUMENTO' in str(c).upper()), None)

    alertas = []
    if col_rut and col_folio:
        duplicados = df_ventas[df_ventas.duplicated(subset=[col_rut, col_folio], keep=False)]
        if not duplicados.empty:
            cant_dups = len(duplicados)
            alertas.append(f"⚠️ Se detectaron {cant_dups} registros con idéntico RUT y Folio (Documento duplicado real).")

    return df_ventas, alertas
