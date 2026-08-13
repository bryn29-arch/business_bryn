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
Sube tus documentos de respaldo. El sistema analizará los bloques estructurados de la factura electrónica para extraer con precisión 
la **Fecha de Emisión, RUT, N° Documento, Monto e IVA**.
""")

# Inicializar memoria de sesión con las columnas requeridas
if 'df_registro_global' not in st.session_state:
    st.session_state['df_registro_global'] = pd.DataFrame(columns=[
        'SELECCIONAR', 'ID', 'NOMBRE DE ARCHIVO', 'FECHA EMISIÓN', 'RUT', 'N° DOCUMENTO', 'MONTO', 'IVA', 'TIPO', 'TAMAÑO', 'ESTADO'
    ])

# Función avanzada de extracción basada en los bloques de documentos tributarios (DTE)
def extraer_datos_pdf(archivo_pdf):
    lineas_texto = []
    texto_completo = ""
    
    try:
        bytes_data = archivo_pdf.read()
        archivo_pdf.seek(0)
        
        with pdfplumber.open(io.BytesIO(bytes_data)) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t:
                    texto_completo += t + "\n"
                    for linea in t.split('\n'):
                        lineas_texto.append(linea.strip())
    except Exception as e:
        print(f"Error leyendo PDF: {e}")

    # 1. Extracción de RUT (Busca patrones de RUT chileno en todo el documento)
    rut_encontrado = "No Detectado"
    # Patrón estándar para RUT chileno (ej: 76.123.456-7 o 12345678-9)
    matches_rut = re.findall(r'\b(\d{1,2}\.\d{3}\.\d{3}-[0-9kK]|\d{7,8}-[0-9kK])\b', texto_completo)
    if matches_rut:
        # Por lo general, el primer RUT que aparece en la cabecera es el del emisor del documento
        rut_encontrado = matches_rut[0]

    # 2. Extracción de Fecha de Emisión (Bloque de cabecera)
    fecha_encontrada = "No Detectada"
    for i, linea in enumerate(lineas_texto):
        if re.search(r'emisi[oó]n|fecha', linea, re.IGNORECASE):
            # Busca en la misma línea o en la línea siguiente
            match_f = re.search(r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b', linea)
            if match_f:
                fecha_encontrada = match_f.group(1)
                break
            elif i + 1 < len(lineas_texto):
                match_f_next = re.search(r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b', lineas_texto[i+1])
                if match_f_next:
                    fecha_encontrada = match_f_next.group(1)
                    break
    if fecha_encontrada == "No Detectada":
        match_gen_f = re.search(r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b', texto_completo)
        if match_gen_f:
            fecha_encontrada = match_gen_f.group(1)

    # 3. Extracción de N° Documento / Folio (Bloque superior derecho o etiquetas)
    folio_encontrado = "S/F"
    for i, linea in enumerate(lineas_texto):
        if re.search(r'n[oº°]\s*(?:de\s*)?folio|folio|n[oº°]\s*d[oé]c|factura|boleta', linea, re.IGNORECASE):
            match_fol = re.search(r'(?:folio|n[oº°]\s*d[oé]c|factura|boleta)[\s.:#]*(\d+)', linea, re.IGNORECASE)
            if match_fol:
                folio_encontrado = match_fol.group(1)
                break
            elif i + 1 < len(lineas_texto):
                match_fol_next = re.search(r'(\d{1,10})', lineas_texto[i+1])
                if match_fol_next:
                    folio_encontrado = match_fol_next.group(1)
                    break

    # 4. Extracción de IVA (Bloque de Totales)
    iva_encontrado = "0"
    for i, linea in enumerate(lineas_texto):
        if re.search(r'\biva\b', linea, re.IGNORECASE):
            # Extrae todos los números con formato de moneda en esa línea o la siguiente
            numeros_iva = re.findall(r'([\d{1,3}(?:\.\d{3})*]+)', linea)
            if numeros_iva:
                iva_encontrado = numeros_iva[-1]
                break
            elif i + 1 < len(lineas_texto):
                numeros_iva_next = re.findall(r'([\d{1,3}(?:\.\d{3})*]+)', lineas_texto[i+1])
                if numeros_iva_next:
                    iva_encontrado = numeros_iva_next[-1]
                    break

    # 5. Extracción de Monto Total (Bloque de Totales / Total a Pagar)
    monto_encontrado = "0"
    for i, linea in enumerate(lineas_texto):
        if re.search(r'total\s*(?:a\s*pago|monto)?', linea, re.IGNORECASE):
            numeros_monto = re.findall(r'([\d{1,3}(?:\.\d{3})*]+)', linea)
            if numeros_monto:
                monto_encontrado = numeros_monto[-1]
                break
            elif i + 1 < len(lineas_texto):
                numeros_monto_next = re.findall(r'([\d{1,3}(?:\.\d{3})*]+)', lineas_texto[i+1])
                if numeros_monto_next:
                    monto_encontrado = numeros_monto_next[-1]
                    break

    # Respaldo financiero si el monto no fue capturado por etiqueta
    if monto_encontrado == "0" or monto_encontrado == "":
        todos_los_montos = re.findall(r'\$\s*([\d{1,3}(?:\.\d{3})*]+)', texto_completo)
        if todos_los_montos:
            monto_encontrado = todos_los_montos[-1]

    return {
        'FECHA EMISIÓN': fecha_encontrada,
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
    st.markdown("### 👁️ 2. Vista Previa y Análisis de Bloques Estructurados")
    
    nombres_archivos = [a.name for a in archivos_subidos]
    archivo_sel = st.selectbox("Selecciona un archivo para previsualizar y revisar los datos extraídos:", nombres_archivos)
    
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
            st.markdown("#### 🔍 Datos Estructurados Detectados")
            if ext == 'pdf':
                archivo_obj.seek(0)
                datos_extraidos = extraer_datos_pdf(archivo_obj)
                archivo_obj.seek(0)
                
                st.info("💡 Lectura basada en bloques de cabecera y totales:")
                st.metric("📅 Fecha de Emisión", datos_extraidos['FECHA EMISIÓN'])
                st.metric("🏢 RUT Identificado", datos_extraidos['RUT'])
                st.metric("📄 N° de Documento / Folio", datos_extraidos['N° DOCUMENTO'])
                st.metric("💰 Monto Total", f"$ {datos_extraidos['MONTO']}")
                st.metric("📊 IVA Extraído", f"$ {datos_extraidos['IVA']}")
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
                    f_val = d['FECHA EMISIÓN']
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
                    'FECHA EMISIÓN': f_val,
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
            st.success(f"✅ ¡Se han registrado {len(nuevos)} archivos correctamente con sus bloques extraídos!")
            st.rerun()
        else:
            st.warning("⚠️ Todos los archivos seleccionados ya se encontraban registrados previamente.")

# 3. Historial Consolidado con Tabla Interactiva y Reordenamiento
if not st.session_state['df_registro_global'].empty:
    st.divider()
    st.subheader("📋 Historial Consolidado de Documentos Registrados")
    st.markdown("Marca la casilla (**`SELECCIONAR`**) en la tabla de abajo de los documentos que deseas eliminar y haz clic en el botón de borrado:")
    
    columnas_a_ocultar = ['NOMBRE DE ARCHIVO', 'TIPO', 'TAMAÑO', 'ID']
    df_vista = st.session_state['df_registro_global'].drop(columns=columnas_a_ocultar, errors='ignore')
    
    columnas_intermedias = [col for col in df_vista.columns if col not in ['SELECCIONAR', 'ESTADO']]
    nuevo_orden = []
    if 'SELECCIONAR' in df_vista.columns:
        nuevo_orden.append('SELECCIONAR')
    nuevo_orden.extend(columnas_intermedias)
    if 'ESTADO' in df_vista.columns:
        nuevo_orden.append('ESTADO')
    
    df_vista = df_vista[nuevo_orden]
    
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
                'SELECCIONAR', 'ID', 'NOMBRE DE ARCHIVO', 'FECHA EMISIÓN', 'RUT', 'N° DOCUMENTO', 'MONTO', 'IVA', 'TIPO', 'TAMAÑO', 'ESTADO'
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
    st.info("💡 Sube tus documentos arriba para previsualizarlos, validar su análisis de bloques y agregarlos al registro de control.")
