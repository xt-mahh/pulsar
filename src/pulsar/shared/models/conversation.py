from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
from datetime import datetime, timezone
import enum


class ConversationRole(str, enum.Enum):
    """对话消息角色枚举。"""
    SYSTEM = "system"                 # 系统提示词
    USER = "user"                     # 用户消息
    ASSISTANT = "assistant"           # Agent 回复
    TOOL = "tool"                     # 工具调用结果
    FUNCTION = "function"             # 函数调用（兼容旧格式）


class ConversationMessage(BaseModel):
    """单条对话消息模型。

    对应 LLM Chat API（如 OpenAI）中的一条 message。
    """
    model_config = ConfigDict(frozen=True)

    role: ConversationRole = Field(
        ...,
        description="消息角色: system/user/assistant/tool/function。"
    )
    content: str | None = Field(
        ...,
        description="消息内容。tool 角色时可为空（使用 tool_call_id 关联）。"
    )
    name: Optional[str] = Field(
        default=None,
        description="发送者名称。用于区分不同用户或多 Agent 场景。"
    )
    tool_call_id: Optional[str] = Field(
        default=None,
        description="工具调用 ID。仅 tool 角色使用，关联到 assistant 发起的工具调用。"
    )
    tool_calls: Optional[list[dict]] = Field(
        default=None,
        description="工具调用列表。仅 assistant 角色使用，LLM 发起的并行工具调用。"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="消息时间戳。"
    )
    tokens: Optional[int] = Field(
        default=None,
        description="此消息包含的 Token 数（仅系统计算，非 LLM 返回）。"
    )


class ConversationContext(BaseModel):
    """对话上下文模型。

    维护多轮对话的状态和历史记录。由 Cognition 层的 Dialogue Manager 使用。
    """
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(
        ...,
        description="会话唯一标识。格式: 'sess_' + UUID（8 位十六进制）。"
                    "例如: sess_f1e2d3c4。"
    )
    messages: list[ConversationMessage] = Field(
        default_factory=list,
        description="对话历史消息列表。按时间正序排列。"
    )

    # ---- 状态 ----
    intents: list[str] = Field(
        default_factory=list,
        description="本次会话中已识别的用户意图列表。按识别时间正序排列。"
    )
    current_intent: Optional[str] = Field(
        default=None,
        description="当前正在处理的用户意图。"
    )
    collected_info: dict = Field(
        default_factory=dict,
        description="已收集的用户偏好信息。如主题、风格、长度等。"
                    "格式: {'key': {'value': ..., 'source': 'user_input'} }"
    )

    # ---- 元数据 ----
    platform: str = Field(
        default="",
        description="本次对话关联的目标平台。如 'wechat'。"
    )
    user_id: str = Field(
        default="",
        description="关联的用户标识。"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="会话创建时间。"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="会话最后更新时间。每次添加消息后更新。"
    )
    expired_at: Optional[datetime] = Field(
        default=None,
        description="会话过期时间。过期后会话被归档。默认创建后 24 小时过期。"
    )
    token_count: int = Field(
        default=0,
        description="当前会话的总 Token 消耗（截止到最近一次 LLM 调用）。"
    )

    # ---- 配置 ----
    max_messages: int = Field(
        default=50,
        description="最大保留消息数。超出后进行滑动窗口裁剪。"
    )
    max_tokens: int = Field(
        default=128_000,
        description="最大 Token 数。超出时执行上下文压缩或裁剪。"
    )

    # ---- 校验 ----
    @field_validator('messages')
    @classmethod
    def check_token_limit(cls, messages: list) -> list:
        """验证消息数不超过上限。"""
        if len(messages) > 200:
            raise ValueError("消息数超过 200 条上限")
        return messages

    # ---- 方法 ----
    def add_message(self, message: ConversationMessage) -> "ConversationContext":
        """添加消息到对话历史，自动管理窗口。

        当消息数超过 max_messages 时，移除最早的消息（保留 system 角色消息）。
        """
        import copy
        new_messages = list(self.messages) + [message]

        # 滑动窗口裁剪
        system_messages = [m for m in new_messages if m.role == ConversationRole.SYSTEM]
        non_system = [m for m in new_messages if m.role != ConversationRole.SYSTEM]

        while len(new_messages) > self.max_messages and len(non_system) > 1:
            non_system.pop(0)
            new_messages = system_messages + non_system

        return ConversationContext(
            session_id=self.session_id,
            messages=new_messages,
            intents=list(self.intents),
            current_intent=self.current_intent,
            collected_info=dict(self.collected_info),
            platform=self.platform,
            user_id=self.user_id,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc),
            expired_at=self.expired_at,
            token_count=self.token_count,
            max_messages=self.max_messages,
            max_tokens=self.max_tokens,
        )

    def get_recent_messages(self, count: int = 10) -> list[ConversationMessage]:
        """获取最近的 N 条消息（不包含 system 消息）。"""
        non_system = [m for m in self.messages if m.role != ConversationRole.SYSTEM]
        return non_system[-count:]
