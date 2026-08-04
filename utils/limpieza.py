import unicodedata
import re
import pandas as pd

ABREVIATURAS = {
    'CORP': 'CORPORACION', 'EDUC': 'EDUCACION', 'LIMITADA': 'LTDA',
    'SOCIEDAD': 'SOC', 'ANONIMA': 'SA', 'HERMANOS': 'HROS',
    'EIRL': '', 'SPA': '', 'S': 'SPA', 'EXP': 'EXPORTACION', 
    'ING': 'INGENIERIA', 'SERV': 'SERVICIOS'
}

def extraer_rut(texto):
    if not isinstance(texto, str) or pd.isna(texto): 
        return ""
    match = re.search(r'\b(0*\d{1,3}\.?\d{3}\.?\d{3}-?[\dkK])\b', str(texto))
    if match:
        return re.sub(r'[^0-9K]', '', match.group(1).upper()).lstrip('0')
    return ""

def limpiar_texto_general(texto):
    """Limpia tildes, caracteres raros, pasa a mayúsculas y elimina espacios extras."""
    if not isinstance(texto, str) or pd.isna(texto): 
        return ""
    texto = unicodedata.normalize('NFD', str(texto)).encode('ascii', 'ignore').decode("utf-8").upper()
    texto = re.sub(r'[^A-Z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()

def expandir_y_limpiar_texto(texto):
    if not isinstance(texto, str) or pd.isna(texto): 
        return ""
    texto_limpio = limpiar_texto_general(texto)
    palabras = [ABREVIATURAS.get(p, p) for p in texto_limpio.split()]
    return " ".join(palabras).strip()

def limpiar_monto_entero(val):
    if pd.isna(val): 
        return 0
    if isinstance(val, (int, float)): 
        return int(round(abs(val)))
    
    val_str = str(val).strip().replace('$', '').replace(' ', '')
    if ',' in val_str and '.' in val_str:
        if val_str.rfind('.') < val_str.rfind(','): 
            val_str = val_str.replace('.', '').replace(',', '.')
        else: 
            val_str = val_str.replace(',', '')
    elif ',' in val_str: 
        val_str = val_str.replace(',', '.')
        
    val_str = re.sub(r'[^0-9.-]', '', val_str)
    try: 
        return int(round(abs(float(val_str))))
    except: 
        return 0
