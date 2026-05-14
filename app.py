import streamlit as st
import pandas as pd
import re
import json
import gspread
import requests
import time
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfReader
from google.oauth2 import service_account

# --- DESCARGA AUTOMÁTICA DEL NAVEGADOR INVISIBLE ---
os.system("playwright install chromium")

def enviar_telegram(mensaje):
    try:
        token = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": mensaje}
        requests.post(url, json=payload)
    except Exception as e:
        st.error(f"⚠️ Error Telegram: {e}")
        
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
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--single-process"])
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto("https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda")
            page.fill("input#numFolio", folio)
            page.click("button#btnBuscar")
            
            # Esperamos a que la página reaccione (3 seg de cortesía)
            page.wait_for_timeout(3000)
            
            # Verificamos si salió el mensaje de "Aún no cuenta con asignación"
            contenido = page.content().lower()
            if "asignaci" in contenido and "no cuenta" in contenido:
                browser.close()
                return "Aún en fila PJF", "Sin asignar", "Sin asignar", None

            # Si pasó el filtro, extraemos con selectores de texto (más robustos)
            def extraer(label):
                try:
                    # Buscamos el texto que está justo después de la etiqueta
                    elemento = page.locator(f"text={label}").first
                    # El dato suele estar en el elemento siguiente o dentro del mismo contenedor
                    return page.evaluate(f"el => el.parentElement.innerText.replace('{label}', '').strip()", 
                                       elemento.element_handle())
                except:
                    return "Sin asignar"

            organo = extraer("Órgano Jurisdiccional:")
            asunto = extraer("Tipo de Asunto:")
            expediente = extraer("Número de Expediente:")
            
            path_img = f"captura_{folio.replace('/', '_')}.png"
            page.screenshot(path=path_img)
            
            browser.close()
            return organo, asunto, expediente, path_img
        except Exception as e:
            if browser: browser.close()
            return f"Error: {str(e)}", "N/A", "N/A", None
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
        datos = pd.DataFrame(ws.get_all_records())
        
        if datos.empty:
            st.info("No hay datos en la matriz.")
        else:
            cambios_totales = 0
            for index, row in datos.iterrows():
                # Revisamos si falta Órgano o Expediente
                if row['Estatus'] == "Pendiente" or row['Órgano Jurisdiccional'] == "Sin asignar" or row['Número de Expediente'] == "Sin asignar":
                    st.write(f"🔍 Revisando: {row['Folio']}...")
                    
                    organo, asunto, exp, img = consultar_pjf(row['Folio'])
                    fila = index + 2
                    actualizo_algo = False
                    
                    # Actualizar Órgano (Col 5)
                    if organo not in ["Sin asignar", "Aún en fila PJF", "N/A"] and organo != row['Órgano Jurisdiccional']:
                        ws.update_cell(fila, 5, organo)
                        actualizo_algo = True
                    
                    # Actualizar Expediente (Col 6)
                    if exp not in ["Sin asignar", "N/A"] and exp != row['Número de Expediente']:
                        ws.update_cell(fila, 6, exp)
                        actualizo_algo = True
                    
                    # Determinar si ya terminamos con este folio
                    # Solo se marca "Asignado" si ya tenemos los dos datos clave
                    if organo != "Sin asignar" and organo != "Aún en fila PJF" and exp != "Sin asignar":
                        ws.update_cell(fila, 7, "Asignado")
                    
                    if actualizo_algo:
                        st.success(f"✅ ¡Nuevos datos para {row['Folio']}!")
                        enviar_telegram(f"🚨 ACTUALIZACIÓN PJF\n👤 {row['Promovente']}\n🏛️ {organo}\n📁 Exp: {exp}")
                        cambios_totales += 1
                    elif organo == "Aún en fila PJF":
                        st.warning(f"⏳ {row['Folio']} sigue en fila.")
            
            if cambios_totales > 0:
                st.balloons()
            st.info("Terminó la revisión de la matriz.")
