"""Pulsar 主运行时 — 系统 daemon 入口

负责：
- 加载配置
- 启动 MCP 消息总线
- 管理所有 Agent 子进程生命周期
- 健康检查与自动恢复
- 信号处理与优雅关闭
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any

from shared.models import AgentConfig, MCPRequest, MCPResponse
from shared.errors import ConfigError, LifecycleError
from runtime.config import load_config, watch_config
from runtime.mcp_bus import MCPBus
from runtime.lifecycle import AgentLifecycleManager
from runtime.health import HealthChecker
from runtime.logging import AuditLogger

logger = logging.getLogger("pulsar.runtime")


class PulsarRuntime:
    """Pulsar 系统主运行时

    用法:
        runtime = PulsarRuntime("config.yaml")
        await runtime.start()
        await runtime.run_forever()
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: dict[str, Any] = {}
        self.mcp_bus = MCPBus()
        self.lifecycle = AgentLifecycleManager(self.mcp_bus)
        self.health: HealthChecker | None = None
        self.audit: AuditLogger | None = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """启动运行时

        按顺序：
        1. 加载配置
        2. 初始化审计日志
        3. 注册系统 MCP 处理器
        4. 启动 MCP 消息总线
        5. 启动所有配置的 Agent
        6. 启动健康检查
        7. 启动配置热加载
        """
        logger.info("=" * 50)
        logger.info("Pulsar 运行时启动中...")
        logger.info("=" * 50)

        # 1. 加载配置
        try:
            self.config = load_config(self.config_path)
        except ConfigError as e:
            logger.error(f"配置加载失败: {e}")
            sys.exit(1)

        system_config = self.config.get("system", {})
        logger.info(f"系统: {system_config.get('name', 'Pulsar')} v{system_config.get('version', '0.1.0')}")

        # 2. 初始化审计日志
        audit_config = self.config.get("audit", {})
        self.audit = AuditLogger(audit_config)
        logger.info(f"审计日志: {'已启用' if audit_config.get('enabled', True) else '已禁用'}")

        # 3. 注册系统 MCP 处理器
        self._register_system_handlers()

        # 4. 启动 MCP 消息总线
        asyncio.create_task(self.mcp_bus.listen())
        logger.info("MCP 消息总线已启动")

        # 5. 启动所有配置的 Agent
        await self._start_agents()

        # 6. 启动健康检查
        runtime_config = self.config.get("runtime", {})
        check_interval = runtime_config.get("heartbeat_interval", 15)
        self.health = HealthChecker(self.lifecycle, check_interval=check_interval)
        await self.health.start_monitoring()

        # 7. 启动配置热加载
        watch_config(self.config_path, callback=self._on_config_reload)

        self._running = True
        logger.info("Pulsar 运行时启动完成")
        self._log_audit("system_event", "runtime", "start", {"config": self.config_path})

    async def shutdown(self, grace_period: int = 30) -> None:
        """优雅关闭运行时

        Args:
            grace_period: 优雅关闭等待秒数
        """
        if not self._running:
            return

        logger.info(f"开始优雅关闭 (超时: {grace_period}s)")
        self._running = False

        # 停止健康检查
        if self.health:
            await self.health.stop_monitoring()

        # 关闭所有 Agent
        await self.lifecycle.drain_all(timeout=grace_period)

        # 关闭 MCP 总线
        await self.mcp_bus.close()

        # 关闭审计日志
        if self.audit:
            self.audit.close()

        self._shutdown_event.set()
        logger.info("Pulsar 运行时已关闭")
        self._log_audit("system_event", "runtime", "shutdown", {})

    async def run_forever(self) -> None:
        """保持运行直到收到关闭信号"""
        # 注册信号处理器
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self.shutdown()),
                )
            except NotImplementedError:
                # Windows 不支持 add_signal_handler
                pass

        # Windows 信号处理
        if sys.platform == "win32":
            try:
                import signal as win_signal
                win_signal.signal(win_signal.SIGTERM, lambda *_: asyncio.create_task(self.shutdown()))
                win_signal.signal(win_signal.SIGINT, lambda *_: asyncio.create_task(self.shutdown()))
            except (AttributeError, ValueError):
                pass

        logger.info("Pulsar 运行中 (按 Ctrl+C 停止)")
        await self._shutdown_event.wait()

    def get_status(self) -> dict[str, Any]:
        """获取系统运行状态"""
        agent_status = self.lifecycle.get_status() if self.lifecycle else {}
        health_summary = self.health.get_health_summary() if self.health else {}

        return {
            "running": self._running,
            "config_path": self.config_path,
            "agents": agent_status,
            "health": health_summary,
            "version": self.config.get("system", {}).get("version", "0.1.0"),
        }

    def _register_system_handlers(self) -> None:
        """注册系统级 MCP 方法处理器"""
        # system/ping — 心跳检测
        async def handle_ping(request: MCPRequest) -> MCPResponse:
            return MCPResponse(
                id=request.id,
                result={"pong": True, "timestamp": asyncio.get_event_loop().time()},
            )

        # system/status — 系统状态查询
        async def handle_status(request: MCPRequest) -> MCPResponse:
            return MCPResponse(
                id=request.id,
                result=self.get_status(),
            )

        # system/shutdown — 关闭系统
        async def handle_shutdown(request: MCPRequest) -> MCPResponse:
            asyncio.create_task(self.shutdown())
            return MCPResponse(
                id=request.id,
                result={"message": "正在关闭..."},
            )

        self.mcp_bus.register_handler("system/ping", handle_ping)
        self.mcp_bus.register_handler("system/status", handle_status)
        self.mcp_bus.register_handler("system/shutdown", handle_shutdown)

        logger.debug("系统 MCP 处理器已注册")

    async def _start_agents(self) -> None:
        """启动所有配置的 Agent"""
        # 从配置中读取 Agent 列表
        # Phase 1 支持：gateway, adapter.wechat
        agent_configs = []

        # LLM Gateway
        gateway_config = self.config.get("gateway", {})
        if gateway_config.get("enabled", True):
            agent_configs.append(AgentConfig(
                name="gateway",
                layer=1,
                type="gateway",
                enabled=True,
                config=gateway_config,
            ))

        # 平台适配器
        adapters_config = self.config.get("adapters", {})
        for adapter_name, adapter_cfg in adapters_config.items():
            if adapter_cfg.get("enabled", True):
                agent_configs.append(AgentConfig(
                    name=f"adapter.{adapter_name}",
                    layer=4,
                    type="adapter",
                    enabled=True,
                    config=adapter_cfg,
                ))

        # 启动每个 Agent
        for agent_config in agent_configs:
            try:
                await self.lifecycle.start_agent(agent_config)
            except LifecycleError as e:
                logger.error(f"启动 Agent {agent_config.name} 失败: {e}")

        logger.info(f"已启动 {len(self.lifecycle._agents)} 个 Agent")

    def _on_config_reload(self, new_config: dict[str, Any]) -> None:
        """配置热加载回调"""
        logger.info("检测到配置变更，重新加载...")
        old_config = self.config
        self.config = new_config

        # 更新审计日志配置
        audit_config = new_config.get("audit", {})
        if self.audit:
            self.audit.enabled = audit_config.get("enabled", True)

        self._log_audit("system_event", "runtime", "config_reload", {
            "changes": self._diff_config(old_config, new_config),
        })
        logger.info("配置已热加载")

    def _log_audit(self, event_type: str, agent: str, action: str, params: dict) -> None:
        """记录审计日志的快捷方法"""
        if self.audit:
            self.audit.log(
                event_type=event_type,
                agent=agent,
                action=action,
                params=params,
            )

    @staticmethod
    def _diff_config(old: dict, new: dict) -> list[str]:
        """比较配置差异（简化版）"""
        changes = []
        for key in set(list(old.keys()) + list(new.keys())):
            if key not in old:
                changes.append(f"+{key}")
            elif key not in new:
                changes.append(f"-{key}")
            elif old[key] != new[key]:
                changes.append(f"~{key}")
        return changes