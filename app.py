"""
Streamlit application for login‑free group formation with Supabase.

Flow:
1. Docente crea la sessione (nome, materia, data, tema, dimensione gruppi).
2. Viene generato un link/QR per la sessione.
3. Studenti entrano con l'ID sessione e scelgono un PIN a 4 cifre.
4. Ogni studente compila il proprio profilo (alias, hobby, approccio, materie, obiettivi).
5. Il docente vede in tempo reale chi ha scansionato (nickname) e chi ha completato il profilo (pronti).
6. Il docente imposta i pesi di matching (hobby vs approccio) e crea i gruppi.
7. Una volta soddisfatto, il docente pubblica i gruppi.
8. Ogni studente vede il proprio gruppo con il nickname evidenziato.

Le informazioni sono salvate su Supabase senza necessità di login degli studenti.
"""

import streamlit as st
from supabase import create_client
from datetime import datetime
import uuid
import json
from io import BytesIO
import qrcode

# -----------------------------------------------------------------------------
#  Configurazione e connessione
# -----------------------------------------------------------------------------

# Configura la pagina Streamlit
st.set_page_config(page_title="Gruppi login‑free", page_icon="📚", layout="centered")

# Connetti a Supabase con la chiave di servizio (preferibile) o chiave anonima
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY", st.secrets.get("SUPABASE_ANON_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Dizionario per generare nomi di gruppi in base al tema
THEME_GROUP_NAMES = {
    "Anime": ["Akira", "Totoro", "Naruto", "Luffy", "Saitama", "Asuka", "Shinji", "Kenshin"],
    "Sport": ["Maradona", "Jordan", "Federer", "Bolt", "Ali", "Phelps", "Serena"],
    "Spazio": ["Apollo", "Orion", "Luna", "Cosmos", "Nova", "Mars"],
    "Natura": ["Quercia", "Rosa", "Vento", "Onda", "Sole", "Mare", "Cielo"],
    "Tecnologia": ["Byte", "Pixel", "Quantum", "Neural", "Circuit", "Code"],
    "Storia": ["Roma", "Atene", "Sparta", "Troia", "Cartagine", "Babilonia"],
    "Mitologia": ["Zeus", "Athena", "Thor", "Ra", "Anubi", "Odino"],
}

# -----------------------------------------------------------------------------
#  Funzioni di utilità
# -----------------------------------------------------------------------------

def build_join_url(session_id: str) -> str:
    """Restituisce un URL pubblico per la sessione corrente."""
    base = st.secrets.get("PUBLIC_URL", st.secrets.get("PUBLIC_BASE_URL", "http://localhost:8501"))
    if not base.endswith("/"):
        base += "/"
    return f"{base}?session_id={session_id}"


def generate_session_id() -> str:
    """Genera un ID alfanumerico di 8 caratteri per la sessione."""
    return str(uuid.uuid4())[:8]


def get_nicknames(session_id: str):
    """Recupera tutti i record della tabella 'nicknames' per la sessione."""
    try:
        res = supabase.table("nicknames").select("id, code4, nickname, created_at").eq("session_id", session_id).execute()
        return res.data or []
    except Exception:
        return []


def get_ready_ids(session_id: str):
    """Restituisce l'insieme degli ID nickname che hanno un profilo associato."""
    nicks = get_nicknames(session_id)
    nick_ids = [n["id"] for n in nicks]
    if not nick_ids:
        return set()
    try:
        res = supabase.table("profiles").select("id").in_("id", nick_ids).execute()
        return set([r["id"] for r in (res.data or [])])
    except Exception:
        return set()


def create_session_db(nome: str, materia: str, data_sessione, tema: str):
    """Crea una sessione nella tabella 'sessioni'."""
    sid = generate_session_id()
    link_pubblico = build_join_url(sid)
    record = {
        "id": sid,
        "nome": nome,
        "materia": materia,
        "data": str(data_sessione),
        "tema": tema,
        "link_pubblico": link_pubblico,
        "creato_da": "public",
        "timestamp": datetime.now().isoformat(),
        "attiva": True,
        "chiusa_il": None,
    }
    supabase.table("sessioni").insert(record).execute()
    return sid


def create_nickname(session_id: str, code4: int):
    """Crea un record nella tabella 'nicknames' con il codice a 4 cifre."""
    # Verifica univocità del PIN per la sessione
    res_check = supabase.table("nicknames").select("id").eq("session_id", session_id).eq("code4", code4).execute()
    if res_check.data:
        raise ValueError("PIN già in uso in questa sessione")
    payload = {
        "session_id": session_id,
        "code4": code4,
        "nickname": None,
        "created_at": datetime.now().isoformat(),
    }
    res = supabase.table("nicknames").insert(payload).execute()
    if res.data:
        return res.data[0]
    raise RuntimeError("Impossibile creare nickname")


def save_profile(nickname_id: str, alias: str, approccio: str, hobby: list[str], materie_fatte: list[str], materie_dafare: list[str], obiettivi: list[str]):
    """Salva o aggiorna il profilo utente e aggiorna il nickname nella tabella 'nicknames'."""
    record = {
        "id": nickname_id,
        "nickname": alias,
        "approccio": approccio,
        "hobby": hobby,
        "materie_fatte": materie_fatte,
        "materie_dafare": materie_dafare,
        "obiettivi": obiettivi,
        "created_at": datetime.now().isoformat(),
    }
    try:
        existing = supabase.table("profiles").select("id").eq("id", nickname_id).execute()
        if existing.data:
            supabase.table("profiles").update(record).eq("id", nickname_id).execute()
        else:
            supabase.table("profiles").insert(record).execute()
    except Exception as e:
        st.warning(f"Errore nel salvataggio del profilo: {e}")
    # Aggiorna l'alias nel record nickname
    try:
        supabase.table("nicknames").update({"nickname": alias}).eq("id", nickname_id).execute()
    except Exception as e:
        st.warning(f"Errore nell'aggiornamento del nickname: {e}")


def compute_similarity(p1, p2, w_hobby: float, w_approccio: float) -> float:
    """Calcola la similarità tra due profili basandosi su hobby e approccio."""
    def normalize(x):
        if not x:
            return set()
        if isinstance(x, str):
            try:
                x = json.loads(x)
            except Exception:
                x = [x]
        if not isinstance(x, list):
            x = [x]
        return set(map(str, x))
    h1 = normalize(p1.get("hobby", []))
    h2 = normalize(p2.get("hobby", []))
    inter = len(h1 & h2)
    tot = len(h1 | h2)
    sim_hobby = inter / tot if tot else 0.0
    sim_approccio = 1.0 if p1.get("approccio") == p2.get("approccio") else 0.0
    return w_hobby * sim_hobby + w_approccio * sim_approccio


def create_groups(session_id: str, group_size: int, w_hobby: float, w_approccio: float):
    """Crea gruppi per la sessione in base ai pesi indicati."""
    nick_res = supabase.table("nicknames").select("id").eq("session_id", session_id).execute()
    nick_ids = [n["id"] for n in (nick_res.data or [])]
    if not nick_ids:
        st.warning("Nessun partecipante ha effettuato la scansione.")
        return
    prof_res = supabase.table("profiles").select("id, approccio, hobby").in_("id", nick_ids).execute()
    profiles = {p["id"]: p for p in (prof_res.data or [])}
    if not profiles:
        st.warning("Nessun profilo completato. Non è possibile creare i gruppi.")
        return
    students = list(profiles.values())
    # Calcola la similarità media per ogni profilo
    avg_score = {}
    for p in students:
        scores = [compute_similarity(p, q, w_hobby, w_approccio) for q in students if q["id"] != p["id"]]
        avg_score[p["id"]] = sum(scores) / len(scores) if scores else 0.0
    # Ordina per punteggio decrescente
    students.sort(key=lambda x: avg_score[x["id"]], reverse=True)
    # Suddivide in gruppi
    groups = [students[i : i + group_size] for i in range(0, len(students), group_size)]
    # Recupera tema della sessione
    sess_res = supabase.table("sessioni").select("tema").eq("id", session_id).execute()
    theme = sess_res.data[0]["tema"] if sess_res.data else "Generico"
    names_pool = THEME_GROUP_NAMES.get(theme, [f"Gruppo {i+1}" for i in range(len(groups))])
    # Cancella eventuali gruppi esistenti
    supabase.table("gruppi").delete().eq("sessione_id", session_id).execute()
    # Inserisce i nuovi gruppi
    for idx, grp in enumerate(groups):
        membri_ids = [p["id"] for p in grp]
        nome = names_pool[idx % len(names_pool)]
        record = {
            "sessione_id": session_id,
            "nome_gruppo": nome,
            "membri": membri_ids,
            "tema": theme,
            "data_creazione": datetime.now().isoformat(),
            "pesi": {"hobby": w_hobby, "approccio": w_approccio},
        }
        supabase.table("gruppi").insert(record).execute()
    st.success(f"Creati {len(groups)} gruppi basati sui pesi selezionati.")
    # Segna come non pubblicati nello stato locale
    published = st.session_state.setdefault("published_sessions", {})
    published[session_id] = False


def publish_groups(session_id: str):
    """Segna i gruppi come pubblicati nello stato locale."""
    published = st.session_state.setdefault("published_sessions", {})
    published[session_id] = True
    st.success("Gruppi pubblicati!")


def get_user_group(session_id: str, nickname_id: str):
    """Ritorna il gruppo in cui si trova il nickname, oppure None."""
    try:
        res = supabase.table("gruppi").select("nome_gruppo, membri").eq("sessione_id", session_id).execute()
        for g in res.data or []:
            if nickname_id in (g.get("membri") or []):
                return g
    except Exception:
        pass
    return None


# -----------------------------------------------------------------------------
#  INTERFACCIA UTENTE
# -----------------------------------------------------------------------------

st.title("🎓 App Gruppi login‑free")

# Tab di navigazione principale: Docente vs Studente
tab_teacher, tab_student = st.tabs(["👩‍🏫 Docente", "👤 Studente"])


with tab_teacher:
    """
    Vista per il docente. Permette di creare sessioni, vedere la lobby, regolare i pesi,
    creare e pubblicare i gruppi.
    """
    st.header("Gestisci la sessione")
    teacher_sid = st.session_state.get("teacher_session_id")
    # Se non c'è una sessione corrente, mostra il form di creazione
    if not teacher_sid:
        st.subheader("Crea una nuova sessione")
        nome = st.text_input("Nome sessione", key="doc_nome")
        materia = st.text_input("Materia", key="doc_materia")
        data_sessione = st.date_input("Data", value=datetime.now().date(), key="doc_data")
        tema = st.selectbox("Tema", list(THEME_GROUP_NAMES.keys()), key="doc_tema")
        group_size = st.number_input("Dimensione gruppi", min_value=2, max_value=12, value=4, step=1, key="doc_gr_size")
        if st.button("📦 Crea sessione", key="doc_create_session"):
            if not nome.strip():
                st.error("Inserisci un nome valido per la sessione.")
            else:
                sid = create_session_db(nome, materia, data_sessione, tema)
                st.session_state["teacher_session_id"] = sid
                st.session_state["teacher_group_size"] = int(group_size)
                # inizializza stato pubblicazione
                published = st.session_state.setdefault("published_sessions", {})
                published[sid] = False
                st.success(f"Sessione '{nome}' creata con ID {sid}.")
    else:
        sid = teacher_sid
        # Mostra i dettagli della sessione corrente
        try:
            sess = supabase.table("sessioni").select("nome, materia, data, tema, link_pubblico").eq("id", sid).execute()
        except Exception:
            sess = None
        s = sess.data[0] if sess and sess.data else {}
        st.markdown(f"**ID sessione:** `{sid}`  ")
        st.markdown(f"**Nome:** {s.get('nome','')}  ")
        st.markdown(f"**Materia:** {s.get('materia','')}  ")
        st.markdown(f"**Data:** {s.get('data','')}  ")
        st.markdown(f"**Tema:** {s.get('tema','')}  ")
        st.markdown(f"**Dimensione gruppi:** {st.session_state.get('teacher_group_size', 4)}  ")
        join_url = s.get("link_pubblico", build_join_url(sid))
        # Mostra QR e link pubblico
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(join_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="QR per gli studenti", use_column_width=False)
        st.write("Link pubblico:")
        st.code(join_url)
        st.divider()
        # Lobby
        st.subheader("Lobby studenti")
        nicknames = get_nicknames(sid)
        ready_ids = get_ready_ids(sid)
        st.metric("Scansionati", len(nicknames))
        st.metric("Pronti", len(ready_ids))
        if nicknames:
            table_data = []
            for n in nicknames:
                pin = n.get("code4")
                alias = n.get("nickname") or "—"
                stato = "✅" if n.get("id") in ready_ids else "⏳"
                table_data.append({"PIN": f"{pin:04d}" if pin is not None else "----", "Alias": alias, "Pronto": stato})
            st.table(table_data)
        else:
            st.write("Nessuno studente ha ancora scansionato.")
        st.divider()
        # Imposta pesi
        st.subheader("Pesi per il matching")
        peso_hobby = st.slider("Peso hobby", 0.0, 1.0, 0.7, 0.05)
        peso_approccio = 1.0 - peso_hobby
        # Bottone per creare gruppi
        if st.button("🔀 Crea gruppi", key="doc_crea_gruppi"):
            size = st.session_state.get("teacher_group_size", 4)
            create_groups(sid, size, peso_hobby, peso_approccio)
        # Bottone per pubblicare
        if st.button("📢 Pubblica gruppi", key="doc_pubblica_gruppi"):
            publish_groups(sid)
        # Bottone per reset
        if st.button("♻️ Nuova sessione", key="doc_reset_session"):
            # Resetta lo stato
            st.session_state.pop("teacher_session_id", None)
            st.session_state.pop("teacher_group_size", None)
            st.experimental_rerun()
        st.divider()
        # Mostra i gruppi se presenti
        st.subheader("Gruppi creati")
        try:
            res = supabase.table("gruppi").select("nome_gruppo, membri").eq("sessione_id", sid).execute()
            gruppi_creati = res.data or []
        except Exception:
            gruppi_creati = []
        if not gruppi_creati:
            st.info("Nessun gruppo ancora creato.")
        else:
            # Mappa degli alias per i nickname
            all_ids = list({mid for g in gruppi_creati for mid in (g.get("membri") or [])})
            alias_map = {}
            if all_ids:
                try:
                    nick_res = supabase.table("nicknames").select("id, code4, nickname").in_("id", all_ids).execute()
                    for r in nick_res.data or []:
                        pin = r.get("code4")
                        alias_map[r["id"]] = r.get("nickname") or f"{pin:04d}"
                except Exception:
                    pass
            for g in gruppi_creati:
                st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**  ")
                members_names = [alias_map.get(mid, mid[:4]) for mid in (g.get("membri") or [])]
                st.write(", ".join(members_names))


with tab_student:
    """
    Vista per lo studente. Permette di inserire l'ID sessione, scegliere un PIN e
    compilare il profilo. Mostra il gruppo una volta pubblicato.
    """
    st.header("Partecipa alla sessione")
    # Legge il parametro session_id dagli URL (nuova API)
    qp = getattr(st, "query_params", {})
    qp_session = None
    if qp:
        qp_val = qp.get("session_id")
        if qp_val:
            qp_session = qp_val[0] if isinstance(qp_val, (list, tuple)) else qp_val
    # Input per l'ID sessione
    session_id_input = st.text_input("ID sessione", value=qp_session or "", max_chars=8, key="stu_session_input")
    # Memorizza l'ID in session_state
    if session_id_input:
        st.session_state["student_session_id"] = session_id_input
    # Sub-tabs per PIN e Profilo
    subtab_pin, subtab_profilo = st.tabs(["🔑 PIN", "📝 Profilo"])
    # Gestione del PIN
    with subtab_pin:
        if not session_id_input:
            st.info("Inserisci l'ID della sessione per procedere.")
        else:
            nickname_id = st.session_state.get("student_nickname_id")
            nickname_session = st.session_state.get("student_session_id_cached")
            # Se non abbiamo ancora un nickname o la sessione è diversa, chiedi PIN
            if not nickname_id or nickname_session != session_id_input:
                pin_val = st.text_input("Scegli un PIN a 4 cifre", max_chars=4, key="stu_pin_input")
                if st.button("Conferma PIN", key="stu_confirm_pin"):
                    if not pin_val or not pin_val.isdigit() or len(pin_val) != 4:
                        st.error("Il PIN deve essere un numero di 4 cifre.")
                    else:
                        try:
                            new_nick = create_nickname(session_id_input, int(pin_val))
                            st.session_state["student_nickname_id"] = new_nick["id"]
                            st.session_state["student_session_id_cached"] = session_id_input
                            st.session_state["student_pin"] = pin_val
                            st.success("PIN confermato! Ora passa alla scheda Profilo per completare i dati.")
                        except Exception as e:
                            st.error(f"Errore durante la creazione del nickname: {e}")
            else:
                st.success("PIN già confermato. Puoi compilare il profilo nella scheda successiva.")
                st.write(f"Il tuo PIN: {st.session_state.get('student_pin', '—')}")
    # Gestione del profilo
    with subtab_profilo:
        # Verifica se lo studente ha un nickname creato
        nickname_id = st.session_state.get("student_nickname_id")
        if not nickname_id:
            st.info("Prima scegli un PIN nella scheda precedente.")
        else:
            # Carica profilo esistente
            try:
                prof_res = supabase.table("profiles").select("*").eq("id", nickname_id).execute()
                profile_data = prof_res.data[0] if prof_res.data else None
            except Exception:
                profile_data = None
            with st.form("stud_form_profilo"):
                # Alias: default al PIN se non impostato
                default_alias = profile_data.get("nickname") if profile_data else st.session_state.get("student_pin", "")
                alias = st.text_input("Alias (puoi usare il tuo PIN o un nome)", value=default_alias, max_chars=12)
                # Approccio
                approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
                selected_approccio = profile_data.get("approccio") if profile_data else approcci[0]
                approccio = st.selectbox("Approccio al lavoro di gruppo", approcci, index=approcci.index(selected_approccio) if selected_approccio in approcci else 0)
                # Hobby
                hobby_options = ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"]
                current_hobbies = []
                raw_h = profile_data.get("hobby") if profile_data else []
                if raw_h:
                    if isinstance(raw_h, list):
                        current_hobbies = raw_h
                    elif isinstance(raw_h, str):
                        try:
                            current_hobbies = json.loads(raw_h)
                        except Exception:
                            current_hobbies = [raw_h]
                hobbies = st.multiselect("Hobby", hobby_options, default=[h for h in current_hobbies if h in hobby_options])
                # Materie
                mf_default = ", ".join(profile_data.get("materie_fatte", [])) if profile_data else ""
                md_default = ", ".join(profile_data.get("materie_dafare", [])) if profile_data else ""
                materie_fatte_in = st.text_area("Materie già superate", value=mf_default)
                materie_dafare_in = st.text_area("Materie da fare", value=md_default)
                # Obiettivi
                obiettivi_opts = [
                    "Passare gli esami a prescindere dal voto",
                    "Raggiungere una media del 30",
                    "Migliorare la comprensione delle materie",
                    "Creare connessioni e fare gruppo",
                    "Prepararmi per la carriera futura",
                ]
                current_ob = []
                raw_o = profile_data.get("obiettivi") if profile_data else []
                if raw_o:
                    if isinstance(raw_o, list):
                        current_ob = raw_o
                    elif isinstance(raw_o, str):
                        try:
                            current_ob = json.loads(raw_o)
                        except Exception:
                            current_ob = [raw_o]
                obiettivi_sel = st.multiselect("Obiettivi accademici", options=obiettivi_opts, default=[o for o in current_ob if o in obiettivi_opts])
                invia = st.form_submit_button("💾 Salva profilo")
            if invia:
                mf_list = [m.strip() for m in materie_fatte_in.split(",") if m.strip()]
                md_list = [m.strip() for m in materie_dafare_in.split(",") if m.strip()]
                save_profile(nickname_id, alias or st.session_state.get("student_pin", ""), approccio, hobbies, mf_list, md_list, obiettivi_sel)
                st.success("Profilo salvato!")
            # Mostra il gruppo se pubblicato
            # Controlla lo stato locale di pubblicazione
            published = st.session_state.get("published_sessions", {}).get(st.session_state.get("student_session_id"))
            if published:
                g = get_user_group(st.session_state.get("student_session_id"), nickname_id)
                if g:
                    st.subheader("Il tuo gruppo")
                    st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**")
                    member_ids = g.get("membri") or []
                    alias_map = {}
                    if member_ids:
                        try:
                            nr = supabase.table("nicknames").select("id, code4, nickname").in_("id", member_ids).execute()
                            for r in nr.data or []:
                                alias_map[r["id"]] = r.get("nickname") or f"{r.get('code4'):04d}"
                        except Exception:
                            pass
                    members_display = []
                    for mid in member_ids:
                        name = alias_map.get(mid, mid[:4])
                        if mid == nickname_id:
                            members_display.append(f"**{name} (tu)**")
                        else:
                            members_display.append(name)
                    st.write(", ".join(members_display))
                else:
                    st.info("Non sei ancora assegnato a un gruppo.")