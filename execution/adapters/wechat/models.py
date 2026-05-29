"""微信数据模型 — 映射微信公众号 API 的数据结构"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WeChatArticle(BaseModel):
    """微信图文消息文章"""

    title: str = Field(..., max_length=32, description="标题（限制 32 字）")
    author: str = Field(default="Pulsar", max_length=16, description="作者（限制 16 字）")
    digest: str = Field(default="", max_length=128, description="摘要（限制 128 字）")
    content: str = Field(..., description="图文消息的具体内容，支持 HTML 标签，必须少于 20K 字符")
    content_source_url: str = Field(default="", description="图文消息的原文地址")
    thumb_media_id: str = Field(default="", description="图文消息的封面图片素材 ID")
    need_open_comment: int = Field(default=1, ge=0, le=1, description="是否打开评论，0 不打开，1 打开")
    only_fans_can_comment: int = Field(default=0, ge=0, le=1, description="是否粉丝才可评论，0 所有人，1 粉丝")
    need_show_cover: int = Field(default=1, ge=0, le=1, description="是否显示封面，0 不显示，1 显示")


class WeChatDraft(BaseModel):
    """微信草稿"""

    media_id: str = Field(..., description="草稿的 media_id")
    content: dict[str, Any] = Field(default_factory=dict, description="草稿内容")
    create_time: datetime | None = Field(default=None, description="创建时间")
    update_time: datetime | None = Field(default=None, description="更新时间")


class WeChatPublishResult(BaseModel):
    """微信发布结果"""

    publish_id: str = Field(..., description="发布任务 ID")
    msg_status: int = Field(default=0, description="发布状态：0 进行中，1 已完成，2 失败")
    msg_id: str = Field(default="", description="发布后生成的群发 msg_id")


class WeChatPublishStatus(BaseModel):
    """微信发布状态查询结果"""

    publish_id: str = Field(..., description="发布任务 ID")
    msg_status: int = Field(..., description="发布状态：0 进行中，1 已完成，2 失败")
    article_id: str = Field(default="", description="发布成功后的文章 ID")
    fail_idx: list[int] = Field(default_factory=list, description="发布失败的索引")


class WeChatStatsOverview(BaseModel):
    """微信数据统计概览"""

    ref_date: str = Field(..., description="数据日期")
    user_source: int = Field(default=0, description="用户渠道")
    new_user: int = Field(default=0, description="新增用户数")
    cancel_user: int = Field(default=0, description="取消关注用户数")
    cumulate_user: int = Field(default=0, description="总用户数")


class WeChatArticleStats(BaseModel):
    """微信单篇文章数据"""

    ref_date: str = Field(..., description="数据日期")
    msgid: str = Field(..., description="消息 ID")
    title: str = Field(..., description="文章标题")
    int_page_read_user: int = Field(default=0, description="阅读人数")
    int_page_read_count: int = Field(default=0, description="阅读次数")
    share_user: int = Field(default=0, description="分享人数")
    share_count: int = Field(default=0, description="分享次数")
    add_to_fav_user: int = Field(default=0, description="收藏人数")
    add_to_fav_count: int = Field(default=0, description="收藏次数")
    target_user: int = Field(default=0, description="送达人数")


class WeChatMedia(BaseModel):
    """微信素材"""

    media_id: str = Field(..., description="素材 ID")
    name: str = Field(default="", description="素材名称")
    url: str = Field(default="", description="素材 URL")
    update_time: datetime | None = Field(default=None, description="更新时间")
    type: str = Field(default="image", description="素材类型：image, voice, video, thumb")


class WeChatComment(BaseModel):
    """微信评论"""

    comment_id: int = Field(..., description="评论 ID")
    content: str = Field(..., description="评论内容")
    create_time: datetime | None = Field(default=None, description="评论时间")
    reply_content: str = Field(default="", description="回复内容")
    status: int = Field(default=0, description="评论状态：0 未精选，1 已精选，2 已删除")
    user_comment_id: int = Field(default=0, description="用户评论 ID")
    nick_name: str = Field(default="", description="评论用户昵称")


class WeChatMenuButton(BaseModel):
    """微信菜单按钮"""

    type: str = Field(..., description="菜单类型：click, view, miniprogram 等")
    name: str = Field(..., max_length=40, description="菜单名称（限制 40 字）")
    key: str = Field(default="", description="click 类型菜单的 key")
    url: str = Field(default="", description="view 类型菜单的 URL")
    sub_buttons: list["WeChatMenuButton"] = Field(default_factory=list, description="子菜单列表")