import streamlit as st
import pandas as pd
from pypdf import PdfReader
import re
import gspread
from playwright.sync_api import sync_playwright
import time
import os
os.system("playwright install chromium")
import json
from google.oauth2 import service_account
import requests

# --- DESCARGA AUTOMÁTICA DEL NAVEGADOR INVISIBLE ---
os.system("playwright install chromium")

# --- CONFIGURACIÓN DE SEGURIDAD ---
def check_password():
    def password_guessed():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("Contraseña de acceso", type="password", on_change=password_guessed, key="password")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# --- CONEXIÓN A GOOGLE SHEETS ---
def conectar_sheets():
    # 1. Leemos el diccionario de los secrets (Asegúrate de que en secrets se llame GOOGLE_CREDS)
    cred_dict = json.loads(st.secrets["GOOGLE_CREDS"])
    
    # 2. Construimos las credenciales usando el método oficial de Google (Igual que en Nimbus)
    creds_sheets = service_account.Credentials.from_service_account_info(
        cred_dict, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    
    # 3. Autorizamos al cliente de gspread
    client = gspread.authorize(creds_sheets)
    
    # 4. Abrimos el archivo por su ID directo y seleccionamos la primera hoja
    sheet = client.open_by_key('1ZP__a71alDwwjzVMF32LokjCzeS2AzilbEB48kVRjFk').sheet1
    
    return sheet
    
# --- LÓGICA DE PLAYWRIGHT (PJF) ---
def consultar_pjf(folio):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu",
                "--single-process"
            ]
        )
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda")
            
            # Ingresar el folio
            page.fill("input#txtFolio", folio) 
            page.click("button#btnConsultar")
            
           # ⏱️ Esperamos 3 segundos exactos para que el PJF cargue la respuesta
            page.wait_for_timeout(3000)
            
            # Tomamos la fotografía de evidencia
            path_img = f"captura_{folio.replace('/', '_')}.png"
            page.screenshot(path=path_img)
            
            # 🔍 LECTURA INTELIGENTE (VERSIÓN BLINDADA)
            # Extraemos TODO el código fuente (HTML) de la página y lo pasamos a minúsculas
            texto_pagina = page.content().lower() 
            
            # Buscamos fragmentos clave sin depender de acentos perfectos
            if "no cuenta con" in texto_pagina or "asignaci" in texto_pagina or "intentar" in texto_pagina:
                browser.close()
                return "Aún en fila PJF", "Aún en fila PJF", path_img
            
            # Si no está el mensaje rojo, procedemos a buscar los selectores reales
            organo = page.inner_text("#lblOrgano") if page.query_selector("#lblOrgano") else "Juzgado Extraído"
            expediente = page.inner_text("#lblExpediente") if page.query_selector("#lblExpediente") else "Expediente Extraído"
            
            browser.close()
            return organo, expediente, path_img
            
        except Exception as e:
            browser.close()
            return f"Error: {str(e)}", "N/A", None
# --- INTERFAZ ---
st.sidebar.title("LegalHub Navigator")
menu = st.sidebar.radio("Ir a:", ["Carga de Acuses", "Monitor de Estrados"])

# --- GENERADOR DE INICIALES (Añádelo justo arriba del if menu...) ---
def generar_iniciales(nombre):
    if nombre == "No encontrado" or not nombre:
        return ""
    # Palabras que no queremos que generen inicial (ej. "de la Cruz")
    excluir = ['de', 'del', 'la', 'las', 'el', 'los', 'y', 'en', 'para', 'a']
    # Limpiamos símbolos extraños y dividimos en palabras
    palabras = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', nombre).split()
    iniciales = [p[0].upper() for p in palabras if p.lower() not in excluir]
    return "".join(iniciales)

# ------------------------------------------------------------------

if menu == "Carga de Acuses":
    st.header("📂 Carga de nuevos expedientes")
    files = st.file_uploader("Sube los acuses en PDF", accept_multiple_files=True, type=['pdf'])
    
    if files:
        nuevos_datos = []
        for f in files:
            reader = PdfReader(f)
            texto = reader.pages[0].extract_text()
            
            # 1. Extraer Folio
            match_folio = re.search(r'\d{8}/\d{4}', texto)
            folio = match_folio.group(0) if match_folio else "No encontrado"
            
            # 2. Batería exhaustiva para extraer el Nombre
            patrones_nombre = [
                r"(?i)Promovente\s*:\s*([^\n]+)",
                r"(?i)Quejoso\s*:\s*([^\n]+)",
                r"(?i)Actor\s*:\s*([^\n]+)",
                r"(?i)Nombre\s*:\s*([^\n]+)",
                r"(?i)Usuario\s*:\s*([^\n]+)"
            ]
            
            promovente = "No encontrado"
            for patron in patrones_nombre:
                match = re.search(patron, texto)
                if match:
                    # Limpiamos espacios al inicio y al final
                    promovente = match.group(1).strip()
                    break
            
            # 3. Calcular Iniciales
            iniciales = generar_iniciales(promovente)
            
            # Empaquetamos todo respetando las 7 columnas de tu CSV
            nuevos_datos.append({
                "Folio": folio, 
                "Promovente": promovente,
                "Iniciales": iniciales,
                "Tipo de Monitoreo": "Diario", # Por defecto
                "Órgano": "Sin asignar",
                "Expediente": "Sin asignar",
                "Estatus": "Pendiente"
            })
        
        st.write("Datos extraídos listos para revisar:", pd.DataFrame(nuevos_datos))
        
        if st.button("Guardar en Google Sheets"):
            ws = conectar_sheets()
            for d in nuevos_datos:
                # Escribe la fila con los datos exactos en orden
                ws.append_row([
                    d['Folio'], 
                    d['Promovente'], 
                    d['Iniciales'], 
                    d['Tipo de Monitoreo'], 
                    d['Órgano'], 
                    d['Expediente'], 
                    d['Estatus']
                ])
            st.success("✅ Registros añadidos a la Matriz con Nombres e Iniciales.")

if menu == "Monitor de Estrados":
    st.header("🔍 Monitor de Estrados PJF")
    
    if st.button("🚀 Iniciar Monitoreo Diario", type="primary"):
        ws = conectar_sheets()
        # Leemos toda la matriz
        datos = pd.DataFrame(ws.get_all_records())
        
        if datos.empty:
            st.info("No hay datos en la matriz para monitorear.")
        else:
            cambios_realizados = 0
            
            for index, row in datos.iterrows():
                if row['Estatus'] == "Pendiente":
                    st.write(f"Consultando Folio: {row['Folio']} ({row['Promovente']})...")
                    
                    organo, exp, img = consultar_pjf(row['Folio'])
                    
                    # ESCENARIO 1: Sigue en fila
                    if organo == "Aún en fila PJF":
                        st.warning(f"⏳ Folio {row['Folio']}: Sigue en fila de espera del PJF.")
                        
                    # ESCENARIO 2: Error del navegador o de la página
                    elif "Error" in organo:
                        st.error(f"❌ Error al consultar {row['Folio']}: {organo}")
                        
                    # ESCENARIO 3: ¡Éxito! El PJF asignó el expediente
                    else:
                        st.success(f"🎉 ¡Asignación encontrada para {row['Folio']}! {organo} - {exp}")
                        
                        # Calculamos la fila exacta en Google Sheets (índice Pandas + 2)
                        fila_sheet = index + 2 
                        
                        # Actualizamos las celdas directamente (Columnas 5, 6 y 7 de tu CSV)
                        ws.update_cell(fila_sheet, 5, organo)      # Órgano Jurisdiccional
                        ws.update_cell(fila_sheet, 6, exp)         # Número de Expediente
                        ws.update_cell(fila_sheet, 7, "Asignado")  # Estatus
                        
                        cambios_realizados += 1
                        
                        # Enviamos la alerta a tu celular vía Telegram
                        mensaje_tg = (
                            f"🚨 NUEVA ASIGNACIÓN PJF 🚨\n\n"
                            f"👤 Promovente: {row['Promovente']}\n"
                            f"📄 Folio: {row['Folio']}\n"
                            f"🏛️ Órgano: {organo}\n"
                            f"📁 Expediente: {exp}"
                        )
                        enviar_telegram(mensaje_tg)
            
            if cambios_realizados > 0:
                st.balloons() # Celebramos si hubo asignaciones
                st.success(f"✅ Monitoreo finalizado. Se actualizaron {cambios_realizados} expedientes en la matriz.")
            else:
                st.info("✅ Monitoreo finalizado. No hubo nuevas asignaciones hoy.")
def enviar_telegram(mensaje):
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensaje}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"⚠️ No se pudo enviar el Telegram: {e}")
