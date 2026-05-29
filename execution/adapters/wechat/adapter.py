"""微信公众平台 MCP Adapter 主类 — 对接微信公众号全部 API"""

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from execution.adapters.base import BasePlatformAdapter
from execution.adapters.wechat.auth import WeChatTokenManager
from execution.adapters.wechat.tools import ALL_WECHAT_TOOLS
from shared.models import ToolDefinition

logger = logging.getLogger("pulsar.adapter.wechat")


class WeChatAdapter(BasePlatformAdapter):
    """微信公众平台 MCP Adapter

    提供微信公众号 API 的完整封装，包括：
    - 草稿管理（创建/更新/获取/删除/列表）
    - 发布管理（提交发布/查询状态/获取详情/删除）
    - 素材管理（上传/获取/列表）
    - 评论管理（列表/精选/取消精选/删除/回复）
    - 菜单管理（创建/获取/删除）
    - 数据统计（用户/文章）
    - 用户管理（列表/信息）
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        api_base: str = "https://api.weixin.qq.com",
        token_cache_ttl: int = 7200,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base.rstrip("/")
        self.token_cache_ttl = token_cache_ttl

        self._token_manager: WeChatTokenManager = None  # type: ignore[assignment]
        self._http: httpx.AsyncClient = None  # type: ignore[assignment]
        self._initialized = False

    # ============================================================
    # BasePlatformAdapter 接口实现
    # ============================================================

    @property
    def name(self) -> str:
        return "wechat"

    @property
    def platform(self) -> str:
        return "微信公众号"

    async def initialize(self) -> bool:
        """初始化微信 Adapter

        验证 AppID 和 AppSecret 的有效性。

        Returns:
            初始化是否成功
        """
        self._http = httpx.AsyncClient(timeout=30)
        self._token_manager = WeChatTokenManager(
            app_id=self.app_id,
            app_secret=self.app_secret,
            api_base=self.api_base,
            cache_ttl=self.token_cache_ttl,
        )

        try:
            # 尝试验证凭据
            token = await self._token_manager.get_token()
            self._initialized = bool(token)
            if self._initialized:
                logger.info("微信 Adapter 初始化成功")
            else:
                logger.error("微信 Adapter 初始化失败：无法获取 access_token")
            return self._initialized
        except Exception as e:
            logger.error(f"微信 Adapter 初始化失败: {e}")
            self._initialized = False
            return False

    async def get_tools(self) -> list[ToolDefinition]:
        """返回微信 Adapter 提供的所有工具定义"""
        return ALL_WECHAT_TOOLS

    async def handle_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """处理 MCP 工具调用

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            工具执行结果
        """
        if not self._initialized:
            raise RuntimeError("微信 Adapter 未初始化，请先调用 initialize()")

        tool_map: dict[str, Any] = {
            # 草稿管理
            "wechat_draft_add": self._draft_add,
            "wechat_draft_update": self._draft_update,
            "wechat_draft_get": self._draft_get,
            "wechat_draft_delete": self._draft_delete,
            "wechat_draft_list": self._draft_list,
            # 发布管理
            "wechat_publish_submit": self._publish_submit,
            "wechat_publish_get_status": self._publish_get_status,
            "wechat_publish_get_article_detail": self._publish_get_article_detail,
            "wechat_publish_delete": self._publish_delete,
            # 素材管理
            "wechat_media_upload": self._media_upload,
            "wechat_media_upload_image": self._media_upload_image,
            "wechat_media_get": self._media_get,
            "wechat_media_list": self._media_list,
            # 评论管理
            "wechat_comment_list": self._comment_list,
            "wechat_comment_markelect": self._comment_markelect,
            "wechat_comment_unmarkelect": self._comment_unmarkelect,
            "wechat_comment_delete": self._comment_delete,
            "wechat_comment_reply": self._comment_reply,
            # 菜单管理
            "wechat_menu_create": self._menu_create,
            "wechat_menu_get": self._menu_get,
            "wechat_menu_delete": self._menu_delete,
            # 数据统计
            "wechat_stats_user_summary": self._stats_user_summary,
            "wechat_stats_user_cumulate": self._stats_user_cumulate,
            "wechat_stats_article_summary": self._stats_article_summary,
            "wechat_stats_article_total": self._stats_article_total,
            # 用户管理
            "wechat_user_get": self._user_get,
            "wechat_user_info": self._user_info,
        }

        handler = tool_map.get(name)
        if handler is None:
            raise ValueError(f"未知的微信工具: {name}")

        logger.info(f"调用微信工具: {name}")
        start_time = time.time()
        try:
            result = await handler(**args)
            duration = time.time() - start_time
            logger.info(f"微信工具 {name} 执行完成，耗时 {duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"微信工具 {name} 执行失败 ({duration:.2f}s): {e}")
            raise

    async def shutdown(self) -> None:
        """关闭 Adapter，释放资源"""
        if self._token_manager:
            await self._token_manager.close()
        if self._http:
            await self._http.aclose()
        self._initialized = False
        logger.info("微信 Adapter 已关闭")

    # ============================================================
    # 内部辅助方法
    # ============================================================

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 GET 请求到微信 API"""
        token = await self._token_manager.get_token()
        url = f"{self.api_base}{path}"
        request_params = {"access_token": token, **(params or {})}
        response = await self._http.get(url, params=request_params)
        data: dict[str, Any] = response.json()
        self._check_error(data)
        return data

    async def _post(
        self, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """发送 POST 请求到微信 API"""
        token = await self._token_manager.get_token()
        url = f"{self.api_base}{path}?access_token={token}"
        response = await self._http.post(url, json=body or {})
        data: dict[str, Any] = response.json()
        self._check_error(data)
        return data

    async def _upload(
        self, path: str, file_path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """上传文件到微信 API"""
        token = await self._token_manager.get_token()
        url = f"{self.api_base}{path}?access_token={token}"
        if params:
            url += "&" + "&".join(f"{k}={v}" for k, v in params.items())

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path_obj, "rb") as f:
            files = {"media": (file_path_obj.name, f, "application/octet-stream")}
            response = await self._http.post(url, files=files)

        data: dict[str, Any] = response.json()
        self._check_error(data)
        return data

    @staticmethod
    def _check_error(data: dict[str, Any]) -> None:
        """检查微信 API 返回的错误"""
        errcode = data.get("errcode", 0)
        if errcode != 0:
            errmsg = data.get("errmsg", "未知错误")
            raise RuntimeError(f"微信 API 错误 [{errcode}]: {errmsg}")

    # ============================================================
    # 草稿管理
    # ============================================================

    async def _draft_add(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        """创建图文草稿"""
        return await self._post("/cgi-bin/draft/add", {"articles": articles})

    async def _draft_update(
        self, media_id: str, articles: list[dict[str, Any]], index: int | None = None
    ) -> dict[str, Any]:
        """更新图文草稿"""
        body: dict[str, Any] = {"media_id": media_id, "articles": articles}
        if index is not None:
            body["index"] = index
        return await self._post("/cgi-bin/draft/update", body)

    async def _draft_get(self, media_id: str) -> dict[str, Any]:
        """获取草稿内容"""
        return await self._post("/cgi-bin/draft/get", {"media_id": media_id})

    async def _draft_delete(self, media_id: str) -> dict[str, Any]:
        """删除草稿"""
        return await self._post("/cgi-bin/draft/delete", {"media_id": media_id})

    async def _draft_list(
        self, offset: int = 0, count: int = 20, no_content: int = 0
    ) -> dict[str, Any]:
        """获取草稿列表"""
        return await self._post(
            "/cgi-bin/draft/batchget",
            {"offset": offset, "count": count, "no_content": no_content},
        )

    # ============================================================
    # 发布管理
    # ============================================================

    async def _publish_submit(self, media_id: str) -> dict[str, Any]:
        """提交发布任务"""
        return await self._post("/cgi-bin/publish/submit", {"media_id": media_id})

    async def _publish_get_status(self, publish_id: str) -> dict[str, Any]:
        """查询发布任务状态"""
        return await self._post(
            "/cgi-bin/publish/get", {"publish_id": publish_id}
        )

    async def _publish_get_article_detail(self, article_id: str) -> dict[str, Any]:
        """获取已发布文章详情"""
        return await self._post(
            "/cgi-bin/publish/get_article", {"article_id": article_id}
        )

    async def _publish_delete(
        self, article_id: str, index: int | None = None
    ) -> dict[str, Any]:
        """删除已发布文章"""
        body: dict[str, Any] = {"article_id": article_id}
        if index is not None:
            body["index"] = index
        return await self._post("/cgi-bin/publish/delete", body)

    # ============================================================
    # 素材管理
    # ============================================================

    async def _media_upload(self, file_path: str, type: str) -> dict[str, Any]:
        """上传素材"""
        return await self._upload(
            "/cgi-bin/material/add_material", file_path, {"type": type}
        )

    async def _media_upload_image(self, file_path: str) -> dict[str, Any]:
        """上传图文消息内的图片"""
        return await self._upload("/cgi-bin/media/uploadimg", file_path)

    async def _media_get(self, media_id: str) -> dict[str, Any]:
        """获取素材 URL"""
        return await self._post(
            "/cgi-bin/material/get_material", {"media_id": media_id}
        )

    async def _media_list(
        self, type: str, offset: int = 0, count: int = 20
    ) -> dict[str, Any]:
        """获取素材列表"""
        return await self._post(
            "/cgi-bin/material/batchget_material",
            {"type": type, "offset": offset, "count": count},
        )

    # ============================================================
    # 评论管理
    # ============================================================

    async def _comment_list(
        self,
        msg_data_id: str,
        index: int = 0,
        begin: int = 0,
        count: int = 50,
        type: int = 0,
    ) -> dict[str, Any]:
        """获取文章评论列表"""
        return await self._post(
            "/cgi-bin/comment/list",
            {
                "msg_data_id": msg_data_id,
                "index": index,
                "begin": begin,
                "count": count,
                "type": type,
            },
        )

    async def _comment_markelect(
        self, msg_data_id: str, comment_id: int, index: int = 0
    ) -> dict[str, Any]:
        """将评论标记为精选"""
        return await self._post(
            "/cgi-bin/comment/markelect",
            {"msg_data_id": msg_data_id, "index": index, "comment_id": comment_id},
        )

    async def _comment_unmarkelect(
        self, msg_data_id: str, comment_id: int, index: int = 0
    ) -> dict[str, Any]:
        """取消精选评论"""
        return await self._post(
            "/cgi-bin/comment/unmarkelect",
            {"msg_data_id": msg_data_id, "index": index, "comment_id": comment_id},
        )

    async def _comment_delete(
        self, msg_data_id: str, comment_id: int, index: int = 0
    ) -> dict[str, Any]:
        """删除评论"""
        return await self._post(
            "/cgi-bin/comment/delete",
            {"msg_data_id": msg_data_id, "index": index, "comment_id": comment_id},
        )

    async def _comment_reply(
        self, msg_data_id: str, comment_id: int, content: str, index: int = 0
    ) -> dict[str, Any]:
        """回复评论"""
        return await self._post(
            "/cgi-bin/comment/reply",
            {
                "msg_data_id": msg_data_id,
                "index": index,
                "comment_id": comment_id,
                "content": content,
            },
        )

    # ============================================================
    # 菜单管理
    # ============================================================

    async def _menu_create(self, button: list[dict[str, Any]]) -> dict[str, Any]:
        """创建自定义菜单"""
        return await self._post("/cgi-bin/menu/create", {"button": button})

    async def _menu_get(self) -> dict[str, Any]:
        """获取自定义菜单配置"""
        return await self._get("/cgi-bin/menu/get")

    async def _menu_delete(self) -> dict[str, Any]:
        """删除自定义菜单"""
        return await self._get("/cgi-bin/menu/delete")

    # ============================================================
    # 数据统计
    # ============================================================

    async def _stats_user_summary(
        self, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        """获取用户增减数据"""
        return await self._post(
            "/datacube/getusersummary",
            {"begin_date": begin_date, "end_date": end_date},
        )

    async def _stats_user_cumulate(
        self, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        """获取累计用户数据"""
        return await self._post(
            "/datacube/getusercumulate",
            {"begin_date": begin_date, "end_date": end_date},
        )

    async def _stats_article_summary(
        self, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        """获取图文群发每日数据"""
        return await self._post(
            "/datacube/getarticlesummary",
            {"begin_date": begin_date, "end_date": end_date},
        )

    async def _stats_article_total(
        self, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        """获取图文统计数据"""
        return await self._post(
            "/datacube/getarticletotal",
            {"begin_date": begin_date, "end_date": end_date},
        )

    # ============================================================
    # 用户管理
    # ============================================================

    async def _user_get(self, next_openid: str = "") -> dict[str, Any]:
        """获取用户列表"""
        params = {}
        if next_openid:
            params["next_openid"] = next_openid
        return await self._get("/cgi-bin/user/get", params)

    async def _user_info(self, openid: str, lang: str = "zh_CN") -> dict[str, Any]:
        """获取用户基本信息"""
        return await self._get(
            "/cgi-bin/user/info", {"openid": openid, "lang": lang}
        )