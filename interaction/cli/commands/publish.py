"""发布相关 CLI 命令"""

import asyncio
from pathlib import Path

import click

from interaction.cli.formats import (
    print_success,
    print_error,
    print_info,
    print_key_value,
    print_divider,
)


@click.group(name="publish", help="发布内容到平台")
def publish_group() -> None:
    """发布内容命令组"""
    pass


@publish_group.command(name="wechat", help="发布内容到微信公众号")
@click.option("--title", "-t", required=True, help="文章标题（最多 32 字）")
@click.option("--content", "-c", required=True, type=click.Path(exists=True), help="文章内容文件路径（HTML/Markdown）")
@click.option("--cover", "-cv", type=click.Path(exists=True), help="封面图路径")
@click.option("--author", "-a", default="Pulsar", help="作者名（最多 16 字）")
@click.option("--digest", "-d", default="", help="摘要（最多 128 字）")
@click.option("--schedule", "-s", default="", help="定时发布时间，格式 HH:MM")
@click.option("--no-publish", is_flag=True, help="仅创建草稿，不发布")
@click.option("--open-comment", is_flag=True, default=True, help="开启评论")
@click.pass_context
def publish_wechat(
    ctx: click.Context,
    title: str,
    content: str,
    cover: str | None,
    author: str,
    digest: str,
    schedule: str,
    no_publish: bool,
    open_comment: bool,
) -> None:
    """发布内容到微信公众号"""
    runtime = ctx.obj.get("runtime")

    # 读取内容文件
    content_path = Path(content)
    if not content_path.exists():
        print_error(f"内容文件不存在: {content}")
        return

    try:
        content_text = content_path.read_text(encoding="utf-8")
    except Exception as e:
        print_error(f"读取内容文件失败: {e}")
        return

    print_info(f"正在发布到微信公众号...")
    print_info(f"标题: {title}")
    print_info(f"作者: {author}")
    if digest:
        print_info(f"摘要: {digest}")
    if schedule:
        print_info(f"定时发布: {schedule}")
    print_divider()

    # 构建发布参数
    publish_args = {
        "title": title,
        "content": content_text,
        "author": author,
        "digest": digest,
        "need_open_comment": open_comment,
        "need_publish": not no_publish,
    }

    if cover:
        publish_args["thumb_media_id"] = cover
    if schedule:
        publish_args["schedule_time"] = schedule

    try:
        # 通过 Runtime 调用微信 Adapter
        result = asyncio.run(
            runtime.call_tool("adapter.wechat", "publish_article", publish_args)
        )

        if result.get("draft"):
            draft = result["draft"]
            print_success("草稿创建成功")
            print_key_value([
                ("MediaID", draft.get("media_id", "N/A")),
            ])

        if result.get("publish"):
            pub = result["publish"]
            print_success("发布任务已提交")
            print_key_value([
                ("PublishID", pub.get("publish_id", "N/A")),
            ])
            print_info("预计 2-5 分钟后完成发布")

        print_divider()

    except Exception as e:
        print_error(f"发布失败: {e}")


@publish_group.command(name="status", help="查看发布状态")
@click.argument("publish_id", required=True)
@click.pass_context
def publish_status(ctx: click.Context, publish_id: str) -> None:
    """查看发布任务状态"""
    runtime = ctx.obj.get("runtime")

    try:
        result = asyncio.run(
            runtime.call_tool(
                "adapter.wechat",
                "wechat_publish_get",
                {"publish_id": publish_id},
            )
        )

        status_map = {
            0: "成功",
            1: "被拒绝",
            2: "发送中",
            3: "审核中",
        }
        status_code = result.get("publish_status", -1)
        status_text = status_map.get(status_code, f"未知 ({status_code})")

        print_key_value([
            ("PublishID", publish_id),
            ("状态", status_text),
            ("文章ID", result.get("article_id", "N/A")),
            ("失败原因", result.get("fail_reason", "N/A")),
        ])

    except Exception as e:
        print_error(f"查询发布状态失败: {e}")