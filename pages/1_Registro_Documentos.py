import streamlit as st
import pandas as pd
import io

st.set_page_config(
    page_title="Registro de Documentos y PDFs",
    page_icon="📂",
    layout="wide"
)

st.title("📂 Registro y Control de Documentos (PDFs y Respaldos)")
st.markdown("""
En esta página puedes subir tus archivos PDF, facturas o planillas de respaldo. 
Los archivos se irán **acumulando y registrando en la lista** para que lleves un control ordenado de tu documentación.
""")

# 1. Inicializar la memoria (session_state) para que el registro no se borre
if 'df_registro_global' not in st.session_state:
    st.session_state['df_registro_global'] = pd.DataFrame(columns=[
        'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
    ])

# 2. Contenedor para la subida de archivos
with st.container(border=True):
    st.markdown("### 📥 Subir Nuevos Documentos (PDF, Excel, CSV)")
    archivos_nuevos = st.file_uploader(
        "Selecciona uno o varios archivos de respaldo:",
        type=["pdf", "xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="uploader_pdf_page"
    )

    if archivos_nuevos:
        if st.button("➕ Registrar Archivos en el Sistema", type="primary"):
            nuevos_datos = []
            for archivo in archivos_nuevos:
                nombre = archivo.name
                extension = nombre.split('.')[-1].upper()
                tamanio_kb = round(archivo.size / 1024, 2)
                
                nuevos_datos.append({
                    'Nombre de Archivo': nombre,
                    'Tipo': extension,
                    'Tamaño (KB)': tamanio_kb,
                    'Estado': 'Registrado y Disponible'
                })
            
            df_nuevo = pd.DataFrame(nuevos_datos)
            
            # Combinamos con lo que ya estaba registrado previamente en la sesión
            st.session_state['df_registro_global'] = pd.concat(
                [st.session_state['df_registro_global'], df_nuevo]
            ).drop_duplicates(subset=['Nombre de Archivo'], keep='last')
            
            st.success(f"✨ ¡Se han registrado **{len(archivos_nuevos)}** archivos nuevos exitosamente!")

# 3. Mostrar la tabla con el registro acumulado
if not st.session_state['df_registro_global'].empty:
    st.divider()
    st.subheader("📋 Historial de Documentos Registrados")
    st.markdown(f"Total de documentos en registro: **{len(st.session_state['df_registro_global'])}**")
    
    # Tabla interactiva
    st.dataframe(st.session_state['df_registro_global'], use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        # Botón para descargar el registro completo en Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            st.session_state['df_registro_global'].to_excel(writer, sheet_name='Registro_Documentos', index=False)
        
        st.download_button(
            label="📥 Descargar Registro Completo en Excel",
            data=output.getvalue(),
            file_name="Registro_Documentos_Cruce.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_registro"
        )
    with col2:
        if st.button("🗑️ Limpiar / Reiniciar Registro"):
            st.session_state['df_registro_global'] = pd.DataFrame(columns=[
                'Nombre de Archivo', 'Tipo', 'Tamaño (KB)', 'Estado'
            ])
            st.rerun()
else:
    st.info("💡 Aún no hay documentos registrados. Sube tus PDFs o planillas arriba y haz clic en registrar.")
