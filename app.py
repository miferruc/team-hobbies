import streamlit as st
import pandas as pd
from pathlib import Path
from typing import List, Dict
import socket
import qrcode
from io import BytesIO
import os
import datetime

# NEW ▶ Supabase client
from supabase import create_client

# ───────────── Config ─────────────
DATA_FILE = Path("responses.csv")
MATERIE = [
    "Matematica Finanziaria", "Diritto Commerciale", "Diritto Pubblico", "Logistica", "EGI", "statistica"
]
HOBBIES = [
    "Astronomia","Ballo","Birdwatching","Calcio","Camping","Ciclismo","Cinema","Coding",
    "Collezionismo (monete, francobolli, ecc.)","Cucina","Disegno","Escursionismo","Fotografia",
    "Gaming","Giardinaggio","Lingue straniere","Lettura","Meditazione","Modellismo","Musica",
    "Nuoto","Origami","Palestra","Pesca","Pittura","Podcasting","Scacchi","Scrittura creativa",
    "Skateboard","Surf","Teatro","Trekking","Viaggi","Volontariato","Yoga"
]

# NEW ▶ Inizializza Supabase dal secrets
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ───────────── Session & Access Control ─────────────
# Inizializza la sessione utente e aggiunge controllo d'accesso.

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None  # struttura base: {"id": ..., "email": ...}

def require_login():
    """
    Verifica che l'utente sia loggato.
    Se non lo è, blocca l'esecuzione dell'app e mostra un messaggio.
    """
    if st.session_state.auth_user is None:
        st.warning("🔒 Devi effettuare il login per accedere all'app.")
        st.stop()  # Interrompe tutto ciò che segue

# ───────────── Step 1 Check ─────────────
st.divider()
st.subheader("✅ Step 1: Login Lock Check")

# Se l'utente è loggato, mostra messaggio di conferma
if st.session_state.auth_user:
    st.success("🔓 Accesso consentito: l'utente è loggato correttamente.")
else:
    st.warning("🚫 Accesso bloccato: devi eseguire il login per continuare.")

# ───────────── Step 2: Profilo Utente ─────────────
def load_profile():
    """Carica o crea il profilo dell'utente loggato su Supabase."""
    user = st.session_state.auth_user
    if not user:
        return None

    try:
        # Verifica se esiste un profilo per questo utente
        prof = supabase.table("profiles").select("*").eq("id", user["id"]).execute()
        data = prof.data

        # Se non esiste, crealo automaticamente
        if not data:
            supabase.table("profiles").insert({
                "id": user["id"],
                "email": user["email"],
                "nome": ""
            }).execute()
            return None  # Torna None per far partire il setup

        # Se esiste, prendi il primo record
        profile = data[0]
        required = ["nome"]
        if any(not profile.get(field) for field in required):
            return None
        return profile

    except Exception as e:
        st.error(f"Errore nel caricamento/creazione del profilo: {e}")
        return None

def setup_profilo():
    """Mostra il form di setup per i nuovi utenti."""
    st.subheader("🧭 Setup del tuo profilo")
    st.info("Completa il tuo profilo per accedere all'applicazione.")

    nome = st.text_input("Il tuo nome completo:")
    if st.button("Salva profilo"):
        if nome:
            try:
                supabase.table("profiles").update({"nome": nome}).eq("id", st.session_state.auth_user["id"]).execute()
                st.success("Profilo completato ✅")
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel salvataggio del profilo: {e}")
        else:
            st.warning("Inserisci un nome prima di salvare.")




# ───────────── Utils: storage CSV condiviso ─────────────
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

# ───────────── Utils: IP/QR/Link ─────────────
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
    try:
        url = st.secrets.get("PUBLIC_URL", "").strip()
    except Exception:
        url = ""
    if url:
        return url
    local_ip = get_local_ip()
    port = os.environ.get("PORT", 8501)
    return f"http://{local_ip}:{port}"

# ───────────── Utils: Team logic ─────────────
def hobbies_in_common(members: pd.DataFrame) -> str:
    sets = [set(h.split(",")) for h in members["Hobbies"] if isinstance(h, str) and h]
    return ", ".join(sorted(set.intersection(*sets))) if sets else "Nessuno"

def find_organizer(members: pd.DataFrame):
    """Organizzatore = chi ha fatto materie che gli altri devono ancora fare."""
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
    teams_adjusted, last_team = {}, None
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

# ───────────── UI: Sidebar Login/Signup ─────────────
# ───────────── Sidebar: Auth Supabase ─────────────
with st.sidebar:
    st.subheader("🔐 Accesso")

    if supabase is None:
        st.info("Supabase non configurato (manca SUPABASE_URL/KEY nei secrets).")
    else:
        logged = st.session_state.get("auth_user")

        if not logged:
            tab_login, tab_signup = st.tabs(["Entra", "Registrati"])

            # ------- ENTRA -------
            with tab_login:
                email = st.text_input("Email", key="auth_login_email")
                pwd = st.text_input("Password", type="password", key="auth_login_pwd")
                if st.button("Accedi"):
                    try:
                        res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                        st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
                        # assicuro il profilo esista
                        try:
                            prof = supabase.table("profiles").select("id").eq("id", res.user.id).single().execute()
                            if not getattr(prof, "data", None):
                                supabase.table("profiles").insert({
                                    "id": res.user.id, "email": res.user.email, "nome": ""
                                }).execute()
                        except Exception:
                            pass
                        st.success(f"Benvenuto {res.user.email} 👋")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Login fallito: {e}")

            # ------- REGISTRATI -------
            with tab_signup:
                s_email = st.text_input("Email", key="auth_signup_email")
                s_pwd   = st.text_input("Password", type="password", key="auth_signup_pwd")
                s_nome  = st.text_input("Nome (profilo)", key="auth_signup_nome")
                if st.button("Crea account"):
                    try:
                        # 1) crea utente (se conferma email è ON, invia mail)
                        supabase.auth.sign_up({"email": s_email, "password": s_pwd})

                        # 2) prova login subito (funziona se conferma email è OFF)
                        try:
                            login = supabase.auth.sign_in_with_password({"email": s_email, "password": s_pwd})
                        except Exception as e2:
                            login = None
                            # Se conferma email è ON, tipicamente qui ritorna "Email not confirmed"
                            st.info("📧 Controlla l'email per confermare l'account, poi fai **Entra**.")
                        
                        # 3) se login riuscito, crea/aggiorna profilo e logga
                        if login and getattr(login, "user", None):
                            try:
                                supabase.table("profiles").upsert({
                                    "id": login.user.id, "email": login.user.email, "nome": s_nome
                                }).execute()
                            except Exception:
                                pass
                            st.session_state.auth_user = {"id": login.user.id, "email": login.user.email}
                            st.success("Account creato! Sei dentro ✅")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Registrazione fallita: {e}")
        else:
            me = st.session_state.auth_user
            st.success(f"Connesso come: {me['email']}")
            if st.button("Esci"):
                try:
                    supabase.auth.sign_out()
                except Exception:
                    pass
                st.session_state.auth_user = None
                st.rerun()

# ───────────── Step 2 Check ─────────────
require_login()  # blocca chi non è loggato

profile_data = load_profile()

if profile_data is None:
    st.warning("🧩 Profilo incompleto: vai al setup.")
    setup_profilo()
else:
    st.success(f"👋 Benvenuto {profile_data['nome']}! Il tuo profilo è completo.")

# ───────────── UI principale ─────────────
st.title("Mini App – Team Hobbies + Materie")

# Autofill del Nome dal profilo (se loggato)
default_name = ""
if supabase and st.session_state.auth_user:
    try:
        prof = supabase.table("profiles").select("nome").eq("id", st.session_state.auth_user["id"]).single().execute()
        default_name = (prof.data or {}).get("nome") or ""
    except Exception:
        pass

# Input utente
name = st.text_input("Nome", value=default_name)
hobbies = st.multiselect("Seleziona i tuoi hobby:", HOBBIES)
fatte = st.multiselect("Materie fatte:", MATERIE)
dafare = st.multiselect("Materie da fare:", MATERIE)

if st.button("Invia"):
    if name and hobbies:
        save_row(name, hobbies, fatte, dafare)
        st.success("Risposta salvata ✅")
    else:
        st.error("Inserisci nome + almeno un hobby.")

# Partecipanti
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

        csv = df_out.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Scarica CSV dei team", data=csv, file_name="team_generati.csv", mime="text/csv")

# QR per invitare altri (Cloud usa PUBLIC_URL; locale usa IP)
st.subheader("📱 QR Code per invitare amici")
link = get_public_link()
qr = generate_qr_code(link)
st.image(qr, caption=link)
