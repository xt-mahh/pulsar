# Pulsar Phase 1 Sprint 1 — task/ 模块详细计划

> 本文档描述 `task/` 模块的设计方案，包含 Cron 调度器和任务队列。
> task 是系统的项目经理，负责把目标和策略拆解成可执行的任务单元。

---

## 一、模块定位

**职责**：提供基础的定时任务调度和任务队列管理能力。

**Phase 1 范围**：
- 简易 Cron 调度器（从 config.yaml 加载定时任务）
- FIFO 内存队列 + SQLite 持久化
- 任务状态机：pending → running → completed / failed
- 失败自动重试最多 3 次

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `task/__init__.py` | P0 | 无 |
| 2 | `task/scheduler.py` | P0 | shared, queue |
| 3 | `task/queue.py` | P0 | shared |

---

## 三、`task/queue.py` 设计方案

### 3.1 职责

FIFO 任务队列，支持内存队列 + SQLite 持久化。

### 3.2 核心实现

```python
class TaskQueue:
    """任务队列 — FIFO + SQLite 持久化"""
    
    def __init__(self, db_path: str = "data/state.db"):
        self._db_path = db_path
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._running: dict[str, Task] = {}  # task_id → Task
        self._lock = asyncio.Lock()
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """初始化数据库表"""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
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
        await self._db.commit()
        
        # 恢复未完成的任务
        cursor = await self._db.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running')"
        )
        rows = await cursor.fetchall()
        for row in rows:
            task = Task(
                id=row[0], type=row[1], status=row[2],
                input=json.loads(row[3]), output=json.loads(row[4]) if row[4] else None,
                error=row[5], retry_count=row[6], max_retries=row[7],
            )
            await self._queue.put(task)
    
    async def enqueue(self, task: Task) -> str:
        """加入队列"""
        await self._queue.put(task)
        await self._persist(task)
        return task.id
    
    async def dequeue(self) -> Optional[Task]:
        """取出任务（阻塞）"""
        task = await self._queue.get()
        task.status = "running"
        self._running[task.id] = task
        await self._update_status(task)
        return task
    
    async def complete(self, task_id: str, output: dict):
        """标记任务完成"""
        task = self._running.pop(task_id, None)
        if task:
            task.status = "completed"
            task.output = output
            task.updated_at = datetime.utcnow()
            await self._update_status(task)
    
    async def fail(self, task_id: str, error: str):
        """标记任务失败（自动重试）"""
        task = self._running.get(task_id)
        if not task:
            return
        
        task.retry_count += 1
        if task.retry_count < task.max_retries:
            # 重新入队
            task.status = "pending"
            await self._queue.put(task)
        else:
            task.status = "failed"
            task.error = error
        
        task.updated_at = datetime.utcnow()
        await self._update_status(task)
        self._running.pop(task_id, None)
    
    async def get_status(self, task_id: str) -> Optional[dict]:
        """查询任务状态"""
        cursor = await self._db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "id": row[0], "type": row[1], "status": row[2],
                "retry_count": row[6], "max_retries": row[7],
                "created_at": row[8], "updated_at": row[9],
            }
        return None
    
    async def _persist(self, task: Task):
        """持久化任务到 SQLite"""
        await self._db.execute(
            """INSERT OR REPLACE INTO tasks 
               (id, type, status, input, output, error, retry_count, max_retries, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.type, task.status,
             json.dumps(task.input), json.dumps(task.output) if task.output else None,
             task.error, task.retry_count, task.max_retries,
             task.created_at.isoformat(), task.updated_at.isoformat())
        )
        await self._db.commit()
    
    async def _update_status(self, task: Task):
        """更新任务状态"""
        await self._db.execute(
            "UPDATE tasks SET status=?, output=?, error=?, retry_count=?, updated_at=? WHERE id=?",
            (task.status, json.dumps(task.output) if task.output else None,
             task.error, task.retry_count, task.updated_at.isoformat(), task.id)
        )
        await self._db.commit()
```

---

## 四、`task/scheduler.py` 设计方案

### 4.1 职责

Cron 调度器，从 config.yaml 加载定时任务，按 Cron 表达式触发。

### 4.2 核心实现

```python
class Scheduler:
    """Cron 调度器"""
    
    def __init__(self, config: dict, task_queue: TaskQueue):
        self._jobs: list[dict] = config.get("jobs", [])
        self._task_queue = task_queue
        self._running = False
        self._tasks: list[asyncio.Task] = []
    
    async def start(self):
        """启动调度器"""
        self._running = True
        for job in self._jobs:
            task = asyncio.create_task(self._run_job(job))
            self._tasks.append(task)
    
    async def stop(self):
        """停止调度器"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
    
    async def _run_job(self, job: dict):
        """运行单个定时任务"""
        schedule = job["schedule"]
        cron_parts = schedule.split()
        
        while self._running:
            now = datetime.now()
            # 计算下次执行时间
            next_run = self._calculate_next_run(cron_parts, now)
            wait_seconds = (next_run - now).total_seconds()
            
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            if not self._running:
                break
            
            # 创建并执行任务
            task = Task(
                id=f"{job['name']}_{int(time.time())}",
                type=job["task"]["type"],
                status="pending",
                input=job["task"],
            )
            await self._task_queue.enqueue(task)
    
    def _calculate_next_run(self, cron_parts: list[str], from_time: datetime) -> datetime:
        """计算下次 Cron 执行时间（简化实现）"""
        minute, hour, day, month, day_of_week = cron_parts
        
        # 简单实现：仅支持 "0 17 * * *" 这种格式
        if minute == "0" and hour != "*":
            next_run = from_time.replace(
                hour=int(hour), minute=0, second=0, microsecond=0
            )
            if next_run <= from_time:
                next_run += timedelta(days=1)
            return next_run
        
        # 兜底：每分钟检查
        return from_time + timedelta(minutes=1)
```

---

## 五、验收标准

- [ ] `TaskQueue.enqueue()` 将任务加入队列并持久化到 SQLite
- [ ] `TaskQueue.dequeue()` 取出 pending 状态的任务
- [ ] `TaskQueue.complete()` 标记任务完成
- [ ] `TaskQueue.fail()` 自动重试（最多 3 次），超过后标记 failed
- [ ] 系统重启后恢复未完成的任务
- [ ] `Scheduler.start()` 从 config.yaml 加载定时任务
- [ ] 定时任务在指定 Cron 时间触发

---

## 六、注意事项

1. **Cron 表达式**：Phase 1 仅支持简化的 Cron 格式（5 段式），完整实现可引入 `croniter` 库
2. **任务幂等**：任务执行应支持幂等重试，避免重复执行导致的问题
3. **SQLite 并发**：使用 aiosqlite 确保异步安全，写操作加锁
4. **任务超时**：Phase 1 暂不实现任务超时机制，后续可添加