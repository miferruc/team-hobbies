import os, uuid, random, io
import streamlit as st
from supabase import create_client, Client

# === [APP-STEP2.A] import opzionali per QR e URL ===
try:
    import qrcode
except Exception:
    qrcode = None  # fallback: mostriamo solo il link se manca qrcode
# === [/APP-STEP2.A] ===

LOGIN_FREE = True

# === [APP-STEP1] code4 helper: prenota un codice 4 cifre per una sessione ===
def reserve_code4_for_session(supabase_client, session_id: str) -> int:
    """
    Chiama l'RPC 'reserve_code4' su Supabase per ottenere un code4 libero nella sessione.
    Ritorna un int tra 0 e 9999.
    """
    res = supabase_client.rpc("reserve_code4", {"p_session_id": session_id}).execute()
    if not getattr(res, "data", None) and not isinstance(res.data, int):
        raise RuntimeError("reserve_code4 RPC failed")
    return int(res.data)
# === [/APP-STEP1] ===

# === [APP-STEP3.A] helper: crea nickname (nicknames) per sessione ===
def create_nickname_record(sbx: Client, session_id: str, guest_id: str) -> dict:
    """
    Se esiste già un nickname per questo guest_id+session, lo riusa.
    Altrimenti chiede un code4 all'RPC e inserisce su 'nicknames'.
    Ritorna il record 'nicknames' creato/esistente.
    """
    res = sbx.table("nicknames").select("*").eq("session_id", session_id).eq("guest_id", guest_id).limit(1).execute()
    if res.data:
        return res.data[0]

    code4 = reserve_code4_for_session(sbx, session_id)
    payload = {
        "session_id": session_id,
        "guest_id": guest_id,
        "code4": code4,
    }
    ins = sbx.table("nicknames").insert(payload).execute()
    if not ins.data:
        raise RuntimeError("Creazione nickname fallita")
    return ins.data[0]
# === [/APP-STEP3.A] ===

# === [APP-UTIL.QP] query params compatibili nuovo/legacy ===
def _qp_read(key: str, default: str | None = None) -> str | None:
    try:
        if hasattr(st, "query_params"):
            v = st.query_params.get(key)
            if v is not None:
                return v[0] if isinstance(v, (list, tuple)) else str(v)
    except Exception:
        pass
    try:
        v = st.experimental_get_query_params().get(key)
        return v[0] if isinstance(v, list) and v else default
    except Exception:
        return default

def _qp_update(d: dict):
    try:
        if hasattr(st, "query_params"):
            st.query_params.update(d)
            return
    except Exception:
        pass
    st.experimental_set_query_params(**d)
# === [/APP-UTIL.QP] ===

@st.cache_resource
def sb() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

def current_user_id():
    gid = st.session_state.get("guest_id")
    if not gid:
        gid = str(uuid.uuid4())
        st.session_state["guest_id"] = gid
    return gid

def goto(view: str, **params):
    # === [APP-PATCH] usa helper compatibile per aggiornare i query params ===
    _qp_update({"view": view, **params})

def view_router():
    view = _qp_read("view", "join")
    if view == "teacher":
        teacher_view()
    elif view == "profile":
        profile_view()
    elif view == "mygroup":
        mygroup_view()
    else:
        join_view()

# === [APP-STEP3.B] JOIN VIEW: genera code4 e porta al profilo ===
def join_view():
    st.title("Entra nella sessione")

    # 1) session_id dal link/QR o input manuale
    session_id = _qp_read("session_id")
    if not session_id:
        with st.form("join_manual"):
            sid_in = st.text_input("Inserisci Session ID", placeholder="es. 8-char code")
            ok = st.form_submit_button("Entra")
        if ok and sid_in:
            session_id = sid_in.strip().upper()
            _qp_update({"view": "join", "session_id": session_id})
        else:
            st.warning("Session ID mancante. Usa il QR, il link del docente o inserisci l'ID sopra.")
            return

    # 2) guest_id locale
    gid = current_user_id()

    # 3) crea/recupera nickname in DB
    try:
        sbx = sb()
        nick = create_nickname_record(sbx, session_id, gid)
    except Exception as e:
        st.error(f"Errore creazione nickname: {e}")
        return

    # 4) mostra codice e stato
    code4_str = f"{nick.get('code4', 0):04d}"
    st.success(f"Il tuo codice: {code4_str}")
    st.caption("Conserva il codice. Verrà evidenziato quando i gruppi saranno pubblicati.")

    # 5) bottone per completare il profilo
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Completa profilo", type="primary", use_container_width=True):
            goto("profile", session_id=session_id, nickname_id=str(nick["id"]))
    with c2:
        st.button("Riprova join", help="Ricarica la pagina senza creare un nuovo codice.", on_click=lambda: st.rerun())
# === [/APP-STEP3.B] ===

def profile_view(): 
    st.write("PROFILE placeholder")

def mygroup_view(): 
    st.write("MY GROUP placeholder")

def teacher_view(): 
    st.write("TEACHER LOBBY placeholder")

if __name__ == "__main__":
    st.set_page_config(page_title="iStudy — login-free", layout="wide")
    view_router()
