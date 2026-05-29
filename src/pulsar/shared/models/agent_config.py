from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
import enum


class AgentStatus(str, enum.Enum):
    """Agent 运行状态枚举。"""
    INIT = "init"               # 初始化中，尚未就绪
    RUNNING = "running"         # 正常运行
    DEGRADED = "degraded"       # 部分组件异常
    STOPPED = "stopped"         # 已停止
    RESTARTING = "restarting"   # 正在重启


class LogLevel(str, enum.Enum):
    """日志级别枚举。"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class Environment(str, enum.Enum):
    """运行环境枚举。"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class RuntimeLimits(BaseModel):
    """运行时资源限制配置模型。

    用于限制 Agent 运行时能使用的系统资源，防止失控行为。
    """
    model_config = ConfigDict(frozen=True)

    max_open_files: int = Field(
        default=1024,
        description="最大同时打开文件数。超出后新文件操作会阻塞等待。",
        ge=64,
        le=65536,
    )
    max_memory_mb: int = Field(
        default=512,
        description="最大内存使用量（MB）。设置为 0 表示不限制。",
        ge=0,
        le=32768,
    )
    max_tool_output_bytes: int = Field(
        default=10_485_760,  # 10 MB
        description="单次工具调用的输出最大字节数。超出部分将被截断。",
        ge=1024,
        le=1_073_741_824,
    )


class AgentConfig(BaseModel):
    """Agent 配置模型（对应 pulsar.yaml 完整配置）。

    该模型在 Agent 启动时从配置文件加载，运行时通过 Config Manager 管理。
    支持热重载：部分字段的修改无需重启进程即可生效。
    """
    model_config = ConfigDict(frozen=True)

    # ---- 系统配置 ----
    name: str = Field(
        default="pulsar",
        description="应用名称。影响日志文件名、审计标签、指标维度。"
    )
    env: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="运行环境。影响日志级别、错误处理行为、调试输出。"
    )
    debug: bool = Field(
        default=False,
        description="调试模式开关。开启后输出更详细的日志和原始错误栈。"
    )
    data_dir: str = Field(
        default="./data",
        description="数据目录。存放草稿缓存、会话历史、工具临时文件、Token 持久化存储。"
    )
    timezone: str = Field(
        default="UTC",
        description="系统时区。影响日志时间戳和定时发布计算。格式: 时区名称如 Asia/Shanghai。"
    )
    pid_file: str = Field(
        default="/tmp/pulsar.pid",
        description="PID 文件路径。用于进程管理和单实例检测。"
    )

    # ---- 运行时配置 ----
    max_concurrency: int = Field(
        default=10,
        description="最大并发任务数。同时执行中的工具调用和 API 请求数量上限。",
        ge=1,
        le=100,
    )
    shutdown_timeout: int = Field(
        default=15,
        description="优雅关闭的超时时间（秒）。超时后强制终止未完成的任务。",
        ge=5,
        le=120,
    )
    health_check_interval: int = Field(
        default=30,
        description="健康检查间隔（秒）。HealthChecker 的探测频率。",
        ge=5,
        le=300,
    )
    task_timeout: int = Field(
        default=120,
        description="单个工具或 LLM 调用的最大等待时间（秒）。超时后触发重试。",
        ge=10,
        le=600,
    )
    limits: RuntimeLimits = Field(
        default_factory=RuntimeLimits,
        description="资源限制配置。",
    )

    # ---- LLM 网关配置 ----
    default_provider: str = Field(
        default="deepseek",
        description="默认使用的 LLM Provider 名称。需在 providers 列表中存在。"
    )

    # ---- 适配器配置 ----
    wechat_enabled: bool = Field(
        default=False,
        description="是否启用微信适配器。为 False 时不会加载 WeChatAdapter。"
    )

    # ---- 审计日志配置 ----
    audit_enabled: bool = Field(default=True, description="是否启用审计日志记录。")
    audit_level: LogLevel = Field(default=LogLevel.INFO, description="审计日志级别。")
    audit_output: str = Field(default="both", description="审计输出目标: stdout | file | both。")

    # ---- 交互配置 ----
    cli_enabled: bool = Field(default=True, description="是否启用 CLI/REPL 模式。")
    cli_prompt: str = Field(default="pulsar> ", description="CLI 提示符字符串。")
    cli_context_messages: int = Field(default=20, description="对话上下文保留的消息数量。")
    mcp_server_enabled: bool = Field(default=False, description="是否启用 MCP Server 模式。")

    # ---- 元数据 ----
    config_hash: str = Field(
        default="",
        description="配置文件内容的 SHA-256 哈希。用于热重载检测和审计追踪。"
    )
    loaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="配置加载时间（UTC）。用于判断配置是否为最新。"
    )
