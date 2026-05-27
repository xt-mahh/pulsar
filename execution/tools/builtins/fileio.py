import json
from pathlib import Path
from execution.tools.registry import tool


@tool(name="file_read", description="读取文件内容")
async def file_read(path: str, encoding: str = "utf-8") -> dict:
    content = Path(path).read_text(encoding=encoding)
    return {"content": content, "size": len(content)}


@tool(name="file_write", description="写入文件")
async def file_write(path: str, content: str, encoding: str = "utf-8") -> dict:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return {"path": str(p.absolute()), "size": len(content)}


@tool(name="json_parse", description="JSON 解析与校验")
async def json_parse(content: str) -> dict:
    data = json.loads(content)
    return {"data": data, "valid": True}