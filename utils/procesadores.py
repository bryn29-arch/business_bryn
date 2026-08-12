import pandas as pd
import pdfplumber

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario.
    Elimina la cabecera, detecta los encabezados, separa columnas y corta los pies de página de la cartola.
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
                            
        # 2. Encontrar dónde comienzan realmente los datos
        idx_inicio = 0
        for i, linea in enumerate(lineas_crudas):
            linea_upper = linea.upper()
            if ('FECHA' in linea_upper and 'ABONO' in linea_upper) or ('/' in linea and ('TRASPASO' in linea_upper or 'PAGO' in linea_upper or 'DEPOSITO' in linea_upper)):
                idx_inicio = i if '/' in linea else i + 1
                break
                
        lineas_utiles = lineas_crudas[idx_inicio:]
        
        # 3. Estructurar las líneas en columnas limpias filtrando basura inicial y pies de página finales
        filas_procesadas = []
        for linea in lineas_utiles:
            linea_upper = linea.upper()
            
            # Palabras clave comunes que indican pie de página, legales o cierre de hoja bancaria
            palabras_pie = [
                'ATENTAMENTE', 'ESTIMADOS', 'PAGINA', 'CORREO', 
                'BANCO', 'CASA MATRIZ', 'ATENCION', 'TELEFONO', 
                'DOCUMENTO ELECTRONICO', 'FIRMA', 'DIRECCION'
            ]
            
            # Si detectamos una línea típica de pie de página al final, dejamos de agregar filas
            if any(palabra in linea_upper for palabra in palabras_pie) and len(linea) > 25:
                # Si ya llevamos bastantes transacciones, es muy probable que estemos en el pie de página final
                if len(filas_procesadas) > 2:
                    break
                continue
                
            # Omitir líneas aisladas muy cortas o irrelevantes
            if any(basura in linea_upper for basura in ['ATENTAMENTE', 'ESTIMADOS', 'PAGINA']):
                continue
                
            # Intentar separar la fecha (formato DD/MM/YYYY)
            if len(linea) > 10 and linea[2] == '/' and linea[5] == '/':
                fecha = linea[:10]
                resto = linea[10:].strip()
                filas_procesadas.append([fecha, resto])
            else:
                # Si es una línea de continuación de la descripción anterior
                if filas_procesadas:
                    # Nos aseguramos de no anexar texto que parezca pie de página institucional
                    if not any(p in linea_upper for p in ['LTDA', 'S.A.', 'SPA', 'BANCO']):
                        filas_procesadas[-1][1] += " " + linea
                    
        if filas_procesadas:
            df = pd.DataFrame(filas_procesadas, columns=["FECHA", "DESCRIPCION_Y_MONTO"])
            return df
        else:
            raise ValueError("No se pudieron estructurar las transacciones del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
