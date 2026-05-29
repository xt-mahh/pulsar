"""Health checker — tracks agent component status and exposes health reports."""

from __future__ import annotations

import time
import logging
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    INIT = "init"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    RESTARTING = "restarting"


@dataclass
class ComponentHealth:
    """Health snapshot for a single component/agent."""
    status: AgentStatus = AgentStatus.INIT
    last_heartbeat: float = 0.0
    uptime: float = 0.0
    error: str | None = None


class HealthChecker:
    """Monitors component health, records heartbeats, and produces aggregate reports.

    The runtime's heartbeat loop calls ``record_heartbeat()`` for each tracked
    component.  Components are automatically initialized on first contact.
    """

    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}
        self._start_time: float = time.time()
        self._total_calls: int = 0
        self._failed_calls: int = 0
        self._total_duration_ms: float = 0.0

    @property
    def start_time(self) -> float:
        return self._start_time

    # ── component tracking ────────────────────────────────────────────────

    def register(self, name: str) -> ComponentHealth:
        """Register a new component (idempotent)."""
        if name not in self._components:
            h = ComponentHealth(status=AgentStatus.INIT, last_heartbeat=time.time())
            self._components[name] = h
        return self._components[name]

    def record_heartbeat(self, name: str) -> ComponentHealth:
        """Record a heartbeat for *name*.  Auto-registers if absent."""
        h = self._components.get(name)
        if h is None:
            h = self.register(name)
        h.last_heartbeat = time.time()
        if h.status in (AgentStatus.INIT, AgentStatus.RESTARTING):
            h.status = AgentStatus.RUNNING
            h.uptime = 0.0
        return h

    def set_status(self, name: str, status: AgentStatus, error: str | None = None) -> None:
        h = self._components.get(name)
        if h is None:
            h = self.register(name)
        h.status = status
        if error is not None:
            h.error = error

    # ── metrics ───────────────────────────────────────────────────────────

    def record_call(self, duration_ms: float, success: bool = True) -> None:
        self._total_calls += 1
        self._total_duration_ms += duration_ms
        if not success:
            self._failed_calls += 1

    # ── pings ─────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Simplified ping for the runtime's own health."""
        return True

    # ── reports ───────────────────────────────────────────────────────────

    def get_health(self) -> dict:
        """Return a full health report dict."""
        now = time.time()
        uptime_s = now - self._start_time

        agents_report: dict[str, dict] = {}
        overall = AgentStatus.RUNNING
        for name, h in self._components.items():
            entry = {"status": h.status.value, "last_heartbeat": h.last_heartbeat}
            if h.uptime > 0:
                entry["uptime"] = h.uptime
            else:
                entry["uptime"] = now - h.last_heartbeat if h.last_heartbeat else 0.0
            if h.error:
                entry["error"] = h.error
            agents_report[name] = entry
            # Degraded is worse than running but better than stopped
            if h.status == AgentStatus.STOPPED:
                overall = AgentStatus.DEGRADED

        avg_duration = self._total_duration_ms / max(self._total_calls, 1)

        return {
            "status": overall.value,
            "uptime_seconds": uptime_s,
            "agents": agents_report,
            "metrics": {
                "total_calls": self._total_calls,
                "failed_calls": self._failed_calls,
                "avg_duration_ms": round(avg_duration, 2),
            },
        }

    def get_status_report(self) -> dict:
        """Lightweight system/status response (PIP protocol)."""
        h = self.get_health()
        return {
            "status": h["status"],
            "uptime_seconds": h["uptime_seconds"],
            "active_tasks": sum(
                1 for c in self._components.values() if c.status == AgentStatus.RUNNING
            ),
            "queue_depth": 0,
        }
