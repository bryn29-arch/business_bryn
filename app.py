import re
import pandas as pd

def extraer_rut_o_nombre(texto):
    """
    Detecta RUTs (estándar, sin guión o dentro de 'Pago Proveedores')
    o Nombres/Razones Sociales en glosas bancarias.
    """
    if not isinstance(texto, str) or not texto.strip():
        return "NO_DETECTADO"

    # 1. Pago Proveedores con RUT de 9 o 10 dígitos pegado (ej: 0966910607 -> 96.691.060-7 o 093546000k -> 93.546.000-K)
    match_prov = re.search(r'Pago:\s*Proveedores\s+0?(\d{7,8})([\dkK])\b', texto, re.IGNORECASE)
    if match_prov:
        body, dv = match_prov.group(1), match_prov.group(2).upper()
        return f"{int(body)}-{dv}"

    # 2. RUT Estándar con puntos/guión o sin ellos (12.345.678-9 o 12345678-9)
    match_std = re.search(r'\b(\d{1,2}(?:\.?\d{3}){2}-?[\dkK])\b', texto)
    if match_std:
        rut_raw = match_std.group(0).replace('.', '').upper()
        if '-' not in rut_raw:
            rut_raw = rut_raw[:-1] + '-' + rut_raw[-1]
        return rut_raw

    # 3. RUT Continuo aislado de 8 o 9 dígitos
    match_continuo = re.search(r'\b0?(\d{7,8}[\dkK])\b', texto)
    if match_continuo:
        raw = match_continuo.group(1).upper()
        return f"{int(raw[:-1])}-{raw[-1]}"

    # 4. Extracción de Nombre o Empresa en Traspasos o Pagos
    match_nombre = re.search(r'(?:Traspaso De:|Pago:|Transferencia de:)\s*([A-Za-z0-9\s]+)', texto, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip()
        # Limpiar palabras clave residuales de la glosa bancaria
        nombre = re.sub(r'\s+(Internet|Cta|Cuenta|Transferencia|Oficina|Central).*$', '', nombre, flags=re.IGNORECASE)
        return nombre[:35].strip()
        
    return "NO_DETECTADO"


def extraer_monto_chileno_estricto(texto_o_celda):
    """
    Extrae montos numéricos soportando comas o puntos como separadores de miles
    (ej: 3,694,950 o 3.694.950).
    """
    if pd.isna(texto_o_celda) or str(texto_o_celda).strip() in ['', 'None', 'nan', '0']:
        return None

    # Si ya viene como un número directo
    if isinstance(texto_o_celda, (int, float)):
        val = int(round(float(texto_o_celda)))
        return val if val > 0 else None

    texto = str(texto_o_celda).strip()

    # Limpiamos bloques que corresponden a RUTs o identificadores numéricos de proveedores
    texto_limpio = re.sub(r'\b\d{7,8}-[\dkK]\b', '', texto)
    texto_limpio = re.sub(r'Pago:\s*Proveedores\s+\d+[\dkK]?', '', texto_limpio, flags=re.IGNORECASE)

    # 1. Buscar montos con comas o puntos como separadores de miles (ej: 3,694,950 o 3.694.950)
    coincidencias = re.findall(r'\b\d{1,3}(?:[.,]\d{3})+\b', texto_limpio)
    if coincidencias:
        # Extraemos la última coincidencia (habitualmente el monto total al final de la glosa)
        monto_str = coincidencias[-1].replace('.', '').replace(',', '')
        try:
            val = int(monto_str)
            if 0 < val < 500000000:
                return val
        except ValueError:
            pass

    # 2. Búsqueda con signo de pesos explicitado
    match_pesos = re.search(r'\$\s*([\d\.,]+)', texto_limpio)
    if match_pesos:
        monto_str = match_pesos.group(1).replace('.', '').replace(',', '')
        try:
            val = int(monto_str)
            if 0 < val < 500000000:
                return val
        except ValueError:
            pass

    # 3. Entero simple al final de la cadena
    match_entero = re.search(r'\b(\d{5,9})\b', texto_limpio)
    if match_entero:
        try:
            val = int(match_entero.group(1))
            if 1000 < val < 500000000:
                return val
        except ValueError:
            pass

    return None


def procesar_fila_cartola(row):
    """
    Función de evaluación para clasificar cada fila en VÁLIDA (OK) o INCOMPLETA.
    """
    glosa = str(row.get('Glosa Capturada', ''))
    
    # 1. Extraer Fecha (Formatos DD/MM/YYYY)
    match_fecha = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', glosa)
    fecha_valida = match_fecha.group(1) if match_fecha else row.get('Fecha', None)

    # 2. Extraer Identificador (RUT o Nombre)
    identificador = extraer_rut_o_nombre(glosa)

    # 3. Extraer Monto
    monto = extraer_monto_chileno_estricto(glosa)

    # Motivos de error / revisión
    motivos = []
    if not fecha_valida or pd.isna(fecha_valida):
        motivos.append("Fecha no detectada")
    if identificador == "NO_DETECTADO":
        motivos.append("RUT/Nombre no identificado")
    if monto is None:
        motivos.append("Monto no detectado")

    # Si cumple todos los criterios pasa como OK
    es_valida = len(motivos) == 0

    return pd.Series({
        'Es Valida': es_valida,
        'Fecha Procesada': fecha_valida,
        'Identificador': identificador,
        'Monto Procesado': monto if monto else 0,
        'Motivo Revision': " / ".join(motivos) if motivos else "OK"
    })
