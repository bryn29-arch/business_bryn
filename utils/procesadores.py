import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """Lee archivos Excel, CSV o PDF de manera universal, asegurando extraer todas las filas."""
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
            for num_pag, pagina in enumerate(pdf.pages):
                # Intentamos extraer tabla estructurada por página
                tabla = pagina.extract_table()
                if tabla:
                    filas_pdf.extend(tabla)
                else:
                    # Si la página no tiene formato de tabla estricta, extraemos texto línea por línea
                    texto = pagina.extract_text()
                    if texto:
                        for linea in texto.split('\n'):
                            # Filtramos líneas basura típicas de encabezados de correo o pies de página
                            linea_upper = linea.upper()
                            if not any(excl in linea_upper for `in` ['PAGINA', 'DE:', 'ENVIADO EL:', 'ESTIMADOS']):
                                filas_pdf.append([linea])
                                
        if filas_pdf:
            # Buscamos la fila que contenga los títulos reales en todo el PDF extraído
            idx_encabezado = 0
            for idx, row in enumerate(filas_pdf[:15]):
                row_str = " ".join([str(v).upper() for v in row if v])
                if 'FECHA' in row_str and ('ABONO' in row_str or 'DESCRIPCION' in row_str or 'GLOSA' in row_str):
                    idx_encabezado = idx
                    break
            
            headers = filas_pdf[idx_encabezado] if idx_encabezado < len(filas_pdf) else [f"Col_{i}" for i in range(len(filas_pdf[0]))]
            data = filas_pdf[idx_encabezado + 1:]
            
            # Limpiamos filas que tengan celdas vacías o sean nulas
            data_limpia = [row for row in data if any(val not in [None, ""] for val in row)]
            
            return pd.DataFrame(data_limpia, columns=headers[:len(data_limpia[0])] if data_limpia else None)
        else:
            raise ValueError("No se pudo extraer contenido legible del PDF.")
            
    else:
        raise ValueError("Formato de archivo no compatible.")
