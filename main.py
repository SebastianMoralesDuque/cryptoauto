import requests
import json
import time
import os
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Configuración desde variables de entorno ---
JSON_FILE = "solana_tokens.json"
PROCESSED_TOKENS_FILE = "processed_tokens.json"

API_KEY_COINGECKO = os.environ.get("API_KEY_COINGECKO", "")
API_KEY_GEMINI = os.environ.get("API_KEY_GEMINI", "")
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# Lista de destinatarios separados por coma en el ENV
TO_EMAILS = os.environ.get("TO_EMAILS", "cheviotin200@gmail.com").split(",")

# URLs de las APIs
URL_COINGECKO = "https://api.coingecko.com/api/v3/onchain/tokens/info_recently_updated"
URL_GEMINI = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY_GEMINI}"
HEADERS = {
    "accept": "application/json",
    "x-cg-demo-api-key": API_KEY_COINGECKO
}

# Otros parámetros
GT_SCORE_THRESHOLD = 60.0
MAX_TOKENS_PER_CHECK = 100

# --- Configuración de Email ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- Carga de datos ---
if Path(JSON_FILE).exists():
    try:
        with open(JSON_FILE, "r", encoding='utf-8') as f:
            saved_tokens = json.load(f)
    except json.JSONDecodeError:
        saved_tokens = []
else:
    saved_tokens = []

saved_ids = {token["id"] for token in saved_tokens}

if Path(PROCESSED_TOKENS_FILE).exists():
    try:
        with open(PROCESSED_TOKENS_FILE, "r", encoding='utf-8') as f:
            processed_tokens_data = json.load(f)
    except json.JSONDecodeError:
        processed_tokens_data = {}
else:
    processed_tokens_data = {}

# --- Funciones auxiliares ---
def save_tokens(tokens_to_save):
    if not tokens_to_save:
        return
    saved_tokens.extend(tokens_to_save)
    with open(JSON_FILE, "w", encoding='utf-8') as f:
        json.dump(saved_tokens, f, indent=4, ensure_ascii=False)
    print(f"Guardados {len(tokens_to_save)} tokens nuevos en {JSON_FILE}.")

def save_processed_tokens():
    with open(PROCESSED_TOKENS_FILE, "w", encoding='utf-8') as f:
        json.dump(processed_tokens_data, f, indent=4, ensure_ascii=False)

def send_email(token_info, ai_analysis):
    """Envía un correo con la info del token a múltiples destinatarios."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = ", ".join(TO_EMAILS)
        msg['Subject'] = f"Nuevo Token Potencialmente Interesante: {token_info['attributes']['name']} ({token_info['attributes']['symbol']})"

        body = f"""
        Se ha detectado un nuevo token con un GT Score superior a {GT_SCORE_THRESHOLD}%.

        Información del Token:
        - Nombre: {token_info['attributes']['name']}
        - Símbolo: {token_info['attributes']['symbol']}
        - ID: {token_info['id']}
        - Dirección: {token_info['attributes']['address']}
        - GT Score: {token_info['attributes']['gt_score']}
        - Descripción: {token_info['attributes']['description']}
        - Sitio Web: {token_info['attributes'].get('websites', ['N/A'])[0] if token_info['attributes'].get('websites') else 'N/A'}
        - Twitter: @{token_info['attributes'].get('twitter_handle', 'N/A')}

        Análisis de IA:
        {ai_analysis}

        ---
        Este correo fue generado automáticamente por el script de monitoreo.
        """
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, TO_EMAILS, text)
        server.quit()
        print(f"Correo enviado para el token {token_info['id']}")
    except Exception as e:
        print(f"Error al enviar correo para {token_info['id']}: {e}")

def analyze_with_ai(token_info):
    prompt = f"""
    Eres un analista de criptomonedas experto. Analiza el siguiente token de criptomoneda y proporciona una evaluación breve, directa y profesional.

    Información del Token:
    - Nombre: {token_info['attributes']['name']}
    - Símbolo: {token_info['attributes']['symbol']}
    - Descripción: {token_info['attributes']['description']}
    - Sitio Web: {token_info['attributes'].get('websites', ['N/A'])[0] if token_info['attributes'].get('websites') else 'N/A'}
    - Twitter: @{token_info['attributes'].get('twitter_handle', 'N/A')}
    - GT Score: {token_info['attributes']['gt_score']}

    Basándote únicamente en la información proporcionada, ¿cuál es tu evaluación general del proyecto?
    """
    
    headers_gemini = {"Content-Type": "application/json"}
    data_gemini = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        print(f"--- Solicitando análisis a Gemini para {token_info['id']} ---")
        response = requests.post(URL_GEMINI, headers=headers_gemini, data=json.dumps(data_gemini))
        response.raise_for_status()
        
        result_data = response.json()
        ai_analysis = result_data['candidates'][0]['content']['parts'][0]['text']
        print(f"Análisis de Gemini:\n{ai_analysis}\n")
        
        return ai_analysis
    except Exception as e:
        print(f"Error durante análisis con Gemini: {e}")
        return "Análisis no disponible."

def fetch_new_tokens():
    print("Revisando nuevos tokens Solana...")
    try:
        response = requests.get(URL_COINGECKO, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error al obtener datos: {response.status_code} - {response.text}")
            return [], []

        data = response.json().get("data", [])
        
        solana_tokens = []
        high_score_tokens = []
        newly_saved_count = 0

        for token in data:
            network_id = token.get("relationships", {}).get("network", {}).get("data", {}).get("id")
            if network_id != "solana":
                continue

            token_id = token["id"]
            if token_id in saved_ids:
                continue

            if newly_saved_count >= MAX_TOKENS_PER_CHECK:
                 print(f"Límite de {MAX_TOKENS_PER_CHECK} nuevos tokens alcanzado.")
                 break

            solana_tokens.append(token)
            saved_ids.add(token_id)
            newly_saved_count += 1
           
            gt_score = token.get("attributes", {}).get("gt_score", 0)
            if gt_score is not None and gt_score > GT_SCORE_THRESHOLD:
                 if token_id not in processed_tokens_data:
                     high_score_tokens.append(token)

        return solana_tokens, high_score_tokens
    except Exception as e:
        print(f"Excepción al obtener tokens: {e}")
        return [], []

# --- Ejecución Única ---
def main():
    new_tokens, high_score_tokens = fetch_new_tokens()
    save_tokens(new_tokens)

    for token in high_score_tokens:
        token_id = token["id"]
        print(f"\n--- Procesando token con alto puntaje: {token_id} ---")
       
        ai_analysis_result = analyze_with_ai(token)
        send_email(token, ai_analysis_result)
       
        processed_tokens_data[token_id] = {
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "token_info": token,
            "ai_analysis": ai_analysis_result
        }
        save_processed_tokens()
        print(f"Token {token_id} marcado como procesado.\n")

if __name__ == "__main__":
    main()
