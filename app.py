def normalizar_cartola(archivo_subido):
    """Lee la cartola ignorando los encabezados de tabla del PDF."""
    nombre_archivo = archivo_subido.name.lower()
    try:
        registros_ok = []
        registros_dudosos = []

        # Lista de palabras clave para omitir encabezados y saldos
        palabras_ignorar = [
            'saldo inicial', 'saldo final', 'cartola de cuenta', 
            'canal o sucursal', 'nro. docto', 'abonos (clp)', 
            'monto abono', 'fecha descripción'
        ]

        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for num_pag, pagina in enumerate(pdf.pages, start=1):
                    tablas = pagina.extract_tables()
                    for tabla in tablas:
                        for fila in tabla:
                            if not fila:
                                continue
                            
                            f_clean = [str(c).strip().replace('\n', ' ') if c else "" for c in fila]
                            texto_fila = " ".join(f_clean)
                            texto_lower = texto_fila.lower()
                            
                            # Si la fila está vacía o es un encabezado/saldo, se ignora por completo
                            if not any(f_clean) or any(p in texto_lower for p in palabras_ignorar):
                                continue
                            
                            monto_encontrado = None
                            for celda in reversed(f_clean):
                                m = extraer_monto_chileno(celda)
                                if m:
                                    monto_encontrado = m
                                    break
                            
                            if not monto_encontrado:
                                monto_encontrado = extraer_monto_chileno(texto_fila)

                            match_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto_fila)
                            fecha = match_fecha.group(0) if match_fecha else "S/F"
                            
                            identificador = extraer_rut_o_nombre(texto_fila)
                            glosa_limpia = re.sub(r'\b\d{1,3}(?:[.,]\d{3})+\b', '', texto_fila).strip()

                            if monto_encontrado:
                                registros_ok.append({
                                    'Fecha': fecha,
                                    'Identificador / Cliente': identificador,
                                    'Monto Pago': monto_encontrado,
                                    'Descripción Glosa': glosa_limpia[:120]
                                })
                            else:
                                if len(texto_fila) > 15:
                                    registros_dudosos.append({
                                        'Página': num_pag,
                                        'Fecha': fecha,
                                        'Glosa Capturada': texto_fila[:100],
                                        'Observación': 'Fila sin monto legible'
                                    })

        elif nombre_archivo.endswith(('.xlsx', '.xls', '.csv')):
            df_raw = pd.read_excel(archivo_subido) if nombre_archivo.endswith(('.xlsx', '.xls')) else pd.read_csv(archivo_subido)
            for idx, row in df_raw.iterrows():
                texto_fila = " ".join([str(v) for v in row.values if pd.notna(v)])
                m = extraer_monto_chileno(texto_fila)
                if m:
                    registros_ok.append({
                        'Fecha': 'VER_EXCEL',
                        'Identificador / Cliente': extraer_rut_o_nombre(texto_fila),
                        'Monto Pago': m,
                        'Descripción Glosa': texto_fila[:100]
                    })

        df_ok = pd.DataFrame(registros_ok).reset_index(drop=True) if registros_ok else pd.DataFrame(columns=['Fecha', 'Identificador / Cliente', 'Monto Pago', 'Descripción Glosa'])
        df_dudosos = pd.DataFrame(registros_dudosos).reset_index(drop=True) if registros_dudosos else pd.DataFrame(columns=['Página', 'Fecha', 'Glosa Capturada', 'Observación'])

        return df_ok, df_dudosos, "OK"

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), f"Error al procesar: {str(e)}"
