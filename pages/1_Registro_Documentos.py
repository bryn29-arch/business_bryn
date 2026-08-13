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


def _cortar_por_palabras_clave(texto, palabras_clave):
  """Corta el texto en el primer punto donde aparece una palabra clave
  de una columna vecina que pdfplumber fusionó por error en la misma línea
  (ocurre cuando dos columnas del PDF quedan a la misma altura vertical)."""
  if not texto:
    return texto
  texto_up = texto.upper()
  posiciones = [
      texto_up.find(p.upper()) for p in palabras_clave if p.upper() in texto_up
  ]
  if posiciones:
    return texto[: min(posiciones)].strip(' -:')
  return texto.strip()


PALABRAS_CORTE_EMISOR = [
    'FACTURA', 'GUIA DE DESPACHO', 'BOLETA', 'NOTA DE CREDITO',
    'NOTA DE DEBITO', 'EXENTA', 'ELECTRONICA', 'GIRO:', 'R.U.T',
    'TIPO DE VENTA', 'FECHA EMISION', 'S.I.I',
]

PALABRAS_CORTE_DEUDOR = [
    'FECHA EMISION', 'GIRO:', 'R.U.T', 'RUT', 'S.I.I', 'DIRECCION', 'COMUNA',
]


# Función avanzada de extracción blindada contra espacios en RUTs, bloques DTE
# y columnas fusionadas por pdfplumber
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
    for l in lineas_texto[1:5]:
      if len(l) > 3 and 'GIRO' not in l.upper():
        nombre_emisor = l
        break

  # 🛠️ Corta el nombre del emisor si viene fusionado con el recuadro
  # "FACTURA ELECTRONICA" de la columna vecina
  if nombre_emisor != 'No Detectado':
    nombre_emisor = _cortar_por_palabras_clave(
        nombre_emisor, PALABRAS_CORTE_EMISOR
    )

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
        # 🛠️ Corta si "Fecha Emision:" u otra columna vecina quedó pegada
        texto_limpio = _cortar_por_palabras_clave(
            partes[1].strip(), PALABRAS_CORTE_DEUDOR
        )
        if texto_limpio:
          deudor_lineas.append(texto_limpio)
      continue
    if capturando:
      if 'R.U.T.' in linea_up or 'RUT' in linea_up or 'GIRO:' in linea_up:
        break
      if linea:
        texto_limpio = _cortar_por_palabras_clave(linea, PALABRAS_CORTE_DEUDOR)
        if texto_limpio:
          deudor_lineas.append(texto_limpio)
        # Si esta línea traía una columna vecina fusionada, detenemos
        # la captura aquí (ya llegamos al final del nombre del deudor)
        if texto_limpio != linea.strip():
          break

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


# 1. Carga de Archivos
with st.container(border=True):
  st.markdown('### 📥 Cargar Facturas o Documentos PDF')
  archivos_subidos = st.file_uploader(
      'Selecciona tus archivos PDF de respaldo:',
      type=['pdf', 'xlsx', 'xls', 'csv'],
      accept_multiple_files=True,
      key='uploader_dte',
  )

if archivos_subidos:
  st.divider()
  st.markdown('### 👁️ Vista Previa y Datos Extraídos')
  nombres = [a.name for a in archivos_subidos]
  sel = st.selectbox('Selecciona archivo para revisar:', nombres)

  obj = next((f for f in archivos_subidos if f.name == sel), None)

  if obj:
    ext = obj.name.split('.')[-1].lower()
    c1, c2 = st.columns(2)

    with c1:
      st.markdown('#### Vista Previa Visual')
      if ext == 'pdf':
        try:
          doc = fitz.open(stream=obj.read(), filetype='pdf')
          if len(doc) > 0:
            st.image(
                doc[0].get_pixmap(dpi=120).tobytes('png'),
                use_container_width=True,
            )
          obj.seek(0)
        except Exception as e:
          st.error(f'Error al previsualizar PDF: {e}')

    with c2:
      st.markdown('#### Datos Detectados')
      if ext == 'pdf':
        obj.seek(0)
        datos = extraer_datos_pdf(obj)
        obj.seek(0)

        st.write(f"🏢 **Emisor:** {datos['NOMBRE EMISOR']}")
        st.write(f"🆔 **RUT Emisor:** {datos['RUT EMISOR']}")
        st.write(f"📄 **N° Documento:** {datos['NUMERO DE DOCUMENTO']}")
        st.write(f"👤 **Deudor:** {datos['NOMBRE DEUDOR']}")
        st.write(f"🆔 **RUT Deudor:** {datos['RUT DEUDOR']}")
        st.write(f"📅 **Fecha Emisión:** {datos['FECHA DE EMISION']}")
        st.write(f"💵 **Neto:** $ {datos['MONTO NETO']}")
        st.write(f"📊 **IVA 19%:** $ {datos['I.V.A 19%']}")
        st.write(f"💳 **Total:** $ {datos['TOTAL']}")

  st.divider()
  if st.button(
      '➕ Confirmar y Registrar en la Planilla',
      type='primary',
      use_container_width=True,
  ):
    nuevos = []
    for arc in archivos_subidos:
      if (
          arc.name
          not in st.session_state['df_registro_global'][
              'NOMBRE EMISOR'
          ].values
          and arc.name.lower().endswith('.pdf')
      ):
        arc.seek(0)
        d = extraer_datos_pdf(arc)
        arc.seek(0)

        nuevos.append({
            'SELECCIONAR': False,
            'ID': f'{arc.name}_{arc.size}',
            'NOMBRE EMISOR': d['NOMBRE EMISOR'],
            'RUT EMISOR': d['RUT EMISOR'],
            'NUMERO DE DOCUMENTO': d['NUMERO DE DOCUMENTO'],
            'NOMBRE DEUDOR': d['NOMBRE DEUDOR'],
            'RUT DEUDOR': d['RUT DEUDOR'],
            'FECHA DE EMISION': d['FECHA DE EMISION'],
            'MONTO NETO': d['MONTO NETO'],
            'I.V.A 19%': d['I.V.A 19%'],
            'TOTAL': d['TOTAL'],
            'ESTADO': 'Registrado y Validado',
        })

    if nuevos:
      df_nuevo = pd.DataFrame(nuevos)
      st.session_state['df_registro_global'] = pd.concat(
          [st.session_state['df_registro_global'], df_nuevo], ignore_index=True
      )
      st.success(
          f'✅ ¡Se han registrado {len(nuevos)} documentos con la estructura'
          ' solicitada!'
      )
      st.rerun()
    else:
      st.warning('⚠️ Los documentos seleccionados ya están registrados.')

# Tabla Principal Consolidada
if not st.session_state['df_registro_global'].empty:
  st.divider()
  st.subheader('📋 Planilla Consolidada de Registro')

  df_vista = st.session_state['df_registro_global'].drop(
      columns=['ID'], errors='ignore'
  )

  cols_intermedias = [
      c for c in df_vista.columns if c not in ['SELECCIONAR', 'ESTADO']
  ]
  orden_final = ['SELECCIONAR'] + cols_intermedias + ['ESTADO']
  df_vista = df_vista[orden_final]

  df_editado = st.data_editor(
      df_vista,
      column_config={
          'SELECCIONAR': st.column_config.CheckboxColumn(
              '🗑️ Seleccionar', default=False
          )
      },
      disabled=cols_intermedias,
      hide_index=True,
      use_container_width=True,
      num_rows='fixed',
      key='tabla_maestra_dte',
  )

  if len(df_editado) == len(st.session_state['df_registro_global']):
    st.session_state['df_registro_global']['SELECCIONAR'] = df_editado[
        'SELECCIONAR'
    ]

  col1, col2 = st.columns(2)
  with col1:
    if st.button('❌ Eliminar Filas Seleccionadas', type='primary'):
      mantener = st.session_state['df_registro_global'][
          st.session_state['df_registro_global']['SELECCIONAR'] == False
      ]
      borrados = len(st.session_state['df_registro_global']) - len(mantener)
      if borrados > 0:
        st.session_state['df_registro_global'] = mantener
        st.success(f'🗑️ Se eliminaron {borrados} registros.')
        st.rerun()
      else:
        st.warning('Selecciona al menos una casilla.')
  with col2:
    if st.button('⚠️ Vaciar Todo'):
      st.session_state['df_registro_global'] = pd.DataFrame(
          columns=columnas_backend
      )
      st.success('Historial reiniciado.')
      st.rerun()

  st.divider()

  df_excel = st.session_state['df_registro_global'].drop(
      columns=['SELECCIONAR', 'ID'], errors='ignore'
  )
  output = io.BytesIO()
  with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df_excel.to_excel(writer, sheet_name='Registro_Facturas', index=False)

  st.download_button(
      label='📥 Descargar Planilla Consolidada en Excel',
      data=output.getvalue(),
      file_name='Registro_Facturas_Consolidado.xlsx',
      mime=(
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      ),
      type='secondary',
      key='dl_excel_dte',
  )
else:
  st.info(
      '💡 Sube tus documentos PDF arriba para procesarlos y construir la'
      ' planilla de registro.'
  )
