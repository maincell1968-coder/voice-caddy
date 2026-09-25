from __future__ import annotations

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable
try:
    from monitoring.hooks import PrometheusMetricsHook
except ImportError:
    from voice_caddy.monitoring.hooks import PrometheusMetricsHook

logger = logging.getLogger("VoiceCaddyMonitoring.Exporter")


class PrometheusRequestHandler(BaseHTTPRequestHandler):
    """Handler HTTP leggero per esporre le metriche Prometheus su /metrics."""

    hook: Optional[PrometheusMetricsHook] = None
    summary_provider: Optional[Callable[[], dict]] = None

    def log_message(self, format, *args):
        # Disabilita il log verboso delle richieste per preservare performance e zero rumore
        pass

    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            if self.hook:
                body = self.hook.render_prometheus_text().encode("utf-8")
            else:
                body = b"# No metrics hook registered\n"
            self.wfile.write(body)

        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            res = {"status": "UP", "service": "Voice Caddy Zero-Cost Monitoring Exporter"}
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif self.path == "/api/summary":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {}
            if self.summary_provider:
                data = self.summary_provider()
            elif self.hook:
                data = self.hook.get_all_metrics()
            self.wfile.write(json.dumps(data, default=str).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")


class PrometheusExporterServer:
    """Server HTTP in background per servire le metriche a Grafana e Prometheus."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9102, hook: Optional[PrometheusMetricsHook] = None):
        self.host = host
        self.port = port
        self.hook = hook
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self, summary_provider: Optional[Callable[[], dict]] = None) -> bool:
        if self.is_running:
            return True

        handler_cls = PrometheusRequestHandler
        handler_cls.hook = self.hook
        handler_cls.summary_provider = summary_provider

        try:
            self._server = HTTPServer((self.host, self.port), handler_cls)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            self.is_running = True
            logger.info(f"Prometheus Exporter avviato su http://{self.host}:{self.port}/metrics")
            return True
        except Exception as e:
            logger.error(f"Impossibile avviare il server Prometheus su porta {self.port}: {e}")
            return False

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        self.is_running = False
        logger.info("Prometheus Exporter arrestato.")
