import streamlit as st
import pandas as pd
import io
import base64

st.set_page_config(
    page_title="Gestión y Registro de Documentos",
    page_icon="📂",
    layout="wide"
)

st.title("📂 Registro, Previsualización y Control de Documentos")
st.markdown("""
Sube tus documentos de respaldo (PDFs, Excel, CSV), revísalos en la vista previa para asegurarte de que son los correctos, 
regístralos oficialmente y **elimina cualquier archivo** del historial si cometiste un error.
""")

# Inicializar memoria de sesión para el registro acumulativo
if 'df_registro_global' not in st.session_state:
    st.session_state['df_registro_global'] = pd.DataFrame(columns=[
        'ID', 'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
    ])

# 1. Carga de Archivos
with st.container(border=True):
    st.markdown("### 📥 1. Cargar Archivo(s)")
    archivos_subidos = st.file_uploader(
        "Selecciona uno o varios archivos (PDF, Excel, CSV):",
        type=["pdf", "xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="uploader_principal"
    )

# 2. Vista Previa y Validación antes del registro
if archivos_subidos:
    st.divider()
    st.markdown("### 👁️ 2. Vista Previa y Validación")
    
    nombres_archivos = [a.name for a in archivos_subidos]
    archivo_sel = st.selectbox("Selecciona un archivo para previsualizar antes de registrar:", nombres_archivos)
    
    archivo_obj = next((f for f in archivos_subidos if f.name == archivo_sel), None)
    
    if archivo_obj:
        ext = archivo_obj.name.split('.')[-1].lower()
        
        if ext == 'pdf':
            try:
                base64_pdf = base64.b64encode(archivo_obj.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="450px" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error al mostrar la vista previa del PDF: {e}")
        elif ext in ['xlsx', 'xls']:
            try:
                df_prev = pd.read_excel(archivo_obj)
                st.dataframe(df_prev.head(25), use_container_width=True)
            except Exception as e:
                st.error(f"Error al leer el Excel: {e}")
        elif ext == 'csv':
            try:
                archivo_obj.seek(0)
                try:
                    df_prev = pd.read_csv(archivo_obj, sep=';')
                except:
                    archivo_obj.seek(0)
                    df_prev = pd.read_csv(archivo_obj, sep=',')
                st.dataframe(df_prev.head(25), use_container_width=True)
            except Exception as e:
                st.error(f"Error al leer el CSV: {e}")

    st.divider()
    
    # Botón para confirmar y registrar oficialmente los archivos validados
    if st.button("➕ Confirmar y Registrar Archivos Validados", type="primary", use_container_width=True):
        nuevos = []
        for arc in archivos_subidos:
            if arc.name not in st.session_state['df_registro_global']['Nombre de Archivo'].values:
                nuevos.append({
                    'ID': f"{arc.name}_{arc.size}",
                    'Nombre de Archivo': arc.name,
                    'Tipo': arc.name.split('.')[-1].upper(),
                    'Tamaño (KB)': round(arc.size / 1024, 2),
                    'Estado': 'Registrado y Validado'
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

# 3. Historial Consolidado con Opciones de Borrado y Descarga
if not st.session_state['df_registro_global'].empty:
    st.divider()
    st.subheader("📋 Historial de Documentos Registrados")
    st.markdown(f"Total de documentos guardados: **{len(st.session_state['df_registro_global'])}**")
    
    # Mostrar tabla limpia sin la columna técnica ID
    df_mostrar = st.session_state['df_registro_global'].drop(columns=['ID'])
    st.dataframe(df_mostrar, use_container_width=True)
    
    st.markdown("#### 🗑️ Gestión y Eliminación de Registros")
    st.markdown("Selecciona los archivos que deseas retirar del registro si cometiste algún error:")
    
    archivos_disponibles = st.session_state['df_registro_global']['Nombre de Archivo'].tolist()
    a_borrar = st.multiselect("Selecciona archivos a eliminar:", options=archivos_disponibles, key="multiselect_borrar")
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("❌ Eliminar Archivos Seleccionados", type="primary"):
            if a_borrar:
                st.session_state['df_registro_global'] = st.session_state['df_registro_global'][
                    ~st.session_state['df_registro_global']['Nombre de Archivo'].isin(a_borrar)
                ]
                st.success(f"🗑️ Se eliminaron {len(a_borrar)} archivos del registro.")
                st.rerun()
            else:
                st.warning("Selecciona al menos un archivo para borrar.")
    with col_b2:
        if st.button("⚠️ Vaciar Todo el Historial"):
            st.session_state['df_registro_global'] = pd.DataFrame(columns=[
                'ID', 'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
            ])
            st.success("🧹 Historial vaciado por completo.")
            st.rerun()

    st.divider()

    # Botón de Descarga General en Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_mostrar.to_excel(writer, sheet_name='Registro_Documentos', index=False)
    
    st.download_button(
        label="📥 Descargar Registro Consolidado en Excel",
        data=output.getvalue(),
        file_name="Registro_Documentos_Cruce.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
        key="dl_excel_final"
    )
else:
    st.info("💡 Sube tus documentos arriba para previsualizarlos, validarlos y agregarlos al registro de control.")
