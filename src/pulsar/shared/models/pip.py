from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional
from datetime import datetime, timezone


class PIPRequest(BaseModel):
    """PIP 协议请求模型。

    PIP 用于 Pulsar 内部层间通信，结构与 MCPRequest 相似，
    但使用 target 字段替代 method 的组件前缀，便于内部路由。
    """
    model_config = ConfigDict(frozen=True)

    jsonrpc: str = Field(
        default="2.0",
        description="JSON-RPC 协议版本。固定为 '2.0'。"
    )
    id: str = Field(
        ...,
        description="请求唯一标识符。格式: 'pip_' + UUID 前缀。"
    )
    target: str = Field(
        ...,
        description="目标层/组件标识。例如: 'layer2/intent'、'layer3/orchestrator'、'layer1/tool_registry'。"
    )
    method: str = Field(
        ...,
        description="要调用的方法名称。格式: '<组件>.<动作>'。"
    )
    params: dict = Field(
        default_factory=dict,
        description="方法参数。不同 method 有不同参数结构。"
    )
    context: Optional[dict] = Field(
        default=None,
        description="请求上下文。包含 session_id、user_id、trace_id 等跨层传递的信息。"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="请求发起时间（UTC）。用于超时检测和性能分析。"
    )

    def is_notification(self) -> bool:
        """判断是否为通知消息（无需响应）。"""
        return self.id is None or self.id == ""


class PIPResponse(BaseModel):
    """PIP 协议响应模型。

    内部层间通信的响应，结构与 MCPResponse 一致，
    但由 PipBus 内部路由到对应等待中的请求处理器。
    """
    model_config = ConfigDict(frozen=True)

    jsonrpc: str = Field(
        default="2.0",
        description="JSON-RPC 协议版本。固定为 '2.0'。"
    )
    id: str = Field(
        ...,
        description="对应请求的 ID。用于匹配请求和响应。"
    )
    result: Optional[Any] = Field(
        default=None,
        description="调用结果。成功时返回具体数据，失败时为 None。"
    )
    error: Optional[dict] = Field(
        default=None,
        description="错误信息。失败时返回，包含 code 和 message 字段。"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="响应生成时间（UTC）。"
    )

    def is_success(self) -> bool:
        """判断请求是否执行成功。"""
        return self.error is None

    def is_error(self) -> bool:
        """判断请求是否执行失败。"""
        return self.error is not None


class PIPNotification(BaseModel):
    """PIP 通知模型（服务器推送事件）。

    通知与请求的区别在于没有 id 字段，客户端不需要回复。
    """
    model_config = ConfigDict(frozen=True)

    jsonrpc: str = Field(default="2.0", description="JSON-RPC 协议版本。")
    method: str = Field(
        ...,
        description="事件类型。如 'event/publish'、'task.progress'。"
                    "事件类型命名规则: <域>.<事件名>。"
    )
    params: dict = Field(
        default_factory=dict,
        description="事件参数。包含 type、data 等字段。"
    )


class PIPError(BaseModel):
    """PIP 错误模型。

    标准 JSON-RPC 错误码:
        -32700: 解析错误（JSON 格式不正确）
        -32600: 无效请求
        -32601: 方法未找到
        -32602: 无效参数
        -32603: 内部错误
        -32000 ~ -32099: 服务器端自定义错误

    Pulsar 自定义错误码:
        -32100: 层间路由错误（目标层不可达）
        -32101: 时间超时
        -32102: 认证失败
        -32103: 权限不足
        -32104: 工具执行错误
        -32105: LLM 调用错误（返回不符合预期格式）
        -32106: 平台适配器错误（微信 API 返回错误）
        -32107: 资源限制（超出限频或配额）
    """
    model_config = ConfigDict(frozen=True)

    code: int = Field(
        ...,
        description="错误码。遵循 JSON-RPC 2.0 标准 + Pulsar 自定义扩展。"
    )
    message: str = Field(
        ...,
        description="人类可读的错误描述（中文）。"
    )
    data: Optional[dict] = Field(
        default=None,
        description="错误的附加信息。包含 errcode、stack_trace、retry_after 等调试信息。"
    )


class ActionStep(BaseModel):
    """执行计划中的单个步骤。"""
    model_config = ConfigDict(frozen=True)

    tool: str = Field(
        ...,
        description="工具名称，如 'shell/execute'、'wechat.create_draft'。"
    )
    params: dict = Field(
        default_factory=dict,
        description="工具调用参数。"
    )
    description: str = Field(
        default="",
        description="这一步做什么（自然语言描述）。"
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description="依赖的步骤索引（从 0 开始）。执行前需确保所有依赖步骤已完成。"
    )


class ActionPlan(BaseModel):
    """执行计划模型。

    Layer 2 意图识别产出→Layer 3 编排器消费的完整执行计划。
    """
    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(
        ...,
        description="工作流唯一标识。格式: 'wf_' + UUID（8 位十六进制）。"
                    "用于追踪 ActionPlan 的完整生命周期。"
    )
    steps: list[ActionStep] = Field(
        ...,
        description="执行步骤列表。按依赖关系拓扑排序。"
    )
    user_intent: str = Field(
        ...,
        description="用户意图描述。自然语言形式，如 '在微信公众号发布一篇关于脉冲星的文章'。"
    )
    confidence: float = Field(
        ...,
        description="意图识别置信度（0.0 ~ 1.0）。低于阈值时需用户确认。",
        ge=0.0,
        le=1.0,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ActionPlan 创建时间（UTC）。"
    )
