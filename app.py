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
