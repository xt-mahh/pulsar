# 配置参考文档 — config.yaml

> 本文档定义了 Pulsar 项目的完整配置模板，包含所有可用配置节、字段说明、默认值及环境变量覆盖方式。

---

## 一、完整配置模板

```yaml
# ============================================================================
# Pulsar 配置文件
# ============================================================================
# 配置加载优先级（从高到低）：
#   1. 环境变量（PULSAR_<SECTION>_<KEY>）
#   2. 命令行参数（--<section>.<key>）
#   3. 配置文件（config.yaml）
#   4. 默认值
# ============================================================================

# ---------------------------------------------------------------------------
# 系统配置
# ---------------------------------------------------------------------------
system:
  # 应用名称（影响日志、审计、指标标签）
  name: "pulsar"
  # 运行环境: development | staging | production
  env: "development"
  # 调试模式（开启后输出更详细的日志和错误信息）
  debug: false
  # 数据目录（存放草稿缓存、会话历史、工具临时文件）
  data_dir: "./data"
  # 时区，如 Asia/Shanghai, UTC
  timezone: "UTC"
  # PID 文件路径（用于进程管理）
  pid_file: "/tmp/pulsar.pid"

# ---------------------------------------------------------------------------
# 运行时配置
# ---------------------------------------------------------------------------
runtime:
  # 最大并发任务数（工具调用、API 请求等）
  max_concurrency: 10
  # 组件优雅关闭超时（秒）
  shutdown_timeout: 15
  # 健康检查间隔（秒）
  health_check_interval: 30
  # 任务执行超时（秒），单个工具/LLM 调用的最大等待时间
  task_timeout: 120
  # 资源限制
  limits:
    # 最大打开文件数
    max_open_files: 1024
    # 最大内存使用（MB），0 表示不限制
    max_memory_mb: 512
    # 工具输出最大大小（字节）
    max_tool_output_bytes: 10485760  # 10 MB

# ---------------------------------------------------------------------------
# LLM Gateway 配置
# ---------------------------------------------------------------------------
gateway:
  # 默认使用的 Provider 名称（对应 providers 中的 key）
  default_provider: "deepseek"

  # 可用 LLM Provider 列表
  providers:
    # DeepSeek
    deepseek:
      # API Base URL
      base_url: "https://api.deepseek.com/v1"
      # API 密钥（推荐使用环境变量：${DEEPSEEK_API_KEY}）
      api_key: "${DEEPSEEK_API_KEY}"
      # 模型名称
      model: "deepseek-chat"
      # 最大 Token 数（输出）
      max_tokens: 4096
      # 温度参数（0.0-2.0）
      temperature: 0.7
      # Top-P 采样
      top_p: 0.95
      # 请求超时（秒）
      timeout: 60
      # 重试配置
      retry:
        # 最大重试次数
        max_retries: 3
        # 重试间隔基数（毫秒，指数退避）
        base_delay_ms: 1000
        # 最大重试间隔（毫秒）
        max_delay_ms: 30000

    # OpenAI（可选备用 Provider）
    openai:
      base_url: "https://api.openai.com/v1"
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o"
      max_tokens: 4096
      temperature: 0.7
      top_p: 0.95
      timeout: 60
      retry:
        max_retries: 3
        base_delay_ms: 1000
        max_delay_ms: 30000

  # 请求缓存配置
  cache:
    # 是否启用 LLM 响应缓存（相同请求命中缓存）
    enabled: false
    # 缓存类型: memory | redis
    type: "memory"
    # 缓存 TTL（秒）
    ttl: 3600
    # Redis 连接地址（仅 type=redis 时使用）
    redis_addr: "localhost:6379"

  # 速率限制
  rate_limit:
    # 每分钟最大请求数
    requests_per_minute: 60
    # 每分钟最大 Token 数
    tokens_per_minute: 100000

# ---------------------------------------------------------------------------
# 适配器配置
# ---------------------------------------------------------------------------
adapters:
  # 微信公众平台适配器
  wechat:
    # 是否启用微信适配器
    enabled: false
    # 微信 API Base URL
    base_url: "https://api.weixin.qq.com"
    # 开发者凭据（单账号模式）
    credentials:
      # AppID（推荐使用环境变量：${WECHAT_APP_ID}）
      app_id: "${WECHAT_APP_ID}"
      # AppSecret（推荐使用环境变量：${WECHAT_APP_SECRET}）
      app_secret: "${WECHAT_APP_SECRET}"
      # Token（用于服务器配置验证）
      token: "${WECHAT_TOKEN}"
      # EncodingAESKey（消息加解密密钥，安全模式下使用）
      encoding_aes_key: "${WECHAT_ENCODING_AES_KEY}"

    # 多账号配置（可选，替代上方单账号 credentials）
    # 当配置了 accounts 列表时，上方的 credentials 作为默认账号
    accounts:
    - name: "main_account"                 # 账号别名，用于日志和路由标识
      enabled: true
      credentials:
        app_id: "${WECHAT_MAIN_APP_ID}"
        app_secret: "${WECHAT_MAIN_APP_SECRET}"
        token: "${WECHAT_MAIN_TOKEN}"
        encoding_aes_key: "${WECHAT_MAIN_AES_KEY}"
      # 每个账号独立的速率限制
      rate_limit:
        token_refresh: 2000                # 每日 Token 刷新次数上限
        publish: 1                         # 每日发布次数上限
        mass_send: 1                       # 每日群发次数上限
      # 每个账号独立的 Token 管理
      token:
        auto_refresh: true
        refresh_ahead_seconds: 300
        storage: "encrypted_file"
        encrypt_key: "${WECHAT_MAIN_TOKEN_KEY}"

    - name: "backup_account"
      enabled: false
      credentials:
        app_id: "${WECHAT_BACKUP_APP_ID}"
        app_secret: "${WECHAT_BACKUP_APP_SECRET}"
        token: "${WECHAT_BACKUP_TOKEN}"
      rate_limit:
        token_refresh: 2000
        publish: 1
        mass_send: 1
      token:
        auto_refresh: true
        refresh_ahead_seconds: 300
        storage: "encrypted_file"
        encrypt_key: "${WECHAT_BACKUP_TOKEN_KEY}"

    # 多账号路由规则：决定哪个账号处理哪个请求
    account_routing:
      # 路由策略: first_available | round_robin | by_platform | fixed
      strategy: "first_available"
      # fixed 模式下指定账号名
      # fixed_account: "main_account"
      # 按内容类型分流（仅 by_platform 策略）
      content_routes:
        topic_tech: "main_account"
        topic_science: "backup_account"

    # 令牌管理
    token:
      # 是否自动刷新令牌
      auto_refresh: true
      # 令牌刷新提前量（秒），在过期前提前刷新
      refresh_ahead_seconds: 300
      # 令牌存储方式: memory | file | encrypted_file
      storage: "encrypted_file"
      # 加密存储密码（推荐环境变量：${WECHAT_TOKEN_ENCRYPT_KEY}）
      encrypt_key: "${WECHAT_TOKEN_ENCRYPT_KEY}"

    # 草稿箱配置
    draft:
      # 最大草稿数（微信限制）
      max_drafts: 100
      # 草稿自动保存间隔（秒）
      auto_save_interval: 60
      # 草稿本地缓存路径
      cache_path: "./data/wechat/drafts"

    # 素材管理
    material:
      # 素材上传超时（秒）
      upload_timeout: 120
      # 临时素材存储路径
      temp_path: "./data/wechat/materials"
      # 图片上传最大尺寸（字节）
      max_image_bytes: 10485760  # 10 MB
      # 音频上传最大尺寸（字节）
      max_audio_bytes: 52428800  # 50 MB
      # 视频上传最大尺寸（字节）
      max_video_bytes: 104857600  # 100 MB

    # 发布配置
    publish:
      # 发布后是否确认
      confirm_before_publish: true
      # 定时发布默认时间（格式: HH:MM，空表示立即发布）
      schedule_time: ""
      # 发布失败后尝试次数
      retry_count: 3

    # 网络配置
    network:
      # 代理地址（如 http://proxy:8080）
      proxy: ""
      # 连接超时（秒）
      connect_timeout: 10
      # 读取超时（秒）
      read_timeout: 30
      # 写入超时（秒）
      write_timeout: 30

    # 每个 Provider 独立速率限制（覆盖全局 gateway.rate_limit）
    # 若不设置则继承全局 gateway.rate_limit 配置
    rate_limit:
      # 每分钟最大 LLM 请求数（针对此适配器下发的 LLM 调用）
      requests_per_minute: 30
      # 每分钟最大 Token 消耗数
      tokens_per_minute: 50000

# ---------------------------------------------------------------------------
# 交互模式配置
# ---------------------------------------------------------------------------
interaction:
  # CLI / REPL 模式
  cli:
    # 是否启用 REPL
    enabled: true
    # 提示符样式
    prompt: "pulsar> "
    # 多行输入模式（允许输入多行代码/文本）
    multiline_mode: true
    # 命令历史文件路径
    history_file: "./data/history"
    # 最大历史记录数
    max_history: 1000
    # 彩色输出
    color_output: true
    # 输出格式: text | json | markdown
    output_format: "text"
    # 对话上下文保留消息数
    context_messages: 20
    # 自动补全
    autocomplete:
      # 是否启用 Tab 自动补全
      enabled: true
      # 补全提示颜色
      hint_color: "cyan"

  # MCP Server 模式（远程调用）
  mcp_server:
    # 是否启用 MCP Server
    enabled: false
    # 监听地址
    host: "0.0.0.0"
    # 监听端口
    port: 9800
    # 传输协议: grpc | http | websocket
    transport: "grpc"
    # TLS 配置
    tls:
      # 是否启用 TLS
      enabled: false
      # 证书文件路径
      cert_file: ""
      # 密钥文件路径
      key_file: ""
    # 鉴权配置
    auth:
      # 鉴权方式: none | token | jwt | mtls
      mode: "token"
      # API Token（mode=token 时使用）
      api_token: "${PULSAR_MCP_TOKEN}"
      # JWT 密钥（mode=jwt 时使用）
      jwt_secret: "${PULSAR_MCP_JWT_SECRET}"
    # 最大连接数
    max_connections: 100
    # 连接空闲超时（秒）
    idle_timeout: 300
    # 消息大小限制（字节）
    max_message_size: 4194304  # 4 MB

# ---------------------------------------------------------------------------
# 任务调度器配置
# ---------------------------------------------------------------------------
scheduler:
  # 是否启用调度器
  enabled: false
  # 调度器类型: memory | redis | database
  type: "memory"
  # 工作线程数
  workers: 4
  # 任务队列最大长度
  queue_size: 1000
  # 任务默认超时（秒）
  task_timeout: 300
  # 轮询间隔（秒），检查是否有到期任务
  poll_interval: 5
  # 最大重试次数
  max_retries: 3
  # 重试间隔（秒）
  retry_delay: 30
  # 任务保留天数（完成后保留多久）
  retention_days: 30

  # Redis 配置（仅 type=redis 时使用）
  redis:
    addr: "localhost:6379"
    password: ""
    db: 0
    # 任务队列 Key 前缀
    key_prefix: "pulsar:scheduler:"

  # 数据库配置（仅 type=database 时使用）
  database:
    # 驱动: sqlite | mysql | postgres
    driver: "sqlite"
    # 数据库连接字符串
    dsn: "./data/pulsar.db"
    # 连接池大小
    pool_size: 10

# ---------------------------------------------------------------------------
# 审计日志配置
# ---------------------------------------------------------------------------
audit:
  # 是否启用审计日志
  enabled: true
  # 审计级别: none | error | warn | info | debug
  level: "info"
  # 输出目标: stdout | file | both
  output: "both"
  # 日志文件路径
  file_path: "./data/audit/audit.log"
  # 日志文件最大大小（MB），超过后轮转
  max_file_size_mb: 100
  # 日志文件最大保留数
  max_backups: 7
  # 日志文件最大保留天数
  max_age_days: 30
  # 是否压缩历史日志文件
  compress: true
  # 输出格式: json | text
  format: "json"
  # 需审计的操作类型（空列表表示审计所有操作）
  # 可选: tool_call, llm_call, publish, login, config_change, error
  filter_operations: []
  # 敏感字段脱敏配置（安全审计要求）
  redact_fields:
    # 是否启用敏感字段脱敏
    enabled: true
    # 需脱敏的字段名列表（支持嵌套路径，如 "credentials.api_key"）
    fields:
      - "api_key"
      - "api_secret"
      - "app_secret"
      - "access_token"
      - "token"
      - "password"
      - "secret"
      - "authorization"
      - "credentials.api_key"
      - "credentials.app_secret"
      - "credentials.encoding_aes_key"
      - "token.encrypt_key"
    # 脱敏替换字符串
    mask: "***REDACTED***"

# ---------------------------------------------------------------------------
# 内容安全配置（安全审计要求）
# ---------------------------------------------------------------------------
content_safety:
  # 是否启用内容安全检查
  enabled: true
  # 检查策略: strict | moderate | lenient
  policy: "moderate"
  # 敏感词检查
  sensitive_words:
    # 敏感词文件路径（每行一个词）
    file_path: "./data/safety/sensitive_words.txt"
    # 检查模式: exact | fuzzy | regex
    mode: "fuzzy"
    # 匹配时的处理方式: reject | flag | replace
    action: "flag"
    # 替换字符（action=replace 时使用）
    replacement: "***"
  # AI 内容审核 API（可选第三方服务）
  ai_review:
    enabled: false
    provider: ""      # 审核服务提供商
    api_key: ""       # API 密钥
    endpoint: ""      # API 端点
    timeout: 10       # 审核超时（秒）

# ---------------------------------------------------------------------------
# 日志配置（系统运行日志，区别于审计日志）
# ---------------------------------------------------------------------------
log:
  # 日志级别: debug | info | warn | error | fatal
  level: "info"
  # 输出目标: stdout | file | both
  output: "both"
  # 日志文件路径
  file_path: "./data/logs/pulsar.log"
  # 日志文件最大大小（MB）
  max_file_size_mb: 50
  # 日志文件最大保留数
  max_backups: 5
  # 日志文件最大保留天数
  max_age_days: 7
  # 是否压缩
  compress: false
  # 输出格式: json | text
  format: "text"
  # 是否显示调用者信息（文件名:行号）
  caller: false

# ---------------------------------------------------------------------------
# 监控与遥测
# ---------------------------------------------------------------------------
telemetry:
  # 是否启用遥测
  enabled: false
  # 指标导出方式: prometheus | stdout | none
  metrics: "none"
  # Prometheus 指标暴露地址
  metrics_addr: ":9090"
  # 链路追踪
  tracing:
    # 追踪导出方式: otlp | stdout | none
    exporter: "none"
    # OTLP 端点
    otlp_endpoint: "http://localhost:4318"
    # 采样率（0.0-1.0）
    sampling_rate: 0.1
```

---

## 二、环境变量参考

| 环境变量 | 对应配置路径 | 说明 | 是否必填 |
|----------|-------------|------|---------|
| `PULSAR_SYSTEM_NAME` | `system.name` | 应用名称 | 否 |
| `PULSAR_SYSTEM_ENV` | `system.env` | 运行环境 | 否 |
| `PULSAR_SYSTEM_DEBUG` | `system.debug` | 调试模式 | 否 |
| `PULSAR_SYSTEM_DATA_DIR` | `system.data_dir` | 数据目录 | 否 |
| `PULSAR_SYSTEM_TIMEZONE` | `system.timezone` | 时区 | 否 |
| `DEEPSEEK_API_KEY` | `gateway.providers.deepseek.api_key` | DeepSeek API 密钥 | **是**（使用 DeepSeek 时） |
| `OPENAI_API_KEY` | `gateway.providers.openai.api_key` | OpenAI API 密钥 | 否（使用 OpenAI 时必填） |
| `WECHAT_APP_ID` | `adapters.wechat.credentials.app_id` | 微信公众号 AppID | **是**（启用微信时） |
| `WECHAT_APP_SECRET` | `adapters.wechat.credentials.app_secret` | 微信公众号 AppSecret | **是**（启用微信时） |
| `WECHAT_TOKEN` | `adapters.wechat.credentials.token` | 微信服务器 Token | 否 |
| `WECHAT_ENCODING_AES_KEY` | `adapters.wechat.credentials.encoding_aes_key` | 消息加解密密钥 | 否 |
| `WECHAT_TOKEN_ENCRYPT_KEY` | `adapters.wechat.token.encrypt_key` | Token 加密存储密钥 | 否 |
| `PULSAR_MCP_TOKEN` | `interaction.mcp_server.auth.api_token` | MCP Server 访问令牌 | 否（启用 MCP Server 且 mode=token 时必填） |
| `PULSAR_MCP_JWT_SECRET` | `interaction.mcp_server.auth.jwt_secret` | MCP Server JWT 密钥 | 否 |
| `PULSAR_CONTENT_SAFETY_ENABLED` | `content_safety.enabled` | 内容安全是否启用 | 否 |
| `PULSAR_CONTENT_SAFETY_POLICY` | `content_safety.policy` | 内容安全检查策略 | 否 |
| `PULSAR_AUDIT_REDACT_ENABLED` | `audit.redact_fields.enabled` | 审计脱敏是否启用 | 否 |
| `PULSAR_SCHEDULER_REDIS_PASSWORD` | `scheduler.redis.password` | Redis 密码 | 否 |

> **环境变量命名规则：** `PULSAR_<SECTION>_<KEY>`，其中 `<SECTION>` 和 `<KEY>` 均为大写，多级嵌套使用下划线连接。
>
> 例如：`adapters.wechat.draft.max_drafts` → `PULSAR_ADAPTERS_WECHAT_DRAFT_MAX_DRAFTS`

---

## 三、配置项默认值速查表

| 配置路径 | 默认值 | 说明 |
|----------|--------|------|
| `system.name` | `"pulsar"` | 应用名称 |
| `system.env` | `"development"` | 运行环境 |
| `system.debug` | `false` | 调试模式 |
| `system.data_dir` | `"./data"` | 数据目录 |
| `system.timezone` | `"UTC"` | 时区 |
| `system.pid_file` | `"/tmp/pulsar.pid"` | PID 文件 |
| `runtime.max_concurrency` | `10` | 最大并发数 |
| `runtime.shutdown_timeout` | `15` | 优雅关闭超时（秒） |
| `runtime.health_check_interval` | `30` | 健康检查间隔（秒） |
| `runtime.task_timeout` | `120` | 任务超时（秒） |
| `runtime.limits.max_open_files` | `1024` | 最大文件数 |
| `runtime.limits.max_memory_mb` | `512` | 最大内存（MB） |
| `runtime.limits.max_tool_output_bytes` | `10485760` | 工具输出最大大小（字节） |
| `gateway.default_provider` | `"deepseek"` | 默认 Provider |
| `gateway.providers.deepseek.base_url` | `"https://api.deepseek.com/v1"` | DeepSeek API 地址 |
| `gateway.providers.deepseek.model` | `"deepseek-chat"` | DeepSeek 模型 |
| `gateway.providers.deepseek.max_tokens` | `4096` | 最大输出 Token |
| `gateway.providers.deepseek.temperature` | `0.7` | 温度参数 |
| `gateway.providers.deepseek.top_p` | `0.95` | Top-P |
| `gateway.providers.deepseek.timeout` | `60` | 请求超时（秒） |
| `gateway.providers.deepseek.retry.max_retries` | `3` | 最大重试次数 |
| `gateway.cache.enabled` | `false` | 是否启用缓存 |
| `gateway.cache.type` | `"memory"` | 缓存类型 |
| `gateway.cache.ttl` | `3600` | 缓存 TTL（秒） |
| `gateway.rate_limit.requests_per_minute` | `60` | 每分钟请求上限 |
| `gateway.rate_limit.tokens_per_minute` | `100000` | 每分钟 Token 上限 |
| `adapters.wechat.enabled` | `false` | 是否启用微信适配器 |
| `adapters.wechat.base_url` | `"https://api.weixin.qq.com"` | 微信 API 地址 |
| `adapters.wechat.token.auto_refresh` | `true` | 自动刷新令牌 |
| `adapters.wechat.token.refresh_ahead_seconds` | `300` | 提前刷新时间（秒） |
| `adapters.wechat.token.storage` | `"encrypted_file"` | 令牌存储方式 |
| `adapters.wechat.draft.max_drafts` | `100` | 最大草稿数 |
| `adapters.wechat.draft.auto_save_interval` | `60` | 自动保存间隔（秒） |
| `adapters.wechat.material.upload_timeout` | `120` | 素材上传超时（秒） |
| `adapters.wechat.publish.confirm_before_publish` | `true` | 发布前确认 |
| `adapters.wechat.publish.retry_count` | `3` | 发布重试次数 |
| `adapters.wechat.network.connect_timeout` | `10` | 连接超时（秒） |
| `interaction.cli.enabled` | `true` | 是否启用 REPL |
| `interaction.cli.prompt` | `"pulsar> "` | REPL 提示符 |
| `interaction.cli.multiline_mode` | `true` | 多行输入模式 |
| `interaction.cli.max_history` | `1000` | 历史记录上限 |
| `interaction.cli.color_output` | `true` | 彩色输出 |
| `interaction.cli.output_format` | `"text"` | 输出格式 |
| `interaction.cli.context_messages` | `20` | 上下文保留消息数 |
| `interaction.cli.autocomplete.enabled` | `true` | 自动补全 |
| `interaction.mcp_server.enabled` | `false` | 是否启用 MCP Server |
| `interaction.mcp_server.host` | `"0.0.0.0"` | MCP Server 监听地址 |
| `interaction.mcp_server.port` | `9800` | MCP Server 端口 |
| `interaction.mcp_server.transport` | `"grpc"` | 传输协议 |
| `interaction.mcp_server.tls.enabled` | `false` | TLS 是否启用 |
| `interaction.mcp_server.auth.mode` | `"token"` | 鉴权方式 |
| `interaction.mcp_server.max_connections` | `100` | 最大连接数 |
| `interaction.mcp_server.idle_timeout` | `300` | 空闲超时（秒） |
| `interaction.mcp_server.max_message_size` | `4194304` | 消息大小上限（字节） |
| `content_safety.enabled` | `true` | 是否启用内容安全 |
| `content_safety.policy` | `"moderate"` | 安全检查策略 |
| `content_safety.sensitive_words.mode` | `"fuzzy"` | 敏感词检查模式 |
| `content_safety.sensitive_words.action` | `"flag"` | 敏感词处理方式 |
| `audit.redact_fields.enabled` | `true` | 是否启用审计脱敏 |
| `audit.redact_fields.mask` | `"***REDACTED***"` | 脱敏替换字符串 |
| `scheduler.enabled` | `false` | 是否启用调度器 |
| `scheduler.type` | `"memory"` | 调度器类型 |
| `scheduler.workers` | `4` | 工作线程数 |
| `scheduler.queue_size` | `1000` | 队列长度 |
| `scheduler.task_timeout` | `300` | 任务超时（秒） |
| `scheduler.poll_interval` | `5` | 轮询间隔（秒） |
| `scheduler.max_retries` | `3` | 最大重试次数 |
| `scheduler.retry_delay` | `30` | 重试间隔（秒） |
| `scheduler.retention_days` | `30` | 任务保留天数 |
| `audit.enabled` | `true` | 是否启用审计 |
| `audit.level` | `"info"` | 审计级别 |
| `audit.output` | `"both"` | 审计输出目标 |
| `audit.max_file_size_mb` | `100` | 审计文件大小上限（MB） |
| `audit.max_backups` | `7` | 审计文件保留数 |
| `audit.max_age_days` | `30` | 审计文件保留天数 |
| `audit.compress` | `true` | 是否压缩审计日志 |
| `audit.format` | `"json"` | 审计日志格式 |
| `log.level` | `"info"` | 日志级别 |
| `log.output` | `"both"` | 日志输出目标 |
| `log.max_file_size_mb` | `50` | 日志文件大小上限（MB） |
| `log.max_backups` | `5` | 日志文件保留数 |
| `log.max_age_days` | `7` | 日志文件保留天数 |
| `log.compress` | `false` | 是否压缩日志 |
| `log.format` | `"text"` | 日志格式 |
| `log.caller` | `false` | 是否显示调用者 |
| `telemetry.enabled` | `false` | 是否启用遥测 |
| `telemetry.metrics` | `"none"` | 指标导出方式 |
| `telemetry.tracing.exporter` | `"none"` | 追踪导出方式 |
| `telemetry.tracing.sampling_rate` | `0.1` | 追踪采样率 |

---

## 四、最小可用配置

```yaml
# config.yaml — 最小配置，仅需设置 API Key 即可运行
system:
  env: "development"

gateway:
  default_provider: "deepseek"
  providers:
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"

interaction:
  cli:
    enabled: true
  mcp_server:
    enabled: false

audit:
  enabled: true
  output: "stdout"
```

只需在执行目录放置此配置并设置 `DEEPSEEK_API_KEY` 环境变量，即可启动 Pulsar REPL 进行对话。

---

## 五、生产环境配置示例

```yaml
system:
  name: "pulsar-prod"
  env: "production"
  data_dir: "/var/lib/pulsar"
  timezone: "Asia/Shanghai"

runtime:
  max_concurrency: 50
  shutdown_timeout: 30
  task_timeout: 300
  limits:
    max_memory_mb: 2048

gateway:
  default_provider: "deepseek"
  providers:
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"
      model: "deepseek-chat"
      max_tokens: 8192
      timeout: 120
      retry:
        max_retries: 5
  cache:
    enabled: true
    type: "redis"
    redis_addr: "redis:6379"

adapters:
  wechat:
    enabled: true
    credentials:
      app_id: "${WECHAT_APP_ID}"
      app_secret: "${WECHAT_APP_SECRET}"
    token:
      storage: "encrypted_file"
    publish:
      confirm_before_publish: true

interaction:
  cli:
    enabled: false
  mcp_server:
    enabled: true
    host: "0.0.0.0"
    port: 9800
    transport: "grpc"
    tls:
      enabled: true
      cert_file: "/etc/pulsar/certs/server.crt"
      key_file: "/etc/pulsar/certs/server.key"
    auth:
      mode: "jwt"
      jwt_secret: "${PULSAR_MCP_JWT_SECRET}"

scheduler:
  enabled: true
  type: "redis"
  workers: 8
  redis:
    addr: "redis:6379"
    db: 1

audit:
  enabled: true
  level: "info"
  output: "file"
  file_path: "/var/log/pulsar/audit.log"
  format: "json"
  redact_fields:
    enabled: true
    fields:
      - "api_key"
      - "app_secret"
      - "access_token"
      - "credentials.app_secret"
      - "token.encrypt_key"
    mask: "***REDACTED***"

content_safety:
  enabled: true
  policy: "moderate"
  sensitive_words:
    file_path: "/etc/pulsar/sensitive_words.txt"
    mode: "fuzzy"
    action: "reject"

log:
  level: "warn"
  output: "file"
  file_path: "/var/log/pulsar/pulsar.log"
  format: "json"

telemetry:
  enabled: true
  metrics: "prometheus"
  metrics_addr: ":9090"
```
