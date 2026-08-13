import fitz  # PyMuPDF
import numpy as np
import pdfplumber
import pytesseract
from PIL import Image


def extraer_texto_pdf_robusto(uploaded_file):
  """Extrae texto de un PDF.

  Primero intenta con pdfplumber y PyMuPDF. Si no detecta texto (PDF escaneado),
  aplica OCR usando pdf2image y pytesseract.
  """
  texto_completo = ''

  # Intentar extraer texto con pdfplumber primero
  try:
    with pdfplumber.open(uploaded_file) as pdf:
      for pagina in pdf.pages:
        texto_pag = pagina.extract_text()
        if texto_pag:
          texto_completo += texto_pag + '\n'
  except Exception as e:
    print(f'Error con pdfplumber: {e}')

  # Si el texto extraído es muy corto o vacío, probablemente sea un PDF escaneado
  if len(texto_completo.strip()) < 50:
    print(
        'El PDF parece ser una imagen o escaneo. Aplicando OCR (Modo'
        ' Blindado)...'
    )
    texto_completo = ''
    try:
      # Reiniciar el puntero del archivo subido en Streamlit
      uploaded_file.seek(0)
      # Leer el PDF con PyMuPDF (fitz) para convertir páginas a imágenes
      doc = fitz.open(stream=uploaded_file.read(), filetype='pdf')

      for i, pagina in enumerate(doc):
        # Renderizar página a imagen (resolución de 300 DPI para buen OCR)
        pix = pagina.get_pixmap(dpi=300)
        img_bytes = pix.tobytes('png')

        # Convertir bytes a imagen de PIL
        import io

        imagen = Image.open(io.BytesIO(img_bytes))

        # Aplicar OCR en español
        texto_ocr = pytesseract.image_to_string(imagen, lang='spa')
        texto_completo += texto_ocr + '\n'

    except Exception as e:
      print(f'Error al aplicar OCR: {e}')

  return texto_completo
