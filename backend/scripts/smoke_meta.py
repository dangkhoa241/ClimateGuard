"""Smoke test: one call to Muse Spark 1.3 on the Meta Model API. Prints final answer + usage."""
import _path  # noqa: F401

from climateguard import config
from climateguard.llm import chat

res = chat(
    "meta",
    config.CHAT_MODEL,
    [{"role": "user", "content": "Responde en una frase corta: un consejo para protegerse del humo de incendios."}],
    max_tokens=1024,  # includes reasoning tokens
    purpose="smoke_test",
)
print(f"model:     {res.model}  (USE_CONTRIBUTOR={config.USE_CONTRIBUTOR})")
print(f"answer:    {res.text}")
print(f"tokens:    in={res.prompt_tokens} out={res.completion_tokens} (reasoning={res.reasoning_tokens})")
print(f"est. cost: ${res.cost_usd:.6f}{'  (cache hit)' if res.cache_hit else ''}")
