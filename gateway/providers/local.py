from gateway.providers.openai import OpenAIProvider


class LocalProvider(OpenAIProvider):
    def __init__(self, name: str = "local", base_url: str = "http://localhost:8080/v1", model: str = "qwen2.5-14b", **kwargs):
        super().__init__(
            name=name,
            base_url=base_url,
            api_key=kwargs.get("api_key", "not-needed"),
            model=model,
            max_tokens=kwargs.get("max_tokens", 4096),
        )