# Layer 3 — 任务管理 (Task Management)

## 概述

Layer 3 任务管理系统负责项目中所有异步任务的调度、编排、执行、状态跟踪和失败重试。系统由三大核心组件构成：**工作流编排器 (Orchestrator)**、**任务调度器 (Scheduler)** 和 **任务队列 (Queue)**。Orchestrator 负责多步骤 DAG 工作流的协调执行与失败补偿，Scheduler 负责定时触发任务，Queue 负责 FIFO 执行和自动重试。

---

## 工作流编排器 (Orchestrator)

### 文件位置

```
task/orchestrator.py
```

### 核心职责

- 接收 **ActionPlan**（一组带依赖关系的步骤列表），解析依赖顺序并构建 DAG
- 按拓扑序执行步骤，支持串行和并行执行
- 步骤失败时触发 **回滚补偿 (Rollback Compensation)**，执行已成功步骤的补偿动作
- 每个步骤可定义自己的补偿动作，确保资源一致性

### ActionPlan 数据模型

```python
@dataclass
class ActionStep:
    id: str                          # 步骤唯一标识
    tool: str                        # 执行工具标识，对应 handler
    params: dict                     # 步骤参数
    depends_on: list[int]            # 依赖的步骤索引列表
    compensation: Optional[ActionStep] = None  # 补偿动作（可选）

@dataclass
class ActionPlan:
    workflow_id: str                 # 工作流唯一标识
    steps: list[ActionStep]          # 所有步骤
    user_intent: str                 # 用户意图描述
    confidence: float                # 意图识别置信度 (0.0~1.0)
    created_at: datetime             # 创建时间

@dataclass
class StepResult:
    step_id: str                     # 步骤 ID
    status: StepStatus               # 步骤状态
    output: Any                      # 步骤输出结果
    error: Optional[str] = None      # 错误信息
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

@dataclass
class CompensationAction:
    step_id: str                     # 对应原始步骤 ID
    action: str                      # 补偿动作标识
    params: dict                     # 补偿参数
    status: StepStatus               # 补偿执行状态
```

### 步骤状态机 (Step State Machine)

每个步骤在其生命周期内经历以下状态转换：

```
                         ┌─────────────────────────────────────────┐
                         │             补偿链 (可选)                │
                         │                                         │
                    ┌────▼────┐    ┌──────────────┐               │
                    │ ROLLBACK│ ──►│ COMPENSATED  │               │
                    │ (补偿中)│    │  (已补偿)    │               │
                    └────┬────┘    └──────────────┘               │
                         │                                        │
                    ┌────▼────┐                                   │
                    │COMPENSATE│ (执行补偿动作)                     │
                    │ (触发)  │                                   │
                    └────┬────┘                                   │
                         │                                        │
                         │     ┌─────────────────────────┐        │
                         │     │      正常执行路径        │        │
                         │     │                         │        │
                    ┌────┴─────▼──┐                     │        │
                    │   PENDING   │                     │        │
                    └──────┬──────┘                     │        │
                           │  开始执行                   │        │
                    ┌──────▼──────┐                     │        │
                    │   RUNNING   │                     │        │
                    └──┬──────┬──┘                     │        │
                       │      │                         │        │
                   成功 │      │ 失败                    │        │
                       │      │                         │        │
              ┌────────▼──┐ ┌─▼──────────────┐         │        │
              │  SUCCESS  │ │    FAILED      │         │        │
              └───────────┘ └────────┬───────┘         │        │
                                     │                  │        │
                                     │ 有补偿动作      │        │
                                     └──► COMPENSATE ──┘        │
                                         └──► ROLLBACK ─────────┘
                                              └──► COMPENSATED
```

**状态说明：**

| 状态 | 说明 |
|------|------|
| `PENDING` | 步骤等待执行，依赖尚未全部满足 |
| `RUNNING` | 步骤正在执行 |
| `SUCCESS` | 步骤执行成功 |
| `FAILED` | 步骤执行失败 |
| `COMPENSATE` | 失败触发，准备执行补偿动作 |
| `ROLLBACK` | 补偿动作正在执行 |
| `COMPENSATED` | 补偿动作执行完毕 |

### DAG 工作流执行流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Orchestrator 执行流程                             │
│                                                                     │
│  1. 接收 ActionPlan                                                  │
│  2. 解析步骤依赖，构建 DAG（有向无环图）                              │
│  3. 拓扑排序：确定执行顺序                                            │
│  4. 并行执行无依赖步骤，串行执行有链式依赖步骤                        │
│  5. 收集 StepResult，监控状态                                        │
│  6. 所有步骤成功 → 工作流完成                                       │
│  7. 任意步骤失败 → 触发补偿流程                                     │
│     a. 按依赖反向顺序遍历已成功步骤                                  │
│     b. 对有 compensation 定义的步骤执行补偿动作                      │
│     c. 标记补偿状态为 ROLLBACK → COMPENSATED                        │
│  8. 返回最终 WorkflowResult（含所有 StepResult 和 CompensationResult）│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### ASCII 示例：ActionPlan DAG

```
             ┌──────────┐
             │  Step A   │  (无依赖)
             └────┬─────┘
                  │
          ┌───────┼───────┐
          │       │       │
    ┌─────▼────┐ ┌▼──────┐ │
    │  Step B  │ │Step C │ │  (依赖 A)
    └─────┬────┘ └───┬───┘ │
          │          │     │
          └──────┬───┘     │
                 │         │
           ┌─────▼─────┐   │
           │  Step D   │   │  (依赖 B, C)
           └─────┬─────┘   │
                 │         │
           ┌─────▼─────┐   │
           │  Step E   │   │  (依赖 D)
           └───────────┘   │
                           │
                    ┌──────▼──────┐
                    │ Workflow    │
                    │ 完成/失败   │
                    └─────────────┘
```

**串行执行**（链式依赖）：A → B → D → E
**并行执行**（无相互依赖）：B 和 C 可同时执行

### 补偿回滚示例

假设以下 ActionPlan，Step C 定义了补偿动作 delete_image：

| 步骤 | 动作 | 依赖 | 补偿动作 |
|------|------|------|---------|
| Step A | upload_image | 无 | delete_image |
| Step B | create_draft | A | cancel_draft |
| Step C | publish_article | B | 无 |

**执行过程：**

```
Step A (upload_image)    ── 成功 ──► 记录输出 (image_id)
Step B (create_draft)    ── 成功 ──► 记录输出 (draft_id)
Step C (publish_article) ── 失败! ──► 触发补偿

补偿顺序（反向依赖）：
  Step B (cancel_draft)  ── 执行补偿 ──► 删除草稿
  Step A (delete_image)  ── 执行补偿 ──► 删除已上传图片

最终状态：C → FAILED, B → COMPENSATED, A → COMPENSATED
```

### Workflow 聚合数据模型

```python
@dataclass
class Workflow:
    workflow_id: str                 # 工作流唯一标识
    plan: ActionPlan                 # 原始 ActionPlan
    step_results: dict[str, StepResult]  # 步骤 ID → 执行结果
    compensation_results: dict[str, CompensationAction]  # 步骤 ID → 补偿结果
    status: WorkflowStatus           # 工作流整体状态
    created_at: datetime
    completed_at: Optional[datetime] = None

class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"

class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    COMPENSATE = "compensate"
    ROLLBACK = "rollback"
    COMPENSATED = "compensated"
```

### Orchestrator 核心接口 (伪代码)

```python
class Orchestrator:
    def __init__(self, queue: TaskQueue):
        self.queue = queue
        self.active_workflows: dict[str, Workflow] = {}

    async def execute_plan(self, plan: ActionPlan) -> Workflow:
        """执行一个完整的 ActionPlan 工作流。"""
        workflow = Workflow(workflow_id=plan.workflow_id, plan=plan, ...)
        dag = self._build_dag(plan.steps)
        execution_order = self._topological_sort(dag)

        for batch in execution_order:  # batch = 可并行执行的步骤列表
            try:
                results = await asyncio.gather(*[
                    self._run_step(step, workflow) for step in batch
                ])
            except Exception as e:
                # 步骤失败，启动补偿流程
                await self._compensate(workflow, failed_step_id)
                workflow.status = WorkflowStatus.COMPENSATED
                return workflow

        workflow.status = WorkflowStatus.COMPLETED
        return workflow

    async def _run_step(self, step: ActionStep, workflow: Workflow) -> StepResult:
        """执行单个步骤，记录结果。"""
        result = StepResult(step_id=step.id, status=StepStatus.RUNNING)
        try:
            output = await execute_handler(step.action, step.params)
            result.status = StepStatus.SUCCESS
            result.output = output
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            raise
        finally:
            result.completed_at = now()
            workflow.step_results[step.id] = result
        return result

    async def _compensate(self, workflow: Workflow, failed_step_id: str):
        """按依赖反向顺序执行补偿。"""
        ordered_steps = self._reverse_dependency_order(workflow.plan.steps)
        for step in ordered_steps:
            if step.id == failed_step_id:
                continue  # 失败步骤本身无需补偿
            result = workflow.step_results.get(step.id)
            if result and result.status == StepStatus.SUCCESS and step.compensation:
                comp = CompensationAction(
                    step_id=step.id,
                    action=step.compensation.action,
                    params=step.compensation.params,
                    status=StepStatus.ROLLBACK
                )
                try:
                    await execute_handler(step.compensation.action, step.compensation.params)
                    comp.status = StepStatus.COMPENSATED
                except Exception:
                    comp.status = StepStatus.FAILED  # 补偿本身失败，记录但继续
                workflow.compensation_results[step.id] = comp
```

### SQLite 表结构（扩展）

```sql
CREATE TABLE workflows (
    workflow_id TEXT PRIMARY KEY,
    plan_json TEXT NOT NULL,         -- ActionPlan JSON
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE workflow_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    step_id TEXT NOT NULL,
    action TEXT NOT NULL,
    params TEXT,                    -- JSON
    depends_on TEXT,                -- JSON 数组
    compensation_json TEXT,         -- 补偿动作 JSON (可选)
    status TEXT DEFAULT 'pending',
    output TEXT,                    -- JSON
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE compensation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    step_id TEXT NOT NULL,
    compensation_action TEXT NOT NULL,
    params TEXT,                    -- JSON
    status TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_workflow_steps_wf ON workflow_steps(workflow_id);
CREATE INDEX idx_compensation_log_wf ON compensation_log(workflow_id);
```

---

## 任务调度器 (Scheduler)

### 文件位置

```
task/scheduler.py
```

### 核心机制

- **调度引擎**：基于 `croniter` 库解析 Cron 表达式
- **运行循环**：异步事件循环，每 60 秒触发一次调度检查
- **任务触发**：到达 Cron 时间点时，将任务提交至任务队列

### 工作流程

```
┌─────────────────────────────────────────────────────────┐
│                     Scheduler Loop                       │
│                                                          │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ 等待 60s  │ ──► │ 解析 Cron  │ ──► │ 匹配当前时间  │ │
│  └──────────┘     └──────────────┘     └──────┬───────┘ │
│                                                │         │
│                                         ┌──────▼───────┐│
│                                         │ 提交到队列   ││
│                                         └──────────────┘│
└─────────────────────────────────────────────────────────┘
```

### Job 配置格式 (YAML)

```yaml
jobs:
  - name: sync_wechat_token
    cron: "*/30 * * * *"
    task_type: wechat.token_refresh
    params:
      app_id: "wx_xxx"
    enabled: true
    retry:
      max_attempts: 3
      backoff: exponential

  - name: daily_article_publish
    cron: "0 9 * * *"
    task_type: wechat.publish
    params:
      draft_id: "latest"
    enabled: true
    retry:
      max_attempts: 3
      backoff: exponential

  - name: weekly_stats_report
    cron: "0 8 * * 1"
    task_type: stats.generate
    params:
      period: "weekly"
      format: "json"
    enabled: false
```

### 配置字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 任务唯一名称标识 |
| `cron` | str | Cron 表达式 (5 段式) |
| `task_type` | str | 任务类型标识，对应 handler |
| `params` | dict | 任务执行参数 |
| `enabled` | bool | 是否启用 |
| `retry.max_attempts` | int | 最大重试次数 |
| `retry.backoff` | str | 退避策略 (`exponential` / `fixed`) |

---

## 任务队列 (Task Queue)

### 文件位置

```
task/queue.py
```

### 核心特性

| 特性 | 说明 |
|------|------|
| **队列模型** | FIFO (先进先出) |
| **持久化** | SQLite 数据库存储任务状态 |
| **状态流转** | `pending` → `running` → `completed` / `failed` |
| **自动重试** | 最多 3 次，指数退避 |

### 任务状态机

```
                    ┌──────────┐
                    │  PENDING  │
                    └────┬─────┘
                         │
                    ┌────▼─────┐
               ┌───│  RUNNING  │───┐
               │   └────┬─────┘   │
          成功  │        │ 失败    │ 到达重试上限
               │   ┌────▼─────┐   │
               │   │  PENDING  │   │
               │   │ (重试)    │   │
               │   └────┬─────┘   │
               │        │         │
         ┌─────▼────┐  ┌─────────▼─────┐
         │ COMPLETED │  │    FAILED     │
         └──────────┘  └───────────────┘
```

### 任务生命周期 ASCII 图

```
时间线 ──────────────────────────────────────────────────►

  创建       调度      执行        完成/失败
   │          │         │             │
   ▼          ▼         ▼             ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────────┐
│QUEUED│──►│PENDING│──►│RUNNING│──►│COMPLETED │
└──────┘  └──────┘  └──────┘  └──────────┘
                         │
                    失败 │ 重试次数 < 3
                         ▼
                    ┌────────┐
                    │PENDING │ (重新入队)
                    │(重试)  │
                    └────────┘
                         │
                    失败 │ 重试次数 ≥ 3
                         ▼
                    ┌────────┐
                    │ FAILED │
                    └────────┘
```

### 自动重试机制

```python
# 伪代码：重试逻辑
async def execute_with_retry(task, max_attempts=3):
    for attempt in range(1, max_attempts + 1):
        try:
            result = await task.execute()
            task.state = "completed"
            return result
        except Exception as e:
            if attempt == max_attempts:
                task.state = "failed"
                raise
            # 指数退避: 2^attempt 秒
            wait = 2 ** attempt
            task.state = "pending"  # 重新入队
            await asyncio.sleep(wait)
```

### 退避策略

| 重试次数 | 等待时间 (指数退避) |
|----------|-------------------|
| 第 1 次   | 2 秒              |
| 第 2 次   | 4 秒              |
| 第 3 次   | 8 秒              |

### SQLite 表结构

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    params TEXT,                -- JSON 格式
    state TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);

CREATE INDEX idx_tasks_state ON tasks(state);
CREATE INDEX idx_tasks_created ON tasks(created_at);
```

### SQLite 连接配置 (Connection Setup)

```python
import sqlite3

# 数据库连接初始化 — 必须设置 WAL 模式和 busy_timeout
def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 关键 PRAGMA 设置
    conn.execute("PRAGMA journal_mode=WAL;")          # WAL 模式：支持并发读写
    conn.execute("PRAGMA busy_timeout=5000;")          # 忙等待超时 5 秒，避免立即报错
    conn.execute("PRAGMA foreign_keys=ON;")            # 外键约束
    conn.execute("PRAGMA synchronous=NORMAL;")         # 平衡安全性与写入性能

    return conn
```

### 任务状态转换 — 事务处理伪代码

所有状态转换必须包裹在显式 BEGIN/COMMIT/ROLLBACK 事务中，确保 ACID 语义：

```python
async def transition_task_state(task_id: str, from_states: list[str], to_state: str) -> bool:
    """
    安全地将任务从 from_states 之一转换到 to_state。
    使用乐观锁 (state = ? AND updated_at = ?) 防止竞态。
    """
    conn = get_connection("./data/pulsar.db")
    try:
        conn.execute("BEGIN IMMEDIATE;")          # IMMEDIATE 防止死锁

        cursor = conn.execute(
            """UPDATE tasks
               SET state = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND state IN ({})
               RETURNING id, state, updated_at;""".format(
                ",".join("?" for _ in from_states)
            ),
            [to_state, task_id] + from_states
        )
        row = cursor.fetchone()

        if row is None:
            conn.execute("ROLLBACK;")
            logger.warning(f"Task {task_id} state conflict: not in {from_states}")
            return False

        conn.execute("COMMIT;")
        return True
    except sqlite3.OperationalError as e:
        conn.execute("ROLLBACK;")
        logger.error(f"Transaction failed for task {task_id}: {e}")
        raise
    finally:
        conn.close()
```

在 Queue Worker 的主循环中使用：

```python
# Queue Worker 伪代码 — 事务保护
async def worker_loop():
    conn = get_connection("./data/pulsar.db")
    while True:
        try:
            conn.execute("BEGIN IMMEDIATE;")

            # 1. 原子领取下一个 pending 任务（FIFO）
            cursor = conn.execute(
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
            task = cursor.fetchone()

            if task is None:
                conn.execute("ROLLBACK;")
                await asyncio.sleep(1)
                continue

            conn.execute("COMMIT;")

            # 2. 执行任务（不在事务内，避免长事务锁定）
            success = await execute_task(task)

            # 3. 更新结果（新事务）
            conn.execute("BEGIN IMMEDIATE;")
            new_state = "completed" if success else (
                "pending" if task["attempts"] < task["max_attempts"] - 1
                else "failed"
            )
            conn.execute(
                "UPDATE tasks SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_state, task["id"])
            )
            conn.execute("COMMIT;")

        except sqlite3.OperationalError as e:
            conn.execute("ROLLBACK;")
            logger.error(f"Worker transaction error: {e}")
            await asyncio.sleep(5)
```

### Alembic Schema 迁移策略

```python
# alembic/env.py — 关键配置

from alembic import context
from sqlalchemy import engine_from_config

# 自动检测 model 变更并生成迁移
target_metadata = Base.metadata  # 使用 SQLAlchemy declarative Base

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,       # 检测列类型变更
            compare_server_default=True,  # 检测默认值变更
        )
        with context.begin_transaction():
            context.run_migrations()
```

**迁移流程：**
1. 修改 model → `alembic revision --autogenerate -m "描述"`
2. 审查生成的 migration 脚本 → `alembic upgrade head`
3. 回滚 → `alembic downgrade -1`

---

## 整体系统交互流程

Orchestrator、Scheduler 和 Queue 三者协同工作，覆盖从定时触发、DAG 编排到 FIFO 执行的全链路：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Scheduler Loop (60s)                            │
│                                                                     │
│  1. 读取 job 配置 (YAML)                                            │
│  2. 检查每个 job 的 cron 表达式是否匹配当前时间                      │
│  3. 匹配 → 创建 task 记录并写入 SQLite (state: pending)             │
│  4. 等待 60 秒后重复                                                │
│                                                                     │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Queue Worker Loop                               │
│                                                                     │
│  1. 轮询 SQLite 中 state = 'pending' 的任务 (FIFO 顺序)            │
│  2. 更新 state = 'running'                                          │
│  3. 执行任务 handler                                                 │
│     ├── 普通任务 → 成功/失败 + 自动重试                             │
│     └── ActionPlan 任务 → 提交给 Orchestrator                       │
│  4. 成功 → state = 'completed'                                      │
│  5. 失败 → 重试或 state = 'failed'                                  │
│                                                                     │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Orchestrator 引擎                                │
│                                                                     │
│  1. 接收 ActionPlan (从 Queue 分发)                                  │
│  2. 构建 DAG，拓扑排序确定执行顺序                                   │
│  3. 按序执行步骤（并行/串行）                                       │
│  4. 步骤失败 → 反向依赖顺序执行补偿                                 │
│  5. 返回 WorkflowResult 回 Queue                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

> **架构说明**：SQLite 连接配置、事务处理伪代码和 Alembic 迁移策略详见上方「SQLite 连接配置」「任务状态转换 — 事务处理伪代码」和「Alembic Schema 迁移策略」章节。所有状态转换必须包裹在 BEGIN IMMEDIATE / COMMIT / ROLLBACK 内以确保 ACID 语义。
