import pandas as pd
import pdfplumber
import re
import unicodedata

def limpiar_nombre_columna(col):
    """Limpia tildes, espacios y pasa a mayúsculas los nombres de las columnas."""
    col_str = str(col)
    nfkd_form = unicodedata.normalize('NFKD', col_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).strip().upper()

def limpiar_monto_seguro(val):
    """Convierte cualquier formato de monto (con puntos o comas) en un número real válido."""
    if pd.isna(val): 
        return 0.0
    if isinstance(val, (int, float)): 
        return float(val)
    
    s = str(val).strip().replace('$', '').replace(' ', '')
    if not s:
        return 0.0
        
    # Manejo de formatos numéricos chilenos/internacionales
    if '.' in s and ',' in s:
        if s.rfind('.') < s.rfind(','): 
            s = s.replace('.', '').replace(',', '.')
        else: 
            s = s.replace(',', '')
    elif ',' in s: 
        s = s.replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
        
    s = re.sub(r'[^0-9.-]', '', s)
    try: 
        return float(s)
    except: 
        return 0.0

def leer_archivo_subido(archivo):
    """
    Lector universal para Excel, CSV y PDF bancario.
    Estandariza columnas, montos y textos de forma automática.
    """
    if archivo is None:
        return None
        
    nombre = archivo.name.lower()
    
    # -------------------------------------------------------------
    # 1. LECTURA DE ARCHIVOS EXCEL O CSV (Planilla de Ventas / Cartola Excel)
    # -------------------------------------------------------------
    if nombre.endswith(('.xlsx', '.xls', '.csv')):
        if nombre.endswith('.csv'):
            try:
                df = pd.read_csv(archivo, sep=';', encoding='utf-8')
            except:
                df = pd.read_csv(archivo, sep=',', encoding='utf-8')
        else:
            df = pd.read_excel(archivo, sheet_name=0)
            
        # Estandarizar nombres de columnas
        df.columns = [limpiar_nombre_columna(c) for c in df.columns]
        return df
        
    # -------------------------------------------------------------
    # 2. LECTURA DE CARTOLAS BANCARIAS EN PDF
    # -------------------------------------------------------------
    elif nombre.endswith('.pdf'):
        lineas_crudas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        if linea.strip():
                            lineas_crudas.append(linea.strip())
                            
        lineas_utiles = []
        comenzar_captura = False
        
        for linea in lineas_crudas:
            linea_upper = linea.upper()
            if not comenzar_captura:
                if ('/' in linea and len(linea) >= 10 and linea[2] == '/' and linea[5] == '/') and any(kw in linea_upper for kw in ['TRASPASO', 'PAGO', 'DEPOSITO', 'ABONO', 'TRANSFERENCIA', 'COMPRA', 'RETIRO', 'CARGO']):
                    comenzar_captura = True
            
            if comenzar_captura:
                es_basura = any(b in linea_upper for b in ['ATENTAMENTE', 'ESTIMADOS', 'PAGINA', 'SALDO CONTABLE', 'SALDO DISPONIBLE'])
                if not es_basura and len(linea) > 2:
                    lineas_utiles.append(linea)
                    
        transacciones_crudas = []
        for linea in lineas_utiles:
            if len(linea) >= 10 and linea[2] == '/' and linea[5] == '/':
                transacciones_crudas.append(linea)
            else:
                if transacciones_crudas:
                    transacciones_crudas[-1] += " " + linea
                    
        filas_procesadas = []
        for tx in transacciones_crudas:
            fecha = tx[:10]
            resto = tx[10:].strip()
            
            # Extraer monto al final del texto de la cartola
            patron_monto = re.search(r'(-?[\d\.]+[\d]+)$', resto)
            if patron_monto:
                monto_str = patron_monto.group(1)
                descripcion = resto[: -len(monto_str)].strip()
                monto_limpio = limpiar_monto_seguro(monto_str)
                filas_procesadas.append([fecha, descripcion, monto_limpio])
            else:
                filas_procesadas.append([fecha, resto, 0.0])
                
        if filas_procesadas:
            df = pd.DataFrame(filas_procesadas, columns=["FECHA", "DESCRIPCION", "MONTO"])
            return df
        else:
            raise ValueError("No se pudieron estructurar las transacciones del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
