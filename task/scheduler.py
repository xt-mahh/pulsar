"""Pulsar Cron 调度器 — 基于 asyncio 的定时任务管理"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger("pulsar.task.scheduler")


class CronJob:
    """Cron 定时任务"""

    def __init__(
        self,
        name: str,
        schedule: str,
        task_type: str,
        platform: str,
        params: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.schedule = schedule
        self.task_type = task_type
        self.platform = platform
        self.params = params or {}
        self.enabled = enabled
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.run_count: int = 0

    def __repr__(self) -> str:
        return (
            f"CronJob(name={self.name!r}, schedule={self.schedule!r}, "
            f"enabled={self.enabled})"
        )


class Scheduler:
    """Cron 调度器

    管理定时任务的生命周期，支持添加、移除、暂停、恢复任务。
    基于 asyncio 的事件循环实现定时触发。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, CronJob] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._on_trigger: Callable[[CronJob], Coroutine[Any, Any, None]] | None = None

    def set_trigger_handler(
        self, handler: Callable[[CronJob], Coroutine[Any, Any, None]]
    ) -> None:
        """设置任务触发时的回调处理器"""
        self._on_trigger = handler

    def add_job(self, job: CronJob) -> None:
        """添加定时任务"""
        self._jobs[job.name] = job
        logger.info("Added cron job: %s (schedule: %s)", job.name, job.schedule)

    def remove_job(self, name: str) -> bool:
        """移除定时任务"""
        if name in self._jobs:
            del self._jobs[name]
            logger.info("Removed cron job: %s", name)
            return True
        return False

    def get_job(self, name: str) -> CronJob | None:
        """获取定时任务"""
        return self._jobs.get(name)

    def list_jobs(self, status: str = "all") -> list[dict[str, Any]]:
        """列出定时任务"""
        result = []
        for job in self._jobs.values():
            if status == "active" and not job.enabled:
                continue
            if status == "paused" and job.enabled:
                continue
            result.append({
                "name": job.name,
                "schedule": job.schedule,
                "task_type": job.task_type,
                "platform": job.platform,
                "enabled": job.enabled,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "run_count": job.run_count,
            })
        return result

    def pause_job(self, name: str) -> bool:
        """暂停定时任务"""
        job = self._jobs.get(name)
        if job:
            job.enabled = False
            logger.info("Paused cron job: %s", name)
            return True
        return False

    def resume_job(self, name: str) -> bool:
        """恢复定时任务"""
        job = self._jobs.get(name)
        if job:
            job.enabled = True
            logger.info("Resumed cron job: %s", name)
            return True
        return False

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")

    async def _run_loop(self) -> None:
        """调度器主循环

        每 60 秒检查一次是否有任务需要触发。
        Phase 1 实现简单的轮询调度，后续可优化为精确 Cron 表达式解析。
        """
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                current_hour = now.hour
                current_minute = now.minute

                for job in self._jobs.values():
                    if not job.enabled:
                        continue

                    # 简单 Cron 解析：仅支持 "分 时 * * *" 格式
                    if self._should_trigger(job.schedule, current_hour, current_minute):
                        if self._on_trigger:
                            job.last_run = now
                            job.run_count += 1
                            logger.info(
                                "Triggering cron job: %s (run #%d)",
                                job.name,
                                job.run_count,
                            )
                            asyncio.create_task(self._on_trigger(job))

                # 每 60 秒检查一次
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error: %s", str(e))
                await asyncio.sleep(60)

    @staticmethod
    def _should_trigger(schedule: str, hour: int, minute: int) -> bool:
        """检查当前时间是否匹配 Cron 表达式

        支持格式：分 时 * * *
        示例："0 17 * * *" → 每天 17:00
        """
        parts = schedule.strip().split()
        if len(parts) < 2:
            return False

        try:
            cron_minute = parts[0]
            cron_hour = parts[1]

            minute_match = cron_minute == "*" or int(cron_minute) == minute
            hour_match = cron_hour == "*" or int(cron_hour) == hour

            return minute_match and hour_match
        except (ValueError, IndexError):
            return False