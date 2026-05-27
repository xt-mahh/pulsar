import asyncio
import re
from datetime import datetime, timezone
from typing import Callable, Coroutine
from shared.models import Task
from task.queue import TaskQueue


class CronScheduler:
    def __init__(self, task_queue: TaskQueue, config: dict = None):
        self.task_queue = task_queue
        self.config = config or {}
        self._jobs: list[dict] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def _parse_cron(self, expr: str) -> tuple:
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expr}")
        return tuple(
            self._parse_field(p, i) for i, p in enumerate(parts)
        )

    def _parse_field(self, field: str, position: int) -> set[int]:
        ranges = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
        lo, hi = ranges[position]

        if field == "*":
            return set(range(lo, hi + 1))

        result = set()
        for part in field.split(","):
            if "/" in part:
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    base_range = range(lo, hi + 1, step)
                else:
                    start, end = base.split("-")
                    base_range = range(int(start), int(end) + 1, step)
                result.update(base_range)
            elif "-" in part:
                start, end = part.split("-")
                result.update(range(int(start), int(end) + 1))
            else:
                result.add(int(part))
        return result

    def _matches(self, cron_fields: tuple, dt: datetime) -> bool:
        minute, hour, day, month, weekday = cron_fields
        return (
            dt.minute in minute
            and dt.hour in hour
            and dt.day in day
            and dt.month in month
            and dt.weekday() in weekday
        )

    def load_jobs(self, jobs_config: list[dict]):
        self._jobs = []
        for job in jobs_config:
            self._jobs.append({
                "name": job.get("name", "unnamed"),
                "schedule": job.get("schedule", "0 0 * * *"),
                "task": job.get("task", {}),
                "cron_fields": self._parse_cron(job.get("schedule", "0 0 * * *")),
            })

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        last_check = None
        while self._running:
            now = datetime.now()
            check_key = (now.minute, now.hour, now.day, now.month)
            if check_key != last_check:
                last_check = check_key
                for job in self._jobs:
                    if self._matches(job["cron_fields"], now):
                        task = Task(
                            type=job["task"].get("type", "unknown"),
                            input=job["task"],
                        )
                        await self.task_queue.enqueue(task)
            await asyncio.sleep(30)