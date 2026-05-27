import click
import asyncio
from datetime import datetime, timedelta
from interaction.cli.formats import console, print_error, print_success, print_info
from execution.adapters.wechat.adapter import WeChatAdapter
from execution.adapters.wechat.tools import publish_article


@click.group(name="publish")
def publish_group():
    """发布内容到平台"""


@publish_group.command(name="wechat")
@click.option("--title", required=True, help="文章标题（≤32字）")
@click.option("--content", required=True, help="文章内容（HTML或Markdown文件路径）")
@click.option("--author", default="Pulsar", help="作者名（≤16字）")
@click.option("--digest", default="", help="摘要（≤128字）")
@click.option("--cover", default="", help="封面图路径")
@click.option("--schedule", default="", help="定时发布（可选），格式 HH:MM")
@click.option("--no-publish", is_flag=True, help="仅创建草稿，不发布")
def publish_wechat(title, content, author, digest, cover, schedule, no_publish):
    """发布文章到微信公众号"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        import os
        if os.path.isfile(content):
            with open(content, "r", encoding="utf-8") as f:
                content_text = f.read()
        else:
            content_text = content

        thumb_media_id = ""
        if cover:
            from execution.adapters.wechat.tools import wechat_upload_media
            print_info(f"正在上传封面图: {cover}")
            media_result = loop.run_until_complete(wechat_upload_media(cover, "image"))
            thumb_media_id = media_result.get("media_id", "")
            print_success(f"封面上传成功, media_id: {thumb_media_id}")

        print_info(f"正在发布文章: {title}")
        result = loop.run_until_complete(publish_article(
            title=title,
            content=content_text,
            author=author,
            digest=digest,
            thumb_media_id=thumb_media_id,
            need_publish=not no_publish,
        ))

        print_success(f"草稿创建成功")
        print_info(f"  MediaID: {result['draft']['media_id']}")
        if "publish" in result:
            print_success(f"发布任务已提交")
            print_info(f"  PublishID: {result['publish']['publish_id']}")
            print_info(f"  预计 2-5 分钟后完成")

        return result
    except Exception as e:
        print_error(f"发布失败: {e}")
        raise
    finally:
        loop.close()