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


class BrowserCompletionAgent(ZeroCostBaseAgent):
    """
    Agente specializzato nel tracciare il completamento del percorso utente nel Browser
    e nel calcolare il funnel di conversione (Telegram -> Browser Completion) a costo token zero.

    Monitora:
    1. Eventi di completamento nel browser (salvataggio definitivo del giro su DB,
       consultazione scorecard web, download PDF di gara).
    2. Correlazione tra la sessione avviata su Telegram e la chiusura nel browser.
    3. Tasso di completamento globale e tasso di abbandono per ciascuna fase.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        web_log_path: Optional[Path] = None,
        **kwargs
    ):
        project_root = Path(__file__).resolve().parent.parent
        self.db_path = db_path or (project_root / "voice_caddy.db")
        self.web_log_path = web_log_path
        super().__init__(name="BrowserCompletionAgent", **kwargs)

    def _register_default_tools(self) -> None:
        self.register_tool(
            "scan_browser_completed_rounds",
            self.tool_scan_browser_completed_rounds,
            "Ispeziona i giri storici salvati e consolidati nel database SQLite (tabella rounds)"
        )
        self.register_tool(
            "scan_web_access_logs",
            self.tool_scan_web_access_logs,
            "Analizza i log di accesso web per individuare visite alla dashboard, export PDF e visualizzatore"
        )
        self.register_tool(
            "calculate_funnel_conversion",
            self.tool_calculate_funnel_conversion,
            "Calcola la percentuale di completamento da avvio Telegram a chiusura definitiva su Browser"
        )
        self.register_tool(
            "generate_funnel_breakdown",
            self.tool_generate_funnel_breakdown,
            "Genera il report dettagliato delle tappe del funnel e dei punti di abbandono"
        )

    def tool_scan_browser_completed_rounds(self, db_path: Optional[Path] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Legge in sola lettura la tabella rounds di SQLite per quantificare
        i giri effettivamente consolidati e chiusi nel sistema.
        """
        target_db = db_path or self.db_path
        if not target_db or (not target_db.exists() and str(target_db) != ":memory:"):
            return []

        conn = self.guardrail.open_readonly_sqlite(target_db)
        try:
            cursor = conn.cursor()
            query = """
                SELECT id, user_id, group_name, course_name, date_played, holes_played,
                       total_score, created_at
                FROM rounds
                ORDER BY id DESC
                LIMIT ?
            """
            self.guardrail.assert_readonly_sql(query)
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def tool_scan_web_access_logs(self, log_path: Optional[Path] = None, max_lines: int = 500) -> Dict[str, Any]:
        """Scansiona i log del web server per tracciare accessi alle pagine chiave."""
        target = log_path or self.web_log_path
        if not target or not Path(target).exists():
            return {
                "dashboard_views": 0,
                "pdf_downloads": 0,
                "strategy_3d_views": 0,
                "status": "web_log_not_configured"
            }

        validated = self.guardrail.validate_read_path(target)
        pdf_pattern = re.compile(r"download_pdf|mobile_pdf|report.*\.pdf", re.IGNORECASE)
        dash_pattern = re.compile(r"GET /|streamlit|visualizzatore", re.IGNORECASE)
        strat_pattern = re.compile(r"strategia|green_radar|tactical", re.IGNORECASE)

        counts = {"dashboard_views": 0, "pdf_downloads": 0, "strategy_3d_views": 0}
        try:
            with open(validated, "r", encoding="utf-8", errors="ignore") as f:
                for line in f.readlines()[-max_lines:]:
                    if pdf_pattern.search(line):
                        counts["pdf_downloads"] += 1
                    if dash_pattern.search(line):
                        counts["dashboard_views"] += 1
                    if strat_pattern.search(line):
                        counts["strategy_3d_views"] += 1
        except Exception as e:
            counts["read_error"] = str(e)

        return counts

    def tool_calculate_funnel_conversion(
        self,
        telegram_started: int,
        telegram_completed: int,
        browser_completed: int
    ) -> Dict[str, Any]:
        """
        Calcola i ratei di conversione matematica tra ogni step del funnel:
        Fase 1: Inizio su Telegram
        Fase 2: Conclusione 18 buche su Telegram
        Fase 3: Validazione/Revisione/Salvataggio su Browser
        """
        t_started = max(0, int(telegram_started))
        t_completed = max(0, int(telegram_completed))
        b_completed = max(0, int(browser_completed))

        # Tasso di completamento globale (%)
        overall_completion_rate = (b_completed / t_started * 100.0) if t_started > 0 else 0.0
        # Tasso Telegram completamento (%)
        telegram_finish_rate = (t_completed / t_started * 100.0) if t_started > 0 else 0.0
        # Tasso di passaggio da Telegram a Browser (%)
        telegram_to_browser_bridge_rate = (b_completed / t_completed * 100.0) if t_completed > 0 else 0.0

        # Normalizzazione in caso di sessioni storiche già su DB
        if overall_completion_rate > 100.0:
            overall_completion_rate = 100.0
        if telegram_finish_rate > 100.0:
            telegram_finish_rate = 100.0

        return {
            "telegram_started": t_started,
            "telegram_completed": t_completed,
            "browser_completed": b_completed,
            "overall_completion_rate_pct": round(overall_completion_rate, 1),
            "telegram_finish_rate_pct": round(telegram_finish_rate, 1),
            "telegram_to_browser_bridge_rate_pct": round(telegram_to_browser_bridge_rate, 1),
            "dropoff_telegram_in_round": max(0, t_started - t_completed),
            "dropoff_before_browser_save": max(0, t_completed - b_completed)
        }

    def tool_generate_funnel_breakdown(self, funnel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Genera un riepilogo leggibile con diagnosi dei colli di bottiglia."""
        rate = funnel_data.get("overall_completion_rate_pct", 0.0)
        diagnosis = "Ottimale"
        if rate < 30.0:
            diagnosis = "Critico: Forte dispersione tra l'avvio della partita e la chiusura nel browser."
        elif rate < 60.0:
            diagnosis = "Buono: Alcuni giocatori completano su Telegram ma non consultano il report finale su web."
        else:
            diagnosis = "Eccellente: Alto tasso di conversione end-to-end (Telegram -> Web)."

        return {
            "funnel_summary": funnel_data,
            "funnel_health_diagnosis": diagnosis,
            "steps": [
                {"step": 1, "name": "Avvio Partita Telegram", "count": funnel_data.get("telegram_started", 0)},
                {"step": 2, "name": "Conclusione Giro Telegram", "count": funnel_data.get("telegram_completed", 0)},
                {"step": 3, "name": "Salvataggio/Analisi Browser", "count": funnel_data.get("browser_completed", 0)},
            ]
        }

    def run_monitoring_cycle(self, telegram_started: int = 0, telegram_completed: int = 0) -> Dict[str, Any]:
        """Esegue il ciclo di tracciamento browser e calcolo del funnel."""
        cycle_start = time.time()

        # 1. Recupero giri completati memorizzati a DB
        completed_rounds = self.execute_tool("scan_browser_completed_rounds", db_path=self.db_path)
        browser_count = len(completed_rounds)

        # 2. Controllo log accessi web
        web_logs = self.execute_tool("scan_web_access_logs", log_path=self.web_log_path)

        # Se non passati esplicitamente, tenta di usare i valori dallo stato o dalle stime con casting sicuro
        raw_tg_started = self.state.get("last_telegram_started")
        try:
            st_tg_started = int(raw_tg_started) if raw_tg_started is not None else 0
        except (ValueError, TypeError):
            st_tg_started = 0

        raw_tg_completed = self.state.get("last_telegram_completed")
        try:
            st_tg_completed = int(raw_tg_completed) if raw_tg_completed is not None else 0
        except (ValueError, TypeError):
            st_tg_completed = 0

        cur_tg_started = int(telegram_started) if telegram_started is not None else 0
        cur_tg_completed = int(telegram_completed) if telegram_completed is not None else 0

        t_started = max(cur_tg_started, browser_count, st_tg_started)
        t_completed = max(cur_tg_completed, browser_count, st_tg_completed)

        # 3. Calcolo del Funnel
        funnel_res = self.execute_tool(
            "calculate_funnel_conversion",
            telegram_started=t_started,
            telegram_completed=t_completed,
            browser_completed=browser_count
        )

        # 4. Report breakdown
        breakdown = self.execute_tool("generate_funnel_breakdown", funnel_data=funnel_res)

        # Emissione metriche per Prometheus
        self.emit_metric("voice_caddy_browser_completions_total", float(browser_count))
        self.emit_metric("voice_caddy_funnel_completion_rate_percent", float(funnel_res.get("overall_completion_rate_pct", 0.0)))
        self.emit_metric("voice_caddy_web_dashboard_views_total", float(web_logs.get("dashboard_views", 0)))
        self.emit_metric("voice_caddy_pdf_downloads_total", float(web_logs.get("pdf_downloads", 0)))

        # Aggiornamento stato locale
        self.state["last_run"] = cycle_start
        self.state["browser_completed_count"] = browser_count
        self.state["last_telegram_started"] = t_started
        self.state["last_telegram_completed"] = t_completed
        self.state["funnel"] = funnel_res
        self.state["cycle_count"] = int(self.state.get("cycle_count") or 0) + 1

        self.persist_state()

        return {
            "browser_completed": browser_count,
            "completion_rate_pct": funnel_res["overall_completion_rate_pct"],
            "funnel_diagnosis": breakdown["funnel_health_diagnosis"],
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000.0, 2)
        }
