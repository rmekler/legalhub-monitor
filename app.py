import streamlit as st
import pandas as pd
import re
import json
import gspread
import requests
import os
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfReader
from google.oauth2 import service_account

# INSTALACIÓN AUTOMÁTICA DEL NAVEGADOR
# Cambiamos 'adminuser' por 'appuser' que es la ruta real que vemos en tus logs
if not os.path.exists("/home/appuser/.cache/ms-playwright"):
    with st.spinner("Configurando navegador por primera vez..."):
        os.system("playwright install chromium")
# --- FUNCIONES DE APOYO ---

def enviar_telegram(mensaje):
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensaje}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"⚠️ Error Telegram: {e}")

def conectar_sheets():
    # Usamos la lógica de Mini Nimbus que ya tienes probada
    cred_dict = json.loads(st.secrets["GOOGLE_CREDS"])
    creds_sheets = service_account.Credentials.from_service_account_info(
        cred_dict, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds_sheets)
    # Tu ID de Matriz Estrados
    return client.open_by_key('1ZP__a71alDwwjzVMF32LokjCzeS2AzilbEB48kVRjFk').sheet1

def generar_iniciales(nombre):
    if not nombre or nombre == "No encontrado": return ""
    excluir = ['de', 'del', 'la', 'las', 'el', 'los', 'y']
    palabras = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', nombre).split()
    return "".join([p[0].upper() for p in palabras if p.lower() not in excluir])

def consultar_pjf(folio):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--single-process"])
        page = browser.new_page()
        try:
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda")
            page.fill("input#numFolio", folio)
            page.click("button#btnBuscar")
            page.wait_for_timeout(4000) # Tiempo para carga de datos reales
            
            contenido = page.content().lower()
            if "no cuenta con" in contenido or "asignaci" in contenido:
                browser.close()
                return "Aún en fila PJF", "Sin asignar", "Sin asignar"

            # Extracción por etiquetas exactas
            def extraer(label):
                try:
                    elemento = page.locator(f"text={label}").first
                    return page.evaluate(f"el => el.parentElement.innerText.replace('{label}', '').strip()", elemento.element_handle())
                except: return "Sin asignar"

            organo = extraer("Órgano Jurisdiccional:")
            asunto = extraer("Tipo de Asunto:")
            expediente = extraer("Número de Expediente:")
            
            browser.close()
            return organo, asunto, expediente
        except Exception as e:
            if browser: browser.close()
            return f"Error: {str(e)}", "N/A", "N/A"

# --- INTERFAZ STREAMLIT ---

st.title("⚖️ LegalHub Monitor")
menu = st.sidebar.selectbox("Menú", ["Carga de Acuses", "Monitor de Estrados"])

if menu == "Carga de Acuses":
    st.header("📂 Carga de Acuses (PDF)")
    files = st.file_uploader("Sube los PDFs", accept_multiple_files=True, type=['pdf'])
    
    if files:
        datos_extraidos = []
        for f in files:
            reader = PdfReader(f)
            texto = reader.pages[0].extract_text()
            match_folio = re.search(r'\d{8}/\d{4}', texto)
            folio = match_folio.group(0) if match_folio else "No encontrado"
            
            # Buscador de nombre
            match_nom = re.search(r"(?i)(?:Promovente|Quejoso|Nombre)\s*:\s*([^\n]+)", texto)
            nombre = match_nom.group(1).strip() if match_nom else "No encontrado"
            
            datos_extraidos.append([folio, nombre, generar_iniciales(nombre), "Diario", "Sin asignar", "Sin asignar", "Pendiente"])
        
        if st.button("Guardar en Google Sheets"):
            ws = conectar_sheets()
            for fila in datos_extraidos:
                ws.append_row(fila)
            st.success("✅ Datos guardados.")

if menu == "Monitor de Estrados":
    st.header("🔍 Monitoreo Diario PJF")
    if st.button("🚀 Iniciar Monitoreo", type="primary"):
        ws = conectar_sheets()
        df = pd.DataFrame(ws.get_all_records())
        
        for idx, row in df.iterrows():
            if row['Estatus'] == "Pendiente" or row['Órgano Jurisdiccional'] == "Sin asignar":
                st.write(f"Revisando: {row['Folio']}...")
                organo, asunto, exp = consultar_pjf(row['Folio'])
                fila_excel = idx + 2
                
                # Actualización inteligente
                if organo not in ["Sin asignar", "Aún en fila PJF", "N/A"] and organo != row['Órgano Jurisdiccional']:
                    ws.update_cell(fila_excel, 5, organo)
                if exp not in ["Sin asignar", "N/A"] and exp != row['Número de Expediente']:
                    ws.update_cell(fila_excel, 6, exp)
                
                # Si ya tenemos los dos datos, finalizamos
                if organo != "Sin asignar" and organo != "Aún en fila PJF" and exp != "Sin asignar":
                    ws.update_cell(fila_excel, 7, "Asignado")
                    enviar_telegram(f"🚨 ASIGNADO\n👤 {row['Promovente']}\n🏛️ {organo}\n📁 Exp: {exp}")
                    st.success(f"¡Asignado! {row['Folio']}")
