from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional
from datetime import datetime, timezone
import enum


class AuditEvent(str, enum.Enum):
    """审计事件类型枚举。

    命名规则: <组件>.<动作>
    """
    # Agent 生命周期
    AGENT_START = "agent.start"             # Agent 启动
    AGENT_STOP = "agent.stop"               # Agent 停止
    AGENT_RESTART = "agent.restart"         # 心跳检测触发重启

    # LLM 调用
    LLM_REQUEST = "llm.request"             # LLM 调用开始
    LLM_RESPONSE = "llm.response"           # LLM 调用结束
    LLM_ERROR = "llm.error"                 # LLM 调用失败

    # 工具调用
    TOOL_CALL = "tool.call"                 # 工具调用开始
    TOOL_RESULT = "tool.result"             # 工具调用结束
    TOOL_ERROR = "tool.error"               # 工具调用失败

    # 平台操作
    PLATFORM_LOGIN = "platform.login"       # 平台登录
    PLATFORM_PUBLISH = "platform.publish"   # 平台发布内容
    PLATFORM_DELETE = "platform.delete"     # 平台删除内容
    PLATFORM_UPLOAD = "platform.upload"     # 平台上传素材
    PLATFORM_ERROR = "platform.error"       # 平台 API 错误

    # 配置
    CONFIG_RELOAD = "config.reload"         # 配置热重载
    CONFIG_CHANGE = "config.change"         # 配置手动修改

    # 系统
    SYSTEM_ERROR = "system.error"           # 未分类错误
    SYSTEM_WARNING = "system.warning"       # 系统警告


class AuditLevel(str, enum.Enum):
    """审计级别枚举。"""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class AuditLog(BaseModel):
    """审计日志条目模型。

    每次关键操作生成一条审计日志记录，保存到 JSON Lines 文件。
    所有审计日志不可变（frozen=True），写入后不得修改。
    """
    model_config = ConfigDict(frozen=True)

    # ---- 核心字段 ----
    event: AuditEvent = Field(
        ...,
        description="审计事件类型。标识发生的操作类别。"
    )
    level: AuditLevel = Field(
        default=AuditLevel.INFO,
        description="日志级别。根据事件的严重程度设置。"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="事件发生时间（UTC）。精确到毫秒。"
    )

    # ---- 关联信息 ----
    session_id: str = Field(
        default="",
        description="关联的会话 ID。用于将同一次交互的多个审计事件串联。"
    )
    task_id: str = Field(
        default="",
        description="关联的任务 ID。如果此事件是任务执行的一部分。"
    )
    request_id: str = Field(
        default="",
        description="关联的请求 ID。用于追踪 PIP 请求链路。"
    )
    user_id: str = Field(
        default="system",
        description="触发此操作的用户标识。'system' 表示系统自动操作。"
    )

    # ---- 操作详情 ----
    action: str = Field(
        default="",
        description="具体操作名称。如 'publish_draft'、'chat'。"
    )
    resource: str = Field(
        default="",
        description="操作的资源标识。如 'media_id:abc123'、'article:宇宙的灯塔'。"
    )
    details: dict = Field(
        default_factory=dict,
        description="操作的详细信息。包含请求参数摘要、响应摘要等。"
                    "注意：不存储敏感信息（如 Token、密码）。"
    )

    # ---- 结果 ----
    success: bool = Field(
        default=True,
        description="操作是否成功。"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="操作失败时的错误信息。"
    )
    error_code: Optional[str] = Field(
        default=None,
        description="操作失败时的错误码。如 'WECHAT_40001'、'TIMEOUT'。"
    )

    # ---- 性能 ----
    duration_ms: Optional[int] = Field(
        default=None,
        description="操作耗时（毫秒）。对于长时间操作很有价值。"
    )

    # ---- 序列化 ----
    def to_json_line(self) -> str:
        """将审计日志序列化为 JSON Lines 格式字符串。

        返回:
            单行 JSON 字符串，末尾带 \\n。
        """
        import json
        data = self.model_dump()
        data["event"] = self.event.value
        data["level"] = self.level.value
        # 将 datetime 转换为 ISO 格式
        data["timestamp"] = self.timestamp.isoformat()
        return json.dumps(data, ensure_ascii=False, default=str) + "\n"
