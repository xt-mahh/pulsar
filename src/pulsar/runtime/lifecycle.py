"""Agent lifecycle manager — subprocess start/stop/restart with heartbeat monitoring."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Callable, Awaitable

from pulsar.runtime.health import HealthChecker, AgentStatus

logger = logging.getLogger(__name__)


class ManagedAgent:
    """Tracks a single managed agent process."""

    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd = Path(cwd) if cwd else None
        self.env = env
        self.process: asyncio.subprocess.Process | None = None
        self.heartbeat_misses: int = 0
        self._restart_count: int = 0


class AgentLifecycleManager:
    """Manages subprocess agent lifecycle: start, stop, restart, heartbeat monitoring.

    Heartbeat interval: 15 seconds.  After 3 consecutive misses the agent
    is automatically restarted.
    """

    HEARTBEAT_INTERVAL = 15
    MAX_MISSES = 3

    def __init__(
        self,
        health_checker: HealthChecker,
        pip_bus: "PIPBus",  # noqa: F821 — deferred
        on_restart: Callable[[ManagedAgent], Awaitable[None]] | None = None,
    ) -> None:
        self._health = health_checker
        self._pip_bus = pip_bus
        self._on_restart = on_restart
        self._agents: dict[str, ManagedAgent] = {}
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

    # ── registration ──────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        command: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ManagedAgent:
        """Register an agent for lifecycle management."""
        agent = ManagedAgent(name=name, command=command, cwd=cwd, env=env)
        self._agents[name] = agent
        self._health.register(name)
        return agent

    def get(self, name: str) -> ManagedAgent | None:
        return self._agents.get(name)

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all registered agents."""
        self._running = True
        tasks = [self._start_one(agent) for agent in self._agents.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self, name: str) -> None:
        """Start a specific agent by name."""
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"Unknown agent: {name}")
        await self._start_one(agent)

    async def stop_all(self, grace_period: int = 15) -> None:
        """Gracefully stop all agents."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        tasks = [self._stop_one(agent, grace_period) for agent in self._agents.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self, name: str, grace_period: int = 15) -> None:
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"Unknown agent: {name}")
        await self._stop_one(agent, grace_period)

    async def restart(self, name: str, grace_period: int = 5) -> None:
        """Restart a specific agent (stop + start)."""
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"Unknown agent: {name}")

        self._health.set_status(name, AgentStatus.RESTARTING)
        await self._stop_one(agent, grace_period)
        await self._start_one(agent)
        logger.info("Agent %s restarted (attempt %d)", name, agent._restart_count)

    # ── heartbeat monitoring ──────────────────────────────────────────────

    async def start_heartbeat_monitor(self) -> None:
        """Start the background heartbeat monitoring loop."""
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Check all agents every HEARTBEAT_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            for name, agent in list(self._agents.items()):
                try:
                    healthy = await self._check_agent_health(name, agent)
                except Exception:
                    logger.exception("Health check failed for %s", name)
                    healthy = False

                if healthy:
                    agent.heartbeat_misses = 0
                else:
                    agent.heartbeat_misses += 1
                    logger.warning(
                        "Agent %s heartbeat miss %d/%d",
                        name, agent.heartbeat_misses, self.MAX_MISSES,
                    )
                    if agent.heartbeat_misses >= self.MAX_MISSES:
                        logger.error("Agent %s unreachable — auto-restarting", name)
                        try:
                            if self._on_restart:
                                await self._on_restart(agent)
                            await self.restart(name)
                        except Exception:
                            logger.exception("Auto-restart failed for %s", name)

    async def _check_agent_health(self, name: str, agent: ManagedAgent) -> bool:
        """Ping an agent via PIPBus."""
        if agent.process is None or agent.process.returncode is not None:
            return False

        try:
            result = await self._pip_bus.ping(timeout=5.0)
            if result:
                self._health.record_heartbeat(name)
            return result
        except Exception:
            return False

    # ── internals ─────────────────────────────────────────────────────────

    async def _start_one(self, agent: ManagedAgent) -> None:
        """Launch a subprocess for *agent* and connect stdio PIP transport."""
        if agent.process is not None and agent.process.returncode is None:
            logger.debug("Agent %s already running", agent.name)
            return

        logger.info("Starting agent %s: %s", agent.name, " ".join(agent.command))

        kwargs: dict = {}
        if agent.cwd:
            kwargs["cwd"] = str(agent.cwd)
        if agent.env:
            kwargs["env"] = {**__import__("os").environ, **agent.env}

        agent.process = await asyncio.create_subprocess_exec(
            *agent.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )

        # Connect PIP transport over stdio
        if agent.process.stdin and agent.process.stdout:
            transport = self._pip_bus.bind_stdio(
                reader=agent.process.stdout,
                writer=agent.process.stdin,
            )
            await self._pip_bus.start()

        self._health.set_status(agent.name, AgentStatus.RUNNING)
        agent.heartbeat_misses = 0
        agent._restart_count += 1

    async def _stop_one(self, agent: ManagedAgent, grace_period: int = 15) -> None:
        """Gracefully stop an agent process."""
        if agent.process is None or agent.process.returncode is not None:
            self._health.set_status(agent.name, AgentStatus.STOPPED)
            return

        logger.info("Stopping agent %s (grace=%ds)", agent.name, grace_period)
        self._health.set_status(agent.name, AgentStatus.STOPPED)

        try:
            agent.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(agent.process.wait(), timeout=grace_period)
            except asyncio.TimeoutError:
                logger.warning("Agent %s did not respond to SIGTERM, sending SIGKILL", agent.name)
                agent.process.send_signal(signal.SIGKILL)
                await agent.process.wait()
        except ProcessLookupError:
            pass  # already dead

        agent.process = None
