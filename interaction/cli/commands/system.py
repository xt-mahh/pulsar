"""系统管理 CLI 命令"""

import asyncio

import click

from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_warning,
    print_table,
    print_key_value,
    print_agent_status,
    print_divider,
)


@click.group(name="system", help="系统管理")
def system_group() -> None:
    """系统管理命令组"""
    pass


@system_group.command(name="status", help="查看系统运行状态")
@click.pass_context
def system_status(ctx: click.Context) -> None:
    """查看系统运行状态"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "system_status",
                {},
            )
        )

        # 系统概览
        system_info = result.get("system", {})
        print_key_value([
            ("系统名称", system_info.get("name", "Pulsar")),
            ("版本", system_info.get("version", "0.1.0")),
            ("运行时间", system_info.get("uptime", "N/A")),
            ("PID", str(system_info.get("pid", "N/A"))),
        ])
        print_divider()

        # Agent 状态
        agents = result.get("agents", [])
        if agents:
            print_agent_status(agents)
        else:
            print_warning("暂无 Agent 运行")

        print_divider()

        # 资源使用
        resources = result.get("resources", {})
        print_key_value([
            ("内存使用", resources.get("memory_mb", "N/A")),
            ("CPU 使用率", resources.get("cpu_percent", "N/A")),
            ("线程数", str(resources.get("threads", "N/A"))),
        ])

    except Exception as e:
        print_error(f"获取系统状态失败: {e}")


@system_group.command(name="logs", help="查看系统日志")
@click.option("--lines", "-n", default=50, type=int, help="显示行数")
@click.option("--level", "-l", default="", help="日志级别过滤 (INFO/WARNING/ERROR)")
@click.option("--follow", "-f", is_flag=True, help="持续跟踪日志输出")
@click.pass_context
def system_logs(
    ctx: click.Context,
    lines: int,
    level: str,
    follow: bool,
) -> None:
    """查看系统日志"""
    runtime = ctx.obj.get("runtime")

    params = {"lines": lines}
    if level:
        params["level"] = level.upper()
    if follow:
        params["follow"] = True

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "system_logs",
                params,
            )
        )

        entries = result.get("entries", [])
        if not entries:
            print_info("暂无日志记录")
            return

        for entry in entries:
            timestamp = entry.get("timestamp", "")
            level_str = entry.get("level", "INFO")
            message = entry.get("message", "")
            agent = entry.get("agent", "")

            # 根据级别着色
            level_style = {
                "INFO": "blue",
                "WARNING": "yellow",
                "ERROR": "red bold",
                "DEBUG": "dim",
            }.get(level_str, "white")

            print_info(f"[{timestamp}] [{level_str}] [{agent}] {message}")

    except Exception as e:
        print_error(f"获取日志失败: {e}")


@system_group.command(name="test-gateway", help="测试 LLM Gateway 连接")
@click.option("--provider", "-p", default="", help="指定测试的提供商（默认测试所有）")
@click.option("--prompt", "-m", default="Hello, please respond with 'OK' only.", help="测试提示词")
@click.pass_context
def test_gateway(
    ctx: click.Context,
    provider: str,
    prompt: str,
) -> None:
    """测试 LLM Gateway 连接"""
    runtime = ctx.obj.get("runtime")

    params = {"prompt": prompt}
    if provider:
        params["provider"] = provider

    try:
        result = asyncio.run(
            runtime.call_tool(
                "gateway",
                "test_connection",
                params,
            )
        )

        results = result.get("results", [result])
        for r in results:
            provider_name = r.get("provider", "unknown")
            status = r.get("status", "error")
            latency = r.get("latency_ms", 0)
            response = r.get("response", "")

            if status == "success":
                print_success(f"{provider_name}: {latency}ms")
                print_info(f"  响应: {response[:100]}")
            else:
                error_msg = r.get("error", "连接失败")
                print_error(f"{provider_name}: {error_msg}")

    except Exception as e:
        print_error(f"测试 Gateway 失败: {e}")


@system_group.command(name="restart", help="重启系统")
@click.option("--force", "-f", is_flag=True, help="强制重启（不等待任务完成）")
@click.pass_context
def system_restart(ctx: click.Context, force: bool) -> None:
    """重启系统"""
    runtime = ctx.obj.get("runtime")

    if not force:
        click.confirm("确定要重启系统吗？正在进行的任务可能会中断", abort=True)

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "system_restart",
                {"force": force},
            )
        )

        if result.get("success"):
            print_success("系统正在重启...")
        else:
            print_error(f"重启失败: {result.get('error', '未知错误')}")

    except Exception as e:
        print_error(f"重启系统失败: {e}")


@system_group.command(name="shutdown", help="关闭系统")
@click.option("--force", "-f", is_flag=True, help="强制关闭（不等待任务完成）")
@click.pass_context
def system_shutdown(ctx: click.Context, force: bool) -> None:
    """关闭系统"""
    runtime = ctx.obj.get("runtime")

    if not force:
        click.confirm("确定要关闭系统吗？正在进行的任务可能会中断", abort=True)

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "system_shutdown",
                {"force": force},
            )
        )

        if result.get("success"):
            print_success("系统正在关闭...")
        else:
            print_error(f"关闭失败: {result.get('error', '未知错误')}")

    except Exception as e:
        print_error(f"关闭系统失败: {e}")