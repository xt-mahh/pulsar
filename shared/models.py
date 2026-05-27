from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timezone
import uuid


class AgentConfig(BaseModel):
    name: str
    layer: Literal[1, 2, 3, 4, 5]
    type: Literal["runtime", "adapter", "tool", "skill", "gateway"]
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    method: str
    params: dict = Field(default_factory=dict)


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: Optional[dict] = None
    error: Optional[dict] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict
    agent: str = ""


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    type: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    input: dict = Field(default_factory=dict)
    output: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str
    agent: str
    action: str
    params: dict = Field(default_factory=dict)
    result: Optional[dict] = None
    duration_ms: int = 0
    user: str = "system"
    success: bool = True


class PulsarConfig(BaseModel):
    system: dict = Field(default_factory=dict)
    runtime: dict = Field(default_factory=dict)
    gateway: dict = Field(default_factory=dict)
    adapters: dict = Field(default_factory=dict)
    interaction: dict = Field(default_factory=dict)
    scheduler: dict = Field(default_factory=dict)
    audit: dict = Field(default_factory=dict)