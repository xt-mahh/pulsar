"""WeChat API response models — Pydantic models for all WeChat API responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WeChatToken(BaseModel):
    """WeChat access_token model."""
    access_token: str = Field(..., description="API access token")
    expires_in: int = Field(7200, description="Token validity in seconds")
    acquired_at: float = Field(..., description="Unix timestamp when acquired")


class WeChatDraftArticle(BaseModel):
    """Single article within a draft."""
    title: str = Field(..., description="Article title (1-64 chars)")
    author: str = Field("", description="Author (1-8 chars)")
    digest: str = Field("", description="Article summary (auto from content if empty)")
    content: str = Field(..., description="Article body HTML")
    cover_media_id: str = Field(..., description="Cover image media_id")
    need_open_comment: int = Field(0, description="0=close, 1=open comments")
    only_fans_can_comment: int = Field(0, description="0=all, 1=fans only")
    need_show_cover: int = Field(1, description="0=hide, 1=show cover in body")
    content_source_url: str = Field("", description="Original article URL")
    category_id: Optional[int] = Field(None, description="Category ID")
    pic_crop_235_1: Optional[str] = Field(None, description="Cover crop (2.35:1), 'x1,y1,x2,y2'")
    pic_crop_1_1: Optional[str] = Field(None, description="Cover crop (1:1), 'x1,y1,x2,y2'")


class WeChatDraft(BaseModel):
    """WeChat draft model."""
    media_id: str = Field(..., description="Draft unique ID")
    title: str = Field(..., description="Article title")
    author: str = Field("", description="Author")
    digest: str = Field("", description="Summary")
    content: str = Field(..., description="Article body HTML")
    cover_media_id: str = Field(..., description="Cover image media_id")
    need_open_comment: int = Field(0, description="Comments enabled")
    create_time: datetime = Field(..., description="Creation time")
    update_time: datetime = Field(..., description="Last modified time")
    url: Optional[str] = Field(None, description="Preview URL")


class WeChatPublishResult(BaseModel):
    """WeChat publish result model."""
    publish_id: str = Field(..., description="Publish task ID")
    status: int = Field(..., description="0=success, 1=publishing, 2=failed")
    article_id: Optional[str] = Field(None, description="Published article ID")
    fail_idx: list[int] = Field(default_factory=list, description="Failed article indices")
    publish_time: Optional[datetime] = Field(None, description="Actual publish time")


class WeChatMedia(BaseModel):
    """WeChat material model."""
    media_id: str = Field(..., description="Material unique ID")
    name: str = Field("", description="File name")
    url: Optional[str] = Field(None, description="Material URL")
    size: int = Field(0, description="File size in bytes")
    created_at: datetime = Field(..., description="Upload time")
    type: str = Field("image", description="Material type: image/voice/video/thumb")


class WeChatStats(BaseModel):
    """WeChat article statistics model."""
    article_id: str = Field(..., description="Article ID")
    title: str = Field(..., description="Article title")
    read_count: int = Field(0, description="Read count")
    like_count: int = Field(0, description="Like count")
    share_count: int = Field(0, description="Share count")
    collect_count: int = Field(0, description="Collect count")
    comment_count: int = Field(0, description="Comment count")
    date: str = Field(..., description="Statistics date (yyyy-mm-dd)")


class WeChatAPIError(BaseModel):
    """WeChat API error response."""
    errcode: int = Field(..., description="WeChat error code")
    errmsg: str = Field(..., description="Error message")


class WeChatMenu(BaseModel):
    """WeChat menu button."""
    name: str = Field(..., description="Button name")
    type: Optional[str] = Field(None, description="Button type: click/view/miniprogram")
    key: Optional[str] = Field(None, description="Key for click type")
    url: Optional[str] = Field(None, description="URL for view type")
    appid: Optional[str] = Field(None, description="AppID for miniprogram")
    pagepath: Optional[str] = Field(None, description="Page path for miniprogram")
    sub_button: Optional[list["WeChatMenu"]] = Field(None, description="Sub-buttons")


class WeChatUserInfo(BaseModel):
    """WeChat user info model."""
    subscribe: int = Field(0, description="Whether user is subscribed: 0=no, 1=yes")
    openid: str = Field(..., description="User's OpenID")
    nickname: str = Field("", description="Nickname")
    sex: int = Field(0, description="Gender: 0=unknown, 1=male, 2=female")
    city: str = Field("", description="City")
    country: str = Field("", description="Country")
    province: str = Field("", description="Province")
    language: str = Field("zh_CN", description="Language")
    headimgurl: str = Field("", description="Avatar URL")
    subscribe_time: int = Field(0, description="Subscribe timestamp")
    unionid: Optional[str] = Field(None, description="UnionID (cross-account)")
    remark: str = Field("", description="Admin remark")
    groupid: int = Field(0, description="Group ID")
    tagid_list: list[int] = Field(default_factory=list, description="Tag IDs")
    subscribe_scene: str = Field("", description="Subscribe scene")
    qr_scene: int = Field(0, description="QR scene")
    qr_scene_str: str = Field("", description="QR scene string")


class WeChatComment(BaseModel):
    """WeChat article comment model."""
    comment_id: int = Field(..., description="Comment ID")
    content: str = Field(..., description="Comment content")
    create_time: int = Field(..., description="Creation timestamp")
    reply: Optional[dict] = Field(None, description="Reply to this comment")
    user_comment_id: Optional[int] = Field(None, description="Parent comment ID")
    openid: str = Field(..., description="Commenter's OpenID")
    nick_name: str = Field("", description="Commenter's nickname")
    like_count: int = Field(0, description="Like count")
    is_top: bool = Field(False, description="Whether pinned")
    comment_type: int = Field(0, description="0=normal, 1=selected")
