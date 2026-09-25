from __future__ import annotations

import os
import re
import socket
import time
import urllib.request
import urllib.parse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
try:
    from monitoring.base_agent import ZeroCostBaseAgent
except ImportError:
    from voice_caddy.monitoring.base_agent import ZeroCostBaseAgent


class ServerMonitorAgent(ZeroCostBaseAgent):
    """
    Agente specializzato nel monitoraggio della salute dei server a costo zero.
    Monitora:
    1. Uptime server e stato dei processi applicativi.
    2. Latenza HTTP (ms) per la dashboard Streamlit o i servizi di backend.
    3. Errori HTTP 5xx nei log applicativi in tempo reale.
    4. Integrazione con l'API gratuita di UptimeRobot (o fallback trasparente su probe locale).
    """

    def __init__(
        self,
        target_url: str = "http://127.0.0.1:8501",
        uptimerobot_api_key: Optional[str] = None,
        log_file_path: Optional[Path] = None,
        **kwargs
    ):
        self.target_url = target_url
        self.uptimerobot_api_key = uptimerobot_api_key or os.getenv("UPTIMEROBOT_API_KEY", "")
        self.log_file_path = log_file_path
        super().__init__(name="ServerMonitorAgent", **kwargs)

    def _register_default_tools(self) -> None:
        self.register_tool(
            "check_http_endpoint",
            self.tool_check_http_endpoint,
            "Controlla disponibilità e latenza di un endpoint HTTP (es. Streamlit 8501)"
        )
        self.register_tool(
            "fetch_uptimerobot_status",
            self.tool_fetch_uptimerobot_status,
            "Interroga l'API di UptimeRobot (piano free 50 monitor) o fallback locale"
        )
        self.register_tool(
            "scan_log_errors_5xx",
            self.tool_scan_log_errors_5xx,
            "Scansiona i log per rilevare errori 500, 502, 503, 504 in real-time"
        )
        self.register_tool(
            "check_local_port_listening",
            self.tool_check_local_port_listening,
            "Verifica la presenza di socket attivi su porte strategiche (8501, 9102)"
        )

    def tool_check_http_endpoint(self, url: Optional[str] = None, timeout: float = 3.0) -> Dict[str, Any]:
        """Esegue una chiamata HTTP GET a livello di processo misurando la latenza precisa in millisecondi."""
        target = url or self.target_url
        t0 = time.perf_counter()
        status_code = 0
        is_up = False
        error_msg = None

        try:
            req = urllib.request.Request(target, headers={"User-Agent": "VoiceCaddyMonitor/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                is_up = (200 <= status_code < 400)
        except Exception as e:
            error_msg = str(e)
            # Riconosci status code se presente nell'eccezione HTTPError
            if hasattr(e, "code"):
                status_code = getattr(e, "code")
                is_up = (status_code < 500)

        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "url": target,
            "is_up": is_up,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "error": error_msg,
            "timestamp": time.time()
        }

    def tool_fetch_uptimerobot_status(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Interroga l'API v2 di UptimeRobot se la chiave API è configurata.
        Se non presente, restituisce lo stato derivato dalle verifiche locali.
        """
        key = api_key or self.uptimerobot_api_key
        if not key or key == "mock_key":
            return {
                "source": "local_fallback",
                "configured": False,
                "message": "UptimeRobot API key non configurata (usare probe HTTP locale)",
                "monitors": []
            }

        endpoint = "https://api.uptimerobot.com/v2/getMonitors"
        data = urllib.parse.urlencode({
            "api_key": key,
            "format": "json",
            "logs": "1"
        }).encode("utf-8")

        try:
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return {
                    "source": "uptimerobot_api",
                    "configured": True,
                    "stat": res.get("stat"),
                    "total": res.get("pagination", {}).get("total", 0),
                    "monitors": res.get("monitors", [])
                }
        except Exception as e:
            return {
                "source": "uptimerobot_api",
                "configured": True,
                "error": str(e),
                "monitors": []
            }

    def tool_scan_log_errors_5xx(self, log_path: Optional[Path] = None, max_lines: int = 500) -> Dict[str, Any]:
        """
        Legge la coda del file di log per contare gli errori 5xx verificatisi di recente.
        Utilizza guardrail deny-by-default per la sicurezza del percorso.
        """
        target = log_path or self.log_file_path
        if not target or not Path(target).exists():
            return {"error_count_5xx": 0, "status": "log_not_found_or_empty", "errors": []}

        validated_path = self.guardrail.validate_read_path(target)
        error_regex = re.compile(r"\b(500|502|503|504)\b|Internal Server Error|Traceback", re.IGNORECASE)

        errors_found = []
        try:
            with open(validated_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-max_lines:]
                for line in lines:
                    if error_regex.search(line):
                        errors_found.append(line.strip())
        except Exception as e:
            return {"error_count_5xx": 0, "read_error": str(e), "errors": []}

        return {
            "error_count_5xx": len(errors_found),
            "file": str(validated_path),
            "errors": errors_found[-10:]
        }

    def tool_check_local_port_listening(self, host: str = "127.0.0.1", port: int = 8501, timeout: float = 1.0) -> bool:
        """Verifica a livello di socket TCP se il servizio locale è in ascolto."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            res = sock.connect_ex((host, port))
            return res == 0
        finally:
            sock.close()

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Esegue il ciclo completo di monitoraggio dell'infrastruttura server."""
        cycle_start = time.time()

        # 1. Probe HTTP
        http_res = self.execute_tool("check_http_endpoint", url=self.target_url)

        # 2. Controllo porta Streamlit (8501)
        port_open = self.execute_tool("check_local_port_listening", host="127.0.0.1", port=8501)

        # 3. Controllo log errori 5xx
        log_res = self.execute_tool("scan_log_errors_5xx", log_path=self.log_file_path)

        # Calcolo Uptime continuativo con gestione difensiva dei tipi (evita TypeError con None)
        raw_uptime = self.state.get("uptime_seconds")
        try:
            uptime_seconds = int(raw_uptime) if raw_uptime is not None else 0
        except (ValueError, TypeError):
            uptime_seconds = 0

        raw_last_run = self.state.get("last_run")
        try:
            last_run = float(raw_last_run) if raw_last_run is not None else None
        except (ValueError, TypeError):
            last_run = None

        if http_res.get("is_up") or port_open:
            if last_run is not None:
                elapsed = max(0, int(time.time() - last_run))
                # Se l'intervallo tra due cicli supera i 5 minuti (300s), resettiamo per evitare salti anomali
                if elapsed > 300:
                    elapsed = 0
            else:
                elapsed = 0
            uptime_seconds += elapsed
        else:
            uptime_seconds = 0

        # Emissione metriche per Prometheus e Grafana
        server_up_val = 1.0 if (http_res.get("is_up") or port_open) else 0.0
        self.emit_metric("voice_caddy_server_status_up", server_up_val)
        self.emit_metric("voice_caddy_server_latency_milliseconds", float(http_res.get("latency_ms", 0.0)))
        self.emit_metric("voice_caddy_server_uptime_seconds", float(uptime_seconds))
        self.emit_metric("voice_caddy_http_5xx_errors_total", float(log_res.get("error_count_5xx", 0)))

        # Aggiornamento dello stato persistente
        self.state["last_run"] = cycle_start
        self.state["uptime_seconds"] = uptime_seconds
        self.state["cycle_count"] = int(self.state.get("cycle_count") or 0) + 1
        self.state["last_http_check"] = http_res
        self.state["port_8501_open"] = port_open
        self.state["errors_5xx_count"] = log_res.get("error_count_5xx", 0)

        self.persist_state()

        return {
            "server_up": bool(server_up_val),
            "latency_ms": http_res.get("latency_ms", 0.0),
            "uptime_seconds": uptime_seconds,
            "errors_5xx": log_res.get("error_count_5xx", 0),
            "cycle_duration_ms": round((time.time() - cycle_start) * 1000.0, 2)
        }
