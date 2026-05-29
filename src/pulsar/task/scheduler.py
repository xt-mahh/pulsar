"""CronScheduler — async cron-based task scheduler using croniter.

Checks cron expressions every 60 seconds and submits matching jobs to the TaskQueue.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from croniter import croniter

logger = logging.getLogger(__name__)


@dataclass
class JobDefinition:
    """Definition of a scheduled job."""

    name: str                                  # Unique job name
    cron: str                                  # 5-field cron expression
    task_type: str                             # Task type identifier (handler)
    params: dict = field(default_factory=dict) # Parameters passed to handler
    enabled: bool = True                       # Whether the job is active
    max_attempts: int = 3                      # Max retry attempts
    backoff: str = "exponential"               # fixed | exponential


class CronScheduler:
    """Async cron scheduler.

    Checks all registered jobs every 60 seconds. When a job's cron expression
    matches the current minute, the job is submitted to the configured task queue.

    Usage:
        scheduler = CronScheduler(queue)
        scheduler.add_job(JobDefinition(name="daily_pub", cron="0 9 * * *", task_type="publish"))
        await scheduler.start()
        ...
        await scheduler.stop()
    """

    def __init__(
        self,
        submit_callback: Optional[Callable[[JobDefinition], Any]] = None,
        check_interval: int = 60,
    ):
        """
        Args:
            submit_callback: Async callable invoked when a job triggers.
                             Receives the JobDefinition as argument.
            check_interval: Seconds between scheduler ticks (default: 60).
        """
        self._jobs: dict[str, JobDefinition] = {}
        self._submit_callback = submit_callback
        self._check_interval = check_interval
        self._task: asyncio.Task | None = None
        self._running = False

    # ── Job management ──────────────────────────────────────────────

    def add_job(self, job: JobDefinition) -> None:
        """Register a new scheduled job.

        Raises:
            ValueError: If a job with the same name already exists.
        """
        if job.name in self._jobs:
            raise ValueError(f"Job '{job.name}' already registered")
        # Validate cron expression
        if not croniter.is_valid(job.cron):
            raise ValueError(f"Invalid cron expression: '{job.cron}'")
        self._jobs[job.name] = job
        logger.info("Scheduler: added job '%s' (cron=%s)", job.name, job.cron)

    def remove_job(self, name: str) -> None:
        """Remove a scheduled job."""
        self._jobs.pop(name, None)
        logger.info("Scheduler: removed job '%s'", name)

    def get_job(self, name: str) -> Optional[JobDefinition]:
        """Get a job definition by name."""
        return self._jobs.get(name)

    def list_jobs(self) -> list[JobDefinition]:
        """List all registered jobs."""
        return list(self._jobs.values())

    def enable_job(self, name: str) -> None:
        """Enable a job."""
        if name in self._jobs:
            self._jobs[name].enabled = True

    def disable_job(self, name: str) -> None:
        """Disable a job."""
        if name in self._jobs:
            self._jobs[name].enabled = False

    # ── Lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "CronScheduler started (check_interval=%ds, %d jobs)",
            self._check_interval,
            len(self._jobs),
        )

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("CronScheduler stopped")

    # ── Internal loop ───────────────────────────────────────────────

    async def _run_loop(self) -> None:
        """Main scheduler loop — runs indefinitely."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                triggered = []

                for job in self._jobs.values():
                    if not job.enabled:
                        continue
                    if self._cron_matches(job.cron, now):
                        triggered.append(job)

                for job in triggered:
                    logger.info("Scheduler: triggering job '%s'", job.name)
                    if self._submit_callback:
                        try:
                            if asyncio.iscoroutinefunction(self._submit_callback):
                                await self._submit_callback(job)
                            else:
                                self._submit_callback(job)
                        except Exception as e:
                            logger.error(
                                "Scheduler: submit callback failed for '%s': %s",
                                job.name,
                                e,
                            )

            except Exception as e:
                logger.error("Scheduler loop error: %s", e)

            await asyncio.sleep(self._check_interval)

    # ── Cron matching ───────────────────────────────────────────────

    @staticmethod
    def _cron_matches(cron: str, dt: datetime) -> bool:
        """Check if a cron expression matches the given datetime.

        Uses croniter's get_prev() to find the previous match. If the previous
        match is within the last `check_interval` seconds, this cron fires now.
        """
        try:
            base = croniter(cron, dt)
            prev_time = base.get_prev(datetime)
            # If the previous match is within the last 60 seconds, fire
            diff = (dt - prev_time).total_seconds()
            return 0 <= diff < 61
        except (ValueError, KeyError):
            return False
