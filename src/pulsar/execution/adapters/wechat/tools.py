"""WeChat API tool implementations — 24 tools covering all WeChat Official Account APIs."""

import json as json_module
import logging
from typing import Any

from pulsar.execution.tools.base import BaseTool
from pulsar.execution.tools.registry import get_registry

logger = logging.getLogger(__name__)

# ── Forward reference: set by WeChatAdapter.initialize() ──────────
_adapter: Any = None


# ══════════════════════════════════════════════════════════════════════
# Base class for WeChat tools
# ══════════════════════════════════════════════════════════════════════

class WeChatBaseTool(BaseTool):
    """Base class for WeChat API tools with shared HTTP calling logic."""

    # Configured by subclasses
    wechat_path: str = ""         # e.g. "/cgi-bin/draft/add"
    http_method: str = "POST"

    async def _wechat_request(
        self,
        params: dict | None = None,
        body: Any = None,
        use_token: bool = True,
        is_multipart: bool = False,
    ) -> dict:
        """Make an authenticated HTTP request to the WeChat API.

        Args:
            params: URL query parameters (access_token is auto-added if use_token=True).
            body: Request body (dict → JSON; bytes → raw for multipart).
            use_token: Whether to attach an access_token.
            is_multipart: If True, skip JSON Content-Type header.

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: If adapter is not initialized.
            WeChatAPIError: If WeChat returns a non-zero errcode.
        """
        if _adapter is None:
            raise RuntimeError("WeChat adapter not initialized. Call WeChatAdapter.initialize() first.")

        token = await _adapter._token_manager.get_valid_token() if use_token else None

        url = f"{_adapter._base_url}{self.wechat_path}"
        query_params = dict(params or {})
        if token:
            query_params["access_token"] = token

        headers = {}
        if body is None:
            body = {}
        if isinstance(body, dict) and not is_multipart:
            headers["Content-Type"] = "application/json"
            body = json_module.dumps(body, ensure_ascii=False)

        from pulsar.execution.tools.builtins.http_tool import http_request

        result = await http_request(
            url=url,
            method=self.http_method,
            headers=headers,
            body=body,
            params=query_params,
            timeout=30,
        )

        if result["status_code"] != 200:
            raise WeChatAPIError(
                errcode=-1,
                errmsg=f"HTTP {result['status_code']}: {result.get('body', '')}",
            )

        resp_body = result["body"]
        if isinstance(resp_body, dict) and "errcode" in resp_body:
            errcode = resp_body["errcode"]
            if errcode != 0:
                raise WeChatAPIError(
                    errcode=errcode,
                    errmsg=resp_body.get("errmsg", "Unknown error"),
                )

        return resp_body if isinstance(resp_body, dict) else {"data": resp_body}


class WeChatAPIError(Exception):
    """Raised when a WeChat API call returns a non-zero error code."""

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeChat API error {errcode}: {errmsg}")


# ══════════════════════════════════════════════════════════════════════
# 1. Draft tools
# ══════════════════════════════════════════════════════════════════════

class CreateDraftTool(WeChatBaseTool):
    name = "wechat.create_draft"
    description = "Create a WeChat draft article. Supports single and multi-article (up to 8) drafts."
    wechat_path = "/cgi-bin/draft/add"
    input_schema = {
        "type": "object",
        "properties": {
            "articles": {
                "type": "array",
                "description": "Article list (1-8 articles)",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title (1-64 chars)", "maxLength": 64},
                        "author": {"type": "string", "description": "Author (1-8 chars)", "maxLength": 8},
                        "digest": {"type": "string", "description": "Summary (auto from content if empty)", "maxLength": 120},
                        "content": {"type": "string", "description": "Body HTML"},
                        "cover_media_id": {"type": "string", "description": "Cover image media_id"},
                        "need_open_comment": {"type": "integer", "enum": [0, 1], "default": 0},
                        "only_fans_can_comment": {"type": "integer", "enum": [0, 1], "default": 0},
                        "need_show_cover": {"type": "integer", "enum": [0, 1], "default": 1},
                        "content_source_url": {"type": "string", "description": "Original URL"},
                    },
                    "required": ["title", "content", "cover_media_id"],
                },
                "minItems": 1,
                "maxItems": 8,
            },
            "need_free_publish": {"type": "integer", "enum": [0, 1], "default": 0},
        },
        "required": ["articles"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        articles = kwargs["articles"]
        if len(articles) < 1 or len(articles) > 8:
            raise ValueError("articles count must be between 1 and 8")
        body = {"articles": articles}
        if "need_free_publish" in kwargs:
            body["need_free_publish"] = kwargs["need_free_publish"]
        return await self._wechat_request(body=body)


class GetDraftTool(WeChatBaseTool):
    name = "wechat.get_draft"
    description = "Get a single draft's full details by media_id."
    wechat_path = "/cgi-bin/draft/get"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id"},
        },
        "required": ["media_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string"},
            "content": {"type": "object"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"media_id": kwargs["media_id"]})


class UpdateDraftTool(WeChatBaseTool):
    name = "wechat.update_draft"
    description = "Update an existing draft by media_id."
    wechat_path = "/cgi-bin/draft/update"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id to update"},
            "index": {"type": "integer", "description": "Article index in multi-article draft (0-based)", "default": 0},
            "articles": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "digest": {"type": "string"},
                    "content": {"type": "string"},
                    "cover_media_id": {"type": "string"},
                    "need_open_comment": {"type": "integer", "enum": [0, 1]},
                    "content_source_url": {"type": "string"},
                },
            },
        },
        "required": ["media_id", "articles"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        body = {
            "media_id": kwargs["media_id"],
            "index": kwargs.get("index", 0),
            "articles": kwargs["articles"],
        }
        return await self._wechat_request(body=body)


class DeleteDraftTool(WeChatBaseTool):
    name = "wechat.delete_draft"
    description = "Delete a draft by media_id."
    wechat_path = "/cgi-bin/draft/delete"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id to delete"},
        },
        "required": ["media_id"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"media_id": kwargs["media_id"]})


class ListDraftsTool(WeChatBaseTool):
    name = "wechat.list_drafts"
    description = "List drafts with pagination (offset, count). Max count is 20."
    wechat_path = "/cgi-bin/draft/batchget"
    input_schema = {
        "type": "object",
        "properties": {
            "offset": {"type": "integer", "description": "Offset for pagination", "default": 0, "minimum": 0},
            "count": {"type": "integer", "description": "Items per page (max 20)", "default": 10, "minimum": 1, "maximum": 20},
            "no_content": {"type": "boolean", "description": "Exclude body content", "default": False},
        },
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total_count": {"type": "integer"},
            "item": {"type": "array"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        body = {
            "offset": kwargs.get("offset", 0),
            "count": kwargs.get("count", 10),
        }
        if kwargs.get("no_content"):
            body["no_content"] = 1
        return await self._wechat_request(body=body)


# ══════════════════════════════════════════════════════════════════════
# 2. Publish tools
# ══════════════════════════════════════════════════════════════════════

class PublishDraftTool(WeChatBaseTool):
    name = "wechat.publish_draft"
    description = "Submit a draft for publishing. Async operation — poll get_publish_status for result."
    wechat_path = "/cgi-bin/freepublish/submit"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id to publish"},
        },
        "required": ["media_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_id": {"type": "string", "description": "Publish task ID for status polling"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"draft_id": kwargs["media_id"]})


class DeletePublishTool(WeChatBaseTool):
    name = "wechat.delete_publish"
    description = "Delete a published article by article_id."
    wechat_path = "/cgi-bin/freepublish/delete"
    input_schema = {
        "type": "object",
        "properties": {
            "article_id": {"type": "string", "description": "Published article ID to delete"},
            "index": {"type": "integer", "description": "Article index in multi-article (0-based)", "default": 0},
        },
        "required": ["article_id"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "article_id": kwargs["article_id"],
            "index": kwargs.get("index", 0),
        })


class GetPublishStatusTool(WeChatBaseTool):
    name = "wechat.get_publish_status"
    description = "Poll the publish status of a submitted draft."
    wechat_path = "/cgi-bin/freepublish/get"
    input_schema = {
        "type": "object",
        "properties": {
            "publish_id": {"type": "string", "description": "Publish task ID from publish_draft"},
        },
        "required": ["publish_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_status": {"type": "string", "description": "0=success, 1=publishing, 2=failed"},
            "article_id": {"type": "string"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"publish_id": kwargs["publish_id"]})


class SchedulePublishTool(WeChatBaseTool):
    name = "wechat.schedule_publish"
    description = "Schedule a draft for future publishing (requires special permission)."
    wechat_path = "/cgi-bin/freepublish/submit"  # Same endpoint, schedule_time in body
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Draft media_id"},
            "schedule_time": {"type": "integer", "description": "Scheduled publish Unix timestamp"},
        },
        "required": ["media_id", "schedule_time"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_id": {"type": "string"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "draft_id": kwargs["media_id"],
            "schedule_time": kwargs["schedule_time"],
        })


class ListPublishedTool(WeChatBaseTool):
    name = "wechat.list_published"
    description = "List published articles with pagination."
    wechat_path = "/cgi-bin/freepublish/batchget"
    input_schema = {
        "type": "object",
        "properties": {
            "offset": {"type": "integer", "default": 0, "minimum": 0},
            "count": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            "no_content": {"type": "boolean", "default": False},
        },
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total_count": {"type": "integer"},
            "item": {"type": "array"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        body = {
            "offset": kwargs.get("offset", 0),
            "count": kwargs.get("count", 10),
        }
        if kwargs.get("no_content"):
            body["no_content"] = 1
        return await self._wechat_request(body=body)


class GetArticleDetailTool(WeChatBaseTool):
    name = "wechat.get_article_detail"
    description = "Get full details of a published article by article_id."
    wechat_path = "/cgi-bin/freepublish/getarticle"
    input_schema = {
        "type": "object",
        "properties": {
            "article_id": {"type": "string", "description": "Published article ID"},
        },
        "required": ["article_id"],
    }
    output_schema = {"type": "object"}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"article_id": kwargs["article_id"]})


# ══════════════════════════════════════════════════════════════════════
# 3. Material tools
# ══════════════════════════════════════════════════════════════════════

class UploadPermanentImageTool(WeChatBaseTool):
    name = "wechat.upload_permanent_image"
    description = "Upload a permanent image material. Returns media_id and public URL."
    wechat_path = "/cgi-bin/material/add_material"
    http_method = "POST"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local image file path"},
            "title": {"type": "string", "description": "Material title (required for video)", "default": ""},
            "introduction": {"type": "string", "description": "Material description", "default": ""},
        },
        "required": ["file_path"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string"},
            "url": {"type": "string", "description": "Public image URL"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        from pathlib import Path
        file_path = kwargs["file_path"]
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Build multipart upload
        import httpx
        token = await _adapter._token_manager.get_valid_token()
        url = f"{_adapter._base_url}/cgi-bin/material/add_material?access_token={token}&type=image"

        files = {"media": open(file_path, "rb")}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)

        result = response.json()
        if "errcode" in result and result["errcode"] != 0:
            raise WeChatAPIError(errcode=result["errcode"], errmsg=result.get("errmsg", ""))
        return result


class UploadPermanentAudioTool(WeChatBaseTool):
    name = "wechat.upload_permanent_audio"
    description = "Upload a permanent audio material."
    wechat_path = "/cgi-bin/material/add_material"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local audio file path"},
            "title": {"type": "string", "description": "Title"},
            "introduction": {"type": "string", "description": "Description", "default": ""},
        },
        "required": ["file_path", "title"],
    }
    output_schema = {
        "type": "object",
        "properties": {"media_id": {"type": "string"}},
    }

    async def execute(self, **kwargs) -> dict:
        import httpx
        token = await _adapter._token_manager.get_valid_token()
        url = f"{_adapter._base_url}/cgi-bin/material/add_material?access_token={token}&type=voice"
        files = {"media": open(kwargs["file_path"], "rb")}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)
        result = response.json()
        if "errcode" in result and result["errcode"] != 0:
            raise WeChatAPIError(errcode=result["errcode"], errmsg=result.get("errmsg", ""))
        return result


class UploadPermanentVideoTool(WeChatBaseTool):
    name = "wechat.upload_permanent_video"
    description = "Upload a permanent video material."
    wechat_path = "/cgi-bin/material/add_material"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local video file path"},
            "title": {"type": "string", "description": "Video title"},
            "introduction": {"type": "string", "description": "Video description", "default": ""},
        },
        "required": ["file_path", "title"],
    }
    output_schema = {
        "type": "object",
        "properties": {"media_id": {"type": "string"}, "url": {"type": "string"}},
    }

    async def execute(self, **kwargs) -> dict:
        import httpx
        token = await _adapter._token_manager.get_valid_token()
        url = f"{_adapter._base_url}/cgi-bin/material/add_material?access_token={token}&type=video"
        description = json_module.dumps({
            "title": kwargs["title"],
            "introduction": kwargs.get("introduction", ""),
        })
        files = {
            "media": open(kwargs["file_path"], "rb"),
            "description": (None, description, "application/json"),
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)
        result = response.json()
        if "errcode" in result and result["errcode"] != 0:
            raise WeChatAPIError(errcode=result["errcode"], errmsg=result.get("errmsg", ""))
        return result


class UploadPermanentThumbnailTool(WeChatBaseTool):
    name = "wechat.upload_permanent_thumbnail"
    description = "Upload a permanent thumbnail material."
    wechat_path = "/cgi-bin/material/add_material"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local thumbnail file path"},
        },
        "required": ["file_path"],
    }
    output_schema = {
        "type": "object",
        "properties": {"media_id": {"type": "string"}},
    }

    async def execute(self, **kwargs) -> dict:
        import httpx
        token = await _adapter._token_manager.get_valid_token()
        url = f"{_adapter._base_url}/cgi-bin/material/add_material?access_token={token}&type=thumb"
        files = {"media": open(kwargs["file_path"], "rb")}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)
        result = response.json()
        if "errcode" in result and result["errcode"] != 0:
            raise WeChatAPIError(errcode=result["errcode"], errmsg=result.get("errmsg", ""))
        return result


class UploadTemporaryMaterialTool(WeChatBaseTool):
    name = "wechat.upload_temporary_material"
    description = "Upload a temporary material (valid for 3 days). Supports image/voice/video/thumb."
    wechat_path = "/cgi-bin/media/upload"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local file path"},
            "type": {"type": "string", "description": "Media type", "enum": ["image", "voice", "video", "thumb"]},
        },
        "required": ["file_path", "type"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "media_id": {"type": "string"},
            "created_at": {"type": "integer"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        import httpx
        token = await _adapter._token_manager.get_valid_token()
        url = f"{_adapter._base_url}/cgi-bin/media/upload?access_token={token}&type={kwargs['type']}"
        files = {"media": open(kwargs["file_path"], "rb")}
        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files)
        result = response.json()
        if "errcode" in result and result["errcode"] != 0:
            raise WeChatAPIError(errcode=result["errcode"], errmsg=result.get("errmsg", ""))
        return result


class GetMaterialTool(WeChatBaseTool):
    name = "wechat.get_material"
    description = "Get a permanent material's details by media_id."
    wechat_path = "/cgi-bin/material/get_material"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Material media_id"},
        },
        "required": ["media_id"],
    }
    output_schema = {"type": "object"}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"media_id": kwargs["media_id"]})


class DeleteMaterialTool(WeChatBaseTool):
    name = "wechat.delete_material"
    description = "Delete a permanent material by media_id."
    wechat_path = "/cgi-bin/material/del_material"
    input_schema = {
        "type": "object",
        "properties": {
            "media_id": {"type": "string", "description": "Material media_id to delete"},
        },
        "required": ["media_id"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"media_id": kwargs["media_id"]})


class ListMaterialsTool(WeChatBaseTool):
    name = "wechat.list_materials"
    description = "List permanent materials by type with pagination."
    wechat_path = "/cgi-bin/material/batchget_material"
    input_schema = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["image", "video", "voice", "news"]},
            "offset": {"type": "integer", "default": 0, "minimum": 0},
            "count": {"type": "integer", "default": 10, "minimum": 1, "maximum": 20},
        },
        "required": ["type"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total_count": {"type": "integer"},
            "item_count": {"type": "integer"},
            "item": {"type": "array"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "type": kwargs["type"],
            "offset": kwargs.get("offset", 0),
            "count": kwargs.get("count", 10),
        })


# ══════════════════════════════════════════════════════════════════════
# 4. Statistics tools
# ══════════════════════════════════════════════════════════════════════

class GetArticleStatsTool(WeChatBaseTool):
    name = "wechat.get_article_stats"
    description = "Get per-article statistics (reads, shares, likes) for a date range."
    wechat_path = "/datacube/getarticlesummary"
    input_schema = {
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD, max 7 days from begin)"},
        },
        "required": ["begin_date", "end_date"],
    }
    output_schema = {
        "type": "object",
        "properties": {"list": {"type": "array"}},
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "begin_date": kwargs["begin_date"],
            "end_date": kwargs["end_date"],
        })


class GetOverallStatsTool(WeChatBaseTool):
    name = "wechat.get_overall_stats"
    description = "Get overall account statistics (user summary, cumulative users) for a date range."
    wechat_path = "/datacube/getusersummary"
    input_schema = {
        "type": "object",
        "properties": {
            "begin_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "end_date": {"type": "string", "description": "End date (YYYY-MM-DD, max 7 days)"},
            "metric": {
                "type": "string",
                "enum": ["user_summary", "user_cumulate", "article_total", "article_read", "article_share", "interface"],
                "default": "user_summary",
                "description": "Which statistics metric to fetch",
            },
        },
        "required": ["begin_date", "end_date"],
    }
    output_schema = {
        "type": "object",
        "properties": {"list": {"type": "array"}},
    }

    async def execute(self, **kwargs) -> dict:
        metric = kwargs.get("metric", "user_summary")
        path_map = {
            "user_summary": "/datacube/getusersummary",
            "user_cumulate": "/datacube/getusercumulate",
            "article_total": "/datacube/getarticletotal",
            "article_read": "/datacube/getuserread",
            "article_share": "/datacube/getusershare",
            "interface": "/datacube/getinterfacesummary",
        }
        self.wechat_path = path_map[metric]
        return await self._wechat_request(body={
            "begin_date": kwargs["begin_date"],
            "end_date": kwargs["end_date"],
        })


# ══════════════════════════════════════════════════════════════════════
# 5. Menu tools
# ══════════════════════════════════════════════════════════════════════

class CreateMenuTool(WeChatBaseTool):
    name = "wechat.create_menu"
    description = "Create a custom menu for the WeChat Official Account."
    wechat_path = "/cgi-bin/menu/create"
    input_schema = {
        "type": "object",
        "properties": {
            "button": {
                "type": "array",
                "description": "Menu button array (max 3 top-level, each with max 5 sub-buttons)",
                "items": {"type": "object"},
            },
        },
        "required": ["button"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={"button": kwargs["button"]})


class GetMenuTool(WeChatBaseTool):
    name = "wechat.get_menu"
    description = "Get the current custom menu configuration."
    wechat_path = "/cgi-bin/menu/get"
    http_method = "GET"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {"menu": {"type": "object"}},
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body=None)


class DeleteMenuTool(WeChatBaseTool):
    name = "wechat.delete_menu"
    description = "Delete all custom menus."
    wechat_path = "/cgi-bin/menu/delete"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "errmsg": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={})


class CreateConditionalMenuTool(WeChatBaseTool):
    name = "wechat.create_conditional_menu"
    description = "Create a personalized conditional menu based on match rules."
    wechat_path = "/cgi-bin/menu/addconditional"
    input_schema = {
        "type": "object",
        "properties": {
            "button": {"type": "array", "description": "Menu buttons"},
            "matchrule": {"type": "object", "description": "Matching rules (sex, region, tag, etc.)"},
        },
        "required": ["button", "matchrule"],
    }
    output_schema = {"type": "object", "properties": {"menuid": {"type": "string"}}}

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "button": kwargs["button"],
            "matchrule": kwargs["matchrule"],
        })


# ══════════════════════════════════════════════════════════════════════
# 6. User management tools
# ══════════════════════════════════════════════════════════════════════

class GetUserInfoTool(WeChatBaseTool):
    name = "wechat.get_user_info"
    description = "Get a user's basic info by OpenID."
    wechat_path = "/cgi-bin/user/info"
    http_method = "GET"
    input_schema = {
        "type": "object",
        "properties": {
            "openid": {"type": "string", "description": "User's OpenID"},
            "lang": {"type": "string", "enum": ["zh_CN", "zh_TW", "en"], "default": "zh_CN"},
        },
        "required": ["openid"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "subscribe": {"type": "integer"},
            "openid": {"type": "string"},
            "nickname": {"type": "string"},
            "headimgurl": {"type": "string"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(
            params={
                "openid": kwargs["openid"],
                "lang": kwargs.get("lang", "zh_CN"),
            },
            body=None,
        )


class GetFollowersTool(WeChatBaseTool):
    name = "wechat.get_followers"
    description = "Get the list of followers (paginated, max 10,000 per call)."
    wechat_path = "/cgi-bin/user/get"
    http_method = "GET"
    input_schema = {
        "type": "object",
        "properties": {
            "next_openid": {
                "type": "string",
                "description": "Next OpenID for pagination (empty = start from beginning)",
                "default": "",
            },
        },
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "count": {"type": "integer"},
            "data": {"type": "object"},
            "next_openid": {"type": "string"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        params = {}
        if kwargs.get("next_openid"):
            params["next_openid"] = kwargs["next_openid"]
        return await self._wechat_request(params=params, body=None)


# ══════════════════════════════════════════════════════════════════════
# 7. Comment tools
# ══════════════════════════════════════════════════════════════════════

class GetCommentListTool(WeChatBaseTool):
    name = "wechat.get_comment_list"
    description = "Get the comment list for a published article."
    wechat_path = "/cgi-bin/comment/list"
    input_schema = {
        "type": "object",
        "properties": {
            "msg_data_id": {"type": "string", "description": "Message data ID"},
            "index": {"type": "integer", "description": "Article index (0-based)", "default": 0},
            "begin": {"type": "integer", "description": "Start offset", "default": 0},
            "count": {"type": "integer", "description": "Number to fetch (max 50)", "default": 10},
            "type": {"type": "integer", "enum": [0, 1], "description": "0=all, 1=selected", "default": 0},
        },
        "required": ["msg_data_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "comment": {"type": "array"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body={
            "msg_data_id": kwargs["msg_data_id"],
            "index": kwargs.get("index", 0),
            "begin": kwargs.get("begin", 0),
            "count": kwargs.get("count", 10),
            "type": kwargs.get("type", 0),
        })


# ══════════════════════════════════════════════════════════════════════
# 8. Tag tools
# ══════════════════════════════════════════════════════════════════════

class GetFanTagsTool(WeChatBaseTool):
    name = "wechat.get_fan_tags"
    description = "Get the list of all fan tags for the account."
    wechat_path = "/cgi-bin/tags/get"
    http_method = "GET"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {"tags": {"type": "array"}},
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body=None)


# ══════════════════════════════════════════════════════════════════════
# 9. Auto-reply tools
# ══════════════════════════════════════════════════════════════════════

class GetAutoReplyRulesTool(WeChatBaseTool):
    name = "wechat.get_auto_reply_rules"
    description = "Get the current auto-reply rules configuration."
    wechat_path = "/cgi-bin/get_current_autoreply_info"
    http_method = "GET"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "is_add_friend_reply_open": {"type": "integer"},
            "is_autoreply_open": {"type": "integer"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        return await self._wechat_request(body=None)


# ══════════════════════════════════════════════════════════════════════
# 10. Message tools
# ══════════════════════════════════════════════════════════════════════

class SendTemplateMessageTool(WeChatBaseTool):
    name = "wechat.send_template_message"
    description = "Send a template message to a user. Requires an approved template."
    wechat_path = "/cgi-bin/message/template/send"
    input_schema = {
        "type": "object",
        "properties": {
            "touser": {"type": "string", "description": "Recipient's OpenID"},
            "template_id": {"type": "string", "description": "Template ID"},
            "data": {"type": "object", "description": "Template data key-value pairs"},
            "url": {"type": "string", "description": "Click-through URL (optional)", "default": ""},
            "miniprogram": {"type": "object", "description": "Mini-program link (optional)"},
        },
        "required": ["touser", "template_id", "data"],
    }
    output_schema = {"type": "object", "properties": {"errcode": {"type": "integer"}, "msgid": {"type": "integer"}}}

    async def execute(self, **kwargs) -> dict:
        body = {
            "touser": kwargs["touser"],
            "template_id": kwargs["template_id"],
            "data": kwargs["data"],
        }
        if kwargs.get("url"):
            body["url"] = kwargs["url"]
        if kwargs.get("miniprogram"):
            body["miniprogram"] = kwargs["miniprogram"]
        return await self._wechat_request(body=body)


# ══════════════════════════════════════════════════════════════════════
# 11. QR code tool
# ══════════════════════════════════════════════════════════════════════

class CreateQRCodeTool(WeChatBaseTool):
    name = "wechat.create_qr_code"
    description = "Create a QR code (temporary or permanent) for the account."
    wechat_path = "/cgi-bin/qrcode/create"
    input_schema = {
        "type": "object",
        "properties": {
            "action_name": {
                "type": "string",
                "enum": ["QR_SCENE", "QR_STR_SCENE", "QR_LIMIT_SCENE", "QR_LIMIT_STR_SCENE"],
                "description": "QR code type",
            },
            "action_info": {"type": "object", "description": "Scene value info"},
            "expire_seconds": {
                "type": "integer",
                "description": "Expiry in seconds (max 2592000=30d, for temp codes)",
                "default": 604800,
            },
        },
        "required": ["action_name", "action_info"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "ticket": {"type": "string"},
            "expire_seconds": {"type": "integer"},
            "url": {"type": "string"},
        },
    }

    async def execute(self, **kwargs) -> dict:
        body = {
            "action_name": kwargs["action_name"],
            "action_info": kwargs["action_info"],
        }
        if kwargs.get("expire_seconds"):
            body["expire_seconds"] = kwargs["expire_seconds"]
        return await self._wechat_request(body=body)


# ══════════════════════════════════════════════════════════════════════
# Tool registry helpers
# ══════════════════════════════════════════════════════════════════════

ALL_WECHAT_TOOLS: list[BaseTool] = [
    # Draft
    CreateDraftTool(),
    GetDraftTool(),
    UpdateDraftTool(),
    DeleteDraftTool(),
    ListDraftsTool(),
    # Publish
    PublishDraftTool(),
    DeletePublishTool(),
    GetPublishStatusTool(),
    SchedulePublishTool(),
    ListPublishedTool(),
    GetArticleDetailTool(),
    # Material
    UploadPermanentImageTool(),
    UploadPermanentAudioTool(),
    UploadPermanentVideoTool(),
    UploadPermanentThumbnailTool(),
    UploadTemporaryMaterialTool(),
    GetMaterialTool(),
    DeleteMaterialTool(),
    ListMaterialsTool(),
    # Stats
    GetArticleStatsTool(),
    GetOverallStatsTool(),
    # Menu
    CreateMenuTool(),
    GetMenuTool(),
    DeleteMenuTool(),
    CreateConditionalMenuTool(),
    # User
    GetUserInfoTool(),
    GetFollowersTool(),
    # Comment
    GetCommentListTool(),
    # Tags
    GetFanTagsTool(),
    # Auto-reply
    GetAutoReplyRulesTool(),
    # Message
    SendTemplateMessageTool(),
    # QR Code
    CreateQRCodeTool(),
]


def register_all_wechat_tools(registry=None) -> list[BaseTool]:
    """Register all WeChat tools into the given registry (or global default)."""
    if registry is None:
        from pulsar.execution.tools.registry import get_registry
        registry = get_registry()

    for tool_instance in ALL_WECHAT_TOOLS:
        try:
            registry.register(tool_instance)
        except ValueError:
            logger.debug("Tool '%s' already registered, skipping", tool_instance.name)

    return ALL_WECHAT_TOOLS


def set_adapter(adapter: Any) -> None:
    """Set the global adapter reference used by all WeChat tools."""
    global _adapter
    _adapter = adapter
