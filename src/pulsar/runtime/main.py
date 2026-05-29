"""PulsarRuntime — main asyncio entry point that coordinates all runtime subsystems."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from pulsar.runtime.config import ConfigManager, PulsarConfig
from pulsar.runtime.pip_bus import PIPBus
from pulsar.runtime.lifecycle import AgentLifecycleManager, ManagedAgent
from pulsar.runtime.logging import AuditLogger
from pulsar.runtime.health import HealthChecker, AgentStatus

logger = logging.getLogger(__name__)


class PulsarRuntime:
    """Main asyncio entry point for the Pulsar Agent runtime.

    Orchestrates:
    - Config loading and hot-reload
    - PIPBus (inter-component messaging)
    - Agent lifecycle (subprocess management + heartbeat monitoring)
    - Audit logging
    - Health checking
    - Graceful shutdown with drain + timeout
    """

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self._config_path = Path(config_path)
        self._config_manager: ConfigManager | None = None
        self._pip_bus: PIPBus | None = None
        self._lifecycle: AgentLifecycleManager | None = None
        self._audit_logger: AuditLogger | None = None
        self._health: HealthChecker | None = None

        self._running = False
        self._start_time: float = 0.0
        self._shutdown_task: asyncio.Task | None = None

    # ── properties ────────────────────────────────────────────────────────

    @property
    def config(self) -> PulsarConfig:
        if self._config_manager is None:
            raise RuntimeError("Runtime not started")
        return self._config_manager.config

    @property
    def pip_bus(self) -> PIPBus:
        if self._pip_bus is None:
            raise RuntimeError("Runtime not started")
        return self._pip_bus

    @property
    def lifecycle(self) -> AgentLifecycleManager:
        if self._lifecycle is None:
            raise RuntimeError("Runtime not started")
        return self._lifecycle

    @property
    def audit(self) -> AuditLogger:
        if self._audit_logger is None:
            raise RuntimeError("Runtime not started")
        return self._audit_logger

    @property
    def health(self) -> HealthChecker:
        if self._health is None:
            raise RuntimeError("Runtime not started")
        return self._health

    @property
    def uptime_seconds(self) -> float:
        if self._start_time == 0:
            return 0.0
        import time
        return time.time() - self._start_time

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize all subsystems and start the main event loop."""
        logger.info("PulsarRuntime starting…")
        self._start_time = __import__("time").time()

        # 1. Load config
        self._config_manager = ConfigManager(
            config_path=self._config_path,
            auto_reload=True,
            reload_callback=self._on_config_reload,
        )
        cfg = self._config_manager.load()

        # 2. Setup logging
        logging.basicConfig(
            level=getattr(logging, cfg.system.env.upper() if cfg.system.env.upper() in ("DEBUG", "INFO", "WARNING", "ERROR") else "INFO"),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        # 3. Create subsystems
        self._health = HealthChecker()
        self._pip_bus = PIPBus()
        self._lifecycle = AgentLifecycleManager(
            health_checker=self._health,
            pip_bus=self._pip_bus,
            on_restart=self._on_agent_restart,
        )

        # 4. Audit logger
        audit_cfg = {
            "enabled": cfg.audit.enabled,
            "file_path": cfg.audit.file_path,
            "max_file_size_mb": cfg.audit.max_file_size_mb,
            "max_backups": cfg.audit.max_backups,
            "max_age_days": cfg.audit.max_age_days,
            "compress": cfg.audit.compress,
            "format": cfg.audit.format,
            "filter_operations": cfg.audit.filter_operations,
            "redact_fields": {
                "enabled": cfg.audit.redact_fields.enabled,
                "fields": cfg.audit.redact_fields.fields,
                "mask": cfg.audit.redact_fields.mask,
            },
        }
        self._audit_logger = AuditLogger(audit_cfg)
        self._audit_logger.open()

        # 5. Register runtime health
        self._health.register("runtime")
        self._health.record_heartbeat("runtime")

        # 6. Start PIPBus
        await self._pip_bus.start()

        # 7. Register PIP handlers for runtime
        self._pip_bus.register("system/ping", self._handle_ping)
        self._pip_bus.register("system/status", self._handle_status)

        # 8. Start lifecycle heartbeat monitor
        await self._lifecycle.start_heartbeat_monitor()

        # 9. Start config watcher
        asyncio.create_task(self._config_manager.watch())

        # 10. Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        self._running = True
        self._audit_logger.log_event("agent.start", {"agent": "runtime", "action": "start"})
        logger.info(
            "PulsarRuntime started (name=%s, env=%s, debug=%s)",
            cfg.system.name, cfg.system.env, cfg.system.debug,
        )

    async def shutdown(self, grace_period: int = 30) -> None:
        """Graceful shutdown with drain logic.

        Steps:
        1. Stop accepting new requests
        2. Notify agents of draining
        3. Wait for in-flight tasks (up to grace_period)
        4. Force-kill remaining agents
        5. Close subsystems
        """
        if not self._running:
            return

        logger.info("PulsarRuntime shutting down (grace=%ds)…", grace_period)
        self._running = False

        self._audit_logger.log_event("system.shutdown", {"action": "shutdown", "grace_period": grace_period})

        # Drain phase: wait briefly for in-flight work
        drain_deadline = __import__("time").time() + min(grace_period // 2, 10)
        await self._drain(drain_deadline)

        # Stop agents
        if self._lifecycle:
            await self._lifecycle.stop_all(grace_period=grace_period)

        # Stop PIPBus
        if self._pip_bus:
            await self._pip_bus.stop()

        # Close audit
        if self._audit_logger:
            self._audit_logger.close()

        # Stop config watcher
        if self._config_manager:
            self._config_manager.stop_watch()

        logger.info("PulsarRuntime shutdown complete")

    # ── agent access ──────────────────────────────────────────────────────

    def get_agent(self, name: str) -> ManagedAgent | None:
        """Get a managed agent by name."""
        if self._lifecycle:
            return self._lifecycle.get(name)
        return None

    # ── config reload ─────────────────────────────────────────────────────

    async def reload_config(self) -> None:
        """Trigger a config hot-reload."""
        if self._config_manager:
            self._config_manager.reload()

    def _on_config_reload(self, cfg: PulsarConfig) -> None:
        """Callback invoked when config is hot-reloaded."""
        logger.info("Config hot-reloaded")
        if self._audit_logger:
            self._audit_logger.log_event("config.reload", {"action": "reload", "status": "success"})

    async def _on_agent_restart(self, agent: ManagedAgent) -> None:
        """Callback when an agent is auto-restarted by the heartbeat monitor."""
        if self._audit_logger:
            self._audit_logger.log_event(
                "agent.restart",
                {"agent": agent.name, "action": "restart", "reason": "heartbeat_miss"},
            )

    # ── PIP handlers ──────────────────────────────────────────────────────

    async def _handle_ping(self, params: dict[str, Any]) -> dict[str, Any]:
        from datetime import datetime, timezone
        return {"pong": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    async def _handle_status(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._health:
            return self._health.get_status_report()
        return {"status": "initializing"}

    # ── drain ─────────────────────────────────────────────────────────────

    async def _drain(self, deadline: float) -> None:
        """Wait for in-flight requests to complete, up to *deadline*."""
        remaining = deadline - __import__("time").time()
        if remaining <= 0:
            return
        logger.debug("Draining in-flight tasks (%.1fs remaining)…", remaining)
        await asyncio.sleep(min(remaining, 5.0))

    # ── signal handling ───────────────────────────────────────────────────

    def _register_signal_handlers(self) -> None:
        """Register asyncio-compatible signal handlers for SIGINT/SIGTERM."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._handle_signal(s)),
                )
            except NotImplementedError:
                # Windows or non-UNIX: signal handlers not supported
                logger.warning("Signal handler not supported for %s", sig)

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle termination signals."""
        logger.info("Received signal %s, initiating shutdown", sig.name)
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self.shutdown())
