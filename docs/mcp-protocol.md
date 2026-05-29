# Pulsar 协议文档

本文档定义 Pulsar 系统中的两种协议：

1. **PIP (Pulsar Internal Protocol)** — 内部层间通信协议
2. **MCP (Model Context Protocol)** — 外部标准协议（Anthropic MCP 兼容）

---

# 第一部分：PIP — Pulsar Internal Protocol

## 概述

PIP (Pulsar Internal Protocol) 是 Pulsar 系统内部组件（层与层）之间通信的标准化协议。基于 **JSON-RPC 2.0** 规范设计，支持多种传输层方式。

**核心原则**：
- 面向内部组件通信（Agent Layer → Tool Layer → 插件层）
- 轻量、高效、无状态
- 不对外暴露，由外部协议适配层转换为 PIP 调用

---

## PIP 协议基础

### 传输层 (Transports)

| 传输方式 | 适用场景 | 描述 |
|---------|---------|------|
| **stdio** | 子进程通信 | 通过标准输入/输出进行 JSON-RPC 消息交换，适合子进程或插件调用 |
| **in-process queue** | 同进程通信 | 内存队列传递，零序列化开销，适合同一进程内层间调用 |
| **HTTP** | 外部接入（Phase 2） | 基于 HTTP POST 的 JSON-RPC，适合外部系统或远程调试（开发阶段） |

### JSON-RPC 2.0 请求格式

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "tools/call",
    "params": {
        "name": "wechat_publish",
        "arguments": {
            "draft_id": "12345"
        }
    }
}
```

### JSON-RPC 2.0 成功响应格式

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "result": {
        "success": true,
        "data": {
            "publish_id": "pub_xxx"
        }
    }
}
```

### JSON-RPC 2.0 错误响应格式

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "error": {
        "code": -32601,
        "message": "Method not found",
        "data": null
    }
}
```

---

## PIP 方法列表

| 方法 | 方向 | 说明 |
|------|------|------|
| `tools/call` | 请求 → 响应 | 调用指定工具 |
| `tools/list` | 请求 → 响应 | 列出所有可用工具 |
| `event/publish` | 发布 → 订阅 | 发布事件通知 |
| `event/subscribe` | 订阅 → 发布 | 订阅特定事件 |
| `system/ping` | 请求 → 响应 | 健康检查心跳 |
| `system/status` | 请求 → 响应 | 获取系统运行状态 |

---

## PIP 方法详述与示例

### 1. `tools/call` — 调用工具

**说明**：调用一个已注册的工具，传入参数并获取执行结果。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "tools/call",
    "params": {
        "name": "wechat_draft_add",
        "arguments": {
            "title": "今日新闻",
            "content": "新闻正文内容...",
            "cover_media_id": "abc123"
        }
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "result": {
        "success": true,
        "data": {
            "draft_id": "draft_xxx"
        }
    }
}
```

**错误响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-001",
    "error": {
        "code": -32104,
        "message": "Tool execution failed: Invalid parameters",
        "data": {
            "tool_name": "wechat_draft_add",
            "param_errors": {
                "title": "Title exceeds 32 characters"
            }
        }
    }
}
```

---

### 2. `tools/list` — 列出工具

**说明**：返回当前系统注册的所有可用工具列表。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-002",
    "method": "tools/list",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-002",
    "result": {
        "tools": [
            {
                "name": "wechat_draft_add",
                "description": "创建微信草稿",
                "params": {
                    "title": {"type": "string", "required": true},
                    "content": {"type": "string", "required": true},
                    "cover_media_id": {"type": "string", "required": false}
                }
            },
            {
                "name": "wechat_publish",
                "description": "发布微信文章",
                "params": {
                    "draft_id": {"type": "string", "required": true}
                }
            }
        ]
    }
}
```

---

### 3. `event/publish` — 发布事件

**说明**：发布一个事件通知，所有已订阅该事件的消费者将收到通知。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-003",
    "method": "event/publish",
    "params": {
        "event": "wechat:publish:completed",
        "data": {
            "publish_id": "pub_xxx",
            "status": "success",
            "article_url": "https://mp.weixin.qq.com/s/xxx"
        }
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-003",
    "result": {
        "success": true,
        "subscribers_notified": 2
    }
}
```

---

### 4. `event/subscribe` — 订阅事件

**说明**：订阅一个或多个事件类型，当事件发布时收到通知。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-004",
    "method": "event/subscribe",
    "params": {
        "events": ["wechat:publish:completed", "wechat:token:expired"],
        "callback": "internal://event_handler"
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-004",
    "result": {
        "success": true,
        "subscription_id": "sub_001"
    }
}
```

---

### 5. `system/ping` — 健康检查

**说明**：简单的 Ping/Pong 健康检查，验证系统是否存活。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-005",
    "method": "system/ping",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-005",
    "result": {
        "pong": true,
        "timestamp": "2026-05-29T12:00:00Z"
    }
}
```

---

### 6. `system/status` — 系统状态

**说明**：返回系统详细的运行状态信息。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-006",
    "method": "system/status",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-006",
    "result": {
        "status": "running",
        "uptime_seconds": 86400,
        "version": "1.0.0",
        "active_tasks": 3,
        "queue_depth": 12,
        "memory_mb": 256.5,
        "cpu_percent": 12.3
    }
}
```

---

## PIP 错误码

| 错误码 | 名称 | 说明 |
|--------|------|------|
| `-32700` | Parse Error | JSON 解析失败，请求不是有效的 JSON |
| `-32600` | Invalid Request | 请求格式不符合 JSON-RPC 2.0 规范 |
| `-32601` | Method Not Found | 请求的方法不存在 |
| `-32104` | Tool Execution Error | 工具执行时发生错误 |
| `-32107` | Rate Limited | 超出调用频率限制 |
| `-32102` | Auth Failed | 认证失败 |

### 错误响应示例

**Parse Error (-32700)**：

```json
{
    "jsonrpc": "2.0",
    "id": null,
    "error": {
        "code": -32700,
        "message": "Parse error: Invalid JSON at position 42",
        "data": null
    }
}
```

**Invalid Request (-32600)**：

```json
{
    "jsonrpc": "2.0",
    "id": null,
    "error": {
        "code": -32600,
        "message": "Invalid Request: Missing 'method' field",
        "data": null
    }
}
```

**Rate Limited (-32107)**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-007",
    "error": {
        "code": -32107,
        "message": "Rate limited: Too many requests",
        "data": {
            "retry_after_seconds": 30,
            "limit": 100,
            "window_minutes": 1
        }
    }
}
```

**Auth Failed (-32102)**：

```json
{
    "jsonrpc": "2.0",
    "id": "req-008",
    "error": {
        "code": -32102,
        "message": "Auth failed: Invalid or expired token",
        "data": {
            "auth_type": "bearer_token",
            "reason": "token_expired"
        }
    }
}
```

---

## PIP 超时处理

### 请求超时

| 方法 | 默认超时 | 说明 |
|------|---------|------|
| `tools/call` | 30 秒 | 工具执行最长等待时间 |
| `tools/list` | 10 秒 | 工具列表查询 |
| `system/ping` | 5 秒 | 心跳检查 |
| `system/status` | 10 秒 | 状态查询 |
| `event/publish` | 10 秒 | 事件发布 |
| `event/subscribe` | 10 秒 | 事件订阅 |

### 超时行为

1. 客户端发起请求时启动计时器
2. 超过超时时间未收到响应 → 返回 `-32101` 错误（含 timeout 信息）
3. 服务端仍可能继续执行（不保证取消）
4. 客户端可选择重试或放弃

### 重试建议

- 幂等操作（如查询）：可直接重试
- 非幂等操作（如创建）：建议先查询状态再决定是否重试

---

## PIP stdio 传输协议约定

### 消息格式

每行一个完整的 JSON 对象，以换行符 `\n` 分隔。

```
{"jsonrpc":"2.0","id":"1","method":"system/ping","params":{}}\n
{"jsonrpc":"2.0","id":"1","result":{"pong":true}}\n
```

### 流控

- 读取：按行读取 stdin
- 写入：按行写入 stdout
- 错误日志：写入 stderr（不干扰协议通道）

---

## PIP HTTP 传输协议约定（Phase 2）

### 端点

```
POST /api/pip
Content-Type: application/json
```

### 请求头

| 头字段 | 说明 |
|--------|------|
| `Content-Type` | 必须为 `application/json` |
| `Authorization` | Bearer Token（可选，用于内部认证） |
| `X-Request-Id` | 请求追踪 ID（可选） |

### 响应状态码

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 | 请求处理完成（含业务错误） |
| 400 | JSON 解析失败或请求格式错误 |
| 401 | 认证失败 |
| 429 | 频率限制 |
| 500 | 服务端内部错误 |

---

# 第二部分：MCP — Model Context Protocol（外部标准协议）

## 概述

MCP (Model Context Protocol) 是 Pulsar 系统对外暴露的标准协议，兼容 **Anthropic MCP 规范**。该协议面向外部 AI 客户端（如 Claude Desktop、自定义 Agent 框架等），提供标准的工具调用、资源访问和提示词管理能力。

**关键点**：
- 仅用于外部客户端与 Pulsar Tool Server 之间的通信
- 完全遵循 Anthropic MCP 规范
- 内部由适配层将 MCP 请求翻译为 PIP 调用

---

## MCP 传输方式

| 传输方式 | 适用场景 | 描述 |
|---------|---------|------|
| **HTTP SSE** | 远程客户端 | 基于 Server-Sent Events 的流式传输，适合 Web 应用 |
| **stdio** | 本地子进程 | 通过标准输入/输出通信，适合 Claude Desktop 等本地客户端 |

---

## MCP 端点列表

| 端点 | 方向 | 说明 | PIP 对应的翻译 |
|------|------|------|---------------|
| `tools/list` | 请求 → 响应 | 列出所有可用工具 | → `tools/list` |
| `tools/call` | 请求 → 响应 | 调用指定工具 | → `tools/call` |
| `resources/list` | 请求 → 响应 | 列出所有可用资源 | → 无（由 MCP 适配层处理） |
| `resources/read` | 请求 → 响应 | 读取指定资源内容 | → 无（由 MCP 适配层处理） |
| `prompts/list` | 请求 → 响应 | 列出所有可用提示词 | → 无（由 MCP 适配层处理） |
| `prompts/get` | 请求 → 响应 | 获取指定提示词内容 | → 无（由 MCP 适配层处理） |
| `system/capabilities` | 请求 → 响应 | 获取系统能力声明 | → 无（由 MCP 适配层处理） |

---

## MCP 方法详述与示例

### 1. `tools/list` — 列出工具

**说明**：返回所有可用工具列表。格式遵循 Anthropic MCP 规范，使用 `inputSchema` 描述参数。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-001",
    "method": "tools/list",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-001",
    "result": {
        "tools": [
            {
                "name": "wechat_draft_add",
                "description": "创建微信草稿",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "文章标题"
                        },
                        "content": {
                            "type": "string",
                            "description": "文章正文"
                        },
                        "cover_media_id": {
                            "type": "string",
                            "description": "封面素材 ID（可选）"
                        }
                    },
                    "required": ["title", "content"]
                }
            }
        ]
    }
}
```

> **内部过程**：MCP 适配层收到此请求后，通过 PIP `tools/list` 获取内部工具列表，然后将 `params` 转换为 `inputSchema` 格式返回。

---

### 2. `tools/call` — 调用工具

**说明**：调用一个工具。输入输出格式遵循 Anthropic MCP 规范，使用 `content` 数组返回结果以支持多模态。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-002",
    "method": "tools/call",
    "params": {
        "name": "wechat_draft_add",
        "arguments": {
            "title": "今日新闻",
            "content": "新闻正文内容..."
        }
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-002",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "草稿创建成功！草稿 ID: draft_xxx"
            }
        ],
        "isError": false
    }
}
```

**错误响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-002",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "工具执行失败：标题超过 32 个字符限制"
            }
        ],
        "isError": true
    }
}
```

> **内部过程**：MCP 适配层将此请求翻译为 PIP `tools/call` 调用，然后将 PIP 响应结果中的 `data` 包装为 MCP `content` 数组。

---

### 3. `resources/list` — 列出资源

**说明**：返回所有可用的资源列表。资源是系统可以向客户端提供的结构化数据（如文件、数据库记录、API 响应等）。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-003",
    "method": "resources/list",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-003",
    "result": {
        "resources": [
            {
                "uri": "wechat://articles/draft_xxx",
                "name": "微信文章草稿",
                "description": "微信文章草稿内容与元数据",
                "mimeType": "application/json"
            },
            {
                "uri": "system://status",
                "name": "系统运行状态",
                "description": "Pulsar 系统当前运行状态概览",
                "mimeType": "application/json"
            }
        ]
    }
}
```

---

### 4. `resources/read` — 读取资源

**说明**：读取指定 URI 的资源内容。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-004",
    "method": "resources/read",
    "params": {
        "uri": "wechat://articles/draft_xxx"
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-004",
    "result": {
        "contents": [
            {
                "uri": "wechat://articles/draft_xxx",
                "mimeType": "application/json",
                "text": "{\"title\":\"今日新闻\",\"content\":\"新闻正文内容...\",\"status\":\"draft\",\"created_at\":\"2026-05-29T10:00:00Z\"}"
            }
        ]
    }
}
```

**错误响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-004",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "资源未找到: wechat://articles/nonexistent"
            }
        ],
        "isError": true
    }
}
```

---

### 5. `prompts/list` — 列出提示词

**说明**：返回所有可用的提示词模板列表。提示词是预定义的模板，用于指导 AI 模型的输出格式和行为。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-005",
    "method": "prompts/list",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-005",
    "result": {
        "prompts": [
            {
                "name": "article_writer",
                "description": "微信文章写作助手",
                "arguments": [
                    {
                        "name": "topic",
                        "description": "文章主题",
                        "required": true
                    },
                    {
                        "name": "tone",
                        "description": "文章风格（formal/casual）",
                        "required": false
                    }
                ]
            },
            {
                "name": "data_analyst",
                "description": "数据分析助手",
                "arguments": [
                    {
                        "name": "dataset",
                        "description": "数据集名称或路径",
                        "required": true
                    }
                ]
            }
        ]
    }
}
```

---

### 6. `prompts/get` — 获取提示词

**说明**：获取指定提示词模板的完整内容，包括模板文本和参数化后的结果。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-006",
    "method": "prompts/get",
    "params": {
        "name": "article_writer",
        "arguments": {
            "topic": "人工智能发展趋势",
            "tone": "formal"
        }
    }
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-006",
    "result": {
        "description": "微信文章写作助手",
        "messages": [
            {
                "role": "system",
                "content": {
                    "type": "text",
                    "text": "你是一位专业的微信文章写作助手。请用正式（formal）的语气撰写关于「人工智能发展趋势」的文章。文章应该结构清晰、观点明确、数据准确。"
                }
            },
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": "请开始撰写关于「人工智能发展趋势」的微信文章。"
                }
            }
        ]
    }
}
```

---

### 7. `system/capabilities` — 系统能力声明

**说明**：返回 Pulsar Tool Server 所支持的全部能力信息，供客户端发现适配。

**请求示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-007",
    "method": "system/capabilities",
    "params": {}
}
```

**成功响应示例**：

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-007",
    "result": {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "tools": {
                "listChanged": true
            },
            "resources": {
                "subscribe": true,
                "listChanged": true
            },
            "prompts": {
                "listChanged": false
            },
            "logging": {},
            "experimental": {
                "streaming": true
            }
        },
        "serverInfo": {
            "name": "pulsar-tool-server",
            "version": "1.0.0"
        }
    }
}
```

---

# 第三部分：PIP 与 MCP 对比

## 对比总表

| 特性 | PIP | MCP |
|------|-----|-----|
| **全称** | Pulsar Internal Protocol | Model Context Protocol |
| **面向受众** | 内部组件间通信（层与层） | 外部 AI 客户端 |
| **基础规范** | JSON-RPC 2.0 | Anthropic MCP 规范 |
| **传输方式** | stdio、in-process queue、HTTP（Phase 2） | HTTP SSE、stdio |
| **参数格式** | `params` 对象（简单键值对） | `inputSchema`（JSON Schema） |
| **返回格式** | `{ success, data }` | `{ content: [...] }`（content 数组，支持多模态） |
| **错误处理** | 标准 JSON-RPC error 对象 | `isError` 标志位 + content 数组 |
| **资源端点** | 无（资源通过工具访问） | `resources/list`、`resources/read` |
| **提示词端点** | 无（提示词通过工具访问） | `prompts/list`、`prompts/get` |
| **能力声明** | `system/status` | `system/capabilities` |
| **事件系统** | `event/publish`、`event/subscribe` | 无（暂未标准化） |
| **认证方式** | Bearer Token 或内部信任 | Bearer Token 或 OAuth |

## 协议栈关系

```
+------------------------------------------------------------------+
|                     外部客户端 (Claude Desktop / Agent)            |
+------------------------------------------------------------------+
                              |  MCP (Anthropic 标准)
                              v
+------------------------------------------------------------------+
|                 Pulsar Tool Server (MCP Adapter Layer)             |
|  - tools/list → tools/call → resources/list → resources/read     |
|  - prompts/list → prompts/get → system/capabilities              |
+------------------------------------------------------------------+
                              |  PIP (JSON-RPC 2.0)
                              v
+------------------------------------------------------------------+
|                     Pulsar Internal Layers                         |
|  Agent Layer  →  Orchestrator Layer  →  Tool Layer  →  Plugins   |
+------------------------------------------------------------------+
```

## MCP 到 PIP 的翻译映射

### tools/call 翻译示例

**外部 MCP 请求：**

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-002",
    "method": "tools/call",
    "params": {
        "name": "wechat_draft_add",
        "arguments": {
            "title": "今日新闻",
            "content": "新闻正文内容..."
        }
    }
}
```

**内部 PIP 请求（MCP 适配层翻译后）：**

```json
{
    "jsonrpc": "2.0",
    "id": "pip-req-001",
    "method": "tools/call",
    "params": {
        "name": "wechat_draft_add",
        "arguments": {
            "title": "今日新闻",
            "content": "新闻正文内容..."
        }
    }
}
```

**内部 PIP 响应：**

```json
{
    "jsonrpc": "2.0",
    "id": "pip-req-001",
    "result": {
        "success": true,
        "data": {
            "draft_id": "draft_xxx"
        }
    }
}
```

**外部 MCP 响应（MCP 适配层包装后）：**

```json
{
    "jsonrpc": "2.0",
    "id": "mcp-req-002",
    "result": {
        "content": [
            {
                "type": "text",
                "text": "草稿创建成功！草稿 ID: draft_xxx"
            }
        ],
        "isError": false
    }
}
```

### 翻译规则

| MCP 端点 | PIP 端点 | 转换说明 |
|----------|---------|---------|
| `tools/list` | `tools/list` | 将 PIP 返回的 `params` 格式转换为 `inputSchema`（JSON Schema）格式 |
| `tools/call` | `tools/call` | 透传 `name` 和 `arguments`；将 PIP 的 `{ success, data }` 包装为 MCP `content` 数组 |
| `resources/list` | — | 由 MCP 适配层自身维护资源注册表，无需 PIP 调用 |
| `resources/read` | — | 由 MCP 适配层根据 URI scheme 路由到对应的内部处理器 |
| `prompts/list` | — | 由 MCP 适配层自身维护提示词注册表，无需 PIP 调用 |
| `prompts/get` | — | 由 MCP 适配层根据 name 查找模板并注入参数 |
| `system/capabilities` | `system/status` | 从 `system/status` 获取版本信息，结合适配层自身能力声明返回 |

### 错误码翻译

| MCP 错误场景 | PIP 错误码 | 翻译方式 |
|-------------|-----------|---------|
| Parse Error | `-32700` | 透传 |
| Invalid Request | `-32600` | 透传 |
| Method Not Found | `-32601` | 透传 |
| Tool Error | `-32000` | 转为 `isError: true` + content 文本 |
| Rate Limited | `-32001` | 透传 |
| Auth Failed | `-32002` | 透传 |

---

## 附录：协议选择指南

| 场景 | 应使用的协议 |
|------|-------------|
| Agent Layer 调用 Tool Layer | PIP（in-process queue 或 stdio） |
| Tool Layer 调用插件 | PIP（stdio） |
| 外部 AI 客户端调用工具 | MCP（HTTP SSE 或 stdio） |
| 内部调试和健康检查 | PIP |
| 第三方系统集成 | MCP（外部端点） |
| 事件驱动的内部通知 | PIP（event/publish、event/subscribe） |
