from gateway.providers.base import BaseProvider
from gateway.providers.openai import OpenAIProvider
from gateway.providers.local import LocalProvider


class Router:
    def __init__(self, config: dict):
        self._providers: dict[str, BaseProvider] = {}
        self._default = config.get("default_provider", "deepseek")
        self._fallback = config.get("fallback_provider", "local")
        self._build_providers(config.get("providers", {}))

    def _build_providers(self, providers_config: dict):
        for name, cfg in providers_config.items():
            provider_type = cfg.get("type", "openai")
            if provider_type == "openai":
                self._providers[name] = OpenAIProvider(
                    name=name,
                    base_url=cfg.get("base_url", "http://localhost:8080/v1"),
                    api_key=cfg.get("api_key", ""),
                    model=cfg.get("model", "gpt-3.5-turbo"),
                    max_tokens=cfg.get("max_tokens", 4096),
                )
            elif provider_type == "local":
                self._providers[name] = LocalProvider(
                    name=name,
                    base_url=cfg.get("base_url", "http://localhost:8080/v1"),
                    model=cfg.get("model", "qwen2.5-14b"),
                    max_tokens=cfg.get("max_tokens", 4096),
                )

    def get_default(self) -> BaseProvider:
        return self._providers.get(self._default)

    def get_fallback(self) -> BaseProvider:
        return self._providers.get(self._fallback)

    def get_by_name(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())