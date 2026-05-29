"""Pulsar 错误类型定义 — 分层错误体系"""


class PulsarError(Exception):
    """Pulsar 基础错误 — 所有自定义错误的基类"""
    code: str = "UNKNOWN_ERROR"
    status_code: int = 500

    def __init__(self, message: str = "", details: dict | None = None):
        self.message = message or self.__doc__ or ""
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigError(PulsarError):
    """配置加载或校验失败"""
    code = "CONFIG_ERROR"
    status_code = 500


class AgentNotFoundError(PulsarError):
    """请求的 Agent 不存在或未注册"""
    code = "AGENT_NOT_FOUND"
    status_code = 404


class ToolCallError(PulsarError):
    """工具调用执行失败"""
    code = "TOOL_CALL_ERROR"
    status_code = 500


class AuthError(PulsarError):
    """认证或授权失败"""
    code = "AUTH_ERROR"
    status_code = 401


class RateLimitError(PulsarError):
    """API 调用频率超限"""
    code = "RATE_LIMIT_ERROR"
    status_code = 429


class TimeoutError(PulsarError):
    """操作超时"""
    code = "TIMEOUT_ERROR"
    status_code = 504


class ValidationError(PulsarError):
    """数据校验失败"""
    code = "VALIDATION_ERROR"
    status_code = 400


class AdapterError(PulsarError):
    """平台适配器错误"""
    code = "ADAPTER_ERROR"
    status_code = 502


class LifecycleError(PulsarError):
    """Agent 生命周期管理错误"""
    code = "LIFECYCLE_ERROR"
    status_code = 500