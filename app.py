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

    # --- Se l'utente NON è loggato ---
    if st.session_state.get("auth_user") is None:
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
                    st.session_state["sb_access_token"] = res.session.access_token
                    st.success(f"✅ Accesso riuscito come {res.user.email}")
                    st.toast("Accesso effettuato 🔓", icon="✅")
                    st.query_params["status"] = "login_done"
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore login: {e}")

        # ----- REGISTRAZIONE -----
        with tab_signup:
            st.markdown("**Crea un nuovo account universitario**")
            st.info("L’email universitaria è usata solo per creare gruppi di studio. Nessun dato è condiviso con terzi.")

            email_reg = st.text_input("Email universitaria (@studenti.unibg.it)", key="signup_email")
            pwd1 = st.text_input("Password", type="password", key="signup_pwd1")
            pwd2 = st.text_input("Ripeti Password", type="password", key="signup_pwd2")

            consenso = st.checkbox(
                "Acconsento al trattamento dei miei dati (email, preferenze, partecipazione alle sessioni) ai sensi del GDPR 2016/679, esclusivamente per la creazione di gruppi di studio.",
                key="signup_consent"
            )

            if st.button("Crea account"):
                if not email_reg or not pwd1 or not pwd2:
                    st.warning("Compila tutti i campi.")
                elif not email_reg.endswith("@studenti.unibg.it"):
                    st.error("Puoi registrarti solo con email universitaria (@studenti.unibg.it).")
                elif pwd1 != pwd2:
                    st.error("Le password non coincidono.")
                elif len(pwd1) < 6:
                    st.warning("La password deve avere almeno 6 caratteri.")
                elif not consenso:
                    st.error("Devi acconsentire al trattamento dati per procedere.")
                else:
                    try:
                        res = supabase.auth.sign_up({"email": email_reg, "password": pwd1})
                        if res.user:
                            try:
                                # Inserisce subito il consenso privacy nel profilo
                                supabase.table("profiles").upsert({
                                    "id": res.user.id,
                                    "email": email_reg,
                                    "role": "student",
                                    "consenso_privacy": True,
                                    "consenso_timestamp": datetime.now().isoformat(),
                                }, on_conflict="id").execute()
                            except Exception:
                                pass

                            st.success("✅ Registrazione completata! Controlla la mail se richiesta verifica, poi accedi.")
                        else:
                            st.warning("Errore durante la registrazione. Riprova.")
                    except Exception as e:
                        st.error(f"Errore registrazione: {e}")

    # --- Se l'utente È loggato ---
    else:
        user_email = getattr(st.session_state.auth_user, "email", None)
        if not user_email and isinstance(st.session_state.auth_user, dict):
            user_email = st.session_state.auth_user.get("email")

        if user_email:
            st.success(f"Connesso come {user_email}")
        else:
            st.warning("Utente connesso ma email non rilevata.")

        if st.button("Esci"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            # pulizia completa sessione e cookie
            for key in ["auth_user", "sb_access_token"]:
                if key in st.session_state:
                    del st.session_state[key]
            cookies.delete("sb_access_token")
            cookies.save()

            st.toast("👋 Logout completato", icon="🔒")
            st.query_params["status"] = "logout_done"
            st.rerun()


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

    # --- Verifica login e mostra utente ---
    require_login()
    user_obj = st.session_state.auth_user

    user_email = getattr(user_obj, "email", None)
    if not user_email and isinstance(user_obj, dict):
        user_email = user_obj.get("email")

    if user_email:
        st.markdown(
            f"<div style='color:green;font-weight:bold'>Connesso come {user_email}</div>",
            unsafe_allow_html=True
        )
    else:
        st.warning("Utente connesso ma email non disponibile.")

    user_id = getattr(user_obj, "id", None) or user_obj.get("id")

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
                "email": user_email,
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

    profile = load_profile(user_id)
    if profile:
        consenso_txt = (
            f"✅ Consenso privacy registrato il {profile.get('consenso_timestamp')[:10]}"
            if profile.get("consenso_privacy")
            else "❌ Consenso privacy non presente"
        )
        st.caption(consenso_txt)

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Nome:** {profile.get('nome','—')}")
            st.write(f"**Corso:** {profile.get('corso','—')}")
            st.write(f"**Approccio:** {profile.get('approccio','—')}")
        with col2:
            st.write(f"**Materie fatte:** {', '.join(profile.get('materie_fatte',[]) or ['—'])}")
            st.write(f"**Materie da fare:** {', '.join(profile.get('materie_dafare',[]) or ['—'])}")

        st.markdown("**🎯 Obiettivi accademici:**")
        st.write(", ".join(profile.get("obiettivi",[]) or ["—"]))

        st.markdown("**🎨 Hobby principali:**")
        hobby = profile.get("hobby", [])
        if isinstance(hobby, str):
            try:
                import json
                hobby = json.loads(hobby)
            except Exception:
                hobby = [hobby]
        st.write(", ".join(hobby or ["—"]))

        st.markdown("---")
        st.markdown("**📦 Dati completi (debug):**")
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
                    "attiva": True,  # ✅ nuova colonna
                    "chiusa_il": None,  # ✅ nuova colonna
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
        data_list = res.data or []

        if data_list:
            for s in data_list:
                nome = s.get("nome", "—")
                attiva = s.get("attiva", True)
                tema = s.get("tema", "")
                materia = s.get("materia", "")
                data_s = s.get("data", "")
                link = s.get("link_pubblico", "")
                status = "🟢 Attiva" if attiva else f"🔴 Chiusa il {str(s.get('chiusa_il',''))[:10]}"

                st.markdown(
                    f"**{nome}** | {tema} | {materia} | 📅 {data_s} | [{link}]({link}) | {status}"
                )

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"📕 Chiudi '{nome}'", key=f"chiudi_{s['id']}"):
                        supabase.table("sessioni").update({
                            "attiva": False,
                            "chiusa_il": datetime.now().isoformat(),
                        }).eq("id", s["id"]).execute()
                        st.success(f"Sessione '{nome}' chiusa.")
                        st.rerun()
                with col2:
                    if not attiva and st.button(f"♻️ Riapri '{nome}'", key=f"riapri_{s['id']}"):
                        supabase.table("sessioni").update({
                            "attiva": True,
                            "chiusa_il": None,
                        }).eq("id", s["id"]).execute()
                        st.info(f"Sessione '{nome}' riaperta.")
                        st.rerun()
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
    session_id = None
    if "session_id" in st.query_params:
        value = st.query_params["session_id"]
        session_id = value[0] if isinstance(value, list) else value


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

    # =====================================================
    # 🔀 CREAZIONE E CANCELLAZIONE GRUPPI (Matching Intelligente)
    # =====================================================

    def crea_gruppi_da_sessione(session_id, size=4):
        try:
            # 🔸 Recupera informazioni della sessione
            res_sess = supabase.table("sessioni").select("tema").eq("id", session_id).execute()
            sessione = res_sess.data[0] if res_sess.data else {"tema": "Generico"}
            tema = sessione.get("tema", "Generico")

            # 🔸 Elimina eventuali gruppi già presenti per la sessione
            supabase.table("gruppi").delete().eq("sessione_id", session_id).execute()

            # 🔸 Recupera i partecipanti iscritti
            res_part = supabase.table("participants").select("user_id").eq("session_id", session_id).execute()
            ids = [p["user_id"] for p in (res_part.data or []) if p.get("user_id")]
            if not ids:
                st.warning("Nessun partecipante iscritto.")
                return

            # 🔸 Recupera i profili completi
            res_prof = supabase.table("profiles").select("id,nome,hobby,approccio").in_("id", ids).execute()
            profili = res_prof.data or []
            if not profili:
                st.warning("Nessun profilo trovato per i partecipanti.")
                return

            # --- Funzione di similarità (hobby + approccio) ---
            def similarita(p1, p2):
                import json
                def normalizza_hobby(x):
                    if isinstance(x, str):
                        try:
                            x = json.loads(x)
                        except Exception:
                            x = [x]
                    if not isinstance(x, list):
                        x = [x]
                    return set(map(str, x))

                h1, h2 = normalizza_hobby(p1.get("hobby", [])), normalizza_hobby(p2.get("hobby", []))
                inter = len(h1 & h2)
                tot = len(h1 | h2)
                sim_hobby = inter / tot if tot else 0
                sim_approccio = 1 if p1.get("approccio") == p2.get("approccio") else 0
                return 0.7 * sim_hobby + 0.3 * sim_approccio  # 70% hobby + 30% approccio

            # --- Calcola la similarità media di ogni studente ---
            score_medio = {}
            for p in profili:
                altri = [similarita(p, q) for q in profili if q["id"] != p["id"]]
                score_medio[p["id"]] = sum(altri) / len(altri) if altri else 0

            # --- Ordina studenti per affinità media ---
            profili = sorted(profili, key=lambda x: score_medio[x["id"]], reverse=True)

            # --- Divide in gruppi di dimensione "size" ---
            gruppi = [profili[i:i + size] for i in range(0, len(profili), size)]
            nomi_tema = temi_gruppi.get(tema, [f"Gruppo{i+1}" for i in range(len(gruppi))])

            # --- Inserisce i gruppi nel DB ---
            for i, gruppo in enumerate(gruppi):
                membri = [p["id"] for p in gruppo]
                nome_gruppo = nomi_tema[i % len(nomi_tema)]
                supabase.table("gruppi").insert({
                    "sessione_id": session_id,
                    "nome_gruppo": nome_gruppo,
                    "membri": membri,
                    "tema": tema,
                    "data_creazione": datetime.now().isoformat(),
                }).execute()

            st.success(f"✅ Creati {len(gruppi)} gruppi ottimizzati per affinità (hobby + approccio).")

        except Exception as e:
            st.error(f"Errore nella creazione gruppi: {e}")

    # =====================================================
    # 🗑️ CANCELLAZIONE GRUPPI
    # =====================================================
    def cancella_gruppi_da_sessione(session_id):
        """Elimina tutti i gruppi della sessione corrente."""
        try:
            supabase.table("gruppi").delete().eq("sessione_id", session_id).execute()
            st.warning("🗑️ Tutti i gruppi di questa sessione sono stati eliminati.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Errore durante l'eliminazione dei gruppi: {e}")

    # =====================================================
    # 🔘 PULSANTI AZIONE
    # =====================================================
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤝 Crea gruppi ora (Matching AI)"):
            crea_gruppi_da_sessione(session_id)
    with col2:
        if st.button("🗑️ Cancella gruppi"):
            cancella_gruppi_da_sessione(session_id)

    # =====================================================
# 📋 GRUPPI ESISTENTI — vista compatta a schede
# =====================================================
st.markdown("---")
st.subheader("📋 Gruppi creati")

# CSS rapido per ridurre spazi
st.markdown("""
<style>
h3, h4, .stCaption, .stMarkdown { margin-bottom:.2rem; }
div.stExpander { border:1px solid #2a2a2a; border-radius:8px; margin:.25rem 0; }
div.stExpander > div > div { padding:.25rem .5rem; }
</style>
""", unsafe_allow_html=True)

# 🔁 Aggiornamento periodico leggero
try:
    if hasattr(st, "autorefresh"):
        st.autorefresh(interval=15000, key="refresh_gruppi")
except Exception:
    pass

try:
    res = supabase.table("gruppi").select("*").eq("sessione_id", session_id).execute()
    gruppi_data = res.data or []
except Exception as e:
    st.error(f"Errore nel caricamento gruppi: {e}")
    gruppi_data = []

if not gruppi_data:
    st.info("Nessun gruppo ancora creato.")
else:
    # griglia 2 colonne per occupare meno spazio in verticale
    cols = st.columns(2)
    for i, g in enumerate(gruppi_data):
        with cols[i % 2]:
            nome_gruppo = g.get("nome_gruppo", "—")
            tema = g.get("tema", "—")
            membri_ids = g.get("membri", []) or []

            st.markdown(f"### {nome_gruppo} — *Tema:* {tema}")
            st.caption(f"👥 Membri: {len(membri_ids)}")

            # dettagli minimali solo su richiesta
            with st.expander("Dettagli"):
                try:
                    if membri_ids:
                        res_prof = supabase.table("profiles").select("nome,hobby").in_("id", membri_ids).execute()
                        profili = res_prof.data or []
                        for p in profili:
                            nome = p.get("nome") or "Sconosciuto"
                            h = p.get("hobby", [])
                            if isinstance(h, str):
                                try:
                                    import json
                                    h = json.loads(h)
                                except Exception:
                                    h = [h]
                            elif not isinstance(h, list):
                                h = [str(h)]
                            st.markdown(f"• **{nome}** — 🎨 {', '.join(h or ['—'])}")
                    else:
                        st.info("Nessun membro in questo gruppo.")
                except Exception as e:
                    st.error(f"Errore dettagli gruppo: {e}")

    
# =====================================================
# 📊 DASHBOARD TOTALE SESSIONE — filtro unico
# =====================================================
import pandas as pd
import matplotlib.pyplot as plt

st.markdown("---")
st.subheader("📊 Dashboard sessione")

# prendi TUTTI i profili dei partecipanti della sessione in un'unica query
try:
    res_part = supabase.table("participants").select("user_id").eq("session_id", session_id).execute()
    all_ids = sorted({p["user_id"] for p in (res_part.data or []) if p.get("user_id")})
    if all_ids:
        res_prof = supabase.table("profiles").select(
            "id,approccio,hobby,materie_fatte,materie_dafare,obiettivi"
        ).in_("id", all_ids).execute()
        profili = res_prof.data or []
    else:
        profili = []
except Exception as e:
    st.error(f"Errore caricamento profili per dashboard: {e}")
    profili = []

if not profili:
    st.info("Nessun dato da visualizzare.")
else:
    metrica = st.selectbox(
        "Mostra distribuzione di:",
        [
            "Hobby",
            "Materie già superate",
            "Materie ancora da sostenere",
            "Obiettivi accademici",
            "Approccio allo studio",
        ],
        index=0,
        help="Scegli cosa analizzare sul totale della sessione."
    )

    # normalizzazione campi lista
    def norm_list(x):
        if isinstance(x, str):
            try:
                import json
                x = json.loads(x)
            except Exception:
                x = [x]
        if x is None:
            return []
        return x if isinstance(x, list) else [str(x)]

    items = []
    label = ""
    if metrica == "Hobby":
        label = "Hobby"
        for p in profili:
            items += norm_list(p.get("hobby"))
    elif metrica == "Materie già superate":
        label = "Materie"
        for p in profili:
            items += norm_list(p.get("materie_fatte"))
    elif metrica == "Materie ancora da sostenere":
        label = "Materie"
        for p in profili:
            items += norm_list(p.get("materie_dafare"))
    elif metrica == "Obiettivi accademici":
        label = "Obiettivi"
        for p in profili:
            items += norm_list(p.get("obiettivi"))
    else:  # Approccio allo studio
        label = "Approcci"
        for p in profili:
            v = p.get("approccio")
            if v:
                items.append(str(v))

    # conta e mostra top 12
    s = pd.Series([i for i in items if i]).value_counts().head(12)

    if s.empty:
        st.info("Nessun dato disponibile per la metrica selezionata.")
    else:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        s.sort_values(ascending=True).plot(kind="barh", ax=ax)
        ax.set_xlabel("Numero studenti")
        ax.set_ylabel(label)
        ax.set_title(f"Distribuzione {metrica.lower()} — totale sessione")
        st.pyplot(fig)

        # mini tabella riassuntiva
        st.caption("Valori principali")
        st.dataframe(
            pd.DataFrame({label: s.index, "n": s.values}),
            use_container_width=True,
            hide_index=True
        )

    # ---------------------------
# DEBUG: creazione / rimozione account "ghost" per test
# ---------------------------
import uuid, random, json
from datetime import datetime

def make_fake_profile():
    first = ["Luca","Marco","Giulia","Anna","Francesco","Sara","Paolo","Elisa","Matteo","Federica","Davide","Marta","Simone","Laura","Alessio","Chiara","Giorgio","Valentina","Riccardo","Martina"]
    last = ["Rossi","Bianchi","Verdi","Russo","Ferrari","Esposito","Romano","Gallo","Conti","Marino"]
    nome = f"{random.choice(first)} {random.choice(last)}"
    corso = random.choice(["Economia","Ingegneria","Matematica","Scienze"])
    materie = ["Economia","Statistica","Diritto","Microeconomia","Marketing","Finanza","Econometria","Gestione"]
    hobby_opts = ["Sport","Lettura","Musica","Viaggi","Videogiochi","Arte","Volontariato"]
    hobby = random.sample(hobby_opts, k=random.randint(0,3))
    approccio = random.choice(["Collaborativo","Individuale","Analitico","Pratico"])
    obiettivi = random.sample([
        "Passare gli esami a prescindere dal voto",
        "Raggiungere una media del 30",
        "Migliorare la comprensione delle materie",
        "Creare connessioni e fare gruppo",
        "Prepararmi per la carriera futura"
    ], k=random.randint(1,2))
    return {
        "id": str(uuid.uuid4()),
        "email": f"ghost_{uuid.uuid4().hex[:8]}@example.com",
        "nome": nome,
        "corso": corso,
        "materie_fatte": random.sample(materie, k=random.randint(0,3)),
        "materie_dafare": random.sample(materie, k=random.randint(0,3)),
        "hobby": hobby,
        "approccio": approccio,
        "obiettivi": obiettivi,
        "role": "ghost",
        "created_at": datetime.now().isoformat()
    }

def create_ghosts(n=20, session_id=None, add_as_participants=False):
    created = []
    try:
        batch = [make_fake_profile() for _ in range(n)]
        # insert in profiles
        for g in batch:
    # usa insert with upsert per evitare errore FK
            supabase.rpc("insert_ghost_profile", {
                "p_id": ghost_id,
                "p_email": email,
                "p_nome": nome,
                "p_corso": corso,
                "p_materie_fatte": [],
                "p_materie_dafare": [],
                "p_hobby": [],
                "p_approccio": "bilanciato",
                "p_obiettivi": [],
                "p_role": "ghost"
            }).execute()

        created = [p["id"] for p in batch]
        # optionally add to participants
        if session_id and add_as_participants:
            part_batch = []
            ts = datetime.now().isoformat()
            for pid in created:
                part_batch.append({"user_id": pid, "session_id": session_id, "joined_at": ts})
            supabase.table("participants").insert(part_batch).execute()
        return created
    except Exception as e:
        st.error(f"Errore creazione ghost: {e}")
        return []

def delete_ghosts():
    try:
        # recupera gli id dei ghost per pulizia participants
        rows = supabase.table("profiles").select("id").eq("role","ghost").execute()
        ids = [r["id"] for r in (rows.data or [])]
        if ids:
            supabase.table("participants").delete().in_("user_id", ids).execute()
        supabase.table("profiles").delete().eq("role","ghost").execute()
        return len(ids)
    except Exception as e:
        st.error(f"Errore rimozione ghost: {e}")
        return 0

# =====================================================
# ⚙️ DEBUG: CREAZIONE / RIMOZIONE GHOST USERS (solo test)
# =====================================================
import uuid

def create_ghosts(n=10, session_id=None, add_as_participants=False):
    """Crea utenti ghost di test creando prima l'utente in auth.users, poi in profiles."""
    created_ids = []
    try:
        for i in range(n):
            nome = f"Ghost User {i+1}"
            email = f"ghost{i+1}@syntia.fake"
            corso = "Test Corso"

            # 🔹 1️⃣ Crea l'utente in Supabase Auth (serve service key!)
            res_user = supabase.auth.admin.create_user({
                "email": email,
                "password": "ghost123!",
                "email_confirm": True,
                "user_metadata": {"role": "ghost"}
            })

            if not res_user or not getattr(res_user, "user", None):
                st.warning(f"Utente ghost {email} non creato correttamente.")
                continue

            ghost_id = res_user.user.id  # UUID generato da auth.users

            # 🔹 2️⃣ Inserisci profilo in tabella 'profiles'
            supabase.table("profiles").insert({
                "id": ghost_id,
                "email": email,
                "nome": nome,
                "corso": corso,
                "materie_fatte": [],
                "materie_dafare": [],
                "hobby": [],
                "approccio": "bilanciato",
                "obiettivi": [],
                "role": "ghost",
                "created_at": datetime.now().isoformat(),
            }).execute()

            # 🔹 3️⃣ Aggiungi alla sessione se richiesto
            if add_as_participants and session_id:
                supabase.table("participants").insert({
                    "user_id": ghost_id,
                    "session_id": session_id,
                    "joined_at": datetime.now().isoformat(),
                }).execute()

            created_ids.append(ghost_id)

        return created_ids

    except Exception as e:
        st.error(f"Errore creazione ghost: {e}")
        return []


def delete_ghosts():
    """Elimina tutti i profili ghost e i relativi participants."""
    try:
        # Rimuove prima i partecipanti ghost
        res_prof = supabase.table("profiles").select("id").eq("role", "ghost").execute()
        ids = [r["id"] for r in res_prof.data] if res_prof.data else []

        if ids:
            supabase.table("participants").delete().in_("user_id", ids).execute()
            supabase.table("profiles").delete().in_("id", ids).execute()

        return len(ids)
    except Exception as e:
        st.error(f"Errore eliminazione ghost: {e}")
        return 0

# ---------- UI (interfaccia) ----------
st.markdown("---")
st.markdown("#### ⚙️ Debug: ghost accounts (solo test)")
enable = st.checkbox("Enable debug ghost tools (solo in locale/testing)", key="enable_ghost_tools")

if enable:
    col_a, col_b = st.columns([2,1])
    with col_a:
        n_ghost = st.number_input("Quanti ghost creare", min_value=1, max_value=200, value=20, step=1, key="ghost_n")
        sess_input = st.text_input("Sessione ID (se vuoi che i ghost entrino nella sessione)", value="", key="ghost_session")
        add_parts = st.checkbox("Aggiungi i ghost come participants alla sessione specificata", value=True, key="ghost_add_part")
    with col_b:
        if st.button("Crea ghost"):
            created = create_ghosts(
                n=int(n_ghost),
                session_id=(sess_input or None),
                add_as_participants=bool(add_parts and sess_input)
            )
            if created:
                st.success(f"✅ Creati {len(created)} ghost. Prime 5 IDs: {', '.join(created[:5])}")
                st.experimental_rerun()

    st.markdown(" ")
    if st.button("🗑️ Rimuovi tutti i ghost creati (role='ghost')"):
        removed = delete_ghosts()
        st.warning(f"🗑️ Eliminati {removed} ghost e relativi participants.")
        st.experimental_rerun()

    st.markdown("***")
    st.info("Uso: crea ghost per testare creazione gruppi, cancellali dopo i test. Non abilitare in produzione.")

    # =====================================================
# 📥 ESPORTAZIONE CSV GRUPPI (per docenti)
# =====================================================
import io
import pandas as pd

st.markdown("---")
st.subheader("📥 Esporta gruppi in CSV")

try:
    # Recupera gruppi e membri
    res_gr = supabase.table("gruppi").select("sessione_id,nome_gruppo,membri").eq("sessione_id", session_id).execute()
    gruppi = res_gr.data or []

    if not gruppi:
        st.info("Nessun gruppo disponibile per l'esportazione.")
    else:
        # Costruzione lista righe: sessione, gruppo, nome
        righe = []
        for g in gruppi:
            membri = g.get("membri", []) or []
            if not membri:
                continue
            # Recupera nomi partecipanti
            res_prof = supabase.table("profiles").select("id,nome").in_("id", membri).execute()
            for p in (res_prof.data or []):
                righe.append({
                    "Sessione": g.get("sessione_id", "—"),
                    "Nome gruppo": g.get("nome_gruppo", "—"),
                    "Nome partecipante": p.get("nome", "—")
                })

        if righe:
            df = pd.DataFrame(righe)
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")

            st.download_button(
                label="📥 Scarica CSV gruppi",
                data=csv_buffer.getvalue(),
                file_name=f"gruppi_sessione_{session_id}.csv",
                mime="text/csv"
            )
        else:
            st.info("Nessun partecipante trovato nei gruppi.")
except Exception as e:
    st.error(f"Errore durante l'esportazione: {e}")

