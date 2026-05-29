"""Pulsar 常量定义 — 枚举与常量"""

from enum import Enum


class Layer(Enum):
    """系统层编号"""
    RUNTIME = 1      # Layer 1: Agent Loop 运行时层
    COGNITION = 2    # Layer 2: 认知分析层
    TASK = 3         # Layer 3: 任务管理层
    EXECUTION = 4    # Layer 4: 执行层
    INTERACTION = 5  # Layer 5: 交互层


class AgentType(Enum):
    """Agent 类型"""
    RUNTIME = "runtime"
    ADAPTER = "adapter"
    TOOL = "tool"
    SKILL = "skill"
    GATEWAY = "gateway"


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(Enum):
    """事件类型"""
    TOOL_CALL = "tool_call"
    SYSTEM_EVENT = "system_event"
    AUTH = "auth"
    PUBLISH = "publish"
    SCHEDULE = "schedule"


# MCP 协议常量
JSONRPC_VERSION = "2.0"

# MCP 方法名
MCP_METHOD_TOOLS_LIST = "tools/list"
MCP_METHOD_TOOLS_CALL = "tools/call"
MCP_METHOD_SYSTEM_PING = "system/ping"
MCP_METHOD_EVENT_PUBLISH = "event/publish"
MCP_METHOD_EVENT_SUBSCRIBE = "event/subscribe"

# 系统默认值
DEFAULT_HEARTBEAT_INTERVAL = 15  # 秒
DEFAULT_MAX_RESTART_ATTEMPTS = 3
DEFAULT_RESTART_DELAY = 5  # 秒
DEFAULT_DRAIN_TIMEOUT = 30  # 秒
DEFAULT_LLM_TIMEOUT = 30  # 秒
DEFAULT_LLM_MAX_RETRIES = 3
DEFAULT_TASK_MAX_RETRIES = 3