# Pulsar · 脉冲星

**通用自媒体运营智能体** — 以 AI 智能体为内核，按精准节律将内容脉冲至多平台。

## 项目简介

Pulsar 是一个通用自媒体运营智能体，采用五层架构设计：

```
Layer 5: 交互层     — CLI / MCP Server / Web Dashboard
Layer 4: 执行层     — Native Tools / Platform Adapters
Layer 3: 任务管理层  — 规划器 / 调度器 / 进度追踪
Layer 2: 认知分析层  — 知识库 / 记忆系统 / RAG
Layer 1: 运行时层    — MCP Runtime / LLM Gateway / 监控
```

## Phase 1 目标

搭建五层骨架，实现「用户通过 CLI / MCP → 系统内部五层流转 → 向微信完成内容发布」的端到端链路。

## 快速开始

### 环境要求

- Python 3.11+
- pip / poetry

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd pulsar

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入微信 API 凭证
```

### 配置

编辑 `config.yaml`，配置以下关键项：

```yaml
# 微信公众平台凭证
adapters:
  wechat:
    app_id: "${WECHAT_APP_ID}"
    app_secret: "${WECHAT_APP_SECRET}"

# LLM 提供商（可选）
gateway:
  default_provider: "deepseek"
  providers:
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"
```

### 运行

```bash
# 启动 Pulsar 系统
pulsar run

# 查看系统状态
pulsar system status

# 发布文章到微信
pulsar publish wechat --title "文章标题" --content ./article.md --cover ./cover.png

# 查看微信运营数据
pulsar stats wechat --period today
```

## 项目结构

```
pulsar/
├── runtime/                  # Layer 1 - Agent Loop Runtime
│   ├── main.py               # 主入口 daemon
│   ├── mcp_bus.py            # 内部 MCP 消息总线
│   ├── lifecycle.py          # Agent 进程生命周期管理
│   ├── config.py             # 配置加载与校验
│   ├── health.py             # 健康检查端点
│   └── logging.py            # 审计日志系统
├── gateway/                  # Layer 1 - LLM Gateway
│   ├── gateway.py            # LLM 统一调用接口
│   ├── router.py             # 多模型路由
│   ├── tokens.py             # Token 计数与预算
│   └── providers/            # 模型提供商实现
├── interaction/              # Layer 5 - 交互层
│   ├── cli/                  # CLI 命令行工具
│   └── mcp_server/           # 对外 MCP Server
├── execution/                # Layer 4 - 执行层
│   ├── tools/                # 工具注册中心与内置工具
│   └── adapters/             # 平台适配器
│       └── wechat/           # 微信 MCP Adapter
├── task/                     # Layer 3 - 任务管理
│   ├── scheduler.py          # Cron 调度器
│   └── queue.py              # 任务队列
├── cognition/                # Layer 2 - 认知层
│   └── knowledge/            # 平台知识库（MD 格式）
├── shared/                   # 共享模型与工具
├── data/                     # 运行时数据目录
├── config.yaml               # 主配置文件
└── Dockerfile                # Docker 部署
```

## 外部 MCP 对接

Pulsar 对外暴露标准 MCP 接口，可与任意 MCP 兼容系统对等互联：

### Claude Code 对接

```json
// ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "pulsar": {
      "command": "pulsar",
      "args": ["mcp-server", "--transport", "stdio"]
    }
  }
}
```

### Hermes Agent 对接

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  pulsar:
    command: "pulsar"
    args: ["mcp-server", "--transport", "stdio"]
```

## 开发指南

### 运行测试

```bash
pytest tests/ -v
```

### 代码风格

项目使用 Black + isort 格式化代码，使用 mypy 进行类型检查。

## 许可证

MIT License