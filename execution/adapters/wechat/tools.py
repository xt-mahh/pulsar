"""微信 MCP 工具定义 — 微信公众号 API 的 22+ 工具清单"""

from shared.models import ToolDefinition

# ============================================================
# 草稿管理 (Draft)
# ============================================================

draft_add = ToolDefinition(
    name="wechat_draft_add",
    description="创建图文草稿",
    input_schema={
        "type": "object",
        "properties": {
            "articles": {
                "type": "array",
                "description": "图文列表（支持多图文，最多 8 篇）",
                "items": {"type": "object"},
            }
        },
        "required": ["articles"],
    },
    agent="adapter.wechat",
)

draft_update = ToolDefinition(
    name="wechat_draft_update",
    description="更新图文草稿",
    input_schema={
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "草稿 media_id"},
            "articles": {"type": "array", "description": "更新后的图文列表"},
            "index": {
                "type": "integer",
                "description": "多图文时的索引（0-based），不传则覆盖全部",
            },
        },
        "required": ["media_id", "articles"],
    },
    agent="adapter.wechat",
)

draft_get = ToolDefinition(
    name="wechat_draft_get",
    description="获取草稿内容",
    input_schema={
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "草稿 media_id"}
        },
        "required": ["media_id"],
    },
    agent="adapter.wechat",
)

draft_delete = ToolDefinition(
    name="wechat_draft_delete",
    description="删除草稿",
    input_schema={
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "草稿 media_id"}
        },
        "required": ["media_id"],
    },
    agent="adapter.wechat",
)

draft_list = ToolDefinition(
    name="wechat_draft_list",
    description="获取草稿列表",
    input_schema={
        "type": "object",
        "properties": {
            "offset": {"type": "integer", "description": "偏移位置，默认 0"},
            "count": {
                "type": "integer",
                "description": "返回数量，默认 20，最大 50",
            },
            "no_content": {
                "type": "integer",
                "description": "是否不返回内容体，1 不返回，0 返回",
            },
        },
    },
    agent="adapter.wechat",
)

# ============================================================
# 发布管理 (Publish)
# ============================================================

publish_submit = ToolDefinition(
    name="wechat_publish_submit",
    description="提交发布任务（将草稿发布到公众号）",
    input_schema={
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "草稿 media_id"}
        },
        "required": ["media_id"],
    },
    agent="adapter.wechat",
)

publish_get_status = ToolDefinition(
    name="wechat_publish_get_status",
    description="查询发布任务状态",
    input_schema={
        "type": "object",
        "properties": {
            "publish_id": {"type": "string", "description": "发布任务 ID"}
        },
        "required": ["publish_id"],
    },
    agent="adapter.wechat",
)

publish_get_article_detail = ToolDefinition(
    name="wechat_publish_get_article_detail",
    description="获取已发布文章详情",
    input_schema={
        "type": "object",
        "properties": {
            "article_id": {"type": "string", "description": "文章 ID"}
        },
        "required": ["article_id"],
    },
    agent="adapter.wechat",
)

publish_delete = ToolDefinition(
    name="wechat_publish_delete",
    description="删除已发布文章",
    input_schema={
        "type": "object",
        "properties": {
            "article_id": {"type": "string", "description": "文章 ID"},
            "index": {
                "type": "integer",
                "description": "多图文时的索引（0-based），不传则删除全部",
            },
        },
        "required": ["article_id"],
    },
    agent="adapter.wechat",
)

# ============================================================
# 素材管理 (Media)
# ============================================================

media_upload = ToolDefinition(
    name="wechat_media_upload",
    description="上传素材（图片、语音、视频、缩略图）",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "素材文件路径"},
            "type": {
                "type": "string",
                "enum": ["image", "voice", "video", "thumb"],
                "description": "素材类型",
            },
        },
        "required": ["file_path", "type"],
    },
    agent="adapter.wechat",
)

media_upload_image = ToolDefinition(
    name="wechat_media_upload_image",
    description="上传图文消息内的图片（用于正文中的图片）",
    input_schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "图片文件路径"}
        },
        "required": ["file_path"],
    },
    agent="adapter.wechat",
)

media_get = ToolDefinition(
    name="wechat_media_get",
    description="获取素材 URL",
    input_schema={
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "素材 media_id"}
        },
        "required": ["media_id"],
    },
    agent="adapter.wechat",
)

media_list = ToolDefinition(
    name="wechat_media_list",
    description="获取素材列表",
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["image", "voice", "video", "thumb", "news"],
                "description": "素材类型",
            },
            "offset": {"type": "integer", "description": "偏移位置，默认 0"},
            "count": {
                "type": "integer",
                "description": "返回数量，默认 20，最大 50",
            },
        },
        "required": ["type"],
    },
    agent="adapter.wechat",
)

# ============================================================
# 评论管理 (Comment)
# ============================================================

comment_list = ToolDefinition(
    name="wechat_comment_list",
    description="获取文章评论列表",
    input_schema={
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "群发返回的 msg_data_id"},
            "index": {"type": "integer", "description": "多图文时的索引"},
            "begin": {"type": "integer", "description": "起始位置，默认 0"},
            "count": {"type": "integer", "description": "返回数量，默认 50"},
            "type": {
                "type": "integer",
                "description": "评论类型：0 全部，1 精选，2 未精选",
            },
        },
        "required": ["msg_data_id"],
    },
    agent="adapter.wechat",
)

comment_markelect = ToolDefinition(
    name="wechat_comment_markelect",
    description="将评论标记为精选",
    input_schema={
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "群发返回的 msg_data_id"},
            "index": {"type": "integer", "description": "多图文时的索引"},
            "comment_id": {"type": "integer", "description": "评论 ID"},
        },
        "required": ["msg_data_id", "comment_id"],
    },
    agent="adapter.wechat",
)

comment_unmarkelect = ToolDefinition(
    name="wechat_comment_unmarkelect",
    description="取消精选评论",
    input_schema={
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "群发返回的 msg_data_id"},
            "index": {"type": "integer", "description": "多图文时的索引"},
            "comment_id": {"type": "integer", "description": "评论 ID"},
        },
        "required": ["msg_data_id", "comment_id"],
    },
    agent="adapter.wechat",
)

comment_delete = ToolDefinition(
    name="wechat_comment_delete",
    description="删除评论",
    input_schema={
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "群发返回的 msg_data_id"},
            "index": {"type": "integer", "description": "多图文时的索引"},
            "comment_id": {"type": "integer", "description": "评论 ID"},
        },
        "required": ["msg_data_id", "comment_id"],
    },
    agent="adapter.wechat",
)

comment_reply = ToolDefinition(
    name="wechat_comment_reply",
    description="回复评论",
    input_schema={
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "群发返回的 msg_data_id"},
            "index": {"type": "integer", "description": "多图文时的索引"},
            "comment_id": {"type": "integer", "description": "评论 ID"},
            "content": {"type": "string", "description": "回复内容"},
        },
        "required": ["msg_data_id", "comment_id", "content"],
    },
    agent="adapter.wechat",
)

# ============================================================
# 菜单管理 (Menu)
# ============================================================

menu_create = ToolDefinition(
    name="wechat_menu_create",
    description="创建自定义菜单",
    input_schema={
        "type": "object",
        "properties": {
            "button": {
                "type": "array",
                "description": "菜单按钮列表（最多 3 个一级菜单，每个最多 5 个子菜单）",
                "items": {"type": "object"},
            }
        },
        "required": ["button"],
    },
    agent="adapter.wechat",
)

menu_get = ToolDefinition(
    name="wechat_menu_get",
    description="获取自定义菜单配置",
    input_schema={"type": "object", "properties": {}},
    agent="adapter.wechat",
)

menu_delete = ToolDefinition(
    name="wechat_menu_delete",
    description="删除自定义菜单",
    input_schema={"type": "object", "properties": {}},
    agent="adapter.wechat",
)

# ============================================================
# 数据统计 (Stats)
# ============================================================

stats_user_summary = ToolDefinition(
    name="wechat_stats_user_summary",
    description="获取用户增减数据（最多 7 天）",
    input_schema={
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
        },
        "required": ["begin_date", "end_date"],
    },
    agent="adapter.wechat",
)

stats_user_cumulate = ToolDefinition(
    name="wechat_stats_user_cumulate",
    description="获取累计用户数据（最多 7 天）",
    input_schema={
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
        },
        "required": ["begin_date", "end_date"],
    },
    agent="adapter.wechat",
)

stats_article_summary = ToolDefinition(
    name="wechat_stats_article_summary",
    description="获取图文群发每日数据",
    input_schema={
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
        },
        "required": ["begin_date", "end_date"],
    },
    agent="adapter.wechat",
)

stats_article_total = ToolDefinition(
    name="wechat_stats_article_total",
    description="获取图文统计数据（含分享/收藏等）",
    input_schema={
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
        },
        "required": ["begin_date", "end_date"],
    },
    agent="adapter.wechat",
)

# ============================================================
# 用户管理 (User)
# ============================================================

user_get = ToolDefinition(
    name="wechat_user_get",
    description="获取用户列表（OPENID）",
    input_schema={
        "type": "object",
        "properties": {
            "next_openid": {
                "type": "string",
                "description": "第一个拉取的 OPENID，不传默认从头开始",
            }
        },
    },
    agent="adapter.wechat",
)

user_info = ToolDefinition(
    name="wechat_user_info",
    description="获取用户基本信息",
    input_schema={
        "type": "object",
        "properties": {
            "openid": {"type": "string", "description": "用户 OPENID"},
            "lang": {
                "type": "string",
                "enum": ["zh_CN", "zh_TW", "en"],
                "description": "语言",
            },
        },
        "required": ["openid"],
    },
    agent="adapter.wechat",
)

# ============================================================
# 工具列表汇总
# ============================================================

ALL_WECHAT_TOOLS: list[ToolDefinition] = [
    # 草稿管理 (5)
    draft_add,
    draft_update,
    draft_get,
    draft_delete,
    draft_list,
    # 发布管理 (4)
    publish_submit,
    publish_get_status,
    publish_get_article_detail,
    publish_delete,
    # 素材管理 (4)
    media_upload,
    media_upload_image,
    media_get,
    media_list,
    # 评论管理 (5)
    comment_list,
    comment_markelect,
    comment_unmarkelect,
    comment_delete,
    comment_reply,
    # 菜单管理 (3)
    menu_create,
    menu_get,
    menu_delete,
    # 数据统计 (4)
    stats_user_summary,
    stats_user_cumulate,
    stats_article_summary,
    stats_article_total,
    # 用户管理 (2)
    user_get,
    user_info,
]