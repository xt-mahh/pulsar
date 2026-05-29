"""CLI 输出格式化工具 — 基于 rich 库的彩色格式化输出"""

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich import box

console = Console()


def print_success(message: str) -> None:
    """打印成功消息"""
    console.print(f"  [bold green]✓[/] {message}")


def print_error(message: str) -> None:
    """打印错误消息"""
    console.print(f"  [bold red]✗[/] {message}")


def print_warning(message: str) -> None:
    """打印警告消息"""
    console.print(f"  [bold yellow]⚠[/] {message}")


def print_info(message: str) -> None:
    """打印信息消息"""
    console.print(f"  [bold blue]ℹ[/] {message}")


def print_header(title: str) -> None:
    """打印标题"""
    console.print()
    console.print(Panel(title, border_style="bold blue"))
    console.print()


def print_json(data: dict[str, Any]) -> None:
    """打印格式化的 JSON"""
    import json
    text = json.dumps(data, indent=2, ensure_ascii=False)
    syntax = Syntax(text, "json", theme="monokai", line_numbers=False)
    console.print(syntax)


def print_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
) -> None:
    """打印表格

    Args:
        title: 表格标题
        columns: 列名列表
        rows: 数据行列表
    """
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
    )
    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*row)

    console.print(table)


def print_key_value(
    items: list[tuple[str, str]],
    title: str | None = None,
) -> None:
    """打印键值对列表

    Args:
        items: (key, value) 元组列表
        title: 可选标题
    """
    text = Text()
    if title:
        text.append(f"{title}\n", style="bold blue")
        text.append("\n")

    for key, value in items:
        text.append(f"  {key}: ", style="bold yellow")
        text.append(f"{value}\n", style="white")

    console.print(text)


def print_status(status: str, message: str) -> None:
    """打印状态消息

    Args:
        status: 状态标识 (success/error/warning/info)
        message: 消息内容
    """
    status_map = {
        "success": ("✓", "green"),
        "error": ("✗", "red"),
        "warning": ("⚠", "yellow"),
        "info": ("ℹ", "blue"),
    }
    symbol, color = status_map.get(status, ("?", "white"))
    console.print(f"  [bold {color}]{symbol}[/] {message}")


def print_divider() -> None:
    """打印分隔线"""
    console.print("  " + "─" * 60, style="dim")


def print_agent_status(
    agents: list[dict[str, Any]],
) -> None:
    """打印 Agent 状态列表

    Args:
        agents: Agent 状态字典列表，每项含 name, layer, status, uptime
    """
    table = Table(
        title="Agent 状态",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column("名称")
    table.add_column("层级")
    table.add_column("状态")
    table.add_column("运行时间")

    for agent in agents:
        status_style = {
            "running": "green",
            "stopped": "red",
            "starting": "yellow",
            "error": "red bold",
        }.get(agent.get("status", ""), "white")

        table.add_row(
            agent.get("name", ""),
            f"Layer {agent.get('layer', '?')}",
            f"[{status_style}]{agent.get('status', 'unknown')}[/]",
            agent.get("uptime", "-"),
        )

    console.print(table)