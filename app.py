import streamlit as st
from supabase import create_client
from datetime import datetime
import uuid
import random
import json
from io import BytesIO
import qrcode

# Configura la pagina
st.set_page_config(page_title="Gruppi login‑free", page_icon="📚", layout="centered")

# Connetti a Supabase
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
# Usa la chiave di servizio se presente, altrimenti la chiave anonima
SUPABASE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY", st.secrets.get("SUPABASE_ANON_KEY"))
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Temi e nomi per i gruppi
THEME_GROUP_NAMES = {
    "Anime": ["Akira", "Totoro", "Naruto", "Luffy", "Saitama", "Asuka", "Shinji", "Kenshin"],
    "Sport": ["Maradona", "Jordan", "Federer", "Bolt", "Ali", "Phelps", "Serena"],
    "Spazio": ["Apollo", "Orion", "Luna", "Cosmos", "Nova", "Mars"],
    "Natura": ["Quercia", "Rosa", "Vento", "Onda", "Sole", "Mare", "Cielo"],
    "Tecnologia": ["Byte", "Pixel", "Quantum", "Neural", "Circuit", "Code"],
    "Storia": ["Roma", "Atene", "Sparta", "Troia", "Cartagine", "Babilonia"],
    "Mitologia": ["Zeus", "Athena", "Thor", "Ra", "Anubi", "Odino"],
}

def build_join_url(session_id: str) -> str:
    """Costruisce l'URL pubblico per far partecipare gli studenti."""
    base = st.secrets.get("PUBLIC_URL", st.secrets.get("PUBLIC_BASE_URL", "http://localhost:8501"))
    if not base.endswith("/"):
        base += "/"
    return f"{base}?session_id={session_id}"

def generate_session_id() -> str:
    """Genera un ID di sessione da 8 caratteri."""
    return str(uuid.uuid4())[:8]

def get_nicknames(session_id: str):
    """Recupera l'elenco dei record nella tabella 'nicknames' per la sessione."""
    try:
        res = supabase.table("nicknames").select("id, code4, nickname, created_at").eq("session_id", session_id).execute()
        return res.data or []
    except Exception:
        return []

def get_ready_ids(session_id: str):
    """Restituisce l'insieme degli ID nickname con profilo associato (pronti)."""
    nicks = get_nicknames(session_id)
    nick_ids = [r["id"] for r in nicks]
    if not nick_ids:
        return set()
    try:
        res = supabase.table("profiles").select("id").in_("id", nick_ids).execute()
        return set([r["id"] for r in (res.data or [])])
    except Exception:
        return set()

def create_session_db(nome: str, materia: str, data_sessione, tema: str, group_size: int):
    """Crea una nuova sessione nel database e restituisce l'ID."""
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
        "group_size": group_size,
        "gruppi_pubblicati": False,
    }
    supabase.table("sessioni").insert(record).execute()
    return sid

def create_nickname(session_id: str, code4: int):
    """Aggiunge un record nella tabella 'nicknames' con il PIN scelto."""
    # Verifica univocità
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

def save_profile(nickname_id: str, nickname_text: str, approccio: str, hobby: list[str], materie_fatte: list[str], materie_dafare: list[str], obiettivi: list[str]):
    """Salva o aggiorna un profilo e aggiorna anche l'alias nella tabella 'nicknames'."""
    record = {
        "id": nickname_id,
        "nickname": nickname_text,
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
        st.warning(f"Salvataggio parziale del profilo: {e}")
    # Aggiorna il nickname nella tabella 'nicknames'
    try:
        supabase.table("nicknames").update({"nickname": nickname_text}).eq("id", nickname_id).execute()
    except Exception as e:
        st.warning(f"Errore aggiornamento nickname: {e}")

def compute_similarity(p1, p2, w_hobby: float, w_approccio: float):
    """Calcola la similarità tra due profili basata su hobby e approccio."""
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
    """Crea gruppi basandosi su hobby e approccio con pesi dati."""
    nick_res = supabase.table("nicknames").select("id").eq("session_id", session_id).execute()
    nick_ids = [n["id"] for n in (nick_res.data or [])]
    if not nick_ids:
        st.warning("Nessun partecipante ha effettuato la scansione.")
        return
    prof_res = supabase.table("profiles").select("id, approccio, hobby, obiettivi, materie_fatte, materie_dafare").in_("id", nick_ids).execute()
    profiles = {p["id"]: p for p in (prof_res.data or [])}
    if not profiles:
        st.warning("Nessun profilo completato. Non è possibile creare i gruppi.")
        return
    students = list(profiles.values())
    avg_score = {}
    for p in students:
        scores = [compute_similarity(p, q, w_hobby, w_approccio) for q in students if q["id"] != p["id"]]
        avg_score[p["id"]] = sum(scores)/len(scores) if scores else 0.0
    students.sort(key=lambda x: avg_score[x["id"]], reverse=True)
    groups = [students[i:i+group_size] for i in range(0, len(students), group_size)]
    # Nome gruppi
    sess_res = supabase.table("sessioni").select("tema").eq("id", session_id).execute()
    theme = sess_res.data[0]["tema"] if sess_res.data else "Generico"
    names_pool = THEME_GROUP_NAMES.get(theme, [f"Gruppo {i+1}" for i in range(len(groups))])
    # Delete existing groups
    supabase.table("gruppi").delete().eq("sessione_id", session_id).execute()
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
    supabase.table("sessioni").update({"gruppi_pubblicati": False}).eq("id", session_id).execute()
    st.success(f"Creati {len(groups)} gruppi basati sui pesi specificati.")

def publish_groups(session_id: str):
    """Segna i gruppi della sessione come pubblicati."""
    try:
        supabase.table("sessioni").update({"gruppi_pubblicati": True}).eq("id", session_id).execute()
        st.success("Gruppi pubblicati!")
    except Exception as e:
        st.error(f"Errore nella pubblicazione: {e}")

def get_user_group(session_id: str, nickname_id: str):
    """Restituisce il gruppo a cui appartiene il nickname, se presente."""
    try:
        res = supabase.table("gruppi").select("nome_gruppo, membri").eq("sessione_id", session_id).execute()
        for g in res.data or []:
            if nickname_id in (g.get("membri") or []):
                return g
    except Exception:
        pass
    return None

# Titolo principale
st.title("🎓 App Gruppi login‑free")

# Tabs per Docente e Studente
tab_teacher, tab_student = st.tabs(["👩‍🏫 Docente", "👤 Studente"])

# --------------- Tab Docente ---------------
with tab_teacher:
    st.header("Gestione sessione docenti")
    teacher_sid = st.session_state.get("teacher_session_id")
    if not teacher_sid:
        st.subheader("Crea una nuova sessione")
        nome = st.text_input("Nome sessione", key="teacher_nome_sessione")
        materia = st.text_input("Materia", key="teacher_materia")
        data_sessione = st.date_input("Data", value=datetime.now().date(), key="teacher_data")
        tema = st.selectbox("Tema", list(THEME_GROUP_NAMES.keys()), key="teacher_tema")
        group_size = st.number_input("Dimensione gruppo", min_value=2, max_value=12, value=4, step=1, key="teacher_group_size")
        if st.button("📦 Crea sessione", key="btn_create_session"):
            if not nome.strip():
                st.error("Inserisci un nome valido per la sessione.")
            else:
                sid = create_session_db(nome, materia, data_sessione, tema, int(group_size))
                st.session_state["teacher_session_id"] = sid
                st.session_state["teacher_group_size"] = int(group_size)
                st.success(f"Sessione '{nome}' creata!")
    else:
        sid = teacher_sid
        # Recupera i dettagli sessione
        sess_res = supabase.table("sessioni").select("nome, materia, data, tema, link_pubblico, gruppi_pubblicati, group_size").eq("id", sid).execute()
        if not sess_res.data:
            st.error("Sessione non trovata.")
        else:
            s = sess_res.data[0]
            st.markdown(f"**Nome:** {s.get('nome','')}  ")
            st.markdown(f"**Materia:** {s.get('materia','')}  ")
            st.markdown(f"**Data:** {s.get('data','')}  ")
            st.markdown(f"**Tema:** {s.get('tema','')}  ")
            st.markdown(f"**Dimensione gruppi:** {s.get('group_size',4)}  ")
            join_url = build_join_url(sid)
            # QR code generazione
            qr = qrcode.QRCode(box_size=6, border=2)
            qr.add_data(join_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="QR per gli studenti", use_column_width=False)
            st.write("Link pubblico per gli studenti:")
            st.code(join_url)
            st.divider()
            # Lobby
            st.subheader("Lobby studenti")
            nicknames = get_nicknames(sid)
            ready_ids = get_ready_ids(sid)
            num_scanned = len(nicknames)
            num_ready = len(ready_ids)
            st.metric("Scansionati", num_scanned)
            st.metric("Pronti", num_ready)
            if nicknames:
                table = []
                for n in nicknames:
                    pin = n.get("code4")
                    alias = n.get("nickname") or "—"
                    rid = "✅" if n.get("id") in ready_ids else "⏳"
                    table.append({"PIN": f"{pin:04d}" if pin is not None else "----", "Alias": alias, "Pronto": rid})
                st.table(table)
            else:
                st.write("Nessuno studente ha ancora scansionato.")
            st.divider()
            st.subheader("Imposta pesi per il matching")
            w_hobby = st.slider("Peso hobby", 0.0, 1.0, 0.7, 0.05)
            w_approccio = 1.0 - w_hobby
            if st.button("🔀 Crea gruppi", key="btn_crea_gruppi"):
                size = s.get("group_size", st.session_state.get("teacher_group_size", 4))
                create_groups(sid, int(size), w_hobby, w_approccio)
            if st.button("📢 Pubblica gruppi", key="btn_pubblica_gruppi"):
                publish_groups(sid)
            if st.button("♻️ Nuova sessione", key="btn_reset_sessione"):
                st.session_state.pop("teacher_session_id", None)
                st.session_state.pop("teacher_group_size", None)
                st.experimental_rerun()
            st.divider()
            st.subheader("Gruppi creati")
            try:
                res = supabase.table("gruppi").select("nome_gruppo, membri, tema").eq("sessione_id", sid).execute()
                groups = res.data or []
            except Exception:
                groups = []
            if not groups:
                st.info("Nessun gruppo creato ancora.")
            else:
                member_ids = list({mid for g in groups for mid in (g.get("membri") or [])})
                alias_map = {}
                if member_ids:
                    prof_res2 = supabase.table("nicknames").select("id, code4, nickname").in_("id", member_ids).execute()
                    for r in prof_res2.data or []:
                        pin = r.get("code4")
                        alias_map[r["id"]] = r.get("nickname") or f"{pin:04d}"
                for g in groups:
                    st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**  ")
                    members = [alias_map.get(mid, mid[:4]) for mid in (g.get("membri") or [])]
                    st.write(", ".join(members))

# --------------- Tab Studente ---------------
with tab_student:
    st.header("Partecipa alla sessione")
    qp_sid = st.experimental_get_query_params().get("session_id", [None])[0]
    session_id_input = st.text_input("ID sessione", value=qp_sid or "", max_chars=8, key="student_session_id_input")
    if not session_id_input:
        st.info("Inserisci l'ID della sessione fornito dal docente o usa il link/QR.")
    else:
        st.session_state["student_session_id"] = session_id_input
        session_id = session_id_input
        nickname_id = st.session_state.get("student_nickname_id")
        nickname_session = st.session_state.get("student_session_id_cached")
        if not nickname_id or nickname_session != session_id:
            st.subheader("Scegli un PIN a 4 cifre (nickname)")
            pin_val = st.text_input("PIN", max_chars=4, key="student_pin")
            if st.button("Conferma PIN", key="btn_confirm_pin"):
                if not pin_val or not pin_val.isdigit() or len(pin_val) != 4:
                    st.error("Inserisci un numero di 4 cifre.")
                else:
                    try:
                        new_nick = create_nickname(session_id, int(pin_val))
                        st.session_state["student_nickname_id"] = new_nick["id"]
                        st.session_state["student_session_id_cached"] = session_id
                        st.success("PIN confermato! Ora completa il profilo.")
                    except Exception as e:
                        st.error(f"Errore durante la creazione del nickname: {e}")
        else:
            nickname_id = st.session_state["student_nickname_id"]
            try:
                res_prof2 = supabase.table("profiles").select("*").eq("id", nickname_id).execute()
                profile_data = res_prof2.data[0] if res_prof2.data else None
            except Exception:
                profile_data = None
            st.subheader("Completa il tuo profilo")
            with st.form("form_profilo"):
                alias = st.text_input("Alias (opzionale)", value=profile_data.get("nickname") if profile_data else "")
                approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
                idx_app = approcci.index(profile_data.get("approccio")) if profile_data and profile_data.get("approccio") in approcci else 0
                approccio = st.selectbox("Approccio al lavoro di gruppo", approcci, index=idx_app)
                hobby_options = ["Sport", "Lettura", "Musica", "Viaggi", "Videogiochi", "Arte", "Volontariato"]
                current_hobbies = []
                raw_hobby = profile_data.get("hobby") if profile_data else []
                if raw_hobby:
                    if isinstance(raw_hobby, list):
                        current_hobbies = raw_hobby
                    elif isinstance(raw_hobby, str):
                        try:
                            current_hobbies = json.loads(raw_hobby)
                        except Exception:
                            current_hobbies = [raw_hobby]
                hobbies = st.multiselect("Hobby", hobby_options, default=[h for h in current_hobbies if h in hobby_options])
                mf_default = ", ".join(profile_data.get("materie_fatte", [])) if profile_data else ""
                md_default = ", ".join(profile_data.get("materie_dafare", [])) if profile_data else ""
                materie_fatte_in = st.text_area("Materie già superate", value=mf_default)
                materie_dafare_in = st.text_area("Materie da fare", value=md_default)
                obiettivi_opts = [
                    "Passare gli esami a prescindere dal voto",
                    "Raggiungere una media del 30",
                    "Migliorare la comprensione delle materie",
                    "Creare connessioni e fare gruppo",
                    "Prepararmi per la carriera futura",
                ]
                current_obj = []
                raw_obj = profile_data.get("obiettivi") if profile_data else []
                if raw_obj:
                    if isinstance(raw_obj, list):
                        current_obj = raw_obj
                    elif isinstance(raw_obj, str):
                        try:
                            current_obj = json.loads(raw_obj)
                        except Exception:
                            current_obj = [raw_obj]
                obiettivi_sel = st.multiselect("Obiettivi accademici", options=obiettivi_opts, default=[o for o in current_obj if o in obiettivi_opts])
                st.checkbox("Sono pronto/a per essere assegnato ai gruppi", value=bool(profile_data))  # placeholder
                submitted = st.form_submit_button("Salva profilo")
            if submitted:
                mf_list = [m.strip() for m in materie_fatte_in.split(",") if m.strip()]
                md_list = [m.strip() for m in materie_dafare_in.split(",") if m.strip()]
                save_profile(nickname_id, alias or f"{st.session_state.get('student_pin', '')}", approccio, hobbies, mf_list, md_list, obiettivi_sel)
                st.success("Profilo salvato! Se i gruppi sono stati pubblicati, verranno visualizzati qui sotto.")
            # Controlla se gruppi pubblicati
            try:
                sess_info = supabase.table("sessioni").select("gruppi_pubblicati").eq("id", session_id).execute()
                published = sess_info.data[0]["gruppi_pubblicati"] if sess_info.data else False
            except Exception:
                published = False
            if published:
                g = get_user_group(session_id, nickname_id)
                if g:
                    st.subheader("Il tuo gruppo")
                    st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**")
                    member_ids = g.get("membri") or []
                    alias_map2 = {}
                    if member_ids:
                        nick_res = supabase.table("nicknames").select("id, code4, nickname").in_("id", member_ids).execute()
                        for r in nick_res.data or []:
                            alias_map2[r["id"]] = r.get("nickname") or f"{r.get('code4'):04d}"
                    members_display = []
                    for mid in member_ids:
                        name = alias_map2.get(mid, mid[:4])
                        if mid == nickname_id:
                            members_display.append(f"**{name} (tu)**")
                        else:
                            members_display.append(name)
                    st.write(", ".join(members_display))
                else:
                    st.info("Non sei ancora assegnato a un gruppo.")