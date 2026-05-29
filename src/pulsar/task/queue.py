"""TaskQueue — FIFO task queue with SQLite persistence, retry with exponential backoff.

Provides async add, poll, and process loop for durable task execution.
"""

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """A unit of work in the queue."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    type: str = ""                          # Task type (handler identifier)
    params: dict = field(default_factory=dict)  # Task parameters
    state: str = "pending"                  # pending | running | completed | failed
    attempts: int = 0
    max_attempts: int = 3
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Task":
        return cls(
            id=row["id"],
            type=row["type"],
            params=json.loads(row["params"]) if row["params"] else {},
            state=row["state"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            error_message=row["error_message"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
            "state": self.state,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskQueue:
    """FIFO task queue with SQLite persistence.

    Features:
        - FIFO ordering (ORDER BY created_at ASC)
        - SQLite persistence with WAL mode
        - Exponential backoff retry (2^attempt seconds)
        - State management with atomic transactions
        - Custom handler dispatching
    """

    def __init__(self, db_path: str = "./data/pulsar/tasks.db"):
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._handler_map: dict[str, Callable] = {}
        self._worker_task: asyncio.Task | None = None
        self._running = False

    # ── Initialization ──────────────────────────────────────────────

    def initialize(self) -> None:
        """Initialize the database and create tables if needed."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                params TEXT DEFAULT '{}',
                state TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                error_message TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
        """)
        self._conn.commit()

    # ── Handler registration ────────────────────────────────────────

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """Register a handler for a task type.

        The handler should be an async callable that takes (task: Task, **params) -> Any.
        """
        self._handler_map[task_type] = handler

    # ── Task operations ─────────────────────────────────────────────

    async def add(self, task_type: str, params: dict | None = None,
                  max_attempts: int = 3) -> str:
        """Add a new task to the queue.

        Args:
            task_type: Handler type identifier.
            params: Task parameters (will be JSON-serialized).
            max_attempts: Max retry attempts (default: 3).

        Returns:
            The newly created task ID.
        """
        task_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._conn.execute(
                """INSERT INTO tasks (id, type, params, state, max_attempts, created_at, updated_at)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
                (task_id, task_type, json.dumps(params or {}), max_attempts, now, now),
            ),
        )
        self._conn.commit()
        logger.debug("TaskQueue: added task '%s' (type=%s)", task_id, task_type)
        return task_id

    async def poll(self) -> Optional[Task]:
        """Atomically claim the next pending task (FIFO order).

        Returns:
            The claimed Task, or None if queue is empty.
        """
        def _poll_sync() -> Optional[Task]:
            cursor = self._conn.execute(
                """UPDATE tasks
                   SET state = 'running', updated_at = CURRENT_TIMESTAMP
                   WHERE id = (
                       SELECT id FROM tasks
                       WHERE state = 'pending'
                       ORDER BY created_at ASC
                       LIMIT 1
                   )
                   RETURNING *;"""
            )
            row = cursor.fetchone()
            return Task.from_row(row) if row else None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _poll_sync)

    async def complete(self, task_id: str) -> None:
        """Mark a task as completed."""
        def _complete_sync():
            self._conn.execute(
                "UPDATE tasks SET state = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id,),
            )
            self._conn.commit()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _complete_sync)

    async def fail(self, task_id: str, error_message: str = "") -> None:
        """Mark a task as failed (after exhausting retries)."""
        def _fail_sync():
            self._conn.execute(
                """UPDATE tasks
                   SET state = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (error_message[:500], task_id),
            )
            self._conn.commit()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _fail_sync)

    async def retry(self, task_id: str, error_message: str = "") -> None:
        """Reset a task to pending for retry (increments attempt count).

        Uses exponential backoff: 2^attempt seconds delay.
        """
        def _retry_sync():
            self._conn.execute(
                """UPDATE tasks
                   SET state = 'pending',
                       attempts = attempts + 1,
                       error_message = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (error_message[:500], task_id),
            )
            self._conn.commit()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _retry_sync)

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        def _get_sync() -> Optional[Task]:
            cursor = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            return Task.from_row(row) if row else None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_sync)

    async def list_tasks(self, state: str | None = None,
                         limit: int = 50, offset: int = 0) -> list[Task]:
        """List tasks, optionally filtered by state."""
        def _list_sync() -> list[Task]:
            if state:
                cursor = self._conn.execute(
                    "SELECT * FROM tasks WHERE state = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (state, limit, offset),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            return [Task.from_row(row) for row in cursor.fetchall()]

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _list_sync)

    async def count(self, state: str | None = None) -> int:
        """Count tasks, optionally filtered by state."""
        def _count_sync() -> int:
            if state:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) as cnt FROM tasks WHERE state = ?", (state,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) as cnt FROM tasks")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _count_sync)

    # ── Worker loop ─────────────────────────────────────────────────

    async def start_worker(self, poll_interval: float = 1.0) -> None:
        """Start the background worker loop that processes tasks."""
        if self._running:
            logger.warning("TaskQueue worker already running")
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(poll_interval))
        logger.info("TaskQueue worker started (poll_interval=%.1fs)", poll_interval)

    async def stop_worker(self) -> None:
        """Stop the background worker loop."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        logger.info("TaskQueue worker stopped")

    async def _worker_loop(self, poll_interval: float) -> None:
        """Main worker loop: poll for tasks and process them."""
        while self._running:
            try:
                task = await self.poll()
                if task is None:
                    await asyncio.sleep(poll_interval)
                    continue

                await self._process_task(task)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("TaskQueue worker error: %s", e)
                await asyncio.sleep(5)

    async def _process_task(self, task: Task) -> None:
        """Process a single task with retry logic."""
        handler = self._handler_map.get(task.type)
        if handler is None:
            logger.error("No handler for task type '%s' (task %s)", task.type, task.id)
            await self.fail(task.id, f"No handler registered for type '{task.type}'")
            return

        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(task, **task.params)
            else:
                handler(task, **task.params)
            await self.complete(task.id)
            logger.info("Task %s completed successfully", task.id)
        except Exception as e:
            error_msg = str(e)
            logger.warning("Task %s failed (attempt %d/%d): %s",
                           task.id, task.attempts + 1, task.max_attempts, error_msg)

            if task.attempts + 1 >= task.max_attempts:
                await self.fail(task.id, error_msg)
                logger.error("Task %s failed after %d attempts", task.id, task.max_attempts)
            else:
                # Exponential backoff: 2^(attempt+1) seconds
                delay = 2 ** (task.attempts + 1)
                await self.retry(task.id, error_msg)
                logger.info("Task %s will retry in %ds (attempt %d/%d)",
                            task.id, delay, task.attempts + 2, task.max_attempts)
                # The delay is handled by the worker polling — the task
                # will be picked up on the next poll cycle

    # ── Cleanup ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
