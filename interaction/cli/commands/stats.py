"""数据查询 CLI 命令"""

import asyncio

import click

from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_table,
    print_key_value,
    print_header,
    print_divider,
)


@click.group(name="stats", help="查看运营数据")
def stats_group() -> None:
    """数据查询命令组"""
    pass


@stats_group.command(name="wechat", help="查看微信公众号运营数据")
@click.option("--period", "-p", default="today", help="统计周期: today|yesterday|week|month|custom")
@click.option("--start", "-s", default="", help="开始日期 (custom 时必填，格式 YYYY-MM-DD)")
@click.option("--end", "-e", default="", help="结束日期 (custom 时必填，格式 YYYY-MM-DD)")
@click.pass_context
def stats_wechat(
    ctx: click.Context,
    period: str,
    start: str,
    end: str,
) -> None:
    """查看微信公众号运营数据"""
    runtime = ctx.obj.get("runtime")

    params = {"period": period}
    if period == "custom":
        if not start or not end:
            print_error("自定义周期需要提供 --start 和 --end 参数")
            return
        params["start"] = start
        params["end"] = end

    try:
        result = asyncio.run(
            runtime.call_tool(
                "adapter.wechat",
                "wechat_stats",
                params,
            )
        )

        # 用户概况
        overview = result.get("overview", {})
        print_header("📊 微信运营数据")
        print_key_value([
            ("新增关注", f"+{overview.get('new_user', 0)}"),
            ("取关", f"-{overview.get('unsubscribe', 0)}"),
            ("净增", f"+{overview.get('net_new', 0)}"),
            ("总用户", str(overview.get('total_user', 0))),
        ])
        print_divider()

        # 文章阅读排行
        articles = result.get("articles", [])
        if articles:
            print_info("文章阅读 TOP3:")
            for i, article in enumerate(articles[:3], 1):
                print_info(
                    f"  {i}. \"{article.get('title', '')}\" — "
                    f"{article.get('read_count', 0)} 阅读 / "
                    f"{article.get('share_count', 0)} 分享"
                )
        else:
            print_info("暂无文章数据")

    except Exception as e:
        print_error(f"获取运营数据失败: {e}")


@stats_group.command(name="overview", help="查看多平台概览")
@click.pass_context
def stats_overview(ctx: click.Context) -> None:
    """查看多平台运营概览"""
    runtime = ctx.obj.get("runtime")

    try:
        # 目前仅支持微信
        result = asyncio.run(
            runtime.call_tool(
                "adapter.wechat",
                "wechat_stats",
                {"period": "today"},
            )
        )

        overview = result.get("overview", {})
        print_table(
            title="多平台运营概览",
            columns=["平台", "新增", "取关", "净增", "总用户"],
            rows=[[
                "微信公众号",
                str(overview.get("new_user", 0)),
                str(overview.get("unsubscribe", 0)),
                str(overview.get("net_new", 0)),
                str(overview.get("total_user", 0)),
            ]],
        )

    except Exception as e:
        print_error(f"获取运营概览失败: {e}")