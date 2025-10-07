import streamlit as st
from supabase import create_client
from pathlib import Path
import pandas as pd
from typing import List
import qrcode
from io import BytesIO

# ───────────── SUPABASE INIT ─────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

st.set_page_config(page_title="Syntia MVP", page_icon="🎓", layout="centered")

# ───────────── SESSION INIT ─────────────
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None  # {"id":..., "email":...}

def require_login():
    """Blocca l'app se l'utente non è autenticato"""
    if st.session_state.auth_user is None:
        st.warning("🔒 Devi effettuare il login per accedere all'app.")
        st.stop()

# ───────────── FUNZIONI PROFILO ─────────────
def load_profile():
    """Carica o crea il profilo utente su Supabase."""
    user = st.session_state.auth_user
    if not user:
        return None
    try:
        prof = supabase.table("profiles").select("*").eq("id", user["id"]).execute()
        data = prof.data
        if not data:
            supabase.table("profiles").insert({
                "id": user["id"],
                "email": user["email"],
                "nome": ""
            }).execute()
            return None
        profile = data[0]
                # Campi obbligatori per considerare il profilo completo
        required = [
            "nome",
            "corso",
            "materie_fatte",
            "materie_dafare",
            "hobby",
            "approccio",
            "obiettivi",
        ]

        # Se manca almeno uno di questi campi → profilo incompleto
        if any(
            not profile.get(f)
            or (isinstance(profile.get(f), list) and len(profile.get(f)) == 0)
            for f in required
        ):
            return None

        return profile
    except Exception as e:
        st.error(f"Errore nel caricamento/creazione profilo: {e}")
        return None

def setup_profilo():
    """Form completo per il setup profilo utente."""
    st.subheader("🧭 Setup del tuo profilo")
    st.info("Completa il tuo profilo per personalizzare i gruppi di studio.")

    # ───────────── DATI BASE ─────────────
    nome = st.text_input("Il tuo nome completo:")
    corso = st.selectbox("Corso di studi:", ["Economia"])  # altri corsi verranno aggiunti

    # ───────────── MATERIE ─────────────
    st.markdown("### 📘 Materie")
    materie_fatte = st.multiselect(
        "Materie già superate:",
        ["Economia Aziendale", "Statistica", "Diritto Privato", "Microeconomia", "Marketing"],
    )
    materie_dafare = st.multiselect(
        "Materie ancora da sostenere:",
        ["Finanza", "Econometria", "Gestione Aziendale", "Macroeconomia", "Comunicazione"],
    )

    # ───────────── HOBBY ─────────────
    st.markdown("### 🎨 Hobby e Interessi")
    hobby = st.multiselect(
        "Seleziona i tuoi hobby:",
        ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Cucina", "Arte", "Volontariato"],
    )

    # ───────────── APPROCCIO ─────────────
    st.markdown("### 🧠 Approccio allo studio")
    approccio = st.selectbox(
        "Come preferisci studiare?",
        [
            "In gruppo e con confronto",
            "Da solo, con concentrazione",
            "In modo pratico (esercizi, esempi)",
            "Analitico (teoria, approfondimento)",
        ],
    )

    # ───────────── OBIETTIVI ─────────────
    st.markdown("### 🎯 Obiettivi accademici")
    obiettivi = st.multiselect(
        "Cosa vuoi ottenere dallo studio universitario?",
        [
            "Passare gli esami a prescindere dal voto",
            "Raggiungere una media del 30",
            "Migliorare la comprensione delle materie",
            "Creare connessioni e fare gruppo",
            "Prepararmi per la carriera futura",
        ],
    )

    # ───────────── SALVATAGGIO DATI ─────────────
    if st.button("💾 Salva profilo completo"):
        if nome:
            try:
                supabase.table("profiles").update(
                    {
                        "nome": nome,
                        "corso": corso,
                        "materie_fatte": materie_fatte,
                        "materie_dafare": materie_dafare,
                        "hobby": hobby,
                        "approccio": approccio,
                        "obiettivi": obiettivi,
                    }
                ).eq("id", st.session_state.auth_user["id"]).execute()
                st.success("Profilo aggiornato con successo ✅")
                st.rerun()
            except Exception as e:
                st.error(f"Errore nel salvataggio del profilo: {e}")
        else:
            st.warning("Inserisci almeno il nome per continuare.")

def show_profilo_completo(profile):
    """Mostra un riepilogo del profilo utente salvato su Supabase."""
    st.subheader("📊 Il tuo profilo")
    st.markdown(f"**👤 Nome:** {profile.get('nome', '-')}")
    st.markdown(f"**🎓 Corso di studi:** {profile.get('corso', '-')}")
    st.markdown(f"**📘 Materie già fatte:** {', '.join(profile.get('materie_fatte', []) or ['-'])}")
    st.markdown(f"**🧮 Materie da fare:** {', '.join(profile.get('materie_dafare', []) or ['-'])}")
    st.markdown(f"**🎨 Hobby:** {', '.join(profile.get('hobby', []) or ['-'])}")
    st.markdown(f"**🧠 Approccio allo studio:** {profile.get('approccio', '-')}")
    st.markdown(f"**🎯 Obiettivi:** {', '.join(profile.get('obiettivi', []) or ['-'])}")

def dashboard_studente(profile):
    """Mostra la dashboard personale dello studente."""
    st.markdown("## 🧩 Dashboard Studente")

    # ───────────── MESSAGGIO BASE ─────────────
    st.info("💬 Partecipa a una lezione per creare il tuo team!")

    # ───────────── MINI STATS ─────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📚 Materie coperte", len(profile.get("materie_fatte", [])))
    with col2:
        st.metric("🎨 Hobby", len(profile.get("hobby", [])))
    with col3:
        st.metric("👥 Gruppi passati", 0)  # placeholder per ora

    st.divider()

    # ───────────── GRUPPI PASSATI ─────────────
    st.markdown("### 🗂️ I tuoi gruppi passati")
    gruppi = []  # verranno caricati in seguito da Supabase
    if gruppi:
        for g in gruppi:
            st.markdown(f"- **{g['nome_gruppo']}** ({g['materia']}) – {g['data']}")
    else:
        st.caption("Non hai ancora partecipato a nessun gruppo.")

    st.divider()

    # ───────────── MODIFICA PROFILO ─────────────
    st.markdown("### ✏️ Modifica profilo")
    if st.button("Apri setup profilo"):
        st.session_state["show_setup"] = True
        st.rerun()


# ───────────── FUNZIONI UTILI ─────────────
def get_public_link() -> str:
    """Restituisce il link pubblico dell'app"""
    return "https://team-hobbies.streamlit.app"

def generate_qr_code(link: str):
    """Genera un QR code a partire da un link"""
    img = qrcode.make(link)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ───────────── SIDEBAR LOGIN/REGISTRAZIONE ─────────────
with st.sidebar:
    st.subheader("🔐 Accesso")

    if st.session_state.auth_user is None:
        tab_login, tab_signup = st.tabs(["Entra", "Registrati"])

        # ---- LOGIN ----
        with tab_login:
            email = st.text_input("Email", key="login_email")
            pwd = st.text_input("Password", type="password", key="login_pwd")
            if st.button("Accedi"):
                try:
                    res = supabase.auth.sign_in_with_password(
                        {"email": email, "password": pwd}
                    )
                    st.session_state.auth_user = {
                        "id": res.user.id,
                        "email": res.user.email,
                    }
                    st.success(f"Benvenuto {res.user.email} 👋")
                    st.rerun()
                except Exception as e:
                    st.error(f"Login fallito: {e}")

        # ---- SIGNUP ----
        with tab_signup:
            email_s = st.text_input("Email", key="signup_email")
            pwd_s = st.text_input("Password", type="password", key="signup_pwd")
            if st.button("Registrati"):
                try:
                    res = supabase.auth.sign_up(
                        {"email": email_s, "password": pwd_s}
                    )
                    st.success("Registrazione completata! Esegui ora l'accesso 👇")
                except Exception as e:
                    st.error(f"Registrazione fallita: {e}")

    else:
        st.success(f"Connesso come {st.session_state.auth_user['email']}")
        if st.button("Esci"):
            supabase.auth.sign_out()
            st.session_state.auth_user = None
            st.rerun()

# ───────────── BLOCCO ACCESSO + CONTROLLO PROFILO ─────────────
require_login()

profile_data = load_profile()

# =====================================================
# 🌐 MENU DI NAVIGAZIONE
# =====================================================

st.sidebar.title("📚 Menu Principale")

menu_labels = {
    "profilo": "👤 Profilo Studente",
    "dashboard": "🎓 Dashboard Studente"
}

scelta = st.sidebar.radio(
    "Naviga",
    list(menu_labels.values()),
    index=0,
    key="menu_principale"
)

# Mappa il valore scelto a una chiave interna
pagina = [k for k, v in menu_labels.items() if v == scelta][0]

# =====================================================
# 🔀 Routing logico in base alla scelta
# =====================================================
if pagina == "profilo":
    # Se il profilo non esiste, mostra il setup
    if profile_data is None or st.session_state.get("show_setup"):
        st.warning("🧩 Profilo incompleto o in modifica: completa il setup.")
        setup_profilo()
        st.session_state["show_setup"] = False
    else:
        st.success(f"👋 Benvenuto {profile_data['nome']}! Il tuo profilo è completo.")
        show_profilo_completo(profile_data)

 # Pulsante per aggiornare il profilo
st.markdown("---")
if st.button("🔄 Aggiorna profilo"):
    st.session_state["show_setup"] = True
    st.session_state["menu_principale"] = "Profilo"  # imposta la label visiva
    st.rerun()




elif pagina == "dashboard":

    user_id = st.session_state.auth_user["id"]
    st.title("🎓 Dashboard Studente")

    # --- Contenuto della dashboard che hai ora ---
    try:
        res = supabase.table("gruppi").select("*").contains("membri", [user_id]).execute()
        gruppi_studente = res.data if res.data else []
    except Exception as e:
        st.error(f"Errore nel caricamento dei gruppi: {e}")
        gruppi_studente = []

    if len(gruppi_studente) > 0:
        st.markdown("### 📚 I tuoi gruppi passati:")
        for g in gruppi_studente:
            st.info(f"**{g['nome_gruppo']}** – creato il {g['data_creazione'][:10]}")
    else:
        st.warning("🧩 Non hai ancora partecipato a nessuna lezione.\nPartecipa a una lezione per creare il tuo team!")

    st.markdown("### 📊 Le tue mini statistiche")
    col1, col2, col3 = st.columns(3)
    col1.metric("Sessioni totali", len(gruppi_studente))
    col2.metric("Ultima attività", gruppi_studente[-1]['data_creazione'][:10] if gruppi_studente else "N/D")
    col3.metric("Livello attuale", "In esplorazione 🚀")

    # Pulsanti test gruppi
    st.markdown("---")
    st.subheader("🧪 Test automatico gruppi")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Genera gruppi di test"):
            crea_gruppi_finti(user_id)
    with col2:
        if st.button("🧹 Elimina gruppi di test"):
            pulisci_gruppi_finti(user_id)



import random
from datetime import datetime, timedelta

def crea_gruppi_finti(user_id, n=3):
    """
    Crea n gruppi casuali di test associati all'utente corrente.
    """
    nomi = ["Economia", "Marketing", "Finanza", "Statistica", "Management"]
    gruppi_creati = []

    for i in range(n):
        nome_gruppo = f"{random.choice(nomi)} {random.randint(10,99)}/10"
        data_creazione = (datetime.now() - timedelta(days=random.randint(0,30))).isoformat()
        membri = [user_id]  # Array con l'ID utente come unico membro

        try:
            res = supabase.table("gruppi").insert({
                "nome_gruppo": nome_gruppo,
                "membri": membri,
                "data_creazione": data_creazione
            }).execute()
            gruppi_creati.append(res.data)
        except Exception as e:
            st.error(f"Errore durante la creazione dei gruppi di test: {e}")

    st.success(f"✅ Creati {len(gruppi_creati)} gruppi di test!")



# ───────────── UI PRINCIPALE ─────────────
st.title("🎓 Syntia MVP – Team Hobbies + Materie")

st.subheader("📱 QR Code per invitare amici")
link = get_public_link()
qr = generate_qr_code(link)
st.image(qr, caption=link)
