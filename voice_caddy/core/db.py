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
            
            # Check for existing table missing user_id / group_name columns
            cursor.execute("PRAGMA table_info(rounds)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE rounds ADD COLUMN user_id TEXT DEFAULT 'default_user'")
            if "group_name" not in columns:
                cursor.execute("ALTER TABLE rounds ADD COLUMN group_name TEXT DEFAULT 'strafatti'")

            conn.commit()

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
