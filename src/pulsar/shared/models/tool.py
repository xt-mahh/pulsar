from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional
from datetime import datetime, timezone


class ToolDefinition(BaseModel):
    """工具定义模型。

    描述一个可被 LLM 或上层系统调用的工具。
    对应 PIP 协议中 tools/list 返回的每个工具条目。
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description="工具名称。全局唯一，格式为 '<域>.<动作>'。"
                    "例如: wechat.create_draft、file_read、http_request。"
                    "命名规则: 小写字母 + 下划线，不得包含空格。",
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$",
    )
    description: str = Field(
        ...,
        description="工具描述。供 LLM 理解工具用途和何时使用。"
                    "应包含使用场景、限制条件和注意事项。"
    )
    input_schema: dict = Field(
        ...,
        description="输入参数的 JSON Schema（Draft-07 标准）。"
                    "包含 type、properties、required 等字段。"
                    "LLM 根据此 Schema 生成正确的参数。"
    )
    output_schema: dict = Field(
        default_factory=dict,
        description="输出结果的 JSON Schema。可选，用于上层校验返回数据。"
    )
    category: str = Field(
        default="",
        description="工具分类标签。用于分组和过滤，如 'wechat'、'file'、'network'。"
    )
    version: str = Field(
        default="1.0.0",
        description="工具版本号。遵循语义化版本规范。修改 input_schema 时需要升级。"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="工具注册时间。"
    )


class ToolCallRequest(BaseModel):
    """工具调用请求模型。

    对应 PIP 协议中 tools/call 请求的参数体。
    从请求中解析出的结构化工具调用信息。
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description="要调用的工具名称。必须对应一个已注册的 ToolDefinition。"
    )
    arguments: dict = Field(
        default_factory=dict,
        description="工具参数。键值对形式，键和值的结构由对应工具的 input_schema 定义。"
    )
    request_id: str = Field(
        ...,
        description="原始请求 ID。用于追踪工具调用链。格式: 'req_' + UUID。"
    )
    trace_id: str = Field(
        default="",
        description="全链路追踪 ID。在微服务/多进程场景下用于串联所有相关调用。"
    )
    session_id: str = Field(
        default="",
        description="会话 ID。关联到具体的用户对话会话。"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="请求时间戳。"
    )


class ToolCallResult(BaseModel):
    """工具调用结果模型。
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="工具名称。")
    success: bool = Field(..., description="是否执行成功。")
    data: Any = Field(default=None, description="执行返回的数据。")
    error: Optional[str] = Field(default=None, description="执行失败时的错误信息。")
    duration_ms: int = Field(default=0, description="执行耗时（毫秒）。")
    request_id: str = Field(..., description="对应的请求 ID。")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="完成时间戳。")
