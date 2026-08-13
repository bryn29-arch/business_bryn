import streamlit as st
import pandas as pd
import io
import base64

st.set_page_config(
    page_title="Registro, Vista Previa y Gestión de Documentos",
    page_icon="📂",
    layout="wide"
)

st.title("📂 Registro, Vista Previa y Gestión de Documentos")
st.markdown("""
Sube tus documentos, revísalos en la vista previa, regístralos de forma segura y **elimina cualquier registro** si cometiste un error.
""")

# 1. Inicializar la memoria (session_state) para el historial acumulativo
if 'df_registro_global' not in st.session_state:
    st.session_state['df_registro_global'] = pd.DataFrame(columns=[
        'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
    ])

# 2. Contenedor para la subida de archivos
with st.container(border=True):
    st.markdown("### 📥 1. Carga de Archivos")
    archivos_subidos = st.file_uploader(
        "Selecciona uno o varios archivos (PDF, Excel, CSV):",
        type=["pdf", "xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="uploader_con_previsualizacion"
    )

# 3. ZONA DE VISTA PREVIA (Para validar antes de registrar)
if archivos_subidos:
    st.divider()
    st.markdown("### 👁️ 2. Vista Previa (Revisa antes de registrar)")
    
    nombres_archivos = [archivo.name for archivo in archivos_subidos]
    archivo_seleccionado_nombre = st.selectbox("Selecciona un archivo para previsualizar:", nombres_archivos)
    
    archivo_obj = next((f for f in archivos_subidos if f.name == archivo_seleccionado_nombre), None)
    
    if archivo_obj:
        ext = archivo_obj.name.split('.')[-1].lower()
        
        if ext == 'pdf':
            try:
                base64_pdf = base64.b64encode(archivo_obj.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500px" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"No se pudo renderizar la vista previa del PDF: {str(e)}")
                
        elif ext in ['xlsx', 'xls']:
            try:
                df_preview = pd.read_excel(archivo_obj)
                st.dataframe(df_preview.head(30), use_container_width=True)
            except Exception as e:
                st.error(f"Error al leer el Excel: {str(e)}")
                
        elif ext == 'csv':
            try:
                archivo_obj.seek(0)
                try:
                    df_preview = pd.read_csv(archivo_obj, sep=';')
                except:
                    archivo_obj.seek(0)
                    df_preview = pd.read_csv(archivo_obj, sep=',')
                st.dataframe(df_preview.head(30), use_container_width=True)
            except Exception as e:
                st.error(f"Error al leer el CSV: {str(e)}")

    st.divider()

    # 4. BOTÓN DE CONFIRMACIÓN Y REGISTRO
    st.markdown("### ✅ 3. Confirmar y Registrar")
    if st.button("➕ Confirmar y Registrar Archivos", type="primary", use_container_width=True):
        nuevos_datos = []
        for archivo in archivos_subidos:
            nombre = archivo.name
            extension = nombre.split('.')[-1].upper()
            tamanio_kb = round(archivo.size / 1024, 2)
            
            nuevos_datos.append({
                'Nombre de Archivo': nombre,
                'Tipo': extension,
                'Tamaño (KB)': tamanio_kb,
                'Estado': 'Registrado y Validado'
            })
        
        df_nuevo = pd.DataFrame(nuevos_datos)
        
        st.session_state['df_registro_global'] = pd.concat(
            [st.session_state['df_registro_global'], df_nuevo]
        ).drop_duplicates(subset=['Nombre de Archivo'], keep='last')
        
        st.success(f"✨ ¡Se han registrado **{len(archivos_subidos)}** archivos oficialmente en el sistema!")

# 5. HISTORIAL CONSOLIDADO Y OPCIONES DE GESTIÓN (BORRAR / DESCARGAR)
if not st.session_state['df_registro_global'].empty:
    st.divider()
    st.subheader("📋 Historial Consolidado de Documentos Registrados")
    st.markdown(f"Total de documentos en el registro: **{len(st.session_state['df_registro_global'])}**")
    
    st.dataframe(st.session_state['df_registro_global'], use_container_width=True)
    
    # --- NUEVA SECCIÓN: ELIMINAR REGISTROS ESPECÍFICOS ---
    with st.expander("🗑️ Opciones de Borrado (Eliminar archivos del historial)"):
        archivos_en_historial = st.session_state['df_registro_global']['Nombre de Archivo'].tolist()
        
        archivos_a_borrar = st.multiselect(
            "Selecciona los archivos que deseas eliminar del registro:",
            options=archivos_en_historial,
            key="selector_borrar_archivos"
        )
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("❌ Eliminar Archivos Seleccionados", type="primary"):
                if archivos_a_borrar:
                    # Filtramos el DataFrame para conservar solo los que NO están en la lista de borrado
                    st.session_state['df_registro_global'] = st.session_state['df_registro_global'][
                        ~st.session_state['df_registro_global']['Nombre de Archivo'].isin(archivos_a_borrar)
                    ]
                    st.success(f"🗑️ Se han eliminado {len(archivos_a_borrar)} archivos del registro correctamente.")
                    st.rerun()
                else:
                    st.warning("⚠️ No has seleccionado ningún archivo para borrar.")
        with col_b2:
            if st.button("⚠️ Borrar Todo el Historial"):
                st.session_state['df_registro_global'] = pd.DataFrame(columns=[
                    'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
                ])
                st.success("🧹 El historial ha sido reiniciado por completo.")
                st.rerun()

    st.divider()
    
    # Botón de Descarga General
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state['df_registro_global'].to_excel(writer, sheet_name='Registro_Documentos', index=False)
    
    st.download_button(
        label="📥 Descargar Registro Consolidado en Excel",
        data=output.getvalue(),
        file_name="Registro_Documentos_Cruce.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
        key="dl_registro_global_btn"
    )
else:
    st.info("💡 Sube tus documentos arriba para revisarlos en la vista previa y agregarlos al registro.")
