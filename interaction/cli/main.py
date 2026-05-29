"""Pulsar CLI 主入口"""

import asyncio
import sys
from pathlib import Path

import click

from interaction.cli.commands.publish import publish_group
from interaction.cli.commands.draft import draft_group
from interaction.cli.commands.stats import stats_group
from interaction.cli.commands.config import config_group
from interaction.cli.commands.system import system_group
from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_header,
)


class PulsarCLIContext:
    """CLI 上下文，持有 Runtime 引用"""

    def __init__(self) -> None:
        self.runtime = None
        self.config_path: str = "config.yaml"

    async def initialize(self) -> bool:
        """初始化 CLI 上下文（连接 Runtime）"""
        try:
            from runtime.main import PulsarRuntime

            self.runtime = PulsarRuntime(config_path=self.config_path)
            await self.runtime.start()
            return True
        except Exception as e:
            print_error(f"初始化 Runtime 失败: {e}")
            return False

    async def shutdown(self) -> None:
        """关闭 Runtime"""
        if self.runtime:
            await self.runtime.shutdown()


@click.group(
    name="pulsar",
    help="Pulsar · 脉冲星 — 通用自媒体运营智能体",
    invoke_without_command=True,
)
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
@click.version_option(version="0.1.0", prog_name="pulsar")
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """Pulsar CLI 主入口"""
    ctx.ensure_object(dict)

    # 存储配置路径
    ctx.obj["config_path"] = config

    # 如果没有子命令，显示帮助
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="run", help="启动 Pulsar Daemon")
@click.option("--daemon", "-d", is_flag=True, help="以守护进程模式运行")
@click.pass_context
def run_daemon(ctx: click.Context, daemon: bool) -> None:
    """启动 Pulsar 系统守护进程"""
    config_path = ctx.obj.get("config_path", "config.yaml")

    print_header("Pulsar · 脉冲星")
    print_info(f"配置文件: {config_path}")
    print_info("正在启动系统...")

    try:
        from runtime.main import PulsarRuntime

        async def _run() -> None:
            runtime = PulsarRuntime(config_path=config_path)
            await runtime.start()
            print_success("Pulsar 系统已启动")
            # 保持运行
            await runtime.run_forever()

        asyncio.run(_run())

    except KeyboardInterrupt:
        print_info("收到关闭信号，正在优雅关闭...")
    except Exception as e:
        print_error(f"启动失败: {e}")
        sys.exit(1)


# 注册命令组
cli.add_command(publish_group)
cli.add_command(draft_group)
cli.add_command(stats_group)
cli.add_command(config_group)
cli.add_command(system_group)


def main() -> None:
    """CLI 入口函数"""
    cli()


if __name__ == "__main__":
    main()