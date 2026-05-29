# Pulsar Phase 1 Sprint 1 — shared/ 模块详细计划

> 本文档描述 `shared/` 模块的设计方案，包含核心数据模型、错误类型、常量定义。
> shared 模块是系统的基础设施层，所有其他模块都依赖它，因此必须最先实现且保持稳定。

---

## 一、模块定位

**职责**：提供全系统共享的类型定义、数据模型和常量，确保各层之间通信的类型安全。

**设计原则**：
- **零外部依赖** — 仅依赖 Python 标准库 + Pydantic v2
- **无业务逻辑** — 只定义数据结构，不包含任何处理逻辑
- **向后兼容** — 字段变更只增不减，废弃字段标记 `@deprecated` 而非删除
- **严格类型** — 所有模型使用 Pydantic v2 严格模式（`strict=True`）

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `shared/__init__.py` | P0 | 无 |
| 2 | `shared/models.py` | P0 | 无 |
| 3 | `shared/errors.py` | P0 | 无 |
| 4 | `shared/constants.py` | P0 | 无 |

---

## 三、`shared/__init__.py` 设计方案

### 3.1 职责

包初始化文件，统一导出 shared 模块的公共类型。

### 3.2 导出策略

```python
# 导出所有模型类
__all__ = [
    # 从 models 导出
    "AgentConfig", "MCPRequest", "MCPResponse",
    "ToolDefinition", "Task", "AuditLog",
    "AgentInfo", "TransportInfo", "RegistryEvent",
    # 从 errors 导出
    "PulsarError", "AgentNotFoundError", "ToolCallError",
    "ConfigError", "AuthError", "RateLimitError", "TimeoutError",
    # 从 constants 导出
    "Layer", "AgentType", "TaskStatus", "EventType",
]
```

### 3.3 注意事项

- 不导入任何运行时模块
- 保持 `__all__` 与 models/errors/constants 的公共 API 同步更新

---

## 四、`shared/models.py` 设计方案

### 4.1 职责

定义全系统共享的 Pydantic v2 数据模型，覆盖：
- Agent 配置与注册信息
- MCP 通信协议消息
- 工具定义
- 任务模型
- 审计日志

### 4.2 模型清单

#### 4.2.1 AgentConfig

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | Agent 唯一标识名，如 `adapter.wechat` |
| `layer` | `Layer` | 是 | 所属层（枚举值 1-5） |
| `type` | `AgentType` | 是 | Agent 类型 |
| `runner` | `Literal["subprocess", "inprocess"]` | 否 | 运行模式，默认 `subprocess` |
| `enabled` | `bool` | 否 | 是否启用，默认 `True` |
| `config` | `dict` | 否 | 私有配置字典 |
| `capabilities` | `list[str]` | 否 | 能力标签列表，如 `["wechat_draft_add", "http_request"]` |

**验证规则**：
- `name` 必须匹配正则 `^[a-z][a-z0-9_.-]{2,63}$`
- `layer` 必须在 1-5 范围内
- `capabilities` 列表元素必须匹配 `^[a-z][a-z0-9_]{2,127}$`

#### 4.2.2 AgentInfo

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | Agent 唯一标识名 |
| `capabilities` | `list[str]` | 是 | 能力标签列表 |
| `transport` | `TransportInfo` | 是 | 传输地址信息 |
| `runner_type` | `str` | 是 | 运行模式 |
| `status` | `Literal["running", "stopped", "crashed"]` | 否 | 当前状态 |
| `started_at` | `datetime` | 否 | 启动时间 |
| `metadata` | `dict` | 否 | 附加元数据 |

#### 4.2.3 TransportInfo

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `Literal["stdio", "tcp", "memory"]` | 是 | 传输类型 |
| `address` | `str` | 是 | 地址标识（stdio 用 `"stdin"`，tcp 用 `"host:port"`，memory 用 `"queue:name"`） |

#### 4.2.4 MCPRequest

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jsonrpc` | `str` | 是 | 固定值 `"2.0"` |
| `id` | `str` | 是 | 消息唯一 ID，格式 `msg_{timestamp}_{seq}` |
| `method` | `str` | 是 | 方法名，如 `tools/call`, `tools/list`, `system/ping` |
| `params` | `dict` | 否 | 参数 |
| `source_agent` | `str` | 否 | 来源 Agent 名称 |
| `target_agent` | `str` | 否 | 目标 Agent 名称 |

**验证规则**：
- `jsonrpc` 必须为 `"2.0"`
- `method` 必须匹配 `^[a-z]+/[a-z_]+(/[a-z_]+)*$`
- `id` 不能为空

#### 4.2.5 MCPResponse

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jsonrpc` | `str` | 是 | 固定值 `"2.0"` |
| `id` | `str` | 是 | 对应请求的 ID |
| `result` | `dict` | 否 | 成功结果 |
| `error` | `dict` | 否 | 错误信息 `{code, message, data}` |

**验证规则**：
- `result` 和 `error` 不能同时存在
- `error.code` 必须为整数

#### 4.2.6 ToolDefinition

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | 工具名，如 `wechat_draft_add` |
| `description` | `str` | 是 | 工具描述 |
| `input_schema` | `dict` | 是 | JSON Schema 格式的输入参数定义 |
| `agent` | `str` | 是 | 提供此工具的 Agent 名称 |

#### 4.2.7 Task

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | 任务唯一 ID |
| `type` | `str` | 是 | 任务类型 |
| `status` | `TaskStatus` | 是 | 任务状态 |
| `input` | `dict` | 是 | 输入参数 |
| `output` | `dict` | 否 | 输出结果 |
| `error` | `str` | 否 | 错误信息 |
| `retry_count` | `int` | 否 | 已重试次数，默认 0 |
| `max_retries` | `int` | 否 | 最大重试次数，默认 3 |
| `created_at` | `datetime` | 否 | 创建时间 |
| `updated_at` | `datetime` | 否 | 更新时间 |

#### 4.2.8 AuditLog

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `timestamp` | `datetime` | 是 | 事件时间 |
| `event_type` | `str` | 是 | 事件类型 |
| `agent` | `str` | 是 | 来源 Agent |
| `action` | `str` | 是 | 操作名称 |
| `params` | `dict` | 是 | 操作参数 |
| `result` | `dict` | 否 | 操作结果 |
| `duration_ms` | `int` | 是 | 耗时（毫秒） |
| `user` | `str` | 否 | 操作用户，默认 `"system"` |
| `success` | `bool` | 否 | 是否成功，默认 `True` |

#### 4.2.9 RegistryEvent

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `str` | 是 | 事件类型（registered / unregistered / updated） |
| `agent_name` | `str` | 是 | 相关 Agent 名称 |
| `agent_info` | `AgentInfo` | 否 | Agent 信息快照 |
| `timestamp` | `datetime` | 否 | 事件时间 |

### 4.3 序列化规范

- 所有模型序列化为 JSON 时使用 `model_dump_json()`
- `datetime` 字段使用 ISO 8601 格式（`2026-05-27T16:30:00Z`）
- 枚举字段序列化为字符串值
- 反序列化时使用 `model_validate_json()`

### 4.4 向后兼容策略

- 新增字段必须设置默认值
- 废弃字段使用 `@field` 装饰器标记 `deprecated`
- 字段类型变更必须兼容旧数据（如 `str` → `Optional[str]`）

---

## 五、`shared/errors.py` 设计方案

### 5.1 职责

定义全系统统一的错误类型层次结构，确保错误处理的一致性和可预测性。

### 5.2 错误层次结构

```
PulsarError (BaseException)
  ├── ConfigError          # 配置相关错误
  │     ├── ConfigNotFoundError     # 配置文件不存在
  │     ├── ConfigParseError        # 配置解析失败
  │     └── ConfigValidationError   # 配置校验失败
  ├── AgentError           # Agent 相关错误
  │     ├── AgentNotFoundError      # Agent 未注册
  │     ├── AgentNotRunningError    # Agent 未运行
  │     └── AgentCrashError         # Agent 崩溃
  ├── ToolError            # 工具调用错误
  │     ├── ToolNotFoundError       # 工具未注册
  │     ├── ToolCallError           # 工具执行失败
  │     └── ToolTimeoutError        # 工具调用超时
  ├── AuthError            # 认证错误
  │     ├── TokenExpiredError       # Token 过期
  │     └── AuthFailedError         # 认证失败
  ├── RateLimitError       # 频率限制错误
  ├── TimeoutError         # 超时错误
  └── ProtocolError        # 协议错误
        ├── InvalidMessageError     # 消息格式错误
        └── MethodNotFoundError     # 方法不存在
```

### 5.3 错误码规范

每个错误类型关联一个整数错误码：

| 错误码范围 | 错误类型 |
|-----------|----------|
| 1000-1999 | ConfigError |
| 2000-2999 | AgentError |
| 3000-3999 | ToolError |
| 4000-4999 | AuthError |
| 5000-5999 | RateLimitError |
| 6000-6999 | TimeoutError |
| 7000-7999 | ProtocolError |

### 5.4 错误序列化

所有错误可序列化为 MCP 错误响应格式：

```python
{
    "code": 3001,
    "message": "Tool 'wechat_draft_add' not found",
    "data": {
        "tool_name": "wechat_draft_add",
        "available_tools": ["wechat_draft_list", "wechat_publish"]
    }
}
```

### 5.5 关键设计决策

- 继承 `Exception` 而非 `BaseException`，允许被标准 `except Exception` 捕获
- 每个错误类包含 `code` 属性和 `to_dict()` 方法
- 支持错误链（`__cause__`），保留原始异常上下文

---

## 六、`shared/constants.py` 设计方案

### 6.1 职责

定义全系统共享的枚举和常量，消除魔法字符串/数字。

### 6.2 枚举定义

#### 6.2.1 Layer（层编号）

| 枚举值 | 数值 | 说明 |
|--------|------|------|
| `RUNTIME` | 1 | 运行时层 |
| `COGNITION` | 2 | 认知分析层 |
| `TASK` | 3 | 任务管理层 |
| `EXECUTION` | 4 | 执行层 |
| `INTERACTION` | 5 | 交互层 |

#### 6.2.2 AgentType（Agent 类型）

| 枚举值 | 说明 |
|--------|------|
| `RUNTIME` | 运行时管理 Agent |
| `ADAPTER` | 平台适配器 |
| `TOOL` | 工具 Agent |
| `SKILL` | 技能 Agent |
| `GATEWAY` | LLM 网关 |

#### 6.2.3 TaskStatus（任务状态）

| 枚举值 | 说明 |
|--------|------|
| `PENDING` | 等待执行 |
| `RUNNING` | 执行中 |
| `COMPLETED` | 已完成 |
| `FAILED` | 失败 |
| `CANCELLED` | 已取消 |

#### 6.2.4 EventType（事件类型）

| 枚举值 | 说明 |
|--------|------|
| `TOOL_CALL` | 工具调用 |
| `SYSTEM_EVENT` | 系统事件 |
| `AUTH` | 认证事件 |
| `HEALTH` | 健康检查事件 |
| `LIFECYCLE` | 生命周期事件 |
| `CONFIG` | 配置变更事件 |

### 6.3 常量定义

```python
# JSON-RPC 协议常量
JSONRPC_VERSION = "2.0"

# MCP 方法名常量
METHOD_TOOLS_CALL = "tools/call"
METHOD_TOOLS_LIST = "tools/list"
METHOD_SYSTEM_PING = "system/ping"
METHOD_EVENT_PUBLISH = "event/publish"
METHOD_EVENT_SUBSCRIBE = "event/subscribe"

# 系统默认值
DEFAULT_HEARTBEAT_INTERVAL = 15       # 心跳间隔（秒）
DEFAULT_MAX_RESTART_ATTEMPTS = 3      # 最大重启次数
DEFAULT_RESTART_DELAY = 5             # 重启延迟（秒）
DEFAULT_DRAIN_TIMEOUT = 30            # 优雅关闭超时（秒）
DEFAULT_MCP_TIMEOUT = 30              # MCP 调用超时（秒）
DEFAULT_MAX_RETRIES = 3               # 最大重试次数
DEFAULT_RETRY_DELAY = 2               # 重试延迟（秒）

# 健康检查常量
HEALTH_CHECK_INTERVAL = 15            # 健康检查间隔（秒）
HEALTH_MAX_FAILURES = 3               # 最大连续失败次数
HEALTH_PING_TIMEOUT = 5               # Ping 超时（秒）

# 审计日志常量
AUDIT_QUEUE_MAXSIZE = 1000            # 审计日志队列最大容量
AUDIT_FLUSH_INTERVAL = 0.5            # 批量写入间隔（秒）
AUDIT_FLUSH_BATCH_SIZE = 10           # 批量写入条数

# 配置热加载常量
CONFIG_DEBOUNCE_DELAY = 0.5           # 配置重载防抖延迟（秒）
```

### 6.4 设计原则

- 所有枚举继承 `str` 和 `Enum`（`StrEnum`），可直接序列化为字符串
- 常量使用大写蛇形命名
- 与配置默认值相关的常量集中在此处，避免散落在各模块中

---

## 七、模块间依赖关系

```
shared/__init__.py
  ├── 导入 shared/models.py
  ├── 导入 shared/errors.py
  └── 导入 shared/constants.py

shared/models.py
  └── 依赖 shared/constants.py（枚举类型）

shared/errors.py
  └── 无依赖（纯异常类定义）

shared/constants.py
  └── 无依赖（纯枚举和常量）
```

**实现顺序**：`constants.py` → `errors.py` → `models.py` → `__init__.py`

---

## 八、验收标准

- [ ] 所有 Pydantic 模型可通过 `model_validate()` 和 `model_validate_json()` 正确反序列化
- [ ] 枚举值可通过字符串反序列化（如 `Layer("runtime")` 返回 `Layer.RUNTIME`）
- [ ] 错误类型可通过 `to_dict()` 序列化为 MCP 兼容格式
- [ ] 所有模型在严格模式下拒绝非法类型
- [ ] `__all__` 导出列表与实际公共 API 一致
- [ ] 无循环依赖
- [ ] 无外部运行时依赖（仅 pydantic + 标准库）

---

## 九、注意事项

1. **Pydantic v2 语法**：使用 `Field()` 而非 v1 的 `Field()`，注意 `model_dump()` 替代 `dict()`，`model_validate()` 替代 `parse_obj()`
2. **时区处理**：所有 `datetime` 字段统一使用 UTC 时区，存储和传输均为 UTC，展示时由消费方转换
3. **枚举序列化**：使用 `StrEnum` 确保枚举值在 JSON 序列化/反序列化时保持为字符串
4. **模型版本标记**：在 `AgentConfig` 和 `AuditLog` 中预留 `version` 字段，便于未来 schema 演进
5. **不引入业务逻辑**：models.py 中不包含任何 `@field_validator` 以外的验证逻辑，业务校验放在各模块的 service 层
