import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """Lector universal y directo para Excel, CSV y PDFs bancarios (sin recortar filas)."""
    nombre = archivo.name.lower()
    
    if nombre.endswith(('.xlsx', '.xls')):
        return pd.read_excel(archivo, sheet_name=0)
    
    elif nombre.endswith('.csv'):
        try:
            return pd.read_csv(archivo, sep=';', encoding='utf-8')
        except:
            return pd.read_csv(archivo, sep=',', encoding='utf-8')
            
    elif nombre.endswith('.pdf'):
        filas_pdf = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                # Extraemos tablas si las hay
                tabla = pagina.extract_table()
                if tabla:
                    filas_pdf.extend(tabla)
                else:
                    # Si no hay tabla estructurada, extraemos cada línea de texto visible
                    texto = pagina.extract_text()
                    if texto:
                        for linea in texto.split('\n'):
                            filas_pdf.append([linea])
                            
        if filas_pdf:
            # Convertimos directamente en DataFrame usando la primera línea como columnas
            df = pd.DataFrame(filas_pdf[1:], columns=filas_pdf[0])
            # Limpiamos filas vacías
            df = df.dropna(how='all').reset_index(drop=True)
            return df
        else:
            raise ValueError("No se pudo extraer texto del PDF.")
            
    else:
        raise ValueError("Formato de archivo no soportado.")
