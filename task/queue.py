"""Pulsar 任务队列 — FIFO 内存队列 + SQLite 持久化"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from shared.models import Task

logger = logging.getLogger("pulsar.task.queue")


class TaskQueue:
    """任务队列

    Phase 1 实现简单的 FIFO 内存队列 + SQLite 持久化。
    任务状态机：pending → running → completed / failed
    失败自动重试最多 3 次。
    """

    def __init__(self, db_path: str = "data/state.db") -> None:
        self.db_path = db_path
        self._memory_queue: list[Task] = []
        self._running_tasks: dict[str, Task] = {}
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    input TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def enqueue(self, task_type: str, input_data: dict[str, Any]) -> Task:
        """将任务加入队列"""
        task = Task(
            id=f"task_{uuid.uuid4().hex[:12]}",
            type=task_type,
            status="pending",
            input=input_data,
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self._memory_queue.append(task)
        self._save_task(task)
        logger.info("Task enqueued: %s (type: %s)", task.id, task_type)
        return task

    def dequeue(self) -> Task | None:
        """从队列取出一个待处理任务"""
        for i, task in enumerate(self._memory_queue):
            if task.status == "pending":
                task.status = "running"
                task.updated_at = datetime.now(timezone.utc)
                self._running_tasks[task.id] = task
                self._memory_queue.pop(i)
                self._update_task(task)
                logger.info("Task dequeued: %s", task.id)
                return task
        return None

    def complete(self, task_id: str, output: dict[str, Any]) -> bool:
        """标记任务为完成"""
        task = self._running_tasks.pop(task_id, None)
        if not task:
            return False

        task.status = "completed"
        task.output = output
        task.updated_at = datetime.now(timezone.utc)
        self._update_task(task)
        logger.info("Task completed: %s", task_id)
        return True

    def fail(self, task_id: str, error: str) -> bool:
        """标记任务为失败，自动重试"""
        task = self._running_tasks.pop(task_id, None)
        if not task:
            return False

        task.retry_count += 1
        task.updated_at = datetime.now(timezone.utc)

        if task.retry_count < task.max_retries:
            # 重新入队等待重试
            task.status = "pending"
            task.error = error
            self._memory_queue.append(task)
            logger.warning(
                "Task failed, retrying (%d/%d): %s - %s",
                task.retry_count,
                task.max_retries,
                task_id,
                error,
            )
        else:
            # 超过最大重试次数，标记为失败
            task.status = "failed"
            task.error = error
            logger.error(
                "Task failed permanently (%d retries): %s - %s",
                task.retry_count,
                task_id,
                error,
            )

        self._update_task(task)
        return True

    def get_status(self, task_id: str) -> Task | None:
        """获取任务状态"""
        # 先查内存中的运行任务
        task = self._running_tasks.get(task_id)
        if task:
            return task

        # 再查内存队列
        for t in self._memory_queue:
            if t.id == task_id:
                return t

        # 最后查数据库
        return self._load_task(task_id)

    def list_tasks(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出任务"""
        conn = sqlite3.connect(self.db_path)
        try:
            if status:
                cursor = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )

            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row[0],
                    "type": row[1],
                    "status": row[2],
                    "input": json.loads(row[3]) if row[3] else {},
                    "output": json.loads(row[4]) if row[4] else None,
                    "error": row[5],
                    "retry_count": row[6],
                    "max_retries": row[7],
                    "created_at": row[8],
                    "updated_at": row[9],
                })
            return tasks
        finally:
            conn.close()

    def retry_failed(self, task_id: str) -> bool:
        """重试失败的任务"""
        task = self._load_task(task_id)
        if not task or task.status != "failed":
            return False

        task.status = "pending"
        task.retry_count = 0
        task.error = None
        task.updated_at = datetime.now(timezone.utc)
        self._memory_queue.append(task)
        self._update_task(task)
        logger.info("Task queued for retry: %s", task_id)
        return True

    def _save_task(self, task: Task) -> None:
        """保存任务到数据库"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (id, type, status, input, output, error, retry_count, max_retries, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    task.type,
                    task.status,
                    json.dumps(task.input),
                    json.dumps(task.output) if task.output else None,
                    task.error,
                    task.retry_count,
                    task.max_retries,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_task(self, task: Task) -> None:
        """更新任务状态"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """UPDATE tasks SET
                   status = ?, output = ?, error = ?,
                   retry_count = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    task.status,
                    json.dumps(task.output) if task.output else None,
                    task.error,
                    task.retry_count,
                    task.updated_at.isoformat(),
                    task.id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_task(self, task_id: str) -> Task | None:
        """从数据库加载任务"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            return Task(
                id=row[0],
                type=row[1],
                status=row[2],
                input=json.loads(row[3]) if row[3] else {},
                output=json.loads(row[4]) if row[4] else None,
                error=row[5],
                retry_count=row[6],
                max_retries=row[7],
                created_at=datetime.fromisoformat(row[8]),
                updated_at=datetime.fromisoformat(row[9]),
            )
        finally:
            conn.close()

    @property
    def pending_count(self) -> int:
        """待处理任务数量"""
        return sum(1 for t in self._memory_queue if t.status == "pending")

    @property
    def running_count(self) -> int:
        """运行中任务数量"""
        return len(self._running_tasks)