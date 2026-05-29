"""草稿管理 CLI 命令"""

import asyncio

import click

from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_table,
    print_key_value,
    print_divider,
)


@click.group(name="draft", help="管理草稿箱")
def draft_group() -> None:
    """草稿管理命令组"""
    pass


@draft_group.command(name="list", help="列出草稿列表")
@click.option("--platform", "-p", default="wechat", help="平台名称")
@click.option("--offset", "-o", default=0, type=int, help="偏移量")
@click.option("--count", "-c", default=20, type=int, help="返回数量")
@click.pass_context
def draft_list(
    ctx: click.Context,
    platform: str,
    offset: int,
    count: int,
) -> None:
    """列出草稿列表"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                f"adapter.{platform}",
                f"{platform}_draft_list",
                {"offset": offset, "count": count},
            )
        )

        items = result.get("items", [])
        total_count = result.get("total_count", 0)

        if not items:
            print_info("暂无草稿")
            return

        print_table(
            title=f"草稿列表 (共 {total_count} 篇)",
            columns=["MediaID", "标题", "状态", "创建时间"],
            rows=[
                [
                    item.get("media_id", "")[:12] + "...",
                    item.get("title", "")[:20],
                    item.get("status", ""),
                    item.get("create_time", ""),
                ]
                for item in items
            ],
        )

    except Exception as e:
        print_error(f"获取草稿列表失败: {e}")


@draft_group.command(name="get", help="查看草稿详情")
@click.argument("media_id", required=True)
@click.option("--platform", "-p", default="wechat", help="平台名称")
@click.pass_context
def draft_get(ctx: click.Context, media_id: str, platform: str) -> None:
    """查看草稿详情"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                f"adapter.{platform}",
                f"{platform}_draft_get",
                {"media_id": media_id},
            )
        )

        article = result.get("article", {})
        print_key_value([
            ("MediaID", media_id),
            ("标题", article.get("title", "N/A")),
            ("作者", article.get("author", "N/A")),
            ("摘要", article.get("digest", "N/A")),
            ("状态", article.get("status", "N/A")),
            ("创建时间", article.get("create_time", "N/A")),
        ])

    except Exception as e:
        print_error(f"获取草稿详情失败: {e}")


@draft_group.command(name="delete", help="删除草稿")
@click.argument("media_id", required=True)
@click.option("--platform", "-p", default="wechat", help="平台名称")
@click.pass_context
def draft_delete(ctx: click.Context, media_id: str, platform: str) -> None:
    """删除草稿"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                f"adapter.{platform}",
                f"{platform}_draft_delete",
                {"media_id": media_id},
            )
        )

        if result.get("errcode", -1) == 0:
            print_success(f"草稿 {media_id} 已删除")
        else:
            print_error(f"删除失败: {result.get('errmsg', '未知错误')}")

    except Exception as e:
        print_error(f"删除草稿失败: {e}")


@draft_group.command(name="update", help="更新草稿")
@click.argument("media_id", required=True)
@click.option("--title", "-t", help="文章标题")
@click.option("--content", "-c", type=click.Path(exists=True), help="文章内容文件路径")
@click.option("--platform", "-p", default="wechat", help="平台名称")
@click.pass_context
def draft_update(
    ctx: click.Context,
    media_id: str,
    title: str | None,
    content: str | None,
    platform: str,
) -> None:
    """更新草稿"""
    runtime = ctx.obj.get("runtime")

    update_args: dict = {"media_id": media_id}
    if title:
        update_args["title"] = title
    if content:
        from pathlib import Path
        content_path = Path(content)
        if not content_path.exists():
            print_error(f"内容文件不存在: {content}")
            return
        update_args["content"] = content_path.read_text(encoding="utf-8")

    try:
        result = asyncio.run(
            runtime.call_tool(
                f"adapter.{platform}",
                f"{platform}_draft_update",
                update_args,
            )
        )

        if result.get("errcode", -1) == 0:
            print_success(f"草稿 {media_id} 已更新")
        else:
            print_error(f"更新失败: {result.get('errmsg', '未知错误')}")

    except Exception as e:
        print_error(f"更新草稿失败: {e}")