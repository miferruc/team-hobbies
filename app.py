import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List, Dict
import socket
import qrcode
from io import BytesIO


# ----------------- Config -----------------
DATA_FILE = Path("responses.csv")
MATERIE = [
    "Matematica Finanziaria",
    "Diritto Commerciale",
    "Diritto Pubblico",
    "Logistica",
    "EGI"
]
HOBBIES = [
    "Astronomia","Ballo","Birdwatching","Calcio","Camping","Ciclismo","Cinema","Coding",
    "Collezionismo (monete, francobolli, ecc.)","Cucina","Disegno","Escursionismo","Fotografia",
    "Gaming","Giardinaggio","Lingue straniere","Lettura","Meditazione","Modellismo","Musica",
    "Nuoto","Origami","Palestra","Pesca","Pittura","Podcasting","Scacchi","Scrittura creativa",
    "Skateboard","Surf","Teatro","Trekking","Viaggi","Volontariato","Yoga"
]

# ----------------- Utils -----------------
def read_data() -> pd.DataFrame:
    if DATA_FILE.exists():
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Nome","Hobbies","Materie_Fatte","Materie_DaFare"])

def save_row(name: str, hobbies: List[str], fatte: List[str], dafare: List[str]):
    df_new = pd.DataFrame([[
        name,
        ",".join(hobbies),
        ",".join(fatte),
        ",".join(dafare)
    ]], columns=["Nome","Hobbies","Materie_Fatte","Materie_DaFare"])

    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df = pd.concat([df, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_csv(DATA_FILE, index=False)

def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def generate_qr_code(link: str):
    qr_img = qrcode.make(link)
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    return buf.getvalue()

# ----------------- UI -----------------
st.title("🎯 Mini App – Team Hobbies + Materie")

# Input utente
name = st.text_input("Nome")
hobbies = st.multiselect("Seleziona i tuoi hobby:", HOBBIES)
fatte = st.multiselect("Materie fatte:", MATERIE)
dafare = st.multiselect("Materie da fare:", MATERIE)

if st.button("Invia"):
    if name and hobbies:
        save_row(name, hobbies, fatte, dafare)
        st.success("Risposta salvata ✅")
    else:
        st.error("Inserisci nome + almeno un hobby.")

# Mostra partecipanti
st.subheader("📋 Partecipanti")
data = read_data()
st.dataframe(data)

import datetime

col1, col2 = st.columns(2)

with col1:
    if not data.empty:
        if st.button("💾 Salva sessione"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"groups_{timestamp}.csv"
            data.to_csv(filename, index=False)
            st.success(f"Sessione salvata come {filename}")

with col2:
    if st.button("🔄 Reset partecipanti"):
        if DATA_FILE.exists():
            DATA_FILE.unlink()   # elimina il file responses.csv
        st.session_state["data"] = pd.DataFrame(columns=["Nome","Hobbies","Materie_Fatte","Materie_DaFare"])
        st.success("Lista partecipanti pulita ✅")



# Sezione Team
st.subheader("👥 Crea i Team")
mode = st.radio("Regola di unione:", ["Simili (stesso hobby + materie)", "Diversi (materie in comune)"])
size = st.slider("Dimensione team", 2, 6, 3)

if st.button("Genera Team"):
    if data.empty:
        st.warning("Nessun partecipante.")
    else:
        # TODO: qui puoi aggiungere la logica dei team come prima
        st.write("👉 Qui andrà la logica aggiornata di generazione dei team")

# QR per invitare altri
st.subheader("📱 QR Code per invitare amici")
local_ip = get_local_ip()
port = 8501
link = f"http://{local_ip}:{port}"
qr = generate_qr_code(link)
st.image(qr, caption=link)

