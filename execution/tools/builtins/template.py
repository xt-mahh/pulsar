from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template
from execution.tools.registry import tool


@tool(name="template_render", description="Jinja2 模板渲染")
async def template_render(
    template: str,
    context: dict,
    template_dir: str = None,
) -> dict:
    if template_dir:
        env = Environment(loader=FileSystemLoader(template_dir))
        tmpl = env.from_string(Path(template).read_text(encoding="utf-8") if template_dir else template)
    else:
        tmpl = Template(template)
    result = tmpl.render(**context)
    return {"content": result, "size": len(result)}