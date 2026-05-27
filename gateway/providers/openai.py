import httpx
from gateway.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    def __init__(self, name: str, base_url: str, api_key: str, model: str, max_tokens: int = 4096, **kwargs):
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    async def chat(self, messages: list[dict], **kwargs) -> dict:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
            "temperature": kwargs.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=kwargs.get("timeout", 30)) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {
                "provider": self._name,
                "model": self._model,
                "content": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
            }