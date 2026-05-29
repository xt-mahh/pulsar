# Pulsar Phase 1 Sprint 1 — gateway/ 模块详细计划

> 本文档描述 `gateway/` 模块的设计方案，包含 LLM Gateway 基础路由、多模型提供商支持。
> gateway 是系统的 LLM 统一调用接口，为所有需要 LLM 能力的组件提供服务。

---

## 一、模块定位

**职责**：为系统中所有需要 LLM 能力的组件提供统一的模型调用接口。

**Phase 1 范围**：
- 多提供商抽象（OpenAI 兼容 API + 本地模型）
- 按配置自动路由（默认模型 + Fallback 模型）
- 基础 Token 计数和成本追踪
- 超时控制（30s 默认超时）和重试（3 次指数退避）

---

## 二、文件清单

| # | 文件 | 优先级 | 依赖 |
|---|------|--------|------|
| 1 | `gateway/__init__.py` | P0 | 无 |
| 2 | `gateway/providers/__init__.py` | P0 | 无 |
| 3 | `gateway/providers/base.py` | P0 | shared |
| 4 | `gateway/providers/openai.py` | P0 | base |
| 5 | `gateway/providers/local.py` | P1 | base |
| 6 | `gateway/router.py` | P0 | providers |
| 7 | `gateway/gateway.py` | P0 | router |
| 8 | `gateway/tokens.py` | P1 | shared |

---

## 三、`gateway/providers/base.py` 设计方案

### 3.1 职责

定义 LLM 提供商基类，所有提供商必须实现此接口。

### 3.2 提供商基类

```python
class BaseProvider(ABC):
    """LLM 提供商基类"""
    
    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "unknown")
        self.model = config.get("model", "unknown")
        self.max_tokens = config.get("max_tokens", 4096)
    
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> dict:
        """发送聊天请求
        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
            **kwargs: 额外参数（temperature, max_tokens, top_p 等）
        Returns:
            {"content": str, "usage": {"prompt_tokens": int, "completion_tokens": int}}
        """
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """估算文本的 token 数量"""
    
    async def health_check(self) -> bool:
        """健康检查（默认实现：发送一个简单请求）"""
        try:
            await self.chat([{"role": "user", "content": "ping"}], max_tokens=10)
            return True
        except Exception:
            return False
```

---

## 四、`gateway/providers/openai.py` 设计方案

### 4.1 职责

实现 OpenAI 兼容 API 的提供商（兼容 DeepSeek、Claude、本地模型的 OpenAI 格式 API）。

### 4.2 核心实现

```python
class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API 提供商"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.api_key = config.get("api_key", "")
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.get("timeout", 30),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._client
    
    async def chat(self, messages: list[dict], **kwargs) -> dict:
        """发送聊天请求到 OpenAI 兼容 API"""
        client = self._get_client()
        
        body = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 1.0),
        }
        
        # 添加可选参数
        for key in ["stop", "frequency_penalty", "presence_penalty"]:
            if key in kwargs:
                body[key] = kwargs[key]
        
        response = await client.post("/chat/completions", json=body)
        data = response.json()
        
        if "error" in data:
            raise ProviderError(f"LLM API 错误: {data['error']}")
        
        return {
            "content": data["choices"][0]["message"]["content"],
            "usage": {
                "prompt_tokens": data["usage"]["prompt_tokens"],
                "completion_tokens": data["usage"]["completion_tokens"],
                "total_tokens": data["usage"]["total_tokens"],
            },
            "model": data.get("model", self.model),
        }
    
    async def count_tokens(self, text: str) -> int:
        """估算 token 数量（使用 tiktoken 或简单估算）"""
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self.model)
            return len(encoding.encode(text))
        except (ImportError, KeyError):
            # 回退：按字符数估算（中英文混合约 1 token/1.5 字符）
            return int(len(text) / 1.5)
    
    async def health_check(self) -> bool:
        """检查 API 是否可用"""
        try:
            await self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0,
            )
            return True
        except Exception:
            return False
```

---

## 五、`gateway/providers/local.py` 设计方案

### 5.1 职责

实现本地模型提供商（连接本地 llama.cpp/Ollama 服务）。

### 5.2 核心实现

```python
class LocalProvider(BaseProvider):
    """本地模型提供商（OpenAI 兼容格式）"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:8080/v1")
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.get("timeout", 60),  # 本地模型可能较慢
            )
        return self._client
    
    async def chat(self, messages: list[dict], **kwargs) -> dict:
        """发送聊天请求到本地模型"""
        client = self._get_client()
        
        body = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        
        response = await client.post("/chat/completions", json=body)
        data = response.json()
        
        return {
            "content": data["choices"][0]["message"]["content"],
            "usage": data.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            "model": data.get("model", self.model),
        }
    
    async def count_tokens(self, text: str) -> int:
        """本地模型 token 估算"""
        return int(len(text) / 1.5)  # 简单估算
```

---

## 六、`gateway/router.py` 设计方案

### 6.1 职责

多模型路由，根据配置选择默认/备用提供商，支持 Fallback 链。

### 6.2 核心实现

```python
class ModelRouter:
    """多模型路由器"""
    
    def __init__(self, config: dict):
        self._providers: dict[str, BaseProvider] = {}
        self._default_provider: str = config.get("default_provider", "")
        self._fallback_provider: str = config.get("fallback_provider", "")
        self._timeout = config.get("timeout", 30)
        self._max_retries = config.get("max_retries", 3)
        self._retry_delay = config.get("retry_delay", 2)
        
        # 初始化所有提供商
        for name, provider_config in config.get("providers", {}).items():
            provider_type = provider_config.get("type", "openai")
            if provider_type == "openai":
                provider_config["name"] = name
                self._providers[name] = OpenAIProvider(provider_config)
            elif provider_type == "local":
                provider_config["name"] = name
                self._providers[name] = LocalProvider(provider_config)
    
    def get_provider(self, name: str = None) -> BaseProvider:
        """获取指定名称的提供商"""
        name = name or self._default_provider
        provider = self._providers.get(name)
        if not provider:
            raise ProviderNotFoundError(f"提供商 '{name}' 未配置")
        return provider
    
    async def chat(self, messages: list[dict], provider: str = None, **kwargs) -> dict:
        """发送聊天请求（带 Fallback）
        1. 使用指定或默认提供商
        2. 失败时使用 Fallback 提供商
        3. 重试策略：指数退避
        """
        provider_name = provider or self._default_provider
        last_error = None
        
        # 尝试主提供商
        for attempt in range(self._max_retries):
            try:
                p = self.get_provider(provider_name)
                return await asyncio.wait_for(
                    p.chat(messages, **kwargs),
                    timeout=kwargs.get("timeout", self._timeout),
                )
            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    wait = self._retry_delay * (2 ** attempt)
                    await asyncio.sleep(wait)
        
        # 主提供商失败，尝试 Fallback
        if self._fallback_provider and self._fallback_provider != provider_name:
            try:
                p = self.get_provider(self._fallback_provider)
                return await asyncio.wait_for(
                    p.chat(messages, **kwargs),
                    timeout=kwargs.get("timeout", self._timeout),
                )
            except Exception as e:
                last_error = e
        
        raise ProviderError(f"所有提供商调用失败: {last_error}")
    
    def list_providers(self) -> list[str]:
        """列出所有已配置的提供商"""
        return list(self._providers.keys())
```

---

## 七、`gateway/gateway.py` 设计方案

### 7.1 职责

LLM Gateway 统一调用接口，整合 Router + Provider，对外提供简洁的 API。

### 7.2 核心实现

```python
class LLMGateway:
    """LLM Gateway — 统一调用接口"""
    
    def __init__(self, config: dict):
        self._router = ModelRouter(config)
        self._token_counter = TokenCounter(config)
        self._config = config
    
    async def chat(self, messages: list[dict], **kwargs) -> dict:
        """发送聊天请求
        返回格式:
        {
            "content": str,
            "usage": {"prompt_tokens": int, "completion_tokens": int},
            "model": str,
            "provider": str,
        }
        """
        provider = kwargs.pop("provider", None)
        result = await self._router.chat(messages, provider=provider, **kwargs)
        
        # 追踪成本
        self._token_counter.track(
            provider or self._config.get("default_provider", ""),
            result["usage"]["prompt_tokens"],
            result["usage"]["completion_tokens"],
        )
        
        return result
    
    async def chat_with_system(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """便捷方法：system + user 消息"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = await self.chat(messages, **kwargs)
        return result["content"]
    
    async def count_tokens(self, text: str, provider: str = None) -> int:
        """估算 token 数量"""
        p = self._router.get_provider(provider)
        return await p.count_tokens(text)
    
    def get_usage_stats(self) -> dict:
        """获取使用统计"""
        return self._token_counter.get_stats()
    
    async def health_check(self) -> dict:
        """检查所有提供商健康状态"""
        results = {}
        for name in self._router.list_providers():
            try:
                p = self._router.get_provider(name)
                results[name] = await p.health_check()
            except Exception:
                results[name] = False
        return results
```

---

## 八、`gateway/tokens.py` 设计方案

### 8.1 职责

Token 计数与成本追踪。

### 8.2 核心实现

```python
class TokenCounter:
    """Token 计数器与成本追踪"""
    
    def __init__(self, config: dict):
        self._config = config
        self._usage: dict[str, dict] = {}  # provider → {prompt_tokens, completion_tokens, cost}
        self._lock = asyncio.Lock()
    
    def track(self, provider: str, prompt_tokens: int, completion_tokens: int):
        """记录一次调用的 token 使用量"""
        provider_config = self._config.get("providers", {}).get(provider, {})
        cost_per_1k_input = provider_config.get("cost_per_1k_input", 0)
        cost_per_1k_output = provider_config.get("cost_per_1k_output", 0)
        
        cost = (prompt_tokens / 1000 * cost_per_1k_input +
                completion_tokens / 1000 * cost_per_1k_output)
        
        if provider not in self._usage:
            self._usage[provider] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost": 0.0,
                "call_count": 0,
            }
        
        self._usage[provider]["prompt_tokens"] += prompt_tokens
        self._usage[provider]["completion_tokens"] += completion_tokens
        self._usage[provider]["total_tokens"] += prompt_tokens + completion_tokens
        self._usage[provider]["cost"] += cost
        self._usage[provider]["call_count"] += 1
    
    def get_stats(self) -> dict:
        """获取所有提供商的使用统计"""
        return dict(self._usage)
    
    def get_total_cost(self) -> float:
        """获取总成本"""
        return sum(p["cost"] for p in self._usage.values())
```

---

## 九、验收标准

- [ ] `LLMGateway.chat()` 可调用配置的默认模型并返回结果
- [ ] 主提供商失败后自动切换到 Fallback 提供商
- [ ] 重试机制生效（3 次指数退避）
- [ ] `TokenCounter` 正确追踪 token 使用量和成本
- [ ] `health_check()` 返回所有提供商的健康状态
- [ ] 支持通过 `provider` 参数指定使用哪个提供商

---

## 十、注意事项

1. **API Key 安全**：API Key 通过环境变量注入，不硬编码在配置中
2. **超时控制**：所有 LLM 调用有超时，默认 30s，本地模型可配置更长
3. **错误处理**：区分可重试错误（超时、限流）和不可重试错误（认证失败、参数错误）
4. **成本追踪**：成本数据仅用于统计，不用于计费
5. **模型热切换**：修改配置后重启系统即可切换模型，无需代码变更