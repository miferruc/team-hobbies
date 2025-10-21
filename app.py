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
# =====================================================
# 🎯 CHECKPOINT 1 — PROFILO STUDENTE (versione corretta)
# =====================================================

import json
from datetime import datetime

st.title("👤 Profilo studente")

# --- Richiede login ---
require_login()
user = st.session_state.auth_user
user_id = user["id"]

# =====================================================
# 📥 FUNZIONI DI CARICAMENTO E SALVATAGGIO
# =====================================================

def load_profile(uid):
    """Recupera il profilo utente da Supabase"""
    try:
        res = supabase.table("profiles").select("*").eq("id", uid).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Errore nel caricamento profilo: {e}")
        return None


def save_profile(uid, nome, corso, hobby, approccio):
    """Salva o aggiorna il profilo utente"""
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


# =====================================================
# 🧩 FORM PROFILO
# =====================================================

profile = load_profile(user_id)

nome = st.text_input("Nome completo", value=profile.get("nome") if profile else "")
corso = st.text_input("Corso di studi", value=profile.get("corso") if profile else "")

# --- Sanitizzazione del valore hobby ---
default_hobby = []
if profile and profile.get("hobby"):
    val = profile.get("hobby")
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                default_hobby = parsed
        except Exception:
            default_hobby = [val]
    elif isinstance(val, list):
        default_hobby = val

hobby = st.multiselect(
    "Hobby principali",
    ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"],
    default=default_hobby,
)

approccio = st.selectbox(
    "Approccio allo studio",
    ["Collaborativo", "Individuale", "Analitico", "Pratico"],
    index=(
        ["Collaborativo", "Individuale", "Analitico", "Pratico"].index(profile.get("approccio"))
        if profile and profile.get("approccio") in ["Collaborativo", "Individuale", "Analitico", "Pratico"]
        else 0
    ),
)

# --- Pulsante Salva ---
if st.button("💾 Salva profilo"):
    save_profile(user_id, nome, corso, hobby, approccio)

# =====================================================
# 📊 RIEPILOGO PROFILO SALVATO
# =====================================================

st.markdown("---")
st.subheader("📋 Riepilogo profilo")

profile = load_profile(user_id)
if profile:
    st.json(profile)
else:
    st.info("Nessun profilo ancora salvato.")
