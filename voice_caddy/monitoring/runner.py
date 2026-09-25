from __future__ import annotations

import os
import sys
import json
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# Aggiungi root al path di Python se necessario
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from monitoring.guardrails import SecurityGuardrail
    from monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from monitoring.server_monitor_agent import ServerMonitorAgent
    from monitoring.telegram_session_agent import TelegramSessionAgent
    from monitoring.browser_completion_agent import BrowserCompletionAgent
    from monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from monitoring.metrics_exporter import PrometheusExporterServer
except ImportError:
    from voice_caddy.monitoring.guardrails import SecurityGuardrail
    from voice_caddy.monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from voice_caddy.monitoring.server_monitor_agent import ServerMonitorAgent
    from voice_caddy.monitoring.telegram_session_agent import TelegramSessionAgent
    from voice_caddy.monitoring.browser_completion_agent import BrowserCompletionAgent
    from voice_caddy.monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from voice_caddy.monitoring.metrics_exporter import PrometheusExporterServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ZeroCostMonitor] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("VoiceCaddyMonitoring.Runner")


class MonitoringOrchestrator:
    """Orchestratore principale per l'esecuzione continua degli agenti a costo token zero."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        exporter_port: int = 9102,
        cycle_interval_seconds: int = 15,
        target_server_url: str = "http://127.0.0.1:8501"
    ):
        self.interval = cycle_interval_seconds
        self.is_running = False

        # Inizializzazione Guardrail
        self.guardrail = SecurityGuardrail()
        monitor_dir = Path(__file__).resolve().parent
        self.state_dir = monitor_dir / ".state"
        self.logs_dir = monitor_dir / "logs"
        self.pid_file = self.state_dir / "monitor.pid"

        self.guardrail.allow_directory(self.state_dir)
        self.guardrail.allow_directory(self.logs_dir)

        # Inizializzazione Lifecycle Hooks
        self.hooks = LifecycleHookRegistry()
        self.prom_hook = PrometheusMetricsHook()
        self.audit_hook = AuditLogHook(self.logs_dir / "telemetry_audit.jsonl", self.guardrail)

        self.hooks.register(self.prom_hook)
        self.hooks.register(self.audit_hook)

        # Inizializzazione Agenti Specializzati (3-5 tools ciascuno)
        self.server_agent = ServerMonitorAgent(
            target_url=target_server_url,
            guardrail=self.guardrail,
            hook_registry=self.hooks,
            state_dir=self.state_dir
        )

        self.tg_agent = TelegramSessionAgent(
            db_path=db_path,
            guardrail=self.guardrail,
            hook_registry=self.hooks,
            state_dir=self.state_dir
        )

        self.browser_agent = BrowserCompletionAgent(
            db_path=db_path,
            guardrail=self.guardrail,
            hook_registry=self.hooks,
            state_dir=self.state_dir
        )

        self.advisor_agent = GolfIntelligenceAdvisorAgent(
            db_path=db_path,
            guardrail=self.guardrail,
            hook_registry=self.hooks,
            state_dir=self.state_dir
        )

        # Prometheus Exporter Server
        self.exporter = PrometheusExporterServer(port=exporter_port, hook=self.prom_hook)

    def write_pid(self) -> None:
        try:
            self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass

    def remove_pid(self) -> None:
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

    def run_single_iteration(self) -> Dict[str, Any]:
        """Esegue un ciclo sincrono di tutti gli agenti a costo token = 0."""
        # 1. Server Monitor
        server_res = self.server_agent.run_monitoring_cycle()

        # 2. Telegram Sessions
        tg_res = self.tg_agent.run_monitoring_cycle()

        # 3. Browser Completions & Funnel Rate
        browser_res = self.browser_agent.run_monitoring_cycle(
            telegram_started=tg_res["sessions_started"],
            telegram_completed=tg_res["sessions_completed"]
        )

        # 4. Golf Intelligence Advisory (valutazione periodica)
        advisor_res = self.advisor_agent.run_monitoring_cycle()

        summary = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "server": server_res,
            "telegram": tg_res,
            "browser": browser_res,
            "advisor": advisor_res,
            "tokens_consumed": 0,
            "llm_cost_eur": 0.0
        }
        return summary

    def start(self) -> None:
        """Avvia il demone continuo di monitoraggio."""
        self.is_running = True
        self.write_pid()
        self.exporter.start(summary_provider=self.run_single_iteration)

        logger.info("======================================================================")
        logger.info("⛳ VOICE CADDY PRO - SUITE DI MONITORAGGIO A COSTO TOKEN ZERO AVVIATA")
        logger.info("======================================================================")
        logger.info(f"Intervallo di scansione: {self.interval} secondi")
        logger.info(f"Prometheus Metriche: http://127.0.0.1:{self.exporter.port}/metrics")
        logger.info(f"API Telemetria JSON: http://127.0.0.1:{self.exporter.port}/api/summary")
        logger.info("Agenti attivi: ServerMonitorAgent, TelegramSessionAgent, BrowserCompletionAgent, GolfIntelligenceAdvisorAgent")
        logger.info("SafeVault Protection: ATTIVA (Scrittura negata sui dati di produzione)")

        try:
            while self.is_running:
                res = self.run_single_iteration()
                srv = res["server"]
                tg = res["telegram"]
                brw = res["browser"]
                logger.info(
                    f"Status Server: {'UP' if srv['server_up'] else 'DOWN'} ({srv['latency_ms']}ms) | "
                    f"TG Avviate: {tg['sessions_started']} | TG Chiuse: {tg['sessions_completed']} | "
                    f"Browser Completi: {brw['browser_completed']} | Funnel: {brw['completion_rate_pct']}% | "
                    f"Tokens: 0"
                )
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Arresto manuale del monitoraggio intercettato.")
        finally:
            self.stop()

    def stop(self) -> None:
        self.is_running = False
        self.exporter.stop()
        self.remove_pid()
        logger.info("Monitoraggio terminato correttamente.")


def main():
    parser = argparse.ArgumentParser(description="Voice Caddy Pro Zero-Cost Monitoring Suite")
    parser.add_argument("--interval", type=int, default=15, help="Intervallo di polling in secondi (default: 15)")
    parser.add_argument("--port", type=int, default=9102, help="Porta per l'exporter Prometheus (default: 9102)")
    parser.add_argument("--once", action="store_true", help="Esegue un solo ciclo e stampa il riepilogo JSON")
    parser.add_argument("--target-url", type=str, default="http://127.0.0.1:8501", help="URL server Streamlit da verificare")
    args = parser.parse_args()

    orchestrator = MonitoringOrchestrator(
        exporter_port=args.port,
        cycle_interval_seconds=args.interval,
        target_server_url=args.target_url
    )

    if args.once:
        res = orchestrator.run_single_iteration()
        print(json.dumps(res, indent=2, default=str))
    else:
        # Gestione segnali di terminazione
        def handle_sig(sig, frame):
            orchestrator.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_sig)
        signal.signal(signal.SIGTERM, handle_sig)
        orchestrator.start()


if __name__ == "__main__":
    main()
