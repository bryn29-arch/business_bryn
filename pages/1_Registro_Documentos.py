import streamlit as st
import pandas as pd
import io
import sys
import os

# Esto le indica a Python que busque la carpeta utils en la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

st.set_page_config(
    page_title="Registro de Documentos", 
    page_icon="📂", 
    layout="wide"
)

st.title("📂 Registro y Extracción Liviana de Documentos")
st.markdown("""
Este módulo está diseñado para **procesar tus archivos en el momento** (facturas, boletas, planillas de respaldo), 
generar una tabla resumen limpia y **descargarla directamente a tu computador o memoria externa**, 
evitando acumular archivos pesados en la memoria de la nube.
""")

with st.container(border=True):
    st.markdown("### 📥 Subir Archivo para Extracción")
    archivo_registro = st.file_uploader(
        "Selecciona un archivo de respaldo (Excel o CSV)",
        type=["xlsx", "xls", "csv"],
        key="uploader_registro_liviano"
    )

if archivo_registro is not None:
    try:
        nombre_reg = archivo_registro.name.lower()
        if nombre_reg.endswith('.csv'):
            try:
                df_reg_raw = pd.read_csv(archivo_registro, sep=';', encoding='utf-8')
            except:
                archivo_registro.seek(0)
                df_reg_raw = pd.read_csv(archivo_registro, sep=',', encoding='utf-8')
            hojas_reg = None
        else:
            archivo_registro.seek(0)
            xls_reg = pd.ExcelFile(archivo_registro)
            hojas_reg = xls_reg.sheet_names
            archivo_registro.seek(0)
            if len(hojas_reg) > 1:
                hoja_reg_sel = st.selectbox("📌 Selecciona la hoja a procesar:", hojas_reg, key="sel_hoja_reg")
                archivo_registro.seek(0)
                df_reg_raw = pd.read_excel(archivo_registro, sheet_name=hoja_reg_sel)
            else:
                archivo_registro.seek(0)
                df_reg_raw = pd.read_excel(archivo_registro, sheet_name=0)

        st.success("✅ Archivo procesado correctamente para extracción.")

        # Métricas rápidas de la tabla extraída
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("📄 Total de Registros Extraídos", f"{len(df_reg_raw):,}".replace(",", "."))
        col_m2.metric("📊 Columnas Identificadas", len(df_reg_raw.columns))

        # Vista previa ligera (primeras 50 filas máximo)
        with st.expander("👁️ Ver Vista Previa del Registro Extraído (Primeras 50 filas)"):
            st.dataframe(df_reg_raw.head(50), use_container_width=True)

        st.divider()

        # Botón para descargar el archivo limpio a la PC del usuario y liberar la nube
        st.markdown("### 💾 Guardar Registro en tu Computador")
        st.markdown("Haz clic abajo para descargar la tabla procesada en tu disco local o memoria externa:")

        output_reg = io.BytesIO()
        with pd.ExcelWriter(output_reg, engine='openpyxl') as writer_reg:
            df_reg_raw.to_excel(writer_reg, sheet_name='Registro_Documentos', index=False)

        nombre_salida = f"Registro_{archivo_registro.name.split('.')[0]}.xlsx"
        st.download_button(
            label="📥 Descargar Tabla en Excel Local",
            data=output_reg.getvalue(),
            file_name=nombre_salida,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="dl_registro_local"
        )

    except Exception as e:
        st.error(f"Error al leer el archivo para registro: {str(e)}")
else:
    st.info("👈 Sube un archivo en esta página para generar su tabla resumen y guardarlo directamente en tu equipo.")
