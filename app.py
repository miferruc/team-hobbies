# =====================================================
# 🌐 APP BASE – STREAMLIT + SUPABASE
# =====================================================

import streamlit as st
from supabase import create_client
from datetime import datetime

# =====================================================
# 🔧 CONFIGURAZIONE BASE
# =====================================================

st.set_page_config(page_title="App Base", page_icon="🎓", layout="centered")

# --- CONNESSIONE SUPABASE ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# =====================================================
# 🧠 SESSIONE STREAMLIT
# =====================================================

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


def require_login():
    """Blocca la pagina se non sei loggato"""
    if st.session_state.auth_user is None:
        st.warning("🔒 Effettua prima il login per continuare.")
        st.stop()

# =====================================================
# 🔐 LOGIN / LOGOUT BASE
# =====================================================

with st.sidebar:
    st.subheader("🔐 Accesso")

    if st.session_state.auth_user is None:
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")

        if st.button("Accedi"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
                st.success(f"Accesso riuscito come {res.user.email}")
                st.rerun()
            except Exception as e:
                st.error(f"Errore login: {e}")

        st.markdown("---")
        st.info("Inserisci le tue credenziali Supabase per accedere.")
    else:
        st.success(f"Connesso come {st.session_state.auth_user['email']}")
        if st.button("Esci"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.session_state.auth_user = None
            st.success("Logout effettuato ✅")
            st.rerun()

# =====================================================
# 🧩 CONTENUTO PRINCIPALE
# =====================================================

st.title("📘 App Base con Supabase")
if st.session_state.auth_user:
    st.write("✅ Connessione attiva a Supabase.")
    st.write("Utente corrente:", st.session_state.auth_user)
else:
    st.info("Effettua l'accesso per continuare.")

# =====================================================
# 🎯 CHECKPOINT 1 — PROFILO STUDENTE
# =====================================================

import json

st.title("👤 Profilo studente")

# richiede login
require_login()
user = st.session_state.auth_user
user_id = user["id"]

# --- Carica profilo se esiste ---
def load_profile(uid):
    try:
        res = supabase.table("profiles").select("*").eq("id", uid).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Errore nel caricamento profilo: {e}")
        return None

# --- Salva profilo ---
def save_profile(uid, nome, corso, hobby, approccio):
    try:
        existing = load_profile(uid)
        record = {
            "id": uid,
            "email": user["email"],
            "nome": nome,
            "corso": corso,
            "hobby": hobby,
            "approccio": approccio,
            "timestamp": datetime.now().isoformat(),
        }
        if existing:
            supabase.table("profiles").update(record).eq("id", uid).execute()
        else:
            supabase.table("profiles").insert(record).execute()
        st.success("✅ Profilo salvato correttamente")
    except Exception as e:
        st.error(f"Errore nel salvataggio: {e}")

# --- Form profilo ---
profile = load_profile(user_id)

nome = st.text_input("Nome completo", value=profile.get("nome") if profile else "")
corso = st.text_input("Corso di studi", value=profile.get("corso") if profile else "")
hobby = st.multiselect(
    "Hobby principali",
    ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"],
    default=profile.get("hobby") if profile else [],
)
approccio = st.selectbox(
    "Approccio allo studio",
    ["Collaborativo", "Individuale", "Analitico", "Pratico"],
    index=["Collaborativo", "Individuale", "Analitico", "Pratico"].index(profile.get("approccio"))
    if profile and profile.get("approccio") in ["Collaborativo", "Individuale", "Analitico", "Pratico"]
    else 0,
)

if st.button("💾 Salva profilo"):
    save_profile(user_id, nome, corso, hobby, approccio)

# --- Mostra profilo salvato ---
st.markdown("---")
st.subheader("📋 Riepilogo profilo")
profile = load_profile(user_id)
if profile:
    st.json(profile)
else:
    st.info("Nessun profilo ancora salvato.")
