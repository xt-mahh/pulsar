import asyncio
from gateway.router import Router
from gateway.tokens import count_tokens, estimate_cost, TokenBudget


class LLMGateway:
    def __init__(self, config: dict):
        self.config = config
        self.router = Router(config)
        self.budget = TokenBudget(max_tokens=config.get("max_tokens_per_hour", 100000))
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 2)

    async def chat(self, messages: list[dict], provider: str = None, **kwargs) -> dict:
        provider_obj = self.router.get_by_name(provider) if provider else self.router.get_default()
        if not provider_obj:
            raise ValueError(f"No provider available")

        input_tokens = sum(count_tokens(m.get("content", "")) for m in messages)
        if not self.budget.check(input_tokens):
            raise ValueError("Token budget exceeded")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = await asyncio.wait_for(
                    provider_obj.chat(messages, timeout=self.timeout, **kwargs),
                    timeout=self.timeout,
                )
                output_tokens = count_tokens(result.get("content", ""))
                self.budget.use(input_tokens + output_tokens)
                return result
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))

        fallback = self.router.get_fallback()
        if fallback and fallback.name != provider_obj.name:
            try:
                result = await asyncio.wait_for(
                    fallback.chat(messages, timeout=self.timeout, **kwargs),
                    timeout=self.timeout,
                )
                return result
            except Exception as e:
                last_error = e

        raise last_error or RuntimeError("LLM call failed")