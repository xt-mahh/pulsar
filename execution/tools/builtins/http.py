import httpx
from execution.tools.registry import tool


@tool(name="http_request", description="发送 HTTP 请求")
async def http_request(
    url: str,
    method: str = "GET",
    headers: dict = None,
    body: str = None,
    timeout: int = 30,
) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                content=body,
            )
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
    except Exception as e:
        return {
            "error": str(e),
            "status_code": 0,
            "body": "",
        }