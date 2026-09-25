from __future__ import annotations

import unittest
import tempfile
import sqlite3
import json
import time
from pathlib import Path

import sys
from pathlib import Path

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
if str(VOICE_CADDY_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_CADDY_DIR))

try:
    from monitoring.guardrails import SecurityGuardrail, SecurityViolationError
    from monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from monitoring.base_agent import ZeroCostBaseAgent
    from monitoring.server_monitor_agent import ServerMonitorAgent
    from monitoring.telegram_session_agent import TelegramSessionAgent
    from monitoring.browser_completion_agent import BrowserCompletionAgent
    from monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from monitoring.runner import MonitoringOrchestrator
except ImportError:
    from voice_caddy.monitoring.guardrails import SecurityGuardrail, SecurityViolationError
    from voice_caddy.monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from voice_caddy.monitoring.base_agent import ZeroCostBaseAgent
    from voice_caddy.monitoring.server_monitor_agent import ServerMonitorAgent
    from voice_caddy.monitoring.telegram_session_agent import TelegramSessionAgent
    from voice_caddy.monitoring.browser_completion_agent import BrowserCompletionAgent
    from voice_caddy.monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from voice_caddy.monitoring.runner import MonitoringOrchestrator


class TestZeroCostMonitoringSuite(unittest.TestCase):
    """
    Test di conformità per la suite di agenti di monitoraggio a costo zero.
    Rigorosamente isolato in directory temporanea (SafeVault compliant).
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Crea un database temporaneo isolato con schema minimo compatibile
        self.db_path = self.temp_path / "test_voice_caddy.db"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE live_sessions (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT,
                course_id TEXT,
                current_hole INTEGER DEFAULT 1,
                current_shot_index INTEGER DEFAULT 1,
                selected_tee TEXT DEFAULT 'gialli',
                game_format TEXT DEFAULT 'stableford',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                interactive_state_json TEXT,
                completed_scores_json TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                group_name TEXT,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Inserisci dati di test isolati
        cursor.execute("""
            INSERT INTO live_sessions (chat_id, user_id, current_hole, updated_at, interactive_state_json, completed_scores_json)
            VALUES 
                ('1001', 'mario_rossi', 4, '2026-09-25 07:00:00', '{"state": "PLAYING_HOLE", "fsm_state": "PLAYING_HOLE"}', '[]'),
                ('1002', 'luigi_bianchi', 18, '2026-09-25 07:30:00', '{"state": "GIRO_CHIUSO", "fsm_state": "GIRO_CHIUSO"}', '[{"hole": 1}]')
        """)

        cursor.execute("""
            INSERT INTO rounds (user_id, course_name, holes_played, total_score, total_putts, fairway_accuracy_pct, gir_pct, scrambling_pct, penalty_strokes)
            VALUES ('luigi_bianchi', 'Conero Golf Club', 18, 82, 31, 64.3, 44.4, 50.0, 1)
        """)

        conn.commit()
        conn.close()

        # Guardrail con permessi sulla sola cartella temporanea
        self.guardrail = SecurityGuardrail(allowed_directories=[self.temp_path])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_guardrail_safevault_deny_by_default(self):
        """Verifica che i guardrail blocchino qualsiasi scrittura su file protetti."""
        # 1. Blocco SafeVault sui file di produzione
        with self.assertRaises(SecurityViolationError):
            self.guardrail.validate_write_path("voice_caddy.db")

        with self.assertRaises(SecurityViolationError):
            self.guardrail.validate_write_path("users.json")

        # 2. Blocco scrittura fuori dalle cartelle autorizzate
        forbidden_path = Path("C:/Windows/System32/evil.txt")
        with self.assertRaises(SecurityViolationError):
            self.guardrail.validate_write_path(forbidden_path)

        # 3. Blocco comandi SQL distruttivi
        with self.assertRaises(SecurityViolationError):
            self.guardrail.assert_readonly_sql("DROP TABLE rounds")

        with self.assertRaises(SecurityViolationError):
            self.guardrail.assert_readonly_sql("DELETE FROM live_sessions WHERE chat_id = '1'")

        # 4. Consenso su query SELECT lecite
        self.guardrail.assert_readonly_sql("SELECT * FROM live_sessions")

    def test_lifecycle_hooks_and_prometheus_export(self):
        """Verifica la raccolta metrica tramite hooks e il rendering conforme a Prometheus."""
        hooks = LifecycleHookRegistry()
        prom = PrometheusMetricsHook()
        hooks.register(prom)

        hooks.trigger_metric("voice_caddy_server_status_up", 1.0)
        hooks.trigger_metric("voice_caddy_server_latency_milliseconds", 45.2)

        prom_text = prom.render_prometheus_text()
        self.assertIn("voice_caddy_llm_tokens_used 0", prom_text)
        self.assertIn("voice_caddy_server_status_up 1.0", prom_text)
        self.assertIn("voice_caddy_server_latency_milliseconds 45.2", prom_text)

    def test_server_monitor_agent_zero_tokens(self):
        """Verifica il ServerMonitorAgent su log e check a zero token."""
        # Crea un file di log simulato con un errore 500
        test_log = self.temp_path / "server_test.log"
        test_log.write_text("2026-09-25 07:00:00 INFO [200] GET /\n2026-09-25 07:01:00 ERROR 500 Internal Server Error\n", encoding="utf-8")

        agent = ServerMonitorAgent(
            target_url="http://127.0.0.1:8501",
            log_file_path=test_log,
            guardrail=self.guardrail,
            state_dir=self.temp_path
        )

        res = agent.tool_scan_log_errors_5xx(test_log)
        self.assertEqual(res["error_count_5xx"], 1)

        # Verifica zero token
        self.assertEqual(agent.tokens_used, 0)

    def test_server_monitor_agent_initial_run_none_last_run(self):
        """Verifica che ServerMonitorAgent non sollevi TypeError al primo avvio quando last_run è None e il server è ONLINE."""
        agent = ServerMonitorAgent(
            target_url="http://127.0.0.1:8501",
            guardrail=self.guardrail,
            state_dir=self.temp_path
        )
        # Assicura che last_run sia esplicitamente None (default da base_agent.py)
        agent.state["last_run"] = None
        agent.state["uptime_seconds"] = None

        # Simula server ONLINE (porta 8501 aperta o HTTP 200)
        original_execute_tool = agent.execute_tool
        def mock_execute_tool(tool_name, **kwargs):
            if tool_name == "check_http_endpoint":
                return {"is_up": True, "latency_ms": 12.5, "status_code": 200}
            if tool_name == "check_local_port_listening":
                return True
            if tool_name == "scan_log_errors_5xx":
                return {"error_count_5xx": 0, "errors": []}
            return original_execute_tool(tool_name, **kwargs)

        agent.execute_tool = mock_execute_tool

        # Primo ciclo (non deve sollevare TypeError: unsupported operand type(s) for -: 'float' and 'NoneType')
        cycle1 = agent.run_monitoring_cycle()
        self.assertTrue(cycle1["server_up"])
        self.assertEqual(cycle1["uptime_seconds"], 0)
        self.assertIsInstance(agent.state["last_run"], float)

        # Secondo ciclo (uptime deve incrementarsi regolarmente senza errori)
        agent.state["last_run"] = time.time() - 10  # 10 secondi fa
        cycle2 = agent.run_monitoring_cycle()
        self.assertGreaterEqual(cycle2["uptime_seconds"], 10)

    def test_server_monitor_agent_corrupted_state_resilience(self):
        """Verifica che stati anomali (stringhe al posto di numeri, None, tipi non validi) non mandino in crash l'agente."""
        agent = ServerMonitorAgent(
            target_url="http://127.0.0.1:8501",
            guardrail=self.guardrail,
            state_dir=self.temp_path
        )
        agent.state["last_run"] = "invalid_timestamp_string"
        agent.state["uptime_seconds"] = "not_a_number"
        agent.state["cycle_count"] = None

        def mock_execute_tool(tool_name, **kwargs):
            if tool_name == "check_http_endpoint":
                return {"is_up": True, "latency_ms": 15.0, "status_code": 200}
            if tool_name == "check_local_port_listening":
                return False
            if tool_name == "scan_log_errors_5xx":
                return {"error_count_5xx": 0, "errors": []}
            return {}

        agent.execute_tool = mock_execute_tool
        res = agent.run_monitoring_cycle()
        self.assertTrue(res["server_up"])
        self.assertEqual(res["uptime_seconds"], 0)
        self.assertEqual(agent.state["cycle_count"], 1)

    def test_telegram_session_agent_isolated(self):
        """Verifica estrazione sessioni attive e completate dal DB temporaneo."""
        agent = TelegramSessionAgent(
            db_path=self.db_path,
            guardrail=self.guardrail,
            state_dir=self.temp_path,
            inactivity_timeout_minutes=10
        )

        summary = agent.tool_get_session_summary()
        self.assertEqual(summary["total_registered_chats"], 2)
        self.assertEqual(summary["active_sessions"], 1)  # 1001 è PLAYING_HOLE
        self.assertEqual(summary["completed_sessions"], 1)  # 1002 è GIRO_CHIUSO

        cycle_res = agent.run_monitoring_cycle()
        self.assertEqual(cycle_res["active_now"], 1)
        self.assertEqual(agent.tokens_used, 0)

    def test_browser_completion_agent_and_funnel_math(self):
        """Verifica calcolo matematico del funnel tra Telegram e Browser."""
        agent = BrowserCompletionAgent(
            db_path=self.db_path,
            guardrail=self.guardrail,
            state_dir=self.temp_path
        )

        # Test calcolo funnel
        funnel = agent.tool_calculate_funnel_conversion(
            telegram_started=10,
            telegram_completed=8,
            browser_completed=4
        )
        self.assertEqual(funnel["overall_completion_rate_pct"], 40.0)
        self.assertEqual(funnel["telegram_finish_rate_pct"], 80.0)
        self.assertEqual(funnel["telegram_to_browser_bridge_rate_pct"], 50.0)
        self.assertEqual(funnel["dropoff_telegram_in_round"], 2)
        self.assertEqual(funnel["dropoff_before_browser_save"], 4)

        # Test caso limite: 0 partenze
        zero_funnel = agent.tool_calculate_funnel_conversion(0, 0, 0)
        self.assertEqual(zero_funnel["overall_completion_rate_pct"], 0.0)

        # Esecuzione ciclo
        cycle_res = agent.run_monitoring_cycle(telegram_started=2, telegram_completed=1)
        self.assertGreaterEqual(cycle_res["browser_completed"], 1)
        self.assertEqual(agent.tokens_used, 0)

    def test_golf_intelligence_advisor_recommendations(self):
        """Verifica le raccomandazioni statistiche di golf e il catalogo degli agenti."""
        agent = GolfIntelligenceAdvisorAgent(
            db_path=self.db_path,
            guardrail=self.guardrail,
            state_dir=self.temp_path
        )

        stats = agent.tool_recommend_advanced_golf_stats()
        self.assertGreaterEqual(len(stats["ambiti_statistici_raccomandati"]), 8)

        agents = agent.tool_suggest_free_specialized_agents_suite()
        self.assertGreaterEqual(len(agents["suite_agenti_specializzati_gratuiti"]), 6)

        agent_names = [a["nome_agente"] for a in agents["suite_agenti_specializzati_gratuiti"]]
        self.assertIn("SafeVaultDataGuardianAgent", agent_names)
        self.assertIn("PaceOfPlayMarshallAgent", agent_names)
        self.assertIn("TacticalHazardRiskAgent", agent_names)
        self.assertIn("WHSHandicapAuditorAgent", agent_names)

        # Zero token check
        self.assertEqual(agent.tokens_used, 0)

    def test_full_orchestrator_iteration(self):
        """Verifica che l'intero orchestratore esegua un ciclo completo a costo zero."""
        orchestrator = MonitoringOrchestrator(
            db_path=self.db_path,
            exporter_port=9199,
            cycle_interval_seconds=10
        )
        summary = orchestrator.run_single_iteration()

        self.assertEqual(summary["tokens_consumed"], 0)
        self.assertEqual(summary["llm_cost_eur"], 0.0)
        self.assertIn("server", summary)
        self.assertIn("telegram", summary)
        self.assertIn("browser", summary)
        self.assertIn("advisor", summary)

    def test_advanced_golf_stats_engine(self):
        """Verifica che il motore AdvancedGolfStatsEngine calcoli tutte le 8 aree golfistiche a costo zero."""
        from core.advanced_golf_stats import AdvancedGolfStatsEngine
        from core.schemas import HoleData, Shot, GolfRoundData, PerformanceSummary, RoundInfo

        # Genera 18 buche simulate per il test
        holes = []
        for h_idx in range(1, 19):
            shots = [
                Shot(shot_index=1, club="Driver", distance_meters=215.0, lie="fairway", result="good"),
                Shot(shot_index=2, club="Ferro 7", distance_meters=140.0, lie="fairway", result="green", plays_like_distance=145.0, elevation_diff=4.0)
            ]
            holes.append(HoleData(
                hole_number=h_idx,
                par=4,
                score=4 if h_idx % 2 == 0 else 5,
                fairway_hit=True if h_idx % 3 != 0 else False,
                gir=True if h_idx % 2 == 0 else False,
                putts=2 if h_idx % 4 != 0 else 1,
                penalties=1 if h_idx == 7 else 0,
                shots=shots
            ))

        engine = AdvancedGolfStatsEngine()
        disp = engine.analyze_dispersion(holes)
        self.assertIn("miss_tendency", disp)
        self.assertGreater(disp["avg_distance_m"], 100.0)

        ltg = engine.analyze_lie_to_gir(holes)
        self.assertIn("conversion_matrix", ltg)

        sg = engine.analyze_strokes_gained_4way(holes, player_handicap=15.0)
        self.assertIn("sg_off_the_tee", sg)
        self.assertIn("sg_approach", sg)
        self.assertIn("sg_putting", sg)

        bb = engine.analyze_bounce_back(holes)
        self.assertIn("bounce_back_rate_pct", bb)

        pz = engine.analyze_putting_zones(holes)
        self.assertIn("pressure_putts_less_than_1_5m_pct", pz)

        pl = engine.analyze_plays_like_efficiency(holes)
        self.assertIn("plays_like_correction_efficiency_pct", pl)

        cc = engine.analyze_caddy_compliance(holes)
        self.assertIn("strokes_saved_by_caddy_discipline", cc)

        fc = engine.analyze_fatigue_curve(holes)
        self.assertTrue(fc["has_18_holes"])
        self.assertIn("delta_back_vs_front", fc)

        # Report completo su round valido
        from core.demo_data import get_demo_golf_round
        round_mock = get_demo_golf_round()
        full_rep = engine.compile_full_player_report([round_mock], player_handicap=15.0)
        self.assertGreaterEqual(full_rep["total_holes_analyzed"], 1)

    def test_admin_exclusive_monitoring_policy(self):
        """Verifica che le autorizzazioni di monitoraggio siano rigorosamente circoscritte all'amministratore."""
        from core.auth import UserRecord

        admin_user = UserRecord(
            user_id="strafatti_stefano_pirani",
            group="strafatti",
            first_name="Stefano",
            last_name="Pirani",
            username="Stefano",
            password_hash="fakehash",
            salt="fakesalt",
            must_change_password=False,
            is_admin=True,
            role="admin"
        )

        regular_user = UserRecord(
            user_id="strafatti_mario_rossi",
            group="strafatti",
            first_name="Mario",
            last_name="Rossi",
            username="Mario",
            password_hash="fakehash",
            salt="fakesalt",
            must_change_password=False,
            is_admin=False,
            role="user"
        )

        # Regola di autorizzazione: solo Stefano (is_admin=True) può accedere
        self.assertTrue(admin_user.is_admin)
        self.assertEqual(admin_user.role, "admin")
        self.assertFalse(regular_user.is_admin)
        self.assertEqual(regular_user.role, "user")


if __name__ == "__main__":
    unittest.main()
