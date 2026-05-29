# Pulsar Phase 1 Sprint 1 — 根文件详细计划

> 本文档描述项目根目录下的配置文件、入口脚本和文档。

---

## 一、文件清单

| # | 文件 | 优先级 | 用途 |
|---|------|--------|------|
| 1 | `pyproject.toml` | P0 | 项目元数据与构建配置 |
| 2 | `requirements.txt` | P0 | 精确依赖锁定 |
| 3 | `config.yaml` | P0 | 主配置文件 |
| 4 | `Dockerfile` | P1 | Docker 部署 |
| 5 | `README.md` | P1 | 项目文档 |
| 6 | `pulsar/__init__.py` | P0 | pulsar 包初始化 |
| 7 | `pulsar/__main__.py` | P0 | `python -m pulsar` 入口 |

---

## 二、`pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "pulsar"
version = "0.1.0"
description = "Pulsar · 脉冲星 — 通用自媒体运营智能体"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "Pulsar Team"},
]

dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "httpx>=0.27",
    "pydantic>=2.0",
    "loguru>=0.7",
    "aiosqlite>=0.20",
    "pyyaml>=6.0",
    "mcp>=1.0",
    "pillow>=10.0",
    "jinja2>=3.1",
]

[project.scripts]
pulsar = "interaction.cli.main:cli"

[tool.setuptools.packages.find]
include = ["pulsar*", "runtime*", "gateway*", "interaction*", "execution*", "task*", "cognition*", "shared*"]
```

---

## 三、`requirements.txt`

```
click>=8.1
rich>=13.0
httpx>=0.27
pydantic>=2.0
loguru>=0.7
aiosqlite>=0.20
pyyaml>=6.0
mcp>=1.0
pillow>=10.0
jinja2>=3.1
pytest>=8.0
pytest-asyncio>=0.23
```

---

## 四、`config.yaml`

按文档第十节完整实现，包含以下配置段：
- `system`：系统基础配置（name, version, data_dir, log_level）
- `runtime`：运行时配置（heartbeat_interval, max_restart_attempts, restart_delay, drain_timeout）
- `gateway`：LLM Gateway 配置（default_provider, fallback_provider, timeout, max_retries, providers）
- `adapters.wechat`：微信 Adapter 配置（app_id, app_secret, token_cache_ttl, api_base, rate_limit）
- `interaction`：交互层配置（cli, mcp_server）
- `scheduler`：调度器配置（enabled, jobs）
- `audit`：审计日志配置（enabled, output, path, log_levels）

---

## 五、`Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/logs data/state

EXPOSE 8910

CMD ["pulsar", "run", "--config", "config.yaml"]
```

---

## 六、`pulsar/__main__.py`

```python
"""python -m pulsar 入口"""
from interaction.cli.main import cli

if __name__ == "__main__":
    cli()
```

---

## 七、验收标准

- [ ] `pip install -e .` 可安装 pulsar 包
- [ ] `pulsar --help` 显示帮助信息
- [ ] `python -m pulsar --help` 同样有效
- [ ] `config.yaml` 配置项完整，环境变量占位符正确
- [ ] `Docker build` 成功
- [ ] `README.md` 包含安装、配置、使用说明