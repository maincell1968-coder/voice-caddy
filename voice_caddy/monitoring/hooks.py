from __future__ import annotations

import json
import time
import logging
from abc import ABC
from pathlib import Path
from typing import Dict, Any, List, Optional
try:
    from monitoring.guardrails import SecurityGuardrail
except ImportError:
    from voice_caddy.monitoring.guardrails import SecurityGuardrail

logger = logging.getLogger("VoiceCaddyMonitoring.Hooks")


class BaseLifecycleHook(ABC):
    """Interfaccia astratta per i Lifecycle Hooks ispirati all'Antigravity SDK."""

    def on_session_start(self, agent_name: str, session_id: str, metadata: Dict[str, Any]) -> None:
        pass

    def on_tool_call(self, agent_name: str, tool_name: str, params: Dict[str, Any]) -> None:
        pass

    def on_tool_result(self, agent_name: str, tool_name: str, result: Any, duration_ms: float) -> None:
        pass

    def on_error(self, agent_name: str, error: Exception, context: Dict[str, Any]) -> None:
        pass

    def on_metric_emitted(self, metric_name: str, value: float, labels: Dict[str, str], timestamp: float) -> None:
        pass

    def on_state_persisted(self, agent_name: str, state_file: Path) -> None:
        pass


class PrometheusMetricsHook(BaseLifecycleHook):
    """
    Hook in-memory per accumulare metriche in formato compatibile Prometheus/Grafana.
    Memorizza counters, gauges e timeline a costo computazionale nullo e zero token.
    """

    def __init__(self):
        self._gauges: Dict[str, float] = {}
        self._counters: Dict[str, float] = {}
        self._labels: Dict[str, Dict[str, str]] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_history = 500

    def on_metric_emitted(self, metric_name: str, value: float, labels: Dict[str, str], timestamp: float) -> None:
        key = metric_name
        self._gauges[key] = value
        self._labels[key] = labels or {}

        if metric_name.endswith("_total") or "counter" in metric_name:
            self._counters[key] = self._counters.get(key, 0.0) + value

        self._history.append({
            "metric": metric_name,
            "value": value,
            "labels": labels,
            "timestamp": timestamp
        })
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_gauge(self, name: str, default: float = 0.0) -> float:
        return self._gauges.get(name, default)

    def get_all_metrics(self) -> Dict[str, Any]:
        return {
            "gauges": dict(self._gauges),
            "counters": dict(self._counters),
            "labels": dict(self._labels),
            "recent_events": list(self._history[-20:])
        }

    def render_prometheus_text(self) -> str:
        """Restituisce il testo conforme alla sintassi Prometheus standard per lo scraping HTTP."""
        lines = [
            "# HELP voice_caddy_monitoring Voice Caddy Zero-Cost Telemetry",
            "# TYPE voice_caddy_monitoring gauge"
        ]
        now = int(time.time())

        # Tokens used gauge (sempre 0 per dimostrare l'assenza di costi LLM)
        lines.append("# HELP voice_caddy_llm_tokens_used Consumo token LLM nel monitoraggio (garantito 0)")
        lines.append("# TYPE voice_caddy_llm_tokens_used counter")
        lines.append("voice_caddy_llm_tokens_used 0")

        for k, v in self._gauges.items():
            label_dict = self._labels.get(k, {})
            label_str = ""
            if label_dict:
                items = [f'{lk}="{lv}"' for lk, lv in label_dict.items()]
                label_str = "{" + ",".join(items) + "}"
            lines.append(f"{k}{label_str} {v}")

        return "\n".join(lines) + "\n"


class AuditLogHook(BaseLifecycleHook):
    """Registra tutti gli eventi del ciclo di vita su file JSONL per tracciamento real-time."""

    def __init__(self, log_path: Path, guardrail: SecurityGuardrail):
        self.guardrail = guardrail
        self.log_path = self.guardrail.validate_write_path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_entry(self, entry: Dict[str, Any]) -> None:
        try:
            entry["timestamp"] = time.time()
            entry["iso_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            line = json.dumps(entry, default=str) + "\n"
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"Impossibile scrivere audit log su {self.log_path}: {e}")

    def on_session_start(self, agent_name: str, session_id: str, metadata: Dict[str, Any]) -> None:
        self._write_entry({
            "event": "SESSION_START",
            "agent": agent_name,
            "session_id": session_id,
            "metadata": metadata
        })

    def on_tool_call(self, agent_name: str, tool_name: str, params: Dict[str, Any]) -> None:
        self._write_entry({
            "event": "TOOL_CALL",
            "agent": agent_name,
            "tool": tool_name,
            "params": params
        })

    def on_tool_result(self, agent_name: str, tool_name: str, result: Any, duration_ms: float) -> None:
        # Tronca risultati troppo lunghi per non appesantire il log
        res_summary = str(result)[:300] if result is not None else None
        self._write_entry({
            "event": "TOOL_RESULT",
            "agent": agent_name,
            "tool": tool_name,
            "duration_ms": duration_ms,
            "result_summary": res_summary
        })

    def on_error(self, agent_name: str, error: Exception, context: Dict[str, Any]) -> None:
        self._write_entry({
            "event": "ERROR",
            "agent": agent_name,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "context": context
        })


class LifecycleHookRegistry:
    """Registro centrale per la distribuzione sincrona degli eventi a tutti gli hook attivi."""

    def __init__(self):
        self._hooks: List[BaseLifecycleHook] = []

    def register(self, hook: BaseLifecycleHook) -> None:
        if hook not in self._hooks:
            self._hooks.append(hook)

    def trigger_session_start(self, agent_name: str, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        meta = metadata or {}
        for h in self._hooks:
            try:
                h.on_session_start(agent_name, session_id, meta)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_session_start: {e}")

    def trigger_tool_call(self, agent_name: str, tool_name: str, params: Dict[str, Any]) -> None:
        for h in self._hooks:
            try:
                h.on_tool_call(agent_name, tool_name, params)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_tool_call: {e}")

    def trigger_tool_result(self, agent_name: str, tool_name: str, result: Any, duration_ms: float) -> None:
        for h in self._hooks:
            try:
                h.on_tool_result(agent_name, tool_name, result, duration_ms)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_tool_result: {e}")

    def trigger_error(self, agent_name: str, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        ctx = context or {}
        for h in self._hooks:
            try:
                h.on_error(agent_name, error, ctx)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_error: {e}")

    def trigger_metric(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None, timestamp: Optional[float] = None) -> None:
        t = timestamp or time.time()
        lbls = labels or {}
        for h in self._hooks:
            try:
                h.on_metric_emitted(metric_name, value, lbls, t)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_metric_emitted: {e}")

    def trigger_state_persisted(self, agent_name: str, state_file: Path) -> None:
        for h in self._hooks:
            try:
                h.on_state_persisted(agent_name, state_file)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dell'hook on_state_persisted: {e}")
