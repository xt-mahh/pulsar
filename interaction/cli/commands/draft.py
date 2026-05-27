import click
import asyncio
from interaction.cli.formats import console, print_error, print_success, print_info
from execution.adapters.wechat.tools import (
    wechat_draft_list, wechat_draft_get, wechat_draft_delete,
)


@click.group(name="draft")
def draft_group():
    """管理草稿箱"""


@draft_group.command(name="list")
@click.argument("platform", default="wechat")
@click.option("--offset", default=0, help="偏移量")
@click.option("--count", default=20, help="数量")
def draft_list(platform, offset, count):
    """列出草稿"""
    if platform != "wechat":
        print_error(f"不支持的平台: {platform}")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(wechat_draft_list(offset=offset, count=count))
        items = result.get("item", [])
        print_success(f"草稿列表 ({len(items)} 篇):")
        for item in items:
            content = item.get("content", {})
            news_item = content.get("news_item", [{}])[0]
            print_info(f"  📄 {news_item.get('title', '无标题')} — {item.get('media_id', '')}")
        return result
    except Exception as e:
        print_error(f"获取草稿列表失败: {e}")
    finally:
        loop.close()


@draft_group.command(name="get")
@click.argument("media_id")
def draft_get(media_id):
    """获取单篇草稿"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(wechat_draft_get(media_id))
        print_success(f"草稿详情:")
        print_info(result)
        return result
    except Exception as e:
        print_error(f"获取草稿失败: {e}")
    finally:
        loop.close()


@draft_group.command(name="delete")
@click.argument("media_id")
def draft_delete(media_id):
    """删除草稿"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(wechat_draft_delete(media_id))
        print_success(f"草稿已删除: {media_id}")
        return result
    except Exception as e:
        print_error(f"删除草稿失败: {e}")
    finally:
        loop.close()