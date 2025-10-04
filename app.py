import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List, Dict
import socket
import qrcode
from io import BytesIO
import os
import datetime

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

# ----------------- Utils: storage CSV condiviso -----------------
def read_data() -> pd.DataFrame:
    if DATA_FILE.exists():
        return pd.read_csv(DATA_FILE)
    return pd.DataFrame(columns=["Nome","Hobbies","Materie_Fatte","Materie_DaFare"])

def save_row(name: str, hobbies: List[str], fatte: List[str], dafare: List[str]):
    df_new = pd.DataFrame([[name, ",".join(hobbies), ",".join(fatte), ",".join(dafare)]],
                          columns=["Nome","Hobbies","Materie_Fatte","Materie_DaFare"])
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE)
        df = pd.concat([df, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(DATA_FILE, index=False)

# ----------------- Utils: IP/QR/Link -----------------
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

def get_public_link() -> str:
    # Se su Streamlit Cloud ho il secret PUBLIC_URL, uso quello
    try:
        url = st.secrets.get("PUBLIC_URL", "").strip()
    except Exception:
        url = ""
    if url:
        return url
    # fallback in locale
    local_ip = get_local_ip()
    port = os.environ.get("PORT", 8501)
    return f"http://{local_ip}:{port}"

# ----------------- Utils: Team logic -----------------
def hobbies_in_common(members: pd.DataFrame) -> str:
    sets = [set(h.split(",")) for h in members["Hobbies"] if isinstance(h, str) and h]
    return ", ".join(sorted(set.intersection(*sets))) if sets else "Nessuno"

def find_organizer(members: pd.DataFrame):
    """
    Organizzatore = chi ha fatto materie che gli altri devono ancora fare.
    Ritorna (nome_organizzatore, 'materie spiegate').
    """
    for _, row in members.iterrows():
        fatte = set([m for m in (row["Materie_Fatte"] or "").split(",") if m])
        others = members[members["Nome"] != row["Nome"]]
        others_dafare = set([m for m in ",".join(others["Materie_DaFare"].dropna()).split(",") if m]) if not others.empty else set()
        diff = {m for m in fatte if m in others_dafare}
        if diff:
            return row["Nome"], ", ".join(sorted(diff))
    return "Nessuno", "—"

def build_similar(df: pd.DataFrame, team_size=3) -> Dict[str, List[str]]:
    teams, idx = {}, 1
    df2 = df.copy()
    df2["Primario"] = df2["Hobbies"].apply(lambda x: x.split(",")[0] if isinstance(x, str) and x else "Varie")
    for hobby, group in df2.groupby("Primario"):
        members = group["Nome"].tolist()
        for i in range(0, len(members), team_size):
            teams[f"Team {idx} ({hobby})"] = members[i:i+team_size]
            idx += 1
    return teams

def build_diverse(df: pd.DataFrame, team_size=3) -> Dict[str, List[str]]:
    teams, idx = {}, 1
    for materia in MATERIE:
        cluster = df[
            df["Materie_Fatte"].fillna("").str.contains(materia) |
            df["Materie_DaFare"].fillna("").str.contains(materia)
        ]
        if not cluster.empty:
            members = cluster["Nome"].tolist()
            for i in range(0, len(members), team_size):
                teams[f"Team {idx} ({materia})"] = members[i:i+team_size]
                idx += 1
    return teams

def adjust_teams(teams: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Evita team da 1; se resta un solo team da 2, mostra acknowledge."""
    if not teams:
        return teams
    teams_adjusted = {}
    last_team = None
    for tname, members in teams.items():
        if len(members) == 1:
            if last_team:
                teams_adjusted[last_team].extend(members)
            else:
                teams_adjusted[tname] = members
        else:
            teams_adjusted[tname] = members
            last_team = tname
    if len(teams_adjusted) == 1 and len(list(teams_adjusted.values())[0]) == 2:
        st.warning("⚠️ Non ci sono matching forti. Vuoi comunque formare un team da 2 persone?")
    return teams_adjusted

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
st.dataframe(data, use_container_width=True)

# Azioni: salva sessione / reset
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
            DATA_FILE.unlink()
        st.success("Lista partecipanti pulita ✅")

# Team
st.subheader("👥 Crea i Team")
mode = st.radio("Regola di unione:", ["Simili (stesso hobby + materie)", "Diversi (materie in comune)"])
size = st.slider("Dimensione team", 2, 6, 3)

if st.button("Genera Team"):
    if data.empty:
        st.warning("Nessun partecipante.")
    else:
        teams = build_similar(data, size) if mode.startswith("Simili") else build_diverse(data, size)
        teams = adjust_teams(teams)

        rows = []
        for team_name, members in teams.items():
            members_df = data[data["Nome"].isin(members)]
            common_hobbies = hobbies_in_common(members_df)
            organizer, materia_spiegata = find_organizer(members_df)
            rows.append({
                "Team": team_name,
                "Membri": ", ".join(members),
                "Hobby comuni": common_hobbies,
                "Organizzatore": organizer,
                "Materia spiegata": materia_spiegata
            })

        df_out = pd.DataFrame(rows)
        st.dataframe(df_out, use_container_width=True)

        # download CSV dei team
        csv = df_out.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Scarica CSV dei team", data=csv, file_name="team_generati.csv", mime="text/csv")

# QR per invitare altri (Cloud usa PUBLIC_URL; locale usa IP)
st.subheader("📱 QR Code per invitare amici")
link = get_public_link()
qr = generate_qr_code(link)
st.image(qr, caption=link)
