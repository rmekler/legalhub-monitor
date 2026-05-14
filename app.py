import streamlit as st
import pandas as pd
from pypdf import PdfReader
import re
import gspread
from playwright.sync_api import sync_playwright
import time
import os

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
    # Usa los secretos configurados en Streamlit Cloud
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    # Cambia esto por el nombre exacto de tu Google Sheet
    sh = gc.open("Matriz Estrados") 
    return sh.get_worksheet(0)

# --- LÓGICA DE PLAYWRIGHT (PJF) ---
def consultar_pjf(folio):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # URL proporcionada para la consulta
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda")
            
            # Ingresar el folio (Ajustar selectores según el portal)
            page.fill("input#txtFolio", folio) # Selector de ejemplo
            page.click("button#btnConsultar")
            time.sleep(3) # Espera a que cargue la info
            
            # Extraer datos y tomar captura
            path_img = f"captura_{folio.replace('/', '_')}.png"
            page.screenshot(path=path_img)
            
            # Lógica para extraer Órgano y Expediente
            organo = page.inner_text("#lblOrgano") if page.query_selector("#lblOrgano") else "Sin asignar"
            expediente = page.inner_text("#lblExpediente") if page.query_selector("#lblExpediente") else "Sin asignar"
            
            browser.close()
            return organo, expediente, path_img
        except Exception as e:
            browser.close()
            return f"Error: {str(e)}", "N/A", None

# --- INTERFAZ ---
st.sidebar.title("LegalHub Navigator")
menu = st.sidebar.radio("Ir a:", ["Carga de Acuses", "Monitor de Estrados"])

if menu == "Carga de Acuses":
    st.header("📂 Carga de nuevos expedientes")
    files = st.file_uploader("Sube los acuses en PDF", accept_multiple_files=True, type=['pdf'])
    
    if files:
        nuevos_datos = []
        for f in files:
            reader = PdfReader(f)
            texto = reader.pages[0].extract_text()
            folio = re.search(r'\d{8}/\d{4}', texto).group(0) if re.search(r'\d{8}/\d{4}', texto) else "No encontrado"
            nuevos_datos.append({"Folio": folio, "Estatus": "Pendiente"})
        
        st.write("Datos extraídos:", pd.DataFrame(nuevos_datos))
        if st.button("Guardar en Google Sheets"):
            ws = conectar_sheets()
            for d in nuevos_datos:
                ws.append_row([d['Folio'], "", "", "", "Sin asignar", "Sin asignar", "Pendiente"])
            st.success("Registros añadidos a la Matriz.")

elif menu == "Monitor de Estrados":
    st.header("⚖️ Seguimiento en tiempo real")
    if st.button("🚀 Iniciar Monitoreo Diario"):
        ws = conectar_sheets()
        datos = pd.DataFrame(ws.get_all_records())
        
        for index, row in datos.iterrows():
            if row['Estatus'] == "Pendiente":
                st.write(f"Consultando Folio: {row['Folio']}...")
                organo, exp, img = consultar_pjf(row['Folio'])
                
                # Actualizar el Sheet si hubo cambios
                if exp != "Sin asignar":
                    # (Lógica para actualizar celda en gspread)
                    st.success(f"¡Asignación encontrada para {row['Folio']}!")
                    # Aquí enviarías a Telegram usando st.secrets["TELEGRAM_TOKEN"]
