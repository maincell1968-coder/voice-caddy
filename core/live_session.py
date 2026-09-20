from __future__ import annotations

import sqlite3
import json
import time
import contextlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from core.elevation_service import haversine_distance
from core.whs_rules import RoundHandicapProfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "voice_caddy.db"


class LiveSessionManager:
    """
    Gestore dello stato live della partita in corso per ciascuna chat Telegram.
    Mantiene sincronizzati buca corrente, avanzamento dei colpi, coordinate dell'ultima posizione
    e tracciamento dei metri percorsi dal colpo precedente.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self._init_tables()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_sessions (
                    chat_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    course_id TEXT DEFAULT 'conero_golf_club',
                    current_hole INTEGER DEFAULT 1,
                    current_shot_index INTEGER DEFAULT 1,
                    last_latitude REAL,
                    last_longitude REAL,
                    last_altitude REAL,
                    pin_overrides TEXT DEFAULT '{}',
                    selected_tee TEXT DEFAULT 'gialli',
                    game_format TEXT DEFAULT 'stableford',
                    format_percentage REAL DEFAULT 0.95,
                    playing_hcp INTEGER,
                    handicap_profile_json TEXT,
                    awaiting_tee_choice INTEGER DEFAULT 0,
                    has_specified_tee INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS live_shots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT,
                    hole_number INTEGER,
                    shot_index INTEGER,
                    club TEXT,
                    lie TEXT,
                    latitude REAL,
                    longitude REAL,
                    altitude REAL,
                    distance_covered REAL,
                    raw_distance_to_green REAL,
                    plays_like_distance REAL,
                    elevation_diff REAL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migrazione dinamica colonne per database esistenti
            existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(live_sessions)").fetchall()]
            new_columns = [
                ("selected_tee", "TEXT", "'gialli'"),
                ("game_format", "TEXT", "'stableford'"),
                ("format_percentage", "REAL", "0.95"),
                ("playing_hcp", "INTEGER", "NULL"),
                ("handicap_profile_json", "TEXT", "NULL"),
                ("awaiting_tee_choice", "INTEGER", "0"),
                ("has_specified_tee", "INTEGER", "0"),
                ("completed_scores_json", "TEXT", "'[]'"),
                ("last_location_timestamp", "REAL", "NULL"),
                ("round_sequence_json", "TEXT", "'[]'"),
                ("pending_round_state", "TEXT", "'IDLE'"),
                ("pending_round_data_json", "TEXT", "'{}'"),
                ("interactive_state_json", "TEXT", "'{}'"),
            ]
            for col_name, col_type, default_val in new_columns:
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE live_sessions ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")
                    except Exception:
                        pass
            conn.commit()

    def get_or_create_session(self, chat_id: int | str, user_id: str, course_id: str = "conero_golf_club") -> Dict[str, Any]:
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Crea nuova sessione
            cursor.execute("""
                INSERT INTO live_sessions (chat_id, user_id, course_id, current_hole, current_shot_index, selected_tee, game_format, format_percentage)
                VALUES (?, ?, ?, 1, 1, 'gialli', 'stableford', 0.95)
            """, (c_id, user_id, course_id))
            conn.commit()
            return {
                "chat_id": c_id,
                "user_id": user_id,
                "course_id": course_id,
                "current_hole": 1,
                "current_shot_index": 1,
                "last_latitude": None,
                "last_longitude": None,
                "last_altitude": None,
                "pin_overrides": "{}",
                "selected_tee": "gialli",
                "game_format": "stableford",
                "format_percentage": 0.95,
                "playing_hcp": None,
                "handicap_profile_json": None,
                "awaiting_tee_choice": 0
            }

    def set_current_hole(self, chat_id: int | str, hole_number: int) -> bool:
        c_id = str(chat_id)
        h = max(1, min(18, hole_number))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET current_hole = ?, current_shot_index = 1,
                    last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (h, c_id))
            conn.commit()
            return cursor.rowcount > 0

    def next_hole(self, chat_id: int | str) -> int:
        c_id = str(chat_id)
        session = self.get_or_create_session(c_id, user_id="default_user")
        curr = session.get("current_hole", 1)
        next_h = 1 if curr >= 18 else curr + 1
        self.set_current_hole(c_id, next_h)
        return next_h

    def advance_shot(self, chat_id: int | str) -> int:
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET current_shot_index = current_shot_index + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (c_id,))
            conn.commit()
            cursor.execute("SELECT current_shot_index FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            return row["current_shot_index"] if row else 1

    def update_position(
        self,
        chat_id: int | str,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None
    ) -> Tuple[Optional[float], int, int]:
        """
        Aggiorna la posizione live della palla per la chat.
        Calcola la distanza coperta dall'ultima posizione nota (se presente) in metri.
        Restituisce: (distanza_percorsa_dal_colpo_precedente, current_hole, current_shot_index)
        """
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if not row:
                self.get_or_create_session(c_id, user_id="default_user")
                cursor.execute("SELECT * FROM live_sessions WHERE chat_id = ?", (c_id,))
                row = cursor.fetchone()

            prev_lat = row["last_latitude"]
            prev_lon = row["last_longitude"]
            current_hole = row["current_hole"]
            current_shot = row["current_shot_index"]

            distance_covered = None
            if prev_lat is not None and prev_lon is not None:
                distance_covered = haversine_distance(prev_lat, prev_lon, latitude, longitude)

            # Salva la nuova posizione e il timestamp epoch
            now_ts = time.time()
            cursor.execute("""
                UPDATE live_sessions
                SET last_latitude = ?, last_longitude = ?, last_altitude = ?,
                    last_location_timestamp = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (latitude, longitude, altitude, now_ts, c_id))
            conn.commit()

            return distance_covered, current_hole, current_shot

    def get_last_position(self, chat_id: int | str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        Recupera l'ultima posizione GPS registrata per la chat:
        (latitude, longitude, altitude, location_timestamp_epoch)
        """
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_latitude, last_longitude, last_altitude, last_location_timestamp
                FROM live_sessions WHERE chat_id = ?
            """, (c_id,))
            row = cursor.fetchone()
            if row:
                return row["last_latitude"], row["last_longitude"], row["last_altitude"], row["last_location_timestamp"]
        return None, None, None, None

    def set_last_position(
        self,
        chat_id: int | str,
        latitude: float,
        longitude: float,
        altitude: Optional[float] = None
    ) -> bool:
        """Salva direttamente l'ultima posizione GPS nella sessione."""
        c_id = str(chat_id)
        now_ts = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET last_latitude = ?, last_longitude = ?, last_altitude = ?,
                    last_location_timestamp = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (latitude, longitude, altitude, now_ts, c_id))
            conn.commit()
            return cursor.rowcount > 0


    def record_live_shot(
        self,
        chat_id: int | str,
        hole_number: int,
        shot_index: Optional[int] = None,
        club: Optional[str] = None,
        lie: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        altitude: Optional[float] = None,
        distance_covered: Optional[float] = None,
        raw_distance_to_green: Optional[float] = None,
        plays_like_distance: Optional[float] = None,
        elevation_diff: Optional[float] = None,
        notes: str = ""
    ) -> int:
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not shot_index:
                cursor.execute("SELECT COALESCE(MAX(shot_index), 0) + 1 FROM live_shots WHERE chat_id = ? AND hole_number = ?", (c_id, hole_number))
                row_idx = cursor.fetchone()
                shot_index = row_idx[0] if row_idx else 1
            cursor.execute("""
                INSERT INTO live_shots (
                    chat_id, hole_number, shot_index, club, lie,
                    latitude, longitude, altitude, distance_covered,
                    raw_distance_to_green, plays_like_distance, elevation_diff, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c_id, hole_number, shot_index, club, lie,
                latitude, longitude, altitude, distance_covered,
                raw_distance_to_green, plays_like_distance, elevation_diff, notes
            ))
            conn.commit()
            return cursor.lastrowid

    def get_hole_shots(self, chat_id: int | str, hole_number: int) -> List[Dict[str, Any]]:
        """Recupera la sequenza cronologica dei colpi registrati per una specifica buca."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT shot_index, club, lie, latitude, longitude, altitude,
                       distance_covered, raw_distance_to_green, plays_like_distance,
                       elevation_diff, notes, created_at
                FROM live_shots
                WHERE chat_id = ? AND hole_number = ?
                ORDER BY shot_index ASC
            """, (c_id, hole_number))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def set_pin_override(self, chat_id: int | str, hole_number: int, lat: float, lon: float, alt: Optional[float] = None):
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pin_overrides FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            overrides = {}
            if row and row["pin_overrides"]:
                try:
                    overrides = json.loads(row["pin_overrides"])
                except Exception:
                    overrides = {}

            overrides[str(hole_number)] = {"lat": lat, "lon": lon, "alt": alt}
            cursor.execute("""
                UPDATE live_sessions
                SET pin_overrides = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (json.dumps(overrides), c_id))
            conn.commit()

    def get_pin_override(self, chat_id: int | str, hole_number: int) -> Optional[Tuple[float, float, Optional[float]]]:
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pin_overrides FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["pin_overrides"]:
                try:
                    overrides = json.loads(row["pin_overrides"])
                    h_data = overrides.get(str(hole_number))
                    if h_data:
                        return (h_data["lat"], h_data["lon"], h_data.get("alt"))
                except Exception:
                    pass
        return None

    def reset_session(self, chat_id: int | str, clear_handicap_profile: bool = False):
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if clear_handicap_profile:
                cursor.execute("""
                    UPDATE live_sessions
                    SET current_hole = 1, current_shot_index = 1,
                        last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                        pin_overrides = '{}', handicap_profile_json = NULL,
                        playing_hcp = NULL, awaiting_tee_choice = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (c_id,))
            else:
                cursor.execute("""
                    UPDATE live_sessions
                    SET current_hole = 1, current_shot_index = 1,
                        last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                        pin_overrides = '{}', awaiting_tee_choice = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (c_id,))
            cursor.execute("DELETE FROM live_shots WHERE chat_id = ?", (c_id,))
            conn.commit()

    # ---------------------------------------------------------
    # WHS Handicap & Tee State Management
    # ---------------------------------------------------------
    def set_handicap_profile(self, chat_id: int | str, profile: RoundHandicapProfile) -> bool:
        """Salva nel database il profilo completo WHS per la sessione attiva."""
        c_id = str(chat_id)
        self.get_or_create_session(c_id, user_id=profile.user_id)
        prof_json = profile.model_dump_json()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET selected_tee = ?, game_format = ?, format_percentage = ?,
                    playing_hcp = ?, handicap_profile_json = ?,
                    awaiting_tee_choice = 0, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (
                profile.tee_name.lower(),
                profile.format_name,
                profile.format_percentage,
                profile.playing_hcp,
                prof_json,
                c_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_handicap_profile(self, chat_id: int | str) -> Optional[RoundHandicapProfile]:
        """Recupera il profilo WHS persistente della sessione attiva se presente."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT handicap_profile_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["handicap_profile_json"]:
                try:
                    return RoundHandicapProfile.model_validate_json(row["handicap_profile_json"])
                except Exception:
                    pass
        return None

    def set_selected_tee(self, chat_id: int | str, tee_name: str) -> bool:
        """Imposta il tee scelto dall'utente e azzera il flag di attesa selezione."""
        c_id = str(chat_id)
        self.get_or_create_session(c_id, user_id="default_user")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET selected_tee = ?, has_specified_tee = 1, awaiting_tee_choice = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (str(tee_name).strip().lower(), c_id))
            conn.commit()
            return cursor.rowcount > 0

    def has_specified_tee(self, chat_id: int | str) -> bool:
        """Verifica se l'utente ha specificato esplicitamente il tee per questo round."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT has_specified_tee FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and "has_specified_tee" in row.keys() and row["has_specified_tee"]:
                return bool(row["has_specified_tee"])
        return False

    def get_selected_tee(self, chat_id: int | str) -> str:
        """Recupera il tee attualmente registrato per la chat."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT selected_tee FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["selected_tee"]:
                return str(row["selected_tee"])
        return "gialli"

    def set_game_format(self, chat_id: int | str, format_name: str, percentage: float = 0.95) -> bool:
        """Imposta il formato di gara (es. stableford 95% o match play 100%)."""
        c_id = str(chat_id)
        self.get_or_create_session(c_id, user_id="default_user")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET game_format = ?, format_percentage = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (format_name.lower(), percentage, c_id))
            conn.commit()
            return cursor.rowcount > 0

    def set_awaiting_tee_choice(self, chat_id: int | str, awaiting: bool) -> bool:
        """Imposta il flag di attesa selezione tee per il round."""
        c_id = str(chat_id)
        self.get_or_create_session(c_id, user_id="default_user")
        val = 1 if awaiting else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET awaiting_tee_choice = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (val, c_id))
            conn.commit()
            return cursor.rowcount > 0

    def is_awaiting_tee_choice(self, chat_id: int | str) -> bool:
        """Verifica se il bot è in attesa della selezione tee dall'utente."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT awaiting_tee_choice FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["awaiting_tee_choice"]:
                return bool(row["awaiting_tee_choice"])
        return False

    def record_completed_hole(
        self,
        chat_id: int | str,
        hole_number: int,
        par: int,
        stroke_index: int,
        gross_strokes: int,
        putts: int,
        received_strokes: int,
        net_par: int,
        stableford_points: int,
        net_strokes: int,
        score_label: str = "",
        advance_hole: bool = True
    ) -> Dict[str, Any]:
        """
        Registra la buca completata, aggiorna i totali progressivi e, se advance_hole è True, avanza alla buca successiva.
        """
        c_id = str(chat_id)
        self.get_or_create_session(c_id, user_id="default_user")

        hole_entry = {
            "hole_number": hole_number,
            "par": par,
            "stroke_index": stroke_index,
            "gross_strokes": gross_strokes,
            "putts": putts,
            "received_strokes": received_strokes,
            "net_par": net_par,
            "stableford_points": stableford_points,
            "net_strokes": net_strokes,
            "score_label": score_label
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT completed_scores_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            scores_list = []
            if row and row["completed_scores_json"]:
                try:
                    scores_list = json.loads(row["completed_scores_json"])
                except Exception:
                    scores_list = []

            # Se la buca era già stata registrata, aggiorna; altrimenti aggiunge in ordine
            existing_idx = next((i for i, h in enumerate(scores_list) if h.get("hole_number") == hole_number), None)
            if existing_idx is not None:
                scores_list[existing_idx] = hole_entry
            else:
                scores_list.append(hole_entry)
            scores_list.sort(key=lambda x: x.get("hole_number", 0))

            if advance_hole:
                next_h = 1 if hole_number >= 18 else hole_number + 1
                cursor.execute("""
                    UPDATE live_sessions
                    SET completed_scores_json = ?, current_hole = ?, current_shot_index = 1,
                        last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (json.dumps(scores_list), next_h, c_id))
            else:
                cursor.execute("""
                    UPDATE live_sessions
                    SET completed_scores_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (json.dumps(scores_list), c_id))
            conn.commit()

        return self.get_round_scorecard(c_id)

    def get_round_scorecard(self, chat_id: int | str) -> Dict[str, Any]:
        """
        Recupera il riepilogo progressivo di tutte le buche completate nel round:
        - Totale Stableford parziale
        - Colpi Lordi totali e totale sul Par
        - Putt totali e media putt/buca
        - Lista delle buche giocate
        """
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT completed_scores_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            scores = []
            if row and row["completed_scores_json"]:
                try:
                    scores = json.loads(row["completed_scores_json"])
                except Exception:
                    scores = []

        holes_played = len(scores)
        total_stableford = sum(h.get("stableford_points", 0) for h in scores)
        total_gross = sum(h.get("gross_strokes", 0) for h in scores)
        total_net = sum(h.get("net_strokes", 0) for h in scores)
        total_putts = sum(h.get("putts", 0) for h in scores)
        total_par = sum(h.get("par", 0) for h in scores)
        gross_to_par = total_gross - total_par
        putts_avg = round(total_putts / holes_played, 2) if holes_played > 0 else 0.0

        return {
            "completed_holes": scores,
            "holes_played": holes_played,
            "total_stableford": total_stableford,
            "total_gross": total_gross,
            "total_net": total_net,
            "total_putts": total_putts,
            "total_par": total_par,
            "gross_to_par": gross_to_par,
            "putts_avg": putts_avg
        }

    def reset_round_scores(self, chat_id: int | str) -> bool:
        """Azzera la scorecard del round corrente."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET completed_scores_json = '[]', current_hole = 1, current_shot_index = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (c_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ---------------------------------------------------------
    # Round Sequence & Pre-Flight Management
    # ---------------------------------------------------------
    def _ensure_session_exists(self, chat_id: int | str):
        """Garantisce che esista un record per la chat in live_sessions prima di eseguire aggiornamenti."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM live_sessions WHERE chat_id = ?", (c_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT OR IGNORE INTO live_sessions (
                        chat_id, user_id, course_id, current_hole, current_shot_index,
                        selected_tee, game_format, format_percentage
                    ) VALUES (?, 'user_default', 'conero_golf_club', 1, 1, 'gialli', 'stableford', 0.95)
                """, (c_id,))
                conn.commit()

    def set_round_sequence(self, chat_id: int | str, sequence: List[int]) -> bool:
        """Salva la sequenza personalizzata delle buche giocate (es. Shotgun [7..18, 1..6])."""
        self._ensure_session_exists(chat_id)
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET round_sequence_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (json.dumps(sequence), c_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_round_sequence(self, chat_id: int | str) -> List[int]:
        """Restituisce la sequenza di buche impostata, o [1..18] come fallback."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT round_sequence_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["round_sequence_json"]:
                try:
                    seq = json.loads(row["round_sequence_json"])
                    if isinstance(seq, list) and len(seq) > 0:
                        return seq
                except Exception:
                    pass
        return list(range(1, 19))

    def set_round_state(self, chat_id: int | str, state: str) -> bool:
        """Imposta lo stato del round: IDLE, AWAITING_SETUP, AWAITING_VERIFICATION."""
        self._ensure_session_exists(chat_id)
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET pending_round_state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (state, c_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_round_state(self, chat_id: int | str) -> str:
        """Restituisce lo stato corrente del round per la chat."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pending_round_state FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["pending_round_state"]:
                return str(row["pending_round_state"])
        return "IDLE"

    # ---------------------------------------------------------
    # Pending Round Audit & Anomaly Gate
    # ---------------------------------------------------------
    def set_pending_round(self, chat_id: int | str, round_data: Dict[str, Any], state: str = "AWAITING_VERIFICATION") -> bool:
        """Memorizza i dati provvisori del round per la fase di verifica e audit prima del salvataggio."""
        self._ensure_session_exists(chat_id)
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET pending_round_data_json = ?, pending_round_state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (json.dumps(round_data), state, c_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_round(self, chat_id: int | str) -> Optional[Dict[str, Any]]:
        """Recupera la struttura dati provvisoria del round sotto verifica."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pending_round_data_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["pending_round_data_json"]:
                try:
                    data = json.loads(row["pending_round_data_json"])
                    if isinstance(data, dict) and data:
                        return data
                except Exception:
                    pass
        return None

    def update_pending_hole_shot(self, chat_id: int | str, hole_number: int, shot_data: Dict[str, Any]) -> bool:
        """Aggiunge o corregge un colpo nella buca provvisoria durante l'audit."""
        pending = self.get_pending_round(chat_id)
        if not pending or "holes" not in pending:
            return False

        target_hole = None
        for h in pending["holes"]:
            if h.get("hole_number") == hole_number:
                target_hole = h
                break

        if not target_hole:
            return False

        shots = target_hole.get("shots", [])
        shot_idx = shot_data.get("shot_index")
        if shot_idx and 1 <= shot_idx <= len(shots):
            # Aggiorna colpo esistente
            shots[shot_idx - 1].update(shot_data)
        else:
            # Aggiungi nuovo colpo
            new_idx = len(shots) + 1
            shot_data["shot_index"] = new_idx
            shots.append(shot_data)

        target_hole["shots"] = shots
        target_hole["gross_strokes"] = len(shots) + target_hole.get("penalties", 0)
        target_hole["score"] = target_hole["gross_strokes"]
        return self.set_pending_round(chat_id, pending, state="AWAITING_VERIFICATION")

    def add_pending_hole_penalty(self, chat_id: int | str, hole_number: int, penalty_type: str, strokes: int = 1) -> bool:
        """Aggiunge una penalità alla buca provvisoria e ricalcola il lordo."""
        pending = self.get_pending_round(chat_id)
        if not pending or "holes" not in pending:
            return False

        target_hole = None
        for h in pending["holes"]:
            if h.get("hole_number") == hole_number:
                target_hole = h
                break

        if not target_hole:
            return False

        current_pen = target_hole.get("penalties", 0)
        target_hole["penalties"] = current_pen + strokes
        shots_count = len(target_hole.get("shots", []))
        target_hole["gross_strokes"] = shots_count + target_hole["penalties"]
        target_hole["score"] = target_hole["gross_strokes"]

        # Aggiungi alla lista penalità descrittiva
        pen_list = target_hole.get("penalties_detail", [])
        pen_list.append({"type": penalty_type, "strokes": strokes})
        target_hole["penalties_detail"] = pen_list

        return self.set_pending_round(chat_id, pending, state="AWAITING_VERIFICATION")

    def update_pending_hole_putts(self, chat_id: int | str, hole_number: int, putts: int) -> bool:
        """Aggiorna il conteggio putt della buca provvisoria."""
        pending = self.get_pending_round(chat_id)
        if not pending or "holes" not in pending:
            return False

        target_hole = None
        for h in pending["holes"]:
            if h.get("hole_number") == hole_number:
                target_hole = h
                break

        if not target_hole:
            return False

        target_hole["putts"] = putts
        return self.set_pending_round(chat_id, pending, state="AWAITING_VERIFICATION")

    def clear_pending_round(self, chat_id: int | str) -> bool:
        """Pulisce la sessione di verifica del round."""
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET pending_round_data_json = '{}', pending_round_state = 'IDLE', updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (c_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ---------------------------------------------------------
    # INTERACTIVE BUTTON-BASED (NO-AUDIO) GOLF TRACKER
    # ---------------------------------------------------------
    def get_interactive_state(self, chat_id: int | str) -> Dict[str, Any]:
        """Recupera lo stato corrente del flusso interattivo a pulsanti per la chat."""
        c_id = str(chat_id)
        default_state = {
            "state": "IDLE",
            "tee_name": "gialli",
            "start_hole": 1,
            "current_hole": 1,
            "current_shot_number": 1,
            "hole_shots": [],
            "hole_penalties": [],
            "active_shot": None,
            "waiting_location": False
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT interactive_state_json FROM live_sessions WHERE chat_id = ?", (c_id,))
            row = cursor.fetchone()
            if row and row["interactive_state_json"]:
                try:
                    data = json.loads(row["interactive_state_json"])
                    if isinstance(data, dict) and data:
                        for k, v in default_state.items():
                            if k not in data:
                                data[k] = v
                        return data
                except Exception:
                    pass
        return default_state

    def set_interactive_state(self, chat_id: int | str, state_data: Dict[str, Any]) -> bool:
        """Salva lo stato corrente del flusso interattivo."""
        self._ensure_session_exists(chat_id)
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET interactive_state_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (json.dumps(state_data), c_id))
            conn.commit()
            return cursor.rowcount > 0

    def start_interactive_round(
        self,
        chat_id: int | str,
        user_id: str = "default_user",
        course_id: str = "conero_golf_club",
        tee_name: str = "gialli",
        start_hole: int = 1
    ) -> Dict[str, Any]:
        """Inizializza una nuova partita interattiva azzerando la scorecard precedente."""
        c_id = str(chat_id)
        self._ensure_session_exists(c_id)
        clean_tee = str(tee_name).strip().lower()
        h_num = max(1, min(18, int(start_hole)))

        state = {
            "state": "PLAYING_HOLE",
            "tee_name": clean_tee,
            "start_hole": h_num,
            "current_hole": h_num,
            "current_shot_number": 1,
            "hole_shots": [],
            "hole_penalties": [],
            "active_shot": None,
            "waiting_location": False
        }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET user_id = ?, course_id = ?, selected_tee = ?, current_hole = ?, current_shot_index = 1,
                    completed_scores_json = '[]', interactive_state_json = ?,
                    last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (user_id, course_id, clean_tee, h_num, json.dumps(state), c_id))
            # Pulisci colpi live precedenti per la chat
            cursor.execute("DELETE FROM live_shots WHERE chat_id = ?", (c_id,))
            conn.commit()

        return state

    def record_interactive_shot_start(
        self,
        chat_id: int | str,
        club_type: str,
        start_lat: Optional[float] = None,
        start_lon: Optional[float] = None
    ) -> Dict[str, Any]:
        """Registra l'inizio di un colpo (selezione bastone e coordinate di partenza)."""
        state = self.get_interactive_state(chat_id)
        shot_num = state.get("current_shot_number", 1)
        state["active_shot"] = {
            "shot_number": shot_num,
            "club": club_type,
            "start_lat": start_lat,
            "start_lon": start_lon,
            "distance_meters": None,
            "lie": None,
            "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        state["waiting_location"] = False
        self.set_interactive_state(chat_id, state)
        return state

    def record_interactive_shot_end(
        self,
        chat_id: int | str,
        end_lat: float,
        end_lon: float,
        distance_meters: Optional[float] = None
    ) -> Dict[str, Any]:
        """Registra le coordinate finali della palla e calcola o salva la distanza percorsa."""
        state = self.get_interactive_state(chat_id)
        act = state.get("active_shot")
        if not act:
            act = {
                "shot_number": state.get("current_shot_number", 1),
                "club": "Ferro",
                "start_lat": None,
                "start_lon": None,
                "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }

        act["end_lat"] = end_lat
        act["end_lon"] = end_lon
        act["timestamp_end"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if distance_meters is not None:
            act["distance_meters"] = int(round(distance_meters))
        elif act.get("start_lat") and act.get("start_lon"):
            d = haversine_distance(act["start_lat"], act["start_lon"], end_lat, end_lon)
            act["distance_meters"] = int(round(d))

        state["active_shot"] = act
        state["waiting_location"] = False
        state["state"] = "WAITING_LIE"
        self.set_interactive_state(chat_id, state)

        # Aggiorna anche last_latitude e last_longitude nella sessione
        self.set_last_position(chat_id, end_lat, end_lon)
        return state

    def set_interactive_shot_lie(self, chat_id: int | str, lie: str) -> Dict[str, Any]:
        """Assegna la posizione della palla (lie) al colpo attivo e lo aggiunge alla buca."""
        state = self.get_interactive_state(chat_id)
        act = state.get("active_shot")
        if not act:
            act = {
                "shot_number": state.get("current_shot_number", 1),
                "club": "Ferro",
                "distance_meters": None,
                "timestamp_start": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }

        act["lie"] = lie
        state["hole_shots"].append(act)

        # Salva anche nella tabella live_shots per coerenza con app.py
        c_id = str(chat_id)
        h_num = state.get("current_hole", 1)
        s_num = act["shot_number"]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO live_shots (chat_id, hole_number, shot_index, club, lie, latitude, longitude, distance_covered)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (c_id, h_num, s_num, act["club"], lie, act.get("end_lat"), act.get("end_lon"), act.get("distance_meters")))
            conn.commit()

        state["active_shot"] = None
        state["waiting_location"] = False

        if lie.lower() == "green":
            state["state"] = "ON_GREEN"
        else:
            state["current_shot_number"] = len(state["hole_shots"]) + 1
            state["state"] = "PLAYING_HOLE"

        self.set_interactive_state(chat_id, state)
        return state

    def add_interactive_penalty(self, chat_id: int | str, penalty_type: str, strokes: int = 1) -> Dict[str, Any]:
        """Aggiunge una penalità alla buca corrente."""
        state = self.get_interactive_state(chat_id)
        pen_entry = {
            "type": penalty_type,
            "strokes": strokes,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        state["hole_penalties"].append(pen_entry)
        self.set_interactive_state(chat_id, state)
        return state

    def undo_interactive_last_shot(self, chat_id: int | str) -> Optional[Dict[str, Any]]:
        """Annulla l'ultimo colpo registrato nella buca corrente."""
        state = self.get_interactive_state(chat_id)
        # Se c'era un colpo attivo non ancora completato, annulla quello
        if state.get("active_shot"):
            state["active_shot"] = None
            state["waiting_location"] = False
            state["state"] = "PLAYING_HOLE"
            self.set_interactive_state(chat_id, state)
            return state

        # Altrimenti rimuovi l'ultimo colpo confermato dalla lista
        if state.get("hole_shots"):
            removed = state["hole_shots"].pop()
            c_id = str(chat_id)
            h_num = state.get("current_hole", 1)
            s_idx = removed.get("shot_number", len(state["hole_shots"]) + 1)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM live_shots WHERE chat_id = ? AND hole_number = ? AND shot_index = ?", (c_id, h_num, s_idx))
                conn.commit()

            state["current_shot_number"] = len(state["hole_shots"]) + 1
            state["state"] = "PLAYING_HOLE"
            self.set_interactive_state(chat_id, state)
            return state

        # Se non ci sono colpi ma ci sono penalità, rimuovi l'ultima penalità
        if state.get("hole_penalties"):
            state["hole_penalties"].pop()
            self.set_interactive_state(chat_id, state)
            return state

        return None

    def close_interactive_hole(
        self,
        chat_id: int | str,
        putts: int,
        par: int = 4,
        stroke_index: int = 1,
        received_strokes: int = 0
    ) -> Dict[str, Any]:
        """Chiude la buca corrente calcolando colpi lordi, netti e Stableford."""
        state = self.get_interactive_state(chat_id)
        h_num = state.get("current_hole", 1)
        shots_count = len(state.get("hole_shots", []))
        penalties_count = sum(p.get("strokes", 1) for p in state.get("hole_penalties", []))

        gross_score = shots_count + putts + penalties_count
        if gross_score == 0:
            gross_score = max(par, putts + 1)

        net_score = gross_score - received_strokes
        net_par = par + received_strokes
        stbl_net = max(0, 2 + par - net_score)
        stbl_gross = max(0, 2 + par - gross_score)

        # Determina label punteggio
        diff = gross_score - par
        if diff <= -2:
            score_label = "Eagle or Better"
        elif diff == -1:
            score_label = "Birdie"
        elif diff == 0:
            score_label = "Par"
        elif diff == 1:
            score_label = "Bogey"
        else:
            score_label = "Double+ Bogey"

        # Salva tramite record_completed_hole (advance_hole=False finché l'utente non clicca 'Prossima Buca')
        card = self.record_completed_hole(
            chat_id=chat_id,
            hole_number=h_num,
            par=par,
            stroke_index=stroke_index,
            gross_strokes=gross_score,
            putts=putts,
            received_strokes=received_strokes,
            net_par=net_par,
            stableford_points=stbl_net,
            net_strokes=net_score,
            score_label=score_label,
            advance_hole=False
        )

        state["state"] = "HOLE_COMPLETED"
        state["last_completed_hole"] = h_num
        self.set_interactive_state(chat_id, state)

        return {
            "hole_number": h_num,
            "par": par,
            "stroke_index": stroke_index,
            "gross_score": gross_score,
            "net_score": net_score,
            "putts": putts,
            "penalties": penalties_count,
            "received_strokes": received_strokes,
            "net_par": net_par,
            "stableford_points": stbl_net,
            "stableford_gross": stbl_gross,
            "score_label": score_label,
            "scorecard": card
        }

    def advance_to_next_interactive_hole(self, chat_id: int | str) -> int:
        """Avanza alla buca successiva, azzerando i colpi e le penalità temporanee."""
        state = self.get_interactive_state(chat_id)
        cur_h = state.get("current_hole", 1)
        next_h = 1 if cur_h >= 18 else cur_h + 1

        state["current_hole"] = next_h
        state["current_shot_number"] = 1
        state["hole_shots"] = []
        state["hole_penalties"] = []
        state["active_shot"] = None
        state["waiting_location"] = False
        state["state"] = "PLAYING_HOLE"

        self.set_interactive_state(chat_id, state)
        self.set_current_hole(chat_id, next_h)
        return next_h



