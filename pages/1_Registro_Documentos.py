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
Sube tus documentos PDF. El sistema normalizará los espacios de los RUTs y analizará la estructura de la factura 
para extraer con absoluta precisión: **Nombre Emisor, RUT Emisor, Número de Documento, Nombre Deudor, RUT Deudor, Fecha de Emisión, Monto Neto, I.V.A 19% y Total**.
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
  texto_limpio = re.sub(
      r'\b\d{1,2}\s+de\s+[a-zA-ZáéíóúÁÉÍÓÚñÑ]+\s+(?:de|del)\s+\d{2,4}\b',
      '',
      texto,
      flags=re.IGNORECASE,
  )
  texto_limpio = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', texto_limpio)
  return re.sub(r'\s+', ' ', texto_limpio).strip().strip('-/_').strip()


# Función avanzada de extracción blindada contra espacios en RUTs y bloques DTE
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

  # 🛠️ Solución para espacios fantasmas entre el guion y el dígito verificador del RUT
  texto_completo = re.sub(r'-\s+([0-9kK])', r'-\1', texto_completo)

  # 1. Extracción de RUTs por orden estricto de aparición (1° Emisor, 2° Deudor)
  todos_ruts = re.findall(
      r'\b(\d{1,2}\.\d{3}\.\d{3}-[0-9kK]|\d{7,8}-[0-9kK])\b', texto_completo
  )
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
    for
