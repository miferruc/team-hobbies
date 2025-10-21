# =====================================================
# 🌐 APP BASE – STREAMLIT + SUPABASE
# =====================================================

import streamlit as st
from supabase import create_client
from datetime import datetime


# =====================================================
# 🍪 COOKIE MANAGER — persistenza login
# =====================================================
from streamlit_cookies_manager import EncryptedCookieManager

cookies = EncryptedCookieManager(
    prefix="team_hobbies_",
    password="chiave_super_sicura"  # cambia con un valore lungo e unico
)

if not cookies.ready():
    st.stop()
st.write("")  # evita errore di rendering durante caricamento cookie


# =====================================================
# 🔧 CONFIGURAZIONE BASE
# =====================================================

st.set_page_config(page_title="App Base", page_icon="🎓", layout="centered")

# --- CONNESSIONE SUPABASE ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# =====================================================
# 🔁 FUNZIONE DI RIPRISTINO SESSIONE (cookie + token)
# =====================================================
def restore_session():
    """Mantiene l'utente loggato anche dopo refresh o chiusura browser"""
    if not cookies.ready():
        return  # evita errori se il cookie manager non è ancora pronto

    # 1️⃣ Recupera token da cookie
    if "sb_access_token" not in st.session_state:
        token_cookie = cookies.get("sb_access_token")
        if token_cookie:
            st.session_state["sb_access_token"] = token_cookie

    # 2️⃣ Recupera utente da token
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None

    if st.session_state.get("sb_access_token") and st.session_state.auth_user is None:
        try:
            res = supabase.auth.get_user(st.session_state["sb_access_token"])
            if res and res.user:
                st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
        except Exception:
            pass

    # 3️⃣ Se loggato, salva token nel cookie (solo se non esiste già)
    if st.session_state.get("sb_access_token"):
        if cookies.get("sb_access_token") != st.session_state["sb_access_token"]:
            cookies["sb_access_token"] = st.session_state["sb_access_token"]
            cookies.save()


# Esegui subito al caricamento
restore_session()


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
# 🔐 LOGIN / REGISTRAZIONE / LOGOUT BASE (persistente)
# =====================================================
with st.sidebar:
    st.subheader("🔐 Accesso o Registrazione")

    # --- Se c'è un token salvato, tenta il ripristino ---
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    if "sb_access_token" in st.session_state and st.session_state.auth_user is None:
        try:
            res = supabase.auth.get_user(st.session_state["sb_access_token"])
            if res and res.user:
                st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
        except Exception:
            pass

    # --- Tabs Login e Registrazione ---
    if st.session_state.auth_user is None:
        tab_login, tab_signup = st.tabs(["🔑 Accedi", "🆕 Registrati"])

        # ----- LOGIN -----
        with tab_login:
            st.markdown("**Entra con le tue credenziali universitarie**")
            email = st.text_input("Email universitaria", key="login_email")
            pwd = st.text_input("Password", type="password", key="login_pwd")

            if st.button("Accedi"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                    st.session_state.auth_user = {"id": res.user.id, "email": res.user.email}
                    token = res.session.access_token
                    st.session_state["sb_access_token"] = token
                    cookies["sb_access_token"] = token
                    cookies.save()

                    st.success(f"Accesso riuscito come {res.user.email}")
                    st.experimental_set_query_params(_="login_done")
                    st.toast("✅ Accesso effettuato", icon="🔓")

                except Exception as e:
                    st.error(f"Errore login: {e}")

        # ----- REGISTRAZIONE -----
        with tab_signup:
            st.markdown("**Crea un nuovo account universitario**")
            email_reg = st.text_input("Email universitaria (@studenti.unibg.it)", key="signup_email")
            pwd1 = st.text_input("Password", type="password", key="signup_pwd1")
            pwd2 = st.text_input("Ripeti Password", type="password", key="signup_pwd2")

            if st.button("Crea account"):
                if not email_reg or not pwd1 or not pwd2:
                    st.warning("Compila tutti i campi.")
                elif "@studenti." not in email_reg:
                    st.warning("Usa un'email universitaria valida.")
                elif pwd1 != pwd2:
                    st.error("Le password non coincidono.")
                elif len(pwd1) < 6:
                    st.warning("La password deve avere almeno 6 caratteri.")
                else:
                    try:
                        res = supabase.auth.sign_up({"email": email_reg, "password": pwd1})
                        if res.user:
                            st.success("✅ Registrazione completata! Ora puoi accedere.")
                        else:
                            st.warning("Errore durante la registrazione. Riprova.")
                    except Exception as e:
                        st.error(f"Errore registrazione: {e}")

    else:
        # ----- LOGOUT -----
        st.success(f"Connesso come {st.session_state.auth_user['email']}")
        if st.button("Esci"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            for key in ["auth_user", "sb_access_token"]:
                if key in st.session_state:
                    del st.session_state[key]
            cookies.delete("sb_access_token")  # ← spostato fuori
            cookies.save()
            st.success("Logout effettuato ✅")
            st.experimental_set_query_params(_="logout_done")
            st.toast("👋 Logout completato", icon="🔒")




# =====================================================
# 🧩 CONTENUTO PRINCIPALE
# =====================================================

tab1, tab2, tab3 = st.tabs(["👤 Profilo", "🏫 Sessioni", "🤝 Gruppi"])

# =====================================================
# TAB 1 — PROFILO STUDENTE
# =====================================================
with tab1:
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


    def save_profile(uid, nome, corso, materie_fatte, materie_dafare, hobby, approccio, obiettivi):
        """Salva o aggiorna il profilo utente"""
        try:
            existing = load_profile(uid)
            record = {
                "id": uid,
                "email": user["email"],
                "nome": nome,
                "corso": corso,
                "materie_fatte": materie_fatte,
                "materie_dafare": materie_dafare,
                "hobby": hobby,
                "approccio": approccio,
                "obiettivi": obiettivi,
                "role": "student",  # default
                "created_at": datetime.now().isoformat(),
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

    materie_fatte = st.multiselect(
        "Materie già superate",
        ["Economia Aziendale", "Statistica", "Diritto Privato", "Microeconomia", "Marketing"],
        default=profile.get("materie_fatte") if profile and isinstance(profile.get("materie_fatte"), list) else [],
    )

    materie_dafare = st.multiselect(
        "Materie ancora da sostenere",
        ["Finanza", "Econometria", "Gestione Aziendale", "Macroeconomia", "Comunicazione"],
        default=profile.get("materie_dafare") if profile and isinstance(profile.get("materie_dafare"), list) else [],
    )

    # --- Hobby gestito in modo sicuro ---
    default_hobby = []
    if profile:
        raw = profile.get("hobby")
        if isinstance(raw, list):
            default_hobby = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    default_hobby = parsed
                else:
                    default_hobby = [raw]
            except Exception:
                default_hobby = [raw]

    options_hobby = ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"]
    default_hobby = [x for x in default_hobby if x in options_hobby]

    hobby = st.multiselect("Hobby principali", options=options_hobby, default=default_hobby)

    approccio = st.selectbox(
        "Approccio allo studio",
        ["Collaborativo", "Individuale", "Analitico", "Pratico"],
        index=(
            ["Collaborativo", "Individuale", "Analitico", "Pratico"].index(profile.get("approccio"))
            if profile and profile.get("approccio") in ["Collaborativo", "Individuale", "Analitico", "Pratico"]
            else 0
        ),
    )

    obiettivi = st.multiselect(
        "Obiettivi accademici",
        [
            "Passare gli esami a prescindere dal voto",
            "Raggiungere una media del 30",
            "Migliorare la comprensione delle materie",
            "Creare connessioni e fare gruppo",
            "Prepararmi per la carriera futura",
        ],
        default=profile.get("obiettivi") if profile and isinstance(profile.get("obiettivi"), list) else [],
    )

    # --- Pulsante Salva ---
    if st.button("💾 Salva profilo"):
        save_profile(user_id, nome, corso, materie_fatte, materie_dafare, hobby, approccio, obiettivi)

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
   
# =====================================================
# TAB 2 — SESSIONI (Checkpoint 2 - compatibile con DB)
# =====================================================
with tab2:
    import qrcode
    from io import BytesIO
    import base64
    import uuid

    st.title("🏫 Creazione sessione")

    require_login()
    user = st.session_state.auth_user
    user_id = user["id"]

    st.markdown("Crea una nuova sessione per la tua lezione o per un assignment di gruppo:")

    # --- FORM DATI SESSIONE ---
    nome = st.text_input("Nome sessione", placeholder="Esempio: Economia_16_10_2025")
    materia = st.text_input("Materia", placeholder="Esempio: Economia")
    data = st.date_input("Data", value=datetime.now().date())
    tema = st.selectbox(
        "Tema dei gruppi",
        ["Anime", "Sport", "Spazio", "Natura", "Tecnologia", "Storia", "Mitologia"],
        index=0,
    )

    # --- PULSANTE CREAZIONE ---
    if st.button("📦 Crea sessione"):
        if not nome.strip():
            st.warning("Inserisci un nome valido per la sessione.")
        else:
            try:
                # Genera ID sessione
                session_id = str(uuid.uuid4())[:8]

                # Base URL app
                base_url = st.secrets.get("PUBLIC_URL", "https://team-hobbies-9ghc3ehkc4mbkxwpdhkqhn.streamlit.app/")
                link_pubblico = f"{base_url}?session_id={session_id}"

                # Salva nel DB
                record = {
                    "id": session_id,
                    "nome": nome,
                    "materia": materia,
                    "data": str(data),
                    "tema": tema,
                    "link_pubblico": link_pubblico,
                    "creato_da": user_id,
                    "timestamp": datetime.now().isoformat(),
                }
                supabase.table("sessioni").insert(record).execute()

                st.success(f"✅ Sessione creata con successo: {nome}")

                # --- QR code ---
                qr = qrcode.QRCode(box_size=6, border=2)
                qr.add_data(link_pubblico)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buf = BytesIO()
                img.save(buf, format="PNG")
                qr_b64 = base64.b64encode(buf.getvalue()).decode()
                st.image(f"data:image/png;base64,{qr_b64}", caption="Scansiona per unirti alla sessione")

                # --- Mostra link ---
                st.markdown(f"**Link pubblico:** [{link_pubblico}]({link_pubblico})")

            except Exception as e:
                st.error(f"Errore durante la creazione della sessione: {e}")

    # =====================================================
    # 📋 SESSIONI CREATE DALL'UTENTE
    # =====================================================
    st.markdown("---")
    st.subheader("📚 Le tue sessioni create")

    try:
        res = (
            supabase.table("sessioni")
            .select("*")
            .eq("creato_da", user_id)
            .order("timestamp", desc=True)
            .execute()
        )
        if res.data:
            for s in res.data:
                st.write(
                    f"• **{s['nome']}** | Tema: *{s.get('tema','')}* | Materia: *{s.get('materia','')}* "
                    f"| 📅 {s.get('data','')} | [Apri link]({s.get('link_pubblico','')})"
                )
        else:
            st.info("Nessuna sessione creata ancora.")
    except Exception as e:
        st.error(f"Errore nel caricamento delle sessioni: {e}")
# =====================================================
# TAB 3 — GRUPPI E PARTECIPANTI (Auto-refresh partecipanti + gruppi)
# =====================================================
with tab3:
    import random
    from datetime import datetime

    st.title("🤝 Gruppi e partecipanti")

    require_login()
    user = st.session_state.auth_user
    user_id = user["id"]

    # --- Recupera query string ---
    qp = st.query_params if hasattr(st, "query_params") else {}
    session_id = qp.get("session_id")
    if isinstance(session_id, list):
        session_id = session_id[0]

    if not session_id:
        st.info("Scansiona un QR code o apri un link di sessione per unirti.")
        st.stop()

    # --- Recupera dettagli sessione ---
    try:
        res_sess = supabase.table("sessioni").select("*").eq("id", session_id).execute()
        if not res_sess.data:
            st.error("Sessione non trovata.")
            st.stop()
        sessione = res_sess.data[0]
        st.success(f"🎓 Sessione trovata: **{sessione['nome']}** – Tema *{sessione.get('tema','N/D')}*")
    except Exception as e:
        st.error(f"Errore nel caricamento sessione: {e}")
        st.stop()

    # --- Join automatico (participants) ---
    try:
        res_check = (
            supabase.table("participants")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not res_check.data:
            supabase.table("participants").insert({
                "user_id": user_id,
                "session_id": session_id,
                "joined_at": datetime.now().isoformat(),
            }).execute()
            st.success("✅ Ti sei unito alla sessione!")
        else:
            st.info("Sei già iscritto a questa sessione ✅")
    except Exception as e:
        st.error(f"Errore durante l’unione alla sessione: {e}")

     # =====================================================
    # 👥 LISTA PARTECIPANTI (stabile e senza refresh inutili)
    # =====================================================
    st.markdown("### 👥 Studenti collegati")

    # Attiva l'autorefresh solo in questa tab
    if "disable_autorefresh" not in st.session_state:
        st.session_state["disable_autorefresh"] = True

    try:
        if st.session_state.get("disable_autorefresh", False) and hasattr(st, "autorefresh"):
            st.autorefresh(interval=5000, key="refresh_partecipanti")
    except Exception:
        pass  # compatibilità Streamlit versioni vecchie

    try:
        # Recupera tutti i partecipanti della sessione
        res_part = supabase.table("participants").select("user_id").eq("session_id", session_id).execute()
        ids = [p["user_id"] for p in res_part.data if p.get("user_id")]

        if ids:
            # Recupera i nomi dai profili corrispondenti
            res_prof = supabase.table("profiles").select("id,nome").in_("id", ids).execute()
            nomi = [p["nome"] for p in res_prof.data if p.get("nome")]
            nomi_ordinati = sorted(set(nomi))  # rimuove eventuali duplicati
            st.write(", ".join(nomi_ordinati))
            st.caption(f"Aggiornamento automatico ogni 5 s — {len(nomi_ordinati)} studenti collegati.")
        else:
            st.info("Ancora nessun partecipante.")
    except Exception as e:
        st.error(f"Errore nel caricamento partecipanti: {e}")


    # =====================================================
    # 🔀 CREAZIONE GRUPPI AUTOMATICI
    # =====================================================
    temi_gruppi = {
        "Anime": ["Akira", "Totoro", "Naruto", "Luffy", "Saitama", "Asuka", "Shinji", "Kenshin"],
        "Sport": ["Maradona", "Jordan", "Federer", "Bolt", "Ali", "Phelps", "Serena"],
        "Spazio": ["Apollo", "Orion", "Luna", "Cosmos", "Nova", "Mars"],
        "Natura": ["Quercia", "Rosa", "Vento", "Onda", "Sole", "Mare", "Cielo"],
        "Tecnologia": ["Byte", "Pixel", "Quantum", "Neural", "Circuit", "Code"],
        "Storia": ["Roma", "Atene", "Sparta", "Troia", "Cartagine", "Babilonia"],
        "Mitologia": ["Zeus", "Athena", "Thor", "Ra", "Anubi", "Odino"],
    }

    def crea_gruppi_da_sessione(session_id, size=4):
        try:
            res_part = supabase.table("participants").select("user_id").eq("session_id", session_id).execute()
            ids = [p["user_id"] for p in res_part.data]
            if not ids:
                st.warning("Nessun partecipante iscritto.")
                return

            res_prof = supabase.table("profiles").select("*").in_("id", ids).execute()
            profili = res_prof.data
            random.shuffle(profili)

            gruppi = [profili[i:i + size] for i in range(0, len(profili), size)]
            tema = sessione.get("tema", "Generico")
            nomi_tema = temi_gruppi.get(tema, [f"Gruppo{i+1}" for i in range(len(gruppi))])
            random.shuffle(nomi_tema)

            for i, g in enumerate(gruppi):
                membri = [p["id"] for p in g]
                nome_gruppo = nomi_tema[i % len(nomi_tema)]

                supabase.table("gruppi").insert({
                    "sessione_id": session_id,
                    "nome_gruppo": nome_gruppo,
                    "membri": membri,
                    "tema": tema,
                    "materia": sessione.get("materia", ""),
                    "data_creazione": datetime.now().isoformat(),
                }).execute()

            st.success(f"✅ Creati {len(gruppi)} gruppi a tema *{tema}*.")
        except Exception as e:
            st.error(f"Errore nella creazione gruppi: {e}")

    if st.button("🤝 Crea gruppi ora"):
        crea_gruppi_da_sessione(session_id)

    # =====================================================
    # 📋 GRUPPI ESISTENTI (auto-refresh 10s)
    # =====================================================
    st.markdown("---")
    st.subheader("📋 Gruppi creati")

    try:
        if hasattr(st, "autorefresh"):
            st.autorefresh(interval=10000, key="refresh_gruppi")
    except Exception:
        pass

    try:
        res = supabase.table("gruppi").select("*").eq("sessione_id", session_id).execute()
        if res.data:
            for g in res.data:
                membri = ", ".join(g.get("membri", []))
                st.write(f"• **{g['nome_gruppo']}** ({g.get('tema','')}) → {membri}")
            st.caption("Aggiornamento automatico ogni 10 s.")
        else:
            st.info("Nessun gruppo ancora creato.")
    except Exception as e:
        st.error(f"Errore nel caricamento gruppi: {e}")
