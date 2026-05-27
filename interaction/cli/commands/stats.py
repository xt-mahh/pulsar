import click
import asyncio
from datetime import datetime, timedelta
from interaction.cli.formats import console, print_error, print_success, print_info
from execution.adapters.wechat.tools import (
    wechat_stats_user_summary, wechat_stats_user_cumulate,
    wechat_stats_article_summary,
)


def _get_date_range(period: str) -> tuple[str, str]:
    today = datetime.now()
    if period == "today":
        return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    elif period == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d"), yesterday.strftime("%Y-%m-%d")
    elif period == "week":
        week_ago = today - timedelta(days=7)
        return week_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    elif period == "month":
        month_ago = today - timedelta(days=30)
        return month_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


@click.group(name="stats")
def stats_group():
    """查看运营数据"""


@stats_group.command(name="wechat")
@click.option("--period", default="today", type=click.Choice(["today", "yesterday", "week", "month"]))
def stats_wechat(period):
    """查询微信运营数据"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        begin_date, end_date = _get_date_range(period)

        user_summary = loop.run_until_complete(wechat_stats_user_summary(begin_date, end_date))
        user_cumulate = loop.run_until_complete(wechat_stats_user_cumulate(begin_date, end_date))
        article_summary = loop.run_until_complete(wechat_stats_article_summary(begin_date, end_date))

        total_new = sum(u.get("new_user", 0) for u in user_summary.get("list", []))
        total_cancel = sum(u.get("cancel_user", 0) for u in user_summary.get("list", []))
        total_cumulate = sum(u.get("cumulate_user", 0) for u in user_cumulate.get("list", []))

        print_success(f"📊 微信{period}运营数据")
        print_info(f"  新增关注: +{total_new}")
        print_info(f"  取关: -{total_cancel}")
        print_info(f"  净增: {total_new - total_cancel}")
        print_info(f"  总用户: {total_cumulate}")

        articles = article_summary.get("list", [])
        if articles:
            print_info(f"\n  文章阅读 TOP:")
            for i, article in enumerate(sorted(articles, key=lambda x: x.get("int_page_read_count", 0), reverse=True)[:3], 1):
                print_info(f"  {i}. \"{article.get('title', '未知')}\" — {article.get('int_page_read_count', 0)} 阅读 / {article.get('share_count', 0)} 分享")

        return {"user_summary": user_summary, "user_cumulate": user_cumulate, "article_summary": article_summary}
    except Exception as e:
        print_error(f"获取统计数据失败: {e}")
    finally:
        loop.close()