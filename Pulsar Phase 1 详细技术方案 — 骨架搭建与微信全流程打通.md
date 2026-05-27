# Pulsar Phase 1 详细技术方案 — 骨架搭建与微信全流程打通

**Pulsar · 脉冲星** — Phase 1 目标：跑通五层骨架，实现「用户通过 CLI / MCP → 系统内部五层流转 → 向微信完成内容发布」的端到端链路。让第一束脉冲信号穿透星尘，抵达目标。

---

# 一、Phase 1 范围与目标

## 1\.1 核心目标

搭建 Pulsar 系统骨架，打通「交互层 → 执行层 → 运行时层」核心链路，实现微信单平台的端到端内容发布能力。

## 1\.2 范围边界

|范围|包含|不包含|
|---|---|---|
|**Layer 1**|MCP Runtime 主进程、LLM Gateway 基础路由、审计日志|完整监控面板、自动扩缩容、分布式运行时|
|**Layer 2**|基础配置存储、微信平台知识 MD 文件|知识库 RAG 系统、用户记忆持久化、向量数据库|
|**Layer 3**|简易 Cron 调度器、线性任务队列|任务 DAG 规划、资源分配器、进度追踪仪表盘|
|**Layer 4**|Native Tool 框架、微信 MCP Adapter（v2\.0 增强版）|Skill 框架、多平台 Adapter、第三方 MCP 工具发现|
|**Layer 5**|CLI 交互工具、对外 MCP Server|Web Dashboard、微信 Clawbot、飞书 Bot|

## 1\.3 验收标准

* [ ] 用户可通过 CLI 完成：创建草稿 → 上传封面 → 发布文章 → 查看发布状态 → 查看数据统计

* [ ] 外部 Agent（如 Claude Code）可通过 MCP 协议调用上述全流程

* [ ] 微信 MCP Adapter 对接真实微信服务端 API，通过认证后可正常发布

* [ ] LLM Gateway 支持至少 2 个模型提供商（本地 \+ 云端）

* [ ] 系统启动后自动拉起各 Agent 进程，崩溃后自动恢复

* [ ] 所有操作写入审计日志

---

# 二、总体架构与项目结构

## 2\.1 Phase 1 架构图

## 2\.2 项目目录结构

```
pulsar/
├── runtime/                  # Layer 1 - Agent Loop Runtime
│   ├── __init__.py
│   ├── main.py               # 主入口 daemon
│   ├── mcp_bus.py            # 内部 MCP 消息总线
│   ├── lifecycle.py          # Agent 进程生命周期管理
│   ├── config.py             # 配置加载与校验
│   ├── health.py             # 健康检查端点
│   └── logging.py            # 审计日志系统
├── gateway/                  # Layer 1 - LLM Gateway
│   ├── __init__.py
│   ├── router.py             # 多模型路由
│   ├── gateway.py            # LLM 统一调用接口
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── openai.py         # OpenAI 兼容 API
│   │   ├── local.py          # 本地模型 (llama.cpp)
│   │   └── base.py           # 提供商基类
│   └── tokens.py             # Token 计数与预算
├── interaction/              # Layer 5 - 交互层
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py           # CLI 入口
│   │   ├── commands/
│   │   │   ├── publish.py    # 发布相关命令
│   │   │   ├── draft.py      # 草稿管理命令
│   │   │   ├── stats.py      # 数据查询命令
│   │   │   ├── config.py     # 配置管理命令
│   │   │   └── system.py     # 系统管理命令
│   │   └── formats.py        # 输出格式化 (rich)
│   └── mcp_server/
│       ├── __init__.py
│       ├── server.py         # MCP Server 入口
│       └── tools.py          # 对外工具定义
├── execution/                # Layer 4 - 执行层
│   ├── __init__.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py       # 工具注册中心
│   │   ├── base.py           # 工具基类
│   │   └── builtins/
│   │       ├── __init__.py
│   │       ├── http.py       # HTTP 请求
│   │       ├── fileio.py     # 文件读写
│   │       └── image.py      # 图片处理
│   └── adapters/
│       ├── __init__.py
│       ├── base.py           # Adapter 基类
│       └── wechat/
│           ├── __init__.py
│           ├── adapter.py    # 微信 Adapter 主类
│           ├── tools.py      # 微信 MCP 工具定义
│           ├── auth.py       # Token 管理
│           └── models.py     # 微信数据模型
├── task/                     # Layer 3 - 任务管理(基础)
│   ├── __init__.py
│   ├── scheduler.py          # Cron 调度器
│   └── queue.py              # 任务队列
├── cognition/                # Layer 2 - 认知层(基础)
│   ├── __init__.py
│   └── knowledge/
│       ├── wechat/           # 微信平台知识
│       │   ├── rules.md      # 运营规则
│       │   ├── limits.md     # API 限制说明
│       │   └── tips.md       # 最佳实践
│       └── platforms.md      # 各平台概览
├── shared/                   # 共享模型与工具
│   ├── __init__.py
│   ├── models.py             # 核心数据模型
│   ├── errors.py             # 错误类型定义
│   └── constants.py          # 常量定义
├── data/                     # 运行时数据目录
│   ├── state.db              # SQLite 状态数据库
│   └── logs/                 # 日志目录
├── config.yaml               # 主配置文件
├── requirements.txt          # Python 依赖
├── pyproject.toml            # 项目元数据
├── Dockerfile                # Docker 部署
└── README.md                 # 项目文档

```

---

# 三、Layer 1 运行时层详细设计

## 3\.1 MCP Runtime 主进程

**职责**：作为系统主 daemon 运行，负责管理所有 Agent 子进程的生命周期、提供内部 MCP 消息总线，对外暴露健康检查和配置热加载接口。

**核心设计**：

- **进程模型**：Python asyncio 主进程 \+ 多子进程模式。每个 Agent 作为独立子进程运行，通过 stdio 与主进程通信

- **健康检查**：每个子进程每隔 15 秒发送一次心跳 ping；连续 3 次无响应则自动重启

- **配置热加载**：监听 config\.yaml 文件变更（inotify/polling），变更后向相关 Agent 发送配置更新事件

- **优雅关闭**：收到 SIGTERM/SIGINT 后，先通知所有 Agent 进入 draining 模式，等待进行中的任务完成，超时强制终止

```
# runtime/main.py - 核心结构
class PulsarRuntime:
    """Pulsar 系统主运行时"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self.mcp_bus = MCPBus()
        self.lifecycle = AgentLifecycleManager(self.mcp_bus)
        self.health = HealthChecker()
        self.logger = AuditLogger(self.config.logging)
    
    async def start(self):
        """启动所有 Agent 进程"""
        for agent_config in self.config.agents:
            await self.lifecycle.start_agent(agent_config)
        self.health.start_monitoring()
        await self.mcp_bus.listen()
    
    async def shutdown(self, grace_period=30):
        """优雅关闭"""
        await self.lifecycle.drain_all(timeout=grace_period)
        await self.mcp_bus.close()

```

## 3\.2 内部 MCP 消息总线

系统内部 Agent 间的通信协议，采用 JSON\-RPC 2\.0 子集。每个消息通过 stdio 传输，格式统一：

```
{
  "jsonrpc": "2.0",
  "id": "msg_20260527_001",
  "method": "tools/call",
  "params": {
    "name": "wechat_draft_add",
    "arguments": {
      "title": "今日 AI 快讯",
      "content": "...",
      "thumb_media_id": "abc123"
    },
    "source_agent": "cli",
    "target_agent": "adapter.wechat"
  }
}

```

|方法|方向|用途|
|---|---|---|
|`tools/call`|请求→响应|调用另一个 Agent 提供的工具|
|`tools/list`|请求→响应|查询 Agent 提供的工具列表|
|`event/publish`|发布→订阅|Agent 发布事件（如：发布完成、数据更新）|
|`event/subscribe`|请求→响应|订阅事件流|
|`system/ping`|请求→响应|心跳检测|

## 3\.3 LLM Gateway

**职责**：为系统中所有需要 LLM 能力的组件提供统一的模型调用接口

Phase 1 实现基础版本，支持：

- 多提供商抽象（OpenAI 兼容 API → DeepSeek/Claude 等 \+ 本地模型）

- 按配置自动路由（默认模型 \+ Fallback 模型）

- 基础 Token 计数和成本追踪

- 超时控制（30s 默认超时）和重试（3 次指数退避）

```
# config.yaml 中的 Gateway 配置示例
gateway:
  default_provider: deepseek
  fallback_provider: claude
  timeout: 30
  max_retries: 3
  providers:
    deepseek:
      type: openai
      base_url: "https://api.deepseek.com/v1"
      api_key: "sk-xxx"
      model: "deepseek-chat"
      max_tokens: 4096
      cost_per_1k_input: 0.001
      cost_per_1k_output: 0.002
    claude:
      type: anthropic
      api_key: "sk-ant-xxx"
      model: "claude-sonnet-4-20250514"
    local:
      type: openai
      base_url: "http://localhost:8080/v1"
      api_key: "not-needed"
      model: "qwen2.5-14b"

```

## 3\.4 审计日志系统

所有关键操作记录结构化日志：

```
{
  "timestamp": "2026-05-27T16:30:00Z",
  "event_type": "tool_call",
  "agent": "adapter.wechat",
  "tool": "wechat_publish_submit",
  "params": {"media_id": "..."},
  "result": {"status": "success", "publish_id": "..."},
  "duration_ms": 1250,
  "user": "cli:admin"
}

```

Phase 1 日志写入 `data/logs/audit\.log`（JSON Lines 格式），后续可对接 ELK / Loki。

---

# 四、Layer 4 执行层详细设计

## 4\.1 Native Tool 框架

**设计模式**：注册中心模式。所有工具通过装饰器或配置文件注册到全局 Registry，按名称发现和调用。

```
# 工具注册
@tool(name="http_request", description="发送 HTTP 请求")
async def http_request(
    url: str,
    method: str = "GET",
    headers: dict = None,
    body: str = None,
    timeout: int = 30
) -> dict:
    """通用 HTTP 请求工具"""
    ...

# 注册中心用法
registry = ToolRegistry()
registry.register(http_request)
tool = registry.get("http_request")
result = await tool.execute(url="https://api.weixin.qq.com/...")

```

Phase 1 内置工具：

|工具名|用途|
|---|---|
|`http\_request`|HTTP/HTTPS 请求（REST API 调用）|
|`file\_read`|读取文件内容|
|`file\_write`|写入文件|
|`json\_parse`|JSON 解析与校验|
|`image\_process`|图片基础处理（裁剪、缩放、格式转换）|
|`template\_render`|Jinja2 模板渲染（用于文章排版）|

## 4\.2 微信 MCP Adapter v2\.0

**基础**：在现有 `wechat\-official\-account\-mcp v1\.0\.2` 基础上重构升级

### 4\.2\.1 工具清单（完整版）

### 4\.2\.2 Adapter 基类规范

```
# execution/adapters/base.py
class BasePlatformAdapter(ABC):
    """平台适配器基类 — 所有平台 MCP Adapter 必须实现此接口"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def platform(self) -> str: ...
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化适配器（凭据验证等）"""
        ...
    
    @abstractmethod
    async def get_tools(self) -> list[ToolDefinition]:
        """返回此适配器提供的所有工具"""
        ...
    
    @abstractmethod
    async def handle_tool_call(self, name: str, args: dict) -> dict:
        """处理 MCP 工具调用"""
        ...

```

### 4\.2\.3 Token 管理

```
# execution/adapters/wechat/auth.py
class WeChatTokenManager:
    """微信 access_token 管理（带缓存与自动刷新）"""
    
    async def get_token(self) -> str:
        """获取可用 token（优先使用缓存）"""
        if self._token and not self._is_expired():
            return self._token
        return await self._refresh()
    
    async def get_stable_token(self) -> str:
        """获取稳定版 token（推荐用于定时任务）"""
        # POST /cgi-bin/stable_token
        return await self._refresh(stable=True)
    
    async def _refresh(self, stable=False) -> str:
        """从微信服务器获取新 token"""
        url = "https://api.weixin.qq.com/cgi-bin/token"
        # ... access_token / stable_token 获取逻辑

```

### 4\.2\.4 草稿 \+ 发布完整工作流

```
# 端到端发布工作流
async def publish_article(
    title: str,
    content: str,          # 文章正文 HTML
    author: str = "Pulsar",
    digest: str = "",
    thumb_media_id: str = "",
    need_open_comment: bool = True,
    need_publish: bool = True
) -> dict:
    """完整的微信图文发布流程"""
    
    # Step 1: 上传正文中的图片
    # 注意：正文中的图片 URL 必须通过 uploadimg 接口获取
    image_urls = extract_image_urls(content)
    for old_url in image_urls:
        wechat_url = await wechat_upload_image(old_url)
        content = content.replace(old_url, wechat_url)
    
    # Step 2: 创建草稿
    draft = await wechat_draft_add(
        articles=[{
            "title": title[:32],                # 限制 32 字
            "author": author[:16],              # 限制 16 字
            "digest": digest[:128],              # 限制 128 字
            "content": content,                  # < 20K 字符
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 1 if need_open_comment else 0,
        }]
    )
    
    # Step 3: 提交发布
    if need_publish:
        publish_result = await wechat_publish_submit(
            media_id=draft["media_id"]
        )
        return {"draft": draft, "publish": publish_result}
    
    return {"draft": draft}

```

---

# 五、交互层设计

## 5\.1 CLI 交互工具

**定位**：Phase 1 主要的用户交互入口。通过命令行完成所有系统操作。

```
$ pulsar --help
Usage: pulsar [OPTIONS] COMMAND [ARGS]...

  Pulsar · 脉冲星 — 通用自媒体运营智能体

Commands:
  publish   发布内容到平台
  draft     管理草稿箱
  stats     查看运营数据
  config    系统配置管理
  system    系统管理（状态、日志、重启）
  run        启动 Pulsar Daemon

$ pulsar publish wechat \\
    --title "今日 AI 快讯" \\
    --content ./article.md \\
    --cover ./cover.png \\
    --schedule "17:30"

✓ 草稿创建成功
  MediaID: abc123
✓ 发布任务已提交
  PublishID: pub_456
  预计 2-5 分钟后完成

$ pulsar stats wechat --period today

📊 微信今日运营数据
  新增关注: +12
  取关: -3
  净增: +9
  总用户: 1,247
  
  文章阅读 TOP3:
  1. "今日 AI 快讯" — 156 阅读 / 23 分享
  2. "开源项目速览" — 89 阅读 / 12 分享

```

## 5\.2 对外 MCP Server

**定位**：将 Pulsar 的全部能力通过标准 MCP 协议暴露，供外部 Agent（Claude Code、Clawvard、Hermes 等）直接调用。

Phase 1 暴露的 MCP 工具：

|工具名|描述|归属|
|---|---|---|
|`platform\_publish`|发布内容到指定平台|微信 Adapter|
|`platform\_draft\_create`|创建草稿|微信 Adapter|
|`platform\_draft\_list`|草稿列表|微信 Adapter|
|`platform\_stats`|查询运营数据|微信 Adapter|
|`platform\_upload\_media`|上传素材|微信 Adapter|
|`system\_status`|查询系统运行状态|Runtime|
|`task\_schedule`|创建定时任务|任务管理层|
|`task\_list`|查看任务列表|任务管理层|

```
# interaction/mcp_server/tools.py
tools = [
    Tool(
        name="platform_publish",
        description="发布内容到指定内容平台",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "title": {"type": "string", "maxLength": 32},
                "content": {"type": "string", "description": "HTML 正文"},
                "cover_path": {"type": "string", "description": "封面图本地路径"},
                "schedule_time": {"type": "string", "description": "定时发布（可选）"},
            },
            "required": ["platform", "title", "content"]
        }
    ),
    ...
]

```

---

# 六、任务管理层（基础版）

## 6\.1 Cron 调度器

```
# config.yaml 中的调度配置
scheduler:
  jobs:
    - name: "daily_wechat_publish"
      schedule: "0 17 * * *"     # 每天 17:00
      task:
        type: "publish"
        platform: "wechat"
        source: "./plans/daily.yaml"
    
    - name: "hourly_health_check"
      schedule: "0 * * * *"     # 每小时
      task:
        type: "system.health_check"

```

## 6\.2 任务队列

Phase 1 实现简单的 FIFO 内存队列 \+ SQLite 持久化：

- 任务状态机：`pending → running → completed / failed`

- 失败自动重试最多 3 次

- 任务执行记录写入审计日志

---

# 七、技术选型

|组件|技术选型|理由|
|---|---|---|
|编程语言|Python 3\.11\+|团队熟悉、Hermes 生态一致、MCP SDK Python 可用|
|MCP 协议|`mcp` pypi 包 \(Anthropic 官方\)|与外部 Agent 标准兼容|
|进程管理|asyncio \+ subprocess|轻量无额外依赖，stdin/stdout 管道通信|
|配置格式|YAML \(PyYAML\)|可读性强、支持注释|
|状态存储|SQLite \(aiosqlite\)|零配置、嵌入式、Phase 2 可平滑迁移 PostgreSQL|
|CLI 框架|click \+ rich|成熟生态、渲染美观|
|HTTP 客户端|httpx \(async\)|支持 async/await、HTTP/2|
|数据模型|Pydantic v2|类型安全、校验、序列化一站式|
|日志|loguru|结构化日志、按天轮转、彩色输出|
|测试框架|pytest \+ pytest\-asyncio|标准选择|
|部署|Docker \+ systemd|容器化部署 \+ Linux 系统服务兜底|

---

# 八、数据模型定义

```
# shared/models.py — Phase 1 核心数据模型

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str
    layer: Literal[1, 2, 3, 4, 5]
    type: Literal["runtime", "adapter", "tool", "skill", "gateway"]
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class MCPRequest(BaseModel):
    """内部 MCP 请求"""
    jsonrpc: str = "2.0"
    id: str
    method: str         # tools/call, tools/list, system/ping
    params: dict = Field(default_factory=dict)


class MCPResponse(BaseModel):
    """内部 MCP 响应"""
    jsonrpc: str = "2.0"
    id: str
    result: Optional[dict] = None
    error: Optional[dict] = None


class ToolDefinition(BaseModel):
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: dict
    agent: str          # 提供此工具的 Agent


class Task(BaseModel):
    """任务模型"""
    id: str
    type: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    input: dict
    output: Optional[dict] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(BaseModel):
    """审计日志条目"""
    timestamp: datetime
    event_type: str     # tool_call, system_event, auth
    agent: str
    action: str
    params: dict
    result: Optional[dict] = None
    duration_ms: int
    user: str = "system"
    success: bool = True

```

---

# 九、实施计划与里程碑

## 9\.1 Sprint 划分

|Sprint|周期|交付内容|关键里程碑|
|---|---|---|---|
|**Sprint 1**<br>基础骨架|第 1\-3 天|项目脚手架、配置系统、MCP 消息总线、Agent 生命周期管理、数据模型|✅ Runtime 能启动/停止 Agent 进程|
|**Sprint 2**<br>执行层|第 4\-6 天|Tool 注册中心、内置工具、微信 Adapter 核心 \+ 认证 \+ 草稿|✅ 可通过工具框架调用微信草稿 API|
|**Sprint 3**<br>交互 \+ LLM|第 7\-9 天|CLI 命令框架、LLM Gateway 基础、对外 MCP Server、发布模块|✅ 可通过 CLI 完成草稿→发布全流程|
|**Sprint 4**<br>集成与完善|第 10\-12 天|任务调度器、审计日志、全部微信工具覆盖、端到端测试、Docker 部署|✅ 完成 Phase 1 全部验收标准|

## 9\.2 实现顺序依赖

---

# 十、配置系统设计

```
# config.yaml — Pulsar 主配置 (Phase 1)

# ========== 系统基础 ==========
system:
  name: "Pulsar"
  version: "0.1.0"
  data_dir: "./data"
  log_level: "INFO"

# ========== 运行时 ==========
runtime:
  heartbeat_interval: 15        # 心跳间隔(秒)
  max_restart_attempts: 3       # 最大重启次数
  restart_delay: 5              # 重启延迟(秒)
  drain_timeout: 30             # 优雅关闭超时(秒)

# ========== 网关 ==========
gateway:
  default_provider: "deepseek"
  fallback_provider: "local"
  timeout: 30
  max_retries: 3
  retry_delay: 2
  providers:
    deepseek:
      type: openai
      base_url: "https://api.deepseek.com/v1"
      api_key: "${DEEPSEEK_API_KEY}"      # 环境变量
      model: "deepseek-chat"
      max_tokens: 4096
    local:
      type: openai
      base_url: "http://localhost:8080/v1"
      api_key: "not-needed"
      model: "qwen2.5-14b"

# ========== 平台适配器 ==========
adapters:
  wechat:
    enabled: true
    app_id: "${WECHAT_APP_ID}"
    app_secret: "${WECHAT_APP_SECRET}"
    token_cache_ttl: 7200           # Token 缓存时间(秒)
    api_base: "https://api.weixin.qq.com"
    rate_limit:
      max_calls_per_minute: 100
      max_calls_per_hour: 2000

# ========== 交互层 ==========
interaction:
  cli:
    enabled: true
    prompt_format: "rich"           # rich | plain | json
  mcp_server:
    enabled: true
    transport: "stdio"              # stdio | http
    host: "0.0.0.0"
    port: 8910

# ========== 任务管理 ==========
scheduler:
  enabled: true
  jobs:
    - name: "daily_publish"
      schedule: "0 17 * * *"
      task:
        type: "publish"
        platform: "wechat"

# ========== 审计 ==========
audit:
  enabled: true
  output: "file"                    # file | stdout
  path: "./data/logs/audit.log"
  log_levels: ["tool_call", "system_event", "auth"]

```

---

# 十一、与外部系统对接方案

## 11\.1 Claude Code 对接

Claude Code 作为 MCP Client 连接 Pulsar Server：

```
// ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "pulsar": {
      "command": "pulsar",
      "args": ["mcp-server", "--transport", "stdio"]
    }
  }
}

```

之后在 Claude Code 中可直接：

```
/use pulsar publish wechat --title "..." --content ...

```

## 11\.2 Hermes Agent 对接

```
# ~/.hermes/config.yaml
mcp_servers:
  pulsar:
    command: "pulsar"
    args: ["mcp-server", "--transport", "stdio"]

```

## 11\.3 Clawvard 对接

通过 HTTP MCP 传输对接：

```
# Clawvard 工作流中调用 Pulsar MCP 工具
- mcp_call:
    server: pulsar
    tool: platform_publish
    args:
      platform: wechat
      title: "{{ topic }}"
      content: "{{ article }}"

```

---

# 十二、部署方案

## 12\.1 Docker 部署

```
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 创建数据目录
RUN mkdir -p data/logs data/state

# 暴露 MCP HTTP 端口
EXPOSE 8910

# 启动
CMD ["pulsar", "run", "--config", "config.yaml"]

```

## 12\.2 systemd 服务（裸机部署）

```
[Unit]
Description=Pulsar - Universal Social Media Agent
After=network.target

[Service]
Type=simple
User=pulsar
WorkingDirectory=/opt/pulsar
EnvironmentFile=/opt/pulsar/.env
ExecStart=/opt/pulsar/.venv/bin/pulsar run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

```

---

# 十三、Phase 1 验收检查表

|\#|验收项|验证方法|状态|
|---|---|---|---|
|1|Runtime 能启动/停止所有 Agent|`pulsar system status` 显示所有 Agent 健康|☐|
|2|Agent 崩溃后自动重启|kill Agent 进程，`pulsar system status` 显示自动恢复|☐|
|3|LLM Gateway 可调用配置的模型|`pulsar system test\-gateway` 返回 LLM 回复|☐|
|4|微信 token 自动获取/缓存/刷新|首次调用获取 token，第二次使用缓存，过期自动刷新|☐|
|5|微信草稿创建成功|`pulsar draft list wechat` 显示新创建的草稿|☐|
|6|微信发布全流程成功|`pulsar publish wechat \.\.\.` → 公众号实际收到文章|☐|
|7|微信数据统计可查询|`pulsar stats wechat \-\-period yesterday` 返回数据|☐|
|8|外部 MCP 客户端可调用工具|Claude Code 或 curL 调用 MCP Server 并返回结果|☐|
|9|Cron 定时任务触发成功|到设定时间自动执行发布|☐|
|10|审计日志正确记录|查看 data/logs/audit\.log 包含完整操作记录|☐|
|11|Docker 部署运行正常|`docker run pulsar` → 系统正常运行|☐|
|12|配置热加载生效|修改 config\.yaml，系统自动 reload 配置|☐|

---

# 十四、交付物清单

* [ ] Pulsar 源码仓库 \(完整项目结构\)

* [ ] config\.yaml 默认配置

* [ ] 微信 MCP Adapter v2\.0（22\+ 工具）

* [ ] CLI 命令行工具（5 个命令组）

* [ ] 对外 MCP Server（8\+ 工具暴露）

* [ ] Docker 镜像

* [ ] README\.md（安装、配置、使用文档）

* [ ] Phase 1 验收测试报告

---

**Phase 1 核心原则**：\&lt;bold\&gt;先跑通、再优化\&lt;/bold\&gt;。
不追求 Phase 1 就做成完美产品，而是快速构建可运行的骨架。每一层只做 Phase 1 范围定义的最小可行功能，但必须保证链路完整——从用户输入 CLI 命令的那一刻起，信号依次穿透五层，最终变成微信上真实发布的文章。

这就是 Pulsar 的第一束脉冲。

> (注：内容由 AI 生成，请谨慎参考）
