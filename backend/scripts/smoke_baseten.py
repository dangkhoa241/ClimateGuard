"""Smoke test: one call to Muse Spark Open on Baseten. Prints final answer + usage."""
import _path  # noqa: F401

from climateguard import config
from climateguard.llm import chat

res = chat(
    "baseten",
    config.MONITOR_MODEL,
    [{"role": "user", "content": "In one short sentence, give one heat-safety tip for outdoor farmworkers."}],
    max_tokens=1024,  # includes reasoning tokens
    purpose="smoke_test",
)
print(f"model:     {res.model}")
print(f"answer:    {res.text}")
print(f"tokens:    in={res.prompt_tokens} out={res.completion_tokens} (reasoning={res.reasoning_tokens})")
print(f"est. cost: ${res.cost_usd:.6f}{'  (cache hit)' if res.cache_hit else ''}")
