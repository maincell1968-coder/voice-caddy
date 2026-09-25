"""
Voice Caddy Pro - Zero-Cost Monitoring Package.
Fornisce agenti specializzati per il monitoraggio a costo token zero (Zero LLM Tokens)
di server, sessioni Telegram, completamenti Browser, funnel di conversione
e consulenza statistica avanzata sul golf.
"""

from __future__ import annotations

try:
    from monitoring.guardrails import SecurityGuardrail, SecurityViolationError
    from monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from monitoring.base_agent import ZeroCostBaseAgent
    from monitoring.server_monitor_agent import ServerMonitorAgent
    from monitoring.telegram_session_agent import TelegramSessionAgent
    from monitoring.browser_completion_agent import BrowserCompletionAgent
    from monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from monitoring.metrics_exporter import PrometheusExporterServer
except ImportError:
    from voice_caddy.monitoring.guardrails import SecurityGuardrail, SecurityViolationError
    from voice_caddy.monitoring.hooks import LifecycleHookRegistry, PrometheusMetricsHook, AuditLogHook
    from voice_caddy.monitoring.base_agent import ZeroCostBaseAgent
    from voice_caddy.monitoring.server_monitor_agent import ServerMonitorAgent
    from voice_caddy.monitoring.telegram_session_agent import TelegramSessionAgent
    from voice_caddy.monitoring.browser_completion_agent import BrowserCompletionAgent
    from voice_caddy.monitoring.golf_intelligence_advisor import GolfIntelligenceAdvisorAgent
    from voice_caddy.monitoring.metrics_exporter import PrometheusExporterServer

__all__ = [
    "SecurityGuardrail",
    "SecurityViolationError",
    "LifecycleHookRegistry",
    "PrometheusMetricsHook",
    "AuditLogHook",
    "ZeroCostBaseAgent",
    "ServerMonitorAgent",
    "TelegramSessionAgent",
    "BrowserCompletionAgent",
    "GolfIntelligenceAdvisorAgent",
    "PrometheusExporterServer",
]
