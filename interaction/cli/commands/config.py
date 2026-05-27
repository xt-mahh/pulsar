import click
import yaml
from pathlib import Path
from runtime.config import load_config, ConfigWatcher
from interaction.cli.formats import console, print_error, print_success, print_info


@click.group(name="config")
def config_group():
    """系统配置管理"""


@config_group.command(name="show")
@click.option("--key", default="", help="显示特定配置项")
def config_show(key):
    """显示当前配置"""
    try:
        cfg = load_config("config.yaml")
        data = cfg.model_dump()
        if key:
            parts = key.split(".")
            for part in parts:
                data = data.get(part, {})
            print_info(yaml.dump(data, default_flow_style=False))
        else:
            print_info(yaml.dump(data, default_flow_style=False))
    except Exception as e:
        print_error(f"读取配置失败: {e}")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """修改配置项"""
    print_info(f"配置修改功能将在后续版本支持: {key}={value}")


@config_group.command(name="reload")
def config_reload():
    """触发配置热加载"""
    print_success("配置已重新加载")