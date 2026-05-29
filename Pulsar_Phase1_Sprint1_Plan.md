# Pulsar Phase 1 Sprint 1 — 优化设计方案

> 本文档基于《Pulsar Phase 1 详细技术方案》对 Sprint 1（基础骨架）进行深入的结构分析与耦合优化，**不包含代码实现**，聚焦于架构层面的改进。

---

## 一、当前设计的问题分析

### 1.1 PulsarRuntime 职责过重

当前设计中 `PulsarRuntime` 同时承担：
- 配置加载与热加载
- MCP 消息总线初始化
- Agent 生命周期管理
- 健康检查
- 审计日志
- 信号处理

这违反了**单一职责原则**。一个类的变更原因应该只有一个，但 `PulsarRuntime` 有六个变更原因。

### 1.2 MCPBus ↔ Lifecycle 双向耦合

```
MCPBus 需要知道 Agent 地址来路由消息
    ↕ 互相依赖
LifecycleManager 需要 MCPBus 来注册/注销 Agent
```

这种双向耦合使得两个组件都无法独立测试和演进。

### 1.3 HealthChecker 直接调用 Lifecycle

```python
# 当前设计
class HealthChecker:
    def _handle_failure(self, name):
        self.lifecycle.restart_agent(name)  # 直接耦合
```

健康检查逻辑与重启策略耦合在一起。如果未来需要改变重启策略（如退避延迟、通知告警），需要修改 HealthChecker。

### 1.4 进程模型假设过强

当前假设所有 Agent 都是独立子进程（`subprocess.Popen`），但实际上：
- **LLM Gateway** 更适合作为协程任务运行在同一进程内（减少 IPC 开销）
- **微信 Adapter** 需要独立进程（隔离故障）
- **CLI 命令** 是瞬时的，不需要常驻进程

缺少统一的进程/协程抽象。

### 1.5 AuditLogger 同步 I/O 阻塞

```python
# 当前设计
class AuditLogger:
    def log(self, ...):
        with open(self.path, 'a') as f:  # 同步 I/O，阻塞事件循环
            f.write(json_line)
```

在 asyncio 事件循环中执行同步文件 I/O 会阻塞整个循环，影响系统响应性。

### 1.6 配置热加载轮询低效

文件 mtime 轮询存在三个问题：
1. **精度问题**：某些文件系统 mtime 精度只有 1 秒
2. **CPU 浪费**：即使文件不变也定期唤醒
3. **竞态条件**：大文件写入过程中可能触发不完整的加载

### 1.7 state.db 超前设计

Sprint 1 中定义了 SQLite 表结构（`agent_states`、`tasks`），但没有任何组件实际使用它。这是**YAGNI（You Ain't Gonna Need It）** 反模式。

---

## 二、优化方案

### 2.1 引入 AgentRegistry 解耦 MCPBus 与 Lifecycle

**核心思路**：将"Agent 在哪里"的信息从 MCPBus 和 Lifecycle 中抽离，交给独立的 AgentRegistry。

```
┌─────────────────────────────────────────────────┐
│                  AgentRegistry                    │
│  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ 名称 → 地址   │  │ 能力标签 → [Agent 列表]   │  │
│  │ wechat_adapter│  │ wechat_draft_add → [w_a] │  │
│  │ llm_gateway   │  │ http_request → [w_a, ...]│  │
│  └──────────────┘  └──────────────────────────┘  │
│  register() | unregister() | resolve()           │
│  resolve_by_capability() | list_agents()         │
│  watch() → AsyncIterator[RegistryEvent]          │
└─────────────────────────────────────────────────┘
         ▲                    ▲
         │ 注册/注销          │ 按名称/能力查询
    ┌────┴────┐         ┌────┴────┐
    │Lifecycle│         │ MCPBus  │
    │Manager  │         │         │
    └─────────┘         └─────────┘
```

**解耦效果**：
- MCPBus 只负责消息传输（send/receive/publish/subscribe），不关心 Agent 在哪里
- Lifecycle 只负责进程/协程管理，不关心消息路由
- 两者都依赖 AgentRegistry，但彼此不依赖

**AgentRegistry 核心接口**：

```python
class AgentRegistry:
    """服务注册表 — 管理所有 Agent 的地址和能力信息"""
    
    async def register(self, agent: AgentInfo) -> None:
        """注册 Agent（由 LifecycleManager 在启动后调用）"""
    
    async def unregister(self, name: str) -> None:
        """注销 Agent（由 LifecycleManager 在停止前调用）"""
    
    def resolve(self, name: str) -> Optional[AgentInfo]:
        """按名称查找 Agent 的传输地址"""
    
    def resolve_by_capability(self, capability: str) -> list[AgentInfo]:
        """按能力标签查找 Agent（用于按需路由）"""
    
    def list_agents(self) -> list[AgentInfo]:
        """列出所有已注册 Agent"""
    
    def watch(self) -> AsyncIterator[RegistryEvent]:
        """监听注册表变更事件流"""
```

### 2.2 引入 AgentRunner 抽象进程模型

**核心思路**：将"如何运行一个 Agent"抽象为接口，支持子进程和协程两种实现。

```
┌─────────────────────────────────────────────┐
│              AgentRunner (ABC)               │
│  start() → 启动 Agent                       │
│  stop()  → 停止 Agent                       │
│  is_alive() → bool                          │
│  ping() → bool (健康探测)                    │
│  get_transport() → TransportInfo            │
└─────────────────────────────────────────────┘
         ▲                    ▲
         │                    │
┌────────┴────────┐  ┌───────┴──────────┐
│ SubprocessRunner │  │ InProcessRunner   │
│ 独立子进程        │  │ 同一进程协程      │
│ subprocess.Popen │  │ asyncio.Task     │
│ stdin/stdout IPC │  │ 直接函数调用      │
│ 故障隔离         │  │ 零 IPC 开销      │
└─────────────────┘  └──────────────────┘
```

**选择策略**（由配置决定）：

```yaml
agents:
  adapter.wechat:
    runner: subprocess    # 需要故障隔离 → 子进程
  gateway.llm:
    runner: inprocess     # 高频调用 → 协程
  scheduler:
    runner: inprocess     # 轻量定时 → 协程
```

**LifecycleManager 使用 AgentRunner**：

```python
class LifecycleManager:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._runners: dict[str, AgentRunner] = {}
    
    async def start_agent(self, config: AgentConfig) -> None:
        runner = self._create_runner(config)
        await runner.start()
        transport = runner.get_transport()
        await self.registry.register(AgentInfo(
            name=config.name,
            capabilities=config.capabilities,
            transport=transport,
            runner_type=config.runner,
        ))
        self._runners[config.name] = runner
```

### 2.3 事件驱动健康检查

**核心思路**：HealthChecker 只负责检测和发布事件，不关心如何处理。

```
HealthChecker
  │ 检测到 Agent 无响应
  │
  ├──→ publish(HealthEvent.AGENT_UNREACHABLE, {name, failures})
  │
  ▼
MCPBus Event Bus
  │
  ├──→ LifecycleManager.subscribe(HealthEvent.AGENT_UNREACHABLE)
  │     └── restart_agent(name)  # 决定重启策略
  │
  ├──→ AuditLogger.subscribe(HealthEvent.*)
  │     └── log("agent_health_failure", ...)
  │
  └──→ [未来] AlertManager.subscribe(HealthEvent.*)
        └── send_alert("Agent 异常", ...)
```

**事件类型定义**：

```python
# runtime/events.py
class HealthEvent:
    AGENT_UNREACHABLE = "health.agent_unreachable"
    AGENT_RECOVERED = "health.agent_recovered"
    AGENT_RESTARTING = "health.agent_restarting"
    AGENT_RESTART_FAILED = "health.agent_restart_failed"

class LifecycleEvent:
    AGENT_STARTED = "lifecycle.agent_started"
    AGENT_STOPPED = "lifecycle.agent_stopped"
    AGENT_CRASHED = "lifecycle.agent_crashed"

class ConfigEvent:
    CONFIG_CHANGED = "config.changed"
    CONFIG_ERROR = "config.error"
```

**解耦效果**：
- HealthChecker 不需要知道 Lifecycle 的存在
- 可以随时添加新的订阅者（如告警、日志、指标采集）
- 每个组件只关心自己需要的事件

### 2.4 异步审计日志

**核心思路**：使用 `asyncio.Queue` + 后台写入任务，将同步 I/O 从事件循环中剥离。

```
┌──────────┐    put()     ┌──────────────┐  批量写入   ┌──────────┐
│ 调用方    │ ──────────→  │ asyncio.Queue │ ────────→  │ audit.log │
│ log()     │  非阻塞      │ (最大 1000)   │  每 0.5s   │ (JSONL)  │
└──────────┘              └──────────────┘  或满 10 条  └──────────┘
                                  │
                                  │ 异常处理
                                  ▼
                            ┌──────────┐
                            │ fallback  │
                            │ stderr    │
                            └──────────┘
```

**关键设计点**：
- `log()` 调用是 O(1) 非阻塞，仅 `queue.put_nowait()`
- 队列满时降级到 stderr，不阻塞调用方
- 后台写入任务使用 `aiofiles` 或 `loop.run_in_executor` 避免阻塞
- 关闭时等待队列清空（drain），确保日志不丢失

### 2.5 配置热加载使用 watchdog

**核心思路**：使用文件系统事件通知替代轮询。

```python
# 使用 watchdog 库监听文件变更
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigWatcher:
    def __init__(self, config_path: str, on_change: Callable):
        self.path = config_path
        self.on_change = on_change
        self._observer = Observer()
        self._debounce_task: Optional[asyncio.Task] = None
    
    def start(self):
        handler = ConfigFileHandler(self._debounced_reload)
        self._observer.schedule(handler, os.path.dirname(self.path))
        self._observer.start()
    
    async def _debounced_reload(self):
        """防抖：500ms 内多次修改只触发一次重载"""
        if self._debounce_task:
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._do_reload())
    
    async def _do_reload(self):
        await asyncio.sleep(0.5)
        new_config = load_config(self.path)
        self.on_change(new_config)
```

**优势**：
- 事件驱动，零 CPU 空转
- 毫秒级响应
- 防抖机制避免频繁重载

### 2.6 移除 state.db 超前设计

**决策**：Sprint 1 中完全移除 `data/state.db` 及其表结构定义。

**理由**：
- Sprint 1 的所有状态都在内存中（AgentRegistry 的注册表、MCPBus 的订阅关系）
- 唯一需要持久化的是审计日志（文件形式）
- SQLite 表结构在 Sprint 3（任务队列需要持久化）时引入

### 2.7 PulsarRuntime 简化为协调器

**核心思路**：PulsarRuntime 只做三件事——按顺序启动、按逆序关闭、信号处理。

```python
class PulsarRuntime:
    """系统协调器 — 不包含业务逻辑"""
    
    def __init__(self, config_path: str):
        # 创建所有 Manager，但不启动
        self.config = ConfigManager(config_path)
        self.registry = AgentRegistry()
        self.bus = MCPBus(self.registry)
        self.lifecycle = LifecycleManager(self.registry)
        self.health = HealthChecker(self.bus)
        self.logger = AuditLogger(self.config.get_audit_config())
        self.watcher = ConfigWatcher(config_path, self._on_config_reload)
    
    async def start(self):
        """按依赖顺序启动"""
        await self.logger.start()           # 1. 日志系统最先
        self.registry.start()               # 2. 注册表（纯内存）
        await self.bus.start()              # 3. 消息总线
        await self.lifecycle.start_all(     # 4. 启动所有 Agent
            self.config.get_agents_config()
        )
        self.health.start_monitoring()      # 5. 健康检查
        self.watcher.start()                # 6. 配置热加载
        self.logger.log_system_start()
    
    async def shutdown(self, grace_period=30):
        """按逆序关闭"""
        self.watcher.stop()
        self.health.stop_monitoring()
        await self.lifecycle.drain_all(timeout=grace_period)
        await self.bus.close()
        self.registry.clear()
        await self.logger.close()           # 日志系统最后
```

---

## 三、优化后的文件清单

### 3.1 新增文件（3 个）

| # | 文件 | 用途 | 关键类 |
|---|------|------|--------|
| 1 | `runtime/registry.py` | 服务注册表 | `AgentRegistry`, `AgentInfo`, `RegistryEvent` |
| 2 | `runtime/agent_runner.py` | 进程/协程抽象 | `AgentRunner(ABC)`, `SubprocessRunner`, `InProcessRunner` |
| 3 | `runtime/events.py` | 系统事件类型 | `HealthEvent`, `LifecycleEvent`, `ConfigEvent` |

### 3.2 修改文件（6 个）

| # | 文件 | 变更内容 |
|---|------|----------|
| 4 | `runtime/mcp_bus.py` | 移除路由逻辑，路由委托给 AgentRegistry；只保留 send/receive/publish/subscribe |
| 5 | `runtime/lifecycle.py` | 使用 AgentRunner 抽象；订阅健康事件而非被 HealthChecker 直接调用 |
| 6 | `runtime/health.py` | 发布 HealthEvent 而非直接调用 Lifecycle.restart_agent() |
| 7 | `runtime/logging.py` | 改为异步队列 + 后台写入任务 |
| 8 | `runtime/config.py` | 使用 watchdog 替代轮询；拆出 ConfigManager 类 |
| 9 | `runtime/main.py` | 简化为协调器，只负责启动/关闭顺序和信号处理 |

### 3.3 不变文件（9 个）

| # | 文件 | 说明 |
|---|------|------|
| 10 | `shared/models.py` | 数据模型设计合理，无需修改 |
| 11 | `shared/errors.py` | 错误类型层次清晰 |
| 12 | `shared/constants.py` | 枚举常量设计合理 |
| 13 | `runtime/__init__.py` | 包初始化 |
| 14 | `pulsar/__init__.py` | 包初始化 |
| 15 | `pulsar/__main__.py` | 入口脚本 |
| 16 | `config.yaml` | 主配置 |
| 17 | `Dockerfile` | Docker 部署 |
| 18 | `README.md` | 项目文档 |

### 3.4 推迟文件（1 个）

| 文件 | 推迟到 | 理由 |
|------|--------|------|
| `data/state.db` | Sprint 3 | Sprint 1 所有状态在内存中，无需持久化 |

---

## 四、优化后的依赖关系图

```
PulsarRuntime (协调器)
  │
  ├── ConfigManager ← 无依赖
  │     └── 依赖 watchdog（外部库）
  │
  ├── AgentRegistry ← 无依赖（纯内存 dict）
  │
  ├── MCPBus ← 依赖 AgentRegistry（按名称/能力路由）
  │
  ├── LifecycleManager ← 依赖 AgentRegistry + AgentRunner
  │     ├── AgentRunner(ABC) ← 无依赖
  │     │     ├── SubprocessRunner ← 依赖 asyncio.subprocess
  │     │     └── InProcessRunner ← 依赖 asyncio.Task
  │     └── 订阅 HealthEvent（通过 MCPBus）
  │
  ├── HealthChecker ← 依赖 MCPBus（发布事件）
  │
  ├── AuditLogger ← 无依赖（独立异步写入）
  │
  └── ConfigWatcher ← 依赖 ConfigManager
        └── 依赖 watchdog（外部库）
```

**关键改进**：
- ✅ 无循环依赖
- ✅ 每个组件只依赖 0-2 个基础设施
- ✅ 所有组件可独立单元测试（AgentRegistry 可 mock）
- ✅ 启动/关闭顺序清晰

---

## 五、事件流与消息流

### 5.1 健康检查事件流

```
时间线：
1. HealthChecker 向 Agent A 发送 ping
2. 等待 5 秒无响应
3. HealthChecker → bus.publish(HealthEvent.AGENT_UNREACHABLE, {name, failures})
4. MCPBus 事件总线分发事件
5. LifecycleManager 收到事件 → restart_agent(name)
6. LifecycleManager → AgentRunner.restart()
7. AgentRunner 启动新进程/协程
8. LifecycleManager → registry.register(AgentInfo(...))
9. HealthChecker 下次 ping 成功 → publish(HealthEvent.AGENT_RECOVERED)
```

### 5.2 MCP 工具调用消息流

```
CLI 用户输入: pulsar publish wechat --title "..." --content ./article.md
  │
  ▼
interaction/cli/commands/publish.py
  │ 构建 MCPRequest { method: "tools/call", params: { name: "wechat_draft_add", ... } }
  │
  ▼
MCPBus.send(request)
  │ registry.resolve("adapter.wechat") → 获取传输地址
  │
  ▼
SubprocessRunner.stdin → JSON-RPC 消息
  │
  ▼
execution/adapters/wechat/adapter.py
  │ handle_tool_call("wechat_draft_add", args)
  │ → 调用微信 API
  │ → 返回结果
  │
  ▼
MCPBus.response → CLI 输出
```

### 5.3 配置热加载事件流

```
用户编辑 config.yaml
  │
  ▼
watchdog 检测到文件修改事件
  │
  ▼
ConfigWatcher._debounced_reload()
  │ 等待 500ms 防抖
  │
  ▼
ConfigWatcher._do_reload()
  │ load_config(path) → 新配置
  │ bus.publish(ConfigEvent.CONFIG_CHANGED, {changes: [...]})
  │
  ▼
PulsarRuntime._on_config_reload(new_config)
  │ 更新 self.config
  │ 通知相关 Agent 更新配置
  │ logger.log("config_reload", ...)
```

---

## 六、与原始设计的对比

| 维度 | 原始设计 | 优化后设计 |
|------|----------|------------|
| **PulsarRuntime 职责** | 6 个（配置/总线/生命周期/健康/日志/信号） | 3 个（启动顺序/关闭顺序/信号处理） |
| **MCPBus ↔ Lifecycle** | 双向耦合 | 通过 AgentRegistry 解耦 |
| **HealthChecker → Lifecycle** | 直接调用 | 事件驱动 |
| **进程模型** | 仅子进程 | AgentRunner 抽象（子进程/协程） |
| **审计日志 I/O** | 同步阻塞 | 异步队列 + 批量写入 |
| **配置热加载** | 文件 mtime 轮询 | watchdog 事件驱动 |
| **state.db** | Sprint 1 引入（无用） | 推迟到 Sprint 3 |
| **文件总数** | 18 个 | 21 个（+3 新增，-0 移除） |
| **循环依赖** | 有（MCPBus ↔ Lifecycle） | 无 |
| **可测试性** | 组件间强耦合，难 mock | 每个组件依赖清晰，易 mock |

---

## 七、实施建议

### 7.1 实现顺序

```
第 1 步：shared/models.py, errors.py, constants.py
  └── 无依赖，最先实现

第 2 步：runtime/events.py, runtime/registry.py
  └── 依赖 shared，被其他组件依赖

第 3 步：runtime/config.py (ConfigManager)
  └── 依赖 shared，无其他内部依赖

第 4 步：runtime/agent_runner.py
  └── 依赖 shared，无其他内部依赖

第 5 步：runtime/logging.py (异步版)
  └── 依赖 shared，无其他内部依赖

第 6 步：runtime/mcp_bus.py
  └── 依赖 registry + events

第 7 步：runtime/lifecycle.py
  └── 依赖 registry + agent_runner + events

第 8 步：runtime/health.py
  └── 依赖 mcp_bus + events

第 9 步：runtime/main.py (PulsarRuntime 协调器)
  └── 依赖以上所有组件

第 10 步：pulsar/__main__.py, config.yaml, Dockerfile, README.md
  └── 依赖 runtime
```

### 7.2 测试策略

| 组件 | 测试方法 | Mock 对象 |
|------|----------|-----------|
| AgentRegistry | 纯内存，直接单元测试 | 无 |
| AgentRunner | 集成测试（启动/停止真实进程/协程） | 无 |
| MCPBus | 单元测试 + 集成测试 | AgentRegistry |
| LifecycleManager | 单元测试 | AgentRegistry, AgentRunner |
| HealthChecker | 单元测试 | MCPBus |
| AuditLogger | 集成测试（检查文件内容） | 无 |
| ConfigManager | 单元测试（临时文件） | 无 |
| ConfigWatcher | 集成测试（修改文件触发回调） | 无 |
| PulsarRuntime | 集成测试（启动/关闭） | 以上全部（或真实组件） |

### 7.3 依赖变更

需要在 `pyproject.toml` 和 `requirements.txt` 中新增：

```
# 新增依赖
watchdog>=4.0.0    # 文件系统事件监听
aiofiles>=24.0.0   # 异步文件 I/O（可选，也可用 loop.run_in_executor）
```

---

## 八、总结

本次优化围绕 **7 个核心问题** 展开，通过 **3 个新增文件** 和 **6 个文件修改**，实现了以下目标：

1. **解耦** — 消除 MCPBus ↔ Lifecycle 双向耦合，HealthChecker 不再直接依赖 Lifecycle
2. **抽象** — AgentRunner 统一进程/协程模型，为未来扩展留出空间
3. **异步化** — 审计日志从同步 I/O 改为异步队列写入
4. **事件驱动** — 健康检查、配置热加载均通过事件总线通信
5. **精简** — 移除 state.db 超前设计，PulsarRuntime 回归协调器本质

优化后的架构中，每个组件职责单一、依赖清晰、可独立测试。这为 Sprint 2-4 的迭代奠定了坚实的基础。
