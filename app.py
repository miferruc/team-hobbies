"""
Gruppi login‑free con profilo esteso e matching multi‑parametro.

Questo modulo implementa una versione aggiornata dell’applicazione
Streamlit per la formazione di gruppi di studio senza login. È basata
sulla versione originale `app2.py`, ma aggiunge le seguenti
caratteristiche:

• Preimposta elenchi di materie per le sezioni "già superate" e "da fare".
• Introduce un nuovo campo di profilo "Dove mi vedo fra 5 anni" con
  opzioni (es. Manager, CEO, Imprenditore, Consulente, Ricercatore,
  Docente, Libero professionista, Altro). Per salvare questo campo è
  necessario aggiungere la colonna `future_role` alla tabella
  `profiles` su Supabase.
• Permette di impostare pesi di matching non solo per hobby e
  approccio, ma anche per materie, obiettivi e ruolo futuro. Il
  calcolo della similarità usa una versione estesa della funzione
  `compute_similarity` che combina le singole somiglianze pesate.
• Rinomina "PIN" in "nickname" ovunque nell’interfaccia.

Il flusso rimane identico:
1. Il docente crea una sessione e ottiene subito link pubblico e QR.
2. Gli studenti entrano con l’ID sessione e scelgono un nickname a 4
   cifre. Possono quindi compilare il profilo in un’apposita tab.
3. La lobby docente mostra quanti studenti hanno effettuato la scansione e
   quanti hanno completato il profilo. Il docente regola i pesi di
   matching, crea e pubblica i gruppi.
4. Gli studenti vedono il proprio gruppo una volta pubblicato.

Nota: per utilizzare correttamente il nuovo campo `future_role`, è
necessario aggiungerlo alla tabella `profiles` su Supabase. Se la
colonna non esiste, il salvataggio del profilo ignorerà questo campo.
"""

import json
import uuid
from datetime import datetime
from io import BytesIO

import streamlit as st
from supabase import create_client
import qrcode


# ----------------------------------------------------------------------------
# Configurazione e connessione
# ----------------------------------------------------------------------------

# Configura la pagina Streamlit
st.set_page_config(page_title="Gruppi login‑free", page_icon="📚", layout="centered")

# Connetti a Supabase con chiave di servizio o anonima
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY", st.secrets.get("SUPABASE_ANON_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# Lista predefinita di materie disponibili
SUBJECTS_OPTIONS = [
    "Economia Aziendale",
    "Statistica",
    "Diritto Privato",
    "Microeconomia",
    "Marketing",
    "Finanza",
    "Econometria",
    "Gestione Aziendale",
    "Macroeconomia",
    "Comunicazione",
    "Matematica",
    "Fisica",
    "Programmazione",
    "Chimica",
    "Biologia",
]

# Opzioni per la domanda "Dove mi vedo fra 5 anni"
FUTURE_ROLE_OPTIONS = [
    "Manager",
    "CEO",
    "Imprenditore",
    "Consulente",
    "Ricercatore",
    "Docente",
    "Libero professionista",
    "Altro",
]

# Nomi di gruppi in base al tema
THEME_GROUP_NAMES = {
    "Anime": ["Akira", "Totoro", "Naruto", "Luffy", "Saitama", "Asuka", "Shinji", "Kenshin"],
    "Sport": ["Maradona", "Jordan", "Federer", "Bolt", "Ali", "Phelps", "Serena"],
    "Spazio": ["Apollo", "Orion", "Luna", "Cosmos", "Nova", "Mars"],
    "Natura": ["Quercia", "Rosa", "Vento", "Onda", "Sole", "Mare", "Cielo"],
    "Tecnologia": ["Byte", "Pixel", "Quantum", "Neural", "Circuit", "Code"],
    "Storia": ["Roma", "Atene", "Sparta", "Troia", "Cartagine", "Babilonia"],
    "Mitologia": ["Zeus", "Athena", "Thor", "Ra", "Anubi", "Odino"],
}


# ----------------------------------------------------------------------------
# Funzioni di utilità
# ----------------------------------------------------------------------------

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
        res = (
            supabase.table("nicknames")
            .select("id, code4, nickname, created_at")
            .eq("session_id", session_id)
            .execute()
        )
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
    res_check = (
        supabase.table("nicknames").select("id").eq("session_id", session_id).eq("code4", code4).execute()
    )
    if res_check.data:
        raise ValueError("Questo nickname è già in uso in questa sessione")
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


def save_profile(
    nickname_id: str,
    alias: str,
    approccio: str,
    hobby: list,
    materie_fatte: list,
    materie_dafare: list,
    obiettivi: list,
    future_role: str,
):
    """Salva o aggiorna il profilo utente e aggiorna il nickname nella tabella 'nicknames'."""
    # Costruisci record da salvare nel profilo. Non include il campo 'nickname', che viene
    # salvato nella tabella 'nicknames'.
    record = {
        "id": nickname_id,
        "approccio": approccio,
        "hobby": hobby,
        "materie_fatte": materie_fatte,
        "materie_dafare": materie_dafare,
        "obiettivi": obiettivi,
        "future_role": future_role,
        "created_at": datetime.now().isoformat(),
    }
    # Salva o aggiorna la tabella 'profiles'. Se alcune colonne non esistono,
    # prova a rimuoverle gradualmente.
    try:
        existing = supabase.table("profiles").select("id").eq("id", nickname_id).execute()
        if existing.data:
            # Aggiorna profilo esistente
            try:
                supabase.table("profiles").update(record).eq("id", nickname_id).execute()
            except Exception:
                # fallback: prova senza 'future_role'
                alt_record = record.copy()
                alt_record.pop("future_role", None)
                supabase.table("profiles").update(alt_record).eq("id", nickname_id).execute()
        else:
            try:
                supabase.table("profiles").insert(record).execute()
            except Exception:
                # fallback: prova senza 'future_role'
                alt_record = record.copy()
                alt_record.pop("future_role", None)
                supabase.table("profiles").insert(alt_record).execute()
    except Exception as e:
        st.warning(f"Errore nel salvataggio del profilo: {e}")
    # Aggiorna l'alias nel record nickname
    try:
        supabase.table("nicknames").update({"nickname": alias}).eq("id", nickname_id).execute()
    except Exception as e:
        st.warning(f"Errore nell'aggiornamento del nickname: {e}")


def normalize_field(x) -> set:
    """Normalizza un campo hobby/materie/obiettivi in un set di stringhe."""
    if not x:
        return set()
    if isinstance(x, list):
        return set([str(i) for i in x])
    if isinstance(x, str):
        try:
            parsed = json.loads(x)
            if isinstance(parsed, list):
                return set([str(i) for i in parsed])
        except Exception:
            return {x}
    return {str(x)}


def compute_similarity_ext(p1, p2, weights: dict) -> float:
    """
    Calcola una misura di somiglianza tra due profili combinando
    hobby, approccio, materie, obiettivi e ruolo futuro. Ogni
    categoria è pesata secondo il dizionario `weights`.
    """
    score = 0.0
    # Hobby: Jaccard tra insiemi
    h1, h2 = normalize_field(p1.get("hobby")), normalize_field(p2.get("hobby"))
    if h1 or h2:
        score += weights.get("hobby", 0) * (len(h1 & h2) / len(h1 | h2))
    # Approccio: 1 se uguale
    if p1.get("approccio") and p2.get("approccio"):
        score += weights.get("approccio", 0) * (1.0 if p1["approccio"] == p2["approccio"] else 0.0)
    # Materie: unione di fatte+da fare
    m1 = normalize_field(p1.get("materie_fatte")) | normalize_field(p1.get("materie_dafare"))
    m2 = normalize_field(p2.get("materie_fatte")) | normalize_field(p2.get("materie_dafare"))
    if m1 or m2:
        score += weights.get("materie", 0) * (len(m1 & m2) / len(m1 | m2))
    # Obiettivi
    o1, o2 = normalize_field(p1.get("obiettivi")), normalize_field(p2.get("obiettivi"))
    if o1 or o2:
        score += weights.get("obiettivi", 0) * (len(o1 & o2) / len(o1 | o2))
    # Ruolo futuro
    fr1, fr2 = p1.get("future_role"), p2.get("future_role")
    if fr1 and fr2:
        score += weights.get("future_role", 0) * (1.0 if fr1 == fr2 else 0.0)
    return score


def create_groups_ext(session_id: str, group_size: int, weights: dict):
    """Crea gruppi in base ai pesi indicati."""
    # recupera tutti i nickname ID per la sessione
    nick_res = supabase.table("nicknames").select("id").eq("session_id", session_id).execute()
    nick_ids = [n["id"] for n in (nick_res.data or [])]
    if not nick_ids:
        st.warning("Nessun partecipante ha effettuato la scansione.")
        return
    # recupera profili per gli ID
    try:
        prof_res = (
            supabase.table("profiles")
            .select(
                "id, approccio, hobby, materie_fatte, materie_dafare, obiettivi, future_role"
            )
            .in_("id", nick_ids)
            .execute()
        )
    except Exception:
        # fallback senza future_role
        prof_res = (
            supabase.table("profiles")
            .select("id, approccio, hobby, materie_fatte, materie_dafare, obiettivi")
            .in_("id", nick_ids)
            .execute()
        )
    profiles = {p["id"]: p for p in (prof_res.data or [])}
    if not profiles:
        st.warning("Nessun profilo completato. Non è possibile creare i gruppi.")
        return
    # lista di profili presenti (ignora i nickname senza profilo)
    students = list(profiles.values())
    # calcola punteggio medio di similarità per ciascun studente
    avg_score = {}
    for p in students:
        scores = [compute_similarity_ext(p, q, weights) for q in students if q["id"] != p["id"]]
        avg_score[p["id"]] = sum(scores) / len(scores) if scores else 0.0
    # ordina studenti per punteggio decrescente
    students.sort(key=lambda x: avg_score[x["id"]], reverse=True)
    # suddivide in gruppi
    groups = [students[i : i + group_size] for i in range(0, len(students), group_size)]
    # recupera tema della sessione
    sess_res = supabase.table("sessioni").select("tema").eq("id", session_id).execute()
    theme = sess_res.data[0]["tema"] if sess_res.data else "Generico"
    names_pool = THEME_GROUP_NAMES.get(theme, [f"Gruppo {i+1}" for i in range(len(groups))])
    # cancella gruppi esistenti per la sessione
    try:
        supabase.table("gruppi").delete().eq("sessione_id", session_id).execute()
    except Exception:
        pass
    # inserisci nuovi gruppi
    for idx, grp in enumerate(groups):
        membri_ids = [p["id"] for p in grp]
        nome = names_pool[idx % len(names_pool)]
        record = {
            "sessione_id": session_id,
            "nome_gruppo": nome,
            "membri": membri_ids,
            "tema": theme,
            "data_creazione": datetime.now().isoformat(),
            "pesi": weights,
        }
        supabase.table("gruppi").insert(record).execute()
    st.success(f"Creati {len(groups)} gruppi basati sui pesi selezionati.")
    # marca come non pubblicati nello stato locale
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


# ----------------------------------------------------------------------------
# Interfaccia utente
# ----------------------------------------------------------------------------

st.title("🎓 App Gruppi login‑free")

# Tab di navigazione principale: Docente vs Studente
tab_teacher, tab_student = st.tabs(["👩‍🏫 Docente", "👤 Studente"])


with tab_teacher:
    """
    Vista per il docente. Permette di creare sessioni, vedere la lobby,
    regolare i pesi per tutte le categorie e creare/pubblicare i gruppi.
    """
    st.header("Gestisci la sessione")
    teacher_sid = st.session_state.get("teacher_session_id")
    # se non c'è sessione corrente, mostra il form di creazione
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
                # crea la sessione nel DB
                sid = create_session_db(nome, materia, data_sessione, tema)
                st.session_state["teacher_session_id"] = sid
                st.session_state["teacher_group_size"] = int(group_size)
                # inizializza stato pubblicazione
                published = st.session_state.setdefault("published_sessions", {})
                published[sid] = False
                st.success(f"Sessione '{nome}' creata con ID {sid}.")
                # Ricarica l'app per mostrare subito i dettagli e il QR della sessione
                st.experimental_rerun()
    else:
        sid = teacher_sid
        # mostra i dettagli della sessione corrente
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
        # mostra QR e link
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(join_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        # Usa use_container_width per evitare deprecazione di use_column_width
        st.image(buf.getvalue(), caption="QR per gli studenti", use_container_width=False)
        st.write("Link pubblico:")
        st.code(join_url)
        st.divider()
        # lobby
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
                table_data.append({"Nickname": f"{pin:04d}" if pin is not None else "----", "Alias": alias, "Pronto": stato})
            st.table(table_data)
        else:
            st.write("Nessuno studente ha ancora scansionato.")
        st.divider()
        # pesi
        st.subheader("Pesi per il matching")
        peso_hobby = st.slider("Peso hobby", 0.0, 1.0, 0.7, 0.05)
        peso_approccio = st.slider("Peso approccio", 0.0, 1.0, 0.3, 0.05)
        peso_materie = st.slider("Peso materie", 0.0, 1.0, 0.3, 0.05)
        peso_obiettivi = st.slider("Peso obiettivi", 0.0, 1.0, 0.3, 0.05)
        peso_future_role = st.slider("Peso ruolo futuro", 0.0, 1.0, 0.3, 0.05)
        weights = {
            "hobby": peso_hobby,
            "approccio": peso_approccio,
            "materie": peso_materie,
            "obiettivi": peso_obiettivi,
            "future_role": peso_future_role,
        }
        # bottoni
        col1, col2, col3 = st.columns(3)
        if col1.button("🔀 Crea gruppi", key="doc_crea_gruppi"):
            size = st.session_state.get("teacher_group_size", 4)
            create_groups_ext(sid, size, weights)
        if col2.button("📢 Pubblica gruppi", key="doc_pubblica_gruppi"):
            publish_groups(sid)
        if col3.button("♻️ Nuova sessione", key="doc_reset_session"):
            st.session_state.pop("teacher_session_id", None)
            st.session_state.pop("teacher_group_size", None)
            st.experimental_rerun()
        st.divider()
        # mostra i gruppi se creati
        st.subheader("Gruppi creati")
        try:
            res = (
                supabase.table("gruppi")
                .select("nome_gruppo, membri")
                .eq("sessione_id", sid)
                .execute()
            )
            gruppi_creati = res.data or []
        except Exception:
            gruppi_creati = []
        if not gruppi_creati:
            st.info("Nessun gruppo ancora creato.")
        else:
            # mappa alias
            all_ids = list({mid for g in gruppi_creati for mid in (g.get("membri") or [])})
            alias_map = {}
            if all_ids:
                try:
                    nick_res = (
                        supabase.table("nicknames")
                        .select("id, code4, nickname")
                        .in_("id", all_ids)
                        .execute()
                    )
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
    Vista per lo studente. Permette di inserire l'ID sessione, scegliere un
    nickname a 4 cifre e compilare il profilo. Mostra il gruppo una volta
    pubblicato.
    """
    st.header("Partecipa alla sessione")
    # leggi parametri query
    qp = getattr(st, "query_params", {})
    qp_session = None
    if qp:
        qp_val = qp.get("session_id")
        if qp_val:
            qp_session = qp_val[0] if isinstance(qp_val, (list, tuple)) else qp_val
    # input id sessione
    session_id_input = st.text_input(
        "ID sessione", value=qp_session or "", max_chars=8, key="stu_session_input"
    )
    if session_id_input:
        st.session_state["student_session_id"] = session_id_input
    # sub‑tabs per nickname e profilo
    subtab_pin, subtab_profilo = st.tabs(["🔑 Nickname", "📝 Profilo"])
    # gestione del nickname
    with subtab_pin:
        if not session_id_input:
            st.info("Inserisci l'ID della sessione per procedere.")
        else:
            nickname_id = st.session_state.get("student_nickname_id")
            nickname_session = st.session_state.get("student_session_id_cached")
            if not nickname_id or nickname_session != session_id_input:
                nick_val = st.text_input(
                    "Scegli un nickname (4 cifre)",
                    max_chars=4,
                    key="stu_pin_input",
                )
                if st.button("Conferma nickname", key="stu_confirm_pin"):
                    if not nick_val or not nick_val.isdigit() or len(nick_val) != 4:
                        st.error("Il nickname deve essere un numero di 4 cifre.")
                    else:
                        try:
                            new_nick = create_nickname(session_id_input, int(nick_val))
                            st.session_state["student_nickname_id"] = new_nick["id"]
                            st.session_state["student_session_id_cached"] = session_id_input
                            st.session_state["student_pin"] = nick_val
                            st.success("Nickname confermato! Ora passa alla scheda Profilo per completare i dati.")
                        except Exception as e:
                            st.error(f"Errore durante la creazione del nickname: {e}")
            else:
                st.success("Nickname già confermato. Puoi compilare il profilo nella scheda successiva.")
                st.write(f"Il tuo nickname: {st.session_state.get('student_pin', '—')}")
    # gestione del profilo
    with subtab_profilo:
        nickname_id = st.session_state.get("student_nickname_id")
        if not nickname_id:
            st.info("Prima scegli un nickname nella scheda precedente.")
        else:
            # carica profilo esistente
            try:
                prof_res = supabase.table("profiles").select("*").eq("id", nickname_id).execute()
                profile_data = prof_res.data[0] if prof_res.data else None
            except Exception:
                profile_data = None
            with st.form("stud_form_profilo"):
                # alias: default al nickname se non impostato
                default_alias = (
                    profile_data.get("nickname")
                    if profile_data
                    else st.session_state.get("student_pin", "")
                )
                alias = st.text_input(
                    "Alias (puoi usare il tuo nickname o un nome)",
                    value=default_alias,
                    max_chars=12,
                )
                # approccio
                approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
                selected_app = (
                    profile_data.get("approccio")
                    if profile_data
                    else approcci[0]
                )
                approccio = st.selectbox(
                    "Approccio al lavoro di gruppo",
                    approcci,
                    index=approcci.index(selected_app) if selected_app in approcci else 0,
                )
                # hobby
                hobby_options = [
                    "Sport",
                    "Lettura",
                    "Musica",
                    "Viaggi",
                    "Videogiochi",
                    "Arte",
                    "Volontariato",
                    "Cucina",
                    "Fotografia",
                    "Cinema",
                ]
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
                hobbies = st.multiselect(
                    "Hobby",
                    hobby_options,
                    default=[h for h in current_hobbies if h in hobby_options],
                )
                # materie già superate
                current_fatte = []
                raw_fatte = profile_data.get("materie_fatte") if profile_data else []
                if raw_fatte:
                    if isinstance(raw_fatte, list):
                        current_fatte = raw_fatte
                    elif isinstance(raw_fatte, str):
                        try:
                            current_fatte = json.loads(raw_fatte)
                        except Exception:
                            current_fatte = [raw_fatte]
                materie_fatte = st.multiselect(
                    "Materie già superate",
                    options=SUBJECTS_OPTIONS,
                    default=[m for m in current_fatte if m in SUBJECTS_OPTIONS],
                )
                # materie da fare
                current_dafare = []
                raw_dafare = profile_data.get("materie_dafare") if profile_data else []
                if raw_dafare:
                    if isinstance(raw_dafare, list):
                        current_dafare = raw_dafare
                    elif isinstance(raw_dafare, str):
                        try:
                            current_dafare = json.loads(raw_dafare)
                        except Exception:
                            current_dafare = [raw_dafare]
                # le materie da fare non devono includere quelle già fatte
                available_dafare = [m for m in SUBJECTS_OPTIONS if m not in materie_fatte]
                materie_dafare = st.multiselect(
                    "Materie da fare",
                    options=available_dafare,
                    default=[m for m in current_dafare if m in available_dafare],
                )
                # obiettivi
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
                obiettivi_sel = st.multiselect(
                    "Obiettivi accademici",
                    options=obiettivi_opts,
                    default=[o for o in current_ob if o in obiettivi_opts],
                )
                # dove mi vedo fra 5 anni
                fr_default = (
                    profile_data.get("future_role") if profile_data else FUTURE_ROLE_OPTIONS[0]
                )
                future_role = st.selectbox(
                    "Dove mi vedo fra 5 anni",
                    options=FUTURE_ROLE_OPTIONS,
                    index=FUTURE_ROLE_OPTIONS.index(fr_default) if fr_default in FUTURE_ROLE_OPTIONS else 0,
                )
                invia = st.form_submit_button("💾 Salva profilo")
            if invia:
                save_profile(
                    nickname_id,
                    alias or st.session_state.get("student_pin", ""),
                    approccio,
                    hobbies,
                    materie_fatte,
                    materie_dafare,
                    obiettivi_sel,
                    future_role,
                )
                st.success("Profilo salvato!")
            # mostra gruppo se pubblicato
            published = st.session_state.get("published_sessions", {}).get(
                st.session_state.get("student_session_id")
            )
            if published:
                g = get_user_group(st.session_state.get("student_session_id"), nickname_id)
                if g:
                    st.subheader("Il tuo gruppo")
                    st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**")
                    member_ids = g.get("membri") or []
                    alias_map = {}
                    if member_ids:
                        try:
                            nr = (
                                supabase.table("nicknames")
                                .select("id, code4, nickname")
                                .in_("id", member_ids)
                                .execute()
                            )
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