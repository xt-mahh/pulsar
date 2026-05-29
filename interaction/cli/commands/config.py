"""配置管理 CLI 命令"""

import asyncio

import click

from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_json,
    print_divider,
)


@click.group(name="config", help="系统配置管理")
def config_group() -> None:
    """配置管理命令组"""
    pass


@config_group.command(name="show", help="查看当前配置")
@click.option("--section", "-s", default="", help="配置段名称（如 runtime, gateway, adapters.wechat）")
@click.pass_context
def config_show(ctx: click.Context, section: str) -> None:
    """查看当前配置"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "config_get",
                {"section": section} if section else {},
            )
        )

        print_json(result)

    except Exception as e:
        print_error(f"获取配置失败: {e}")


@config_group.command(name="set", help="设置配置项")
@click.argument("key", required=True)
@click.argument("value", required=True)
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """设置配置项（格式: section.key value）"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "config_set",
                {"key": key, "value": value},
            )
        )

        if result.get("success"):
            print_success(f"配置 {key} 已更新为 {value}")
        else:
            print_error(f"更新失败: {result.get('error', '未知错误')}")

    except Exception as e:
        print_error(f"设置配置失败: {e}")


@config_group.command(name="reload", help="热加载配置")
@click.pass_context
def config_reload(ctx: click.Context) -> None:
    """热加载配置文件"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "config_reload",
                {},
            )
        )

        if result.get("success"):
            print_success("配置已热加载")
            changed = result.get("changed_keys", [])
            if changed:
                print_info(f"变更的配置项: {', '.join(changed)}")
        else:
            print_error(f"热加载失败: {result.get('error', '未知错误')}")

    except Exception as e:
        print_error(f"热加载配置失败: {e}")


@config_group.command(name="validate", help="验证配置文件")
@click.option("--path", "-p", default="config.yaml", help="配置文件路径")
@click.pass_context
def config_validate(ctx: click.Context, path: str) -> None:
    """验证配置文件格式"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "system",
                "config_validate",
                {"path": path},
            )
        )

        if result.get("valid"):
            print_success("配置文件验证通过")
        else:
            print_error(f"配置文件验证失败: {result.get('errors', '未知错误')}")

    except Exception as e:
        print_error(f"验证配置失败: {e}")