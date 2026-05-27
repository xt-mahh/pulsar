import asyncio
import signal
from datetime import datetime, timezone
from shared.models import AgentConfig
from shared.constants import (
    DEFAULT_HEARTBEAT_INTERVAL, DEFAULT_MAX_RESTART_ATTEMPTS,
    DEFAULT_RESTART_DELAY, DEFAULT_DRAIN_TIMEOUT,
)
from runtime.mcp_bus import MCPBus


class AgentProcess:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.status: str = "stopped"
        self.restart_count: int = 0
        self.last_heartbeat: datetime | None = None
        self.consecutive_missed_heartbeats: int = 0


class AgentLifecycleManager:
    def __init__(self, mcp_bus: MCPBus):
        self.mcp_bus = mcp_bus
        self._agents: dict[str, AgentProcess] = {}
        self._heartbeat_task: asyncio.Task | None = None

    async def start_agent(self, config: AgentConfig) -> AgentProcess:
        proc = AgentProcess(config)
        self._agents[config.name] = proc
        proc.status = "starting"

        module_path = f"runtime.agents.{config.type}_{config.name}"
        entry_point = f"python -m {module_path}"

        try:
            proc.process = await asyncio.create_subprocess_shell(
                entry_point,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            reader = asyncio.StreamReader(proc.process.stdout)
            writer = asyncio.StreamWriter(proc.process.stdin, None, None, None)
            self.mcp_bus.register_agent(config.name, reader, writer)
            proc.status = "running"
            proc.restart_count = 0
        except Exception as e:
            proc.status = "failed"
        return proc

    async def stop_agent(self, name: str):
        proc = self._agents.get(name)
        if not proc:
            return
        proc.status = "stopping"
        self.mcp_bus.unregister_agent(name)
        if proc.process and proc.process.returncode is None:
            proc.process.terminate()
            try:
                await asyncio.wait_for(proc.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.process.kill()
        proc.status = "stopped"

    async def drain_all(self, timeout: int = DEFAULT_DRAIN_TIMEOUT):
        for name in list(self._agents.keys()):
            await self.stop_agent(name)

    async def restart_agent(self, name: str):
        config = self._agents[name].config if name in self._agents else None
        if not config:
            return
        await self.stop_agent(name)
        await asyncio.sleep(DEFAULT_RESTART_DELAY)
        await self.start_agent(config)

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(DEFAULT_HEARTBEAT_INTERVAL)
            for name, proc in list(self._agents.items()):
                if proc.status != "running":
                    continue
                if proc.consecutive_missed_heartbeats >= 3:
                    if proc.restart_count < DEFAULT_MAX_RESTART_ATTEMPTS:
                        proc.restart_count += 1
                        await self.restart_agent(name)
                    else:
                        proc.status = "crashed"

    def start_health_checks(self):
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._health_check_loop())

    def get_agent_status(self, name: str) -> dict | None:
        proc = self._agents.get(name)
        if not proc:
            return None
        return {
            "name": proc.config.name,
            "layer": proc.config.layer,
            "type": proc.config.type,
            "status": proc.status,
            "enabled": proc.config.enabled,
            "restart_count": proc.restart_count,
            "last_heartbeat": proc.last_heartbeat.isoformat() if proc.last_heartbeat else None,
        }

    def get_all_status(self) -> list[dict]:
        return [
            self.get_agent_status(name)
            for name in sorted(self._agents.keys())
        ]

    def record_heartbeat(self, name: str):
        proc = self._agents.get(name)
        if proc:
            proc.last_heartbeat = datetime.now(timezone.utc)
            proc.consecutive_missed_heartbeats = 0