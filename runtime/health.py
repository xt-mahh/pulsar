"""健康检查 — Agent 心跳监控与自动恢复"""

import asyncio
import logging
from typing import Any

from runtime.mcp_bus import MCPBus
from runtime.lifecycle import AgentLifecycleManager

logger = logging.getLogger("pulsar.health")


class HealthChecker:
    """健康检查器

    定期检查所有 Agent 的心跳状态，发现异常时触发自动恢复。
    心跳间隔 15 秒，连续 3 次无响应判定为不健康。
    """

    def __init__(self, lifecycle: AgentLifecycleManager, check_interval: int = 15):
        self.lifecycle = lifecycle
        self.check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None

    async def start_monitoring(self) -> None:
        """启动健康检查循环"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"健康检查已启动 (间隔: {self.check_interval}s)")

    async def stop_monitoring(self) -> None:
        """停止健康检查"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("健康检查已停止")

    async def _monitor_loop(self) -> None:
        """健康检查主循环"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.lifecycle.auto_recover()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")

    def get_health_summary(self) -> dict[str, Any]:
        """获取健康状态摘要

        Returns:
            {
                "healthy_agents": [...],
                "unhealthy_agents": [...],
                "total_agents": N,
                "healthy_count": N,
            }
        """
        status = self.lifecycle.get_status()
        healthy = [name for name, s in status.items() if s.get("healthy")]
        unhealthy = [name for name, s in status.items() if not s.get("healthy")]

        return {
            "healthy_agents": healthy,
            "unhealthy_agents": unhealthy,
            "total_agents": len(status),
            "healthy_count": len(healthy),
            "unhealthy_count": len(unhealthy),
        }