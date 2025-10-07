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
        required = ["nome"]
        if any(not profile.get(f) for f in required):
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

if profile_data is None:
    st.warning("🧩 Profilo incompleto: vai al setup.")
    setup_profilo()
else:
    st.success(f"👋 Benvenuto {profile_data['nome']}! Il tuo profilo è completo.")
    show_profilo_completo(profile_data)


# ───────────── UI PRINCIPALE ─────────────
st.title("🎓 Syntia MVP – Team Hobbies + Materie")

st.subheader("📱 QR Code per invitare amici")
link = get_public_link()
qr = generate_qr_code(link)
st.image(qr, caption=link)
