import io
import re
import fitz  # PyMuPDF para previsualización visual del PDF como imagen
import pdfplumber
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Gestión y Registro de Facturas", page_icon="📂", layout="wide"
)

st.title("📂 Extracción Automática y Registro de Documentos Tributarios")
st.markdown("""
Sube tus documentos PDF. El sistema analizará los bloques de la factura para extraer con precisión:
**Nombre Emisor, RUT Emisor, Número de Documento, Nombre Deudor, RUT Deudor, Fecha de Emisión, Monto Neto, I.V.A 19% y Total**.
""")

# Columnas exactas solicitadas
columnas_backend = [
    'SELECCIONAR',
    'ID',
    'NOMBRE EMISOR',
    'RUT EMISOR',
    'NUMERO DE DOCUMENTO',
    'NOMBRE DEUDOR',
    'RUT DEUDOR',
    'FECHA DE EMISION',
    'MONTO NETO',
    'I.V.A 19%',
    'TOTAL',
    'ESTADO',
]

if 'df_registro_global' not in st.session_state:
  st.session_state['df_registro_global'] = pd.DataFrame(
      columns=columnas_backend
  )


def limpiar_nombre_deudor(texto):
  if not texto:
    return 'No Detectado'
  # Eliminar fechas largas o numéricas que se mezclen en el bloque del deudor
  texto_limpio = re.sub(
      r'\b\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚñÑ]+\s+(?:de|del)\s+\d{2,4}\b',
      '',
      texto,
      flags=re.IGNORECASE,
  )
  texto_limpio = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', texto_limpio)
  return re.sub(r'\s+', ' ', texto_limpio).strip().strip('-/_').strip()


# Función avanzada de extracción basada en bloques y etiquetas DTE
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

  # 1. Extracción precisa de RUTs (Emisor y Deudor) mediante etiquetas R.U.T.
  ruts_etiquetados = re.findall(
      r'R\.U\.T\.[:\s]*(\d{1,2}\.\d{3}\.\d{3}-[0-9kK]|\d{7,8}-[0-9kK])',
      texto_completo,
      re.IGNORECASE,
  )
  rut_emisor = (
      ruts_etiquetados[0] if len(ruts_etiquetados) > 0 else 'No Detectado'
  )
  rut_deudor = (
      ruts_etiquetados[1] if len(ruts_etiquetados) > 1 else 'No Detectado'
  )

  if rut_emisor == 'No Detectado' or rut_deudor == 'No Detectado':
    # Respaldo general si las etiquetas varían
    todos_ruts = re.findall(
        r'\b(\d{1,2}\.\d{3}\.\d{3}-[0-9kK]|\d{7,8}-[0-9kK])\b', texto_completo
    )
    if len(todos_ruts) >= 2:
      if rut_emisor == 'No Detectado':
        rut_emisor = todos_ruts[0]
      if rut_deudor == 'No Detectado':
        rut_deudor = todos_ruts[1]
    elif len(todos_ruts) == 1 and rut_emisor == 'No Detectado':
      rut_emisor = todos_ruts[0]

  # 2. Nombre Emisor
  nombre_emisor = 'No Detectado'
  for linea in lineas_texto[:6]:
    if any(
        k in linea.upper() for k in ['SPA', 'LTDA', 'S.A.', 'E.I.R.L.', 'SOCIEDAD']
    ):
      nombre_emisor = linea
      break
  if nombre_emisor == 'No Detectado' and len(lineas_texto) > 1:
    for l in lineas_texto[1:5]:
      if len(l) > 3 and 'GIRO' not in l.upper() and 'HUERTO' not in l.upper():
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
        r'FACTURA\s+ELECTRONICA.*?N[º°]?\s*(\d+)',
        texto_completo,
        re.DOTALL | re.IGNORECASE,
    )
    if match_alt:
      num_doc = match_alt.group(1)

  # 4. Nombre Deudor (Bloque Señor(es)) con limpieza de fecha integrada
  nombre_deudor = 'No Detectado'
  capturando = False
  deudor_lineas = []
  for linea in lineas_texto:
    if 'SEÑOR(ES)' in linea.upper() or 'SENOR(ES)' in linea.upper():
      capturando = True
      partes = re.split(
          r'SEÑOR\(ES\):?|SENOR\(ES\):?', linea, flags=re.IGNORECASE
      )
      if len(partes) > 1 and partes[1].strip():
        deudor_lineas.append(partes[1].strip())
      continue
    if capturando:
      if 'R.U.T.:' in linea.upper() or 'GIRO:' in linea.upper():
        break
      if linea:
        deudor_lineas.append(linea)
  if deudor_lineas:
    nombre_deudor = limpiar_nombre_deudor(' '.join(deudor_lineas))

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
      r'MONTO\s*NETO\s*\$?\s*([\d\.]+)', texto_completo
