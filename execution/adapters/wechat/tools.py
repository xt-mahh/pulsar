import re
import httpx
from typing import Optional
from execution.adapters.wechat.auth import WeChatTokenManager


_wechat_token_manager: Optional[WeChatTokenManager] = None


def _init_tm(app_id: str, app_secret: str, api_base: str = "https://api.weixin.qq.com", cache_ttl: int = 7200):
    global _wechat_token_manager
    if _wechat_token_manager is None:
        _wechat_token_manager = WeChatTokenManager(app_id, app_secret, api_base, cache_ttl)
    return _wechat_token_manager


def _get_tm() -> WeChatTokenManager:
    if _wechat_token_manager is None:
        raise RuntimeError("WeChatTokenManager not initialized. Call init first.")
    return _wechat_token_manager


async def _wechat_post(path: str, data: dict = None, params: dict = None) -> dict:
    tm = _get_tm()
    token = await tm.get_token()
    url = f"{tm.api_base}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, params={"access_token": token, **(params or {})}, json=data)
        result = resp.json()
        if "errcode" in result and result["errcode"] != 0:
            raise Exception(f"WeChat API error [{result['errcode']}]: {result.get('errmsg', '')}")
        return result


async def _wechat_get(path: str, params: dict = None) -> dict:
    tm = _get_tm()
    token = await tm.get_token()
    url = f"{tm.api_base}{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={"access_token": token, **(params or {})})
        result = resp.json()
        if "errcode" in result and result["errcode"] != 0:
            raise Exception(f"WeChat API error [{result['errcode']}]: {result.get('errmsg', '')}")
        return result


async def wechat_draft_add(articles: list) -> dict:
    return await _wechat_post("/cgi-bin/draft/add", {"articles": articles})


async def wechat_draft_list(offset: int = 0, count: int = 20, no_content: int = 0) -> dict:
    return await _wechat_post("/cgi-bin/draft/batchget", {"offset": offset, "count": count, "no_content": no_content})


async def wechat_draft_get(media_id: str) -> dict:
    return await _wechat_post("/cgi-bin/draft/get", {"media_id": media_id})


async def wechat_draft_delete(media_id: str) -> dict:
    return await _wechat_post("/cgi-bin/draft/delete", {"media_id": media_id})


async def wechat_publish_submit(media_id: str) -> dict:
    return await _wechat_post("/cgi-bin/freepublish/submit", {"media_id": media_id})


async def wechat_publish_status(publish_id: str) -> dict:
    return await _wechat_post("/cgi-bin/freepublish/get", {"publish_id": publish_id})


async def wechat_publish_list(offset: int = 0, count: int = 20, no_content: int = 0) -> dict:
    return await _wechat_post("/cgi-bin/freepublish/batchget", {"offset": offset, "count": count, "no_content": no_content})


async def wechat_upload_image(file_path: str) -> dict:
    tm = _get_tm()
    token = await tm.get_token()
    url = f"{tm.api_base}/cgi-bin/media/uploadimg?access_token={token}"
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {"media": f}
            resp = await client.post(url, files=files)
        result = resp.json()
        return result


async def wechat_upload_media(file_path: str, media_type: str = "image") -> dict:
    tm = _get_tm()
    token = await tm.get_token()
    url = f"{tm.api_base}/cgi-bin/material/add_material?access_token={token}&type={media_type}"
    async with httpx.AsyncClient() as client:
        with open(file_path, "rb") as f:
            files = {"media": f}
            resp = await client.post(url, files=files)
        result = resp.json()
        if "errcode" in result and result["errcode"] != 0:
            raise Exception(f"WeChat API error [{result['errcode']}]: {result.get('errmsg', '')}")
        return result


async def wechat_stats_user_summary(begin_date: str, end_date: str) -> dict:
    return await _wechat_post("/datacube/getusersummary", {"begin_date": begin_date, "end_date": end_date})


async def wechat_stats_user_cumulate(begin_date: str, end_date: str) -> dict:
    return await _wechat_post("/datacube/getusercumulate", {"begin_date": begin_date, "end_date": end_date})


async def wechat_stats_article_summary(begin_date: str, end_date: str) -> dict:
    return await _wechat_post("/datacube/getarticlesummary", {"begin_date": begin_date, "end_date": end_date})


async def wechat_stats_article_total(begin_date: str, end_date: str) -> dict:
    return await _wechat_post("/datacube/getarticletotal", {"begin_date": begin_date, "end_date": end_date})


async def wechat_comment_open(msg_data_id: int, index: int = 0) -> dict:
    return await _wechat_post("/cgi-bin/comment/open", {"msg_data_id": msg_data_id, "index": index})


async def wechat_comment_list(msg_data_id: int, index: int = 0, begin: int = 0, count: int = 50, type: int = 0) -> dict:
    return await _wechat_post("/cgi-bin/comment/list", {
        "msg_data_id": msg_data_id, "index": index, "begin": begin, "count": count, "type": type
    })


async def wechat_comment_reply(msg_data_id: int, index: int, user_comment_id: int, content: str) -> dict:
    return await _wechat_post("/cgi-bin/comment/reply", {
        "msg_data_id": msg_data_id, "index": index, "user_comment_id": user_comment_id, "content": content
    })


async def wechat_comment_markelect(msg_data_id: int, index: int, user_comment_id: int) -> dict:
    return await _wechat_post("/cgi-bin/comment/markelect", {
        "msg_data_id": msg_data_id, "index": index, "user_comment_id": user_comment_id
    })


async def wechat_menu_create(menus: dict) -> dict:
    return await _wechat_post("/cgi-bin/menu/create", menus)


async def wechat_menu_get() -> dict:
    return await _wechat_get("/cgi-bin/menu/get")


async def wechat_menu_delete() -> dict:
    return await _wechat_get("/cgi-bin/menu/delete")


async def wechat_user_list(next_openid: str = "") -> dict:
    return await _wechat_get("/cgi-bin/user/get", {"next_openid": next_openid})


async def wechat_user_info(openid: str, lang: str = "zh_CN") -> dict:
    return await _wechat_get("/cgi-bin/user/info", {"openid": openid, "lang": lang})


def extract_image_urls(content: str) -> list[str]:
    pattern = r'<img[^>]+src=["\'](https?://[^"\']+)["\']'
    return re.findall(pattern, content)


async def publish_article(
    title: str, content: str, author: str = "Pulsar",
    digest: str = "", thumb_media_id: str = "",
    need_open_comment: bool = True, need_publish: bool = True
) -> dict:
    image_urls = extract_image_urls(content)
    for old_url in image_urls:
        try:
            wechat_result = await wechat_upload_image(old_url)
            wechat_url = wechat_result.get("url", old_url)
            content = content.replace(old_url, wechat_url)
        except Exception:
            pass

    draft = await wechat_draft_add([{
        "title": title[:32],
        "author": author[:16],
        "digest": digest[:128],
        "content": content,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1 if need_open_comment else 0,
    }])

    if need_publish:
        publish_result = await wechat_publish_submit(draft["media_id"])
        return {"draft": draft, "publish": publish_result}

    return {"draft": draft}