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

import time # ⏱ usato per una breve attesa dopo l'inserimento del nickname

import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager
from supabase import create_client
import qrcode
from datetime import timedelta

# ---------------------------------------------------------
# ⚡ Cache temporanea per il caricamento profilo studente
# ---------------------------------------------------------
@st.cache_data(ttl=30)
def load_profile_cached(nickname_id: str):
    """Carica il profilo dello studente con cache di 30s per ridurre le query."""
    try:
        res = supabase.table("profiles").select("*").eq("id", nickname_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


# ---------------------------------------------------------
# ⚡ Cache temporanea per lobby docente
# ---------------------------------------------------------
@st.cache_data(ttl=15)
def get_nicknames_cached(session_id: str):
    """Lista nicknames per lobby docente con cache 15s."""
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


@st.cache_data(ttl=15)
def get_ready_ids_cached(session_id: str):
    """Set di nickname_id con profilo presente, cache 15s."""
    try:
        nicks = get_nicknames_cached(session_id)
        nick_ids = [n["id"] for n in nicks]
        if not nick_ids:
            return set()
        res = supabase.table("profiles").select("id").in_("id", nick_ids).execute()
        return set([r["id"] for r in (res.data or [])])
    except Exception:
        return set()


# 🧭 Config pagina — deve essere la PRIMA chiamata Streamlit
st.set_page_config(page_title="Gruppi login-free", page_icon="📚", layout="centered")




# Debug toggle (visibile in sidebar)
st.sidebar.title("⚙️ Impostazioni sviluppatore")
DEBUG_MODE = st.sidebar.checkbox("Attiva log debug", value=False)


def log_debug(msg: str):
    """Mostra messaggi solo se debug attivo."""
    if DEBUG_MODE:
        st.info(f"[DEBUG] {msg}")






# inizializzazione sicura che non blocca mai l'app
try:
    cookies = EncryptedCookieManager(prefix="istudy_", password="...")

    # il metodo ready può fallire o restare False dopo reset → bypass controllato
    ready = False
    try:
        ready = cookies.ready()
    except Exception:
        ready = False

    # 🛑 Gate inizializzazione cookie: nessuna manipolazione prima del round-trip
    if not ready:
        st.sidebar.info("Inizializzo i cookie… ricarico l'interfaccia.")
        st.stop()


except Exception as e:
    st.sidebar.error(f"Cookie manager non inizializzabile: {e}")
        # 🧩 DummyCookie compatibile con dict per evitare crash in fallback
    class DummyCookie(dict):
        """Sostituto sicuro quando il cookie manager fallisce.
        Supporta get/set/item per compatibilità completa.
        """
        def __getitem__(self, key):
            return self.get(key)

        def __setitem__(self, key, value):
            # ignora ma evita errori
            super().update({key: value})

        def get(self, key, default=None):
            return super().get(key, default)

        def save(self):
            pass

        def clear(self):
            super().clear()

        def pop(self, key, default=None):
            return super().pop(key, default)
    cookies = DummyCookie()




# ---------------------------------------------------------
# 🔧 Pulsante debug: cancella manualmente TUTTI i cookie
# ---------------------------------------------------------
def manual_cookie_reset():
    try:
        cookies.clear()     # rimuove tutte le chiavi del prefisso 'istudy_'
        cookies.save()      # SALVA UNA SOLA VOLTA per evitare DuplicateElementKey
        st.sidebar.success("Tutti i cookie sono stati rimossi.")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Errore durante la rimozione: {e}")

# Aggiunge il pulsante in sidebar
st.sidebar.button("🧹 Cancella tutti i cookie", on_click=manual_cookie_reset)

# (facoltativo) Stato attuale cookie per debug
if 'DEBUG_MODE' in globals() and DEBUG_MODE:
    try:
        st.sidebar.write("[DEBUG] Cookie attivi:", list(cookies.keys()))
    except Exception:
        pass



# ---------------------------------------------------------
# 🌐 Connessione a Supabase (con gestione errori)
# ---------------------------------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_ANON_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")

supabase = None
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Variabili Supabase mancanti: controlla 'SUPABASE_URL' e 'SUPABASE_ANON_KEY' in .streamlit/secrets.toml")
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        st.sidebar.success("✅ Connessione Supabase attiva.")
    except Exception as e:
        st.sidebar.error(f"Connessione Supabase fallita: {e}")
        supabase = None



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
    """Crea una sessione nella tabella 'sessioni' con fallback automatico sui campi mancanti."""
    import uuid
    sid = uuid.uuid4().hex[:8]

    data_iso = (
        data_sessione.strftime("%Y-%m-%d")
        if hasattr(data_sessione, "strftime")
        else str(data_sessione).replace("/", "-")[:10]
    )

    link_pubblico = build_join_url(sid)
    record = {
        "id": sid,
        "nome": nome,
        "materia": materia,
        "data": data_iso,
        "tema": tema,
        "link_pubblico": str(link_pubblico),
        "creato_da": "public",
        "timestamp": datetime.now().isoformat(),
        "attiva": True,
        "chiusa_il": None,
        "pubblicato": False,
    }

    log_debug(f"Tentativo inserimento sessione → {record}")
    try:
        supabase.table("sessioni").insert(record).execute()
        st.success(f"Sessione creata correttamente: {sid}")
    except Exception as e:
        # rimuove automaticamente i campi non accettati
        invalid_fields = []
        for key in list(record.keys()):
            try:
                supabase.table("sessioni").insert({key: record[key]}).execute()
            except Exception:
                invalid_fields.append(key)
        for key in invalid_fields:
            record.pop(key, None)
        log_debug(f"Campi rimossi per compatibilità DB: {invalid_fields}")
        try:
            supabase.table("sessioni").insert(record).execute()
            st.success(f"Sessione creata (senza {', '.join(invalid_fields)}): {sid}")
        except Exception as e2:
            st.error(f"Errore finale inserimento sessione: {e2}")
    return sid



def create_nickname(session_id: str):
    """
    Crea automaticamente un nickname progressivo da 00000 a 99999 per la sessione.
    Logica: next_code = (max(code4 esistenti) + 1). Se supera 99999 lancia errore.
    Fallback: se non riesce a leggere i codici, usa un numero derivato dall'ora.
    """
    try:
        # Legge tutti i code4 esistenti per quella sessione
        res = (
            supabase.table("nicknames")
            .select("code4")
            .eq("session_id", session_id)
            .execute()
        )
        existing = []
        for r in (res.data or []):
            val = r.get("code4")
            try:
                existing.append(int(val))
            except Exception:
                continue

        next_code = (max(existing) + 1) if existing else 0
        if next_code > 99999:
            raise ValueError("Limite massimo 99999 raggiunto per questa sessione.")
    except Exception as e:
        # Fallback robusto se la select fallisce
        st.warning(f"Errore nel calcolo del prossimo codice: {e}")
        # Usa i secondi dell'ora corrente per generare un numero entro 0..99999
        next_code = int(datetime.now().strftime("%H%M%S")) % 100000

    payload = {
        "session_id": session_id,
        "code4": next_code,
        "nickname": None,  # l'alias potrà essere impostato in seguito dal profilo
    }

    # Inserisce il record; se una race condition genera duplicato, ci riprova una volta
    try:
        res_ins = supabase.table("nicknames").insert(payload).execute()
    except Exception as e:
        # Riprova una sola volta con next_code+1 per ridurre il rischio di collisioni simultanee
        try:
            payload["code4"] = (next_code + 1) % 100000
            res_ins = supabase.table("nicknames").insert(payload).execute()
        except Exception as e2:
            raise RuntimeError(f"Impossibile creare nickname automatico: {e2}")

    if res_ins.data:
        return res_ins.data[0]

    raise RuntimeError("Impossibile creare nickname automatico")


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

    start_time = datetime.now()
    log_debug("Avvio salvataggio profilo...")

    # --- helper: forza liste native di stringhe per colonne text[] ---
    def to_list(x):
        """Ritorna sempre una lista di stringhe (compatibile con text[])."""
        if x is None:
            return []
        if isinstance(x, (list, tuple, set)):
            return ["" if v is None else str(v) for v in x]
        return [str(x)]

    now_str = datetime.now().isoformat()

    # --- payload profilo: campi array come liste native di stringhe (text[]) ---
    record = {
        "id": nickname_id,
        "approccio": approccio,
        "hobby": to_list(hobby),                    # text[]
        "materie_fatte": to_list(materie_fatte),    # text[]
        "materie_dafare": to_list(materie_dafare),  # text[]
        "obiettivi": to_list(obiettivi),            # text[]
        "future_role": future_role,                 # text
        "created_at": now_str,
        "updated_at": now_str,
    }

    # --- preflight: UUID valido e presenza in 'nicknames' (FK) ---
    try:
        import uuid as _uuid
        _ = _uuid.UUID(nickname_id)
    except Exception:
        raise RuntimeError(f"nickname_id non è un UUID valido: {nickname_id}")

    nick_chk = (
        supabase.table("nicknames")
        .select("id")
        .eq("id", nickname_id)
        .limit(1)
        .execute()
    )
    if not nick_chk.data:
        raise RuntimeError(f"nickname_id inesistente in 'nicknames': {nickname_id}")
    log_debug("Preflight OK: nickname esiste.")

    # --- scrittura ottimizzata con UPSERT (merge automatico) ---
    try:
        # 🔹 esegue un'unica query: inserisce o aggiorna in base all'id esistente
        res = (
            supabase.table("profiles")
            .upsert(record, on_conflict="id")
            .execute()
        )
        log_debug(f"UPSERT eseguito con successo: {getattr(res, 'data', None)}")

    except Exception as e:
        # 🔸 fallback unico in caso di errore schema → rimuove solo il campo opzionale future_role
        log_debug(f"UPSERT fallito: {e}. Riprovo senza 'future_role'.")
        rec2 = dict(record)
        rec2.pop("future_role", None)
        try:
            supabase.table("profiles").upsert(rec2, on_conflict="id").execute()
            log_debug("UPSERT senza 'future_role' riuscito.")
        except Exception as e2:
            st.error(f"Errore durante l'UPSERT anche senza 'future_role': {e2}")


    # --- verifica esistenza riga salvata (indipendente dal contenuto) ---
    chk = (
        supabase.table("profiles")
        .select("id")
        .eq("id", nickname_id)
        .limit(1)
        .execute()
    )
    persisted = bool(chk.data)
    log_debug(f"Persisted? {persisted}")
    if not persisted:
        raise RuntimeError("Profilo non persistito. Controlla RLS o lo schema della tabella 'profiles'.")

    # --- aggiorna alias su nicknames solo dopo persistenza confermata ---
    try:
        supabase.table("nicknames").update({"nickname": alias}).eq("id", nickname_id).execute()
    except Exception as e:
        st.warning(f"Errore nell'aggiornamento del nickname: {e}")

    elapsed = (datetime.now() - start_time).total_seconds()
    log_debug(f"Profilo salvato in {elapsed:.2f} s")



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
    start_time = datetime.now()
    log_debug("Avvio creazione gruppi...")

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
    # suddivide in gruppi con algoritmo round-robin serpentino
    bucketed = []
    for i in range(0, len(students), group_size):
        chunk = students[i:i + group_size]
        # alterna l’ordine ogni due blocchi per bilanciare profili simili
        if (i // group_size) % 2 == 1:
            chunk.reverse()
        bucketed.extend(chunk)

    groups = [bucketed[i:i + group_size] for i in range(0, len(bucketed), group_size)]

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

        # ✅ Creazione record con strutture dati native
        record = {
            "sessione_id": session_id,
            "nome_gruppo": nome,
            "membri": membri_ids,                   # lista di UUID → colonna uuid[] o text[]
            "tema": theme,
            "data_creazione": datetime.now().isoformat(),
            "pesi": weights,                        # dizionario → colonna jsonb
        }

        try:
            supabase.table("gruppi").insert(record).execute()
        except Exception as e:
            st.warning(f"Errore inserimento gruppo {nome}: {e}")
            log_debug(f"Record fallito: {record}")

    st.success(f"Creati {len(groups)} gruppi basati sui pesi selezionati.")
    # marca come non pubblicati nello stato locale
    published = st.session_state.setdefault("published_sessions", {})
    published[session_id] = False

    elapsed = (datetime.now() - start_time).total_seconds()
    log_debug(f"Gruppi creati in {elapsed:.2f} s per {len(groups)} gruppi.")



def publish_groups(session_id: str):
    """Segna i gruppi come pubblicati sia su DB sia nello stato locale."""
    try:
        supabase.table("sessioni").update({"pubblicato": True}).eq("id", session_id).execute()
    except Exception as e:
        st.warning(f"Errore durante la pubblicazione su DB: {e}")
    published = st.session_state.setdefault("published_sessions", {})
    published[session_id] = True
    st.success("Gruppi pubblicati!")

# ---------------------------------------------------------
# 🔄 RESET SESSIONE DOCENTE/STUDENTE (versione stabile)
# ---------------------------------------------------------
def reset_teacher_session():
    """Elimina sessione e cookie in modo sicuro, evitando duplicazioni di Streamlit."""
    # 🚩 Flag temporaneo per bloccare re-idratazione automatica al prossimo rerun
    st.session_state["_teacher_reset_in_progress"] = True

    # 1. Cancella le chiavi di stato
    for k in list(st.session_state.keys()):
        if k.startswith(("teacher_", "student_")) or k in ["published_sessions"]:
            del st.session_state[k]

    # 2. Cancella i cookie in un solo passaggio
    keys_to_clear = [
        "teacher_session_id", "teacher_group_size",
        "student_session_id", "student_nickname_id",
        "student_pin", "student_session_expiry",
    ]
    for k in keys_to_clear:
        cookies.pop(k, None)

    # salva solo una volta per evitare DuplicateElementKey
    cookies.save()

    # 3. Pulisci parametri URL
    try:
        st.experimental_set_query_params()
    except Exception:
        pass

    # 4. Log e reload controllato
    log_debug("Cookie e session_state rimossi. Ricarico interfaccia.")
    st.success("✅ Sessione azzerata. Ricarico interfaccia...")
    st.rerun()

# ---------------------------------------------------------
# 🔄 RESET SESSIONE STUDENTE (sicuro e coerente)
# ---------------------------------------------------------
def reset_student_session():
    """Ripulisce cookie e stato studente evitando loop e incoerenze."""
    # 🚩 Flag temporaneo per bloccare re-idratazione automatica al prossimo rerun
    st.session_state["_student_reset_in_progress"] = True

    # 1️⃣ Cancella chiavi di stato relative allo studente
    for k in list(st.session_state.keys()):
        if k.startswith("student_"):
            del st.session_state[k]

    # 2️⃣ Cancella cookie studente
    for key in ["student_session_id", "student_nickname_id", "student_pin", "student_session_expiry"]:
        cookies.pop(key, None)
    cookies.save()

    # 3️⃣ Pulisci parametri URL
    try:
        st.experimental_set_query_params()
    except Exception:
        pass

    # 4️⃣ Log e reload controllato
    log_debug("Cookie e session_state studente rimossi. Ricarico interfaccia.")
    st.success("✅ Sessione studente azzerata. Ricarico interfaccia...")
    st.rerun()


def get_user_group(session_id: str, nickname_id: str):
    """Ritorna il gruppo in cui si trova il nickname, oppure None."""
        # ✅ STEP 3 — decodifica robusta del campo 'membri' salvato come JSON
    try:
        res = supabase.table("gruppi").select("nome_gruppo, membri").eq("sessione_id", session_id).execute()
        for g in res.data or []:
            raw = g.get("membri")
            # normalizza: se stringa JSON → lista; se None → lista vuota
            if isinstance(raw, str):
                try:
                    members = json.loads(raw)
                except Exception:
                    members = []
            elif isinstance(raw, list):
                members = raw
            else:
                members = []

            # mantieni 'membri' come lista per il resto dell'app
            g["membri"] = members

            if nickname_id in members:
                return g
    except Exception:
        pass
    return None



# ----------------------------------------------------------------------------
# Interfaccia utente
# ----------------------------------------------------------------------------



st.title("🎓 App Gruppi login-free")

# 🧠 Ripresa sessione docente SOLO su richiesta
def resume_teacher_from_cookie():
    """Riprende la sessione docente da cookie in modo esplicito."""
    if st.session_state.get("_teacher_reset_in_progress"):
        # Evita ripristini durante/ subito dopo il reset
        st.session_state.pop("_teacher_reset_in_progress", None)
        if DEBUG_MODE:
            st.sidebar.write("[DEBUG] Reset docente in corso: skip resume.")
        return
    tc = cookies.get("teacher_session_id")
    if tc and tc.strip():
        st.session_state["teacher_session_id"] = tc
        st.sidebar.success(f"Ripresa sessione: {tc}")
        st.rerun()
    else:
        st.sidebar.info("Nessuna sessione salvata nei cookie.")

st.sidebar.button("↩️ Riprendi sessione salvata", on_click=resume_teacher_from_cookie)



# Tab di navigazione principale: Docente vs Studente
tab_teacher, tab_student, tab_fun = st.tabs(["👩‍🏫 Docente", "👤 Studente", "🎉 Fun"])


with tab_teacher:
    """
    Vista per il docente. Permette di creare sessioni, vedere la lobby,
    regolare i pesi per tutte le categorie e creare/pubblicare i gruppi.
    """
    st.header("Gestisci la sessione")
    teacher_sid = st.session_state.get("teacher_session_id")

    # ---------------------------------------------------------
    # CREAZIONE SESSIONE
    # ---------------------------------------------------------
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

                cookies["teacher_session_id"] = sid
                cookies["student_session_expiry"] = str(datetime.now() + timedelta(hours=6))
                cookies.save(key=f"sync_cookies_{sid}")




                # Stato pubblicazione
                published = st.session_state.setdefault("published_sessions", {})
                published[sid] = False
                st.success(f"Sessione '{nome}' creata con ID {sid}.")
                st.rerun()

    # ---------------------------------------------------------
    # SESSIONE ATTIVA
    # ---------------------------------------------------------
    else:
        sid = teacher_sid
        try:
            sess = supabase.table("sessioni").select("nome, materia, data, tema, link_pubblico").eq("id", sid).execute()
        except Exception:
            sess = None

        s = sess.data[0] if sess and sess.data else {}
        st.markdown(f"**ID sessione:** `{sid}`")
        st.markdown(f"**Nome:** {s.get('nome','')}")
        st.markdown(f"**Materia:** {s.get('materia','')}")
        st.markdown(f"**Data:** {s.get('data','')}")
        st.markdown(f"**Tema:** {s.get('tema','')}")
        st.markdown(f"**Dimensione gruppi:** {st.session_state.get('teacher_group_size', 4)}")

        join_url = s.get("link_pubblico", build_join_url(sid))

        # QR code
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(join_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="QR per gli studenti", use_container_width=False)
        st.write("Link pubblico:")
        st.code(join_url)
        st.divider()

        # ---------------------------------------------------------
        # LOBBY STUDENTI (aggiornamento automatico ogni 15s)
        # ---------------------------------------------------------
        st.subheader("Lobby studenti")
        if st.button("🔄 Aggiorna dati", key="refresh_lobby"):
            # ✅ Imposta flag per svuotare cache
            st.session_state["refresh_lobby_trigger"] = True
            st.toast("Cache aggiornata 🔁", icon="♻️")
            st.rerun()


        # aggiorna automaticamente ogni 60 s senza flicker
        st.caption(f"Ultimo aggiornamento: {datetime.now().strftime('%H:%M:%S')}")




        # ⚡ Recupero dati con cache (15s) per ridurre query ripetute
        nicknames = get_nicknames_cached(sid)
        ready_ids = get_ready_ids_cached(sid)

        # 🔄 Refresh cache manuale quando richiesto
        if st.session_state.get("refresh_lobby_trigger"):
            get_nicknames_cached.clear()
            get_ready_ids_cached.clear()
            st.session_state.pop("refresh_lobby_trigger", None)

        st.metric("Scansionati", len(nicknames))
        st.metric("Pronti", len(ready_ids))

        if nicknames:
            table_data = []
            for n in nicknames:
                pin = n.get("code4")
                alias = n.get("nickname") or "—"
                stato = "✅" if n.get("id") in ready_ids else "⏳"
                table_data.append({"Nickname": f"{pin:05d}" if pin is not None else "----", "Alias": alias, "Pronto": stato})
            st.table(table_data)
        else:
            st.write("Nessuno studente ha ancora scansionato.")
        st.divider()

        # ---------------------------------------------------------
        # PESI DI MATCHING
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # BOTTONI DOCENTE
        # ---------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        if col1.button("🔀 Crea gruppi", key="doc_crea_gruppi"):
            size = st.session_state.get("teacher_group_size", 4)
            create_groups_ext(sid, size, weights)
        if col2.button("📢 Pubblica gruppi", key="doc_pubblica_gruppi"):
            publish_groups(sid)
        if col3.button("♻️ Nuova sessione", key="doc_reset_session"):
            reset_teacher_session()


        st.divider()

                # ---------------------------------------------------------
        # GESTIONE SESSIONE AVANZATA
        # ---------------------------------------------------------
        st.divider()
        st.subheader("Gestione avanzata sessione")

        # 🗑️ CANCELLA SESSIONE
        if st.button("🗑️ Cancella sessione", key="doc_delete_session"):
            confirm = st.radio("Sei sicuro di voler cancellare questa sessione?", ["No", "Sì"], key="confirm_delete")
            if confirm == "Sì":
                try:
                    supabase.table("gruppi").delete().eq("sessione_id", sid).execute()
                    supabase.table("nicknames").delete().eq("session_id", sid).execute()
                    supabase.table("sessioni").delete().eq("id", sid).execute()
                    st.success(f"Sessione {sid} cancellata con successo.")
                    reset_teacher_session()

                except Exception as e:
                    st.error(f"Errore durante la cancellazione: {e}")

        # 📤 ESPORTA DATI SESSIONE
        import pandas as pd

        if st.button("📤 Esporta dati sessione in CSV", key="doc_export_csv"):
            try:
                nick_res = supabase.table("nicknames").select("id, code4, nickname, session_id").eq("session_id", sid).execute()
                prof_res = supabase.table("profiles").select("*").in_("id", [n["id"] for n in nick_res.data or []]).execute()
                group_res = supabase.table("gruppi").select("sessione_id, nome_gruppo, membri").eq("sessione_id", sid).execute()

                df_nick = pd.DataFrame(nick_res.data or [])
                df_prof = pd.DataFrame(prof_res.data or [])
                df_group = pd.DataFrame(group_res.data or [])

                if not df_prof.empty and not df_nick.empty:
                    df_merge = df_nick.merge(df_prof, on="id", how="left")
                else:
                    df_merge = df_nick

                csv_buf = BytesIO()
                df_merge.to_csv(csv_buf, index=False, encoding="utf-8-sig")
                csv_buf.seek(0)
                st.download_button(
                    label="📄 Scarica CSV (studenti + profili)",
                    data=csv_buf,
                    file_name=f"dati_sessione_{sid}.csv",
                    mime="text/csv",
                )

                if not df_group.empty:
                    csv_buf2 = BytesIO()
                    df_group.to_csv(csv_buf2, index=False, encoding="utf-8-sig")
                    csv_buf2.seek(0)
                    st.download_button(
                        label="📄 Scarica CSV (gruppi)",
                        data=csv_buf2,
                        file_name=f"gruppi_sessione_{sid}.csv",
                        mime="text/csv",
                    )
            except Exception as e:
                st.error(f"Errore durante l'esportazione CSV: {e}")

        # ---------------------------------------------------------
        # GRUPPI CREATI
        # ---------------------------------------------------------
        st.subheader("Gruppi creati")
        try:
            res = supabase.table("gruppi").select("nome_gruppo, membri").eq("sessione_id", sid).execute()
            gruppi_creati = res.data or []
        except Exception:
            gruppi_creati = []

        if not gruppi_creati:
            st.info("Nessun gruppo ancora creato.")
        else:
            # ✅ Normalizza 'membri' a lista
            for g in gruppi_creati:
                raw = g.get("membri")
                if isinstance(raw, str):
                    try:
                        g["membri"] = json.loads(raw)
                    except Exception:
                        g["membri"] = []
                elif isinstance(raw, list):
                    g["membri"] = raw
                else:
                    g["membri"] = []

            # Mappa alias per gli ID membri
            all_ids = list({mid for g in gruppi_creati for mid in g["membri"]})
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
                        alias_map[r["id"]] = r.get("nickname") or (f"{pin:04d}" if isinstance(pin, int) else "")
                except Exception:
                    pass

            # Rendering elenco gruppi
            for g in gruppi_creati:
                st.markdown(f"**{g.get('nome_gruppo','Gruppo')}**")
                members_names = [
                    alias_map.get(mid, (mid[:4] if isinstance(mid, str) else str(mid)))
                    for mid in g["membri"]
                ]
                st.write(", ".join(members_names) if members_names else "—")


with tab_student:
    """
    Vista per lo studente. Permette di inserire l'ID sessione, scegliere un
    nickname a 4 cifre e compilare il profilo. Mostra il gruppo una volta
    pubblicato.
    """
    st.header("Partecipa alla sessione")

    # ---------------------------------------------------------
    # 🔒 COOKIE → STATO (persistenza 6 ore) con controllo reset
    # ---------------------------------------------------------
    if not st.session_state.get("_student_reset_in_progress"):
        # Carica cookie solo se non c'è già una sessione attiva
        if not st.session_state.get("student_session_id") and cookies.get("student_session_id"):
            st.session_state["student_session_id"] = cookies.get("student_session_id")
        if not st.session_state.get("student_nickname_id") and cookies.get("student_nickname_id"):
            st.session_state["student_nickname_id"] = cookies.get("student_nickname_id")
        if not st.session_state.get("student_pin") and cookies.get("student_pin"):
            st.session_state["student_pin"] = cookies.get("student_pin")
    else:
        # Durante il reset evita il ripristino automatico e rimuove il flag
        st.session_state.pop("_student_reset_in_progress", None)
        if DEBUG_MODE:
            st.sidebar.write("[DEBUG] Reset studente in corso: skip re-idratazione.")

    # ---------------------------------------------------------
    # LETTURA QUERY PARAM compatibile con versioni diverse di Streamlit
    # ---------------------------------------------------------
    qp = {}
    try:
        # Streamlit >= 1.30
        qp_obj = getattr(st, "query_params", None)
        if qp_obj:
            qp = dict(qp_obj)
    except Exception:
        pass

    if not qp:
        try:
            # Versioni precedenti
            qp = st.experimental_get_query_params()
        except Exception:
            qp = {}

    qp_session = None
    if qp:
        qp_val = qp.get("session_id")
        if qp_val:
            qp_session = qp_val[0] if isinstance(qp_val, (list, tuple)) else qp_val

    # ---------------------------------------------------------
    # INPUT SESSIONE
    # ---------------------------------------------------------
    default_session = (
        qp_session
        or st.session_state.get("student_session_id")
        or cookies.get("student_session_id")
        or ""
    )
    session_id_input = st.text_input(
        "ID sessione", value=default_session, max_chars=8, key="stu_session_input"
    )

    # Cambio sessione → reset nickname
    if session_id_input and session_id_input != st.session_state.get("student_session_id"):
        st.session_state["student_session_id"] = session_id_input
        st.session_state.pop("student_nickname_id", None)
        st.session_state.pop("student_pin", None)
        # Pulizia selettiva dei soli cookie dello studente
        for key in ["student_session_id", "student_nickname_id", "student_pin", "student_session_expiry"]:
            try:
                cookies.pop(key, None)
            except Exception:
                pass

        cookies["student_session_id"] = session_id_input
        cookies["student_session_expiry"] = str(datetime.now() + timedelta(hours=6))
        cookies.save()

    # ---------------------------------------------------------
    # SUB-TABS: NICKNAME / PROFILO
    # ---------------------------------------------------------
    subtab_pin, subtab_profilo = st.tabs(["🔑 Nickname", "📝 Profilo"])

    # ---------------------------------------------------------
    # NICKNAME
    # ---------------------------------------------------------
    with subtab_pin:
        if not session_id_input:
            st.info("Inserisci l'ID della sessione per procedere.")
        else:
            nickname_id = st.session_state.get("student_nickname_id")
            nickname_session = st.session_state.get("student_session_id_cached")

            if not nickname_id or nickname_session != session_id_input:
                # ✅ Assegnazione automatica del nickname
                if st.button("Conferma nickname", key="stu_confirm_pin"):
                    with st.spinner("Assegnazione automatica in corso..."):
                        try:
                            # Crea nickname automatico su Supabase
                            new_nick = create_nickname(session_id_input)

                            # ⏱ breve attesa per la propagazione su DB
                            time.sleep(0.5)

                            # 🔍 Verifica presenza effettiva del record
                            chk = (
                                supabase.table("nicknames")
                                .select("id")
                                .eq("id", new_nick["id"])
                                .limit(1)
                                .execute()
                            )

                            if not chk.data:
                                st.warning("Registrazione in corso, attendi un secondo e aggiorna la pagina.")
                            else:
                                # ✅ Aggiorna stato e cookie
                                st.session_state["student_nickname_id"] = new_nick["id"]
                                st.session_state["student_session_id_cached"] = session_id_input
                                st.session_state["student_pin"] = f"{new_nick['code4']:05d}"

                                cookies["student_session_id"] = session_id_input
                                cookies["student_nickname_id"] = new_nick["id"]
                                cookies["student_pin"] = st.session_state["student_pin"]
                                cookies["student_session_expiry"] = str(datetime.now() + timedelta(hours=6))
                                cookies.save(key=f"sync_cookies_{session_id_input}")


                                st.success(f"Nickname assegnato automaticamente: {st.session_state['student_pin']}")
                        except Exception as e:
                            st.error(f"Errore durante l'assegnazione del nickname: {e}")

            else:
                st.success("Nickname già confermato. Puoi compilare il profilo nella scheda successiva.")
                st.write(f"Il tuo nickname: {st.session_state.get('student_pin', '—')}")

                # 🔄 Assicura coerenza cookie ↔ stato
                cookies["student_session_id"] = st.session_state["student_session_id"]
                cookies["student_nickname_id"] = st.session_state["student_nickname_id"]
                cookies["student_pin"] = st.session_state["student_pin"]
                cookies["student_session_expiry"] = str(datetime.now() + timedelta(hours=6))
                cookies.save()

    # ---------------------------------------------------------
    # PROFILO
    # ---------------------------------------------------------
    with subtab_profilo:
        nickname_id = st.session_state.get("student_nickname_id")
        if not nickname_id:
            st.info("Prima scegli un nickname nella scheda precedente.")
        else:
            # Carica profilo esistente
            profile_data = load_profile_cached(nickname_id)


            with st.form("stud_form_profilo"):
                # Recupera alias dal DB 'nicknames' per coerenza
                alias_default = st.session_state.get("student_pin", "")
                try:
                    nick_row = supabase.table("nicknames").select("nickname, code4").eq("id", nickname_id).execute()
                    if nick_row.data:
                        alias_default = nick_row.data[0].get("nickname") or f"{nick_row.data[0].get('code4'):04d}"
                except Exception:
                    pass

                alias = st.text_input(
                    "Alias (puoi usare il tuo nickname o un nome)",
                    value=alias_default,
                    max_chars=12,
                )

                approcci = ["Analitico", "Creativo", "Pratico", "Comunicativo"]
                selected_app = profile_data.get("approccio") if profile_data else approcci[0]
                approccio = st.selectbox(
                    "Approccio al lavoro di gruppo",
                    approcci,
                    index=approcci.index(selected_app) if selected_app in approcci else 0,
                )

                hobby_options = [
                    "Sport", "Lettura", "Musica", "Viaggi", "Videogiochi",
                    "Arte", "Volontariato", "Cucina", "Fotografia", "Cinema",
                ]
                current_hobbies = []
                raw_h = profile_data.get("hobby") if profile_data else []
                if raw_h:
                    try:
                        current_hobbies = json.loads(raw_h) if isinstance(raw_h, str) else raw_h
                    except Exception:
                        current_hobbies = [raw_h]
                hobbies = st.multiselect(
                    "Hobby", hobby_options,
                    default=[h for h in current_hobbies if h in hobby_options],
                )

                current_fatte = []
                raw_fatte = profile_data.get("materie_fatte") if profile_data else []
                if raw_fatte:
                    try:
                        current_fatte = json.loads(raw_fatte) if isinstance(raw_fatte, str) else raw_fatte
                    except Exception:
                        current_fatte = [raw_fatte]
                materie_fatte = st.multiselect(
                    "Materie già superate",
                    options=SUBJECTS_OPTIONS,
                    default=[m for m in current_fatte if m in SUBJECTS_OPTIONS],
                )

                current_dafare = []
                raw_dafare = profile_data.get("materie_dafare") if profile_data else []
                if raw_dafare:
                    try:
                        current_dafare = json.loads(raw_dafare) if isinstance(raw_dafare, str) else raw_dafare
                    except Exception:
                        current_dafare = [raw_dafare]
                available_dafare = [m for m in SUBJECTS_OPTIONS if m not in materie_fatte]
                materie_dafare = st.multiselect(
                    "Materie da fare",
                    options=available_dafare,
                    default=[m for m in current_dafare if m in available_dafare],
                )

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
                    try:
                        current_ob = json.loads(raw_o) if isinstance(raw_o, str) else raw_o
                    except Exception:
                        current_ob = [raw_o]
                obiettivi_sel = st.multiselect(
                    "Obiettivi accademici",
                    options=obiettivi_opts,
                    default=[o for o in current_ob if o in obiettivi_opts],
                )

                fr_default = profile_data.get("future_role") if profile_data else FUTURE_ROLE_OPTIONS[0]
                future_role = st.selectbox(
                    "Dove mi vedo fra 5 anni",
                    options=FUTURE_ROLE_OPTIONS,
                    index=FUTURE_ROLE_OPTIONS.index(fr_default)
                    if fr_default in FUTURE_ROLE_OPTIONS else 0,
                )

                invia = st.form_submit_button("💾 Salva profilo")

            # ✅ STEP 1 — Salvataggio profilo con validazioni e gestione errori
                if invia:
                    # 1) Controlli minimi
                    if not st.session_state.get("student_nickname_id"):
                        st.error("ID nickname mancante. Conferma il nickname nella scheda precedente e riprova.")
                    elif supabase is None:
                        st.error("Connessione al database non disponibile. Controlla le credenziali Supabase.")
                    else:
                        # ⏳ Mostra loader temporaneo per ridurre la sensazione di blocco UI
                        with st.spinner("Salvataggio in corso..."):
                            time.sleep(0.2)  # breve pausa per sincronizzazione visiva
                            try:
                                # 2️⃣ Salvataggio effettivo nel DB
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

                                # ✅ Feedback immediato e aggiornamento stato
                                st.toast("Profilo salvato ✅", icon="💾")
                                st.session_state["profile_saved"] = True

                                # ⚡ Aggiorna cache del profilo dopo il salvataggio
                                load_profile_cached.clear()

                            except Exception as e:
                                # ⚠️ Gestione errori chiara
                                st.error(f"Errore durante il salvataggio del profilo: {e}")


            # ---------------------------------------------------------
            # GRUPPO ASSEGNATO
            # ---------------------------------------------------------
            # Verifica pubblicazione su DB con fallback allo stato locale
            sid_curr = st.session_state.get("student_session_id")
            pub_db = False
            try:
                r = supabase.table("sessioni").select("pubblicato").eq("id", sid_curr).execute()
                pub_db = bool(r.data and r.data[0].get("pubblicato"))
            except Exception:
                pub_db = False

            published = pub_db or st.session_state.get("published_sessions", {}).get(sid_curr)
            if published:
                g = get_user_group(sid_curr, nickname_id)

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


with tab_fun:
    """
    🎉 Area social e divertimento.
    In futuro conterrà mini-giochi, quiz e altre attività per far socializzare gli studenti.
    Per ora mostra le statistiche della sessione attuale con grafici interattivi.
    """
    st.header("📊 Statistiche della sessione")

    sessione_corrente = st.session_state.get("student_session_id") or st.session_state.get("teacher_session_id")
    if not sessione_corrente:
        st.info("Nessuna sessione attiva. Accedi prima come docente o studente.")
    else:
        try:
            import pandas as pd
            import plotly.express as px
            import json

            # ---------------------------------------------------------
            # 📋 DATI BASE
            # ---------------------------------------------------------
            nicknames = get_nicknames_cached(sessione_corrente)
            ready_ids = get_ready_ids_cached(sessione_corrente)
            totali = len(nicknames)
            pronti = len(ready_ids)
            completion_rate = round((pronti / totali) * 100, 1) if totali > 0 else 0

            # ---------------------------------------------------------
            # 📊 CARD RIASSUNTIVE
            # ---------------------------------------------------------
            st.subheader("📈 Riepilogo sessione")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="🎓 Totale studenti", value=totali)
            with col2:
                st.metric(label="✅ Profili completati", value=pronti)
            with col3:
                st.metric(label="📈 Percentuale completamento", value=f"{completion_rate}%")

            # ---------------------------------------------------------
            # 🔹 Caricamento profili
            # ---------------------------------------------------------
            prof_res = supabase.table("profiles").select("*").in_("id", list(ready_ids)).execute()

            # ---------------------------------------------------------
            # 🔹 Grafico approccio al lavoro di gruppo
            # ---------------------------------------------------------
            st.subheader("Approccio al lavoro di gruppo")
            try:
                df = pd.DataFrame(prof_res.data)
                if "approccio" in df.columns and not df["approccio"].isna().all():
                    fig = px.histogram(
                        df,
                        x="approccio",
                        color="approccio",
                        title="Distribuzione dell'approccio al lavoro di gruppo",
                        color_discrete_sequence=px.colors.qualitative.Vivid,
                    )
                    fig.update_layout(showlegend=False, template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Nessun dato sull'approccio disponibile.")
            except Exception as e:
                st.warning(f"Errore nel grafico approccio: {e}")

            # ---------------------------------------------------------
            # 🔹 Grafico hobby
            # ---------------------------------------------------------
            st.subheader("Distribuzione hobby")
            hobbies_flat = []
            for p in (prof_res.data or []):
                raw = p.get("hobby")
                if isinstance(raw, str):
                    try:
                        hobbies_flat.extend(json.loads(raw))
                    except Exception:
                        hobbies_flat.append(raw)
                elif isinstance(raw, list):
                    hobbies_flat.extend(raw)
            if hobbies_flat:
                df_hobby = pd.DataFrame({"Hobby": hobbies_flat})
                fig_hobby = px.histogram(
                    df_hobby,
                    x="Hobby",
                    color="Hobby",
                    title="Hobby più popolari nella sessione",
                    color_discrete_sequence=px.colors.qualitative.Pastel1,
                )
                fig_hobby.update_layout(showlegend=False, template="plotly_dark")
                st.plotly_chart(fig_hobby, use_container_width=True)
            else:
                st.info("Ancora nessun hobby disponibile.")

            # ---------------------------------------------------------
            # 🔹 Materie già superate
            # ---------------------------------------------------------
            st.subheader("Materie già superate")
            subjects_done = []
            for p in (prof_res.data or []):
                raw = p.get("materie_fatte")
                if isinstance(raw, str):
                    try:
                        subjects_done.extend(json.loads(raw))
                    except Exception:
                        subjects_done.append(raw)
                elif isinstance(raw, list):
                    subjects_done.extend(raw)
            if subjects_done:
                df_done = pd.DataFrame({"Materia": subjects_done})
                fig_done = px.histogram(
                    df_done,
                    x="Materia",
                    color="Materia",
                    title="Materie già superate",
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig_done.update_layout(showlegend=False, template="plotly_dark")
                st.plotly_chart(fig_done, use_container_width=True)
            else:
                st.info("Nessuna materia superata registrata.")

            # ---------------------------------------------------------
            # 🔹 Materie da fare
            # ---------------------------------------------------------
            st.subheader("Materie da fare")
            subjects_todo = []
            for p in (prof_res.data or []):
                raw = p.get("materie_dafare")
                if isinstance(raw, str):
                    try:
                        subjects_todo.extend(json.loads(raw))
                    except Exception:
                        subjects_todo.append(raw)
                elif isinstance(raw, list):
                    subjects_todo.extend(raw)
            if subjects_todo:
                df_todo = pd.DataFrame({"Materia": subjects_todo})
                fig_todo = px.bar(
                    df_todo,
                    x="Materia",
                    color="Materia",
                    title="Materie ancora da completare",
                    color_discrete_sequence=px.colors.qualitative.Safe,
                )
                fig_todo.update_layout(showlegend=False, template="plotly_dark")
                st.plotly_chart(fig_todo, use_container_width=True)
            else:
                st.info("Nessuna materia da fare registrata.")

            # ---------------------------------------------------------
            # 🔹 Obiettivi accademici
            # ---------------------------------------------------------
            st.subheader("Obiettivi accademici")
            goals_flat = []
            for p in (prof_res.data or []):
                raw = p.get("obiettivi")
                if isinstance(raw, str):
                    try:
                        goals_flat.extend(json.loads(raw))
                    except Exception:
                        goals_flat.append(raw)
                elif isinstance(raw, list):
                    goals_flat.extend(raw)
            if goals_flat:
                df_goals = pd.DataFrame({"Obiettivo": goals_flat})
                fig_goals = px.pie(
                    df_goals,
                    names="Obiettivo",
                    hole=0.5,
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    title="Distribuzione obiettivi accademici"
                )
                fig_goals.update_traces(textinfo="percent+label")
                fig_goals.update_layout(template="plotly_dark")
                st.plotly_chart(fig_goals, use_container_width=True)
            else:
                st.info("Nessun obiettivo disponibile.")

            # ---------------------------------------------------------
            # 🔹 Visione futura
            # ---------------------------------------------------------
            st.subheader("Visione futura (5 anni)")
            futures = [p.get("future_role") for p in (prof_res.data or []) if p.get("future_role")]
            if futures:
                df_future = pd.DataFrame({"Ruolo futuro": futures})
                fig_future = px.bar(
                    df_future,
                    x="Ruolo futuro",
                    color="Ruolo futuro",
                    title="Dove si vedono gli studenti fra 5 anni",
                    color_discrete_sequence=px.colors.qualitative.Vivid,
                )
                fig_future.update_layout(showlegend=False, template="plotly_dark")
                st.plotly_chart(fig_future, use_container_width=True)
            else:
                st.info("Nessun dato sulla visione futura.")
        except Exception as e:
            st.error(f"Errore durante la generazione dei grafici: {e}")
