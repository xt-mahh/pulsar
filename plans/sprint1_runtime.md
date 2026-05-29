# Pulsar Phase 1 Sprint 1 — runtime/ 模块详细计划

> 本文档描述 `runtime/` 模块的设计方案，包含 MCP 消息总线、Agent 生命周期管理、健康检查、审计日志、配置管理、事件系统等核心组件。
> runtime 是系统的运行底座，一切智能体能力的基础保障。

---

## 一、模块定位

**职责**：提供系统运行时的基础设施，包括：
- Agent 进程/协程生命周期管理
- 内部 MCP 消息总线（Agent 间通信）
- 健康检查与自动恢复
- 审计日志记录
- 配置加载与热加载
- 系统事件定义与分发

**设计原则**：
- **无循环依赖** — 通过 AgentRegistry 解耦 MCPBus 与 LifecycleManager
- **事件驱动** — 健康检查、配置变更等通过事件总线通信
- **异步非阻塞** — 所有 I/O 操作使用 asyncio
- **故障隔离** — 子进程 Agent 崩溃不影响主进程

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `runtime/__init__.py` | P0 | 无 |
| 2 | `runtime/events.py` | P0 | shared |
| 3 | `runtime/registry.py` | P0 | shared |
| 4 | `runtime/config.py` | P0 | shared |
| 5 | `runtime/agent_runner.py` | P0 | shared |
| 6 | `runtime/logging.py` | P0 | shared |
| 7 | `runtime/mcp_bus.py` | P0 | registry, events |
| 8 | `runtime/lifecycle.py` | P0 | registry, agent_runner, events |
| 9 | `runtime/health.py` | P0 | mcp_bus, events |
| 10 | `runtime/main.py` | P0 | 以上全部 |

---

## 三、`runtime/events.py` 设计方案

### 3.1 职责

定义系统内部事件类型和事件数据结构，作为事件驱动架构的基础。

### 3.2 事件类型枚举

```python
class HealthEvent:
    """健康检查事件 — 由 HealthChecker 发布"""
    AGENT_UNREACHABLE = "health.agent_unreachable"    # Agent 无响应
    AGENT_RECOVERED = "health.agent_recovered"        # Agent 恢复
    AGENT_RESTARTING = "health.agent_restarting"      # Agent 正在重启
    AGENT_RESTART_FAILED = "health.agent_restart_failed"  # 重启失败

class LifecycleEvent:
    """生命周期事件 — 由 LifecycleManager 发布"""
    AGENT_STARTED = "lifecycle.agent_started"          # Agent 启动
    AGENT_STOPPED = "lifecycle.agent_stopped"          # Agent 停止
    AGENT_CRASHED = "lifecycle.agent_crashed"          # Agent 崩溃

class ConfigEvent:
    """配置变更事件 — 由 ConfigWatcher 发布"""
    CONFIG_CHANGED = "config.changed"                  # 配置变更
    CONFIG_ERROR = "config.error"                      # 配置错误
```

### 3.3 事件数据结构

```python
@dataclass
class SystemEvent:
    """系统事件通用结构"""
    type: str                    # 事件类型（如 "health.agent_unreachable"）
    source: str                  # 事件来源（如 "health_checker"）
    timestamp: datetime          # 事件时间
    data: dict                   # 事件负载数据
    severity: str = "info"       # 严重级别：debug / info / warning / error / critical
```

### 3.4 事件订阅接口

```python
class EventBus(ABC):
    """事件总线接口 — MCPBus 实现此接口提供事件能力"""
    
    @abstractmethod
    async def publish(self, event: SystemEvent) -> None:
        """发布事件到总线"""
    
    @abstractmethod
    async def subscribe(self, event_type: str, callback: Callable) -> str:
        """订阅事件，返回订阅 ID（用于取消订阅）"""
    
    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """取消订阅"""
```

### 3.5 设计要点

- 事件类型使用点分隔的字符串（`"health.agent_unreachable"`），支持通配符订阅（如 `"health.*"`）
- 事件数据结构使用 `@dataclass` 而非 Pydantic，保持轻量
- `EventBus` 作为抽象接口由 `MCPBus` 实现，避免循环依赖

---

## 四、`runtime/registry.py` 设计方案

### 4.1 职责

服务注册表，管理所有 Agent 的地址和能力信息，为 MCPBus 提供路由查询，为 LifecycleManager 提供注册/注销接口。

### 4.2 核心数据结构

```python
@dataclass
class AgentInfo:
    """Agent 注册信息"""
    name: str                          # Agent 唯一标识名
    capabilities: list[str]            # 能力标签列表
    transport: TransportInfo           # 传输地址信息
    runner_type: str                   # 运行模式（subprocess / inprocess）
    status: str = "stopped"            # 当前状态
    started_at: Optional[datetime] = None  # 启动时间
    metadata: dict = field(default_factory=dict)  # 附加元数据

@dataclass
class TransportInfo:
    """传输地址信息"""
    type: str                          # stdio / tcp / memory
    address: str                       # 地址标识
```

### 4.3 核心接口

```python
class AgentRegistry:
    """服务注册表 — 线程安全，支持事件通知"""
    
    async def register(self, info: AgentInfo) -> None:
        """注册 Agent
        - 如果同名 Agent 已存在，覆盖旧记录
        - 发布 RegistryEvent.REGISTERED
        """
    
    async def unregister(self, name: str) -> None:
        """注销 Agent
        - 如果 Agent 不存在，抛出 AgentNotFoundError
        - 发布 RegistryEvent.UNREGISTERED
        """
    
    def resolve(self, name: str) -> Optional[AgentInfo]:
        """按名称查找 Agent
        - 返回 AgentInfo 或 None
        - O(1) 哈希表查找
        """
    
    def resolve_by_capability(self, capability: str) -> list[AgentInfo]:
        """按能力标签查找 Agent
        - 返回所有提供该能力的 Agent 列表
        - 用于按需路由（如查找谁提供 wechat_draft_add）
        """
    
    def list_agents(self) -> list[AgentInfo]:
        """列出所有已注册 Agent"""
    
    def watch(self) -> AsyncIterator[RegistryEvent]:
        """监听注册表变更事件流
        - 用于 MCPBus 更新路由缓存
        - 用于 HealthChecker 获取待检查 Agent 列表
        """
```

### 4.4 内部数据结构

```python
class AgentRegistry:
    _agents: dict[str, AgentInfo]           # name → AgentInfo
    _capability_index: dict[str, set[str]]  # capability → set[name]
    _listeners: list[asyncio.Queue]         # 事件监听者队列
    _lock: asyncio.Lock                     # 并发安全
```

### 4.5 设计要点

- **双索引**：名称索引（`_agents`）用于 O(1) 精确查找；能力索引（`_capability_index`）用于按能力标签查找
- **线程安全**：使用 `asyncio.Lock` 保护所有写操作
- **事件通知**：注册表变更时通知所有监听者，用于 MCPBus 更新路由缓存
- **纯内存**：Sprint 1 不持久化，系统重启后重新注册

---

## 五、`runtime/config.py` 设计方案

### 5.1 职责

配置加载、校验、环境变量替换、热加载监听。

### 5.2 核心接口

```python
class ConfigManager:
    """配置管理器 — 加载、校验、提供配置访问"""
    
    def __init__(self, config_path: str):
        """初始化，不立即加载"""
    
    async def load(self) -> dict:
        """加载配置文件
        1. 读取 YAML 文件
        2. 替换 ${ENV_VAR} 环境变量
        3. 使用 Pydantic 校验
        4. 返回完整配置字典
        """
    
    def get(self, key: str, default=None):
        """获取配置值，支持点号路径（如 "runtime.heartbeat_interval"）"""
    
    def get_agents_config(self) -> list[AgentConfig]:
        """获取所有 Agent 配置列表"""
    
    def get_gateway_config(self) -> dict:
        """获取 LLM Gateway 配置"""
    
    def get_audit_config(self) -> dict:
        """获取审计日志配置"""
    
    def reload(self) -> dict:
        """重新加载配置（热加载时调用）"""


class ConfigWatcher:
    """配置热加载监听器 — 使用 watchdog 监听文件变更"""
    
    def __init__(self, config_path: str, on_change: Callable[[dict], Awaitable[None]]):
        """初始化监听器"""
    
    def start(self) -> None:
        """启动文件监听（非阻塞）"""
    
    def stop(self) -> None:
        """停止文件监听"""
```

### 5.3 环境变量替换规则

```python
# 支持格式
${VAR_NAME}           # 必须设置，未设置则抛出 ConfigError
${VAR_NAME:-default}  # 可选，未设置时使用默认值
${VAR_NAME:?error}    # 必须设置，未设置时抛出自定义错误信息

# 示例
api_key: "${DEEPSEEK_API_KEY}"
app_id: "${WECHAT_APP_ID:-default_app_id}"
```

### 5.4 配置校验规则

| 校验项 | 规则 | 错误类型 |
|--------|------|----------|
| `system.name` | 非空字符串 | ConfigValidationError |
| `runtime.heartbeat_interval` | 整数，5-60 | ConfigValidationError |
| `runtime.max_restart_attempts` | 整数，1-10 | ConfigValidationError |
| `runtime.drain_timeout` | 整数，10-120 | ConfigValidationError |
| `gateway.timeout` | 整数，5-120 | ConfigValidationError |
| `gateway.providers` | 至少一个 provider | ConfigValidationError |
| `adapters.*.enabled` | 布尔值 | ConfigValidationError |
| `audit.enabled` | 布尔值 | ConfigValidationError |

### 5.5 热加载流程

```
1. watchdog 检测到文件修改事件
2. ConfigWatcher._debounced_reload() 启动 500ms 防抖
3. 防抖结束后调用 ConfigManager.reload()
4. 新配置校验通过 → 发布 ConfigEvent.CONFIG_CHANGED
5. 新配置校验失败 → 发布 ConfigEvent.CONFIG_ERROR，保留旧配置
6. PulsarRuntime 收到 CONFIG_CHANGED → 通知相关 Agent
```

### 5.6 设计要点

- **防抖机制**：500ms 内多次修改只触发一次重载，避免频繁重载
- **安全回退**：新配置校验失败时保留旧配置，系统不中断
- **环境变量**：支持默认值和必填两种模式，敏感信息不硬编码
- **路径访问**：支持点号路径语法（`config.get("runtime.heartbeat_interval")`）

---

## 六、`runtime/agent_runner.py` 设计方案

### 6.1 职责

提供统一的 Agent 运行抽象，支持子进程和协程两种运行模式。

### 6.2 抽象基类

```python
class AgentRunner(ABC):
    """Agent 运行器抽象基类"""
    
    @abstractmethod
    async def start(self) -> None:
        """启动 Agent"""
    
    @abstractmethod
    async def stop(self) -> None:
        """停止 Agent"""
    
    @abstractmethod
    async def is_alive(self) -> bool:
        """检查 Agent 是否存活"""
    
    @abstractmethod
    async def ping(self) -> bool:
        """健康探测（发送 ping 并等待 pong）"""
    
    @abstractmethod
    def get_transport(self) -> TransportInfo:
        """获取 Agent 的传输地址信息"""
    
    @abstractmethod
    async def send_message(self, message: str) -> None:
        """发送消息到 Agent"""
    
    @abstractmethod
    async def read_message(self) -> Optional[str]:
        """从 Agent 读取消息"""
```

### 6.3 SubprocessRunner 实现

```python
class SubprocessRunner(AgentRunner):
    """子进程运行器 — 适用于需要故障隔离的 Agent"""
    
    def __init__(self, name: str, command: list[str], env: dict = None):
        self.name = name
        self.command = command          # 启动命令，如 ["python", "-m", "pulsar.adapter.wechat"]
        self.env = env or {}            # 额外环境变量
        self._process: Optional[asyncio.subprocess.Process] = None
        self._transport: Optional[TransportInfo] = None
    
    async def start(self):
        """启动子进程
        1. 使用 asyncio.create_subprocess_exec 创建进程
        2. 连接 stdin/stdout 管道
        3. 设置 TransportInfo(type="stdio", address="stdin")
        """
    
    async def stop(self):
        """停止子进程
        1. 发送 SIGTERM
        2. 等待 grace_period 秒
        3. 未退出则发送 SIGKILL
        """
    
    async def is_alive(self) -> bool:
        """检查进程是否存活（returncode is None）"""
    
    async def ping(self) -> bool:
        """发送 system/ping 消息并等待响应"""
    
    def get_transport(self) -> TransportInfo:
        """返回 TransportInfo(type="stdio", address="stdin")"""
    
    async def send_message(self, message: str):
        """写入 stdin"""
    
    async def read_message(self) -> Optional[str]:
        """从 stdout 读取一行"""
```

### 6.4 InProcessRunner 实现

```python
class InProcessRunner(AgentRunner):
    """进程内运行器 — 适用于高频调用的轻量 Agent"""
    
    def __init__(self, name: str, factory: Callable[[], Awaitable[Agent]]):
        self.name = name
        self.factory = factory          # Agent 工厂函数
        self._task: Optional[asyncio.Task] = None
        self._agent: Optional[Agent] = None
        self._queue: Optional[asyncio.Queue] = None
        self._transport: Optional[TransportInfo] = None
    
    async def start(self):
        """启动协程 Agent
        1. 调用 factory() 创建 Agent 实例
        2. 创建 asyncio.Task 运行 Agent 主循环
        3. 设置 TransportInfo(type="memory", address="queue:name")
        """
    
    async def stop(self):
        """停止协程 Agent
        1. 向 Agent 发送停止信号
        2. 等待 Task 完成（带超时）
        3. 超时则 cancel()
        """
    
    async def is_alive(self) -> bool:
        """检查 Task 是否存活（not done()）"""
    
    async def ping(self) -> bool:
        """通过内存队列发送 ping 并等待 pong"""
    
    def get_transport(self) -> TransportInfo:
        """返回 TransportInfo(type="memory", address="queue:name")"""
    
    async def send_message(self, message: str):
        """写入内存队列"""
    
    async def read_message(self) -> Optional[str]:
        """从内存队列读取"""
```

### 6.5 选择策略

```python
def create_runner(config: AgentConfig) -> AgentRunner:
    """根据配置创建合适的运行器"""
    if config.runner == "subprocess":
        return SubprocessRunner(
            name=config.name,
            command=config.config.get("command", ["python", "-m", f"pulsar.{config.name}"]),
            env=config.config.get("env", {}),
        )
    elif config.runner == "inprocess":
        return InProcessRunner(
            name=config.name,
            factory=config.config.get("factory"),
        )
    else:
        raise ConfigError(f"Unknown runner type: {config.runner}")
```

### 6.6 设计要点

- **统一接口**：无论子进程还是协程，对外暴露相同的 `AgentRunner` 接口
- **故障隔离**：SubprocessRunner 崩溃不影响主进程；InProcessRunner 异常由 Task 包装
- **传输抽象**：子进程用 stdio 通信，协程用内存队列通信，对上层透明
- **可扩展**：未来可添加 `DockerRunner`、`SSHRunner` 等实现

---

## 七、`runtime/logging.py` 设计方案

### 7.1 职责

异步审计日志系统，记录所有关键操作，支持批量写入和查询。

### 7.2 核心接口

```python
class AuditLogger:
    """异步审计日志记录器"""
    
    async def start(self) -> None:
        """启动日志系统
        1. 创建日志目录
        2. 打开日志文件
        3. 启动后台写入任务
        """
    
    async def log(self, event: AuditLog) -> None:
        """记录审计日志（非阻塞）
        1. 将事件放入队列
        2. 队列满时降级到 stderr
        """
    
    async def log_tool_call(self, agent: str, tool: str, params: dict,
                            result: dict, duration_ms: int, success: bool) -> None:
        """便捷方法：记录工具调用"""
    
    async def query(self, event_type: str = None, agent: str = None,
                    start_time: datetime = None, end_time: datetime = None,
                    limit: int = 100) -> list[AuditLog]:
        """查询审计日志（支持按类型/Agent/时间过滤）"""
    
    async def stop(self) -> None:
        """停止日志系统
        1. 刷新队列中剩余日志
        2. 关闭文件
        3. 取消后台任务
        """
    
    async def flush(self) -> None:
        """强制刷新队列到文件"""
```

### 7.3 内部实现

```python
class AuditLogger:
    _queue: asyncio.Queue[AuditLog]       # 异步队列
    _flush_task: asyncio.Task              # 后台批量写入任务
    _file: Optional[AsyncIOFile]           # 日志文件句柄
    _config: dict                          # 审计配置
    
    async def _flush_loop(self):
        """后台循环：每 0.5s 或队列满 10 条时批量写入"""
        while True:
            batch = []
            try:
                # 等待第一条日志或超时
                first = await asyncio.wait_for(
                    self._queue.get(), timeout=AUDIT_FLUSH_INTERVAL
                )
                batch.append(first)
                # 尽可能多地收集
                while len(batch) < AUDIT_FLUSH_BATCH_SIZE and not self._queue.empty():
                    batch.append(self._queue.get_nowait())
            except asyncio.TimeoutError:
                continue
            
            # 批量写入
            lines = [log.model_dump_json() for log in batch]
            await self._file.writelines(f"{line}\n" for line in lines)
            await self._file.flush()
```

### 7.4 设计要点

- **异步非阻塞**：`log()` 仅入队，不阻塞调用方
- **批量写入**：合并多条日志后批量写入，减少 I/O 次数
- **队列降级**：队列满时日志写入 stderr，不丢失关键信息
- **JSON Lines 格式**：每行一个 JSON 对象，便于后续对接 ELK/Loki

---

## 八、`runtime/mcp_bus.py` 设计方案

### 8.1 职责

内部 MCP 消息总线，负责 Agent 间的消息路由和事件发布/订阅。

### 8.2 核心接口

```python
class MCPBus(EventBus):
    """内部 MCP 消息总线 — 实现 EventBus 接口"""
    
    async def start(self) -> None:
        """启动消息总线"""
    
    async def stop(self) -> None:
        """停止消息总线"""
    
    async def send_request(self, target_agent: str, request: MCPRequest,
                           timeout: float = 30) -> MCPResponse:
        """发送请求并等待响应（RPC 模式）
        1. 通过 Registry 查找目标 Agent 的 TransportInfo
        2. 通过对应的 AgentRunner 发送消息
        3. 等待响应或超时
        """
    
    async def send_notification(self, target_agent: str, method: str,
                                params: dict = None) -> None:
        """发送通知（无需响应）"""
    
    async def broadcast(self, method: str, params: dict = None) -> None:
        """广播消息给所有 Agent"""
    
    # EventBus 接口实现
    async def publish(self, event: SystemEvent) -> None:
        """发布事件到总线"""
    
    async def subscribe(self, event_type: str, callback: Callable) -> str:
        """订阅事件，返回订阅 ID"""
    
    async def unsubscribe(self, subscription_id: str) -> None:
        """取消订阅"""
```

### 8.3 消息路由流程

```
send_request("adapter.wechat", request)
  │
  ├─ 1. registry.resolve("adapter.wechat") → AgentInfo
  │     └─ 未找到 → 抛出 AgentNotFoundError
  │
  ├─ 2. 根据 transport.type 获取对应的 AgentRunner
  │     ├─ "stdio" → SubprocessRunner
  │     ├─ "memory" → InProcessRunner
  │     └─ 未知 → 抛出 ProtocolError
  │
  ├─ 3. runner.send_message(json.dumps(request))
  │
  ├─ 4. 等待响应（asyncio.wait_for，默认 30s）
  │     └─ 超时 → 抛出 TimeoutError
  │
  └─ 5. 解析响应 → 返回 MCPResponse
```

### 8.4 事件订阅实现

```python
class MCPBus:
    _subscriptions: dict[str, list[tuple[str, Callable]]]  # event_type → [(sub_id, callback)]
    _pending_responses: dict[str, asyncio.Future]          # msg_id → Future
    
    async def publish(self, event: SystemEvent):
        """发布事件：遍历所有匹配的订阅者，异步调用回调"""
        for event_pattern, subscribers in self._subscriptions.items():
            if fnmatch.fnmatch(event.type, event_pattern):
                for sub_id, callback in subscribers:
                    asyncio.create_task(callback(event))
    
    async def subscribe(self, event_type: str, callback: Callable) -> str:
        """订阅事件：支持通配符（如 "health.*"）"""
        sub_id = f"sub_{uuid4().hex[:8]}"
        self._subscriptions.setdefault(event_type, []).append((sub_id, callback))
        return sub_id
```

### 8.5 设计要点

- **RPC + 事件双模式**：`send_request` 用于请求-响应模式，`publish/subscribe` 用于事件驱动模式
- **通配符订阅**：支持 `"health.*"` 匹配所有健康检查事件
- **超时控制**：所有 RPC 调用有超时，默认 30s
- **Future 管理**：`_pending_responses` 管理等待中的响应，超时自动取消

---

## 九、`runtime/lifecycle.py` 设计方案

### 9.1 职责

Agent 生命周期管理器，负责 Agent 的启动、停止、重启、状态管理。

### 9.2 核心接口

```python
class LifecycleManager:
    """Agent 生命周期管理器"""
    
    def __init__(self, registry: AgentRegistry, mcp_bus: MCPBus, config: ConfigManager):
        self._registry = registry
        self._bus = mcp_bus
        self._config = config
        self._runners: dict[str, AgentRunner] = {}  # name → AgentRunner
    
    async def start_agent(self, agent_config: AgentConfig) -> None:
        """启动单个 Agent
        1. 创建 AgentRunner（根据配置选择 subprocess/inprocess）
        2. 调用 runner.start()
        3. 注册到 Registry
        4. 发布 LifecycleEvent.AGENT_STARTED
        """
    
    async def stop_agent(self, name: str) -> None:
        """停止单个 Agent
        1. 从 Registry 注销
        2. 调用 runner.stop()
        3. 发布 LifecycleEvent.AGENT_STOPPED
        """
    
    async def restart_agent(self, name: str) -> None:
        """重启 Agent（先 stop 再 start）"""
    
    async def start_all(self) -> None:
        """启动所有已启用的 Agent（从配置读取）"""
    
    async def stop_all(self) -> None:
        """停止所有 Agent"""
    
    async def drain_all(self, timeout: float = 30) -> None:
        """优雅关闭所有 Agent
        1. 先通知所有 Agent 进入 draining 模式
        2. 等待进行中的任务完成（最多 timeout 秒）
        3. 强制停止未退出的 Agent
        """
    
    def get_agent_status(self, name: str) -> str:
        """获取 Agent 状态"""
    
    def get_all_status(self) -> dict[str, str]:
        """获取所有 Agent 状态"""
    
    async def handle_crash(self, name: str) -> None:
        """处理 Agent 崩溃
        1. 检查重启次数是否超过限制
        2. 未超限 → 等待 restart_delay 后重启
        3. 已超限 → 标记为 crashed，不自动重启
        """
```

### 9.3 启动流程

```
start_all()
  │
  ├─ 1. 从 ConfigManager 获取所有 Agent 配置
  │
  ├─ 2. 过滤 enabled=True 的 Agent
  │
  ├─ 3. 按 layer 排序（先启动下层 Agent）
  │     Layer 1 → Layer 2 → ... → Layer 5
  │
  ├─ 4. 对每个 Agent：
  │     ├─ 创建 AgentRunner
  │     ├─ runner.start()
  │     ├─ registry.register(info)
  │     └─ 发布 AGENT_STARTED 事件
  │
  └─ 5. 启动完成，发布系统就绪事件
```

### 9.4 崩溃恢复流程

```
handle_crash(name)
  │
  ├─ 1. 从 registry 获取 AgentInfo
  │
  ├─ 2. 检查 _restart_counts[name] < max_restart_attempts
  │     ├─ 是 → 继续
  │     └─ 否 → 标记为 crashed，发布 AGENT_CRASHED，不再重启
  │
  ├─ 3. 递增重启计数
  │
  ├─ 4. 等待 restart_delay 秒
  │
  ├─ 5. 重新创建 AgentRunner 并启动
  │
  ├─ 6. 启动成功 → 重置重启计数，发布 AGENT_STARTED
  │
  └─ 7. 启动失败 → 发布 AGENT_CRASHED
```

### 9.5 设计要点

- **启动顺序**：按层编号升序启动，确保下层先就绪
- **崩溃计数**：每个 Agent 独立计数，重启成功后重置
- **优雅关闭**：draining 模式 + 超时强制终止
- **事件通知**：所有生命周期变更通过 MCPBus 发布事件

---

## 十、`runtime/health.py` 设计方案

### 10.1 职责

健康检查系统，定期检测所有 Agent 的存活状态，发现异常时触发恢复流程。

### 10.2 核心接口

```python
class HealthChecker:
    """健康检查器 — 定期 ping 所有 Agent"""
    
    def __init__(self, registry: AgentRegistry, lifecycle: LifecycleManager,
                 mcp_bus: MCPBus, interval: int = 15):
        self._registry = registry
        self._lifecycle = lifecycle
        self._bus = mcp_bus
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._failure_counts: dict[str, int] = {}  # name → 连续失败次数
    
    def start(self) -> None:
        """启动健康检查循环"""
    
    def stop(self) -> None:
        """停止健康检查"""
    
    async def check_all(self) -> dict[str, bool]:
        """检查所有 Agent 的健康状态
        1. 遍历 registry 中所有 Agent
        2. 对每个 Agent 发送 system/ping
        3. 记录结果和耗时
        """
    
    async def check_agent(self, name: str) -> bool:
        """检查单个 Agent
        1. 通过 MCPBus 发送 system/ping
        2. 等待响应（超时 5s）
        3. 成功 → 重置失败计数
        4. 失败 → 递增失败计数，达到阈值触发恢复
        """
    
    def get_health(self) -> dict:
        """获取所有 Agent 的健康状态快照"""
```

### 10.3 健康检查循环

```python
async def _check_loop(self):
    """健康检查主循环"""
    while True:
        await asyncio.sleep(self._interval)
        
        agents = self._registry.list_agents()
        for agent in agents:
            if agent.status == "stopped":
                continue
            
            try:
                alive = await self.check_agent(agent.name)
                if alive:
                    # 之前不可用，现在恢复了
                    if self._failure_counts.get(agent.name, 0) > 0:
                        self._failure_counts[agent.name] = 0
                        await self._bus.publish(SystemEvent(
                            type=HealthEvent.AGENT_RECOVERED,
                            source="health_checker",
                            timestamp=datetime.utcnow(),
                            data={"agent": agent.name},
                            severity="info",
                        ))
                else:
                    await self._handle_failure(agent.name)
            except Exception as e:
                await self._handle_failure(agent.name, error=str(e))
```

### 10.4 失败处理

```python
async def _handle_failure(self, name: str, error: str = None):
    """处理 Agent 健康检查失败"""
    count = self._failure_counts.get(name, 0) + 1
    self._failure_counts[name] = count
    
    if count >= HEALTH_MAX_FAILURES:
        # 连续失败达到阈值，触发恢复
        await self._bus.publish(SystemEvent(
            type=HealthEvent.AGENT_UNREACHABLE,
            source="health_checker",
            timestamp=datetime.utcnow(),
            data={"agent": name, "failures": count, "error": error},
            severity="warning",
        ))
        # 通知 LifecycleManager 处理崩溃
        await self._lifecycle.handle_crash(name)
```

### 10.5 设计要点

- **定期检查**：每 15 秒检查一次所有 Agent
- **连续失败计数**：单次失败不立即触发恢复，连续 3 次才触发
- **恢复检测**：Agent 从不可用变为可用时发布恢复事件
- **非侵入式**：健康检查通过 MCPBus 发送 ping，不直接操作 Agent 进程

---

## 十一、`runtime/main.py` 设计方案

### 11.1 职责

Pulsar 系统主入口，整合所有运行时组件，提供启动/停止/状态查询接口。

### 11.2 核心接口

```python
class PulsarRuntime:
    """Pulsar 系统主运行时"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: Optional[ConfigManager] = None
        self.registry: Optional[AgentRegistry] = None
        self.mcp_bus: Optional[MCPBus] = None
        self.lifecycle: Optional[LifecycleManager] = None
        self.health: Optional[HealthChecker] = None
        self.audit: Optional[AuditLogger] = None
        self.config_watcher: Optional[ConfigWatcher] = None
        self._running = False
    
    async def start(self) -> None:
        """启动系统
        1. 加载配置
        2. 创建并启动 AuditLogger
        3. 创建 AgentRegistry
        4. 创建并启动 MCPBus
        5. 创建 LifecycleManager
        6. 启动所有 Agent（lifecycle.start_all()）
        7. 启动 HealthChecker
        8. 启动 ConfigWatcher
        9. 标记系统为运行中
        """
    
    async def shutdown(self, grace_period: int = 30) -> None:
        """优雅关闭系统
        1. 标记系统为停止中
        2. 停止 HealthChecker
        3. 停止 ConfigWatcher
        4. 停止所有 Agent（lifecycle.drain_all()）
        5. 停止 MCPBus
        6. 刷新并停止 AuditLogger
        """
    
    async def run_forever(self) -> None:
        """运行直到收到停止信号
        1. 设置信号处理器（SIGTERM/SIGINT）
        2. 调用 start()
        3. 等待停止信号
        4. 调用 shutdown()
        """
    
    def get_status(self) -> dict:
        """获取系统状态快照"""
    
    async def handle_config_change(self, new_config: dict) -> None:
        """处理配置变更
        1. 对比新旧配置的 Agent 列表
        2. 停止被移除的 Agent
        3. 启动新增的 Agent
        4. 更新运行中 Agent 的配置
        """
```

### 11.3 启动顺序

```
PulsarRuntime.run_forever()
  │
  ├─ 1. 设置信号处理器（SIGTERM → shutdown, SIGINT → shutdown）
  │
  ├─ 2. ConfigManager.load()
  │
  ├─ 3. AuditLogger.start()
  │
  ├─ 4. AgentRegistry()
  │
  ├─ 5. MCPBus.start()
  │
  ├─ 6. LifecycleManager(registry, mcp_bus, config)
  │
  ├─ 7. lifecycle.start_all()
  │     ├─ 按层顺序启动所有 Agent
  │     └─ 每个 Agent 启动后注册到 Registry
  │
  ├─ 8. HealthChecker.start()
  │
  ├─ 9. ConfigWatcher.start()
  │
  └─ 10. 等待停止信号...
```

### 11.4 关闭顺序

```
PulsarRuntime.shutdown(grace_period=30)
  │
  ├─ 1. 设置 _running = False
  │
  ├─ 2. HealthChecker.stop()
  │
  ├─ 3. ConfigWatcher.stop()
  │
  ├─ 4. lifecycle.drain_all(timeout=grace_period)
  │     ├─ 通知所有 Agent 进入 draining 模式
  │     ├─ 等待进行中任务完成
  │     └─ 强制停止未退出的 Agent
  │
  ├─ 5. MCPBus.stop()
  │
  ├─ 6. audit.flush() + audit.stop()
  │
  └─ 7. 标记系统已停止
```

### 11.5 验收标准

- [ ] `PulsarRuntime.run_forever()` 启动后，所有配置中的 Agent 进程/协程正常启动
- [ ] `pulsar system status` 返回所有 Agent 的健康状态
- [ ] 手动 kill 一个 Agent 子进程后，HealthChecker 在 45 秒内检测到并自动重启
- [ ] 修改 config.yaml 后，系统自动重载配置（500ms 防抖）
- [ ] 所有工具调用写入 `data/logs/audit.log`（JSON Lines 格式）
- [ ] 发送 SIGTERM 后，系统在 30 秒内优雅关闭
- [ ] 通过 MCPBus 发送 `tools/list` 请求，返回已注册 Agent 的工具列表
- [ ] 配置校验失败时保留旧配置，系统不中断

### 11.6 注意事项

1. **Windows 兼容性**：`asyncio.create_subprocess_exec` 在 Windows 上需要特殊处理信号，SIGTERM 不可用，使用 `process.terminate()` 替代
2. **日志目录**：首次启动时自动创建 `data/logs/` 目录
3. **配置热加载**：watchdog 在 Windows 上使用 polling 模式，性能可接受
4. **子进程通信**：使用 `\n` 作为消息分隔符，每条消息一行 JSON
5. **启动超时**：每个 Agent 启动有 10 秒超时，超时视为启动失败
6. **资源清理**：确保 `shutdown()` 是幂等的，多次调用不会产生副作用

---

## 十二、模块间依赖关系

```
runtime/__init__.py
  └── 导入所有子模块

runtime/events.py
  └── 无依赖（纯 dataclass 和枚举）

runtime/registry.py
  └── 依赖 shared（AgentInfo, TransportInfo）

runtime/config.py
  └── 依赖 shared（AgentConfig, ConfigError）

runtime/agent_runner.py
  └── 依赖 shared（TransportInfo, ConfigError）

runtime/logging.py
  └── 依赖 shared（AuditLog, constants）

runtime/mcp_bus.py
  └── 依赖 events, registry, shared（MCPRequest, MCPResponse）

runtime/lifecycle.py
  └── 依赖 registry, agent_runner, events, config, shared

runtime/health.py
  └── 依赖 mcp_bus, events, shared

runtime/main.py
  └── 依赖以上全部
```

**实现顺序**：
1. `events.py`（无依赖）
2. `registry.py`（依赖 shared）
3. `config.py`（依赖 shared）
4. `agent_runner.py`（依赖 shared）
5. `logging.py`（依赖 shared）
6. `mcp_bus.py`（依赖 events, registry）
7. `lifecycle.py`（依赖 registry, agent_runner, events, config）
8. `health.py`（依赖 mcp_bus, events）
9. `main.py`（依赖以上全部）
10. `__init__.py`（最后）

---

## 十三、关键设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 事件总线实现 | 独立 EventBus / MCPBus 实现 | MCPBus 实现 EventBus 接口 | 减少组件数量，复用消息通道 |
| Agent 通信协议 | JSON-RPC / 自定义协议 | JSON-RPC 2.0 子集 | 与 MCP 标准兼容，工具链成熟 |
| 配置格式 | YAML / TOML / JSON | YAML | 可读性强，支持注释，与文档一致 |
| 进程管理 | asyncio.subprocess / multiprocessing | asyncio.subprocess | 与异步架构一致，stdin/stdout 管道天然支持 |
| 审计日志存储 | JSON Lines / SQLite / 两者 | JSON Lines | 简单可靠，便于对接 ELK |
| 健康检查方式 | 心跳 ping / 进程存在性检查 | 心跳 ping | 能检测到进程挂起而非仅进程退出 |
| 配置热加载 | watchdog / 定时轮询 | watchdog（回退轮询） | 实时性更好，watchdog 不可用时自动回退 |
| 错误处理策略 | 快速失败 / 优雅降级 | 优雅降级 | 单个 Agent 故障不影响系统整体 |

---

## 十四、与 shared 模块的接口约定

runtime 模块消费 shared 模块提供的以下类型：

| shared 类型 | runtime 使用方 | 用途 |
|-------------|---------------|------|
| `AgentConfig` | config.py, lifecycle.py | Agent 配置定义 |
| `MCPRequest` | mcp_bus.py | 内部通信请求 |
| `MCPResponse` | mcp_bus.py | 内部通信响应 |
| `ToolDefinition` | mcp_bus.py | 工具定义（tools/list 响应） |
| `Task` | lifecycle.py（预留） | 任务模型（Sprint 3 使用） |
| `AuditLog` | logging.py | 审计日志条目 |
| `Layer` | lifecycle.py | 层编号枚举 |
| `AgentType` | lifecycle.py | Agent 类型枚举 |
| `TaskStatus` | lifecycle.py（预留） | 任务状态枚举 |
| `EventType` | logging.py | 事件类型枚举 |
| `PulsarError` 系列 | 所有文件 | 错误处理 |
| 常量 | 所有文件 | 默认值、协议常量 |
