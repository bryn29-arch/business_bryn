import streamlit as st
import pandas as pd
import io
import fitz  # PyMuPDF para previsualización visual del PDF como imagen
import pdfplumber
import re

st.set_page_config(
    page_title="Gestión, Lectura y Registro de Documentos",
    page_icon="📂",
    layout="wide"
)

st.title("📂 Extracción Inteligente y Registro de Documentos (PDF, Excel, CSV)")
st.markdown("""
Sube tus documentos de respaldo. El sistema **extraerá automáticamente los datos clave** y podrás gestionar la tabla 
marcando con un **check** las filas que desees eliminar.
""")

# Inicializar memoria de sesión con todas las columnas necesarias
if 'df_registro_global' not in st.session_state:
    st.session_state['df_registro_global'] = pd.DataFrame(columns=[
        'SELECCIONAR', 'ID', 'NOMBRE DE ARCHIVO', 'FECHA', 'RUT', 'N° DOCUMENTO', 'MONTO', 'IVA', 'TIPO', 'TAMAÑO', 'ESTADO'
    ])

# Función inteligente y robusta para extraer datos clave desde el texto de un PDF
def extraer_datos_pdf(archivo_pdf):
    texto_completo = ""
    try:
        # Creamos un flujo seguro en memoria para evitar conflictos con el puntero de Streamlit
        bytes_data = archivo_pdf.read()
        archivo_pdf.seek(0)
        
        with pdfplumber.open(io.BytesIO(bytes_data)) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_completo += t + "\n"
    except Exception as e:
        print(f"Error leyendo PDF: {e}")

    rut_match = re.search(r'\b\d{1,2}\.\d{3}\.\d{3}-[0-9kK]\b|\b\d{7,8}-[0-9kK]\b', texto_completo)
    rut_encontrado = rut_match.group(0) if rut_match else "No Detectado"

    fecha_match = re.search(r'\b\d{2}[-/]\d{2}[-/]\d{4}\b', texto_completo)
    fecha_encontrada = fecha_match.group(0) if fecha_match else "No Detectada"

    folio_match = re.search(r'(?:Folio|N°|Factura|Boleta)[\s.:#]*(\d+)', texto_completo, re.IGNORECASE)
    folio_encontrado = folio_match.group(1) if folio_match else "S/F"

    posibles_montos = re.findall(r'\$\s*([\d{1,3}(?:\.\d{3})*]+)', texto_completo)
    monto_encontrado = posibles_montos[-1] if posibles_montos else "0"

    iva_match = re.search(r'IVA[\s.:\$]*([\d{1,3}(?:\.\d{3})*]+)', texto_completo, re.IGNORECASE)
    iva_encontrado = iva_match.group(1) if iva_match else "0"

    return {
        'FECHA': fecha_encontrada,
        'RUT': rut_encontrado,
        'N° DOCUMENTO': folio_encontrado,
        'MONTO': monto_encontrado,
        'IVA': iva_encontrado
    }

# 1. Carga de Archivos
with st.container(border=True):
    st.markdown("### 📥 1. Cargar Archivo(s) de Respaldo")
    archivos_subidos = st.file_uploader(
        "Selecciona uno o varios archivos (PDF, Excel, CSV):",
        type=["pdf", "xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="uploader_principal"
    )

# 2. Vista Previa Directa y Extracción de Datos
if archivos_subidos:
    st.divider()
    st.markdown("### 👁️ 2. Vista Previa y Datos Extraídos Automáticamente")
    
    nombres_archivos = [a.name for a in archivos_subidos]
    archivo_sel = st.selectbox("Selecciona un archivo para previsualizar y revisar sus datos:", nombres_archivos)
    
    archivo_obj = next((f for f in archivos_subidos if f.name == archivo_sel), None)
    
    if archivo_obj:
        ext = archivo_obj.name.split('.')[-1].lower()
        
        col_v1, col_v2 = st.columns([1, 1])
        
        with col_v1:
            st.markdown("#### 📄 Vista Previa Visual")
            if ext == 'pdf':
                try:
                    bytes_pdf = archivo_obj.read()
                    doc = fitz.open(stream=bytes_pdf, filetype="pdf")
                    if len(doc) > 0:
                        pix = doc[0].get_pixmap(dpi=120)
                        st.image(pix.tobytes("png"), caption=f"Página 1 de {len(doc)}", use_container_width=True)
                    archivo_obj.seek(0)
                except Exception as e:
                    st.error(f"Error al mostrar imagen del PDF: {e}")
            elif ext in ['xlsx', 'xls']:
                try:
                    df_prev = pd.read_excel(archivo_obj)
                    st.dataframe(df_prev.head(15), use_container_width=True)
                    archivo_obj.seek(0)
                except Exception as e:
                    st.error(f"Error al leer Excel: {e}")
            elif ext == 'csv':
                try:
                    archivo_obj.seek(0)
                    try:
                        df_prev = pd.read_csv(archivo_obj, sep=';')
                    except:
                        archivo_obj.seek(0)
                        df_prev = pd.read_csv(archivo_obj, sep=',')
                    st.dataframe(df_prev.head(15), use_container_width=True)
                    archivo_obj.seek(0)
                except Exception as e:
                    st.error(f"Error al leer CSV: {e}")

        with col_v2:
            st.markdown("#### 🔍 Datos Extraídos del Documento")
            if ext == 'pdf':
                archivo_obj.seek(0)
                datos_extraidos = extraer_datos_pdf(archivo_obj)
                archivo_obj.seek(0)
                
                st.info("💡 Estos son los datos detectados automáticamente.")
                st.metric("📅 Fecha Detectada", datos_extraidos['FECHA'])
                st.metric("🏢 RUT Identificado", datos_extraidos['RUT'])
                st.metric("📄 N° de Documento / Folio", datos_extraidos['N° DOCUMENTO'])
                st.metric("💰 Monto Total", f"$ {datos_extraidos['MONTO']}")
                st.metric("📊 IVA Estimado", f"$ {datos_extraidos['IVA']}")
            else:
                st.success("✅ Archivo tabular (Excel/CSV) listo para ser incorporado al registro de control.")

    st.divider()
    
    # Botón para confirmar y registrar oficialmente los archivos validados
    if st.button("➕ Confirmar y Registrar Archivos Validados", type="primary", use_container_width=True):
        nuevos = []
        for arc in archivos_subidos:
            if arc.name not in st.session_state['df_registro_global']['NOMBRE DE ARCHIVO'].values:
                if arc.name.lower().endswith('.pdf'):
                    arc.seek(0)
                    d = extraer_datos_pdf(arc)
                    arc.seek(0)
                    f_val = d['FECHA']
                    rut_val = d['RUT']
                    doc_val = d['N° DOCUMENTO']
                    monto_val = d['MONTO']
                    iva_val = d['IVA']
                else:
                    f_val = "N/A"
                    rut_val = "N/A"
                    doc_val = "N/A"
                    monto_val = "Ver Excel"
                    iva_val = "N/A"

                nuevos.append({
                    'SELECCIONAR': False,
                    'ID': f"{arc.name}_{arc.size}",
                    'NOMBRE DE ARCHIVO': arc.name,
                    'FECHA': f_val,
                    'RUT': rut_val,
                    'N° DOCUMENTO': doc_val,
                    'MONTO': monto_val,
                    'IVA': iva_val,
                    'TIPO': arc.name.split('.')[-1].upper(),
                    'TAMAÑO': round(arc.size / 1024, 2),
                    'ESTADO': 'Registrado y Validado'
                })
        
        if nuevos:
            df_nuevo = pd.DataFrame(nuevos)
            st.session_state['df_registro_global'] = pd.concat(
                [st.session_state['df_registro_global'], df_nuevo], ignore_index=True
            )
            st.success(f"✅ ¡Se han registrado {len(nuevos)} archivos correctamente!")
            st.rerun()
        else:
            st.warning("⚠️ Todos los archivos seleccionados ya se encontraban registrados previamente.")

# 3. Historial Consolidado con Tabla Interactiva y Reordenamiento
if not st.session_state['df_registro_global'].empty:
    st.divider()
    st.subheader("📋 Historial Consolidado de Documentos Registrados")
    st.markdown("Marca la casilla (**`SELECCIONAR`**) en la tabla de abajo de los documentos que deseas eliminar y haz clic en el botón de borrado:")
    
    # Ocultamos metadatos innecesarios en la vista
    columnas_a_ocultar = ['NOMBRE DE ARCHIVO', 'TIPO', 'TAMAÑO', 'ID']
    df_vista = st.session_state['df_registro_global'].drop(columns=columnas_a_ocultar, errors='ignore')
    
    # Reordenamos: 'SELECCIONAR' al principio y 'ESTADO' al final
    columnas_intermedias = [col for col in df_vista.columns if col not in ['SELECCIONAR', 'ESTADO']]
    nuevo_orden = []
    if 'SELECCIONAR' in df_vista.columns:
        nuevo_orden.append('SELECCIONAR')
    nuevo_orden.extend(columnas_intermedias)
    if 'ESTADO' in df_vista.columns:
        nuevo_orden.append('ESTADO')
    
    df_vista = df_vista[nuevo_orden]
    
    # Tabla interactiva con checkboxes
    df_editado = st.data_editor(
        df_vista,
        column_config={
            "SELECCIONAR": st.column_config.CheckboxColumn(
                "🗑️ Seleccionar",
                help="Marca para eliminar este registro",
                default=False,
            )
        },
        disabled=columnas_intermedias,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="editor_tabla_registros"
    )
    
    if len(df_editado) == len(st.session_state['df_registro_global']):
        st.session_state['df_registro_global']['SELECCIONAR'] = df_editado['SELECCIONAR']

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("❌ Eliminar Filas Marcadas con Check", type="primary"):
            filas_a_mantener = st.session_state['df_registro_global'][st.session_state['df_registro_global']['SELECCIONAR'] == False]
            cant_a_borrar = len(st.session_state['df_registro_global']) - len(filas_a_mantener)
            
            if cant_a_borrar > 0:
                st.session_state['df_registro_global'] = filas_a_mantener
                st.success(f"🗑️ Se han eliminado {cant_a_borrar} registros seleccionados.")
                st.rerun()
            else:
                st.warning("⚠️ No has marcado ninguna casilla en la columna 'SELECCIONAR' de la tabla.")
                
    with col_b2:
        if st.button("⚠️ Vaciar Todo el Historial"):
            st.session_state['df_registro_global'] = pd.DataFrame(columns=[
                'SELECCIONAR', 'ID', 'NOMBRE DE ARCHIVO', 'FECHA', 'RUT', 'N° DOCUMENTO', 'MONTO', 'IVA', 'TIPO', 'TAMAÑO', 'ESTADO'
            ])
            st.success("🧹 Historial vaciado por completo.")
            st.rerun()

    st.divider()

    df_exportar = st.session_state['df_registro_global'].drop(columns=['SELECCIONAR', 'ID'], errors='ignore')
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_exportar.to_excel(writer, sheet_name='Registro_Documentos', index=False)
    
    st.download_button(
        label="📥 Descargar Registro Consolidado en Excel",
        data=output.getvalue(),
        file_name="Registro_Documentos_Cruce.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
        key="dl_excel_final"
    )
else:
    st.info("💡 Sube tus documentos arriba para previsualizarlos, ver su extracción de datos automática y agregarlos al registro de control.")
