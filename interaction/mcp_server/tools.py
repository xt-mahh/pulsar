"""Pulsar 对外 MCP 工具定义"""

from typing import Any

# 对外暴露的 MCP 工具定义
# 格式遵循 MCP 协议规范

EXTERNAL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "platform_publish",
        "description": "发布内容到指定内容平台",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "title": {
                    "type": "string",
                    "maxLength": 32,
                    "description": "文章标题",
                },
                "content": {
                    "type": "string",
                    "description": "文章正文（HTML 格式）",
                },
                "cover_path": {
                    "type": "string",
                    "description": "封面图本地路径（可选）",
                },
                "author": {
                    "type": "string",
                    "description": "作者名称（可选）",
                },
                "digest": {
                    "type": "string",
                    "description": "摘要（可选）",
                },
                "schedule_time": {
                    "type": "string",
                    "description": "定时发布时间（可选，格式 HH:MM）",
                },
            },
            "required": ["platform", "title", "content"],
        },
    },
    {
        "name": "platform_draft_create",
        "description": "创建内容草稿到指定平台",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "title": {
                    "type": "string",
                    "maxLength": 32,
                    "description": "文章标题",
                },
                "content": {
                    "type": "string",
                    "description": "文章正文（HTML 格式）",
                },
                "cover_path": {
                    "type": "string",
                    "description": "封面图本地路径（可选）",
                },
                "author": {
                    "type": "string",
                    "description": "作者名称（可选）",
                },
                "digest": {
                    "type": "string",
                    "description": "摘要（可选）",
                },
            },
            "required": ["platform", "title", "content"],
        },
    },
    {
        "name": "platform_draft_list",
        "description": "获取指定平台的草稿列表",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "offset": {
                    "type": "integer",
                    "description": "偏移量（可选，默认 0）",
                },
                "count": {
                    "type": "integer",
                    "description": "获取数量（可选，默认 20）",
                },
            },
            "required": ["platform"],
        },
    },
    {
        "name": "platform_stats",
        "description": "查询指定平台的运营数据",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "week", "month", "custom"],
                    "description": "统计周期",
                },
                "start": {
                    "type": "string",
                    "description": "开始日期（custom 时必填，格式 YYYY-MM-DD）",
                },
                "end": {
                    "type": "string",
                    "description": "结束日期（custom 时必填，格式 YYYY-MM-DD）",
                },
            },
            "required": ["platform", "period"],
        },
    },
    {
        "name": "platform_upload_media",
        "description": "上传素材到指定平台",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "file_path": {
                    "type": "string",
                    "description": "文件本地路径",
                },
                "media_type": {
                    "type": "string",
                    "enum": ["image", "thumb", "voice", "video"],
                    "description": "素材类型",
                },
            },
            "required": ["platform", "file_path", "media_type"],
        },
    },
    {
        "name": "system_status",
        "description": "查询 Pulsar 系统运行状态",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "task_schedule",
        "description": "创建定时发布任务",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "任务名称",
                },
                "schedule": {
                    "type": "string",
                    "description": "Cron 表达式（如 '0 17 * * *' 表示每天 17:00）",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["publish"],
                    "description": "任务类型",
                },
                "platform": {
                    "type": "string",
                    "enum": ["wechat"],
                    "description": "目标平台",
                },
                "params": {
                    "type": "object",
                    "description": "任务参数",
                },
            },
            "required": ["name", "schedule", "task_type", "platform"],
        },
    },
    {
        "name": "task_list",
        "description": "查看定时任务列表",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "paused", "all"],
                    "description": "按状态过滤（可选）",
                },
            },
        },
    },
]


def get_tool_definitions() -> list[dict[str, Any]]:
    """获取所有对外 MCP 工具定义"""
    return EXTERNAL_TOOLS


def find_tool(name: str) -> dict[str, Any] | None:
    """按名称查找工具定义"""
    for tool in EXTERNAL_TOOLS:
        if tool["name"] == name:
            return tool
    return None