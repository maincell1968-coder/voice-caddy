"""
Supabase Service per Voice Caddy Pro.
Gestisce il salvataggio persistente nel cloud e il caricamento automatico
della sacca da golf dell'utente, con fallback sicuro locale e idempotenza (upsert).
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

# Safe import di Streamlit
try:
    import streamlit as st
except ImportError:
    st = None

# Safe import del client ufficiale Supabase
try:
    from supabase import Client, create_client
except ImportError:
    Client = None
    create_client = None

from core.user_profile import ClubDetail, ShaftFlex, sort_clubs_by_distance
from core.schemas import GolfRoundData

logger = logging.getLogger(__name__)

# Cache per l'istanza del client in ambienti non-Streamlit
_GLOBAL_SUPABASE_CLIENT: Optional[Any] = None


def get_supabase_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Recupera l'URL e la chiave Supabase in ordine di priorità:
    1. st.secrets["SUPABASE_URL"] / st.secrets["SUPABASE_KEY"]
    2. Variabili d'ambiente di sistema SUPABASE_URL / SUPABASE_KEY
    """
    url: Optional[str] = None
    key: Optional[str] = None

    if st is not None:
        try:
            if hasattr(st, "secrets"):
                if "SUPABASE_URL" in st.secrets:
                    url = str(st.secrets["SUPABASE_URL"]).strip()
                if "SUPABASE_KEY" in st.secrets:
                    key = str(st.secrets["SUPABASE_KEY"]).strip()
        except Exception as e_sec:
            logger.debug(f"Impossibile leggere st.secrets: {e_sec}")

    if not url:
        url = os.environ.get("SUPABASE_URL", "").strip() or None
    if not key:
        key = os.environ.get("SUPABASE_KEY", "").strip() or None

    return url, key


def init_supabase() -> Tuple[Optional[Any], Optional[str]]:
    """
    Inizializza e restituisce un'istanza del client Supabase.
    Se la libreria non è installata o le credenziali mancano,
    restituisce (None, messaggio_esplicativo) senza mandare l'app in crash.
    """
    global _GLOBAL_SUPABASE_CLIENT

    if create_client is None:
        return None, "La libreria 'supabase' non è installata nel runtime Python. Esegui: pip install supabase"

    url, key = get_supabase_credentials()

    if not url or not key:
        return None, "Credenziali Supabase mancanti. Configura SUPABASE_URL e SUPABASE_KEY in st.secrets (.streamlit/secrets.toml)."

    try:
        if _GLOBAL_SUPABASE_CLIENT is not None:
            return _GLOBAL_SUPABASE_CLIENT, None

        client = create_client(url, key)
        _GLOBAL_SUPABASE_CLIENT = client
        return client, None
    except Exception as exc:
        err_msg = f"Errore durante l'inizializzazione del client Supabase: {exc}"
        logger.error(err_msg)
        return None, err_msg


def reset_supabase_client_cache() -> None:
    """Azzera la cache del client (utile per test o cambio credenziali a runtime)."""
    global _GLOBAL_SUPABASE_CLIENT
    _GLOBAL_SUPABASE_CLIENT = None


def normalize_club_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizza una riga/dizionario bastone nel formato canonico JSON richiesto:
    {
        "mazza": "Legno 3",
        "marca": "Callaway",
        "modello": "",
        "shaft": "Regular",
        "distanza_carry": 220
    }
    Accetta indifferentemente chiavi italiane, inglesi o del DataFrame Streamlit.
    """
    mazza = (
        raw.get("mazza")
        or raw.get("Mazza")
        or raw.get("club_name")
        or raw.get("name")
        or "Ferro 7"
    )

    marca = (
        raw.get("marca")
        or raw.get("Marca")
        or raw.get("brand")
        or "Generica"
    )

    modello = (
        raw.get("modello")
        or raw.get("Modello / Tipo")
        or raw.get("modello_tipo")
        or raw.get("model_type")
        or ""
    )

    shaft_val = (
        raw.get("shaft")
        or raw.get("Shaft")
        or raw.get("shaft_flex")
        or "Regular"
    )
    if hasattr(shaft_val, "value"):
        shaft_str = shaft_val.value
    else:
        shaft_str = str(shaft_val)

    carry_val = (
        raw.get("distanza_carry")
        or raw.get("Distanza Carry (m)")
        or raw.get("distanza_carry_m")
        or raw.get("carry_meters")
        or 0
    )
    try:
        carry_int = int(round(float(carry_val)))
    except (ValueError, TypeError):
        carry_int = 0

    return {
        "mazza": str(mazza).strip(),
        "marca": str(marca).strip() if marca else "Generica",
        "modello": str(modello).strip() if modello else "",
        "shaft": shaft_str.strip() if shaft_str else "Regular",
        "distanza_carry": carry_int,
    }


def df_to_clubs_json(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Converte il DataFrame Streamlit della sacca in una lista di dizionari JSON Supabase."""
    if df is None or df.empty:
        return []

    clubs: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        c_dict = row.to_dict()
        # Se la mazza non è nulla o vuota
        if pd.notna(c_dict.get("Mazza")) or pd.notna(c_dict.get("mazza")) or pd.notna(c_dict.get("club_name")):
            clubs.append(normalize_club_dict(c_dict))
    return clubs


def clubs_json_to_df(clubs_json: List[Dict[str, Any]]) -> pd.DataFrame:
    """Converte la lista JSON Supabase nel DataFrame formattato per st.data_editor."""
    if not clubs_json:
        return pd.DataFrame(columns=["Mazza", "Marca", "Modello / Tipo", "Shaft", "Distanza Carry (m)"])

    rows = []
    for item in clubs_json:
        norm = normalize_club_dict(item)
        rows.append({
            "Mazza": norm["mazza"],
            "Marca": norm["marca"],
            "Modello / Tipo": norm["modello"],
            "Shaft": norm["shaft"],
            "Distanza Carry (m)": norm["distanza_carry"]
        })
    return pd.DataFrame(rows)


def clubs_json_to_club_details(clubs_json: List[Dict[str, Any]]) -> List[ClubDetail]:
    """Converte la lista JSON Supabase in una lista di oggetti ClubDetail pydantic."""
    if not clubs_json:
        return []

    clubs: List[ClubDetail] = []
    for item in clubs_json:
        norm = normalize_club_dict(item)

        # Risolvi shaft flex
        shaft_target = norm["shaft"]
        s_flex = ShaftFlex.REGULAR
        for sf in ShaftFlex:
            if sf.value.lower() == shaft_target.lower() or sf.name.lower() == shaft_target.lower():
                s_flex = sf
                break

        clubs.append(ClubDetail(
            club_name=norm["mazza"],
            brand=norm["marca"],
            model_type=norm["modello"],
            shaft_flex=s_flex,
            carry_meters=float(norm["distanza_carry"])
        ))

    return sort_clubs_by_distance(clubs)


def club_details_to_clubs_json(clubs: List[ClubDetail]) -> List[Dict[str, Any]]:
    """Converte una lista di ClubDetail nel formato JSON per Supabase."""
    if not clubs:
        return []

    res: List[Dict[str, Any]] = []
    sorted_clubs = sort_clubs_by_distance(clubs)
    for c in sorted_clubs:
        res.append({
            "mazza": c.club_name,
            "marca": c.brand or "Generica",
            "modello": c.model_type or "",
            "shaft": c.shaft_flex.value if hasattr(c.shaft_flex, "value") else str(c.shaft_flex),
            "distanza_carry": int(round(c.carry_meters))
        })
    return res


def load_golf_bag_from_supabase(bag_id: str = "default") -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Carica la sacca da golf da Supabase per il bag_id specificato.
    
    Ritorna:
        (clubs_list, None) -> se caricata con successo (lista vuota se tabella vuota o record assente)
        (None, error_msg)  -> se Supabase non è configurato o la query genera un'eccezione
    """
    client, err = init_supabase()
    if client is None:
        return None, err

    try:
        response = (
            client.table("golf_bag")
            .select("bag_id, clubs, updated_at")
            .eq("bag_id", bag_id)
            .execute()
        )

        data = response.data
        if not data or len(data) == 0:
            # Nessun record trovato: tabella vuota o bag_id nuovo
            return [], None

        row = data[0]
        raw_clubs = row.get("clubs", [])
        if isinstance(raw_clubs, str):
            raw_clubs = json.loads(raw_clubs)

        normalized = [normalize_club_dict(c) for c in raw_clubs]
        return normalized, None

    except Exception as exc:
        err_msg = f"Errore durante il caricamento da Supabase: {exc}"
        logger.warning(err_msg)
        return None, err_msg


def save_golf_bag_to_supabase(
    clubs: Union[List[Dict[str, Any]], pd.DataFrame, List[ClubDetail]],
    bag_id: str = "default"
) -> Tuple[bool, str]:
    """
    Salva i dati della sacca da golf su Supabase tramite UPSERT atomico
    basato sul campo univoco 'bag_id' (evita duplicazioni).
    
    Ritorna:
        (True, messaggio_successo)
        (False, messaggio_errore)
    """
    client, err = init_supabase()
    if client is None:
        return False, err or "Client Supabase non disponibile."

    try:
        # 1. Normalizzazione input
        if isinstance(clubs, pd.DataFrame):
            json_clubs = df_to_clubs_json(clubs)
        elif clubs and isinstance(clubs[0], ClubDetail):
            json_clubs = club_details_to_clubs_json(clubs)  # type: ignore
        elif isinstance(clubs, list):
            json_clubs = [normalize_club_dict(c) for c in clubs]
        else:
            json_clubs = []

        # 2. Payload per Supabase
        payload = {
            "bag_id": bag_id,
            "clubs": json_clubs,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # 3. Upsert idempotente su conflict 'bag_id'
        response = client.table("golf_bag").upsert(payload, on_conflict="bag_id").execute()

        return True, "Sacca salvata correttamente su Supabase Cloud!"

    except Exception as exc:
        err_msg = f"Errore durante il salvataggio su Supabase: {exc}"
        logger.error(err_msg)
        return False, err_msg


def check_supabase_health() -> Dict[str, Any]:
    """
    Verifica lo stato della connessione Supabase e restituisce un dizionario diagnostico:
    {
        "status": "connected" | "not_configured" | "error",
        "message": str,
        "url": str (mascherato),
        "details": Optional[str]
    }
    """
    url, key = get_supabase_credentials()
    if not url or not key:
        return {
            "status": "not_configured",
            "message": "Credenziali Supabase non configurate in st.secrets.",
            "url": None,
            "details": "Aggiungi SUPABASE_URL e SUPABASE_KEY in .streamlit/secrets.toml"
        }

    # Maschera URL
    masked_url = url
    try:
        if len(url) > 15:
            masked_url = url[:12] + "..." + url[-8:]
    except Exception:
        pass

    client, err = init_supabase()
    if client is None:
        return {
            "status": "error",
            "message": "Inizializzazione fallita",
            "url": masked_url,
            "details": err
        }

    try:
        # Test leggero di lettura con limit 1
        resp = client.table("golf_bag").select("bag_id").limit(1).execute()
        return {
            "status": "connected",
            "message": "Connesso a Supabase Cloud",
            "url": masked_url,
            "details": "Tabella 'golf_bag' pronta e raggiungibile."
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": "Errore connessione tabella Supabase",
            "url": masked_url,
            "details": str(exc)
        }


# ==============================================================================
# GESTIONE PARTITE & GIRI DI GOLF SU SUPABASE CLOUD (QUOTA & ARCHIVIAZIONE)
# ==============================================================================

MAX_CLOUD_ROUNDS_PER_USER: int = 100


def save_round_to_supabase(
    round_id: int | str,
    round_data: GolfRoundData,
    user_id: str = "default_user",
    group_name: str = "strafatti"
) -> Tuple[bool, str]:
    """
    Salva un giro di golf su Supabase (tabella 'golf_rounds') con upsert idempotente
    su round_key = f"{user_id}_{round_id}".
    Ritorna (True, msg) o (False, err_msg) senza mai mandare in crash l'applicazione.
    """
    client, err = init_supabase()
    if client is None:
        return False, err or "Client Supabase non disponibile."

    try:
        round_key = f"{user_id}_{round_id}"
        summary = round_data.performance_summary
        info = round_data.round_info
        raw_dict = json.loads(round_data.model_dump_json())

        payload = {
            "round_key": round_key,
            "user_id": user_id,
            "group_name": group_name,
            "course_name": info.course_name or "Giro Senza Nome",
            "date_played": info.date or "Non specificata",
            "holes_played": info.holes_played or 18,
            "total_score": summary.total_score,
            "total_putts": summary.total_putts,
            "fairway_accuracy_pct": float(summary.fairway_accuracy_pct or 0.0),
            "gir_pct": float(summary.gir_pct or 0.0),
            "scrambling_pct": float(summary.scrambling_pct or 0.0),
            "penalty_strokes": int(summary.penalty_strokes_total or 0),
            "primary_miss": str(summary.primary_miss_tendency or ""),
            "round_data": raw_dict,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        client.table("golf_rounds").upsert(payload, on_conflict="round_key").execute()
        return True, "Partita sincronizzata con successo su Supabase Cloud!"
    except Exception as exc:
        err_msg = f"Errore durante il salvataggio della partita su Supabase: {exc}"
        logger.warning(err_msg)
        return False, err_msg


def load_rounds_from_supabase(user_id: Optional[str] = None) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Carica le partite salvate su Supabase.
    Ritorna (lista_partite, None) o (None, err_msg).
    Se la tabella è vuota o non esiste ancora, gestisce il caso senza crash.
    """
    client, err = init_supabase()
    if client is None:
        return None, err

    try:
        query = client.table("golf_rounds").select(
            "id, round_key, user_id, group_name, course_name, date_played, holes_played, "
            "total_score, total_putts, fairway_accuracy_pct, gir_pct, scrambling_pct, "
            "penalty_strokes, primary_miss, round_data, created_at, updated_at"
        )
        if user_id:
            query = query.eq("user_id", user_id)

        response = query.order("created_at", desc=True).limit(MAX_CLOUD_ROUNDS_PER_USER).execute()
        return response.data or [], None
    except Exception as exc:
        err_msg = f"Errore durante il caricamento delle partite da Supabase: {exc}"
        logger.warning(err_msg)
        return None, err_msg


def get_user_rounds_cloud_count(user_id: str) -> int:
    """Restituisce il numero di partite attualmente archiviate nel cloud per l'utente."""
    rounds, _ = load_rounds_from_supabase(user_id=user_id)
    return len(rounds) if rounds is not None else 0


def sync_all_local_rounds_to_supabase(db: Any, user_id: Optional[str] = None) -> Tuple[int, int]:
    """
    Sincronizza tutte le partite presenti nel database locale SQLite verso Supabase Cloud.
    Ritorna (sincronizzate_con_successo, totale_partite_locali).
    """
    if db is None:
        return 0, 0

    try:
        local_rounds = db.get_all_rounds(user_id=user_id)
        if not local_rounds:
            return 0, 0

        synced = 0
        for r in local_rounds:
            round_obj = db.get_round_by_id(r["id"])
            if round_obj is not None:
                u_id = r.get("user_id") or user_id or "default_user"
                g_name = r.get("group_name") or "strafatti"
                ok, _ = save_round_to_supabase(round_id=r["id"], round_data=round_obj, user_id=u_id, group_name=g_name)
                if ok:
                    synced += 1
        return synced, len(local_rounds)
    except Exception as exc:
        logger.warning(f"Errore durante la migrazione delle partite locali su Supabase: {exc}")
        return 0, 0
