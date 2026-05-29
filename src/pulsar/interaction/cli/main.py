"""Pulsar CLI entry point - click-based command line interface."""

import click
import asyncio
import sys


async def run_repl():
    """异步 REPL 主循环"""
    from pulsar.runtime.pip_bus import PIPBus
    
    click.echo("")
    click.echo("╭────────────────────────────────────────────╮")
    click.echo("│  ⚡ Pulsar · 脉冲星                          │")
    click.echo("│  通用自媒体运营智能体 / 输入 /help 查看命令  │")
    click.echo("│  Ctrl+C 退出 / 支持自然语言对话               │")
    click.echo("╰────────────────────────────────────────────╯")
    click.echo("")
    
    bus = PIPBus()
    
    while True:
        try:
            # Use prompt_toolkit for rich input
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import FileHistory
            try:
                session = PromptSession(
                    history=FileHistory(".pulsar_history"),
                )
                user_input = await session.prompt_async("> [Pulsar] ")
            except ImportError:
                # Fallback to simple input if prompt_toolkit unavailable
                user_input = input("> ")
            
            if not user_input:
                continue
            
            # Handle / commands
            if user_input.startswith("/"):
                cmd = user_input[1:].strip().lower()
                
                if cmd == "exit" or cmd == "quit":
                    click.echo("再见！")
                    break
                elif cmd == "help":
                    click.echo("\n可用命令：")
                    click.echo("  /help     显示帮助")
                    click.echo("  /exit     退出")
                    click.echo("  /clear    清屏")
                    click.echo("  /stats    查看数据")
                    click.echo("  /version  显示版本")
                    click.echo("")
                elif cmd == "clear":
                    click.echo("\033[2J\033[H", nl=False)
                elif cmd == "version":
                    click.echo("Pulsar v0.1.0")
                else:
                    click.echo(f"未知命令: /{cmd}，输入 /help 查看可用命令")
                continue
            
            # Echo back for now - full intent understanding comes in Sprint 2
            click.echo(f"\n📝 收到: {user_input}")
            click.echo("🤖 对话引擎开发中... 暂回显你的输入\n")
            
        except (KeyboardInterrupt, EOFError):
            click.echo("\n再见！")
            break


@click.group()
@click.version_option(version="0.1.0", prog_name="Pulsar")
def cli():
    """Pulsar · 脉冲星 — 通用自媒体运营智能体"""
    pass


@cli.command()
def repl():
    """启动对话模式（REPL）"""
    asyncio.run(run_repl())


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
def daemon(config):
    """启动后台 Daemon"""
    from pulsar.runtime.main import PulsarRuntime
    
    async def start():
        runtime = PulsarRuntime(config_path=config)
        await runtime.start()
    
    click.echo(f"启动 Pulsar Daemon, 配置文件: {config}")
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        click.echo("\nDaemon 已停止")


@cli.command()
@click.option("--once", "-o", help="一次性对话指令")
def chat(once):
    """一次性对话模式"""
    if once:
        click.echo(f"执行: {once}")
        click.echo("🤖 对话引擎开发中...")
    else:
        asyncio.run(run_repl())


if __name__ == "__main__":
    cli()
