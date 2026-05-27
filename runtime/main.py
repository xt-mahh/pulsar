import asyncio
import signal
from pathlib import Path

from runtime.config import ConfigWatcher
from runtime.mcp_bus import MCPBus
from runtime.lifecycle import AgentLifecycleManager
from runtime.health import HealthChecker
from runtime.logging import AuditLogger
from shared.models import PulsarConfig, AgentConfig
from shared.constants import DEFAULT_DRAIN_TIMEOUT


class PulsarRuntime:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config_watcher = ConfigWatcher(config_path)
        self.config: PulsarConfig = self.config_watcher.get_config()
        self.mcp_bus = MCPBus()
        self.lifecycle = AgentLifecycleManager(self.mcp_bus)
        self.health = HealthChecker()
        self.logger = AuditLogger(self.config.audit)
        self._shutdown_event = asyncio.Event()

    async def start(self):
        self.logger.log_system_event("runtime", "start", {"config_path": self.config_path})

        agent_configs = [
            AgentConfig(name="gateway", layer=1, type="gateway"),
            AgentConfig(name="adapter.wechat", layer=4, type="adapter"),
            AgentConfig(name="tools", layer=4, type="tool"),
            AgentConfig(name="cli", layer=5, type="runtime"),
        ]

        for ac in agent_configs:
            if self.config.adapters.get("wechat", {}).get("enabled", True):
                await self.lifecycle.start_agent(ac)
                self.health.register_agent(ac.name)

        self.lifecycle.start_health_checks()
        self.logger.log_system_event("runtime", "started", {"agents": self.lifecycle.get_all_status()})

        self._shutdown_event.clear()

        try:
            config_check_task = asyncio.create_task(self._config_watch_loop())
            await self.mcp_bus.listen()
        except asyncio.CancelledError:
            pass

    async def _config_watch_loop(self):
        while not self._shutdown_event.is_set():
            await asyncio.sleep(30)
            if self.config_watcher.check_reload():
                self.config = self.config_watcher.get_config()
                self.logger.log_system_event("runtime", "config_reloaded")

    async def shutdown(self, grace_period: int = DEFAULT_DRAIN_TIMEOUT):
        self.logger.log_system_event("runtime", "shutdown", {"grace_period": grace_period})
        self._shutdown_event.set()
        await self.lifecycle.drain_all(timeout=grace_period)
        await self.mcp_bus.close()
        self.logger.log_system_event("runtime", "shutdown_complete")

    def get_status(self) -> dict:
        return {
            "system": {
                "name": "Pulsar",
                "version": "0.1.0",
                "status": "running",
            },
            "agents": self.lifecycle.get_all_status(),
            "health": self.health.get_all_status(),
            "config": self.config.model_dump(),
        }


_runtime: PulsarRuntime | None = None


def run(config_path: str = "config.yaml"):
    global _runtime
    _runtime = PulsarRuntime(config_path)
    asyncio.run(_async_run())


async def _async_run():
    global _runtime
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_runtime.shutdown()))
        except NotImplementedError:
            pass

    await _runtime.start()


def get_runtime() -> PulsarRuntime | None:
    return _runtime