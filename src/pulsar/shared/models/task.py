from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional
from datetime import datetime, timezone
import enum


class TaskStatus(str, enum.Enum):
    """任务生命周期状态枚举。

    任务状态转换图:
    ┌──────────┐
    │  PENDING  │ ── 任务已创建但尚未开始执行
    └────┬─────┘
         │
         ▼
    ┌──────────┐
    │  RUNNING  │ ── 任务正在执行中（可能包含多个子步骤）
    └────┬─────┘
         │
         ├──────────────────┐
         ▼                  ▼
    ┌──────────┐      ┌──────────┐
    │  SUCCESS  │      │  FAILED   │ ── 任务执行失败（不可恢复）
    └──────────┘      └────┬─────┘
                           │
                           ▼
                      ┌──────────┐
                      │ ROLLBACK │ ── 已执行回滚操作
                      └──────────┘

    此外还有两个临时状态:
    - CANCELLED: 用户主动取消
    - TIMEOUT: 任务超过最大执行时间
    """
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    SUCCESS = "success"        # 执行成功
    FAILED = "failed"          # 执行失败
    CANCELLED = "cancelled"    # 已取消
    TIMEOUT = "timeout"        # 执行超时
    ROLLBACK = "rollback"      # 已回滚
    ROLLING_BACK = "rolling_back"  # 正在回滚中


class TaskPriority(str, enum.Enum):
    """任务优先级枚举。"""
    LOW = "low"                # 低优先级（如定时任务、数据清理）
    NORMAL = "normal"          # 普通优先级（默认）
    HIGH = "high"              # 高优先级（如用户交互操作）
    CRITICAL = "critical"      # 紧急优先级（如系统恢复）


class TaskType(str, enum.Enum):
    """任务类型枚举。"""
    PUBLISH_ARTICLE = "publish_article"          # 发布文章
    UPLOAD_MEDIA = "upload_media"                # 上传素材
    DELETE_POST = "delete_post"                  # 删除已发布内容
    SCHEDULE_PUBLISH = "schedule_publish"         # 定时发布
    UPDATE_DRAFT = "update_draft"                # 修改草稿
    SEND_MESSAGE = "send_message"                # 发送模板消息
    SYNC_DATA = "sync_data"                      # 同步数据
    CUSTOM = "custom"                            # 自定义任务


class TaskStep(BaseModel):
    """任务步骤模型。

    一个 Task 由多个 TaskStep 组成，按序或并行执行。
    """
    model_config = ConfigDict(frozen=True)

    step_id: str = Field(
        ...,
        description="步骤唯一标识。格式: 'step_' + UUID。"
    )
    name: str = Field(
        ...,
        description="步骤名称。如 '上传封面图片'、'创建草稿'。"
    )
    tool_name: str = Field(
        ...,
        description="执行此步骤需要调用的工具名称。"
    )
    arguments: dict = Field(
        default_factory=dict,
        description="工具调用参数。"
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="依赖的步骤 ID 列表。所有依赖步骤执行成功后才能执行本步骤。"
    )
    retry_count: int = Field(
        default=0,
        description="已重试次数。"
    )
    max_retries: int = Field(
        default=3,
        description="最大重试次数。超过后步骤标记为失败。"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="步骤当前状态。"
    )
    result: Optional[Any] = Field(
        default=None,
        description="步骤执行结果。失败时包含错误信息。"
    )
    started_at: Optional[datetime] = Field(default=None, description="步骤开始执行时间。")
    completed_at: Optional[datetime] = Field(default=None, description="步骤完成时间。")
    duration_ms: int = Field(default=0, description="步骤执行耗时（毫秒）。")


class Task(BaseModel):
    """任务模型。

    代表一个可追踪的工作单元，由 Orchestrator 创建并管理。
    一个"发布文章"操作可能包含多个 TaskStep。
    """
    model_config = ConfigDict(frozen=True)

    task_id: str = Field(
        ...,
        description="任务唯一标识。格式: 'task_' + UUID（8 位十六进制）。"
                    "例如: task_a1b2c3d4。"
    )
    type: TaskType = Field(
        ...,
        description="任务类型。决定了任务的编排逻辑和默认参数。"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="任务当前状态。"
    )
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL,
        description="任务优先级。影响调度顺序。"
    )
    title: str = Field(
        default="",
        description="任务标题。供用户界面显示。如 '发布文章: 宇宙的灯塔'。"
    )
    description: str = Field(
        default="",
        description="任务描述。包含任务目的和关键参数的 JSON 摘要。"
    )

    # ---- 步骤管理 ----
    steps: list[TaskStep] = Field(
        default_factory=list,
        description="任务步骤列表。步骤按顺序排列，执行前需解析依赖关系。"
    )

    # ---- 上下文 ----
    session_id: str = Field(
        default="",
        description="创建此任务的会话 ID。用于追溯用户交互历史。"
    )
    platform: str = Field(
        default="",
        description="目标平台标识。如 'wechat'、'weibo'。"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="任务元数据。用于存储任意附加信息，如草稿 media_id、发布结果等。"
    )

    # ---- 时间 ----
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="任务创建时间（UTC）。"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="任务开始执行时间（UTC）。"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="任务完成时间（UTC）。包括成功、失败、取消、超时。"
    )
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="定时执行时间（UTC）。为空表示立即执行。"
    )
    timeout_at: Optional[datetime] = Field(
        default=None,
        description="超时截止时间（UTC）。到达此时间后任务强制标记为 TIMEOUT。"
    )

    # ---- 结果 ----
    result: Optional[Any] = Field(
        default=None,
        description="任务最终结果。成功时包含平台返回的数据。"
    )
    error: Optional[str] = Field(
        default=None,
        description="任务错误信息。失败时包含人类可读的错误描述。"
    )
    error_code: Optional[str] = Field(
        default=None,
        description="任务错误码。供程序判断错误类型（如 'WECHAT_API_ERROR'）。"
    )

    # ---- 统计 ----
    total_duration_ms: int = Field(
        default=0,
        description="任务总耗时（毫秒）。从 started_at 到 completed_at。"
    )
    retry_count: int = Field(
        default=0,
        description="任务级别重试次数（整体重试）。"
    )

    # ---- 方法 ----
    def progress(self) -> float:
        """计算任务完成进度（0.0 ~ 1.0）。"""
        if not self.steps:
            return 1.0 if self.status == TaskStatus.SUCCESS else 0.0
        completed = sum(1 for s in self.steps
                        if s.status in (TaskStatus.SUCCESS, TaskStatus.FAILED))
        return completed / len(self.steps)

    def is_terminal(self) -> bool:
        """判断任务是否处于终态。"""
        return self.status in (
            TaskStatus.SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
            TaskStatus.ROLLBACK,
        )
