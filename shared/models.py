"""Pulsar 核心数据模型 — 基于 Pydantic v2"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime
import uuid


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str
    layer: Literal[1, 2, 3, 4, 5]
    type: Literal["runtime", "adapter", "tool", "skill", "gateway"]
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    """内部 MCP 请求 — JSON-RPC 2.0 子集"""
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    method: str  # tools/call, tools/list, system/ping, event/publish
    params: dict[str, Any] = Field(default_factory=dict)


class MCPResponse(BaseModel):
    """内部 MCP 响应 — JSON-RPC 2.0 子集"""
    jsonrpc: str = "2.0"
    id: str
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class ToolDefinition(BaseModel):
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any]
    agent: str = ""  # 提供此工具的 Agent 名称


class Task(BaseModel):
    """任务模型 — 支持状态机和持久化"""
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    type: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    input: dict[str, Any] = Field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(BaseModel):
    """审计日志条目"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str  # tool_call, system_event, auth
    agent: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    duration_ms: int = 0
    user: str = "system"
    success: bool = True