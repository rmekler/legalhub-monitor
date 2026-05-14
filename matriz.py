import pandas as pd

# Función para obtener iniciales limpias
def obtener_iniciales(nombre):
    if not nombre or pd.isna(nombre):
        return "N/A"
    # Filtramos palabras cortas como 'de', 'la', 'del' para iniciales más limpias
    excluir = ['de', 'la', 'del', 'las', 'los', 'y']
    partes = [p for p in nombre.split() if p.lower() not in excluir]
    return "".join([p[0].upper() for p in partes])

# 1. Simulación de los datos extraídos de tus 11 acuses
# (Aquí es donde conectarías el resultado de tu OCR)
datos_acuses = [
    {"folio": "12488284/2026", "promovente": "Miguel Rafael Mekler Granillo", "tipo": "8-folios"},
    # ... los otros 10 registros irían aquí
]

# 2. Creación de la Matriz
df = pd.DataFrame(datos_acuses)
df['iniciales'] = df['promovente'].apply(obtener_iniciales)

# Columnas de seguimiento (inicialmente vacías)
df['organo_asignado'] = "Sin asignar"
df['expediente_asignado'] = "Sin asignar"
df['ultima_actualizacion'] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

# 3. Función para preparar la notificación de Telegram
def preparar_notificacion(row):
    """Genera el mensaje según tu regla: solo Folio e Iniciales"""
    mensaje = f"🔔 Actualización detectada:\n"
    mensaje += f"📄 Folio: {row['folio']}\n"
    mensaje += f"👤 Promovente: {row['iniciales']}\n"
    
    if row['tipo'] == "8-folios":
        mensaje += f"⚖️ Órgano: {row['organo_asignado']}\n"
    
    mensaje += f"📂 Exp: {row['expediente_asignado']}"
    return mensaje

# Ejemplo de cómo se vería el mensaje para Telegram
for index, row in df.head(1).iterrows():
    print("--- Simulación de Telegram ---")
    print(preparar_notificacion(row))