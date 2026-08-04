import pandas as pd
from utils.limpieza import limpiar_texto_general

def limpiar_y_encontrar_encabezados(df):
    """
    Analiza el DataFrame subido, busca la fila real de encabezados 
    (saltando los títulos iniciales o logos del banco/factoring) y estandariza las columnas.
    """
    if df is None or df.empty:
        return df

    # Buscamos en las primeras 15 filas cuál contiene palabras clave típicas de cartolas o carteras
    fila_encabezado = 0
    palabras_clave = ['FECHA', 'GLOSA', 'DESCRIPCION', 'MONTO', 'CARGO', 'ABONO', 'RUT', 'FOLIO', 'DOCUMENTO', 'SALDO']

    for i in range(min(15, len(df))):
        fila_texto = " ".join([str(val).upper() for val in df.iloc[i].values])
        coincidencias = sum(1 for kw in palabras_clave if kw in fila_texto)
        if coincidencias >= 2:  # Si encuentra al menos 2 palabras clave, es la fila correcta
            fila_encabezado = i
            break

    # Si encontramos una fila de encabezado más abajo, reestructuramos el DataFrame
    if fila_encabezado > 0:
        df.columns = df.iloc[fila_encabezado]
        df = df.iloc[fila_encabezado + 1:].reset_index(drop=True)

    # Limpiar nombres de columnas (quitar espacios extra, mayúsculas, etc.)
    df.columns = [limpiar_texto_general(str(col)) for col in df.columns]

    # Eliminar filas que estén completamente vacías
    df = df.dropna(how='all').reset_index(drop=True)

    return df
