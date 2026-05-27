class PulsarError(Exception):
    """Base Pulsar exception."""
    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ToolNotFoundError(PulsarError):
    def __init__(self, name: str):
        super().__init__(f"Tool '{name}' not found", code=-32001)


class AdapterError(PulsarError):
    def __init__(self, platform: str, message: str, code: int = -32002):
        super().__init__(f"[{platform}] {message}", code=code)


class ConfigError(PulsarError):
    def __init__(self, message: str):
        super().__init__(message, code=-32003)


class AuthError(PulsarError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code=-32004)


class AgentNotReadyError(PulsarError):
    def __init__(self, name: str):
        super().__init__(f"Agent '{name}' is not ready", code=-32005)


class TaskError(PulsarError):
    def __init__(self, message: str):
        super().__init__(message, code=-32006)