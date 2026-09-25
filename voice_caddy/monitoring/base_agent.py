from __future__ import annotations

import time
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Callable, Optional, List
try:
    from monitoring.guardrails import SecurityGuardrail
    from monitoring.hooks import LifecycleHookRegistry
except ImportError:
    from voice_caddy.monitoring.guardrails import SecurityGuardrail
    from voice_caddy.monitoring.hooks import LifecycleHookRegistry

logger = logging.getLogger("VoiceCaddyMonitoring.BaseAgent")


class ZeroCostBaseAgent(ABC):
    """
    Classe base per gli agenti di monitoraggio specializzati a costo zero di token.
    Principi architetturali:
    1. ZERO TOKEN: Nessuna chiamata a modelli LLM durante l'esecuzione operativa.
    2. SET MINIMO DI STRUMENTI (3-5 tools deterministici per agente).
    3. PERSISTENZA DELLO STATO: Ripresa del contesto tramite file JSON locale senza database esterni.
    4. LIFECYCLE HOOKS: Notifica continua degli eventi (session_start, tool_call, error, metriche).
    5. SICUREZZA DENY-BY-DEFAULT: Ogni operazione su filesystem o dati rispetta i guardrail di sicurezza.
    """

    def __init__(
        self,
        name: str,
        guardrail: Optional[SecurityGuardrail] = None,
        hook_registry: Optional[LifecycleHookRegistry] = None,
        state_dir: Optional[Path] = None
    ):
        self.name = name
        self.guardrail = guardrail or SecurityGuardrail()
        self.hooks = hook_registry or LifecycleHookRegistry()

        # Percorso per la persistenza dello stato di sessione
        project_root = Path(__file__).resolve().parent.parent
        self.state_dir = Path(state_dir) if state_dir else (project_root / "monitoring" / ".state")
        self.guardrail.allow_directory(self.state_dir)
        self.state_file = self.state_dir / f"{self.name.lower()}_state.json"

        # Stato interno e metriche di costo
        self.state: Dict[str, Any] = {}
        self.tokens_used: int = 0  # Costante 0!
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.session_id: str = f"sess_{self.name.lower()}_{int(time.time())}"

        self._register_default_tools()
        self.load_state()

        # Notifica inizio sessione agente
        self.hooks.trigger_session_start(self.name, self.session_id, {
            "agent_type": "ZeroCostMonitoringAgent",
            "tools_count": len(self.tools),
            "state_file": str(self.state_file)
        })

    def register_tool(self, name: str, func: Callable, description: str) -> None:
        """Registra uno strumento deterministico per l'agente (massimo 5 raccomandati)."""
        self.tools[name] = {
            "name": name,
            "func": func,
            "description": description
        }

    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Esegue uno strumento registrato misurando la latenza e attivando i lifecycle hooks."""
        if tool_name not in self.tools:
            err = ValueError(f"Strumento '{tool_name}' non registrato per l'agente {self.name}")
            self.hooks.trigger_error(self.name, err, {"requested_tool": tool_name})
            raise err

        tool_meta = self.tools[tool_name]
        self.hooks.trigger_tool_call(self.name, tool_name, kwargs)

        start_time = time.perf_counter()
        try:
            result = tool_meta["func"](**kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.hooks.trigger_tool_result(self.name, tool_name, result, duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.hooks.trigger_error(self.name, e, {
                "tool": tool_name,
                "params": kwargs,
                "duration_ms": duration_ms
            })
            raise

    def load_state(self) -> Dict[str, Any]:
        """Carica lo stato persistito dal file JSON locale."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
                    return self.state
            except Exception as e:
                logger.warning(f"Impossibile leggere lo stato di {self.name}: {e}")
        self.state = {
            "last_run": None,
            "cycle_count": 0,
            "metrics": {}
        }
        return self.state

    def persist_state(self) -> None:
        """Salva lo stato corrente su disco locale in modo atomico e sicuro."""
        try:
            validated_path = self.guardrail.validate_write_path(self.state_file)
            temp_path = validated_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
            # Sostituzione atomica
            temp_path.replace(validated_path)
            self.hooks.trigger_state_persisted(self.name, validated_path)
        except Exception as e:
            self.hooks.trigger_error(self.name, e, {"action": "persist_state"})

    def emit_metric(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Emette una metrica telemetrica verso Prometheus e la dashboard live."""
        lbls = labels or {}
        lbls["agent"] = self.name
        self.hooks.trigger_metric(metric_name, value, lbls)

    @abstractmethod
    def _register_default_tools(self) -> None:
        """Ogni sottoclasse registra qui i suoi 3-5 strumenti specifici."""
        pass

    @abstractmethod
    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Esegue un ciclo completo di monitoraggio a costo zero."""
        pass
