from typing import Literal

SYSTEM_NAME = "Pulsar"
SYSTEM_VERSION = "0.1.0"

LAYER_RUNTIME = 1
LAYER_COGNITION = 2
LAYER_TASK = 3
LAYER_EXECUTION = 4
LAYER_INTERACTION = 5

AgentType = Literal["runtime", "adapter", "tool", "skill", "gateway"]
TaskStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
EventType = Literal["tool_call", "system_event", "auth"]

MCP_METHODS = {
    "TOOLS_CALL": "tools/call",
    "TOOLS_LIST": "tools/list",
    "EVENT_PUBLISH": "event/publish",
    "EVENT_SUBSCRIBE": "event/subscribe",
    "SYSTEM_PING": "system/ping",
}

DEFAULT_HEARTBEAT_INTERVAL = 15
DEFAULT_MAX_RESTART_ATTEMPTS = 3
DEFAULT_RESTART_DELAY = 5
DEFAULT_DRAIN_TIMEOUT = 30
DEFAULT_GATEWAY_TIMEOUT = 30
DEFAULT_GATEWAY_MAX_RETRIES = 3