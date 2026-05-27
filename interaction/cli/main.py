import click
from interaction.cli.commands.publish import publish_group
from interaction.cli.commands.draft import draft_group
from interaction.cli.commands.stats import stats_group
from interaction.cli.commands.config import config_group
from interaction.cli.commands.system import system_group
from interaction.cli.formats import console


@click.group()
@click.option("--config", default="config.yaml", help="配置文件路径")
@click.option("--verbose", is_flag=True, help="详细输出")
@click.option("--output-format", default="rich", type=click.Choice(["rich", "plain", "json"]), help="输出格式")
@click.pass_context
def cli(ctx, config, verbose, output_format):
    """Pulsar · 脉冲星 — 通用自媒体运营智能体"""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["output_format"] = output_format


@cli.command()
def run():
    """启动 Pulsar Daemon"""
    from runtime.main import run as runtime_run
    runtime_run()


cli.add_command(publish_group)
cli.add_command(draft_group)
cli.add_command(stats_group)
cli.add_command(config_group)
cli.add_command(system_group)


def main():
    cli()


if __name__ == "__main__":
    main()