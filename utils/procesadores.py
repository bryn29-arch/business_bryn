import pandas as pd
import io

def leer_archivo_subido(archivo_subido):
    """Lee archivos Excel, CSV o PDF y los transforma de manera uniforme en una tabla de Pandas."""
    if archivo_subido is None:
        return None
        
    nombre_archivo = archivo_subido.name.lower()
    
    try:
        if nombre_archivo.endswith('.csv'):
            # Intenta leer CSV con separadores comunes (coma o punto y coma)
            try:
                return pd.read_csv(archivo_subido, encoding='utf-8')
            except:
                archivo_subido.seek(0)
                return pd.read_csv(archivo_subido, encoding='latin1', sep=';')
                
        elif nombre_archivo.endswith(('.xls', '.xlsx')):
            return pd.read_excel(archivo_subido)
            
        elif nombre_archivo.endswith('.pdf'):
            # Bloque especial para procesar PDFs (cartolas bancarias)
            # Nota: Usaremos pdfplumber más adelante de manera segura
            import pdfplumber
            
            datos_filas = []
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    tabla = pagina.extract_table()
                    if tabla:
                        datos_filas.extend(tabla)
                    else:
                        # Si no hay tabla estructurada, extraemos líneas de texto sueltas
                        texto = pagina.extract_text()
                        if texto:
                            for linea in texto.split('\n'):
                                datos_filas.append([linea])
                                
            if datos_filas:
                # Convertimos las líneas extraídas del PDF en una tabla básica
                df = pd.DataFrame(datos_filas)
                if len(df.columns) > 1:
                    df.columns = [f"Col_{i}" for i in range(len(df.columns))]
                else:
                    df.columns = ["Texto_PDF"]
                return df
            else:
                raise ValueError("No se pudo extraer texto legible del PDF.")
                
        else:
            raise ValueError("Formato de archivo no soportado.")
            
    except Exception as e:
        raise Exception(f"Error al leer el archivo {archivo_subido.name}: {str(e)}")
