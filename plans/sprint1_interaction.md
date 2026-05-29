# Pulsar Phase 1 Sprint 1 — interaction/ 模块详细计划

> 本文档描述 `interaction/` 模块的设计方案，包含 CLI 命令行工具和对外 MCP Server。
> interaction 是系统的门面，所有外界对系统的接触都通过这一层。

---

## 一、模块定位

**职责**：提供用户与系统的交互接口，Phase 1 实现 CLI 和 MCP Server 两种接入方式。

**Phase 1 范围**：
- CLI 命令行工具（5 个命令组：publish/draft/stats/config/system）
- 对外 MCP Server（8+ 工具暴露）
- 输出格式化（rich 库彩色输出）

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `interaction/__init__.py` | P0 | 无 |
| 2 | `interaction/cli/__init__.py` | P0 | 无 |
| 3 | `interaction/cli/main.py` | P0 | commands/* |
| 4 | `interaction/cli/formats.py` | P0 | rich |
| 5 | `interaction/cli/commands/publish.py` | P0 | execution |
| 6 | `interaction/cli/commands/draft.py` | P0 | execution |
| 7 | `interaction/cli/commands/stats.py` | P0 | execution |
| 8 | `interaction/cli/commands/config.py` | P0 | runtime/config |
| 9 | `interaction/cli/commands/system.py` | P0 | runtime |
| 10 | `interaction/mcp_server/__init__.py` | P0 | 无 |
| 11 | `interaction/mcp_server/tools.py` | P0 | shared |
| 12 | `interaction/mcp_server/server.py` | P0 | tools, execution |

---

## 三、`interaction/cli/main.py` 设计方案

### 3.1 职责

CLI 入口，定义 `pulsar` 主命令组和 `run` 子命令。

### 3.2 核心实现

```python
import click
from rich.console import Console

console = Console()

@click.group()
@click.version_option(version="0.1.0", prog_name="Pulsar")
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
@click.pass_context
def cli(ctx: click.Context, config: str):
    """Pulsar · 脉冲星 — 通用自媒体运营智能体"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config

@cli.command()
@click.option("--daemon", "-d", is_flag=True, help="以守护进程模式运行")
@click.pass_context
def run(ctx, daemon):
    """启动 Pulsar Daemon"""
    from runtime.main import PulsarRuntime
    runtime = PulsarRuntime(ctx.obj["config_path"])
    
    if daemon:
        # 后台运行
        import asyncio
        asyncio.run(runtime.run_forever())
    else:
        # 前台运行
        import asyncio
        try:
            asyncio.run(runtime.run_forever())
        except KeyboardInterrupt:
            console.print("\n[yellow]收到中断信号，正在关闭...[/yellow]")
            asyncio.run(runtime.shutdown())
            console.print("[green]Pulsar 已停止[/green]")

# 注册子命令组
from .commands.publish import publish
from .commands.draft import draft
from .commands.stats import stats
from .commands.config import config
from .commands.system import system

cli.add_command(publish)
cli.add_command(draft)
cli.add_command(stats)
cli.add_command(config)
cli.add_command(system)
```

---

## 四、命令组设计

### 4.1 `publish.py` — 发布命令

```python
@click.group(name="publish", help="发布内容到平台")
def publish():
    pass

@publish.command(name="wechat")
@click.option("--title", "-t", required=True, help="文章标题")
@click.option("--content", "-c", required=True, help="文章内容（文件路径或直接文本）")
@click.option("--cover", help="封面图路径")
@click.option("--author", default="Pulsar", help="作者名")
@click.option("--schedule", help="定时发布时间（如 17:30）")
@click.option("--no-publish", is_flag=True, help="仅创建草稿，不发布")
@click.pass_context
def wechat_publish(ctx, title, content, cover, author, schedule, no_publish):
    """发布内容到微信公众号"""
    # 1. 读取内容
    if os.path.isfile(content):
        with open(content, "r", encoding="utf-8") as f:
            content_text = f.read()
    else:
        content_text = content
    
    # 2. 获取微信 Adapter
    from execution.adapters.wechat.adapter import WeChatAdapter
    adapter = WeChatAdapter(ctx.obj["wechat_config"])
    
    # 3. 上传封面
    thumb_media_id = ""
    if cover:
        result = asyncio.run(adapter.handle_tool_call("wechat_media_upload", {
            "file_path": cover, "type": "thumb"
        }))
        thumb_media_id = result.get("media_id", "")
    
    # 4. 创建草稿
    draft_result = asyncio.run(adapter.handle_tool_call("wechat_draft_add", {
        "title": title, "content": content_text, "author": author,
        "thumb_media_id": thumb_media_id,
    }))
    
    console.print(f"[green]✓ 草稿创建成功[/green]")
    console.print(f"  MediaID: {draft_result['media_id']}")
    
    # 5. 发布
    if not no_publish:
        if schedule:
            # 定时发布
            publish_result = asyncio.run(adapter.handle_tool_call("wechat_publish_schedule", {
                "media_id": draft_result["media_id"],
                "publish_time": schedule,
            }))
        else:
            publish_result = asyncio.run(adapter.handle_tool_call("wechat_publish_submit", {
                "media_id": draft_result["media_id"],
            }))
        
        console.print(f"[green]✓ 发布任务已提交[/green]")
        console.print(f"  PublishID: {publish_result['publish_id']}")
```

### 4.2 `draft.py` — 草稿管理命令

```python
@click.group(name="draft", help="管理草稿箱")
def draft():
    pass

@draft.command(name="list")
@click.argument("platform", default="wechat")
@click.option("--offset", default=0, help="偏移量")
@click.option("--count", default=20, help="数量")
@click.pass_context
def draft_list(ctx, platform, offset, count):
    """列出草稿"""
    adapter = _get_adapter(ctx, platform)
    result = asyncio.run(adapter.handle_tool_call(f"{platform}_draft_list", {
        "offset": offset, "count": count,
    }))
    _display_drafts(result)

@draft.command(name="delete")
@click.argument("media_id")
@click.argument("platform", default="wechat")
@click.pass_context
def draft_delete(ctx, media_id, platform):
    """删除草稿"""
    adapter = _get_adapter(ctx, platform)
    result = asyncio.run(adapter.handle_tool_call(f"{platform}_draft_delete", {
        "media_id": media_id,
    }))
    console.print(f"[green]✓ 草稿已删除[/green]")
```

### 4.3 `stats.py` — 数据查询命令

```python
@click.group(name="stats", help="查看运营数据")
def stats():
    pass

@stats.command(name="wechat")
@click.option("--period", default="today", help="时间范围: today/yesterday/7d/30d")
@click.pass_context
def wechat_stats(ctx, period):
    """查看微信运营数据"""
    dates = _parse_period(period)
    adapter = _get_adapter(ctx, "wechat")
    
    # 用户数据
    user_stats = asyncio.run(adapter.handle_tool_call("wechat_stats_user_summary", {
        "begin_date": dates[0], "end_date": dates[1],
    }))
    
    # 文章数据
    article_stats = asyncio.run(adapter.handle_tool_call("wechat_stats_article_summary", {
        "begin_date": dates[0], "end_date": dates[1],
    }))
    
    _display_stats(user_stats, article_stats)
```

### 4.4 `config.py` — 配置管理命令

```python
@click.group(name="config", help="系统配置管理")
def config():
    pass

@config.command(name="get")
@click.argument("key", required=False)
@click.pass_context
def config_get(ctx, key):
    """查看配置"""
    config = load_config(ctx.obj["config_path"])
    if key:
        # 支持点号分隔的路径，如 gateway.default_provider
        value = _get_nested(config, key)
        console.print(f"{key}: {value}")
    else:
        console.print(config)

@config.command(name="reload")
@click.pass_context
def config_reload(ctx):
    """热加载配置"""
    # 向 Runtime 发送 SIGHUP 信号
    console.print("[green]✓ 配置已重新加载[/green]")
```

### 4.5 `system.py` — 系统管理命令

```python
@click.group(name="system", help="系统管理")
def system():
    pass

@system.command(name="status")
@click.pass_context
def system_status(ctx):
    """查看系统运行状态"""
    # 显示所有 Agent 状态
    console.print("[bold]Pulsar 系统状态[/bold]")
    console.print("  Runtime: [green]Running[/green]")
    console.print("  Agents:")
    console.print("    - gateway.llm: [green]Healthy[/green]")
    console.print("    - adapter.wechat: [green]Healthy[/green]")
    console.print("    - scheduler: [green]Running[/green]")

@system.command(name="test-gateway")
@click.pass_context
def test_gateway(ctx):
    """测试 LLM Gateway"""
    from gateway.gateway import LLMGateway
    config = load_config(ctx.obj["config_path"])
    gateway = LLMGateway(config["gateway"])
    
    result = asyncio.run(gateway.chat([
        {"role": "user", "content": "回复'Pulsar 系统测试通过'"}
    ]))
    console.print(f"[green]✓ LLM 响应: {result['content']}[/green]")

@system.command(name="logs")
@click.option("--tail", default=50, help="显示最后 N 行")
@click.option("--follow", "-f", is_flag=True, help="持续跟踪")
@click.pass_context
def system_logs(ctx, tail, follow):
    """查看系统日志"""
    # 读取审计日志
    log_path = "data/logs/audit.log"
    if follow:
        # tail -f
        pass
    else:
        # 显示最后 N 行
        pass
```

---

## 五、`interaction/cli/formats.py` 设计方案

### 5.1 职责

提供统一的输出格式化功能，支持 rich 彩色输出、plain 文本、JSON 三种格式。

### 5.2 核心实现

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

def format_result(data: dict, fmt: str = "rich") -> str:
    """格式化结果输出"""
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    elif fmt == "plain":
        return _format_plain(data)
    else:
        return _format_rich(data)

def format_table(headers: list[str], rows: list[list], title: str = "") -> str:
    """格式化表格输出"""
    table = Table(title=title)
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    return table

def format_error(message: str) -> str:
    """格式化错误信息"""
    return f"[red]✗ 错误: {message}[/red]"

def _format_rich(data: dict, indent: int = 0) -> str:
    """递归格式化字典为 rich 输出"""
    lines = []
    for key, value in data.items():
        prefix = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}[bold]{key}:[/bold]")
            lines.append(_format_rich(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}[bold]{key}:[/bold]")
            for item in value:
                if isinstance(item, dict):
                    lines.append(_format_rich(item, indent + 1))
                else:
                    lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}[bold]{key}:[/bold] {value}")
    return "\n".join(lines)
```

---

## 六、`interaction/mcp_server/` 设计方案

### 6.1 `tools.py` — 对外工具定义

```python
from shared.models import ToolDefinition

# 对外暴露的 MCP 工具
EXTERNAL_TOOLS = [
    ToolDefinition(
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
            "required": ["platform", "title", "content"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="platform_draft_create",
        description="创建草稿",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["platform", "title", "content"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="platform_draft_list",
        description="获取草稿列表",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "offset": {"type": "integer", "default": 0},
                "count": {"type": "integer", "default": 20},
            },
            "required": ["platform"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="platform_stats",
        description="查询运营数据",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "begin_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["platform", "begin_date", "end_date"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="platform_upload_media",
        description="上传素材",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "file_path": {"type": "string"},
                "media_type": {"type": "string", "enum": ["image", "thumb", "voice", "video"]},
            },
            "required": ["platform", "file_path", "media_type"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="system_status",
        description="查询系统运行状态",
        input_schema={"type": "object", "properties": {}},
        agent="mcp_server",
    ),
    ToolDefinition(
        name="task_schedule",
        description="创建定时任务",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "schedule": {"type": "string", "description": "Cron 表达式"},
                "task_type": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": ["name", "schedule", "task_type"],
        },
        agent="mcp_server",
    ),
    ToolDefinition(
        name="task_list",
        description="查看任务列表",
        input_schema={"type": "object", "properties": {}},
        agent="mcp_server",
    ),
]
```

### 6.2 `server.py` — MCP Server 入口

```python
class PulsarMCPServer:
    """Pulsar 对外 MCP Server"""
    
    def __init__(self, config: dict):
        self._config = config
        self._transport = config.get("transport", "stdio")
        self._tools = {t.name: t for t in EXTERNAL_TOOLS}
        self._adapter_cache: dict[str, BasePlatformAdapter] = {}
    
    async def handle_request(self, request: dict) -> dict:
        """处理 MCP 请求"""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": [t.dict() for t in EXTERNAL_TOOLS],
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            
            if tool_name not in self._tools:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
                }
            
            try:
                result = await self._execute_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result,
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": str(e)},
                }
        elif method == "system/ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": "pong"}
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method '{method}' not supported"},
            }
    
    async def _execute_tool(self, name: str, args: dict) -> dict:
        """执行 MCP 工具调用"""
        if name == "system_status":
            return {"status": "running", "version": "0.1.0"}
        
        # 平台相关工具 → 路由到对应 Adapter
        platform = args.get("platform", "wechat")
        adapter = self._get_adapter(platform)
        
        # 映射外部工具名到内部工具名
        tool_map = {
            "platform_publish": f"{platform}_publish_submit",
            "platform_draft_create": f"{platform}_draft_add",
            "platform_draft_list": f"{platform}_draft_list",
            "platform_stats": f"{platform}_stats_article_summary",
            "platform_upload_media": f"{platform}_media_upload",
        }
        
        internal_name = tool_map.get(name)
        if internal_name:
            return await adapter.handle_tool_call(internal_name, args)
        
        raise ValueError(f"Unknown tool: {name}")
    
    def _get_adapter(self, platform: str) -> BasePlatformAdapter:
        """获取或缓存平台 Adapter"""
        if platform not in self._adapter_cache:
            if platform == "wechat":
                from execution.adapters.wechat.adapter import WeChatAdapter
                self._adapter_cache[platform] = WeChatAdapter(
                    self._config.get("adapters", {}).get("wechat", {})
                )
        return self._adapter_cache[platform]
    
    async def run_stdio(self):
        """通过 stdio 运行 MCP Server"""
        import sys
        async for line in sys.stdin:
            request = json.loads(line.strip())
            response = await self.handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
```

---

## 七、验收标准

- [ ] `pulsar --help` 显示所有命令组
- [ ] `pulsar run` 启动系统 daemon
- [ ] `pulsar publish wechat --title "test" --content "hello"` 完成发布全流程
- [ ] `pulsar draft list wechat` 显示草稿列表
- [ ] `pulsar stats wechat --period today` 显示运营数据
- [ ] `pulsar system status` 显示系统状态
- [ ] `pulsar system test-gateway` 返回 LLM 响应
- [ ] 外部 MCP 客户端可通过 stdio 调用 `platform_publish` 等工具
- [ ] 输出格式化支持 rich/plain/json 三种格式

---

## 八、注意事项

1. **异步 CLI**：click 本身不支持 async，需要在命令函数内部使用 `asyncio.run()` 执行异步操作
2. **错误处理**：所有 CLI 命令应捕获异常并显示友好的错误信息，而非 Python traceback
3. **MCP Server 传输**：Phase 1 仅实现 stdio 传输，HTTP 传输留到后续 Sprint
4. **Adapter 缓存**：MCP Server 应缓存 Adapter 实例，避免每次调用都重新初始化
5. **配置传递**：CLI 命令通过 click context 传递配置，避免全局变量
6. **输出格式**：默认使用 rich 格式，可通过 `--format json` 切换为 JSON 输出
