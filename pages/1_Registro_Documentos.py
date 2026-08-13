import io
import re
import fitz
import pdfplumber
import pandas as pd
import streamlit as st

# ... (configuraciones previas de tu app)


def extraer_datos_pdf(archivo_pdf):
  lineas_texto = []
  texto_completo = ''

  try:
    bytes_data = archivo_pdf.read()
    archivo_pdf.seek(0)

    with pdfplumber.open(io.BytesIO(bytes_data)) as pdf:
      for pagina in pdf.pages:
        t = pagina.extract_text()
        if t:
          texto_completo += t + '\n'
          for linea in t.split('\n'):
            lineas_texto.append(linea.strip())
  except Exception as e:
    print(f'Error leyendo PDF: {e}')

  # 🛠️ TRUCO MAESTRO: Limpiamos el espacio clásico entre el guion y el dígito verificador (- 3 -> -3)
  texto_completo = re.sub(r'-\s+([0-9kK])', r'-\1', texto_completo)

  # 1. Extracción de RUTs (Ahora tolerante a espacios y con la regla de oro: 1° Emisor, 2° Deudor)
  # El patrón \s* acepta espacios por si acaso quedó alguno suelto
  todos_ruts = re.findall(
      r'\b(\d{1,2}\.\d{3}\.\d{3}-\s*[0-9kK]|\d{7,8}-\s*[0-9kK])\b',
      texto_completo,
  )

  # Limpiamos posibles espacios internos en los RUTs rescatados
  ruts_unicos = []
  for r in todos_ruts:
    r_limpio = r.replace(' ', '')
    if r_limpio not in ruts_unicos:
      ruts_unicos.append(r_limpio)

  rut_emisor = ruts_unicos[0] if len(ruts_unicos) > 0 else 'No Detectado'
  rut_deudor = ruts_unicos[1] if len(ruts_unicos) > 1 else 'No Detectado'

  # 2. Nombre Emisor
  nombre_emisor = 'No Detectado'
  for linea in lineas_texto[:8]:
    linea_up = linea.upper()
    if any(
        k in linea_up
        for k in ['SPA', 'LTDA', 'S.A.', 'E.I.R.L.', 'SOCIEDAD', 'PATAGONIA']
    ):
      if 'GIRO:' not in linea_up and 'HUERTO' not in linea_up:
        nombre_emisor = linea
        break
  if nombre_emisor == 'No Detectado' and len(lineas_texto) > 1:
    for l in lineas_texto[1:5]:
      if len(l) > 3 and 'GIRO' not in l.upper():
        nombre_emisor = l
        break

  # 3. Número de Documento (Folio)
  num_doc = 'S/F'
  match_folio = re.search(
      r'(?:N[º°]|Nº|N°)\s*(\d+)', texto_completo, re.IGNORECASE
  )
  if match_folio:
    num_doc = match_folio.group(1)
  else:
    match_alt = re.search(
        r'FACTURA\s+(?:ELECTRONICA)?.*?(\d{1,6})',
        texto_completo,
        re.DOTALL | re.IGNORECASE,
    )
    if match_alt:
      num_doc = match_alt.group(1)

  # 4. Nombre Deudor (Bloque Señor(es))
  nombre_deudor = 'No Detectado'
  capturando = False
  deudor_lineas = []
  for linea in lineas_texto:
    linea_up = linea.upper()
    if 'SEÑOR' in linea_up or 'SENOR' in linea_up:
      capturando = True
      partes = re.split(
          r'SEÑOR\(ES\):?|SENOR\(ES\):?|SEÑOR\(ES\)', linea, flags=re.IGNORECASE
      )
      if len(partes) > 1 and partes[1].strip():
        deudor_lineas.append(partes[1].strip())
      continue
    if capturando:
      if 'R.U.T.' in linea_up or 'RUT' in linea_up or 'GIRO:' in linea_up:
        break
      if linea:
        deudor_lineas.append(linea)

  if deudor_lineas:
    texto_sucio = ' '.join(deudor_lineas)
    texto_limpio = re.sub(
        r'\b\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚñÑ]+\s+(?:de|del)\s+\d{2,4}\b',
        '',
        texto_sucio,
        flags=re.IGNORECASE,
    )
    texto_limpio = re.sub(
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', texto_limpio
    )
    nombre_deudor = (
        re.sub(r'\s+', ' ', texto_limpio).strip().strip('-/_').strip()
    )

  # 5. Fecha de Emisión
  fecha_emision = 'No Detectada'
  match_fecha = re.search(
      r'Fecha\s*Emision[:\s]*([^\n]+)', texto_completo, re.IGNORECASE
  )
  if match_fecha:
    fecha_emision = match_fecha.group(1).strip()
  else:
    match_f_alt = re.search(r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b', texto_completo)
    if match_f_alt:
      fecha_emision = match_f_alt.group(1)

  # 6. Montos Financieros (Neto, IVA, Total)
  monto_neto = '0'
  iva_19 = '0'
  total = '0'

  match_neto = re.search(
      r'MONTO\s*NETO\s*\$?\s*([\d\.]+)', texto_completo, re.IGNORECASE
  )
  if match_neto:
    monto_neto = match_neto.group(1)

  match_iva = re.search(
      r'I\.V\.A\.\s*19%\s*\$?\s*([\d\.]+)', texto_completo, re.IGNORECASE
  )
  if match_iva:
    iva_19 = match_iva.group(1)

  match_total = re.search(
      r'TOTAL\s*\$?\s*([\d\.]+)', texto_completo, re.IGNORECASE
  )
  if match_total:
    total = match_total.group(1)

  return {
      'NOMBRE EMISOR': nombre_emisor,
      'RUT EMISOR': rut_emisor,
      'NUMERO DE DOCUMENTO': num_doc,
      'NOMBRE DEUDOR': nombre_deudor,
      'RUT DEUDOR': rut_deudor,
      'FECHA DE EMISION': fecha_emision,
      'MONTO NETO': monto_neto,
      'I.V.A 19%': iva_19,
      'TOTAL': total,
  }
