import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario.
    Omite la cabecera de correos y captura la totalidad de las filas de transacciones.
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
        lineas_validas = []
        comenzar_captura = False
        
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        linea_limpia = linea.strip()
                        linea_upper = linea_limpia.upper()
                        
                        # Detectamos el inicio de las transacciones buscando fechas o palabras clave de movimiento
                        if not comenzar_captura:
                            if ('/' in linea_limpia) and any(kw in linea_upper for kw in ['TRASPASO', 'PAGO', 'DEPOSITO', 'ABONO']):
                                comenzar_captura = True
                        
                        # Si ya comenzó la captura, filtramos solo líneas de cierre irrelevantes pero conservamos el resto
                        if comenzar_captura:
                            palabras_basura = ['ATENTAMENTE', 'ESTIMADOS', 'PAGINA', 'CORREO']
                            es_basura = any(basura in linea_upper for basura in palabras_basura)
                            
                            if linea_limpia and len(linea_limpia) > 3 and not es_basura:
                                lineas_validas.append([linea_limpia])
                                
        if lineas_validas:
            return pd.DataFrame(lineas_validas, columns=["DETALLE_TRANSACCION"])
        else:
            raise ValueError("No se pudieron extraer las transacciones completas del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
