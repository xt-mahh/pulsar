# Layer 2 — 认知分析层 (Cognition Layer)

## 概述

Layer 2 认知分析层是 Pulsar 的 **AI 推理引擎**，负责理解用户自然语言输入、管理多轮对话状态、生成目标平台内容，并维护结构化与非结构化的知识库。该层是系统智能化的核心，连接用户意图到具体执行动作。

Layer 2 由四个核心组件构成，所有组件之间通过 **PIP 协议**（Pulsar Internal Protocol）进行异步通信：

| 组件 | 职责 | 调用方 / 被调用方 |
|------|------|-------------------|
| **Intent Recognition** | 意图识别与实体抽取 | 被 Layer 5 ConversationAgent 调用 |
| **Dialogue Manager** | 多轮对话状态管理 | 被 Intent Recognition 调用 |
| **Content Generator** | 内容生成与格式适配 | 被 Dialogue Manager 调用 |
| **Knowledge Store** | 知识文件存储与检索 | 被所有组件调用 |

---

## 1. Intent Recognition（意图识别）

### 职责

接收用户自然语言输入，将其分类为预定义的意图类型，并从中提取结构化实体信息。该组件是系统的"入口"——所有用户请求首先经过意图识别。

### 调用链

```
Layer 5 ConversationAgent
    │  PIP Request: 用户原始文本
    ▼
Layer 2 Intent Recognition
    │  输出: Intent { type, entities, confidence }
    ▼
Layer 2 Dialogue Manager (下一步)
```

### 意图分类体系

| 意图类型 | 枚举值 | 示例用户输入 |
|----------|--------|-------------|
| 内容发布 | `PUBLISH` | "帮我把这篇科普发到公众号" |
| 内容查询 | `QUERY` | "上周发了哪些文章？" |
| 系统管理 | `MANAGE` | "帮我检查微信API配额" |
| 对话澄清 | `CLARIFY` | "（用户反问或确认）" |
| 取消 | `CANCEL` | "算了，不发了" |

### 实体抽取

除意图外，同时从输入中抽取关键实体：

| 实体 | 说明 | 示例 |
|------|------|------|
| `platform` | 目标平台 | `wechat`, `xiaohongshu` |
| `time` | 时间相关 | `2026-05-30`, `上周`, `今天` |
| `topic` | 内容主题 | `AI`, `量子计算`, `养生` |
| `style` | 写作风格 | `科普`, `专业`, `技术` |
| `action` | 具体操作 | `发布`, `预览`, `删除` |

### PIP 通信协议

```
--- PIP Request (Layer 5 → Layer 2 Intent Recognition) ---
{
  "from": "conversation_agent",
  "to": "intent_recognition",
  "method": "classify",
  "payload": {
    "text": "帮我把这篇科普发到公众号",
    "context": { "session_id": "sess_abc123", "turn": 5 }
  },
  "id": "pip_req_001"
}

--- PIP Response (Layer 2 → Layer 5) ---
{
  "from": "intent_recognition",
  "to": "conversation_agent",
  "method": "classify",
  "status": "ok",
  "payload": {
    "intent": {
      "type": "PUBLISH",
      "confidence": 0.94
    },
    "entities": {
      "platform": "wechat",
      "style": "科普",
      "time": null
    }
  },
  "id": "pip_resp_001"
}
```

### 伪代码实现

```python
# cognition/intent_recognition.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IntentType(str, Enum):
    PUBLISH = "PUBLISH"
    QUERY = "QUERY"
    MANAGE = "MANAGE"
    CLARIFY = "CLARIFY"
    CANCEL = "CANCEL"


@dataclass
class Entity:
    platform: Optional[str] = None
    time: Optional[str] = None
    topic: Optional[str] = None
    style: Optional[str] = None
    action: Optional[str] = None


@dataclass
class Intent:
    type: IntentType
    confidence: float
    entities: Entity = field(default_factory=Entity)
    raw_text: str = ""


class IntentRecognizer:
    """
    意图识别器。
    在 Phase 1 中使用规则 + 关键词匹配；
    在 Phase 2 中升级为小模型分类器（如 BERT-based classifier）。
    """

    def __init__(self, knowledge_store=None):
        self.knowledge_store = knowledge_store

    async def classify(self, text: str, context: dict = None) -> Intent:
        """
        接收用户输入文本，返回结构化 Intent 对象。

        通过 PIP 协议被 Layer 5 ConversationAgent 调用。
        """
        # Phase 1: 规则匹配
        intent_type = self._match_intent(text)
        entities = self._extract_entities(text)

        return Intent(
            type=intent_type,
            confidence=0.85,
            entities=entities,
            raw_text=text,
        )

    def _match_intent(self, text: str) -> IntentType:
        """关键词与模式匹配，返回意图类型。"""
        publish_keywords = ["发布", "发到", "发表", "推送"]
        query_keywords = ["查询", "查一下", "看看", "统计", "上周"]
        manage_keywords = ["检查", "配置", "管理", "配额", "设置"]

        for kw in publish_keywords:
            if kw in text:
                return IntentType.PUBLISH
        for kw in query_keywords:
            if kw in text:
                return IntentType.QUERY
        for kw in manage_keywords:
            if kw in text:
                return IntentType.MANAGE
        return IntentType.CLARIFY

    def _extract_entities(self, text: str) -> Entity:
        """从文本中抽取实体。"""
        entity = Entity()
        platforms = {"公众号": "wechat", "小红书": "xiaohongshu", "微博": "weibo"}
        styles = {"科普": "科普", "专业": "专业", "技术": "技术"}

        for keyword, value in platforms.items():
            if keyword in text:
                entity.platform = value
                break
        for keyword, value in styles.items():
            if keyword in text:
                entity.style = value
                break

        return entity
```

---

## 2. Dialogue Manager（对话管理器）

### 职责

维护多轮对话的全局状态，管理上下文窗口，处理用户的澄清与确认流程。在 Phase 1 中为内存状态，Phase 2 将引入持久化存储。

### 核心功能

| 功能 | 说明 |
|------|------|
| **会话状态维护** | 追踪当前会话的意图链、已确认实体、待完成动作 |
| **上下文窗口** | 管理 Token 窗口，滑动丢弃过期或冗余上下文 |
| **澄清循环** | 当意图置信度低或缺少必需实体时，主动向用户提问 |
| **确认循环** | 在执行关键操作前，请求用户二次确认 |
| **状态快照** | 支持对话状态序列化与恢复（Phase 2 持久化） |

### 状态数据结构

```python
@dataclass
class DialogueState:
    session_id: str
    turn: int
    current_intent: Optional[Intent] = None
    confirmed_entities: Entity = field(default_factory=Entity)
    pending_clarifications: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    context_window: list[dict] = field(default_factory=list)
    max_context_tokens: int = 4096
```

### 典型对话流程

```
User: "帮我把这篇科普发到公众号"
  → Intent: PUBLISH, entities: {platform: wechat, style: 科普}
  → Dialogue Manager: 缺少 topic 实体
  → Response: "请问这篇科普的主题是什么？"

User: "关于AI在医疗中的应用"
  → Intent: CLARIFY, entities: {topic: AI医疗}
  → Dialogue Manager: 所有必需实体已齐
  → 提交 Content Generator 生成内容
  → Response: "已为您生成AI医疗科普文章，确认发布到公众号吗？"

User: "确认发布"
  → Intent: PUBLISH, confidence: high
  → Dialogue Manager: 锁定状态，提交发布任务
```

### 伪代码实现

```python
# cognition/dialogue_manager.py

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DialogueState:
    session_id: str
    turn: int = 0
    current_intent: Optional[Intent] = None
    confirmed_entities: Entity = field(default_factory=Entity)
    pending_clarifications: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    context_window: list[dict] = field(default_factory=list)
    max_context_tokens: int = 4096


class DialogueManager:
    """
    管理多轮对话状态与流程。
    所有会话状态存储在内存中（Phase 1），后续迁移至 Redis 或 SQLite。
    使用 OrderedDict 实现的 LRU 缓存，上限 max_sessions=1000，TTL=1800s。
    """

    def __init__(self, max_sessions: int = 1000, ttl_seconds: int = 1800):
        from collections import OrderedDict
        import time

        self.sessions: OrderedDict[str, tuple[DialogueState, float]] = OrderedDict()
        self.max_sessions = max_sessions
        self.ttl_seconds = ttl_seconds

    def _evict_expired(self) -> None:
        """清除所有过期的会话。"""
        now = time.time()
        expired_ids = [
            sid for sid, (_, ts) in self.sessions.items()
            if now - ts > self.ttl_seconds
        ]
        for sid in expired_ids:
            del self.sessions[sid]

    def _evict_lru_if_needed(self) -> None:
        """如果会话数超过上限，淘汰最久未访问的会话。"""
        while len(self.sessions) > self.max_sessions:
            self.sessions.popitem(last=False)  # 淘汰最早插入的

    def _touch(self, session_id: str) -> None:
        """将 session 移到 OrderedDict 末尾（最近访问）。"""
        state, _ = self.sessions.pop(session_id)
        self.sessions[session_id] = (state, time.time())

    async def process_intent(self, intent: Intent, session_id: str) -> dict:
        """
        接收 Intent Recognition 的输出，更新对话状态，
        返回系统响应（继续澄清、确认或转交 Content Generator）。
        """
        state = self._get_or_create_session(session_id)
        state.turn += 1
        state.current_intent = intent

        # 检查是否缺少必需实体
        missing = self._check_required_entities(intent)
        if missing:
            state.pending_clarifications = missing
            return self._build_clarification_response(missing)

        # 检查是否需要确认（如发布操作）
        if intent.type == IntentType.PUBLISH:
            return self._build_confirmation_prompt(state)

        # 实体齐全 → 转交 Content Generator
        return await self._delegate_to_generator(intent, state)

    def _get_or_create_session(self, session_id: str) -> DialogueState:
        self._evict_expired()

        if session_id in self.sessions:
            state, _ = self.sessions[session_id]
            self._touch(session_id)
            return state

        # 创建新会话前检查容量
        self._evict_lru_if_needed()

        state = DialogueState(session_id=session_id)
        self.sessions[session_id] = (state, time.time())
        return state

    def _check_required_entities(self, intent: Intent) -> list[str]:
        """检查当前意图是否缺少必需实体。"""
        missing = []
        if intent.type == IntentType.PUBLISH:
            if not intent.entities.platform:
                missing.append("platform")
            if not intent.entities.topic:
                missing.append("topic")
        return missing

    def _build_clarification_response(self, missing: list[str]) -> dict:
        """构建澄清问题的响应。"""
        questions = {
            "platform": "请问您想发布到哪个平台？（公众号 / 小红书）",
            "topic": "请问内容主题是什么？",
            "style": "请问希望用什么风格？（科普 / 专业 / 技术）",
        }
        return {
            "type": "clarification",
            "questions": [questions[m] for m in missing if m in questions],
        }

    def _build_confirmation_prompt(self, state: DialogueState) -> dict:
        return {
            "type": "confirmation",
            "message": (
                f"即将发布一篇关于「{state.confirmed_entities.topic}」的"
                f"{state.confirmed_entities.style}风格文章到"
                f"{state.confirmed_entities.platform}。确认发布？"
            ),
        }

    async def _delegate_to_generator(self, intent: Intent, state: DialogueState) -> dict:
        """转交 Content Generator 处理。"""
        # 通过 PIP 调用 Content Generator
        return {
            "type": "generation",
            "action": "generate_content",
            "intent": intent,
        }
```

---

## 3. Content Generator（内容生成器）

### 职责

根据意图识别结果和写作风格，构建 Prompt 并调用 LLM Gateway 生成内容，最终格式化为目标平台适配的发布格式。

### 工作流程

```
Intent + Style
    │
    ▼
Knowledge Store ──► 获取风格规则 + 平台限制
    │
    ▼
Prompt Builder ──► 构建系统 Prompt + 用户 Prompt
    │
    ▼
LLM Gateway ──► 调用大模型（GPT / Claude / 本地模型）
    │
    ▼
Format Adapter ──► 按平台规则格式化输出
    │
    ▼
Quality Validator ──► 长度、敏感词、格式校验
    │
    ▼
PIP Response 返回至 Dialogue Manager
```

### 风格管理 (Style Management)

| 风格 | 适用场景 | 说明 |
|------|---------|------|
| `科普` | 大众科普公众号 | 通俗易懂，使用比喻，减少术语 |
| `专业` | 行业分析报告 | 数据驱动，引用文献，专业术语 |
| `技术` | 开发者博客 | 代码示例，架构图，技术细节 |

### 模板系统 (Template System)

每个风格对应一组 Prompt 模板，存储在 Knowledge Store 中：

```yaml
# cognition/knowledge/templates/科普.yaml
---
id: template_科普
style: 科普
system_prompt: |
  你是一个资深的科普作家。请用通俗易懂的语言，
  通过生活化的比喻和案例向大众解释复杂概念。
  限制：不使用超过3个专业术语而不解释。
  结构：引入 → 解释 → 案例 → 总结。
---
```

### 伪代码实现

```python
# cognition/content_generator.py

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerationRequest:
    intent: Intent
    style: str = "科普"
    platform: str = "wechat"
    user_context: str = ""


@dataclass
class GenerationResult:
    content: str
    title: str
    platform: str
    validated: bool
    validation_errors: list[str] = field(default_factory=list)


class ContentGenerator:
    """
    内容生成器。
    通过 PIP 接收 Dialogue Manager 的生成请求，
    调用 LLM Gateway，格式化输出，返回生成结果。
    """

    def __init__(self, knowledge_store=None, llm_gateway=None):
        self.knowledge_store = knowledge_store
        self.llm_gateway = llm_gateway  # LLM Gateway (Layer 1 Runtime)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        主入口：根据意图和风格生成内容。
        """
        # 1. 从 Knowledge Store 获取风格模板
        style_config = await self.knowledge_store.get_style(request.style)
        platform_rules = await self.knowledge_store.get_platform_rules(
            request.platform
        )

        # 2. 构建 Prompt
        prompt = self._build_prompt(request, style_config)

        # 3. 调用 LLM Gateway
        raw_output = await self.llm_gateway.chat(
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            temperature=style_config.get("temperature", 0.7),
        )

        # 4. 格式化输出
        formatted = self._format_output(raw_output, platform_rules)

        # 5. 质量校验
        validated, errors = self._validate(formatted, platform_rules)

        return GenerationResult(
            content=formatted["body"],
            title=formatted["title"],
            platform=request.platform,
            validated=validated,
            validation_errors=errors,
        )

    def _build_prompt(self, request: GenerationRequest, style_config: dict) -> dict:
        """构建系统 Prompt 和用户 Prompt。"""
        return {
            "system": style_config.get("system_prompt", ""),
            "user": (
                f"请写一篇关于「{request.intent.entities.topic}」的"
                f"{style_config.get('style_label', request.style)}风格文章。\n"
                f"目标平台：{request.platform}\n"
                f"额外要求：{request.user_context or '无'}"
            ),
        }

    def _format_output(self, raw: str, rules: dict) -> dict:
        """按平台规则分割标题和正文。"""
        lines = raw.strip().split("\n", 1)
        title = lines[0].replace("# ", "").strip()
        body = lines[1] if len(lines) > 1 else raw

        # 裁剪到平台允许的最大长度
        max_len = rules.get("max_body_length", 20000)
        if len(body) > max_len:
            body = body[:max_len]

        return {"title": title, "body": body}

    def _validate(self, formatted: dict, rules: dict) -> tuple[bool, list[str]]:
        """质量校验：长度、敏感词、格式。"""
        errors = []
        if len(formatted["title"]) > rules.get("max_title_length", 32):
            errors.append(f"标题超长 ({len(formatted['title'])} > {rules.get('max_title_length', 32)})")
        # Phase 2: 接入敏感词检测
        return len(errors) == 0, errors
```

---

## 4. Knowledge Store（知识存储）

*（保留原 Layer 2 的知识管理能力，作为 Cognition Layer 的子组件。）*

### 概述

知识存储是 Layer 2 的知识底座，为 Intent Recognition、Dialogue Manager、Content Generator 提供平台规则、写作风格模板、最佳实践等参考信息。

### 存储路径

```
cognition/knowledge/
```

### 文件组织

```
cognition/
└── knowledge/
    ├── wechat/
    │   ├── rules.md        # 内容发布规则
    │   ├── limits.md       # API 频率与配额限制
    │   └── tips.md         # 最佳实践与避坑指南
    ├── templates/
    │   ├── 科普.yaml       # 科普风格 Prompt 模板
    │   ├── 专业.yaml       # 专业风格 Prompt 模板
    │   └── 技术.yaml       # 技术风格 Prompt 模板
    └── ...                 # 其他领域知识（后续扩展）
```

### 文件格式标准

每个知识文件必须包含 **YAML frontmatter** 元数据头和 **Markdown/YAML** 正文。

```yaml
---
tags:
  - wechat
  - rules
  - content
platform: wechat
version: "1.0"
updated_at: "2026-05-29"
---
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tags` | list[str] | 标签列表，用于分类与检索 |
| `platform` | str | 所属平台标识 |
| `version` | str | 文档版本号 |
| `updated_at` | str | 最后更新日期 (ISO 8601) |

### 伪代码实现

```python
# cognition/knowledge_store.py

from pathlib import Path
import yaml
from typing import Optional


class KnowledgeStore:
    """
    知识存储访问层。
    提供对 Markdown/YAML 知识文件的读取、检索接口。
    Phase 1: 文件系统直接读取
    Phase 2: 叠加向量检索
    """

    def __init__(self, base_path: str = "cognition/knowledge"):
        self.base_path = Path(base_path)

    async def get_platform_rules(self, platform: str) -> dict:
        """获取指定平台的发布规则。"""
        path = self.base_path / platform / "rules.md"
        return await self._read_yaml_frontmatter(path)

    async def get_style(self, style_name: str) -> Optional[dict]:
        """获取指定写作风格的模板配置。"""
        path = self.base_path / "templates" / f"{style_name}.yaml"
        return await self._read_yaml_file(path)

    async def get_tips(self, platform: str) -> list[str]:
        """获取指定平台的最佳实践列表。"""
        path = self.base_path / platform / "tips.md"
        raw = await self._read_markdown_body(path)
        return [line.strip() for line in raw.split("\n") if line.strip()]

    async def search(self, query: str, tags: list[str] = None) -> list[dict]:
        """
        关键词搜索知识条目。
        Phase 1: 简单文件名 + 标签匹配
        Phase 2: 向量语义检索
        """
        results = []
        for md_path in self.base_path.rglob("*.md"):
            frontmatter = await self._read_yaml_frontmatter(md_path)
            if tags and not any(t in frontmatter.get("tags", []) for t in tags):
                continue
            results.append({
                "path": str(md_path.relative_to(self.base_path)),
                "metadata": frontmatter,
            })
        return results

    async def _read_yaml_frontmatter(self, path: Path) -> dict:
        """读取 Markdown 文件的 YAML frontmatter。"""
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
        return {}

    async def _read_yaml_file(self, path: Path) -> dict:
        """读取纯 YAML 文件。"""
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    async def _read_markdown_body(self, path: Path) -> str:
        """读取 Markdown 正文（去掉 frontmatter）。"""
        content = path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        return parts[2].strip() if len(parts) >= 3 else content
```

---

## 5. RAG 扩展路线图 (RAG Roadmap)

从 Phase 1 的静态 Markdown 知识库 + 规则匹配，演进为支持语义检索的 RAG 系统。

### 架构演进

```
Phase 1 (当前)                         Phase 2
┌─────────────────────────┐     ┌──────────────────────────┐
│ Markdown MD 知识文件     │     │ Markdown + 向量化        │
│ 关键词匹配 Intent        │ ──► │ Embedding 语义意图分类    │
│ 内存对话状态             │     │ Redis/SQLite 持久化会话   │
│ 规则 Prompt 模板         │     │ 模板 + 动态 Few-Shot     │
│ 无 RAG                   │     │ 语义检索增强生成          │
└─────────────────────────┘     └──────────────────────────┘
```

### Phase 2 规划

| 模块 | 升级项 | 说明 |
|------|--------|------|
| Intent Recognition | 小模型分类器 | 用 BERT/DistilBERT 替换关键词匹配 |
| Dialogue Manager | 持久化存储 | Redis 存储会话状态，支持断点恢复 |
| Content Generator | 动态 Few-Shot | 根据检索结果构建示例，提升生成质量 |
| Knowledge Store | 向量索引 | 接入 Embedding 模型，支持语义检索 |
| **新增: RAG Pipeline** | 检索增强生成 | Chunking → Embedding → 相似度搜索 → 上下文注入 |

### Phase 2 详细实现步骤

1. **文本分块 (Chunking)**：将 Markdown 知识文件按段落/标题切分为语义块，每块 256-512 tokens
2. **向量化 (Embedding)**：接入 Embedding 模型（如 `text-embedding-3-small` 或 `BAAI/bge-small-zh`）
3. **向量数据库**：引入 Chroma 或 FAISS 作为本地向量存储
4. **语义检索**：用户查询 → Embedding → 向量相似度搜索 → 返回 Top-K 知识块
5. **上下文注入**：将检索结果拼入 Prompt，增强 LLM 生成质量

### 架构兼容性

当前 Markdown 知识文件格式（YAML frontmatter + 结构化正文）已为 RAG 预留设计：

- `tags` 元数据可转为向量搜索的 filter 条件
- `version` 和 `updated_at` 支持版本管理与增量更新
- 层级化目录结构便于分块策略实现

---

## 组件间通信总览

```
Layer 5 ConversationAgent
    │  PIP (classify)
    ▼
┌─────────────────────────────────────────────┐
│  Layer 2 Cognition Layer                     │
│                                              │
│  ┌────────────────────┐                     │
│  │ Intent Recognition  │──── PIP ──────────►│
│  └────────┬───────────┘    (entities)       │
│           │                                  │
│           ▼  PIP (process_intent)            │
│  ┌────────────────────┐                     │
│  │ Dialogue Manager    │                     │
│  └────────┬───────────┘                     │
│           │  PIP (generate)                  │
│           ▼                                  │
│  ┌────────────────────┐  PIP (get_rules)    │
│  │ Content Generator  │◄────────────────────│
│  └────────┬───────────┘                     │
│           │  PIP (get_style/tips)            │
│           ▼                                  │
│  ┌────────────────────┐                     │
│  │ Knowledge Store     │                     │
│  └────────────────────┘                     │
│                                              │
└─────────────────────────────────────────────┘
    │  PIP Response (生成内容)
    ▼
Layer 1 LLM Gateway / Layer 4 Task Scheduler
```

---

## 总结

Layer 2 认知分析层是 Pulsar 的 AI 核心，当前包含四大组件：

| 组件 | Phase 1 实现 | Phase 2 目标 |
|------|-------------|-------------|
| Intent Recognition | 关键词匹配 + 实体抽取 | 小模型分类器 |
| Dialogue Manager | 内存状态管理 + 澄清/确认循环 | Redis 持久化 |
| Content Generator | 规则模板 + LLM 调用 + 格式校验 | 动态 Few-Shot + RAG |
| Knowledge Store | Markdown + YAML 文件系统 | 向量索引 + 语义检索 |

所有组件通过 **PIP 协议** 异步通信，采用 Python `async/await` 模式，为系统的可扩展性和可维护性提供坚实基础。
