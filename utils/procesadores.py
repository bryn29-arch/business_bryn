import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario multihola.
    Procesa todas las páginas de forma continua, descarta encabezados repetidos y pies de página,
    y estructura las transacciones en columnas limpias.
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
        
        # 1. Extraer texto de TODAS las páginas del PDF de manera secuencial
        with pdfplumber.open(archivo) as pdf:
            for num_pag, pagina in enumerate(pdf.pages):
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        linea_limpia = linea.strip()
                        if linea_limpia:
                            lineas_crudas.append(linea_limpia)
                            
        # 2. Filtrar líneas basura globales (cabeceras de correo iniciales) pero conservar todo el contenido transaccional
        lineas_utiles = []
        comenzar_captura = False
        
        for linea in lineas_crudas:
            linea_upper = linea.upper()
            
            # Detectar el inicio real de la primera transacción (ej: fecha DD/MM/YYYY)
            if not comenzar_captura:
                if ('/' in linea and len(linea) >= 10 and linea[2] == '/' and linea[5] == '/') and any(kw in linea_upper for kw in ['TRASPASO', 'PAGO', 'DEPOSITO', 'ABONO', 'TRANSFERENCIA']):
                    comenzar_captura = True
            
            if comenzar_captura:
                # Palabras exactas o frases típicas de pies de página o metadatos repetidos que SÍ debemos ignorar
                es_pie_o_basura = any(basura in linea_upper for basura in [
                    'ATENTAMENTE', 'ESTIMADOS', 'CORREO:', 'ASUNTO:', 'CC:', 'PARA:', 
                    'DOCUMENTO ELECTRONICO', 'CASA MATRIZ', 'ATENCION CLIENTES'
                ])
                
                # Omitir líneas de numeración de página aisladas (ej: "Página 1 de 2" o solo números sueltos de pie de página)
                if linea_upper.startswith('PAGINA') or (linea.isdigit() and len(linea) <= 2):
                    continue
                    
                if not es_pie_o_basura and len(linea) > 2:
                    lineas_utiles.append(linea)
                    
        # 3. Estructurar las líneas útiles en columnas limpias (Fecha y Detalle/Monto)
        filas_procesadas = []
        for linea in lineas_utiles:
            # Si la línea empieza con formato de fecha DD/MM/YYYY
            if len(linea) >= 10 and linea[2] == '/' and linea[5] == '/':
                fecha = linea[:10]
                resto = linea[10:].strip()
                filas_procesadas.append([fecha, resto])
            else:
                # Si es una línea de continuación de la descripción de la transacción anterior
                if filas_procesadas:
                    filas_procesadas[-1][1] += " " + linea
                    
        if filas_procesadas:
            df = pd.DataFrame(filas_procesadas, columns=["FECHA", "DESCRIPCION_Y_MONTO"])
            return df
        else:
            raise ValueError("No se pudieron extraer transacciones válidas del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
