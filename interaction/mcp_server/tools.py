import json
from mcp import Tool
from shared.models import ToolDefinition


def build_mcp_tool(td: ToolDefinition) -> Tool:
    return Tool(
        name=td.name,
        description=td.description,
        input_schema=td.input_schema,
    )


EXTERNAL_TOOLS = [
    Tool(
        name="platform_publish",
        description="发布内容到指定内容平台",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "title": {"type": "string", "maxLength": 32},
                "content": {"type": "string", "description": "HTML 正文"},
                "cover_path": {"type": "string", "description": "封面图本地路径"},
                "schedule_time": {"type": "string", "description": "定时发布（可选）"},
            },
            "required": ["platform", "title", "content"],
        },
    ),
    Tool(
        name="platform_draft_create",
        description="创建平台草稿",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["platform", "title", "content"],
        },
    ),
    Tool(
        name="platform_draft_list",
        description="获取平台草稿列表",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "offset": {"type": "integer", "default": 0},
                "count": {"type": "integer", "default": 20},
            },
            "required": ["platform"],
        },
    ),
    Tool(
        name="platform_stats",
        description="查询平台运营数据",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "period": {"type": "string", "enum": ["today", "yesterday", "week", "month"]},
            },
            "required": ["platform", "period"],
        },
    ),
    Tool(
        name="platform_upload_media",
        description="上传媒体素材到平台",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["wechat"]},
                "file_path": {"type": "string"},
                "media_type": {"type": "string", "default": "image"},
            },
            "required": ["platform", "file_path"],
        },
    ),
    Tool(
        name="system_status",
        description="查询系统运行状态",
        input_schema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="task_schedule",
        description="创建定时任务",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "schedule": {"type": "string", "description": "Cron 表达式"},
                "task_type": {"type": "string", "enum": ["publish", "health_check"]},
                "platform": {"type": "string", "default": "wechat"},
            },
            "required": ["name", "schedule", "task_type"],
        },
    ),
    Tool(
        name="task_list",
        description="查看任务列表",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "running", "completed", "failed"], "default": ""},
            },
        },
    ),
]


TOOL_HANDLERS = {
    "platform_publish": _handle_platform_publish,
    "platform_draft_create": _handle_platform_draft_create,
    "platform_draft_list": _handle_platform_draft_list,
    "platform_stats": _handle_platform_stats,
    "platform_upload_media": _handle_platform_upload_media,
    "system_status": _handle_system_status,
    "task_schedule": _handle_task_schedule,
    "task_list": _handle_task_list,
}


async def _handle_platform_publish(args: dict) -> dict:
    from execution.adapters.wechat.tools import publish_article
    return await publish_article(
        title=args["title"],
        content=args["content"],
        thumb_media_id=args.get("cover_path", ""),
    )


async def _handle_platform_draft_create(args: dict) -> dict:
    from execution.adapters.wechat.tools import wechat_draft_add
    return await wechat_draft_add([{
        "title": args["title"],
        "content": args["content"],
    }])


async def _handle_platform_draft_list(args: dict) -> dict:
    from execution.adapters.wechat.tools import wechat_draft_list
    return await wechat_draft_list(
        offset=args.get("offset", 0),
        count=args.get("count", 20),
    )


async def _handle_platform_stats(args: dict) -> dict:
    from interaction.cli.commands.stats import _get_date_range
    from execution.adapters.wechat.tools import wechat_stats_user_summary, wechat_stats_user_cumulate
    begin_date, end_date = _get_date_range(args.get("period", "today"))
    user_summary = await wechat_stats_user_summary(begin_date, end_date)
    user_cumulate = await wechat_stats_user_cumulate(begin_date, end_date)
    return {"user_summary": user_summary, "user_cumulate": user_cumulate}


async def _handle_platform_upload_media(args: dict) -> dict:
    from execution.adapters.wechat.tools import wechat_upload_media
    return await wechat_upload_media(
        file_path=args["file_path"],
        media_type=args.get("media_type", "image"),
    )


async def _handle_system_status(args: dict) -> dict:
    return {
        "system": "Pulsar",
        "version": "0.1.0",
        "status": "running",
        "agents": ["runtime", "gateway", "adapter.wechat", "tools"],
    }


async def _handle_task_schedule(args: dict) -> dict:
    return {
        "name": args["name"],
        "schedule": args["schedule"],
        "status": "scheduled",
    }


async def _handle_task_list(args: dict) -> dict:
    return {"tasks": []}


async def handle_tool_call(name: str, arguments: dict) -> dict:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        raise ValueError(f"Unknown tool: {name}")
    return await handler(arguments)