import pandas as pd
import pdfplumber
import re

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario.
    Elimina toda la basura inicial, detecta la línea de encabezados y divide los campos en columnas.
    """
    if archivo is None:
        return None
        
    nombre = archivo.name.lower()
    
    if nombre.endswith(('.xlsx', '.xls')):
        return pd.read_excel(archivo, sheet_name=0)
        
    elif nombre.endswith('.csv'):
        try:
            return pd.read_csv(archivo, sep=';', encoding='utf-8')
        except:
            return pd.read_csv(archivo, sep=',', encoding='utf-8')
            
    elif nombre.endswith('.pdf'):
        lineas_crudas = []
        
        # 1. Extraer todo el texto de todas las páginas del PDF
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        linea_limpia = linea.strip()
                        if linea_limpia:
                            lineas_crudas.append(linea_limpia)
                            
        # 2. Encontrar dónde comienzan realmente los datos (buscando la línea de encabezados o la primera fecha con transacción)
        idx_inicio = 0
        for i, linea in enumerate(lineas_crudas):
            linea_upper = linea.upper()
            # Identificamos la fila donde aparecen los títulos de la tabla o el primer movimiento con fecha y monto
            if ('FECHA' in linea_upper and 'ABONO' in linea_upper) or ('/' in linea and ('TRASPASO' in linea_upper or 'PAGO' in linea_upper or 'DEPOSITO' in linea_upper)):
                # Si pilló la línea de encabezados exactos, empezamos justo después; si pilló el primer movimiento, empezamos ahí
                idx_inicio = i if '/' in linea else i + 1
                break
                
        # Cortamos la lista para descartar absolutamente toda la basura de arriba
        lineas_utiles = lineas_crudas[idx_inicio:]
        
        # 3. Estructurar las líneas en columnas limpias
        filas_procesadas = []
        for linea in lineas_utiles:
            # Omitir pies de página o líneas de cierre no transaccionales
            if any(palabra in linea.upper() for palabra in ['ATENTAMENTE', 'ESTIMADOS', 'PAGINA', 'CORREO']):
                continue
                
            # Intentamos separar la fecha (primeros 10 caracteres si tienen formato DD/MM/YYYY)
            if len(linea) > 10 and linea[2] == '/' and linea[5] == '/':
                fecha = linea[:10]
                resto = linea[10:].strip()
                filas_procesadas.append([fecha, resto])
            else:
                # Si es una línea de continuación o texto suelto
                if filas_procesadas:
                    filas_procesadas[-1][1] += " " + linea
                    
        if filas_procesadas:
            df = pd.DataFrame(filas_procesadas, columns=["FECHA", "DESCRIPCION_Y_MONTO"])
            return df
        else:
            raise ValueError("No se pudieron estructurar las transacciones del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
