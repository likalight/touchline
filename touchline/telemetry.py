"""Observability: OpenTelemetry -> Azure Monitor / Application Insights (and the Foundry
tracing view) when APPLICATIONINSIGHTS_CONNECTION_STRING is set; Agent Framework
instrumentation is enabled so every agent run and workflow superstep is traced."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("touchline.telemetry")


def setup_telemetry() -> str:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    mode = "off"
    if conn:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=conn)
            mode = "azure_monitor"
        except Exception as exc:  # pragma: no cover
            log.warning("Azure Monitor not configured: %s", exc)
    elif os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        mode = "otlp"
    if mode != "off":
        try:
            from agent_framework.observability import enable_instrumentation

            enable_instrumentation()
        except Exception as exc:  # pragma: no cover
            log.warning("Agent Framework instrumentation unavailable: %s", exc)
    log.info("telemetry: %s", mode)
    return mode
