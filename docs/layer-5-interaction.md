# Layer 5: 交互层（Interaction Layer）

## 概述

交互层是 Pulsar Agent 面向用户的接口层，提供 CLI 命令行界面、REPL 交互式会话、MCP 服务器接口以及渲染引擎。它是用户与 Agent 核心能力之间的桥梁。

交互层遵循**薄展示层（Thin Presenter）**架构设计：ConversationAgent 仅负责 REPL 循环与展示逻辑，所有意图理解委托给 Layer 2 Intent Recognition，所有操作执行委托给 Layer 3 Orchestrator，上下文管理委托给 Layer 2 Dialogue Manager。

```
用户输入
  │
  ▼
┌──────────────────────────────┐
│  Layer 5: ConversationAgent  │  ← 薄展示层：仅 REPL 循环 + 渲染
│  (Thin Presenter)            │
│  检查斜杠命令 / 委托 →       │
└──────────┬───────────────────┘
           │ PIP (Pulsar Internal Protocol)
           ▼
┌──────────────────────────────┐
│  Layer 2: Intent Recognition │  ← 意图理解
│  Layer 2: Dialogue Manager   │  ← 上下文管理
│  Layer 3: Orchestrator       │  ← ActionPlan 执行
└──────────────────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Layer 1: ToolRegistry       │  ← 工具实际执行
└──────────────────────────────┘
```

---

## 1. ConversationAgent（interaction/cli/conversation.py）

### 职责

ConversationAgent 是 REPL（Read-Eval-Print Loop）模式的核心，采用**薄展示层**设计：

| 职责 | 归属 | 说明 |
|------|------|------|
| REPL 主循环 | ✅ ConversationAgent | Banner → Prompt → Process → Render |
| 斜杠命令处理 | ✅ ConversationAgent | `/help`, `/exit`, `/clear`, `/skills` 等 |
| 输入提示与历史 | ✅ ConversationAgent | prompt_toolkit 集成 |
| 输出渲染 (Rich) | ✅ Renderer | 委托给 Renderer |
| **意图理解** | ❌ → **Layer 2** | 通过 PIP 委托给 Intent Recognition |
| **ActionPlan 生成** | ❌ → **Layer 2** | 通过 PIP 委托给 Intent Recognition |
| **ActionPlan 执行** | ❌ → **Layer 3** | 通过 PIP 委托给 Orchestrator |
| **上下文管理** | ❌ → **Layer 2** | 通过 PIP 委托给 Dialogue Manager |
| **工具调用** | ❌ → **Layer 1** | Orchestrator 调用 ToolRegistry |

### REPL 生命周期

```
┌────────────────────────────────────────────┐
│               REPL 生命周期                  │
│                                            │
│  ┌─────────┐    ┌─────────┐   ┌────────┐  │
│  │  Banner  │ →  │ Prompt  │ → │Process │  │
│  └─────────┘    └─────────┘   └───┬────┘  │
│       ↑                           │       │
│       └───────────────────────────┘       │
│           Render ←───── 继续              │
│                                            │
│  📌 Exit 条件: /exit, Ctrl+D, Ctrl+C       │
└────────────────────────────────────────────┘
```

#### Banner

- Agent 启动时打印欢迎信息。
- 包含：Logo（ASCII art）、版本号、当前配置文件哈希、加载的技能列表。
- 调用 `Renderer.show_banner()` 实现。

```
╔══════════════════════════════════════════╗
║        ⚡ Pulsar Agent v1.0.0            ║
║   Layer 5 — 交互式会话已启动              ║
║   📦 已加载技能: file, shell, web         ║
║   💡 输入 /help 查看帮助                  ║
╚══════════════════════════════════════════╝
```

#### Prompt

- 显示输入提示符，等待用户输入。
- 格式：`pulsar> `（默认）或 `pulsar[stream]> `（流式模式下）。
- 支持：`prompt_toolkit` 历史记录、Tab 补全、语法高亮。

#### Process — 委托式处理流程

用户输入后，ConversationAgent 执行以下**委托流程**：

```
用户输入 "帮我查一下 /tmp 目录下最大的文件"
       │
       ▼
┌─────────────────────────────────────────┐
│ ConversationAgent (Thin Presenter)      │
│  1. 追加用户消息到展示上下文 (本地副本)   │
│  2. 检查斜杠命令 → 是则本地处理          │
│  3. 通过 PIP 发送理解请求 → Layer 2     │
└────────────────┬────────────────────────┘
                 │ PIP Message: {intent/recognize, user_input, context_snapshot}
                 ▼
┌─────────────────────────────────────────┐
│ Layer 2: Intent Recognition             │
│  ┌────────────────────────────────┐     │
│  │ 理解用户意图                     │     │
│  │ 提取关键参数                     │     │
│  │ 生成 ActionPlan（步骤序列）       │     │
│  └──────────────┬─────────────────┘     │
└─────────────────┼───────────────────────┘
                  │ PIP Response: {intent, confidence, action_plan}
                  ▼
┌─────────────────────────────────────────┐
│ ConversationAgent (Thin Presenter)      │
│  显示 "正在执行计划..." (渲染可选)       │
│  通过 PIP 发送执行请求 → Layer 3        │
└────────────────┬────────────────────────┘
                 │ PIP Message: {orchestrator/execute, action_plan}
                 ▼
┌─────────────────────────────────────────┐
│ Layer 3: Orchestrator                   │
│  ┌────────────────────────────────┐     │
│  │ Step 1: shell/find /tmp -type f│     │
│  │   -exec ls -lh | Sort by size  │     │
│  │                                │     │
│  │ Step 2: 解析结果，提取 top 5   │     │
│  └──────────────┬─────────────────┘     │
└─────────────────┼───────────────────────┘
                  │ PIP Response: {results, summary}
                  ▼
┌─────────────────────────────────────────┐
│ ConversationAgent (Thin Presenter)      │
│  追加助手回复到展示上下文               │
│  委托 Renderer 渲染最终回复             │
└─────────────────────────────────────────┘
```

> **关键设计原则**：ConversationAgent 不再直接调用 LLM，也不再管理工具注册表或执行逻辑。它仅作为**展示层**转发请求并通过 PIP 接收响应。

#### ActionPlan 结构（Layer 2 产出，Layer 3 消费）

```python
@dataclass
class ActionPlan:
    workflow_id: str             # 工作流唯一标识
    steps: list[ActionStep]      # 执行步骤列表
    user_intent: str             # 用户意图描述
    confidence: float            # 意图识别置信度
    created_at: datetime         # 创建时间

@dataclass
class ActionStep:
    tool: str                    # 工具名称，如 "shell/execute"
    params: dict                 # 调用参数
    description: str             # 这一步做什么（自然语言）
    depends_on: list[int]        # 依赖的步骤索引
```

> **注**：此为轻量展示结构，完整规范模型（含 Pydantic 验证、frozen 不可变等）定义在 `pulsar/models/pip.py` 的 `ActionPlan` / `ActionStep` 中。`workflow_id` 和 `created_at` 由 Layer 2 生成后向下传递。`depends_on` 统一使用步骤索引（`list[int]`）而非步骤 ID。

#### Render

- 将 Agent 的回复渲染到终端。
- 支持：Markdown 渲染、代码块语法高亮、表格、进度条。
- 流式模式下逐 token 输出。
- 调用 `Renderer.render_response()` 实现。

#### 多轮上下文（Multi-turn Context）— **委托给 Layer 2**

> **变更**：ConversationAgent 不再直接管理 LLM 上下文窗口。它维护一个**展示层本地副本**用于渲染目的，但**真正的上下文管理**（窗口裁剪、摘要、token 计数）由 Layer 2 Dialogue Manager 负责。

| 能力 | 归属 | 说明 |
|------|------|------|
| 展示层上下文副本 | ✅ ConversationAgent | 用于渲染 `/history` 等 |
| 上下文窗口裁剪 | ❌ → Layer 2 DlgMgr | 基于 max_tokens 自动裁剪 |
| 对话摘要 | ❌ → Layer 2 DlgMgr | 长对话自动摘要 |
| 会话保存/加载 | ❌ → Layer 2 DlgMgr | `/save`, `/load` 委托 |

#### 斜杠命令（Slash Commands）

ConversationAgent 本地处理以下命令：

| 命令 | 说明 | 处理方式 |
|------|------|----------|
| `/help` | 显示帮助信息（所有可用命令 + 技能列表） | 本地 + PIP 获取技能列表 |
| `/exit` | 退出 REPL | 本地 |
| `/clear` | 清空本地展示上下文 + 委托 Layer 2 DlgMgr 清空 | 本地 + PIP |
| `/skills` | 列出已加载的技能及其工具（通过 PIP 从 Layer 1 ToolRegistry 获取） | 本地 + PIP |
| `/config` | 显示当前配置 | 本地 |
| `/history` | 显示最近 N 条历史记录（从本地展示上下文） | 本地 |
| `/save <name>` | 保存当前会话 | PIP 委托 Layer 2 DlgMgr |
| `/load <name>` | 加载之前保存的会话 | PIP 委托 Layer 2 DlgMgr |
| `/stats` | 显示会话统计（token 数、调用次数） | PIP 委托 Layer 2 DlgMgr + Layer 3 |

#### 伪代码实现

```python
class ConversationAgent:
    """薄展示层：仅负责 REPL 循环与展示，委托意图和执行给下层。"""

    def __init__(self, pip_bus: PipBus, renderer: Renderer):
        self.pip_bus = pip_bus          # 与 Layer 2/3 通信的 PIP 总线
        self.renderer = renderer        # Rich 渲染器
        self.display_context: list[dict] = []  # 展示层本地上下文副本
        self.running = False

    async def run(self):
        """REPL 主循环"""
        self.running = True
        await self.renderer.show_banner()

        while self.running:
            try:
                # 1. Prompt
                user_input = await self._prompt_user()
                if user_input is None:      # Ctrl+D
                    break

                # 2. 检查斜杠命令（本地处理）
                if user_input.startswith("/"):
                    await self._handle_slash_command(user_input)
                    continue

                # 3. 更新本地展示上下文
                self.display_context.append(
                    {"role": "user", "content": user_input}
                )

                # ─── 委托 Layer 2: 意图理解 ───
                await self.renderer.show_info("正在理解意图...")
                intent_result = await self.pip_bus.request(
                    target="layer2/intent",
                    message={
                        "intent/recognize": {
                            "user_input": user_input,
                            "context_snapshot": self.display_context[-5:],
                        }
                    }
                )
                # intent_result = {intent, confidence, action_plan}

                # ─── 委托 Layer 3: 执行 ActionPlan ───
                await self.renderer.show_info("正在执行计划...")
                execution_result = await self.pip_bus.request(
                    target="layer3/orchestrator",
                    message={
                        "orchestrator/execute": {
                            "action_plan": intent_result["action_plan"],
                            "context": intent_result.get("context", {}),
                        }
                    }
                )
                # execution_result = {results, summary}

                # 4. 获取最终回复（可由 Layer 3 直接返回，或本地拼接）
                response = execution_result.get(
                    "summary",
                    "任务执行完成。"
                )

                # 5. 渲染输出
                await self.renderer.render_response(response)

                # 6. 更新本地展示上下文
                self.display_context.append(
                    {"role": "assistant", "content": response}
                )

            except KeyboardInterrupt:
                continue          # Ctrl+C 不退出，重新 prompt
            except EOFError:
                break

        await self.renderer.show_goodbye()

    async def _handle_slash_command(self, cmd: str):
        """处理斜杠命令（本地）"""
        parts = cmd.split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        handlers = {
            "/exit":   lambda: setattr(self, 'running', False),
            "/clear":  self._clear_context,
            "/help":   self._show_help,
            "/skills": self._show_skills,
            "/config": self._show_config,
            "/history": lambda: self._show_history(args[0] if args else "10"),
            "/save":   lambda: self._save_session(args[0] if args else ""),
            "/load":   lambda: self._load_session(args[0] if args else ""),
            "/stats":  self._show_stats,
        }

        handler = handlers.get(command)
        if handler:
            result = handler()
            if asyncio.iscoroutine(result):
                await result
        else:
            await self.renderer.show_error(f"未知命令: {command}")

    async def _clear_context(self):
        """清空本地展示上下文 + 委托 Layer 2 清空对话管理上下文"""
        self.display_context = [self.display_context[0]]  # 保留系统提示
        await self.pip_bus.send(
            target="layer2/dialogue_manager",
            message={"dialogue/clear": {}}
        )
        await self.renderer.show_success("对话上下文已清空")

    async def _show_help(self):
        """显示帮助信息"""
        skills = await self.pip_bus.request(
            target="layer1/tool_registry",
            message={"tools/list": {}}
        )
        help_text = self._build_help_text(skills)
        await self.renderer.render_response(help_text)

    async def _show_skills(self):
        """通过 PIP 从 Layer 1 ToolRegistry 获取技能列表"""
        skills = await self.pip_bus.request(
            target="layer1/tool_registry",
            message={"tools/list": {}}
        )
        await self.renderer.render_table(
            headers=["技能", "工具", "描述"],
            rows=[
                [s["name"], ", ".join(s["tools"]), s["description"]]
                for s in skills.get("skills", [])
            ],
            title="已加载技能"
        )

    async def _show_stats(self):
        """委托 Layer 2/3 获取统计信息"""
        stats = await self.pip_bus.request(
            target="layer3/orchestrator",
            message={"orchestrator/session_stats": {}}
        )
        await self.renderer.render_response(
            f"**会话统计**\n\n"
            f"- Token 总数: {stats.get('total_tokens', 'N/A')}\n"
            f"- 工具调用次数: {stats.get('tool_calls', 'N/A')}\n"
            f"- 执行步骤: {stats.get('steps_executed', 'N/A')}\n"
        )

    async def _save_session(self, name: str):
        """委托 Layer 2 Dialogue Manager 保存会话"""
        if not name:
            await self.renderer.show_error("请指定会话名称: /save <name>")
            return
        await self.pip_bus.send(
            target="layer2/dialogue_manager",
            message={"dialogue/save": {"name": name}}
        )
        await self.renderer.show_success(f"会话已保存: {name}")

    async def _load_session(self, name: str):
        """委托 Layer 2 Dialogue Manager 加载会话"""
        if not name:
            await self.renderer.show_error("请指定会话名称: /load <name>")
            return
        result = await self.pip_bus.request(
            target="layer2/dialogue_manager",
            message={"dialogue/load": {"name": name}}
        )
        self.display_context = result.get("context", [])
        await self.renderer.show_success(f"会话已加载: {name}")
```

---

## 2. CLI 主入口（interaction/cli/main.py）

### 职责

CLI 主入口是用户启动 Agent 的命令行接口，基于 `click` 框架实现，支持三种运行模式。

### 三种运行模式

| 模式 | 命令参数 | 说明 |
|------|---------|------|
| **REPL 模式**（默认） | `pulsar` | 启动交互式 REPL 会话 |
| **命令模式** | `pulsar --cmd "帮我查下文件"` | 单条命令执行，执行后进入 REPL |
| **一次执行模式** | `pulsar --once "帮我查下文件"` | 单条命令执行，执行后退出 |

### CLI 入口实现

```python
# interaction/cli/main.py
import click
import asyncio

@click.group(invoke_without_command=True)
@click.option("--cmd", "-c", default=None,
              help="执行一条命令后进入 REPL")
@click.option("--once", "-1", default=None,
              help="执行一条命令后退出")
@click.option("--config", "-f", default=None,
              help="指定配置文件路径")
@click.option("--verbose", "-v", is_flag=True, help="详细输出")
@click.pass_context
def cli(ctx, cmd, once, config, verbose):
    """⚡ Pulsar Agent — 智能体交互式 CLI"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose

    if once:
        # 一次执行模式
        asyncio.run(_run_once(once, ctx.obj))
    elif cmd:
        # 命令模式
        asyncio.run(_run_and_repl(cmd, ctx.obj))
    else:
        # 默认 REPL 模式
        asyncio.run(_run_repl(ctx.obj))

@cli.command()
def version():
    """显示版本信息"""
    click.echo(f"Pulsar Agent v{__version__}")

@cli.command()
def help():
    """显示详细帮助"""
    click.echo("""Pulsar Agent — 智能体交互式框架
使用方式:
  pulsar                   启动交互式 REPL
  pulsar --cmd <命令>      执行命令后进入 REPL
  pulsar --once <命令>     执行命令后退出
  pulsar version           查看版本
  pulsar help              查看帮助
""")

async def _init_agent(ctx) -> ConversationAgent:
    """初始化 Agent 组件（薄展示层）"""
    config = load_config(ctx.get("config"))

    # 初始化下层组件
    pip_bus = PipBus()                       # 进程内消息总线
    layer2_intent = IntentRecognition()      # Layer 2 意图识别（按需初始化）
    layer2_dlgmgr = DialogueManager()        # Layer 2 对话管理
    layer3_orch = Orchestrator()             # Layer 3 编排器
    renderer = Renderer()                    # 本层渲染器

    # 注册 PIP 路由
    pip_bus.register("layer2/intent", layer2_intent)
    pip_bus.register("layer2/dialogue_manager", layer2_dlgmgr)
    pip_bus.register("layer3/orchestrator", layer3_orch)

    # 创建薄展示层 Agent
    agent = ConversationAgent(
        pip_bus=pip_bus,
        renderer=renderer,
    )
    return agent

async def _run_repl(ctx):
    """启动 REPL（默认模式）"""
    agent = await _init_agent(ctx)
    await agent.run()

async def _run_and_repl(cmd, ctx):
    """执行命令后进入 REPL"""
    agent = await _init_agent(ctx)
    await agent.process_one_input(cmd)
    await agent.run()

async def _run_once(cmd, ctx):
    """执行一次后退出"""
    agent = await _init_agent(ctx)
    await agent.process_one_input(cmd)
    await agent.shutdown()
```

### 配置加载流程

```
CLI 启动
  │
  ▼
加载默认配置 (config/default.yaml)
  │
  ▼
覆盖用户配置 (--config 或 ~/.pulsar/config.yaml)
  │
  ▼
初始化所有组件
  ├── PipBus                     ← 进程内消息总线
  ├── Layer 2: IntentRecognition ← 意图识别
  ├── Layer 2: DialogueManager   ← 上下文管理
  ├── Layer 3: Orchestrator      ← 执行编排
  └── Renderer                   ← UI 渲染
  │
  ▼
创建 ConversationAgent (Thin Presenter)
  │
  ▼
进入对应模式
```

---

## 3. MCP Server（interaction/mcp_server/）

### 职责

MCP Server 实现 **Model Context Protocol** 服务端，通过 stdio 传输暴露工具、资源和提示词端点，供 LLM 主机（如 Claude Desktop、VS Code 插件）调用。工具定义从 Layer 1 ToolRegistry 读取。

### 协议

- **传输层**：`stdio`（标准输入/输出）
- **消息格式**：JSON-RPC 2.0，每行一个消息（`\n` 分隔）
- **生命周期**：由 LLM 主机启动子进程管理

### 端点一览

| 端点 | 方法 | 说明 | 合规版本 |
|------|------|------|----------|
| **Tools** | `tools/list` | 列出所有可用工具 | MCP 2024-11 |
| | `tools/call` | 调用指定工具 | MCP 2024-11 |
| **Resources** | `resources/list` | 列出所有可用资源 | MCP 2024-11 |
| | `resources/read` | 读取指定资源内容 | MCP 2024-11 |
| **Prompts** | `prompts/list` | 列出所有可用提示词模板 | MCP 2024-11 |
| | `prompts/get` | 获取指定提示词模板（含参数填充） | MCP 2024-11 |
| **System** | `system/ping` | 健康检查 | 自定义 |
| | `system/capabilities` | 返回平台功能清单 | 自定义 |

### 8 个标准工具（从 Layer 1 ToolRegistry 注册）

工具定义从 Layer 1 `ToolRegistry` 读取，使用 **inputSchema（camelCase）** 格式以符合 MCP 外部规范。

| 工具名称 | 描述 | inputSchema |
|---------|------|-------------|
| `read_file` | 读取文件内容 | `{ "type": "object", "properties": { "path": { "type": "string", "description": "文件路径" } }, "required": ["path"] }` |
| `write_file` | 写入文件内容 | `{ "type": "object", "properties": { "path": { "type": "string" }, "content": { "type": "string" } }, "required": ["path", "content"] }` |
| `search_files` | 搜索文件/内容 | `{ "type": "object", "properties": { "pattern": { "type": "string" }, "path": { "type": "string" }, "type": { "type": "string", "enum": ["content", "files"] } }, "required": ["pattern"] }` |
| `execute_command` | 执行 shell 命令 | `{ "type": "object", "properties": { "command": { "type": "string" }, "timeout": { "type": "number" } }, "required": ["command"] }` |
| `list_directory` | 列出目录内容 | `{ "type": "object", "properties": { "path": { "type": "string" }, "depth": { "type": "number" } }, "required": ["path"] }` |
| `get_system_info` | 获取系统信息 | `{ "type": "object", "properties": {} }` |
| `ask_user` | 向用户提问等待确认 | `{ "type": "object", "properties": { "question": { "type": "string" }, "type": { "type": "string", "enum": ["confirm", "input", "choice"] }, "choices": { "type": "array", "items": { "type": "string" } } }, "required": ["question", "type"] }` |
| `search_web` | 搜索网页内容 | `{ "type": "object", "properties": { "query": { "type": "string" }, "maxResults": { "type": "number" } }, "required": ["query"] }` |

> **注意**：外部暴露的 `inputSchema` 使用 **camelCase**（如 `maxResults`），内部实现中的 Python 代码仍使用 snake_case，由 MCP Handler 负责转换。

### Resources 端点

Resources 提供对 Agent 可读文件的访问，遵循 MCP 资源模型。

#### 资源列表（resources/list）

```python
async def handle_resources_list(self, params=None) -> dict:
    """返回所有可用资源"""
    return {
        "resources": [
            {
                "uri": "pulsar://config/current",
                "name": "当前配置",
                "description": "当前 Agent 运行的配置信息",
                "mimeType": "application/json",
            },
            {
                "uri": "pulsar://skills/list",
                "name": "已加载技能",
                "description": "当前所有已加载的技能及其工具列表",
                "mimeType": "application/json",
            },
            {
                "uri": "pulsar://session/current",
                "name": "当前会话上下文",
                "description": "当前对话的上下文摘要",
                "mimeType": "text/plain",
            },
            {
                "uri": "pulsar://system/info",
                "name": "系统信息",
                "description": "主机系统信息（OS、CPU、内存等）",
                "mimeType": "application/json",
            },
            {
                "uri": "pulsar://logs/recent",
                "name": "最近日志",
                "description": "最近 N 条审计日志",
                "mimeType": "text/plain",
            },
        ]
    }
```

#### 资源读取（resources/read）

```python
async def handle_resources_read(self, params: dict) -> dict:
    """读取指定资源内容"""
    uri = params.get("uri", "")

    resource_handlers = {
        "pulsar://config/current": self._read_config,
        "pulsar://skills/list":    self._read_skills,
        "pulsar://session/current": self._read_session,
        "pulsar://system/info":     self._read_system_info,
        "pulsar://logs/recent":     self._read_recent_logs,
    }

    handler = resource_handlers.get(uri)
    if not handler:
        return {"error": {"code": -32602, "message": f"Unknown resource: {uri}"}}

    content = await handler()
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": content.get("mimeType", "text/plain"),
                "text": content.get("text", ""),
            }
        ]
    }
```

### Prompts 端点

Prompts 提供可复用的提示词模板，LLM 主机可列出并获取特定模板。

#### 提示词列表（prompts/list）

```python
async def handle_prompts_list(self, params=None) -> dict:
    """返回所有可用提示词模板"""
    return {
        "prompts": [
            {
                "name": "code_review",
                "description": "代码审查提示词",
                "arguments": [
                    {"name": "language", "description": "编程语言", "required": True},
                    {"name": "code", "description": "代码内容", "required": True},
                ],
            },
            {
                "name": "system_prompt",
                "description": "Agent 系统提示词模板",
                "arguments": [
                    {"name": "skills", "description": "已加载技能列表", "required": False},
                ],
            },
            {
                "name": "summarize",
                "description": "对话摘要提示词",
                "arguments": [
                    {"name": "context", "description": "对话上下文", "required": True},
                ],
            },
            {
                "name": "intent_analysis",
                "description": "意图分析提示词模板",
                "arguments": [
                    {"name": "user_input", "description": "用户输入", "required": True},
                    {"name": "tools", "description": "可用工具列表", "required": False},
                ],
            },
        ]
    }
```

#### 提示词获取（prompts/get）

```python
async def handle_prompts_get(self, params: dict) -> dict:
    """获取指定提示词模板（含参数填充）"""
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    prompt_handlers = {
        "code_review":     self._prompt_code_review,
        "system_prompt":   self._prompt_system,
        "summarize":       self._prompt_summarize,
        "intent_analysis": self._prompt_intent_analysis,
    }

    handler = prompt_handlers.get(name)
    if not handler:
        return {"error": {"code": -32602, "message": f"Unknown prompt: {name}"}}

    return await handler(arguments)
```

### System 端点

#### capabilities（自定义端点）

```python
async def handle_system_capabilities(self, params=None) -> dict:
    """返回平台功能清单"""
    return {
        "capabilities": {
            "tools": {
                "listChanged": False,   # 是否支持 tools/list 变更通知
            },
            "resources": {
                "subscribe": False,     # 是否支持资源订阅
                "listChanged": False,
            },
            "prompts": {
                "listChanged": False,
            },
            "platform": {
                "name": "pulsar",
                "version": __version__,
                "os": sys.platform,
                "python": sys.version,
                "skills_count": len(self.TOOL_REGISTRY),
                "resources_count": 5,
                "prompts_count": 4,
                "max_tool_args_size": 1024 * 100,  # 100KB
            },
            "experimental": {
                "streaming": True,
            },
        }
    }
```

### 实现要点

> **架构说明 (Architecture Note)**：`ToolRegistry` 的主实例位于 **Layer 1 Runtime**。Layer 5 MCP Server 应通过 PIP 从 Layer 1 读取工具定义，**不要**在 Layer 5 创建独立的 ToolRegistry 实例。`MCPRequestHandler.__init__` 接受的 `tool_registry` 参数应传入 Layer 1 ToolRegistry 的引用或代理，而非重新构建。`_default_registry()` 备用方法仅用于独立测试，不应在生产路径中使用。

```python
# interaction/mcp_server/handler.py
class MCPRequestHandler:
    """处理 MCP 协议的 JSON-RPC 请求，支持 Tools/Resources/Prompts 端点。"""

    HANDLERS = {
        # Tools
        "tools/list":          "handle_tools_list",
        "tools/call":          "handle_tools_call",
        # Resources (MCP 2024-11)
        "resources/list":      "handle_resources_list",
        "resources/read":      "handle_resources_read",
        # Prompts (MCP 2024-11)
        "prompts/list":        "handle_prompts_list",
        "prompts/get":         "handle_prompts_get",
        # System (自定义)
        "system/ping":         "handle_system_ping",
        "system/capabilities": "handle_system_capabilities",
    }

    def __init__(self, tool_registry: dict | None = None):
        """
        从 Layer 1 ToolRegistry 注册工具。
        如果未提供，使用内置默认注册表。
        """
        self.TOOL_REGISTRY = tool_registry or self._default_registry()
        # 转换工具描述为 inputSchema（camelCase）格式
        self._normalize_schemas()

    def _normalize_schemas(self):
        """确保所有工具 schema 使用 inputSchema camelCase 命名"""
        for name, tool_def in self.TOOL_REGISTRY.items():
            if "inputSchema" not in tool_def:
                tool_def["inputSchema"] = tool_def.get("schema", {"type": "object", "properties": {}})
            # 递归转换 snake_case → camelCase 在 schema 属性名中
            tool_def["inputSchema"] = self._snake_to_camel_schema(
                tool_def["inputSchema"]
            )

    def _snake_to_camel_schema(self, schema: dict) -> dict:
        """递归将 schema 属性名从 snake_case 转为 camelCase"""
        if not isinstance(schema, dict):
            return schema
        result = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                result[key] = value  # 属性名本身保持原样，属性值中的名字无需转换
            else:
                result[key] = value
        return result

    async def handle_request(self, request: dict) -> dict:
        method = request["method"]
        handler_name = self.HANDLERS.get(method)
        if handler_name:
            return await getattr(self, handler_name)(request.get("params"))
        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    # ── Tools ──

    async def handle_tools_list(self, params=None) -> dict:
        """返回所有工具定义（名称 + description + inputSchema）"""
        tools = []
        for name, tool_def in self.TOOL_REGISTRY.items():
            tools.append({
                "name": name,
                "description": tool_def.get("description", ""),
                "inputSchema": tool_def.get("inputSchema", {"type": "object", "properties": {}}),
            })
        return {"tools": tools}

    async def handle_tools_call(self, params: dict) -> dict:
        """调用指定工具"""
        name = params["name"]
        arguments = params.get("arguments", {})

        tool_def = self.TOOL_REGISTRY.get(name)
        if not tool_def:
            return {"error": {"code": -32602, "message": f"Unknown tool: {name}"}}

        try:
            # 外部 camelCase → 内部 snake_case 转换
            snake_args = self._camel_to_snake_keys(arguments)
            result = await tool_def["fn"](**snake_args)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            return {"error": {"code": -32000, "message": str(e)}}

    def _camel_to_snake_keys(self, d: dict) -> dict:
        """将字典键从 camelCase 转为 snake_case"""
        import re
        def camel_to_snake(name):
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        return {camel_to_snake(k): v for k, v in d.items()}

    # ── Resources ──

    async def handle_resources_list(self, params=None) -> dict:
        """返回所有可用资源"""
        return {
            "resources": [
                {
                    "uri": "pulsar://config/current",
                    "name": "当前配置",
                    "description": "当前 Agent 运行的配置信息",
                    "mimeType": "application/json",
                },
                {
                    "uri": "pulsar://skills/list",
                    "name": "已加载技能",
                    "description": "当前所有已加载的技能及其工具列表",
                    "mimeType": "application/json",
                },
                {
                    "uri": "pulsar://session/current",
                    "name": "当前会话上下文",
                    "description": "当前对话的上下文摘要",
                    "mimeType": "text/plain",
                },
                {
                    "uri": "pulsar://system/info",
                    "name": "系统信息",
                    "description": "主机系统信息（OS、CPU、内存等）",
                    "mimeType": "application/json",
                },
                {
                    "uri": "pulsar://logs/recent",
                    "name": "最近日志",
                    "description": "最近 N 条审计日志",
                    "mimeType": "text/plain",
                },
            ]
        }

    async def handle_resources_read(self, params: dict) -> dict:
        """读取指定资源内容"""
        uri = params.get("uri", "")

        resource_handlers = {
            "pulsar://config/current": self._read_config,
            "pulsar://skills/list":    self._read_skills,
            "pulsar://session/current": self._read_session,
            "pulsar://system/info":     self._read_system_info,
            "pulsar://logs/recent":     self._read_recent_logs,
        }

        handler = resource_handlers.get(uri)
        if not handler:
            return {"error": {"code": -32602, "message": f"Unknown resource: {uri}"}}

        content = await handler()
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": content.get("mimeType", "text/plain"),
                    "text": content.get("text", ""),
                }
            ]
        }

    # ── Prompts ──

    async def handle_prompts_list(self, params=None) -> dict:
        """返回所有可用提示词模板"""
        return {
            "prompts": [
                {
                    "name": "code_review",
                    "description": "代码审查提示词",
                    "arguments": [
                        {"name": "language", "description": "编程语言", "required": True},
                        {"name": "code", "description": "代码内容", "required": True},
                    ],
                },
                {
                    "name": "system_prompt",
                    "description": "Agent 系统提示词模板",
                    "arguments": [
                        {"name": "skills", "description": "已加载技能列表", "required": False},
                    ],
                },
                {
                    "name": "summarize",
                    "description": "对话摘要提示词",
                    "arguments": [
                        {"name": "context", "description": "对话上下文", "required": True},
                    ],
                },
                {
                    "name": "intent_analysis",
                    "description": "意图分析提示词模板",
                    "arguments": [
                        {"name": "user_input", "description": "用户输入", "required": True},
                        {"name": "tools", "description": "可用工具列表", "required": False},
                    ],
                },
            ]
        }

    async def handle_prompts_get(self, params: dict) -> dict:
        """获取指定提示词模板（含参数填充）"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        prompt_handlers = {
            "code_review":     self._prompt_code_review,
            "system_prompt":   self._prompt_system,
            "summarize":       self._prompt_summarize,
            "intent_analysis": self._prompt_intent_analysis,
        }

        handler = prompt_handlers.get(name)
        if not handler:
            return {"error": {"code": -32602, "message": f"Unknown prompt: {name}"}}

        return await handler(arguments)

    async def _prompt_code_review(self, args: dict) -> dict:
        language = args.get("language", "unknown")
        code = args.get("code", "")
        return {
            "messages": [
                {
                    "role": "user",
                    "content": f"请审查以下 {language} 代码：\n\n```{language}\n{code}\n```\n\n请检查：代码质量、安全性、性能问题、最佳实践。"
                }
            ],
            "description": f"代码审查 — {language}",
        }

    async def _prompt_system(self, args: dict) -> dict:
        skills = args.get("skills", "未知")
        return {
            "messages": [
                {
                    "role": "system",
                    "content": f"你是 Pulsar Agent，一个智能助手。已加载技能: {skills}。请根据用户需求选择合适的工具完成任务。"
                }
            ],
            "description": "系统提示词",
        }

    async def _prompt_summarize(self, args: dict) -> dict:
        context = args.get("context", "")
        return {
            "messages": [
                {
                    "role": "user",
                    "content": f"请对以下对话进行摘要：\n\n{context}\n\n摘要要求：简洁、保留关键信息。"
                }
            ],
            "description": "对话摘要",
        }

    async def _prompt_intent_analysis(self, args: dict) -> dict:
        user_input = args.get("user_input", "")
        tools = args.get("tools", "未知")
        return {
            "messages": [
                {
                    "role": "system",
                    "content": f"分析用户意图并生成执行计划。可用工具: {tools}。请以 JSON 格式返回 {{intent, confidence, steps: [{{tool, params, description, depends_on}}]}}。"
                },
                {
                    "role": "user",
                    "content": user_input,
                }
            ],
            "description": "意图分析",
        }

    # ── System ──

    async def handle_system_ping(self, params=None) -> dict:
        """健康检查"""
        return {"status": "ok", "version": __version__}

    async def handle_system_capabilities(self, params=None) -> dict:
        """返回平台功能清单"""
        return {
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": False,
                },
                "prompts": {
                    "listChanged": False,
                },
                "platform": {
                    "name": "pulsar",
                    "version": __version__,
                    "os": sys.platform,
                    "python": sys.version,
                    "skills_count": len(self.TOOL_REGISTRY),
                    "resources_count": 5,
                    "prompts_count": 4,
                    "max_tool_args_size": 1024 * 100,
                },
                "experimental": {
                    "streaming": True,
                },
            }
        }

    # ── Resource Handlers ──

    async def _read_config(self) -> dict:
        return {"mimeType": "application/json", "text": json.dumps(config.current, indent=2)}

    async def _read_skills(self) -> dict:
        return {"mimeType": "application/json", "text": json.dumps(self._get_skills_summary(), indent=2)}

    async def _read_session(self) -> dict:
        return {"mimeType": "text/plain", "text": "当前会话摘要（待实现）"}

    async def _read_system_info(self) -> dict:
        import platform
        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
        }
        return {"mimeType": "application/json", "text": json.dumps(info, indent=2)}

    async def _read_recent_logs(self) -> dict:
        return {"mimeType": "text/plain", "text": "最近日志（待实现）"}
```

### stdio 传输实现

```python
# interaction/mcp_server/transport.py
import sys
import json

class StdioServerTransport:
    """通过标准输入/输出传输 JSON-RPC 消息"""

    def __init__(self, handler: MCPRequestHandler):
        self.handler = handler

    async def start(self):
        """主循环：从 stdin 读取请求，处理，写入 stdout"""
        async for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = await self.handler.handle_request(request)
                if "id" in request:       # 非通知消息才回复
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                error = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(error) + "\n")
                sys.stdout.flush()
```

### Session Management（会话管理）

> **性能/伸缩性设计要点**：当 MCP Server 通过 WebSocket 或 HTTP 传输协议（非 stdio）运行时，每个独立的 WebSocket/HTTP 连接应获得自己独立的 `ConversationAgent` 处理器实例。这称为 **session-per-connection** 模式，确保各用户会话的上下文隔离与资源公平分配。

**核心原则**：
- 每个连接拥有独立的 `ConversationAgent` 实例（含独立的 `display_context` 和 PIP 路由）。
- 连接断开时自动清理对应的 Agent 实例，释放其持有的内存和连接池资源。
- 连接的 `ConversationAgent` 实例通过 **会话工厂（Session Factory）** 创建，工厂负责注入共享的 PIPBus 引用和 Renderer 实例。

```python
# interaction/mcp_server/session.py
import asyncio
from typing import Awaitable, Callable
from ..cli.conversation import ConversationAgent
from ..cli.renderer import Renderer
from runtime.pip_bus import PipBus


class SessionFactory:
    """会话工厂——为每个 WebSocket/HTTP 连接创建独立的 ConversationAgent。"""

    def __init__(self, pip_bus: PipBus):
        self.pip_bus = pip_bus          # 共享的 PIPBus 引用（所有会话共用）
        self._sessions: dict[str, ConversationAgent] = {}

    async def create_session(self, session_id: str) -> ConversationAgent:
        """为指定 session_id 创建独立的 ConversationAgent 实例。"""
        renderer = Renderer()           # 每个会话独立渲染器
        agent = ConversationAgent(
            pip_bus=self.pip_bus,
            renderer=renderer,
        )
        self._sessions[session_id] = agent
        return agent

    async def destroy_session(self, session_id: str):
        """销毁会话，释放资源。"""
        agent = self._sessions.pop(session_id, None)
        if agent:
            # 清理 agent 持有的资源（如有连接池等）
            agent.running = False

    def get_session(self, session_id: str) -> ConversationAgent | None:
        """获取指定会话的 Agent 实例。"""
        return self._sessions.get(session_id)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)


# WebSocket 连接处理示意
async def handle_websocket(websocket, session_factory: SessionFactory):
    """每个 WebSocket 连接对应一个独立的会话。"""
    session_id = str(id(websocket))     # 或使用连接自带的 session_id
    agent = await session_factory.create_session(session_id)
    try:
        async for message in websocket:
            response = await agent.process_one_input(message)
            await websocket.send(response)
    finally:
        await session_factory.destroy_session(session_id)
```

**关键规则**：
- `PIPBus` 是共享单例（所有会话共用同一条消息总线），但每个会话的 `ConversationAgent` 拥有独立的 `display_context`。
- 会话工厂应在 MCP Server 启动时创建一次，持有 `PIPBus` 引用，随 Server 生命周期共存。
- 高并发场景下，注意 `active_sessions` 数量不应超过 `runtime.max_concurrency` 配置值。
- WebSocket 传输模式下，`idle_timeout` 配置项用于自动回收超时会话。

---

## 4. Renderer（interaction/cli/renderer.py）

### 职责

Renderer 负责终端 UI 渲染，使用 `rich` 库提供美观的输出格式。支持富文本表格、横幅、确认提示、进度条和流式输出。

### 核心功能

#### 富文本表格（Rich Tables）

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm

class Renderer:
    def __init__(self):
        self.console = Console()

    def render_table(self, headers: list[str],
                     rows: list[list[str]],
                     title: str | None = None):
        """渲染一个富文本表格"""
        table = Table(title=title)
        for header in headers:
            table.add_column(header, style="cyan")
        for row in rows:
            table.add_row(*row)
        self.console.print(table)

    def show_banner(self, version: str, skills: list[str]):
        """显示启动横幅"""
        banner = Panel.fit(
            f"[bold yellow]⚡ Pulsar Agent v{version}[/]\n"
            f"[dim]交互式会话已启动[/]\n"
            f"📦 已加载技能: {', '.join(skills)}\n"
            f"💡 输入 [bold]/help[/] 查看帮助",
            border_style="yellow"
        )
        self.console.print(banner)

    def render_response(self, content: str):
        """渲染 Agent 回复（Markdown + 语法高亮）"""
        markdown = Markdown(content)
        self.console.print(markdown)

    def render_streaming(self, token_stream):
        """流式渲染：逐 token 输出"""
        from rich.live import Live
        from rich.text import Text

        collected = []
        with Live(refresh_per_second=10, auto_refresh=False) as live:
            for token in token_stream:
                collected.append(token)
                text = Text("".join(collected))
                live.update(text)
                live.refresh()
        return "".join(collected)

    def show_progress(self, description: str,
                      total: int = 100) -> Progress:
        """显示进度条（用于长时间操作）"""
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        progress.add_task(description, total=total)
        return progress

    def show_confirm(self, message: str,
                     default: bool = True) -> bool:
        """显示确认提示"""
        return Confirm.ask(message, default=default)

    def show_error(self, message: str):
        """显示错误信息"""
        self.console.print(f"[bold red]✖ 错误:[/] {message}")

    def show_warning(self, message: str):
        """显示警告信息"""
        self.console.print(f"[bold yellow]⚠ 警告:[/] {message}")

    def show_success(self, message: str):
        """显示成功信息"""
        self.console.print(f"[bold green]✓[/] {message}")

    def show_info(self, message: str):
        """显示普通信息"""
        self.console.print(f"[blue]ℹ[/] {message}")

    def show_goodbye(self):
        """显示退出提示"""
        self.console.print("\n[dim]会话已结束，再见！👋[/]")
```

#### 渲染效果示例

```
✓ 文件已保存到 /tmp/report.md
ℹ 当前共处理 3 个文件
⚠ 磁盘使用率已达 85%

┌─────────── 搜索结果 ───────────┐
│ 文件名          │ 大小 │ 类型   │
├─────────────────┼──────┼────────┤
│ report_2026.md  │ 2MB  │ markdown│
│ data.json       │ 500KB│ json    │
│ script.py       │ 12KB │ python  │
└─────────────────┴──────┴────────┘
```

---

## 5. 依赖关系与架构总览

### 组件依赖

```
CLI (main.py)
  └── ConversationAgent (Thin Presenter) ← 薄展示层
        ├── PipBus ──────→ Layer 2: Intent Recognition    ← 意图理解委托
        │                └─→ Layer 2: Dialogue Manager     ← 上下文管理委托
        │                └─→ Layer 3: Orchestrator         ← 执行委托
        │                └─→ Layer 1: ToolRegistry         ← 工具列表查询
        └── Renderer                                      ← 终端 UI 渲染

MCP Server (mcp_server/)
  ├── Tools:     从 Layer 1 ToolRegistry 注册（8 个工具）
  ├── Resources: pulsar:// 协议资源（配置、技能、会话、系统、日志）
  ├── Prompts:   可复用提示词模板（code_review, system_prompt 等）
  └── System:    ping + capabilities 端点
```

### 架构变更摘要（对比旧版）

| 旧版（Fat Client） | 新版（Thin Presenter） | 变更说明 |
|-------------------|----------------------|---------|
| `ConversationAgent` 直接调用 `LLM Gateway` | 通过 `PipBus` 委托 Layer 2 | 移除 LLM 依赖 |
| `ContentGenerator` 调用 `llm_gateway.chat(messages=[...])` |（与旧版 `generate()` API 对齐）| LLM Gateway 统一使用 `chat(messages=[...])` 接口 |
| `_generate_action_plan()` 内部调用 LLM | → Layer 2 Intent Recognition | 移至下层 |
| `_execute_action_plan()` 直接调用 PIPBus | → Layer 3 Orchestrator | 移至下层 |
| `_generate_response()` 再次调用 LLM | → Layer 3 返回 summary | 执行层直接产出回复 |
| `self.history` 自行管理上下文窗口 | → Layer 2 Dialogue Manager | 上下文管理下沉 |
| `MCP Server` 仅支持 tools/list + tools/call | + resources/list/read + prompts/list/get + system/capabilities | MCP 协议完整实现 |
| Schema 使用 snake_case | 外部 `inputSchema` 使用 camelCase | MCP 外部规范对齐 |

### 数据流

```
用户输入
  │
  ▼
Layer 5 ConversationAgent (Thin Presenter)
  ├── 检查斜杠命令 → 本地处理
  ├── 委托 Layer 2 Intent (PIP)
  │     └── 返回 {intent, confidence, action_plan}
  ├── 委托 Layer 3 Execute (PIP)
  │     └── 返回 {results, summary}
  ├── 委托 Renderer 渲染
  └── 更新展示上下文副本
```

- `ConversationAgent` 依赖 `PipBus` 与 Layer 2/3/1 通信，以及本层的 `Renderer`。
- `CLI main` 依赖 `ConversationAgent` 和 `MCP Server`。
- `MCP Server` 依赖 Layer 1 `ToolRegistry` 获取工具定义，独立运行。
- `Renderer` 是无状态工具类，可被任何模块使用。
