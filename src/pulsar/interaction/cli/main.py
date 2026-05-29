"""Pulsar CLI entry point - click-based command line interface."""

import click

@click.group()
@click.version_option(version="0.1.0", prog_name="Pulsar")
def cli():
    """Pulsar · 脉冲星 — 通用自媒体运营智能体"""
    pass

@cli.command()
def repl():
    """启动对话模式（REPL）"""
    click.echo("⚡ Pulsar · 脉冲星")
    click.echo("对话模式启动中...")
    click.echo("输入 /help 查看命令，Ctrl+C 退出")

@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
def daemon(config):
    """启动后台 Daemon"""
    click.echo(f"启动 Pulsar Daemon, 配置文件: {config}")

if __name__ == "__main__":
    cli()
