from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
import datetime as _dt
from datetime import datetime, timezone
import enum


class WeChatArticle(BaseModel):
    """微信草稿中的单篇文章模型。"""
    model_config = ConfigDict(frozen=True)

    title: str = Field(
        ...,
        description="文章标题。长度限制: 1-64 字符。超出会被截断。",
        max_length=64,
        min_length=1,
    )
    author: str = Field(
        default="",
        description="文章作者。长度限制: 1-8 字符。",
        max_length=8,
    )
    digest: str = Field(
        default="",
        description="文章摘要。不填则自动从正文前 120 字截取。",
        max_length=120,
    )
    content: str = Field(
        ...,
        description="文章正文 HTML。图片使用 <img src=\"media_id\"> 引用。"
                    "大小限制: ≤ 200KB（UTF-8 编码后）。"
    )
    cover_media_id: str = Field(
        ...,
        description="封面图片的 media_id。需先通过 upload_permanent_image 上传。"
    )
    need_open_comment: int = Field(
        default=0,
        description="是否打开评论: 0=关闭, 1=开启。",
        ge=0,
        le=1,
    )
    only_fans_can_comment: int = Field(
        default=0,
        description="是否仅粉丝可评论: 0=所有人可评论, 1=仅粉丝可评论。",
        ge=0,
        le=1,
    )
    need_show_cover: int = Field(
        default=1,
        description="是否在正文中显示封面图: 0=不显示, 1=显示。",
        ge=0,
        le=1,
    )
    content_source_url: str = Field(
        default="",
        description="原文链接 URL。可选的，用于注明文章来源。",
    )
    category_id: Optional[int] = Field(
        default=None,
        description="文章分类 ID。"
    )
    pic_crop_235_1: Optional[str] = Field(
        default=None,
        description="封面裁剪坐标（2.35:1 比例）。格式: 'x1,y1,x2,y2'。"
    )
    pic_crop_1_1: Optional[str] = Field(
        default=None,
        description="封面裁剪坐标（1:1 比例）。格式: 'x1,y1,x2,y2'。"
    )


class WeChatDraft(BaseModel):
    """微信公众号图文草稿模型。

    对应微信草稿箱 API 返回的草稿数据结构。
    """
    model_config = ConfigDict(frozen=True)

    media_id: str = Field(
        ...,
        description="草稿的唯一标识符（media_id）。用于后续的修改、发布等操作。"
    )
    articles: list[WeChatArticle] = Field(
        ...,
        description="草稿中的图文列表。最多 8 篇（多图文）。"
    )
    create_time: datetime = Field(
        ...,
        description="草稿创建时间。"
    )
    update_time: datetime = Field(
        ...,
        description="草稿最后修改时间。"
    )
    account_appid: str = Field(
        default="",
        description="草稿所属的公众号 AppID。"
    )

    # ---- 预览 ----
    preview_url: Optional[str] = Field(
        default=None,
        description="草稿预览 URL。可通过此链接在微信内预览草稿效果。"
    )

    def article_count(self) -> int:
        """返回草稿中的图文数量。"""
        return len(self.articles)


class WeChatPublishResult(BaseModel):
    """微信公众号发布结果模型。

    对应 freepublish/submit 和 freepublish/get 接口的返回数据。
    """
    model_config = ConfigDict(frozen=True)

    publish_id: str = Field(
        ...,
        description="发布任务 ID。用于后续查询发布状态。"
                    "格式: 数字字符串。"
    )
    msg_data_id: str = Field(
        default="",
        description="消息数据 ID。可用于数据统计接口查询文章数据。"
    )
    status: int = Field(
        ...,
        description="发布状态码:\n"
                    "- 0: 发布成功\n"
                    "- 1: 发布中（请轮询）\n"
                    "- 2: 发布失败\n"
                    "- 3: 草稿不可用（已被删除或修改）\n"
                    "- 4: 审核不通过\n"
                    "- 5: 发布超时",
        ge=0,
        le=5,
    )
    article_id: Optional[str] = Field(
        default=None,
        description="发布成功后的文章 ID。仅 status=0 时有值。"
                    "可用于删除已发布文章。"
    )
    fail_idx: list[int] = Field(
        default_factory=list,
        description="发布失败的文章索引列表。多图文模式下部分文章可能发布失败。"
    )
    publish_time: Optional[datetime] = Field(
        default=None,
        description="实际发布时间。"
    )

    # ---- 错误信息 ----
    errcode: Optional[int] = Field(
        default=None,
        description="微信 API 返回的错误码（如有）。"
    )
    errmsg: Optional[str] = Field(
        default=None,
        description="微信 API 返回的错误描述（如有）。"
    )

    def is_success(self) -> bool:
        """判断发布是否成功。"""
        return self.status == 0

    def is_publishing(self) -> bool:
        """判断是否正在发布中。"""
        return self.status == 1


class WeChatStats(BaseModel):
    """微信公众号单篇文章统计数据模型。

    对应微信数据统计接口（datacube 接口）返回的数据。
    统计延迟: 数据 T+1 更新（次日才能查到前一天的数据）。
    """
    model_config = ConfigDict(frozen=True)

    article_id: str = Field(
        ...,
        description="文章 ID（与 publish_result 中的 article_id 一致）。"
    )
    title: str = Field(
        ...,
        description="文章标题。"
    )
    date: _dt.date = Field(
        ...,
        description="统计日期。格式: yyyy-mm-dd。"
    )

    # ---- 阅读数据 ----
    read_count: int = Field(
        default=0,
        description="总阅读次数（含所有来源，含重复打开）。"
    )
    read_count_from_friends: int = Field(
        default=0,
        description="朋友圈来源的阅读次数。"
    )
    read_count_from_history: int = Field(
        default=0,
        description="历史消息来源的阅读次数。"
    )
    read_count_from_feed: int = Field(
        default=0,
        description="公众号会话来源的阅读次数（粉丝在订阅号列表中打开）。"
    )
    read_count_from_other: int = Field(
        default=0,
        description="其他来源的阅读次数（搜一搜、转载等）。"
    )
    read_count_from_moments: int = Field(
        default=0,
        description="朋友圈来源的阅读次数（与 read_count_from_friends 含义相同，微信接口用词不统一）。"
    )
    intime_read_count: int = Field(
        default=0,
        description="发布后 1 小时内的阅读次数。衡量文章初期传播效果。"
    )

    # ---- 互动数据 ----
    like_count: int = Field(
        default=0,
        description="点赞数（在看+点赞）。"
    )
    share_count: int = Field(
        default=0,
        description="分享转发次数。"
    )
    collect_count: int = Field(
        default=0,
        description="收藏次数。"
    )
    comment_count: int = Field(
        default=0,
        description="评论数（含精选和未精选）。"
    )
    reward_count: int = Field(
        default=0,
        description="赞赏次数（需开通赞赏功能）。"
    )

    # ---- 传播数据 ----
    total_share_count: int = Field(
        default=0,
        description="总分享次数。"
    )
    share_from_friends: int = Field(
        default=0,
        description="好友分享次数。"
    )
    share_from_moments: int = Field(
        default=0,
        description="朋友圈分享次数。"
    )
    add_to_fav_count: int = Field(
        default=0,
        description="被添加到收藏的次数。"
    )

    # ---- 粉丝增长 ----
    new_follow_count: int = Field(
        default=0,
        description="因这篇文章新增的关注数。"
    )
    unfollow_count: int = Field(
        default=0,
        description="因这篇文章流失的关注数。"
    )

    # ---- 元数据 ----
    source: str = Field(
        default="wechat_api",
        description="数据来源。'wechat_api' 表示实时查询，'cache' 表示缓存数据。"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="数据最后更新时间。"
    )

    def total_interactions(self) -> int:
        """返回总互动数（点赞+分享+收藏+评论）。"""
        return self.like_count + self.share_count + self.collect_count + self.comment_count


class WeChatOverallStats(BaseModel):
    """微信公众号整体统计数据模型（某时间范围内）。"""
    model_config = ConfigDict(frozen=True)

    start_date: _dt.date = Field(..., description="统计起始日期。")
    end_date: _dt.date = Field(..., description="统计结束日期。")

    # 整体阅读
    total_read_count: int = Field(default=0, description="总阅读次数。")
    total_share_count: int = Field(default=0, description="总分享次数。")
    total_like_count: int = Field(default=0, description="总点赞数。")

    # 文章统计
    article_count: int = Field(default=0, description="期间发布的文章数。")
    avg_read_per_article: float = Field(default=0.0, description="单篇文章平均阅读数。")
    avg_share_per_article: float = Field(default=0.0, description="单篇文章平均分享数。")
    avg_like_per_article: float = Field(default=0.0, description="单篇文章平均点赞数。")

    # 粉丝统计
    total_new_follow: int = Field(default=0, description="期间新增关注数。")
    total_unfollow: int = Field(default=0, description="期间流失关注数。")
    net_follow_growth: int = Field(default=0, description="期间净增关注数。")


class MediaType(str, enum.Enum):
    """素材类型枚举。"""
    IMAGE = "image"          # 图片
    VOICE = "voice"          # 音频
    VIDEO = "video"          # 视频
    THUMB = "thumb"          # 缩略图


class WeChatMedia(BaseModel):
    """微信公众号素材模型。

    对应素材管理接口（material/）返回的数据。
    """
    model_config = ConfigDict(frozen=True)

    media_id: str = Field(
        ...,
        description="素材唯一标识。用于创建草稿时引用。"
    )
    name: str = Field(
        default="",
        description="素材文件名（上传时的原始文件名）。"
    )
    type: MediaType = Field(
        ...,
        description="素材类型: image/voice/video/thumb。"
    )
    url: Optional[str] = Field(
        default=None,
        description="素材 URL。图片素材有永久链接，视频/音频素材可能为临时链接。"
    )

    # ---- 文件信息 ----
    size: int = Field(
        default=0,
        description="文件大小（字节）。"
    )
    width: Optional[int] = Field(
        default=None,
        description="图片宽度（像素）。仅图片素材有值。"
    )
    height: Optional[int] = Field(
        default=None,
        description="图片高度（像素）。仅图片素材有值。"
    )

    # ---- 时间 ----
    created_at: datetime = Field(
        ...,
        description="素材上传时间。"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="素材最后更新时间。永久素材可更新部分信息。"
    )

    # ---- 状态 ----
    is_permanent: bool = Field(
        default=True,
        description="是否为永久素材。True=永久，False=临时（临时素材 3 天后过期）。"
    )
    expired_at: Optional[datetime] = Field(
        default=None,
        description="临时素材的过期时间。永久素材为 None。"
    )


class WeChatTemporaryMedia(WeChatMedia):
    """临时素材模型（继承自 WeChatMedia）。

    临时素材有效期 3 天，过期后无法使用。
    适用于临时场景（如客服消息、被动回复）。
    """
    model_config = ConfigDict(frozen=True)

    is_permanent: bool = Field(
        default=False,
        description="标记为临时素材。"
    )
    expired_at: datetime = Field(
        ...,
        description="临时素材的过期时间。从上传时间起 3 天后。"
    )


class WeChatToken(BaseModel):
    """微信 access_token 模型。

    Token 是调用微信 API 的凭证，有效期 7200 秒（2 小时）。
    每日获取上限: 2000 次。
    """
    model_config = ConfigDict(frozen=True)

    access_token: str = Field(
        ...,
        description="接口调用凭证。用于所有需认证的微信 API 调用（作为 query 参数 access_token=...）。"
    )
    expires_in: int = Field(
        default=7200,
        description="凭证有效期（秒）。微信服务器返回的 expires_in 字段。"
    )
    acquired_at: float = Field(
        ...,
        description="获取时间的 Unix 时间戳（秒）。用于计算剩余有效期。"
    )

    # ---- 稳定模式 ----
    is_stable: bool = Field(
        default=False,
        description="是否通过稳定模式（/cgi-bin/stable_token）获取。"
                    "稳定模式的 Token 在刷新的短时间内不会改变。"
    )

    # ---- 方法 ----
    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """判断 Token 是否已过期（或即将过期）。

        参数:
            buffer_seconds: 缓冲时间（秒）。在过期前提前判定为过期，以便提前刷新。
        """
        import time
        return (time.time() - self.acquired_at) >= (self.expires_in - buffer_seconds)

    def remaining_seconds(self) -> int:
        """返回 Token 的剩余有效时间（秒）。"""
        import time
        return max(0, int(self.expires_in - (time.time() - self.acquired_at)))


class WeChatAPIError(BaseModel):
    """微信 API 错误响应模型。

    微信 API 在出错时返回的 JSON 格式:
    {"errcode": 40001, "errmsg": "invalid credential, access_token is invalid or not latest"}
    """
    model_config = ConfigDict(frozen=True)

    errcode: int = Field(
        ...,
        description="微信全局错误码。常见错误码:\n"
                    "- -1: 系统繁忙\n"
                    "- 0: 请求成功\n"
                    "- 40001: access_token 无效/过期\n"
                    "- 40002: 不合法的凭证类型\n"
                    "- 40003: 不合法的 OpenID\n"
                    "- 40004: 不合法的媒体文件类型\n"
                    "- 40005: 不合法的文件类型\n"
                    "- 40009: 图片大小超限\n"
                    "- 40013: 不合法的 AppID\n"
                    "- 40125: 不合法的 AppSecret\n"
                    "- 41001: 缺少 access_token 参数\n"
                    "- 42001: access_token 超时\n"
                    "- 45009: 接口调用超过限制\n"
                    "- 48001: 未获得 API 授权\n"
                    "- 50001: 未知错误\n"
                    "完整列表: https://developers.weixin.qq.com/doc/offiaccount/Getting_Started/Global_Return_Code.html"
    )
    errmsg: str = Field(
        ...,
        description="错误描述信息（中文）。例如 'access_token is invalid or not latest'。"
    )
    detail: Optional[str] = Field(
        default=None,
        description="详细的错误调试信息（如有）。用于定位问题。"
    )

    def is_token_error(self) -> bool:
        """判断是否为 Token 相关错误（需要刷新 Token）。"""
        return self.errcode in (40001, 40002, 40125, 42001)

    def is_rate_limit_error(self) -> bool:
        """判断是否为频率限制错误。"""
        return self.errcode == 45009

    def is_success(self) -> bool:
        """判断 API 调用是否成功。"""
        return self.errcode == 0
