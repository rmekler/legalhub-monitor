import streamlit as st
import pandas as pd
import re
import json
import gspread
import requests
import os
import time
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfReader
from google.oauth2 import service_account

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="LegalHub Monitor", layout="wide")

# Instalación silenciosa de Playwright
if 'playwright_install' not in st.session_state:
    with st.spinner("Preparando entorno de navegación..."):
        os.system("playwright install chromium")
    st.session_state['playwright_install'] = True

# --- FUNCIONES ---

def enviar_telegram(mensaje):
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": mensaje}, timeout=10)
    except: pass

def conectar_sheets():
    # USAR EL NOMBRE QUE TENGAS EN SECRETS: GOOGLE_CREDS o google_credentials
    nombre_secret = "GOOGLE_CREDS" if "GOOGLE_CREDS" in st.secrets else "google_credentials"
    cred_dict = json.loads(st.secrets[nombre_secret])
    creds = service_account.Credentials.from_service_account_info(
        cred_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    return client.open_by_key('1ZP__a71alDwwjzVMF32LokjCzeS2AzilbEB48kVRjFk').sheet1

def consultar_pjf(folio):
    with sync_playwright() as p:
        # Lanzamiento optimizado
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--single-process"])
        page = browser.new_page()
        try:
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda", timeout=60000)
            page.fill("input#numFolio", folio)
            page.click("button#btnBuscar")
            time.sleep(5) # Tiempo para que el PJF reaccione
            
            contenido = page.content().lower()
            if "no cuenta con" in contenido or "asignaci" in contenido:
                browser.close()
                return "Aún en fila PJF", "Sin asignar", "Sin asignar"

            # Extracción robusta
            def extraer(label):
                try:
                    return page.evaluate(f"""() => {{
                        const el = Array.from(document.querySelectorAll('div, span, label')).find(e => e.innerText.includes('{label}'));
                        return el ? el.parentElement.innerText.replace('{label}', '').strip() : 'Sin asignar';
                    }}""")
                except: return "Sin asignar"

            organo = extraer("Órgano Jurisdiccional:")
            asunto = extraer("Tipo de Asunto:")
            expediente = extraer("Número de Expediente:")
            
            browser.close()
            return organo, asunto, expediente
        except Exception as e:
            if browser: browser.close()
            return f"Error: {str(e)}", "N/A", "N/A"

# --- INTERFAZ ---

st.title("⚖️ LegalHub Monitor")
menu = st.sidebar.selectbox("Menú", ["Carga de Acuses", "Monitor de Estrados"])

if menu == "Carga de Acuses":
    st.header("📂 Carga de Archivos")
    # (Aquí va tu código de carga de PDF que ya funcionaba)
    st.info("Sube tus archivos para integrarlos a la matriz.")

if menu == "Monitor de Estrados":
    st.header("🔍 Monitoreo de Folios Pendientes")
    
    if st.button("🚀 Iniciar Monitoreo Diario", type="primary"):
        try:
            with st.status("Ejecutando proceso...", expanded=True) as status:
                st.write("🔌 Conectando con Google Sheets...")
                ws = conectar_sheets()
                df = pd.DataFrame(ws.get_all_records())
                
                st.write(f"📊 Matriz leída. Total de registros: {len(df)}")
                
                # FILTRO CRÍTICO: ¿Qué vamos a procesar?
                pendientes = df[(df['Estatus'] == 'Pendiente') | (df['Órgano Jurisdiccional'] == 'Sin asignar')]
                st.write(f"🔎 Registros pendientes encontrados: {len(pendientes)}")
                
                if pendientes.empty:
                    st.warning("No hay folios que requieran revisión hoy.")
                
                for idx, row in pendientes.iterrows():
                    folio = str(row['Folio'])
                    st.write(f"🤖 Consultando PJF para: **{folio}**...")
                    
                    organo, asunto, exp = consultar_pjf(folio)
                    
                    fila_excel = idx + 2 # +2 por encabezado y base 0 de pandas
                    
                    # Lógica de guardado
                    if organo not in ["Sin asignar", "Aún en fila PJF", "N/A"] and organo != row['Órgano Jurisdiccional']:
                        ws.update_cell(fila_excel, 5, organo)
                        st.success(f"✅ Juzgado detectado para {folio}")
                    
                    if exp not in ["Sin asignar", "N/A"] and exp != row['Número de Expediente']:
                        ws.update_cell(fila_excel, 6, exp)
                        st.success(f"✅ Expediente detectado para {folio}")
                    
                    if organo != "Sin asignar" and organo != "Aún en fila PJF" and exp != "Sin asignar":
                        ws.update_cell(fila_excel, 7, "Asignado")
                        enviar_telegram(f"🚨 ASIGNADO\n👤 {row['Promovente']}\n🏛️ {organo}\n📁 Exp: {exp}")
                    
                status.update(label="Monitoreo finalizado", state="complete", expanded=False)
                st.balloons()
        except Exception as e:
            st.error(f"Fallo en el motor: {e}")
