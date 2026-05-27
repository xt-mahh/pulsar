import time
from shared.models import ToolDefinition
from shared.errors import AdapterError
from execution.adapters.base import BasePlatformAdapter
from execution.adapters.wechat.auth import WeChatTokenManager
from execution.adapters.wechat import tools as wechat_tools


TOOL_DEFINITIONS = [
    ToolDefinition(name="wechat_draft_add", description="创建图文草稿", input_schema={
        "type": "object", "properties": {
            "articles": {"type": "array", "items": {"type": "object"}, "description": "文章列表"},
        }, "required": ["articles"],
    }),
    ToolDefinition(name="wechat_draft_list", description="获取草稿列表", input_schema={
        "type": "object", "properties": {
            "offset": {"type": "integer", "default": 0},
            "count": {"type": "integer", "default": 20},
        },
    }),
    ToolDefinition(name="wechat_draft_get", description="获取单篇草稿", input_schema={
        "type": "object", "properties": {
            "media_id": {"type": "string"},
        }, "required": ["media_id"],
    }),
    ToolDefinition(name="wechat_draft_delete", description="删除草稿", input_schema={
        "type": "object", "properties": {
            "media_id": {"type": "string"},
        }, "required": ["media_id"],
    }),
    ToolDefinition(name="wechat_publish_submit", description="提交发布", input_schema={
        "type": "object", "properties": {
            "media_id": {"type": "string"},
        }, "required": ["media_id"],
    }),
    ToolDefinition(name="wechat_publish_status", description="查询发布状态", input_schema={
        "type": "object", "properties": {
            "publish_id": {"type": "string"},
        }, "required": ["publish_id"],
    }),
    ToolDefinition(name="wechat_publish_list", description="已发布文章列表", input_schema={
        "type": "object", "properties": {
            "offset": {"type": "integer", "default": 0},
            "count": {"type": "integer", "default": 20},
        },
    }),
    ToolDefinition(name="wechat_upload_image", description="上传正文图片", input_schema={
        "type": "object", "properties": {
            "file_path": {"type": "string"},
        }, "required": ["file_path"],
    }),
    ToolDefinition(name="wechat_upload_media", description="上传素材", input_schema={
        "type": "object", "properties": {
            "file_path": {"type": "string"},
            "media_type": {"type": "string", "default": "image"},
        }, "required": ["file_path"],
    }),
    ToolDefinition(name="wechat_stats_user_summary", description="用户增减数据", input_schema={
        "type": "object", "properties": {
            "begin_date": {"type": "string"},
            "end_date": {"type": "string"},
        }, "required": ["begin_date", "end_date"],
    }),
    ToolDefinition(name="wechat_stats_user_cumulate", description="累计用户数据", input_schema={
        "type": "object", "properties": {
            "begin_date": {"type": "string"},
            "end_date": {"type": "string"},
        }, "required": ["begin_date", "end_date"],
    }),
    ToolDefinition(name="wechat_stats_article_summary", description="图文群发每日数据", input_schema={
        "type": "object", "properties": {
            "begin_date": {"type": "string"},
            "end_date": {"type": "string"},
        }, "required": ["begin_date", "end_date"],
    }),
    ToolDefinition(name="wechat_stats_article_total", description="图文总数据", input_schema={
        "type": "object", "properties": {
            "begin_date": {"type": "string"},
            "end_date": {"type": "string"},
        }, "required": ["begin_date", "end_date"],
    }),
    ToolDefinition(name="wechat_comment_open", description="打开评论", input_schema={
        "type": "object", "properties": {
            "msg_data_id": {"type": "integer"},
            "index": {"type": "integer", "default": 0},
        }, "required": ["msg_data_id"],
    }),
    ToolDefinition(name="wechat_comment_list", description="评论列表", input_schema={
        "type": "object", "properties": {
            "msg_data_id": {"type": "integer"},
            "index": {"type": "integer", "default": 0},
            "begin": {"type": "integer", "default": 0},
            "count": {"type": "integer", "default": 50},
            "type": {"type": "integer", "default": 0},
        }, "required": ["msg_data_id"],
    }),
    ToolDefinition(name="wechat_comment_reply", description="回复评论", input_schema={
        "type": "object", "properties": {
            "msg_data_id": {"type": "integer"},
            "index": {"type": "integer"},
            "user_comment_id": {"type": "integer"},
            "content": {"type": "string"},
        }, "required": ["msg_data_id", "user_comment_id", "content"],
    }),
    ToolDefinition(name="wechat_comment_markelect", description="精选评论", input_schema={
        "type": "object", "properties": {
            "msg_data_id": {"type": "integer"},
            "index": {"type": "integer"},
            "user_comment_id": {"type": "integer"},
        }, "required": ["msg_data_id", "user_comment_id"],
    }),
    ToolDefinition(name="wechat_menu_create", description="创建菜单", input_schema={
        "type": "object", "properties": {
            "button": {"type": "array"},
        }, "required": ["button"],
    }),
    ToolDefinition(name="wechat_menu_get", description="查询菜单", input_schema={
        "type": "object", "properties": {},
    }),
    ToolDefinition(name="wechat_menu_delete", description="删除菜单", input_schema={
        "type": "object", "properties": {},
    }),
    ToolDefinition(name="wechat_user_list", description="用户列表", input_schema={
        "type": "object", "properties": {
            "next_openid": {"type": "string", "default": ""},
        },
    }),
    ToolDefinition(name="wechat_user_info", description="用户详情", input_schema={
        "type": "object", "properties": {
            "openid": {"type": "string"},
            "lang": {"type": "string", "default": "zh_CN"},
        }, "required": ["openid"],
    }),
    ToolDefinition(name="publish_article", description="端到端图文发布", input_schema={
        "type": "object", "properties": {
            "title": {"type": "string", "maxLength": 32},
            "content": {"type": "string"},
            "author": {"type": "string", "default": "Pulsar"},
            "digest": {"type": "string", "default": ""},
            "thumb_media_id": {"type": "string", "default": ""},
            "need_open_comment": {"type": "boolean", "default": True},
            "need_publish": {"type": "boolean", "default": True},
        }, "required": ["title", "content"],
    }),
]


TOOL_MAP = {
    "wechat_draft_add": wechat_tools.wechat_draft_add,
    "wechat_draft_list": wechat_tools.wechat_draft_list,
    "wechat_draft_get": wechat_tools.wechat_draft_get,
    "wechat_draft_delete": wechat_tools.wechat_draft_delete,
    "wechat_publish_submit": wechat_tools.wechat_publish_submit,
    "wechat_publish_status": wechat_tools.wechat_publish_status,
    "wechat_publish_list": wechat_tools.wechat_publish_list,
    "wechat_upload_image": wechat_tools.wechat_upload_image,
    "wechat_upload_media": wechat_tools.wechat_upload_media,
    "wechat_stats_user_summary": wechat_tools.wechat_stats_user_summary,
    "wechat_stats_user_cumulate": wechat_tools.wechat_stats_user_cumulate,
    "wechat_stats_article_summary": wechat_tools.wechat_stats_article_summary,
    "wechat_stats_article_total": wechat_tools.wechat_stats_article_total,
    "wechat_comment_open": wechat_tools.wechat_comment_open,
    "wechat_comment_list": wechat_tools.wechat_comment_list,
    "wechat_comment_reply": wechat_tools.wechat_comment_reply,
    "wechat_comment_markelect": wechat_tools.wechat_comment_markelect,
    "wechat_menu_create": wechat_tools.wechat_menu_create,
    "wechat_menu_get": wechat_tools.wechat_menu_get,
    "wechat_menu_delete": wechat_tools.wechat_menu_delete,
    "wechat_user_list": wechat_tools.wechat_user_list,
    "wechat_user_info": wechat_tools.wechat_user_info,
    "publish_article": wechat_tools.publish_article,
}


class WeChatAdapter(BasePlatformAdapter):
    def __init__(self, config: dict = None):
        self._config = config or {}
        self._token_manager: WeChatTokenManager | None = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "wechat"

    @property
    def platform(self) -> str:
        return "wechat"

    async def initialize(self) -> bool:
        try:
            app_id = self._config.get("app_id", "")
            app_secret = self._config.get("app_secret", "")
            api_base = self._config.get("api_base", "https://api.weixin.qq.com")
            cache_ttl = self._config.get("token_cache_ttl", 7200)

            from execution.adapters.wechat.tools import _init_tm
            _init_tm(app_id, app_secret, api_base, cache_ttl)

            self._initialized = True
            return True
        except Exception as e:
            self._initialized = False
            return False

    async def get_tools(self) -> list[ToolDefinition]:
        return TOOL_DEFINITIONS

    async def handle_tool_call(self, name: str, args: dict) -> dict:
        if not self._initialized:
            raise AdapterError("wechat", "Adapter not initialized")

        tool_fn = TOOL_MAP.get(name)
        if not tool_fn:
            raise AdapterError("wechat", f"Unknown tool: {name}")

        try:
            result = await tool_fn(**args)
            return result
        except Exception as e:
            raise AdapterError("wechat", str(e)) from e