"""Offline tests: reasoning text must never reach users."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from climateguard.llm import strip_reasoning
from climateguard.usage import estimate_cost


def test_reasoning_content_field_is_ignored():
    msg = {"content": "Drink water every 15 minutes.", "reasoning_content": "The user wants..."}
    assert strip_reasoning(msg) == "Drink water every 15 minutes."


def test_inline_think_block_is_removed():
    msg = {"content": "<think>secret plan</think>\nStay in the shade."}
    assert strip_reasoning(msg) == "Stay in the shade."


def test_unclosed_think_block_is_dropped():
    msg = {"content": "<think>still reasoning when tokens ran out"}
    assert strip_reasoning(msg) == ""


def test_stray_closing_tag_keeps_answer_only():
    msg = {"content": "reasoning without opening tag</think>Close windows."}
    assert strip_reasoning(msg) == "Close windows."


def test_cost_estimate():
    # 1M in + 1M out on standard Muse Spark 1.3 = 1.25 + 4.25
    assert abs(estimate_cost("muse-spark-1.3", 1_000_000, 1_000_000) - 5.50) < 1e-9


# --- cache TTL + reasoning_effort defaults (fake client, no network) ---
import os  # noqa: E402

import pytest  # noqa: E402

from climateguard import config, llm  # noqa: E402


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **params):
        self.calls.append(params)

        class _Resp:
            def model_dump(self_inner):
                return {"choices": [{"message": {"content": f"answer {len(self.calls)}"}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        return _Resp()


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    completions = _FakeCompletions()
    client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    monkeypatch.setattr(llm, "_client", lambda provider: client)
    return completions


def _ask(**kw):
    return llm.chat("baseten", "m", [{"role": "user", "content": "hi"}], max_tokens=50, **kw)


def test_cache_hit_within_ttl(fake):
    assert _ask().text == "answer 1"
    second = _ask()
    assert second.cache_hit and second.text == "answer 1"
    assert len(fake.calls) == 1


def test_cache_expires_after_ttl(fake):
    _ask()
    cache_file = next(config.CACHE_DIR.glob("*.json"))
    old = cache_file.stat().st_mtime - 7200
    os.utime(cache_file, (old, old))
    third = _ask(cache_ttl=3600)
    assert not third.cache_hit and third.text == "answer 2"


def test_reasoning_effort_default_and_override(fake):
    _ask()
    assert fake.calls[-1]["reasoning_effort"] == config.REASONING_EFFORT["baseten"]
    _ask(reasoning_effort="high", use_cache=False)
    assert fake.calls[-1]["reasoning_effort"] == "high"


def test_api_key_read_from_ssm_when_env_missing(monkeypatch):
    from climateguard import ssm

    monkeypatch.setattr(config, "BASETEN_API_KEY", "")
    monkeypatch.setattr(config, "BASETEN_API_KEY_PARAM", "/climateguard/baseten-api-key")
    monkeypatch.setattr(ssm, "get_secret", lambda name: f"secret-from:{name}")
    monkeypatch.setattr(llm, "_clients", {})
    client = llm._client("baseten")
    assert client.api_key == "secret-from:/climateguard/baseten-api-key"


def test_missing_key_and_param_raises(monkeypatch):
    monkeypatch.setattr(config, "MODEL_API_KEY", "")
    monkeypatch.setattr(config, "MODEL_API_KEY_PARAM", "")
    monkeypatch.setattr(llm, "_clients", {})
    with pytest.raises(RuntimeError, match="not set"):
        llm._client("meta")
