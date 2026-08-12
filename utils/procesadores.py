import pandas as pd
import pdfplumber
import re

def leer_archivo_subido(archivo):
    """
    Lector universal adaptado para cartolas bancarias de Chile (cualquier banco).
    Identifica de manera flexible nombres de columnas como Fecha, Descripción, Monto, 
    Cargos, Abonos, Débito o Crédito para estandarizarlas de cara al match con Excel.
    """
    if archivo is None:
        return None
        
    nombre = archivo.name.lower()
    
    # -------------------------------------------------------------
    # 1. PROCESAMIENTO DE ARCHIVOS EXCEL (.xlsx, .xls) O CSV
    # -------------------------------------------------------------
    if nombre.endswith(('.xlsx', '.xls', '.csv')):
        if nombre.endswith('.csv'):
            try:
                df = pd.read_csv(archivo, sep=';', encoding='utf-8')
            except:
                df = pd.read_csv(archivo, sep=',', encoding='utf-8')
        else:
            df = pd.read_excel(archivo, sheet_name=0)
            
        # Normalizar nombres de columnas del Excel/CSV subido para buscar equivalencias chilenas
        columnas_originales = df.columns
        mapa_columnas = {}
        
        for col in columnas_originales:
            col_clean = str(col).strip().upper()
            # Mapear Fecha
            if any(k in col_clean for k in ['FECHA', 'F. MOV', 'F_MOV', 'DATE']):
                mapa_columnas[col] = 'FECHA'
            # Mapear Descripción o Detalle
            elif any(k in col_clean for k in ['DESC', 'DETALLE', 'GLOSA', 'MOVIMIENTO', 'DESCRIPCION', 'CONCEPTO']):
                mapa_columnas[col] = 'DESCRIPCION'
            # Mapear Monto / Importe
            elif any(k in col_clean for k in ['MONTO', 'IMPORTE', 'VALOR', 'SALDO']):
                if 'CARGO' not in col_clean and 'ABONO' not in col_clean:
                    mapa_columnas[col] = 'MONTO'
            # Mapear Cargos / Débitos / Retiros
            elif any(k in col_clean for k in ['CARGO', 'DEBITO', 'RETIRO', 'EGRESO']):
                mapa_columnas[col] = 'CARGOS'
            # Mapear Abonos / Créditos / Depósitos
            elif any(k in col_clean for k in ['ABONO', 'CREDITO', 'DEPOSITO', 'INGRESO']):
                mapa_columnas[col] = 'ABONOS'
                
        df = df.rename(columns=mapa_columnas)
        return df
        
    # -------------------------------------------------------------
    # 2. PROCESAMIENTO DE CARTOLAS BANCARIAS EN PDF (Multibanco Chileno)
    # -------------------------------------------------------------
    elif nombre.endswith('.pdf'):
        lineas_crudas = []
        
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    for linea in texto.split('\n'):
                        linea_limpia = linea.strip()
                        if linea_limpia:
                            lineas_crudas.append(linea_limpia)
                            
        lineas_utiles = []
        comenzar_captura = False
        
        for linea in lineas_crudas:
            linea_upper = linea.upper()
            
            if not comenzar_captura:
                # Detección amplia de inicio de transacciones para diferentes bancos en Chile
                if ('/' in linea and len(linea) >= 10 and linea[2] == '/' and linea[5] == '/') and any(kw in linea_upper for kw in ['TRASPASO', 'PAGO', 'DEPOSITO', 'ABONO', 'TRANSFERENCIA', 'COMPRA', 'RETIRO', 'CARGO', 'COMISION', 'REDCOMPRA', 'CAJERO']):
                    comenzar_captura = True
            
            if comenzar_captura:
                es_pie_o_basura = any(basura in linea_upper for basura in [
                    'ATENTAMENTE', 'ESTIMADOS', 'CORREO:', 'ASUNTO:', 'CC:', 'PARA:', 
                    'DOCUMENTO ELECTRONICO', 'CASA MATRIZ', 'ATENCION CLIENTES', 'SALDO CONTABLE', 'SALDO DISPONIBLE'
                ])
                
                if linea_upper.startswith('PAGINA') or (linea.isdigit() and len(linea) <= 2):
                    continue
                    
                if not es_pie_o_basura and len(linea) > 2:
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
            
            # Patrón flexible para montos en pesos chilenos (admite puntos de miles y signo negativo/positivo)
            patron_monto = re.search(r'(-?[\d\.]+[\d]+)$', resto)
            
            if patron_monto:
                monto_str = patron_monto.group(1)
                descripcion = resto[: -len(monto_str)].strip()
                filas_procesadas.append([fecha, descripcion, monto_str])
            else:
                filas_procesadas.append([fecha, resto, ""])
                
        if filas_procesadas:
            df = pd.DataFrame(filas_procesadas, columns=["FECHA", "DESCRIPCION", "MONTO"])
            return df
        else:
            raise ValueError("No se pudieron estructurar las columnas de transacciones del PDF.")
            
    else:
        raise ValueError("Formato no soportado.")
