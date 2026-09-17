from __future__ import annotations

import sqlite3
import json
import contextlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from core.elevation_service import haversine_distance

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
                INSERT INTO live_sessions (chat_id, user_id, course_id, current_hole, current_shot_index)
                VALUES (?, ?, ?, 1, 1)
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
                "pin_overrides": "{}"
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

            # Salva la nuova posizione
            cursor.execute("""
                UPDATE live_sessions
                SET last_latitude = ?, last_longitude = ?, last_altitude = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (latitude, longitude, altitude, c_id))
            conn.commit()

            return distance_covered, current_hole, current_shot

    def record_live_shot(
        self,
        chat_id: int | str,
        hole_number: int,
        shot_index: int,
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

    def reset_session(self, chat_id: int | str):
        c_id = str(chat_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE live_sessions
                SET current_hole = 1, current_shot_index = 1,
                    last_latitude = NULL, last_longitude = NULL, last_altitude = NULL,
                    pin_overrides = '{}', updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            """, (c_id,))
            cursor.execute("DELETE FROM live_shots WHERE chat_id = ?", (c_id,))
            conn.commit()
