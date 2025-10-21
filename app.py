import streamlit as st
from supabase import create_client
from pathlib import Path
import pandas as pd
from typing import List
import qrcode
from io import BytesIO
import random
from datetime import datetime, timedelta

# ───────────── SUPABASE INIT ─────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

st.set_page_config(page_title="Syntia MVP", page_icon="🎓", layout="centered")

# ───────────── AUTH PERSISTENTE (FIX) ─────────────
# Se ho i token, ripristino la sessione in modo corretto (2 argomenti)
if st.session_state.get("sb_access_token") and st.session_state.get("sb_refresh_token"):
    try:
        supabase.auth.set_session(
            st.session_state["sb_access_token"],
            st.session_state["sb_refresh_token"]
        )
    except Exception:
        # Se i token sono scaduti o invalidi, pulisco SOLO i token.
        st.session_state.pop("sb_access_token", None)
        st.session_state.pop("sb_refresh_token", None)
        # Non tocco auth_user qui: evito di sloggarlo se sto entrando ora.


# ───────────── CAPTURE PARAMETRO QR GLOBALE ─────────────
# Se apro il link con ?session_id=... salvo il pending per usarlo post-login
try:
    qp = st.query_params
    if qp and qp.get("session_id"):
        sid = qp.get("session_id", [None])[0] if isinstance(qp.get("session_id"), list) else qp.get("session_id")
        if sid:
            st.session_state["pending_session_id"] = sid
except Exception:
    pass

# ───────────── SESSION INIT ─────────────
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

def require_login():
    """Blocca l'app se l'utente non è autenticato"""
    if st.session_state.auth_user is None:
        st.warning("🔒 Devi effettuare il login per accedere all'app.")
        st.stop()

# 🔧 UPDATE – Controllo ruolo utente
def get_user_role(user_id: str) -> str:
    """Restituisce il ruolo dell'utente (student/admin)."""
    try:
        res = supabase.table("profiles").select("role").eq("id", user_id).execute()
        if res.data and "role" in res.data[0]:
            return res.data[0]["role"]
        return "student"
    except Exception:
        return "student"

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
                "nome": "",
                "role": "student"  # 🔧 UPDATE default role
            }).execute()
            return None
        profile = data[0]

        required = ["nome", "corso", "materie_fatte", "materie_dafare", "hobby", "approccio", "obiettivi"]
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

    nome = st.text_input("Il tuo nome completo:")
    corso = st.selectbox("Corso di studi:", ["Economia"])

    st.markdown("### 📘 Materie")
    materie_fatte = st.multiselect(
        "Materie già superate:",
        ["Economia Aziendale", "Statistica", "Diritto Privato", "Microeconomia", "Marketing"],
    )
    materie_dafare = st.multiselect(
        "Materie ancora da sostenere:",
        ["Finanza", "Econometria", "Gestione Aziendale", "Macroeconomia", "Comunicazione"],
    )

    st.markdown("### 🎨 Hobby e Interessi")
    hobby = st.multiselect(
        "Seleziona i tuoi hobby:",
        ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Cucina", "Arte", "Volontariato"],
    )

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
    # 🔧 Inserisci l'URL reale della tua app (copialo dalla barra del browser Streamlit)
    return "https://team-hobbies-9ghc3ehkc4mbkxwpdhkqhn.streamlit.app"


def generate_qr_code(link: str, session_name: str = None):
    """Genera un QR code personalizzato con il nome della sessione."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    # Genera QR base
    qr_img = qrcode.make(link).convert("RGB")

    # Se è stato passato un nome, aggiungilo sopra come testo
    if session_name:
        width, height = qr_img.size
        new_img = Image.new("RGB", (width, height + 60), "white")
        new_img.paste(qr_img, (0, 60))

        draw = ImageDraw.Draw(new_img)
        text = session_name[:40]  # limita testo lungo

        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()

        # ✅ Calcolo dimensioni testo compatibile con tutte le versioni di Pillow
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            text_w, text_h = draw.textsize(text, font=font)

        draw.text(((width - text_w) / 2, 20), text, fill="black", font=font)
        qr_img = new_img

    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    return buf



# ───────────── LOGIN/REGISTRAZIONE ─────────────
with st.sidebar:
    st.subheader("🔐 Accesso")

    if st.session_state.auth_user is None:
        tab_login, tab_signup = st.tabs(["Entra", "Registrati"])

        # --- LOGIN TAB ---
        with tab_login:
            email = st.text_input("Email", key="login_email")
            pwd = st.text_input("Password", type="password", key="login_pwd")

            if st.button("Accedi"):
                try:
                    # 🔐 Login Supabase
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                    st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}

                    # ✅ salva token per la persistenza corretta
                    st.session_state["sb_access_token"]  = res.session.access_token
                    st.session_state["sb_refresh_token"] = res.session.refresh_token
                    # (opzionale) st.session_state.pop("supabase_session", None)

                    # ───────────── REDIRECT AUTOMATICO POST-LOGIN ─────────────
                    pending_session = st.session_state.get("pending_session_id")

                    if pending_session:
                        try:
                            # ✅ Se non è già iscritto, aggiungilo alla sessione
                            chk = supabase.table("participants").select("*") \
                                .eq("session_id", pending_session).eq("user_id", res.user.id).execute()
                            if not chk.data:
                                supabase.table("participants").insert({
                                    "user_id": res.user.id,
                                    "session_id": pending_session
                                }).execute()

                            # 🎯 Imposta la pagina principale su Dashboard e mantieni l’ID sessione
                            st.session_state["menu_principale"] = "🎓 Dashboard Studente"
                            st.query_params.update({"session_id": pending_session})



                            # ✅ Pulisce e ricarica
                            del st.session_state["pending_session_id"]
                            st.success("✅ Ti sei unito alla sessione. Ti porto alla Dashboard…")
                            st.rerun()

                        except Exception as e:
                            st.error(f"Errore durante l’unione automatica alla sessione: {e}")
                            # Anche se fallisce, continuo col login normale

                    # 🔁 Nessun QR pendente → login normale
                    st.success(f"Benvenuto {res.user.email} 👋")
                    st.rerun()

                except Exception as e:
                    st.error(f"Login fallito: {e}")

        # --- REGISTRAZIONE TAB ---
        with tab_signup:
            email_s = st.text_input("Email", key="signup_email")
            pwd_s = st.text_input("Password", type="password", key="signup_pwd")

            if st.button("Registrati"):
                try:
                    # ✅ Controllo dominio consentito
                    allowed_domains = ["@studenti.unibg.it", "@unibg.it"]
                    # 👉 Aggiungi altri domini qui se necessario:
                    # allowed_domains += ["@altrodominio.it", "@azienda.com"]

                    if not any(email_s.endswith(dom) for dom in allowed_domains):
                        st.error("❌ Registrazione consentita solo per email istituzionali UNIBG.")
                    else:
                        res = supabase.auth.sign_up({"email": email_s, "password": pwd_s})
                        st.success("Registrazione completata! Esegui ora l'accesso 👇")

                except Exception as e:
                    st.error(f"Registrazione fallita: {e}")

    else:
        st.success(f"Connesso come {st.session_state.auth_user['email']}")
        if st.button("Esci"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            # 🔧 Pulizia completa dello stato utente
            for k in [
                "auth_user",
                "sb_access_token",
                "sb_refresh_token",
                "pending_session_id",
                "supabase_session",
            ]:
                st.session_state.pop(k, None)

            st.success("🚪 Logout effettuato correttamente.")
            st.rerun()

    st.sidebar.divider()




# ───────────── BLOCCO ACCESSO + CONTROLLO PROFILO ─────────────
if st.session_state.auth_user is not None:
    profile_data = load_profile()
    user_role = get_user_role(st.session_state.auth_user["id"])
else:
    st.stop()


# =====================================================
# 🌐 MENU DI NAVIGAZIONE
# =====================================================
st.sidebar.title("📚 Menu Principale")

menu_labels = {
    "profilo": "👤 Profilo Studente",
    "dashboard": "🎓 Dashboard Studente",
}

# 🔧 UPDATE – Mostra Command Center solo se admin
if user_role == "admin":
    menu_labels["admin_panel"] = "🧠 Command Center (Admin)"

scelta = st.sidebar.radio("Naviga", list(menu_labels.values()), index=0, key="menu_principale")
pagina = [k for k, v in menu_labels.items() if v == scelta][0]

# =====================================================
# 🔀 ROUTING LOGICO
# =====================================================
if pagina == "profilo":
    if profile_data is None or st.session_state.get("show_setup"):
        st.warning("🧩 Profilo incompleto o in modifica: completa il setup.")
        setup_profilo()
        st.session_state["show_setup"] = False
    else:
        st.success(f"👋 Benvenuto {profile_data['nome']}! Il tuo profilo è completo.")
        show_profilo_completo(profile_data)

        # 🔧 UPDATE – Pulsante aggiornamento integrato
        st.markdown("---")
        if st.button("🔄 Aggiorna profilo"):
            st.session_state["show_setup"] = True
            st.session_state["menu_principale"] = "Profilo"
            st.rerun()

elif pagina == "dashboard":
    # =====================================================
    # 🔗 FASE 5A – JOIN VIA QR (versione aggiornata)
    # =====================================================
    qp = st.query_params
    session_id = None
    if "session_id" in qp:
        val = qp["session_id"]
        session_id = val[0] if isinstance(val, list) else val


    # --- 🔐 FIX LOGIN VIA QR (persistente) ---
    # Se l'utente non è loggato ma ha scansionato un QR → salva e interrompi
    if session_id and not st.session_state.get("auth_user"):
        st.session_state["pending_session_id"] = session_id
        st.warning("⚠️ Effettua prima il login per unirti alla sessione.")
        st.stop()

    # Dopo il login → se esiste una sessione pending → unisciti automaticamente
    if st.session_state.get("auth_user") and st.session_state.get("pending_session_id"):
        try:
            user_id = st.session_state.auth_user["id"]
            pending_session = st.session_state["pending_session_id"]

            # Verifica se già iscritto
            res_check = supabase.table("participants").select("*") \
                .eq("session_id", pending_session).eq("user_id", user_id).execute()

            if not res_check.data:
                supabase.table("participants").insert({
                    "user_id": user_id,
                    "session_id": pending_session
                }).execute()
                st.success("✅ Ti sei unito automaticamente alla sessione!")
            else:
                st.info("Sei già iscritto a questa sessione ✅")

            # Rimuovi il pending ID e resetta la query string
            del st.session_state["pending_session_id"]
            st.query_params.update({"session_id": pending_session})
            st.rerun()

        except Exception as e:
            st.error(f"Errore durante l’unione automatica alla sessione: {e}")

    # --- Titolo Dashboard ---
    st.title("🎓 Dashboard Studente")



    # --- 🔄 JOIN SESSIONE TRAMITE QR ---
    if session_id:
        try:
            res_sess = supabase.table("sessioni").select("*").eq("id", session_id).execute()
            if not res_sess.data:
                st.error("❌ Sessione non trovata. Verifica il link.")
            else:
                sessione = res_sess.data[0]
                st.info(f"🎓 Sessione trovata: **{sessione['nome']}** – tema *{sessione['tema']}*")

                user_id = st.session_state.auth_user["id"]

                # 🔍 Verifica se già iscritto
                res_check = supabase.table("participants").select("*") \
                    .eq("session_id", session_id).eq("user_id", user_id).execute()

                if res_check.data:
                    st.warning("⚠️ Sei già iscritto a questa sessione.")
                else:
                    # ✅ Aggiunge utente alla sessione
                    supabase.table("participants").insert({
                        "user_id": user_id,
                        "session_id": session_id
                    }).execute()
                    st.success("✅ Ti sei unito con successo alla sessione!")
        except Exception as e:
            st.error(f"Errore durante il join della sessione: {e}")

    # =====================================================
    # 📊 FASE 5B–5C: DASHBOARD STUDENTE + GRUPPI
    # =====================================================
    user_id = st.session_state.auth_user["id"]

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

    st.markdown("---")
    st.subheader("🧪 Test automatico gruppi")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Genera gruppi di test"):
            crea_gruppi_finti(user_id)
    with col2:
        if st.button("🧹 Elimina gruppi di test"):
            pulisci_gruppi_finti(user_id)

    # =====================================================
    # 🎯 FASE 5C – GRUPPO STUDENTE
    # =====================================================
    st.markdown("---")
    st.subheader("🎯 Il tuo gruppo di studio")

    try:
        # 1️⃣ Trova se l'utente è iscritto a una sessione
        res_part = supabase.table("participants").select("session_id").eq("user_id", user_id).execute()
        if not res_part.data:
            st.info("Non sei ancora iscritto a nessuna sessione.")
        else:
            session_ids = [p["session_id"] for p in res_part.data]

            # 2️⃣ Cerca se l'utente è in un gruppo
            res_group = supabase.table("gruppi").select("*").execute()
            gruppo_utente = None
            for g in res_group.data:
                if user_id in g.get("membri", []):
                    gruppo_utente = g
                    break

            if gruppo_utente:
                st.success(f"🏷️ Gruppo: **{gruppo_utente['nome_gruppo']}**  \nTema: *{gruppo_utente.get('tema', '-') }*")

                # Mostra membri del gruppo
                membri_ids = gruppo_utente["membri"]
                res_prof = supabase.table("profiles").select("nome, email").in_("id", membri_ids).execute()
                membri_info = [f"• {p['nome']} ({p['email']})" for p in res_prof.data]
                st.markdown("**Membri del gruppo:**")
                st.markdown("\n".join(membri_info))
            else:
                st.warning("⏳ Non sei ancora stato assegnato a un gruppo. Attendi che l'admin completi il matching.")
    except Exception as e:
        st.error(f"Errore durante il caricamento del gruppo: {e}")

    
# =====================================================
# 🧠 FASE 4 – COMMAND CENTER (ADMIN)
# =====================================================
elif pagina == "admin_panel":
    st.title("🧠 Command Center (Admin)")
    st.markdown("Gestisci le sessioni di lezione e genera QR code per l'accesso degli studenti.")
    st.divider()

    # --- CREAZIONE SESSIONE ---
    st.subheader("📅 Crea una nuova sessione")

    materia = st.text_input("Materia della sessione:")
    data_sessione = st.date_input("Data della lezione:")

    # 🔧 Generazione automatica nome standardizzato
    if materia and data_sessione:
        nome_auto = f"{materia}_{data_sessione.strftime('%d_%m_%Y')}"
        st.markdown(f"🔍 **Nome generato automaticamente:** `{nome_auto}`")
    else:
        nome_auto = ""

    # 🔧 Pulsante per modificare manualmente il nome
    modifica_manual = st.checkbox("✏️ Modifica manualmente il nome", value=False)

    if modifica_manual:
        nome_standard = st.text_input(
            "Nome personalizzato:",
            value=nome_auto,
            key="nome_standard_custom",
        )
    else:
        nome_standard = nome_auto

    tema = st.selectbox(
        "Tema nomi gruppi:",
        ["Anime", "Imprese", "Sport", "Università", "Città", "Animali"]
    )

        # --- PULSANTE CREAZIONE SESSIONE ---
    if st.button("🚀 Crea sessione"):
        if materia and nome_standard:
            try:
                from uuid import uuid4
                session_id = str(uuid4())[:8]

                # Crea link pubblico
                public_link = f"{get_public_link()}?session_id={session_id}"

                # Salva su Supabase la nuova sessione
                supabase.table("sessioni").insert({
                    "id": session_id,
                    "materia": materia,
                    "data": str(data_sessione),
                    "nome": nome_standard,
                    "tema": tema,
                    "link_pubblico": public_link,
                    "creato_da": st.session_state.auth_user["id"],
                    "timestamp": datetime.now().isoformat()
                }).execute()

                # ✅ Aggiunge automaticamente l'admin come partecipante
                supabase.table("participants").insert({
                    "user_id": st.session_state.auth_user["id"],
                    "session_id": session_id
                }).execute()

                st.success(f"✅ Sessione '{nome_standard}' creata con successo!")

                # Genera e mostra QR code
                qr_buf = generate_qr_code(public_link, nome_standard)
                st.image(qr_buf, caption=f"Scansiona per accedere – {materia}")
                st.markdown(f"🔗 **Link pubblico:** `{public_link}`")

            except Exception as e:
                st.error(f"Errore nella creazione della sessione: {e}")
        else:
            st.warning("Compila tutti i campi obbligatori.")

    st.divider()


# --- LISTA SESSIONI ATTIVE ---
st.subheader("📋 Sessioni attive")
try:
    res = supabase.table("sessioni").select("*").order("timestamp", desc=True).execute()  # 🔧 corretto
    sessioni = res.data
except Exception as e:
    st.error(f"Errore nel caricamento delle sessioni: {e}")
    sessioni = []

if sessioni:
    for s in sessioni:
        with st.expander(f"📘 {s['nome']} – {s['materia']} ({s['data']})"):
            st.markdown(f"**Tema gruppi:** {s.get('tema', '-')}")  
            st.markdown(f"**Creato da:** {s.get('creato_da', '-')}")  
            st.markdown(f"**Link pubblico:** `{s.get('link_pubblico', '-')}`")  

            qr_buf = generate_qr_code(s["link_pubblico"])
            st.image(qr_buf, caption="QR Code sessione", width=180)

            # --- 👥 LISTA PARTECIPANTI SESSIONE ---
            st.markdown("### 👥 Partecipanti iscritti")

            # Pulsante per aggiornare la lista
            aggiorna = st.button(f"🔄 Aggiorna lista partecipanti ({s['id']})")

            try:
                if aggiorna or True:
                    res_part = supabase.table("participants") \
                        .select("user_id") \
                        .eq("session_id", s["id"]).execute()

                    if res_part.data:
                        partecipanti_ids = [p["user_id"] for p in res_part.data]

                        # Recupera i profili degli utenti
                        res_prof = supabase.table("profiles") \
                            .select("email, nome") \
                            .in_("id", partecipanti_ids).execute()

                        partecipanti = [
                            f"{p.get('nome', 'Sconosciuto')} ({p.get('email', 'no email')})"
                            for p in res_prof.data
                        ]

                        # Mostra la lista
                        st.selectbox(
                            "Partecipanti registrati:",
                            options=partecipanti,
                            index=0 if partecipanti else None,
                            key=f"sel_part_{s['id']}"
                        )

                        totale = len(partecipanti)
                        st.info(f"Totale partecipanti: **{totale}**")

                        # Blocco creazione gruppi se meno di 3
                        if totale < 3:
                            st.warning("⚠️ Servono almeno 3 studenti per creare i gruppi.")
                            crea_attivo = False
                        else:
                            crea_attivo = True
                    else:
                        st.warning("Nessuno studente ha ancora scansionato il QR code.")
                        crea_attivo = False
            except Exception as e:
                st.error(f"Errore nel caricamento partecipanti: {e}")
                crea_attivo = False
            # --- 👥 FINE LISTA PARTECIPANTI ---

            st.markdown("---")

            # --- 🤝 CREA GRUPPI ---
            if crea_attivo and st.button(f"🤝 Crea gruppi per {s['nome']}"):
                crea_gruppi_da_sessione(s["id"])
            elif not crea_attivo:
                st.info("🔒 Il pulsante 'Crea gruppi' si attiverà automaticamente quando ci saranno almeno 3 partecipanti.")

            st.markdown("---")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"📋 Copia link ({s['id']})"):
                    st.code(s["link_pubblico"])
            with col2:
                if st.button(f"🗑️ Elimina sessione ({s['id']})"):
                    try:
                        supabase.table("sessioni").delete().eq("id", s["id"]).execute()  # 🔧 corretto
                        st.success("Sessione eliminata con successo ✅")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'eliminazione: {e}")
else:
    st.info("Nessuna sessione creata finora.")



# =====================================================
# 🔧 FUNZIONI TEST GRUPPI
# =====================================================
def crea_gruppi_finti(user_id, n=3):
    nomi = ["Economia", "Marketing", "Finanza", "Statistica", "Management"]
    gruppi_creati = []
    for i in range(n):
        nome_gruppo = f"{random.choice(nomi)} {random.randint(10,99)}/10"
        data_creazione = (datetime.now() - timedelta(days=random.randint(0,30))).isoformat()
        membri = [user_id]
        try:
            res = supabase.table("gruppi").insert({
                "nome_gruppo": nome_gruppo,
                "materia": random.choice(nomi),  # 🔧 UPDATE
                "session_id": "test",
                "membri": membri,
                "data_creazione": data_creazione
            }).execute()
            gruppi_creati.append(res.data)
        except Exception as e:
            st.error(f"Errore durante la creazione dei gruppi di test: {e}")
    st.success(f"✅ Creati {len(gruppi_creati)} gruppi di test!")

def pulisci_gruppi_finti(user_id):
    try:
        supabase.table("gruppi").delete().contains("membri", [user_id]).eq("session_id", "test").execute()
        st.success("🧹 Gruppi di test eliminati con successo!")
    except Exception as e:
        st.error(f"Errore durante la pulizia dei gruppi: {e}")
