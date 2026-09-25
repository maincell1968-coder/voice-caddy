from __future__ import annotations

import re
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
try:
    from monitoring.base_agent import ZeroCostBaseAgent
except ImportError:
    from voice_caddy.monitoring.base_agent import ZeroCostBaseAgent


class TelegramSessionAgent(ZeroCostBaseAgent):
    """
    Agente specializzato nel tracciamento a costo zero delle sessioni utente su Telegram.
    Monitora:
    1. Avvio di partite/allenamenti sul bot Telegram (es. comandi vocali, bot states, MadelineProto log).
    2. Progresso buca per buca dei giocatori attivi.
    3. Completamento del percorso di gara su Telegram (GIRO_CHIUSO, FINE_DEFINITIVA).
    4. Sessioni in stallo o abbandonate prima del passaggio al browser.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        telegram_log_path: Optional[Path] = None,
        inactivity_timeout_minutes: int = 45,
        **kwargs
    ):
        project_root = Path(__file__).resolve().parent.parent
        self.db_path = db_path or (project_root / "voice_caddy.db")
        self.telegram_log_path = telegram_log_path
        self.inactivity_timeout_seconds = inactivity_timeout_minutes * 60
        super().__init__(name="TelegramSessionAgent", **kwargs)

    def _register_default_tools(self) -> None:
        self.register_tool(
            "scan_telegram_log_events",
            self.tool_scan_telegram_log_events,
            "Analizza i log di Telegram/MadelineProto per estrarre eventi di avvio e chiusura giro"
        )
        self.register_tool(
            "inspect_live_sessions_db",
            self.tool_inspect_live_sessions_db,
            "Interroga in sola lettura la tabella live_sessions di SQLite per estrarre lo stato corrente"
        )
        self.register_tool(
            "detect_stalled_sessions",
            self.tool_detect_stalled_sessions,
            "Individua sessioni che non registrano colpi da oltre X minuti"
        )
        self.register_tool(
            "get_session_summary",
            self.tool_get_session_summary,
            "Compila il report aggregato delle sessioni Telegram (avviate, completate, attive)"
        )

    def tool_scan_telegram_log_events(self, log_path: Optional[Path] = None, max_lines: int = 500) -> Dict[str, Any]:
        """
        Legge i log di Telegram (compatibile con MadelineProto e bot nativo standard)
        per contare eventi real-time di avvio e completamento.
        """
        target = log_path or self.telegram_log_path
        if not target or not Path(target).exists():
            return {
                "events_found": 0,
                "sessions_started": 0,
                "sessions_completed": 0,
                "status": "log_file_not_found"
            }

        validated = self.guardrail.validate_read_path(target)
        started_pattern = re.compile(r"start_interactive_round|COLPO_DA_TEE|CIRCOLO_IDENTIFICATO|/start|/nuovogiro", re.IGNORECASE)
        completed_pattern = re.compile(r"GIRO_CHIUSO|FINE_DEFINITIVA|close_interactive_hole|/concludigiro", re.IGNORECASE)

        started_count = 0
        completed_count = 0

        try:
            with open(validated, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-max_lines:]
                for line in lines:
                    if started_pattern.search(line):
                        started_count += 1
                    elif completed_pattern.search(line):
                        completed_count += 1
        except Exception as e:
            return {"error": str(e), "sessions_started": 0, "sessions_completed": 0}

        return {
            "events_found": started_count + completed_count,
            "sessions_started": started_count,
            "sessions_completed": completed_count
        }

    def tool_inspect_live_sessions_db(self, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Ispeziona in sola lettura la tabella live_sessions del database,
        senza rischiare alcun lock o alterazione dati (SafeVault conforme).
        """
        target_db = db_path or self.db_path
        if not target_db or (not target_db.exists() and str(target_db) != ":memory:"):
            return []

        conn = self.guardrail.open_readonly_sqlite(target_db)
        try:
            cursor = conn.cursor()
            query = """
                SELECT chat_id, user_id, course_id, current_hole, current_shot_index,
                       selected_tee, game_format, updated_at, interactive_state_json, completed_scores_json
                FROM live_sessions
            """
            self.guardrail.assert_readonly_sql(query)
            cursor.execute(query)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                # Calcola numero buche completate
                scores = []
                if item.get("completed_scores_json"):
                    try:
                        scores = json.loads(item["completed_scores_json"])
                    except Exception:
                        scores = []
                item["completed_holes_count"] = len(scores)

                # Estrai FSM state
                fsm_state = "IDLE"
                if item.get("interactive_state_json"):
                    try:
                        istate = json.loads(item["interactive_state_json"])
                        fsm_state = istate.get("fsm_state") or istate.get("state") or "IDLE"
                    except Exception:
                        pass
                item["fsm_state"] = fsm_state
                results.append(item)
            return results
        finally:
            conn.close()

    def tool_detect_stalled_sessions(self, sessions: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Identifica sessioni attive che non ricevono aggiornamenti da troppo tempo."""
        session_list = sessions if sessions is not None else self.tool_inspect_live_sessions_db()
        stalled = []
        now = time.time()

        for s in session_list:
            up_str = s.get("updated_at")
            if not up_str:
                continue
            try:
                # Gestisci formato sqlite TIMESTAMP standard
                updated_ts = time.mktime(time.strptime(up_str[:19], "%Y-%m-%d %H:%M:%S"))
                idle_sec = now - updated_ts
                if idle_sec > self.inactivity_timeout_seconds and s.get("fsm_state") not in ("IDLE", "FINE_DEFINITIVA", "GIRO_CHIUSO"):
                    stalled.append({
                        "chat_id": s.get("chat_id"),
                        "user_id": s.get("user_id"),
                        "current_hole": s.get("current_hole"),
                        "idle_minutes": round(idle_sec / 60.0, 1),
                        "state": s.get("fsm_state")
                    })
            except Exception:
                continue

        return stalled

    def tool_get_session_summary(self) -> Dict[str, Any]:
        """Restituisce il quadro completo delle sessioni Telegram attive e completate."""
        sessions = self.tool_inspect_live_sessions_db()
        closed_states = ("IDLE", "FINE_DEFINITIVA", "GIRO_CHIUSO")
        active = [s for s in sessions if s.get("fsm_state") not in closed_states]
        completed = [s for s in sessions if s.get("fsm_state") in ("GIRO_CHIUSO", "FINE_DEFINITIVA") or s.get("completed_holes_count", 0) >= 9]
        stalled = self.tool_detect_stalled_sessions(sessions)

        return {
            "total_registered_chats": len(sessions),
            "active_sessions": len(active),
            "completed_sessions": len(completed),
            "stalled_sessions": len(stalled),
            "active_players": [
                {
                    "chat_id": s.get("chat_id"),
                    "user_id": s.get("user_id"),
                    "hole": s.get("current_hole"),
                    "holes_completed": s.get("completed_holes_count"),
                    "state": s.get("fsm_state")
                }
                for s in active
            ]
        }

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Esegue il ciclo di telemetria per Telegram."""
        cycle_start = time.time()

        # 1. Ispezione sessioni da DB
        sessions = self.execute_tool("inspect_live_sessions_db", db_path=self.db_path)

        # 2. Controllo log testuali/MadelineProto se configurati
        log_events = self.execute_tool("scan_telegram_log_events", log_path=self.telegram_log_path)

        # 3. Rilevamento sessioni in stallo
        stalled = self.execute_tool("detect_stalled_sessions", sessions=sessions)

        # 4. Sintesi aggregata
        summary = self.execute_tool("get_session_summary")

        # Calcolo contatori cumulativi basandosi su log ed estrazione DB
        # I valori storici cumulativi vengono mantenuti nello stato con casting difensivo
        raw_prev_started = self.state.get("sessions_started_total")
        try:
            prev_started = int(raw_prev_started) if raw_prev_started is not None else 0
        except (ValueError, TypeError):
            prev_started = 0

        raw_prev_completed = self.state.get("sessions_completed_total")
        try:
            prev_completed = int(raw_prev_completed) if raw_prev_completed is not None else 0
        except (ValueError, TypeError):
            prev_completed = 0

        chats_count = summary.get("total_registered_chats", 0) if isinstance(summary, dict) else 0
        log_started = log_events.get("sessions_started", 0) if isinstance(log_events, dict) else 0
        comp_count = summary.get("completed_sessions", 0) if isinstance(summary, dict) else 0
        log_completed = log_events.get("sessions_completed", 0) if isinstance(log_events, dict) else 0

        new_started = max(prev_started, chats_count + log_started)
        new_completed = max(prev_completed, comp_count + log_completed)

        # Emissione metriche per Prometheus
        self.emit_metric("voice_caddy_telegram_sessions_started_total", float(new_started))
        self.emit_metric("voice_caddy_telegram_sessions_completed_total", float(new_completed))
        self.emit_metric("voice_caddy_telegram_sessions_active", float(summary.get("active_sessions", 0) if isinstance(summary, dict) else 0))
        self.emit_metric("voice_caddy_telegram_sessions_stalled", float(len(stalled)))

        # Aggiornamento stato
        self.state["last_run"] = cycle_start
        self.state["sessions_started_total"] = new_started
        self.state["sessions_completed_total"] = new_completed
        self.state["active_sessions"] = summary.get("active_sessions", 0) if isinstance(summary, dict) else 0
        self.state["stalled_sessions_count"] = len(stalled)
        self.state["cycle_count"] = int(self.state.get("cycle_count") or 0) + 1

        self.persist_state()

        return {
            "sessions_started": new_started,
            "sessions_completed": new_completed,
            "active_now": summary["active_sessions"],
            "stalled_count": len(stalled),
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000.0, 2)
        }
