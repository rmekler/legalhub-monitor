import streamlit as st
import pandas as pd
from pypdf import PdfReader
import re
import gspread
from playwright.sync_api import sync_playwright
import time
import os
import json
from google.oauth2 import service_account

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
        # --- EL AJUSTE ESTÁ EN ESTA LÍNEA ---
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu"
            ]
        )
        # ------------------------------------
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # URL proporcionada para la consulta
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda")
            
            # Ingresar el folio (Ajustar selectores según el portal)
            page.fill("input#txtFolio", folio) 
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
