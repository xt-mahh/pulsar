from pydantic import BaseModel, Field
from typing import Optional, List


class WeChatArticle(BaseModel):
    title: str = Field(..., max_length=32)
    author: str = Field(default="Pulsar", max_length=16)
    digest: str = Field(default="", max_length=128)
    content: str = Field(..., description="HTML 正文，< 20K 字符")
    thumb_media_id: str = Field(default="", description="封面素材 media_id")
    need_open_comment: int = Field(default=1, ge=0, le=1)
    need_close_comment: int = Field(default=0, ge=0, le=1)
    only_fans_can_comment: int = Field(default=0, ge=0, le=1)


class WeChatDraftResponse(BaseModel):
    media_id: str
    item: Optional[list] = None


class WeChatPublishSubmitResponse(BaseModel):
    publish_id: str
    msg_data_id: Optional[str] = None
    status: Optional[str] = None


class WeChatPublishStatusResponse(BaseModel):
    publish_id: str
    status: str
    article_id: Optional[str] = None
    fail_msg: Optional[str] = None


class WeChatStatsUserSummary(BaseModel):
    ref_date: str
    user_source: int = 0
    new_user: int = 0
    cancel_user: int = 0


class WeChatStatsArticle(BaseModel):
    ref_date: str
    msgid: str
    title: str
    int_page_read_user: int = 0
    int_page_read_count: int = 0
    share_user: int = 0
    share_count: int = 0