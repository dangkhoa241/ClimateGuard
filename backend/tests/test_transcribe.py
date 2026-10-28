"""Offline tests for voice questions: WAV checks, the API request, cost logging, POST /transcribe."""
import base64
import io
import json
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, transcribe, usage
from climateguard.handlers import ask as ask_handler


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")


def _wav(seconds=2.0, rate=16000, channels=1, width=2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\0" * int(seconds * rate) * channels * width)
    return buf.getvalue()


def test_check_wav_accepts_only_what_the_api_takes():
    assert transcribe.check_wav(_wav(2.0)) == 2000
    assert transcribe.check_wav(_wav(1.0, rate=24000)) == 1000
    for bad, code in ((_wav(rate=44100), "invalid_audio"), (_wav(channels=2), "invalid_audio"),
                      (_wav(width=1), "invalid_audio"), (b"not a wav", "invalid_audio"),
                      (_wav(0.1), "audio_too_short"), (_wav(61), "audio_too_long")):
        with pytest.raises(transcribe.AudioError) as e:
            transcribe.check_wav(bad)
        assert e.value.code == code


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        pass


def _fake_api(monkeypatch, seen, transcript="  Hôm nay có nóng không?  ", ms=4400):
    class _Client:
        api_key = "k"

    def post(url, headers, files, timeout):
        seen.append({"url": url, "request": json.loads(files["request"][1]), "audio": files["audio"][1]})
        return _Resp({"sessionId": "s", "transcript": transcript, "audioDurationMs": ms, "turns": []})
    monkeypatch.setattr(transcribe.llm, "_client", lambda provider: _Client())
    monkeypatch.setattr(transcribe.requests, "post", post)


def test_transcribe_sends_language_bias_and_logs_cost(monkeypatch):
    seen = []
    _fake_api(monkeypatch, seen)
    out = transcribe.transcribe(_wav(), "vi")
    assert out == {"text": "Hôm nay có nóng không?", "audio_ms": 4400}
    req = seen[0]["request"]
    assert seen[0]["url"].endswith("/asr/transcribe")
    assert req["model"] == "muse-voice-transcribe-1.0" and req["languageBias"] == ["Vietnamese", "English"]
    rec = json.loads(config.USAGE_LOG.read_text().splitlines()[-1])
    assert rec["audio_seconds"] == 4 and rec["cost_usd"] == pytest.approx(4 * 0.18 / 3600)
    assert usage.totals()  # the audio record doesn't break the spend report


def _event(audio: bytes, lang="es", ip="1.2.3.4"):
    return {"routeKey": "POST /transcribe", "queryStringParameters": {"lang": lang},
            "body": base64.b64encode(audio).decode(), "isBase64Encoded": True,
            "requestContext": {"http": {"sourceIp": ip}}}


def test_handler_validates_and_rate_limits(monkeypatch):
    _fake_api(monkeypatch, [], transcript="¿Hace calor hoy?")
    r = ask_handler.handler(_event(_wav()), None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["text"] == "¿Hace calor hoy?"
    for event, status, code in ((_event(_wav(), lang="fr"), 400, "invalid_lang"),
                                (_event(_wav(rate=44100)), 400, "invalid_audio"),
                                ({**_event(b""), "body": "A" * (ask_handler.MAX_AUDIO_BODY_CHARS + 1)}, 413,
                                 "audio_too_long")):
        r = ask_handler.handler(event, None)
        assert r["statusCode"] == status and json.loads(r["body"])["error"] == code
    monkeypatch.setattr(ask_handler, "TRANSCRIBE_PER_IP_PER_HOUR", 2)
    codes = [ask_handler.handler(_event(_wav(), ip="9.9.9.9"), None)["statusCode"] for _ in range(3)]
    assert codes == [200, 200, 429]


def test_handler_api_failure_is_a_friendly_error(monkeypatch):
    def boom(*a, **kw):
        raise ConnectionError("down")
    monkeypatch.setattr(transcribe, "transcribe", boom)
    r = ask_handler.handler(_event(_wav()), None)
    assert r["statusCode"] == 502 and json.loads(r["body"])["error"] == "transcribe_failed"
