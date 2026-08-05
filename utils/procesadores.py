import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """Lector ultra seguro para evitar bucles y errores de lectura."""
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
        # Extracción segura línea por línea para evitar bloqueos
        lineas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        lineas.append([linea])
                        
        if lineas:
            return pd.DataFrame(lineas, columns=["Texto_Cartola"])
        else:
            raise ValueError("El PDF está vacío o no contiene texto legible.")
            
    else:
        raise ValueError("Formato no soportado.")
