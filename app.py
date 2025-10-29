"""
App Gruppi login‑free – nuova implementazione

Questo file implementa un’applicazione Streamlit che permette di creare
sessioni per la formazione di gruppi di studio senza necessità di login.
Il flusso completo è:

  1. Il docente crea una nuova sessione inserendo nome, materia, data,
     tema e dimensione dei gruppi. Dopo la creazione vengono mostrati
     l’ID della sessione, il link pubblico e il QR code da condividere
     con gli studenti.

  2. Gli studenti accedono alla sezione *Studente*, inseriscono
     l’ID della sessione ricevuto e scelgono un nickname numerico a
     4 cifre (da utilizzare come identificativo). Una volta confermato,
     possono compilare un profilo personale su tre tab: alias
     (facoltativo), interessi/approccio/materie, obiettivi e dove si
     vedono fra cinque anni.

  3. Il docente può monitorare in tempo reale quanti studenti hanno
     scansionato il QR (o inserito l’ID) e quanti hanno completato il
     profilo. Al momento opportuno può impostare i pesi per il
     matching (hobby, approccio, materie, obiettivi, posizione futura)
     e generare i gruppi di studio, che vengono salvati in Supabase.

  4. Quando i gruppi sono pronti e pubblicati, gli studenti possono
     visualizzare il proprio gruppo nella sezione *Profilo* con il loro
     nickname evidenziato.

Per il corretto funzionamento è necessario che il database Supabase
contenga le seguenti tabelle:
  • `sessioni` con colonne `id` (text), `nome` (text), `materia` (text),
    `data` (text), `tema` (text), `created_at` (timestamp).
  • `nicknames` con colonne `id` (uuid), `session_id` (text), `code4`
    (integer), `nickname` (text), `guest_id` (uuid), `created_at`
    (timestamp). La colonna `code4` deve essere univoca per sessione.
  • `profiles` con colonne `id` (uuid), `approccio` (text), `hobby`
    (json or text), `materie_fatte` (json or text), `materie_dafare`
    (json or text), `obiettivi` (json or text), `future_role` (text),
    `created_at` (timestamp). Si consiglia di rimuovere la colonna
    `nickname` se presente (non è più utilizzata) e di aggiungere la
    colonna `future_role` per la nuova domanda.
  • `gruppi` con colonne `id` (uuid), `session_id` (text), `nome`
    (text), `membri` (json or text), `theme` (text), `weights` (json),
    `created_at` (timestamp).

Se alcune colonne non sono presenti, è necessario aggiornarle su
Supabase prima di usare l’app (vedi README o istruzioni SQL).
"""

import io
import json
import random
import string
import uuid
from datetime import datetime

import streamlit as st
from supabase import create_client, Client

try:
    import qrcode  # QR code generation
except ImportError:
    qrcode = None


# -----------------------------------------------------------------------------
# 🔧 CONFIGURAZIONE INIZIALE
# -----------------------------------------------------------------------------

# Carica le credenziali da Streamlit secrets. Deve essere configurato in
# `.streamlit/secrets.toml` con SUPABASE_URL e SUPABASE_SERVICE_KEY.
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY")

@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    """Inizializza il client Supabase."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# -----------------------------------------------------------------------------
# 🧮 UTILITIES
# -----------------------------------------------------------------------------

def gen_session_id(length: int = 6) -> str:
    """Genera un ID di sessione alfanumerico di lunghezza fissa."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


def create_qr_code(data: str) -> bytes | None:
    """Restituisce i byte dell'immagine PNG del QR code, se disponibile."""
    if not qrcode:
        return None
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def get_supabase() -> Client:
    """Utility per recuperare il client supabase."""
    return get_supabase_client()


def insert_session(record: dict) -> None:
    """Inserisce una sessione nel database."""
    sb = get_supabase()
    sb.table("sessioni").insert(record).execute()


def insert_nickname(record: dict) -> dict:
    """Crea un nickname nel database e ritorna il record creato."""
    sb = get_supabase()
    res = sb.table("nicknames").insert(record).execute()
    if not res.data:
        raise RuntimeError("Errore creazione nickname")
    return res.data[0]


def fetch_nicknames(session_id: str) -> list:
    """Recupera tutti i nickname per una sessione."""
    sb = get_supabase()
    res = (
        sb.table("nicknames")
        .select("id, code4, nickname, created_at")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


def fetch_profiles(nickname_ids: list[str]) -> dict[str, dict]:
    """Restituisce un dizionario nickname_id → profilo (o vuoto se non trovato)."""
    if not nickname_ids:
        return {}
    sb = get_supabase()
    res = (
        sb.table("profiles")
        .select(
            "id, approccio, hobby, materie_fatte, materie_dafare, obiettivi, future_role"
        )
        .in_("id", nickname_ids)
        .execute()
    )
    profiles = {}
    for r in res.data or []:
        profiles[r["id"]] = r
    return profiles


def insert_or_update_profile(nickname_id: str, payload: dict) -> None:
    """Inserisce o aggiorna un profilo utente."""
    sb = get_supabase()
    # controlla se esiste già
    res = sb.table("profiles").select("id").eq("id", nickname_id).limit(1).execute()
    if res.data:
        sb.table("profiles").update(payload).eq("id", nickname_id).execute()
    else:
        sb.table("profiles").insert(payload).execute()


def update_nickname_alias(nickname_id: str, alias: str) -> None:
    """Aggiorna il campo nickname (alias) nella tabella nicknames."""
    sb = get_supabase()
    sb.table("nicknames").update({"nickname": alias}).eq("id", nickname_id).execute()


def compute_similarity(p1: dict, p2: dict, weights: dict[str, float]) -> float:
    """
    Calcola un punteggio di somiglianza tra due profili in base a varie categorie.

    Le categorie considerate sono: hobby, approccio, materie_fatte/materie_dafare, obiettivi,
    future_role. Ogni categoria riceve un peso da 0 a 1. La somiglianza è calcolata come
    somma pesata delle singole somiglianze (Jaccard per insiemi, 1/0 per singoli).
    """
    def jaccard(a, b) -> float:
        s1 = set(a) if isinstance(a, (list, set)) else set(a or [])
        s2 = set(b) if isinstance(b, (list, set)) else set(b or [])
        if not s1 and not s2:
            return 1.0
        return len(s1 & s2) / len(s1 | s2) if (s1 | s2) else 0.0

    score = 0.0
    # hobby
    score += weights.get("hobby", 0) * jaccard(p1.get("hobby", []), p2.get("hobby", []))
    # approccio
    score += weights.get("approccio", 0) * (
        1.0 if p1.get("approccio") == p2.get("approccio") and p1.get("approccio") else 0.0
    )
    # materie (fatte + da fare)
    m1 = set(p1.get("materie_fatte", []) or []) | set(p1.get("materie_dafare", []) or [])
    m2 = set(p2.get("materie_fatte", []) or []) | set(p2.get("materie_dafare", []) or [])
    score += weights.get("materie", 0) * jaccard(m1, m2)
    # obiettivi
    score += weights.get("obiettivi", 0) * jaccard(p1.get("obiettivi", []), p2.get("obiettivi", []))
    # future_role
    score += weights.get("future_role", 0) * (
        1.0 if p1.get("future_role") == p2.get("future_role") and p1.get("future_role") else 0.0
    )
    return score


def group_students(profiles: dict[str, dict], group_size: int, weights: dict[str, float]) -> list[list[str]]:
    """
    Assegna gli studenti a gruppi in modo greedy sulla base delle similitudini.

    L'algoritmo ordina casualmente gli studenti, poi crea gruppi scegliendo
    per ciascun gruppo gli studenti con somiglianza massima tra loro.
    Restituisce una lista di liste di nickname_id.
    """
    if not profiles:
        return []
    ids = list(profiles.keys())
    random.shuffle(ids)
    groups = []
    used = set()
    for i in ids:
        if i in used:
            continue
        group = [i]
        used.add(i)
        # scegli membri più simili finché gruppo non pieno
        while len(group) < group_size:
            candidates = [j for j in ids if j not in used]
            if not candidates:
                break
            # ordina per similitudine decrescente rispetto a media del gruppo
            def avg_sim(j):
                return sum(
                    compute_similarity(profiles[j], profiles[member], weights) for member in group
                ) / len(group)
            best = max(candidates, key=avg_sim)
            group.append(best)
            used.add(best)
        groups.append(group)
    return groups


def save_groups(session_id: str, groups: list[list[str]], theme: str, weights: dict[str, float]) -> None:
    """Salva i gruppi nel database Supabase."""
    sb = get_supabase()
    group_records = []
    for idx, grp in enumerate(groups, start=1):
        record = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "nome": f"Gruppo {idx}",
            "membri": grp,
            "theme": theme,
            "weights": weights,
            "created_at": datetime.utcnow().isoformat(),
        }
        group_records.append(record)
    if group_records:
        sb.table("gruppi").insert(group_records).execute()


def fetch_groups(session_id: str) -> list[dict]:
    """Recupera i gruppi per una sessione."""
    sb = get_supabase()
    res = sb.table("gruppi").select("id, nome, membri").eq("session_id", session_id).order("nome").execute()
    return res.data or []


def profile_completed(nickname_id: str) -> bool:
    """Ritorna True se esiste un profilo per il nickname dato."""
    sb = get_supabase()
    res = sb.table("profiles").select("id").eq("id", nickname_id).limit(1).execute()
    return bool(res.data)


def get_session_link(session_id: str) -> str:
    """Costruisce un link di join basato sull'ID sessione."""
    base = st.secrets.get("PUBLIC_BASE_URL", "http://localhost:8501")
    return f"{base}?session_id={session_id}"


# -----------------------------------------------------------------------------
# 🎓 VISTA DOCENTE
# -----------------------------------------------------------------------------

def teacher_view() -> None:
    """Vista dedicata al docente per creare e gestire sessioni."""
    st.subheader("👩‍🏫 Docente")

    # Inizializza variabili di sessione per il docente
    if "teacher_session_id" not in st.session_state:
        st.session_state.teacher_session_id = None
    if "group_size" not in st.session_state:
        st.session_state.group_size = 4
    if "weights" not in st.session_state:
        st.session_state.weights = {
            "hobby": 0.7,
            "approccio": 0.3,
            "materie": 0.3,
            "obiettivi": 0.3,
            "future_role": 0.3,
        }
    if "published_sessions" not in st.session_state:
        st.session_state.published_sessions = set()

    # Se non esiste una sessione attiva, mostra il form di creazione
    if st.session_state.teacher_session_id is None:
        with st.form("create_session_form", clear_on_submit=False):
            st.write("### Crea una nuova sessione")
            nome = st.text_input("Nome sessione", placeholder="Nome lezione")
            materia = st.text_input("Materia", placeholder="Es. Matematica")
            data_sessione = st.date_input("Data", value=datetime.now().date())
            tema = st.selectbox("Tema", [
                "Innovazione",
                "Spazio",
                "Ambiente",
                "Arte",
                "Letteratura",
                "Tecnologia",
            ])
            group_size = st.number_input("Dimensione gruppi", min_value=2, max_value=10, value=4, step=1)
            create_click = st.form_submit_button("Crea sessione")

        if create_click:
            if not nome or not materia:
                st.warning("Compila tutti i campi per creare la sessione.")
            else:
                # Genera ID e salva la sessione
                sid = gen_session_id()
                record = {
                    "id": sid,
                    "nome": nome,
                    "materia": materia,
                    "data": data_sessione.strftime("%Y-%m-%d"),
                    "tema": tema,
                    "created_at": datetime.utcnow().isoformat(),
                }
                try:
                    insert_session(record)
                    st.session_state.teacher_session_id = sid
                    st.session_state.group_size = int(group_size)
                    st.session_state.session_theme = tema
                    st.success(f"Sessione '{nome}' creata con ID {sid}.")
                except Exception as e:
                    st.error(f"Errore creazione sessione: {e}")

        return  # interrompe l'esecuzione per mostrare solo il form

    # Se esiste una sessione attiva
    sid = st.session_state.teacher_session_id
    group_size = st.session_state.group_size

    # Mostra link e QR code
    st.write(f"### Sessione attiva: `{sid}`")
    join_url = get_session_link(sid)
    col_qr, col_link = st.columns([1, 2])
    with col_qr:
        qr_bytes = create_qr_code(join_url)
        if qr_bytes:
            st.image(qr_bytes, caption="QR per la sessione", use_column_width=False)
        else:
            st.warning("Impossibile generare il QR code (manca la libreria qrcode).")
    with col_link:
        st.write("Link pubblico per studenti:")
        st.code(join_url, language="text")

    st.markdown("---")

    # Lobby: mostra studenti scansionati vs pronti
    st.write("### Lobby studenti")
    nickrows = fetch_nicknames(sid)
    nickname_ids = [r["id"] for r in nickrows]
    profiles = fetch_profiles(nickname_ids)
    ready_ids = set(profiles.keys())
    scanned_count = len(nickrows)
    ready_count = len(ready_ids)
    st.metric("Scansionati", scanned_count)
    st.metric("Pronti", ready_count)

    # Tabella
    table_data = []
    for idx, r in enumerate(nickrows, start=1):
        pin = f"{r.get('code4'):04d}" if r.get("code4") is not None else "—"
        alias = r.get("nickname") or "—"
        pronto = "✅" if r["id"] in ready_ids else "⏳"
        table_data.append({"PIN": pin, "Alias": alias, "Pronto": pronto})
    if table_data:
        st.table(table_data)
    else:
        st.info("Nessuno studente ancora scansionato.")

    st.markdown("---")

    # Imposta pesi matching
    st.write("### Pesi per il matching")
    hobby_w = st.slider("Peso hobby", 0.0, 1.0, value=st.session_state.weights.get("hobby", 0.7), step=0.05)
    approach_w = st.slider(
        "Peso approccio",
        0.0,
        1.0,
        value=st.session_state.weights.get("approccio", 0.3),
        step=0.05,
    )
    subjects_w = st.slider(
        "Peso materie",
        0.0,
        1.0,
        value=st.session_state.weights.get("materie", 0.3),
        step=0.05,
    )
    goals_w = st.slider(
        "Peso obiettivi",
        0.0,
        1.0,
        value=st.session_state.weights.get("obiettivi", 0.3),
        step=0.05,
    )
    role_w = st.slider(
        "Peso dove mi vedo fra 5 anni",
        0.0,
        1.0,
        value=st.session_state.weights.get("future_role", 0.3),
        step=0.05,
    )
    st.session_state.weights = {
        "hobby": hobby_w,
        "approccio": approach_w,
        "materie": subjects_w,
        "obiettivi": goals_w,
        "future_role": role_w,
    }

    # Azioni: crea gruppi, pubblica, nuova sessione
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    create_groups_btn = col_btn1.button("Crea gruppi", disabled=ready_count == 0)
    publish_btn = col_btn2.button("Pubblica gruppi", disabled=ready_count == 0)
    reset_btn = col_btn3.button("Nuova sessione")

    # Gestione nuova sessione
    if reset_btn:
        st.session_state.teacher_session_id = None
        st.session_state.group_size = 4
        st.session_state.weights = {
            "hobby": 0.7,
            "approccio": 0.3,
            "materie": 0.3,
            "obiettivi": 0.3,
            "future_role": 0.3,
        }
        st.rerun()

    # Crea i gruppi
    if create_groups_btn and ready_count > 0:
        # recupera profili dei pronti
        ready_profiles = {rid: profiles[rid] for rid in ready_ids}
        groups = group_students(ready_profiles, group_size, st.session_state.weights)
        # salva gruppi localmente per preview
        st.session_state.groups_preview = [grp.copy() for grp in groups]
        # reset state of publish
        st.session_state.published_sessions.discard(sid)
        st.success("Gruppi creati! Ricordati di pubblicarli.")

    # Pubblica gruppi
    if publish_btn and ready_count > 0:
        groups = getattr(st.session_state, "groups_preview", None)
        if not groups:
            st.warning("Devi prima creare i gruppi.")
        else:
            try:
                save_groups(
                    sid,
                    groups,
                    theme=st.session_state.get("session_theme", ""),
                    weights=st.session_state.weights,
                )
            except Exception:
                # riprova senza tema se errore
                save_groups(sid, groups, theme="", weights=st.session_state.weights)
            st.session_state.published_sessions.add(sid)
            st.success("Gruppi pubblicati!")

    # Mostra preview gruppi
    st.write("### Gruppi creati")
    groups_preview = getattr(st.session_state, "groups_preview", None)
    if groups_preview:
        # Visualizza i gruppi in tabella
        for idx, grp in enumerate(groups_preview, start=1):
            st.markdown(f"**Gruppo {idx}**")
            # mostra alias o pin per ciascun membro
            rows = []
            for nid in grp:
                pin = "—"
                alias = "—"
                for r in nickrows:
                    if r["id"] == nid:
                        pin = f"{r.get('code4'):04d}"
                        alias = r.get("nickname") or pin
                        break
                rows.append({"Nickname": alias, "PIN": pin})
            st.table(rows)
    else:
        st.info("Nessun gruppo ancora creato.")


# -----------------------------------------------------------------------------
# 🎓 VISTA STUDENTE
# -----------------------------------------------------------------------------

def student_view() -> None:
    """Vista per gli studenti: join sessione, scelta nickname, completamento profilo."""
    st.subheader("👨‍🎓 Studente")

    # stati per la vista studente
    if "student_session_id" not in st.session_state:
        st.session_state.student_session_id = ""
    if "nickname_id" not in st.session_state:
        st.session_state.nickname_id = None
    if "pin_confirmed" not in st.session_state:
        st.session_state.pin_confirmed = False
    if "profile_completed" not in st.session_state:
        st.session_state.profile_completed = False
    if "groups_preview" not in st.session_state:
        st.session_state.groups_preview = None

    # Se non è ancora stato inserito un session_id, chiedilo
    if not st.session_state.student_session_id:
        sid_input = st.text_input("ID sessione", placeholder="Inserisci l'ID fornito dal docente")
        if st.button("Conferma sessione"):
            if not sid_input:
                st.warning("Inserisci un ID sessione valido.")
            else:
                st.session_state.student_session_id = sid_input.strip().upper()
                st.rerun()
        return

    sid = st.session_state.student_session_id
    st.write(f"Partecipa alla sessione `{sid}`")

    # Scegli nickname (PIN 4 cifre)
    if not st.session_state.pin_confirmed:
        with st.form("choose_pin"):
            st.write("### Scegli un nickname (PIN a 4 cifre)")
            pin_str = st.text_input(
                "Nickname (4 cifre)", max_chars=4, help="Usa quattro cifre (es. 1234)"
            )
            confirm = st.form_submit_button("Conferma nickname")
        if confirm:
            if not pin_str.isdigit() or len(pin_str) != 4:
                st.error("Il nickname deve essere composto da 4 cifre.")
            else:
                code4 = int(pin_str)
                try:
                    # controlla unicità nel DB
                    nicknames = fetch_nicknames(sid)
                    existing_pins = {n["code4"] for n in nicknames}
                    if code4 in existing_pins:
                        st.error("Questo nickname è già stato preso, scegline un altro.")
                    else:
                        # crea record nickname
                        record = {
                            "id": str(uuid.uuid4()),
                            "session_id": sid,
                            "code4": code4,
                            "nickname": "",  # alias inizialmente vuoto
                            "guest_id": str(uuid.uuid4()),
                            "created_at": datetime.utcnow().isoformat(),
                        }
                        newnick = insert_nickname(record)
                        st.session_state.nickname_id = newnick["id"]
                        st.session_state.pin_confirmed = True
                        # salva il pin inserito per usarlo come fallback alias
                        st.session_state.chosen_pin = pin_str
                        st.success("Nickname confermato! Ora completa il profilo.")
                except Exception as e:
                    st.error(f"Errore durante la creazione del nickname: {e}")
        return

    # nickname scelto, procedi con il profilo
    nickname_id = st.session_state.nickname_id
    if not nickname_id:
        st.error("Impossibile recuperare il tuo nickname. Ricarica la pagina.")
        return

    # recupera profilo esistente se presente
    prof_exist = fetch_profiles([nickname_id])
    existing = prof_exist.get(nickname_id, {})

    # Visualizza form di profilo
    st.write("### Completa il tuo profilo")
    tabs = st.tabs(["Alias", "Interessi", "Obiettivi"])

    # TAB 1: alias
    with tabs[0]:
        alias = st.text_input(
            "Alias (facoltativo)", value="", max_chars=12, help="Un nome alternativo al tuo PIN."
        )

    # TAB 2: interessi e materie
    with tabs[1]:
        approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
        approccio = st.selectbox(
            "Approccio al lavoro di gruppo",
            approcci,
            index=approcci.index(existing.get("approccio", approcci[0]))
            if existing.get("approccio") in approcci
            else 0,
        )
        hobbies_list = [
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
        default_hobbies = []
        raw_hobby = existing.get("hobby")
        if raw_hobby:
            try:
                default_hobbies = json.loads(raw_hobby) if isinstance(raw_hobby, str) else list(raw_hobby)
            except Exception:
                default_hobbies = list(raw_hobby) if isinstance(raw_hobby, list) else []
        hobby = st.multiselect("Hobby", options=hobbies_list, default=[h for h in default_hobbies if h in hobbies_list])
        # predefinite
        subjects_list = [
            "Matematica",
            "Fisica",
            "Statistica",
            "Programmazione",
            "Economia",
            "Marketing",
            "Finanza",
            "Diritto",
            "Ingegneria",
            "Biologia",
            "Chimica",
            "Storia",
            "Letteratura",
        ]
        default_done = []
        raw_done = existing.get("materie_fatte")
        if raw_done:
            try:
                default_done = json.loads(raw_done) if isinstance(raw_done, str) else list(raw_done)
            except Exception:
                default_done = list(raw_done) if isinstance(raw_done, list) else []
        materie_fatte = st.multiselect(
            "Materie già superate",
            options=subjects_list,
            default=[m for m in default_done if m in subjects_list],
        )
        default_todo = []
        raw_todo = existing.get("materie_dafare")
        if raw_todo:
            try:
                default_todo = json.loads(raw_todo) if isinstance(raw_todo, str) else list(raw_todo)
            except Exception:
                default_todo = list(raw_todo) if isinstance(raw_todo, list) else []
        materie_dafare = st.multiselect(
            "Materie da fare",
            options=[m for m in subjects_list if m not in materie_fatte],
            default=[m for m in default_todo if m in subjects_list and m not in materie_fatte],
        )

    # TAB 3: obiettivi e futuro
    with tabs[2]:
        goals_list = [
            "Passare gli esami a prescindere dal voto",
            "Raggiungere una media del 30",
            "Migliorare la comprensione delle materie",
            "Creare connessioni e fare gruppo",
            "Prepararmi per la carriera futura",
        ]
        default_goals = []
        raw_goals = existing.get("obiettivi")
        if raw_goals:
            try:
                default_goals = json.loads(raw_goals) if isinstance(raw_goals, str) else list(raw_goals)
            except Exception:
                default_goals = list(raw_goals) if isinstance(raw_goals, list) else []
        obiettivi = st.multiselect(
            "Obiettivi accademici",
            options=goals_list,
            default=[g for g in default_goals if g in goals_list],
        )
        # nuovo campo: dove mi vedo fra 5 anni
        future_opts = [
            "Manager",
            "CEO",
            "Imprenditore",
            "Consulente",
            "Ricercatore",
            "Docente",
            "Libero professionista",
            "Altro",
        ]
        future_role = st.selectbox(
            "Dove mi vedo fra 5 anni",
            options=future_opts,
            index=future_opts.index(existing.get("future_role", future_opts[0]))
            if existing.get("future_role") in future_opts
            else 0,
        )
        save = st.button("Salva profilo")

    if save:
        # prepara payload per profilo
        payload = {
            "id": nickname_id,
            "approccio": approccio,
            "hobby": hobby,
            "materie_fatte": materie_fatte,
            "materie_dafare": materie_dafare,
            "obiettivi": obiettivi,
            "future_role": future_role,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            insert_or_update_profile(nickname_id, payload)
            # aggiorna alias nella tabella nicknames
            # usa alias inserito o il PIN scelto salvato nello stato sessione
            alias_to_store = alias.strip() if alias.strip() else st.session_state.get("chosen_pin", "")
            update_nickname_alias(nickname_id, alias_to_store)
            st.session_state.profile_completed = True
            st.success("Profilo salvato!")
        except Exception as e:
            st.error(f"Errore nel salvataggio del profilo: {e}")

    # Dopo il salvataggio, se i gruppi sono stati pubblicati, mostra il gruppo
    # Recupera gruppi se pubblicati
    sid = st.session_state.student_session_id
    if sid in st.session_state.published_sessions and st.session_state.profile_completed:
        st.markdown("---")
        st.write("### Il tuo gruppo")
        grp_records = fetch_groups(sid)
        if not grp_records:
            st.info("I gruppi non sono ancora stati caricati.")
        else:
            # trova il gruppo a cui appartengo
            my_group = None
            for rec in grp_records:
                if nickname_id in rec.get("membri", []):
                    my_group = rec
                    break
            if not my_group:
                st.info("Non appartieni ancora a nessun gruppo.")
            else:
                st.markdown(f"**{my_group['nome']}**")
                # mostra membri con evidenziazione
                rows = []
                for nid in my_group.get("membri", []):
                    # trova alias o pin
                    alias_val = "—"
                    pin_val = "—"
                    nicklist = fetch_nicknames(sid)
                    for nrow in nicklist:
                        if nrow["id"] == nid:
                            alias_val = nrow.get("nickname") or f"{nrow.get('code4'):04d}"
                            pin_val = f"{nrow.get('code4'):04d}" if nrow.get("code4") is not None else "—"
                            break
                    highlight = nid == nickname_id
                    rows.append({"Nickname": alias_val, "PIN": pin_val, "Tu": "👈" if highlight else ""})
                st.table(rows)



# -----------------------------------------------------------------------------
# 🚀 MAIN
# -----------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="App Gruppi login‑free", page_icon="🎓", layout="wide")
    st.title("App Gruppi login‑free")

    # due schede per docente e studente
    tab_doc, tab_stud = st.tabs(["Docente", "Studente"])

    with tab_doc:
        teacher_view()

    with tab_stud:
        student_view()


if __name__ == "__main__":
    main()