import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario. 
    Filtra automáticamente textos sueltos, firmas, saludos y líneas irrelevantes de los PDFs.
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
        # Palabras clave que indican que una línea es basura/relleno y NO una transacción
        palabras_basura = [
            'ATENTAMENTE', 'ESTIMADOS', 'PAGINA', 'CORREO', 'SUCURSAL', 
            'BANCO', 'CARTOLA', 'SALDO INICIAL', 'SALDO FINAL', 'TOTAL', '--'
        ]
        
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        linea_limpia = linea.strip()
                        linea_upper = linea_limpia.upper()
                        
                        # Omitir líneas vacías, muy cortas o que contengan palabras basura
                        es_basura = any(basura in linea_upper for basura in palabras_basura)
                        if linea_limpia and len(linea_limpia) > 3 and not es_basura:
                            lineas_validas.append([linea_limpia])
                            
        if lineas_validas:
            return pd.DataFrame(lineas_validas, columns=["DETALLE_TRANSACCION"])
        else:
            raise ValueError("No se encontraron transacciones válidas en el PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
