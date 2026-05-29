# Layer 1: 运行时层（Runtime Layer）

## 概述

运行时层是 Pulsar Agent 框架的基石，负责 Agent 的生命周期管理、进程间通信、LLM 网关、审计日志与健康检查。所有上层模块（交互层、工具层、技能层）均依赖本层提供的基础设施。

---

## 1. PulsarRuntime（runtime/main.py）

### 职责

PulsarRuntime 是 Agent 的主进程入口，基于 `asyncio` 构建事件循环，协调所有子系统的初始化、运行与关闭。

### 核心行为

#### asyncio 主循环与 Agent 生命周期

```
┌─────────────────────────────────────────┐
│            PulsarRuntime                 │
│  ┌───────────────────────────────────┐  │
│  │   asyncio.run(main())             │  │
│  │   ┌─────────┐   ┌───────────┐    │  │
│  │   │  Init   │ → │  Running  │    │  │
│  │   │  Phase  │   │  Phase    │    │  │
│  │   └─────────┘   └─────┬─────┘    │  │
│  │                       │           │  │
│  │              ┌────────▼──────┐   │  │
│  │              │  Shutdown     │   │  │
│  │              │  Phase        │   │  │
│  │              └───────────────┘   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

- **初始化阶段**：加载配置、初始化 PIPBus、注册 Agent 模型、启动 LLM Gateway、开启 HealthChecker 端点
- **运行阶段**：监听信号、处理心跳、接受外部请求、执行 Agent 循环
- **关闭阶段**：触发 drain 逻辑，等待 in-flight requests 完成，强制超时关闭

#### 心跳机制（Heartbeat）

- **间隔**：15 秒一次
- **超时判定**：连续 3 次心跳未响应（45 秒无响应）视为 Agent 失联
- **自动重启**：失联后由 Runtime 自动触发 Agent 重启流程——杀死旧进程、重新初始化、恢复状态
- **实现方式**：在 asyncio 事件循环中注册 `asyncio.Task`，每 15 秒向 HealthChecker 发送 ping

```python
async def _heartbeat_loop(self):
    misses = 0
    while self._running:
        await asyncio.sleep(15)
        if self._health_checker.ping():
            misses = 0
        else:
            misses += 1
            if misses >= 3:
                self._trigger_restart()
```

#### 优雅关闭（Graceful Shutdown）

1. 收到 SIGTERM/SIGINT 信号
2. 通知所有 Agent 进入 draining 模式（停止接受新请求）
3. 等待进行中的任务完成，超时 30 秒
4. 超时后强制终止所有子进程
5. 关闭 PIPBus、审计日志、健康检查服务

#### 配置热重载

- 使用文件监控（inotify 或 polling）监听 config.yaml 变更
- 变更后向相关 Agent 发送配置更新事件
- Agent 可选地处理配置更新或忽略

### 类接口

```python
class PulsarRuntime:
    def __init__(self, config_path: str = "config.yaml"): ...
    
    async def start(self):
        """启动所有 Agent 子系统"""
    
    async def shutdown(self, grace_period: int = 30):
        """优雅关闭"""
    
    def get_agent(self, name: str) -> BaseAgent | None:
        """按名称获取 Agent 实例"""
    
    async def reload_config(self):
        """触发配置热重载"""
```

---

## 2. PIPBus（runtime/pip_bus.py）

### 职责

系统内部消息总线，基于 JSON-RPC 2.0 协议，负责各 Agent 之间的通信路由。

### 通信协议

采用 JSON-RPC 2.0 子集，消息格式统一：

```json
{
  "jsonrpc": "2.0",
  "id": "msg_001",
  "method": "tools/call",
  "params": {
    "name": "wechat_draft_add",
    "arguments": {"title": "...", "content": "..."},
    "source_agent": "conversation_agent",
    "target_agent": "adapter.wechat"
  }
}
```

### 方法清单

| 方法 | 方向 | 用途 |
|------|------|------|
| `tools/call` | 请求→响应 | 调用另一个 Agent 提供的工具 |
| `tools/list` | 请求→响应 | 查询 Agent 提供的工具列表 |
| `event/publish` | 发布→订阅 | Agent 发布事件 |
| `event/subscribe` | 请求→响应 | 订阅事件流 |
| `system/ping` | 请求→响应 | 心跳检测 |
| `system/status` | 请求→响应 | 系统状态查询 |

### 传输层

- **内部子进程**：通过 stdio 传输（JSON 行分隔）
- **同进程 Agent**：通过 asyncio Queue 传输
- **外部 HTTP**：通过 HTTP SSE (Phase 2+)

### 错误处理

| 错误码 | 含义 |
|--------|------|
| -32700 | 解析错误 |
| -32600 | 无效请求 |
| -32601 | 方法不存在 |
| -32104 | 工具执行错误 |
| -32107 | 资源限制（频率限制） |
| -32102 | 认证失败 |

---

## 3. LLM Gateway（gateway/）

### 职责

为系统中所有需要 LLM 能力的组件提供统一的模型调用接口，支持多 Provider 路由、函数调用、流式输出。

### 接口设计

```python
class LLMGateway:
    """LLM 统一调用接口"""
    
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,       # 工具定义（函数调用）
        tool_choice: str | None = None,         # "auto" | "any" | "none"
        stream: bool = False,                   # 流式输出
        response_model: type | None = None,     # 结构化输出
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """统一的 LLM 调用接口"""
    
    async def chat_stream(
        self, messages, tools=None, tool_choice=None, **kwargs
    ) -> AsyncIterator[ChatChunk]:
        """流式版本"""
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本嵌入（Phase 2 RAG 用）"""
```

### Provider 架构

```python
class BaseProvider(ABC):
    """Provider 基类"""
    
    @abstractmethod
    async def chat(self, messages, tools=None, tool_choice=None, stream=False, **kwargs) -> ChatResponse:
        ...
    
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        ...
```

内置 Provider 实现：
- `OpenAIProvider` — 兼容 DeepSeek、OpenAI、Groq 等
- `AnthropicProvider` — Claude API
- `LocalProvider` — 本地模型（llama.cpp / Ollama）

### 路由机制

根据模型名称前缀自动路由：
- `gpt-*` / `deepseek-*` → OpenAIProvider
- `claude-*` → AnthropicProvider
- `local/` → LocalProvider

支持 Provider 降级链：`providers: [deepseek, openai, local]`

### 配置

```yaml
gateway:
  default_provider: deepseek
  fallback_provider: openai
  timeout: 30
  max_retries: 3
  retry_delay: 2
  providers:
    deepseek:
      type: openai
      base_url: "https://api.deepseek.com/v1"
      api_key: "${DEEPSEEK_API_KEY}"
      model: "deepseek-chat"
      model_pattern: "^deepseek-"
```

### 连接池管理（Connection Pooling）

> **性能/伸缩性设计要点**：`httpx.AsyncClient` 应作为 **per-provider 单例** 共享，而非每次请求创建新的客户端实例。每个 LLM Provider（如 `OpenAIProvider`, `AnthropicProvider`, `LocalProvider`）在其初始化时创建一个 `httpx.AsyncClient` 实例，所有发往该 Provider 的请求复用同一个连接池。这样可显著降低 TCP 握手开销、启用 HTTP keep-alive 连接复用，并允许精细控制每个 Provider 的并发连接数。

```python
class BaseProvider(ABC):
    """Provider 基类——每个 Provider 持有自己的 httpx.AsyncClient 连接池"""

    def __init__(self, config: dict):
        self.config = config
        # 每个 Provider 持有独立的连接池，避免 per-request 创建开销
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """懒初始化 httpx 客户端（连接池复用）"""
        if self._client is None:
            limits = httpx.Limits(
                max_keepalive_connections=20,   # 最大 keep-alive 连接数
                max_connections=100,             # 最大并发连接数
                keepalive_expiry=30.0,           # keep-alive 超时（秒）
            )
            self._client = httpx.AsyncClient(
                base_url=self.config.get("base_url", ""),
                timeout=httpx.Timeout(self.config.get("timeout", 30.0)),
                limits=limits,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """关闭连接池——在 Provider 销毁时调用"""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**关键规则**：
- **禁止** 在 `chat()` / `embed()` 等方法内部使用 `async with httpx.AsyncClient() as client:` 创建临时客户端——这会导致每次 LLM 调用都新建 TCP 连接，在高并发场景下产生严重的连接建立开销和端口耗尽风险。
- Provider 实例在 **LLM Gateway 初始化** 时创建，在 **Gateway 关闭** 时统一释放连接池。
- 每个 Provider 的 `connection_pool_size` 可通过配置项单独控制（默认值见配置参考）。

---

## 3.5 LLM 函数调用（Function Calling）支持

> **修正说明**：根据架构评审团队建议，LLM Gateway 必须支持原生函数调用而非脆弱的 JSON 解析。

### Provider 适配要求

| Provider | 工具调用方式 | 结构化输出方式 |
|----------|-------------|---------------|
| OpenAI 兼容 | `tools` 参数 + `tool_choice="auto"` | `response_format={"type": "json_object"}` |
| Anthropic | `tool_use` 系统能力 + `tools` 参数 | JSON mode |
| 本地模型 | 指令提示 + JSON Schema 约束 | 指令提示 |

### 工具定义转换

LLM Gateway 自动将内部 `ToolDefinition` 转换为各 Provider 所需的格式。

### ReAct 循环集成

```python
async def react_loop(gateway, messages, tools):
    """LLM 工具调用循环——Phase 1 由 ConversationAgent 承载"""
    while True:
        response = await gateway.chat(messages, tools=tools, tool_choice="auto")
        
        if response.tool_calls:
            for tc in response.tool_calls:
                result = await execute_tool(tc.name, tc.args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })
        else:
            return response.content
```

---

## 4. AuditLogger（runtime/logging.py）

### 职责

记录所有关键操作的结构化审计日志，支持可观测性和问题追踪。

### 日志格式（JSON Lines）

```json
{
  "timestamp": "2026-05-27T16:30:00Z",
  "event_type": "tool_call",
  "agent": "conversation_agent",
  "action": "understand_intent",
  "params": {"input": "帮我写文章"},
  "result": {"plan": "..."},
  "duration_ms": 1250,
  "user": "cli:admin",
  "success": true
}
```

### 事件类型

| 类型 | 说明 |
|------|------|
| `agent.start` / `agent.stop` / `agent.restart` | Agent 生命周期 |
| `agent.heartbeat_miss` | 心跳丢失 |
| `llm.request` / `llm.response` | LLM 请求和响应 |
| `tool.call` / `tool.result` | 工具调用 |
| `config.reload` | 配置变更 |
| `system.shutdown` | 系统关闭 |

### 配置

```yaml
audit:
  enabled: true
  output: file
  path: "./data/logs/audit.log"
  log_levels: ["tool_call", "system_event", "auth", "llm"]
  rotation: daily
  retention_days: 30
```

---

## 5. HealthChecker（runtime/health.py）

### 职责

监控所有 Agent 的健康状态，提供健康检查端点。

### Agent 状态枚举

```
INIT → RUNNING ↔ DEGRADED → STOPPED
  ↓       ↓         ↓
RESTARTING ←────────┘
```

### 健康检查端点

- **PIP 方法**：`system/ping`（内部使用）
- **HTTP 端点**：`GET /health`（Phase 2，对外暴露）

### 组件级健康报告

```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "agents": {
    "runtime": {"status": "running", "last_heartbeat": "..."},
    "gateway.llm": {"status": "running", "uptime": 3600},
    "adapter.wechat": {"status": "running", "uptime": 3600}
  },
  "metrics": {
    "total_calls": 150,
    "failed_calls": 2,
    "avg_duration_ms": 450
  }
}
```
