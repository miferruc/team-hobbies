"""
Streamlit application for login-free group formation with nickname (PIN) entry.

Features:
1. Teacher creates a session (name, subject, date, theme) and gets a join URL with session ID embedded.
2. Students join via the link/QR and enter a 4‑digit PIN as their nickname.
3. Students complete a lightweight profile (approach, hobbies, goals, etc.).
4. Teacher lobby shows who has scanned the QR (created nickname) and who has completed the profile.
5. Teacher can adjust matching weights and generate groups automatically.
6. Groups can be published, and students see their own group with their nickname highlighted.

This file is self‑contained and does not require user authentication. It relies on a Supabase backend
with the following tables (names are in Italian for continuity with the legacy app):

• sessioni:
    id (text, primary key)
    nome (text)
    materia (text)
    data (date)
    tema (text)
    link_pubblico (text)
    creato_da (text)
    timestamp (timestamp)
    attiva (boolean)
    chiusa_il (timestamp)
• nicknames:
    id (uuid, primary key)
    session_id (text)
    code4 (int) – the 4‑digit PIN chosen by the student
    nickname (text) – same as code4 or a textual alias
    guest_id (text) – anonymous browser identifier
    created_at (timestamp)
    ready (boolean) – profile completed flag
• profiles:
    id (uuid, primary key) – matches nicknames.id
    nickname (text)
    approccio (text)
    hobby (jsonb or text)
    materie_fatte (jsonb or text)
    materie_dafare (jsonb or text)
    obiettivi (jsonb or text)
    created_at (timestamp)
• gruppi:
    id (uuid, primary key)
    session_id (text)
    nome_gruppo (text)
    membri (uuid[]) – list of nickname IDs
    tema (text)
    pesi (jsonb) – weights used for matching
    published (boolean)
    created_at (timestamp)

The app uses Streamlit query parameters to navigate between views:
• view=teacher  – teacher dashboard
• view=join     – student joins session with PIN
• view=profile  – student fills profile
• view=mygroup  – student sees their group
If no view is specified, the join view is shown by default.
"""

import io
import json
import random
import string
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st
from supabase import create_client, Client


# -----------------------------------------------------------------------------
# 🖌️ Global Styling
# -----------------------------------------------------------------------------

st.set_page_config(page_title="iStudy – login free", page_icon="🎓", layout="wide")

st.markdown(
    """
    <style>
    body { background-color: #0E1117; color: #FAFAFA; }
    h1, h2, h3, h4 { color: #E8E8E8; font-family: 'Poppins', sans-serif; font-weight: 600; }
    div.stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.4em 1em;
        font-weight: 600;
        transition: 0.2s;
    }
    div.stButton > button:hover { background-color: #0052a3; transform: scale(1.02); }
    thead tr th { background-color: #222 !important; color: #f1f1f1 !important; }
    tbody tr:nth-child(even) { background-color: #191919 !important; }
    hr { border: 0; border-top: 1px solid #444; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# 🔗 Supabase Connection
# -----------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    """Initialises the Supabase client. Expects SUPABASE_URL and SUPABASE_SERVICE_KEY in secrets."""
    url = st.secrets.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("Supabase URL or key missing in secrets. Set SUPABASE_URL and SUPABASE_SERVICE_KEY (or ANON_KEY).")
        st.stop()
    return create_client(url, key)


supabase: Client = get_supabase()


# -----------------------------------------------------------------------------
# 👤 Anonymous guest identification
# -----------------------------------------------------------------------------

def current_guest_id() -> str:
    """Returns a stable guest ID stored in session state."""
    gid = st.session_state.get("guest_id")
    if not gid:
        gid = str(uuid.uuid4())
        st.session_state["guest_id"] = gid
    return gid


# -----------------------------------------------------------------------------
# 🧭 Query parameter helpers
# -----------------------------------------------------------------------------

def get_query_param(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieves a query parameter in a version‑agnostic way."""
    try:
        if hasattr(st, "query_params"):
            val = st.query_params.get(key)
            if val is None:
                return default
            return val[0] if isinstance(val, (list, tuple)) else str(val)
    except Exception:
        pass
    # fallback legacy API
    try:
        params = st.experimental_get_query_params()
        val = params.get(key)
        if val:
            return val[0]
    except Exception:
        pass
    return default


def set_query_params(**params: str) -> None:
    """Safely updates query parameters using the available API."""
    try:
        if hasattr(st, "query_params") and hasattr(st.query_params, "update"):
            st.query_params.update(params)
            return
    except Exception:
        pass
    # fallback if new API not available
    try:
        st.experimental_set_query_params(**params)
    except Exception:
        pass


def goto(view: str, **params) -> None:
    """Navigates to another view by updating query parameters."""
    set_query_params(view=view, **params)


# -----------------------------------------------------------------------------
# 🆔 Utilities
# -----------------------------------------------------------------------------

def gen_session_id(n: int = 8) -> str:
    """Generates a short alphanumeric session ID (avoids ambiguous characters)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(n))


def build_join_url(session_id: str) -> str:
    """Constructs a public join URL for a session."""
    base = st.secrets.get("PUBLIC_BASE_URL") or st.secrets.get("PUBLIC_URL")
    base = base or "https://streamlit.io"
    return f"{base}?view=join&session_id={session_id}"


# -----------------------------------------------------------------------------
# 🎛️ Teacher View: create session and manage lobby
# -----------------------------------------------------------------------------

def teacher_view() -> None:
    st.title("👩‍🏫 Docente – Gestione sessione e lobby")

    # Session creation panel
    with st.expander("Crea nuova sessione", expanded=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            nome = st.text_input("Nome sessione", placeholder="Es. Economia 16/10/2025")
            materia = st.text_input("Materia", placeholder="Es. Economia Aziendale")
        with col2:
            group_size = st.number_input("Dimensione gruppo", min_value=2, max_value=10, value=4, step=1)
            crea = st.button("Crea sessione", use_container_width=True)

        if crea:
            if not nome.strip():
                st.warning("Inserisci un nome valido per la sessione.")
            else:
                sid = gen_session_id()
                link = build_join_url(sid)
                record = {
                    "id": sid,
                    "nome": nome,
                    "materia": materia,
                    "data": str(datetime.now().date()),
                    "tema": "Generico",
                    "link_pubblico": link,
                    "creato_da": current_guest_id(),
                    "timestamp": datetime.now().isoformat(),
                    "attiva": True,
                    "chiusa_il": None,
                }
                try:
                    supabase.table("sessioni").insert(record).execute()
                    st.session_state["current_session_id"] = sid
                    st.success(f"Sessione creata: {sid}")
                except Exception as e:
                    st.error(f"Errore durante la creazione della sessione: {e}")

    # Determine current session from state or input
    sid = st.session_state.get("current_session_id") or get_query_param("session_id")
    if not sid:
        st.info("Seleziona o crea una sessione per continuare.")
        return

    # Show session info and join link/QR
    st.subheader(f"Sessione attiva: `{sid}`")
    join_url = build_join_url(sid)
    colQ, colL = st.columns([1, 2])
    with colQ:
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(join_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="QR di ingresso", width=180)
        except Exception:
            st.warning("Libreria qrcode non disponibile. Mostro solo il link.")
    with colL:
        st.markdown("**Link pubblico per gli studenti**:")
        st.code(join_url, language="text")

    st.divider()

    # Lobby: scanned vs ready
    st.subheader("Lobby partecipanti")
    try:
        res_n = supabase.table("nicknames").select("id, code4, nickname, ready, created_at").eq("session_id", sid).execute()
        nicknames = res_n.data or []
    except Exception as e:
        st.error(f"Errore caricamento nicknames: {e}")
        nicknames = []

    scanned = nicknames
    ready = [n for n in nicknames if n.get("ready")]

    colA, colB, colC = st.columns(3)
    colA.metric("Scansionati", len(scanned))
    colB.metric("Pronti", len(ready))
    colC.metric("In attesa", max(len(scanned) - len(ready), 0))

    cL, cR = st.columns(2)
    with cL:
        st.markdown("**Scansionati (nickname creati)**")
        st.dataframe(
            [
                {
                    "PIN": f"{n.get('code4', ''):04d}" if n.get("code4") is not None else "—",
                    "Nickname": n.get("nickname") or "—",
                    "Pronto": "✅" if n.get("ready") else "❌",
                }
                for n in scanned
            ],
            hide_index=True,
        )
    with cR:
        st.markdown("**Pronti (profilo completato)**")
        st.dataframe(
            [
                {
                    "PIN": f"{n.get('code4', ''):04d}" if n.get("code4") is not None else "—",
                    "Nickname": n.get("nickname") or "—",
                }
                for n in ready
            ],
            hide_index=True,
        )

    st.divider()

    # Matching weights and group creation
    st.subheader("Creazione gruppi")
    with st.form("weights_form"):
        colW1, colW2 = st.columns(2)
        with colW1:
            weight_hobby = st.slider("Peso hobby", min_value=0.0, max_value=1.0, value=0.7, step=0.05)
        with colW2:
            weight_approccio = st.slider("Peso approccio", min_value=0.0, max_value=1.0, value=0.3, step=0.05)
        st.caption("I pesi verranno normalizzati se non sommano a 1.")
        crea_gr = st.form_submit_button("Crea gruppi")

    if crea_gr:
        try:
            normalize = weight_hobby + weight_approccio
            w_h = weight_hobby / normalize if normalize else 0.5
            w_a = weight_approccio / normalize if normalize else 0.5
            create_groups(session_id=sid, group_size=int(group_size), weights={"hobby": w_h, "approccio": w_a})
            st.success("Gruppi creati con successo.")
        except Exception as e:
            st.error(f"Errore nella creazione dei gruppi: {e}")

    # Publish groups
    if st.button("Pubblica gruppi", disabled=False):
        try:
            supabase.table("gruppi").update({"published": True}).eq("session_id", sid).execute()
            st.success("Gruppi pubblicati.")
        except Exception as e:
            st.error(f"Errore nella pubblicazione: {e}")


# -----------------------------------------------------------------------------
# 🤝 Create Groups Function
# -----------------------------------------------------------------------------

def similarita(p1: Dict, p2: Dict, weights: Dict[str, float]) -> float:
    """Computes similarity between two profile dictionaries based on hobby and approccio."""
    # Normalize hobbies into sets
    def norm_list(x):
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
    h1 = norm_list(p1.get("hobby"))
    h2 = norm_list(p2.get("hobby"))
    inter = len(h1 & h2)
    union = len(h1 | h2)
    sim_hobby = inter / union if union else 0.0
    sim_app = 1.0 if p1.get("approccio") == p2.get("approccio") else 0.0
    w_h = weights.get("hobby", 0.5)
    w_a = weights.get("approccio", 0.5)
    return w_h * sim_hobby + w_a * sim_app


def create_groups(session_id: str, group_size: int, weights: Dict[str, float]) -> None:
    """Generates groups for a session based on profiles and weights."""
    # Fetch ready nicknames
    res_n = supabase.table("nicknames").select("id, ready").eq("session_id", session_id).eq("ready", True).execute()
    nick_ids = [n["id"] for n in res_n.data or []]
    if not nick_ids:
        st.warning("Nessun partecipante pronto.")
        return
    # Fetch profiles
    res_p = supabase.table("profiles").select("id, hobby, approccio").in_("id", nick_ids).execute()
    profiles = res_p.data or []
    # Compute average similarity
    score_avg = {}
    for p in profiles:
        others = [similarita(p, q, weights) for q in profiles if q["id"] != p["id"]]
        score_avg[p["id"]] = sum(others) / len(others) if others else 0.0
    profiles_sorted = sorted(profiles, key=lambda x: score_avg[x["id"]], reverse=True)
    # Group participants greedily
    groups: List[List[str]] = [
        [p["id"] for p in profiles_sorted[i : i + group_size]]
        for i in range(0, len(profiles_sorted), group_size)
    ]
    # Determine group names based on session theme
    sess = supabase.table("sessioni").select("tema").eq("id", session_id).execute()
    tema = sess.data[0].get("tema", "Generico") if sess.data else "Generico"
    temi_gruppi: Dict[str, List[str]] = {
        "Anime": ["Akira", "Totoro", "Naruto", "Luffy", "Saitama", "Asuka", "Shinji", "Kenshin"],
        "Sport": ["Maradona", "Jordan", "Federer", "Bolt", "Ali", "Phelps", "Serena"],
        "Spazio": ["Apollo", "Orion", "Luna", "Cosmos", "Nova", "Mars"],
        "Natura": ["Quercia", "Rosa", "Vento", "Onda", "Sole", "Mare", "Cielo"],
        "Tecnologia": ["Byte", "Pixel", "Quantum", "Neural", "Circuit", "Code"],
        "Storia": ["Roma", "Atene", "Sparta", "Troia", "Cartagine", "Babilonia"],
        "Mitologia": ["Zeus", "Athena", "Thor", "Ra", "Anubi", "Odino"],
    }
    names = temi_gruppi.get(tema, [f"Gruppo{i+1}" for i in range(len(groups))])
    # Remove existing groups for session
    supabase.table("gruppi").delete().eq("session_id", session_id).execute()
    # Insert new groups
    for idx, membri in enumerate(groups):
        record = {
            "session_id": session_id,
            "nome_gruppo": names[idx % len(names)],
            "membri": membri,
            "tema": tema,
            "pesi": weights,
            "published": False,
            "created_at": datetime.now().isoformat(),
        }
        supabase.table("gruppi").insert(record).execute()


# -----------------------------------------------------------------------------
# 🔑 Join View: choose session and PIN
# -----------------------------------------------------------------------------

def join_view() -> None:
    st.title("Entra nella sessione")
    # Determine session ID
    session_id = get_query_param("session_id")
    if not session_id:
        with st.form("join_form"):
            sid_in = st.text_input("Inserisci ID sessione", placeholder="Es. ABCD1234")
            submit = st.form_submit_button("Entra")
        if not submit:
            st.info("Scansiona il QR o inserisci l'ID della sessione.")
            return
        session_id = sid_in.strip().upper()
        if not session_id:
            st.warning("ID sessione non valido.")
            return
        # update params so the URL reflects the session
        set_query_params(view="join", session_id=session_id)

    # Prompt for PIN (4 digits)
    with st.form("pin_form"):
        pin = st.text_input("Scegli un PIN a 4 cifre", max_chars=4, placeholder="1234")
        ok = st.form_submit_button("Conferma PIN")

    if ok:
        # Validate PIN: must be digits and length 4
        if not pin.isdigit() or len(pin) != 4:
            st.warning("Il PIN deve essere un numero di 4 cifre.")
            return
        code4 = int(pin)
        gid = current_guest_id()
        # Check uniqueness
        try:
            res = (
                supabase.table("nicknames")
                .select("id")
                .eq("session_id", session_id)
                .eq("code4", code4)
                .execute()
            )
            if res.data:
                st.error("Questo PIN è già in uso. Scegli un altro codice.")
                return
        except Exception as e:
            st.error(f"Errore durante la verifica del PIN: {e}")
            return
        # Create nickname record
        record = {
            "session_id": session_id,
            "code4": code4,
            "nickname": pin,  # initial nickname equal to pin; can be updated later
            "guest_id": gid,
            "created_at": datetime.now().isoformat(),
            "ready": False,
        }
        try:
            ins = supabase.table("nicknames").insert(record).execute()
            nickname_id = ins.data[0]["id"] if ins.data else None
            if not nickname_id:
                st.error("Impossibile creare il nickname.")
                return
            # Save nickname_id in state and navigate to profile
            goto("profile", session_id=session_id, nickname_id=nickname_id)
        except Exception as e:
            st.error(f"Errore durante la creazione del nickname: {e}")


# -----------------------------------------------------------------------------
# 📝 Profile View: complete user profile
# -----------------------------------------------------------------------------

def profile_view() -> None:
    st.title("Completa il tuo profilo")
    session_id = get_query_param("session_id")
    nickname_id = get_query_param("nickname_id")

    if not nickname_id:
        st.warning("Nessun nickname trovato. Torna alla pagina di join.")
        return

    # --- Fetch existing profile
    try:
        res_prof = supabase.table("profiles").select("*").eq("id", nickname_id).limit(1).execute()
        profile = res_prof.data[0] if res_prof.data else {}
    except Exception as e:
        st.error(f"Errore nel caricamento del profilo: {e}")
        profile = {}

    # --- Tabs
    tab1, tab2, tab3 = st.tabs(["Nickname", "Interessi", "Obiettivi"])

    # --- TAB 1: nickname
    with tab1:
        current_pin = profile.get("nickname") or get_initial_pin(nickname_id)
        nickname_text = st.text_input(
            "Nickname (puoi usare il PIN o un alias)", value=current_pin or "", max_chars=12
        )

    # --- TAB 2: interessi
    with tab2:
        approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
        approccio = st.selectbox(
            "Approccio al lavoro di gruppo",
            approcci,
            index=approcci.index(profile.get("approccio", approcci[0]))
            if profile.get("approccio") in approcci
            else 0,
        )

        hobbies_list = ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"]
        default_hobby = []
        raw_hobby = profile.get("hobby")
        if raw_hobby:
            if isinstance(raw_hobby, str):
                try:
                    default_hobby = json.loads(raw_hobby)
                except Exception:
                    default_hobby = [raw_hobby]
            elif isinstance(raw_hobby, list):
                default_hobby = raw_hobby
        hobby = st.multiselect("Hobby", options=hobbies_list, default=[h for h in default_hobby if h in hobbies_list])
        materie_fatte = st.text_area("Materie già superate", value=comma_join(profile.get("materie_fatte")))
        materie_dafare = st.text_area("Materie da fare", value=comma_join(profile.get("materie_dafare")))

    # --- TAB 3: obiettivi
    with tab3:
        obiettivi_opts = [
            "Passare gli esami a prescindere dal voto",
            "Raggiungere una media del 30",
            "Migliorare la comprensione delle materie",
            "Creare connessioni e fare gruppo",
            "Prepararmi per la carriera futura",
        ]
        default_goals = []
        raw_goal = profile.get("obiettivi")
        if raw_goal:
            if isinstance(raw_goal, str):
                try:
                    default_goals = json.loads(raw_goal)
                except Exception:
                    default_goals = [raw_goal]
            elif isinstance(raw_goal, list):
                default_goals = raw_goal
        obiettivi = st.multiselect(
            "Obiettivi accademici",
            options=obiettivi_opts,
            default=[g for g in default_goals if g in obiettivi_opts],
        )
        pronto = st.checkbox("Segnami come pronto", value=bool(profile))
        salva = st.button("💾 Salva profilo", type="primary")

    # --- SAVE LOGIC
    if salva:
        record = {
            "id": nickname_id,
            "nickname": nickname_text,
            "approccio": approccio,
            "hobby": hobby,
            "materie_fatte": split_by_comma(materie_fatte),
            "materie_dafare": split_by_comma(materie_dafare),
            "obiettivi": obiettivi,
            "created_at": datetime.now().isoformat(),
        }

        # 1️⃣ Salva profilo (anche parziale)
        try:
            if profile:
                supabase.table("profiles").update(record).eq("id", nickname_id).execute()
            else:
                supabase.table("profiles").insert(record).execute()
            st.success("Profilo salvato.")
        except Exception as e:
            st.warning(f"Salvataggio parziale del profilo: {e}")

        # 2️⃣ Aggiorna sempre il nickname e lo stato 'ready' nella tabella principale
        try:
            supabase.table("nicknames").update(
                {"nickname": nickname_text, "ready": True}
            ).eq("id", nickname_id).execute()
        except Exception as e:
            st.error(f"Errore aggiornamento nickname: {e}")

        # 3️⃣ Naviga alla vista gruppo
        goto("mygroup", session_id=session_id, nickname_id=nickname_id)

# -----------------------------------------------------------------------------
# 👥 MyGroup View: show group membership
# -----------------------------------------------------------------------------

def mygroup_view() -> None:
    st.title("Il tuo gruppo")
    session_id = get_query_param("session_id")
    nickname_id = get_query_param("nickname_id")
    if not session_id or not nickname_id:
        st.warning("Parametri mancanti.")
        return
    # Check if groups are published
    try:
        res_g = supabase.table("gruppi").select("published").eq("session_id", session_id).execute()
        if not res_g.data:
            st.info("I gruppi non sono ancora stati creati.")
            return
        published = any(g.get("published") for g in res_g.data)
        if not published:
            st.info("I gruppi non sono ancora stati pubblicati.")
            return
    except Exception as e:
        st.error(f"Errore nel controllo dei gruppi: {e}")
        return
    # Retrieve group that contains the nickname_id
    try:
        res = supabase.table("gruppi").select("nome_gruppo, membri").eq("session_id", session_id).execute()
        gruppo = None
        for g in res.data or []:
            if nickname_id in g.get("membri", []):
                gruppo = g
                break
        if not gruppo:
            st.info("Non sei stato assegnato a nessun gruppo.")
            return
        nome = gruppo.get("nome_gruppo")
        membri_ids = gruppo.get("membri", [])
        st.subheader(f"Sei nel gruppo: {nome}")
        # Fetch nicknames to display names
        res_n = supabase.table("nicknames").select("id, code4, nickname").in_("id", membri_ids).execute()
        nickrows = res_n.data or []
        for n in nickrows:
            nid = n.get("id")
            code = n.get("code4")
            name = n.get("nickname") or f"{code:04d}" if code is not None else "—"
            highlight = nid == nickname_id
            st.markdown(f"- {'**' if highlight else ''}{name}{'**' if highlight else ''}")
    except Exception as e:
        st.error(f"Errore nel caricamento del gruppo: {e}")


# -----------------------------------------------------------------------------
# 📍 View Router
# -----------------------------------------------------------------------------

def view_router():
    view = get_query_param("view", "join")
    if view == "teacher":
        teacher_view()
    elif view == "profile":
        profile_view()
    elif view == "mygroup":
        mygroup_view()
    else:
        join_view()


# -----------------------------------------------------------------------------
# 🚀 Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    view_router()