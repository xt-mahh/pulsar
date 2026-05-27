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
from execution.tools.registry import registry as tool_registry
from execution.tools.builtins.http import http_request
from execution.tools.builtins.fileio import file_read, file_write, json_parse
from execution.tools.builtins.image import image_process
from execution.tools.builtins.template import template_render


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
        self._wechat_adapter = None

    async def start(self):
        self.logger.log_system_event("runtime", "start", {"config_path": self.config_path})
        self._register_builtin_tools()
        await self._init_wechat_adapter()

        agent_configs = [
            AgentConfig(name="gateway", layer=1, type="gateway"),
            AgentConfig(name="adapter.wechat", layer=4, type="adapter"),
            AgentConfig(name="tools", layer=4, type="tool"),
            AgentConfig(name="cli", layer=5, type="runtime"),
        ]
        for ac in agent_configs:
            await self.lifecycle.start_agent(ac)
            self.health.register_agent(ac.name)

        self.lifecycle.start_health_checks()
        self.logger.log_system_event("runtime", "started", {"agents": self.lifecycle.get_all_status()})

        self._shutdown_event.clear()

        try:
            asyncio.create_task(self._config_watch_loop())
            await self.mcp_bus.listen()
        except asyncio.CancelledError:
            pass

    def _register_builtin_tools(self):
        tool_registry.register(http_request)
        tool_registry.register(file_read)
        tool_registry.register(file_write)
        tool_registry.register(json_parse)
        tool_registry.register(image_process)
        tool_registry.register(template_render)

    async def _init_wechat_adapter(self):
        wechat_cfg = self.config.adapters.get("wechat", {})
        if wechat_cfg.get("enabled", True):
            from execution.adapters.wechat.tools import _init_tm
            _init_tm(
                app_id=wechat_cfg.get("app_id", ""),
                app_secret=wechat_cfg.get("app_secret", ""),
                api_base=wechat_cfg.get("api_base", "https://api.weixin.qq.com"),
                cache_ttl=wechat_cfg.get("token_cache_ttl", 7200),
            )

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