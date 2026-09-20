from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from core.schemas import GolfRoundData


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "voice_caddy.db"


class DatabaseManager:
    """
    SQLite Database Manager for persisting historical golf rounds,
    enabling trend tracking, handicap progression, and statistics over time.
    Supports multi-user isolation with user_id and group_name tracking.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        # Se il database esiste già, esegui controllo di integrità e backup preventivo
        if self.db_path.exists() and str(self.db_path) != ":memory:":
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    res = cursor.fetchone()
                    if res and res[0] != "ok":
                        import logging
                        logging.getLogger(__name__).warning(f"Attenzione: PRAGMA integrity_check su DB ha ritornato: {res}")
                
                # Backup automatico preventivo
                self.backup_database()
            except Exception:
                pass

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    group_name TEXT DEFAULT 'strafatti',
                    course_name TEXT,
                    date_played TEXT,
                    holes_played INTEGER,
                    total_score INTEGER,
                    total_putts INTEGER,
                    fairway_accuracy_pct REAL,
                    gir_pct REAL,
                    scrambling_pct REAL,
                    penalty_strokes INTEGER,
                    primary_miss TEXT,
                    json_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telegram_media_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default_user',
                    group_name TEXT DEFAULT 'strafatti',
                    round_date TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content_text TEXT,
                    file_id TEXT,
                    file_path TEXT,
                    hole_number INTEGER,
                    shot_index INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tg_archive_date ON telegram_media_archive (round_date, user_id, chat_id)")
            
            # Check for existing table missing user_id / group_name columns
            cursor.execute("PRAGMA table_info(rounds)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE rounds ADD COLUMN user_id TEXT DEFAULT 'default_user'")
            if "group_name" not in columns:
                cursor.execute("ALTER TABLE rounds ADD COLUMN group_name TEXT DEFAULT 'strafatti'")

            conn.commit()

    def backup_database(self, dest_path: Optional[Path] = None) -> Path:
        """Esegue un backup atomico online del database tramite le API native di SQLite."""
        if str(self.db_path) == ":memory:":
            return Path(":memory:")
        target = Path(dest_path) if dest_path else self.db_path.with_suffix(".db.bak")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as src:
            dest_conn = sqlite3.connect(target)
            try:
                src.backup(dest_conn)
            finally:
                dest_conn.close()
        return target

    def save_round(self, round_data: GolfRoundData, user_id: str = "default_user", group_name: str = "strafatti") -> int:
        summary = round_data.performance_summary
        info = round_data.round_info
        json_str = round_data.model_dump_json()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO rounds (
                    user_id, group_name,
                    course_name, date_played, holes_played, total_score, total_putts,
                    fairway_accuracy_pct, gir_pct, scrambling_pct, penalty_strokes,
                    primary_miss, json_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                group_name,
                info.course_name or "Giro Senza Nome",
                info.date or "Non specificata",
                info.holes_played,
                summary.total_score,
                summary.total_putts,
                summary.fairway_accuracy_pct,
                summary.gir_pct,
                summary.scrambling_pct,
                summary.penalty_strokes_total,
                summary.primary_miss_tendency,
                json_str
            ))
            conn.commit()
            return cursor.lastrowid

    def get_all_rounds(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT id, user_id, group_name, course_name, date_played, holes_played, total_score,
                           total_putts, fairway_accuracy_pct, gir_pct, scrambling_pct,
                           penalty_strokes, primary_miss, created_at
                    FROM rounds
                    WHERE user_id = ?
                    ORDER BY id DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT id, user_id, group_name, course_name, date_played, holes_played, total_score,
                           total_putts, fairway_accuracy_pct, gir_pct, scrambling_pct,
                           penalty_strokes, primary_miss, created_at
                    FROM rounds
                    ORDER BY id DESC
                """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_round_by_id(self, round_id: int) -> Optional[GolfRoundData]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT json_data FROM rounds WHERE id = ?", (round_id,))
            row = cursor.fetchone()
            if row:
                return GolfRoundData.model_validate_json(row["json_data"])
            return None

    def get_latest_round(self, user_id: Optional[str] = None) -> Optional[GolfRoundData]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT json_data FROM rounds WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
            else:
                cursor.execute("SELECT json_data FROM rounds ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return GolfRoundData.model_validate_json(row["json_data"])
            return None

    def delete_round(self, round_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_historical_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    COUNT(*) as total_rounds,
                    AVG(total_score) as avg_score,
                    AVG(total_putts) as avg_putts,
                    AVG(fairway_accuracy_pct) as avg_fairway_pct,
                    AVG(gir_pct) as avg_gir_pct,
                    AVG(scrambling_pct) as avg_scrambling_pct
                FROM rounds
            """
            params = ()
            if user_id:
                query += " WHERE user_id = ?"
                params = (user_id,)

            cursor.execute(query, params)
            row = cursor.fetchone()
            if not row or row["total_rounds"] == 0:
                return {
                    "total_rounds": 0, "avg_score": 0.0, "avg_putts": 0.0,
                    "avg_fairway_pct": 0.0, "avg_gir_pct": 0.0, "avg_scrambling_pct": 0.0
                }
            return {
                "total_rounds": row["total_rounds"],
                "avg_score": round(row["avg_score"], 1) if row["avg_score"] else 0.0,
                "avg_putts": round(row["avg_putts"], 1) if row["avg_putts"] else 0.0,
                "avg_fairway_pct": round(row["avg_fairway_pct"], 1) if row["avg_fairway_pct"] else 0.0,
                "avg_gir_pct": round(row["avg_gir_pct"], 1) if row["avg_gir_pct"] else 0.0,
                "avg_scrambling_pct": round(row["avg_scrambling_pct"], 1) if row["avg_scrambling_pct"] else 0.0
            }

    def save_user_profile(self, user_id: str, profile_json: str) -> bool:
        """Salva o aggiorna il profilo utente e la sacca nel database protetto."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_profiles (user_id, profile_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, profile_json))
            conn.commit()
            return True

    def get_user_profile(self, user_id: str) -> Optional[str]:
        """Recupera il JSON del profilo utente dal database protetto."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return row["profile_json"]
            return None

    # ---------------------------------------------------------
    # Telegram Real-Time Cloud Media & Message Archive
    # ---------------------------------------------------------
    def archive_telegram_message(
        self,
        chat_id: int | str,
        user_id: str = "default_user",
        round_date: Optional[str] = None,
        message_type: str = "text",
        content_text: Optional[str] = None,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        hole_number: Optional[int] = None,
        shot_index: Optional[int] = None,
        group_name: str = "strafatti",
        timestamp: Optional[str] = None
    ) -> int:
        """Archivia un messaggio, nota vocale o colpo ricevuto da Telegram per il recupero per data."""
        from datetime import datetime
        now = datetime.now()
        r_date = round_date or now.strftime("%Y-%m-%d")
        ts = timestamp or now.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO telegram_media_archive (
                    chat_id, user_id, group_name, round_date, timestamp,
                    message_type, content_text, file_id, file_path,
                    hole_number, shot_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(chat_id), user_id, group_name, r_date, ts,
                message_type, content_text, file_id, file_path,
                hole_number, shot_index
            ))
            conn.commit()
            return cursor.lastrowid

    def get_telegram_archived_dates(
        self,
        chat_id: Optional[int | str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Restituisce l'elenco delle date con messaggi Telegram archiviati e relativi conteggi."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT round_date,
                       COUNT(*) as total_count,
                       SUM(CASE WHEN message_type IN ('voice', 'audio', 'video_note', 'video') THEN 1 ELSE 0 END) as voice_count,
                       SUM(CASE WHEN message_type = 'text' THEN 1 ELSE 0 END) as text_count
                FROM telegram_media_archive
            """
            params = []
            conditions = []
            if chat_id:
                conditions.append("chat_id = ?")
                params.append(str(chat_id))
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            if conditions:
                query += " WHERE " + " OR ".join(conditions)
            query += " GROUP BY round_date ORDER BY round_date DESC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_telegram_messages_for_date(
        self,
        round_date: str,
        chat_id: Optional[int | str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Recupera tutti i messaggi/audio Telegram archiviati per una specifica data."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM telegram_media_archive WHERE round_date = ?"
            params = [round_date]
            if chat_id and user_id:
                query += " AND (chat_id = ? OR user_id = ?)"
                params.extend([str(chat_id), user_id])
            elif chat_id:
                query += " AND chat_id = ?"
                params.append(str(chat_id))
            elif user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY id ASC"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

