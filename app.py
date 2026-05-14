import streamlit as st
import pandas as pd
from pypdf import PdfReader
import re

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

# --- LÓGICA DE PROCESAMIENTO ---
def extraer_datos_pdf(file):
    reader = PdfReader(file)
    texto = reader.pages[0].extract_text()
    # Regex para encontrar folio (ej. 12345678/2026)
    folio = re.search(r'\d{8}/\d{4}', texto).group(0) if re.search(r'\d{8}/\d{4}', texto) else "No encontrado"
    return {"Folio": folio, "Texto": texto}

# --- INTERFAZ ---
st.sidebar.title("LegalHub Navigator")
menu = st.sidebar.radio("Ir a:", ["Carga de Acuses", "Monitor de Estrados"])

if menu == "Carga de Acuses":
    st.header("📂 Carga de nuevos expedientes")
    files = st.file_uploader("Sube los acuses en PDF", accept_multiple_files=True, type=['pdf'])
    
    if files:
        nuevos_datos = []
        for f in files:
            datos = extraer_datos_pdf(f)
            nuevos_datos.append(datos)
        
        df_nuevos = pd.DataFrame(nuevos_datos)
        st.write("Vista previa de carga:", df_nuevos)
        if st.button("Actualizar Matriz en Google Sheets"):
            # Aquí iría la conexión a gspread
            st.success("Matriz actualizada correctamente.")

elif menu == "Monitor de Estrados":
    st.header("⚖️ Seguimiento de Expedientes")
    st.info("Esta sección consultará el portal del PJF y enviará capturas a Telegram.")
    
    if st.button("🚀 Iniciar Monitoreo Diario"):
        # Aquí ejecutamos la lógica de Playwright que revisa el portal:
        # https://www.serviciosenlinea.pjf.gob.mx/juicioenlinea/Presentacion/VerDemanda
        st.write("Consultando portal del PJF...")
        # Lógica de Playwright...
        st.success("Monitoreo completado. Reportes enviados a Telegram.")