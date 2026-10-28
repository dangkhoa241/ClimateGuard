"""One chat() entry point for both providers.

Every call: sets a max token cap, strips reasoning so only the final answer is
returned, caches identical requests, and logs usage + estimated cost.
"""
import hashlib
import json
import re
import threading
from dataclasses import dataclass


from . import cache, config, ssm, usage

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_clients: dict = {}  # provider -> openai.OpenAI


class EmptyAnswerError(RuntimeError):
    """Model spent its token budget reasoning and produced no final answer."""


@dataclass
class ChatResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: float
    cache_hit: bool
    raw: dict  # full response, for tool-call handling later; never shown to users


def _client(provider: str):
    if provider not in _clients:
        if provider == "baseten":
            key, param, url = config.BASETEN_API_KEY, config.BASETEN_API_KEY_PARAM, config.BASETEN_BASE_URL
        elif provider == "meta":
            key, param, url = config.MODEL_API_KEY, config.MODEL_API_KEY_PARAM, config.META_BASE_URL
        else:
            raise ValueError(f"unknown provider {provider!r}")
        if not key and param:
            key = ssm.get_secret(param)
        if not key:
            raise RuntimeError(f"API key for {provider} is not set (see .env.example)")
        # Pass api_key explicitly: the SDK does not read MODEL_API_KEY / BASETEN_API_KEY.
        # Imported here, not at module load: the SDK takes ~10 s to import on a 256 MB Lambda,
        # and most collector runs never call a model.
        from openai import OpenAI

        _clients[provider] = OpenAI(api_key=key, base_url=url, timeout=config.LLM_CALL_DEADLINE_S, max_retries=1)
    return _clients[provider]


class CallTimeout(TimeoutError):
    """A model call exceeded its wall-clock deadline."""


def _with_deadline(fn, seconds: float):
    """Run fn() with a hard wall-clock limit. HTTP timeouts only bound the gap between bytes,
    so a server that trickles output can hold a request open far longer (seen: 19 min).
    The worker is a daemon thread: if it hangs, it's abandoned, never waited on."""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise CallTimeout(f"model call exceeded {seconds:.0f} s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def strip_reasoning(message: dict) -> str:
    """Return only the final answer from an assistant message dict.

    Baseten puts reasoning in `reasoning_content` and the answer in `content`;
    we ignore `reasoning_content` entirely and also drop any inline <think>
    blocks (or an unclosed leading one) as a safety net.
    """
    content = message.get("content") or ""
    content = _THINK_RE.sub("", content)
    if "<think>" in content.lower():  # unclosed tag: everything after it is reasoning
        content = content[: content.lower().index("<think>")]
    if "</think>" in content.lower():  # stray closing tag: keep only what follows
        content = content[content.lower().rindex("</think>") + len("</think>"):]
    return content.strip()


def _cache_key(provider: str, params: dict) -> str:
    blob = json.dumps({"provider": provider, **params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def chat(provider: str, model: str, messages: list[dict], *, max_tokens: int,
         purpose: str = "", use_cache: bool = True, cache_ttl: int | None = None,
         reasoning_effort: str | None = None, deadline_s: float | None = None, **extra) -> ChatResult:
    """Call a chat model. `max_tokens` is required and includes reasoning tokens.

    `reasoning_effort` defaults to config.REASONING_EFFORT[provider];
    `cache_ttl` (seconds) defaults to config.CACHE_TTL_SECONDS.
    `deadline_s` (wall clock) defaults to config.LLM_CALL_DEADLINE_S; user-facing calls pass less.
    """
    effort = reasoning_effort or config.REASONING_EFFORT[provider]
    ttl = config.CACHE_TTL_SECONDS if cache_ttl is None else cache_ttl
    params = {"model": model, "messages": messages, "max_tokens": max_tokens,
              "reasoning_effort": effort, **extra}
    key = _cache_key(provider, params)

    raw = cache.get(key, ttl) if use_cache else None
    cache_hit = raw is not None
    if not cache_hit:
        client = _client(provider)
        raw = _with_deadline(lambda: client.chat.completions.create(**params).model_dump(),
                             deadline_s or config.LLM_CALL_DEADLINE_S)

    u = raw.get("usage") or {}
    prompt_tokens = u.get("prompt_tokens") or 0
    completion_tokens = u.get("completion_tokens") or 0
    cached_tokens = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    reasoning_tokens = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    rec = usage.log_call(provider, model, prompt_tokens, completion_tokens, cached_tokens,
                         purpose=purpose, cache_hit=cache_hit)

    choice = raw["choices"][0]
    text = strip_reasoning(choice["message"])
    if not text and not choice["message"].get("tool_calls"):
        raise EmptyAnswerError(
            f"{model} returned no final answer (finish_reason={choice.get('finish_reason')}); "
            f"raise max_tokens (reasoning counts toward it)"
        )

    if use_cache and not cache_hit:
        cache.put(key, raw, ttl)

    return ChatResult(text=text, model=model, prompt_tokens=prompt_tokens,
                      completion_tokens=completion_tokens, reasoning_tokens=reasoning_tokens,
                      cost_usd=rec["cost_usd"], cache_hit=cache_hit, raw=raw)
