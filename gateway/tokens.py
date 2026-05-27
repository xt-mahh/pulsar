import time
from typing import Optional

TOKEN_CHAR_RATIO = 4.0


def count_tokens(text: str) -> int:
    return int(len(text) / TOKEN_CHAR_RATIO)


def estimate_cost(input_tokens: int, output_tokens: int, cost_per_1k_input: float, cost_per_1k_output: float) -> dict:
    input_cost = (input_tokens / 1000) * cost_per_1k_input
    output_cost = (output_tokens / 1000) * cost_per_1k_output
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(input_cost + output_cost, 6),
    }


class TokenBudget:
    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self._used = 0
        self._reset_time = time.time() + 3600

    def check(self, tokens: int) -> bool:
        if time.time() > self._reset_time:
            self._used = 0
            self._reset_time = time.time() + 3600
        return (self._used + tokens) <= self.max_tokens

    def use(self, tokens: int):
        self._used += tokens