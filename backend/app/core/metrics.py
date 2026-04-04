from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass(slots=True)
class MetricsRegistry:
    total_ingested: int = 0
    total_alerts: int = 0
    auth_success: int = 0
    auth_failures: int = 0
    ws_clients: int = 0
    sse_clients: int = 0
    buffer_drops: int = 0
    _lock: Lock = field(default_factory=Lock)

    def increment(self, field_name: str, value: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + value)

    def set_value(self, field_name: str, value: int) -> None:
        with self._lock:
            setattr(self, field_name, value)

    def to_prometheus(self, queue_depth: int, db_ok: bool) -> str:
        lines = [
            "# HELP telemetry_ingested_total Number of telemetry events ingested.",
            "# TYPE telemetry_ingested_total counter",
            f"telemetry_ingested_total {self.total_ingested}",
            "# HELP alerts_generated_total Number of alerts generated.",
            "# TYPE alerts_generated_total counter",
            f"alerts_generated_total {self.total_alerts}",
            "# HELP auth_success_total Successful auth requests.",
            "# TYPE auth_success_total counter",
            f"auth_success_total {self.auth_success}",
            "# HELP auth_failures_total Failed auth requests.",
            "# TYPE auth_failures_total counter",
            f"auth_failures_total {self.auth_failures}",
            "# HELP websocket_clients Active websocket clients.",
            "# TYPE websocket_clients gauge",
            f"websocket_clients {self.ws_clients}",
            "# HELP sse_clients Active SSE clients.",
            "# TYPE sse_clients gauge",
            f"sse_clients {self.sse_clients}",
            "# HELP telemetry_queue_depth Pending queue depth.",
            "# TYPE telemetry_queue_depth gauge",
            f"telemetry_queue_depth {queue_depth}",
            "# HELP telemetry_buffer_drops_total Dropped buffered events.",
            "# TYPE telemetry_buffer_drops_total counter",
            f"telemetry_buffer_drops_total {self.buffer_drops}",
            "# HELP database_health Database connectivity flag.",
            "# TYPE database_health gauge",
            f"database_health {1 if db_ok else 0}",
        ]
        return "\n".join(lines) + "\n"
