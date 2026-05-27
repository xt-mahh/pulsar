import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from shared.models import Task
from shared.constants import DEFAULT_HEARTBEAT_INTERVAL


class TaskQueue:
    def __init__(self, db_path: str = "./data/state.db"):
        self.db_path = db_path
        self._memory_queue: list[Task] = []
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                input TEXT NOT NULL DEFAULT '{}',
                output TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.commit()
        await self._load_pending_tasks()

    async def _load_pending_tasks(self):
        cursor = await self._db.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC")
        rows = await cursor.fetchall()
        for row in rows:
            task = Task(
                id=row[0],
                type=row[1],
                status=row[2],
                input=json.loads(row[3]),
                output=json.loads(row[4]) if row[4] else None,
                error=row[5],
                retry_count=row[6],
                max_retries=row[7],
            )
            self._memory_queue.append(task)

    async def enqueue(self, task: Task) -> Task:
        self._memory_queue.append(task)
        await self._db.execute(
            "INSERT INTO tasks (id, type, status, input, retry_count, max_retries, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.type, task.status, json.dumps(task.input), task.retry_count, task.max_retries,
             task.created_at.isoformat(), task.updated_at.isoformat()),
        )
        await self._db.commit()
        return task

    async def dequeue(self) -> Task | None:
        for i, task in enumerate(self._memory_queue):
            if task.status == "pending":
                task.status = "running"
                task.updated_at = datetime.now(timezone.utc)
                await self._update_task(task)
                return task
        return None

    async def ack(self, task_id: str, output: dict = None):
        for task in self._memory_queue:
            if task.id == task_id:
                task.status = "completed"
                task.output = output
                task.updated_at = datetime.now(timezone.utc)
                await self._update_task(task)
                break

    async def nack(self, task_id: str, error: str = None):
        for task in self._memory_queue:
            if task.id == task_id:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.status = "failed"
                else:
                    task.status = "pending"
                task.error = error
                task.updated_at = datetime.now(timezone.utc)
                await self._update_task(task)
                break

    async def _update_task(self, task: Task):
        await self._db.execute(
            "UPDATE tasks SET status=?, output=?, error=?, retry_count=?, updated_at=? WHERE id=?",
            (task.status, json.dumps(task.output) if task.output else None, task.error,
             task.retry_count, task.updated_at.isoformat(), task.id),
        )
        await self._db.commit()

    async def list_tasks(self, status: str = None) -> list[Task]:
        if status:
            return [t for t in self._memory_queue if t.status == status]
        return list(self._memory_queue)

    async def get_task(self, task_id: str) -> Task | None:
        for task in self._memory_queue:
            if task.id == task_id:
                return task
        return None

    async def close(self):
        if self._db:
            await self._db.close()