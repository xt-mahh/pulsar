"""Agent 生命周期管理 — 进程启停、心跳监控、故障恢复"""

import asyncio
import logging
import signal
from typing import Any

from shared.models import AgentConfig, MCPRequest, MCPResponse
from shared.errors import LifecycleError
from runtime.mcp_bus import MCPBus

logger = logging.getLogger("pulsar.lifecycle")


class AgentProcess:
    """Agent 进程封装"""

    def __init__(self, config: AgentConfig, bus: MCPBus):
        self.config = config
        self.bus = bus
        self.process: asyncio.subprocess.Process | None = None
        self.healthy = False
        self.last_heartbeat: float = 0.0
        self.restart_count = 0

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None


class AgentLifecycleManager:
    """Agent 生命周期管理器

    负责 Agent 子进程的启动、停止、重启、健康监控。
    每个 Agent 作为独立子进程运行，通过 stdin/stdout 与主进程通信。
    """

    def __init__(self, bus: MCPBus):
        self.bus = bus
        self._agents: dict[str, AgentProcess] = {}
        self._running = False

    async def start_agent(self, config: AgentConfig) -> AgentProcess:
        """启动一个 Agent 进程

        Args:
            config: Agent 配置

        Returns:
            AgentProcess 实例

        Raises:
            LifecycleError: 启动失败
        """
        if config.name in self._agents:
            raise LifecycleError(f"Agent {config.name} 已存在")

        agent = AgentProcess(config, self.bus)
        self._agents[config.name] = agent

        try:
            # 根据 Agent 类型确定启动模块
            module_path = self._get_agent_module(config)

            agent.process = await asyncio.create_subprocess_exec(
                "python", "-m", module_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            agent.healthy = True
            agent.last_heartbeat = asyncio.get_event_loop().time()
            logger.info(f"Agent 启动成功: {config.name} (PID: {agent.process.pid})")

            # 启动 stdout/stderr 读取任务
            asyncio.create_task(self._read_stdout(agent))
            asyncio.create_task(self._read_stderr(agent))

            return agent

        except Exception as e:
            logger.error(f"Agent 启动失败: {config.name}: {e}")
            self._agents.pop(config.name, None)
            raise LifecycleError(f"启动 Agent {config.name} 失败: {e}") from e

    async def stop_agent(self, name: str) -> None:
        """停止一个 Agent 进程

        Args:
            name: Agent 名称
        """
        agent = self._agents.get(name)
        if not agent or not agent.process:
            logger.warning(f"Agent {name} 不存在或未运行")
            return

        try:
            # 发送 SIGTERM
            if agent.process.returncode is None:
                agent.process.terminate()
                try:
                    await asyncio.wait_for(agent.process.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    # 超时强制终止
                    agent.process.kill()
                    await agent.process.wait()

            agent.healthy = False
            logger.info(f"Agent 已停止: {name}")
        except Exception as e:
            logger.error(f"停止 Agent {name} 失败: {e}")
        finally:
            self._agents.pop(name, None)

    async def restart_agent(self, name: str) -> AgentProcess:
        """重启一个 Agent 进程

        Args:
            name: Agent 名称

        Returns:
            新的 AgentProcess 实例
        """
        agent = self._agents.get(name)
        if agent:
            config = agent.config
            await self.stop_agent(name)
        else:
            raise LifecycleError(f"Agent {name} 不存在")

        return await self.start_agent(config)

    async def drain_all(self, timeout: float = 30.0) -> None:
        """优雅关闭所有 Agent

        Args:
            timeout: 总超时秒数
        """
        logger.info(f"开始优雅关闭所有 Agent (超时: {timeout}s)")
        start_time = asyncio.get_event_loop().time()

        for name in list(self._agents.keys()):
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"关闭超时，强制终止剩余 Agent")
                break

            try:
                await asyncio.wait_for(
                    self.stop_agent(name),
                    timeout=max(5.0, timeout - elapsed),
                )
            except asyncio.TimeoutError:
                logger.warning(f"关闭 Agent {name} 超时")

        logger.info("所有 Agent 已关闭")

    def get_status(self) -> dict[str, Any]:
        """获取所有 Agent 状态

        Returns:
            {agent_name: {healthy, pid, uptime, ...}}
        """
        now = asyncio.get_event_loop().time()
        status = {}
        for name, agent in self._agents.items():
            status[name] = {
                "healthy": agent.healthy,
                "pid": agent.process.pid if agent.process else None,
                "running": agent.is_running,
                "restart_count": agent.restart_count,
                "last_heartbeat": agent.last_heartbeat,
                "uptime": now - agent.last_heartbeat if agent.last_heartbeat > 0 else 0,
            }
        return status

    def handle_heartbeat(self, agent_name: str) -> None:
        """处理 Agent 心跳

        Args:
            agent_name: Agent 名称
        """
        agent = self._agents.get(agent_name)
        if agent:
            agent.last_heartbeat = asyncio.get_event_loop().time()
            agent.healthy = True

    async def check_health(self) -> list[str]:
        """检查所有 Agent 健康状态

        Returns:
            不健康的 Agent 名称列表
        """
        unhealthy = []
        now = asyncio.get_event_loop().time()
        heartbeat_timeout = 45  # 3 次心跳间隔 (15s * 3)

        for name, agent in self._agents.items():
            if agent.is_running:
                if now - agent.last_heartbeat > heartbeat_timeout:
                    unhealthy.append(name)
                    agent.healthy = False
                    logger.warning(f"Agent 心跳超时: {name}")

        return unhealthy

    async def auto_recover(self, max_restarts: int = 3) -> None:
        """自动恢复不健康的 Agent

        Args:
            max_restarts: 最大重启次数
        """
        unhealthy = await self.check_health()
        for name in unhealthy:
            agent = self._agents.get(name)
            if agent and agent.restart_count < max_restarts:
                agent.restart_count += 1
                logger.info(f"自动重启 Agent: {name} (第 {agent.restart_count} 次)")
                try:
                    await self.restart_agent(name)
                except LifecycleError as e:
                    logger.error(f"自动重启 Agent {name} 失败: {e}")
            elif agent:
                logger.error(f"Agent {name} 重启次数已达上限 ({max_restarts})")

    def _get_agent_module(self, config: AgentConfig) -> str:
        """根据 Agent 类型获取启动模块路径"""
        type_map = {
            "runtime": "runtime.main",
            "adapter": f"execution.adapters.{config.name}",
            "tool": "execution.tools.registry",
            "gateway": "gateway.gateway",
        }
        return type_map.get(config.type, f"runtime.main")

    async def _read_stdout(self, agent: AgentProcess) -> None:
        """读取 Agent 标准输出"""
        try:
            while agent.process and agent.process.stdout:
                line = await agent.process.stdout.readline()
                if not line:
                    break
                logger.debug(f"[{agent.name}] {line.decode().strip()}")
        except Exception as e:
            logger.error(f"读取 Agent {agent.name} stdout 失败: {e}")

    async def _read_stderr(self, agent: AgentProcess) -> None:
        """读取 Agent 标准错误"""
        try:
            while agent.process and agent.process.stderr:
                line = await agent.process.stderr.readline()
                if not line:
                    break
                logger.warning(f"[{agent.name}] {line.decode().strip()}")
        except Exception as e:
            logger.error(f"读取 Agent {agent.name} stderr 失败: {e}")