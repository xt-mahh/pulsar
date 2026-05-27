# Pulsar · 脉冲星

通用自媒体运营智能体 — 以 AI 智能体为内核，按精准节律将内容脉冲至多平台。

## 架构概览

```
interaction/  ← Layer 5: CLI + MCP Server
execution/    ← Layer 4: Tools + Platform Adapters
task/         ← Layer 3: Task Queue + Scheduler
cognition/    ← Layer 2: Knowledge Base
runtime/      ← Layer 1: Agent Loop Runtime + LLM Gateway
```

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置

复制并编辑 `config.yaml`，设置环境变量：

```bash
export WECHAT_APP_ID="your_app_id"
export WECHAT_APP_SECRET="your_app_secret"
export DEEPSEEK_API_KEY="your_api_key"
```

### 使用

```bash
# 启动守护进程
python -m runtime.main run

# 发布文章到微信公众号
python -m interaction.cli.main publish wechat --title "今日 AI 快讯" --content ./article.md

# 查看草稿列表
python -m interaction.cli.main draft list wechat

# 查看运营数据
python -m interaction.cli.main stats wechat --period yesterday

# 启动 MCP Server (供 Claude Code 等外部 Agent 调用)
python -m interaction.mcp_server.server
```

### 作为 MCP Server 接入

在 `~/.claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "pulsar": {
      "command": "python",
      "args": ["-m", "interaction.mcp_server.server"]
    }
  }
}
```

## Docker 部署

```bash
docker build -t pulsar .
docker run -e WECHAT_APP_ID=xxx -e WECHAT_APP_SECRET=xxx pulsar
```

## 项目结构

| 目录 | 层 | 职责 |
|------|----|------|
| `runtime/` | L1 | Agent 生命周期管理、MCP 消息总线、审计日志 |
| `gateway/` | L1 | LLM 统一网关、多模型路由 |
| `cognition/` | L2 | 各平台知识库 (Markdown) |
| `task/` | L3 | 任务队列、Cron 调度器 |
| `execution/` | L4 | Tool 注册中心、平台 MCP Adapter |
| `interaction/` | L5 | CLI 命令行、对外 MCP Server |
| `shared/` | - | 核心数据模型、错误类型、常量 |