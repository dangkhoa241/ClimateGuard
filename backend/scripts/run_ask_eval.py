"""Ask eval: real questions through the live Ask path (Muse Spark 1.3) on today's real data, scored by
checks in code. Also compares reasoning efforts (speed vs. usefulness).

Usage:
  python scripts/run_ask_eval.py                      # all cases at the deployed effort
  python scripts/run_ask_eval.py --effort minimal low # compare efforts (one fresh sample each)
  python scripts/run_ask_eval.py vi_field_6am_2pm     # one case
Results: backend/eval/results/ask-<timestamp>.json and .md. About $0.004 per case and effort.
The checks are heuristics for a person to read with the answers, not a full grade.
"""
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

import _path  # noqa: F401

from climateguard import ask, config

ZONE = "CAZ159"  # Stockton
TEMP = re.compile(r"\d{2,3}\s*(°F|°|degrees|grados|độ)", re.IGNORECASE)
NO_HEALTH = re.compile(r"doctor|bác sĩ|médico|clinic|phòng khám|clínica", re.IGNORECASE)
DONT_KNOW = re.compile(r"không biết|don'?t know|do not know|not sure|no s[ée]|no lo s[ée]", re.IGNORECASE)
DATA_OPENER = re.compile(r"^(số liệu|dữ liệu|theo (số liệu|dữ liệu)|the data|data from|according to the data|"
                         r"los datos|según los datos)", re.IGNORECASE)
ACTIONS = re.compile(r"water|shade|rest|break|layer|sun|hat|sunscreen|nước|bóng râm|nghỉ|nhiều lớp|lớp áo|nắng|nón|mũ|"
                     r"kem chống nắng|agua|sombra|descans|capas|sol|sombrero|protector", re.IGNORECASE)

CASES = [
    # From the iPhone test (2026-10-28): the answer gave only 6 AM and said "I don't know how to prepare".
    {"id": "vi_field_6am_2pm", "lang": "vi",
     "q": "Ngày mai tôi làm ngoài đồng từ sáu giờ sáng đến hai giờ chiều, tôi nên chuẩn bị gì?",
     "min_temps": 2, "actions": True},  # start and warmest (the end may be the warmest)
    {"id": "en_work_afternoon", "lang": "en", "q": "Is it safe to work outside this afternoon?",
     "min_temps": 1, "actions": True},
    {"id": "es_clothes_early", "lang": "es",
     "q": "¿Qué ropa debo llevar mañana temprano para trabajar en el campo?", "min_temps": 1, "actions": True},
    {"id": "vi_air_tomorrow", "lang": "vi", "q": "Chất lượng không khí ngày mai thế nào?", "min_temps": 0,
     "actions": False, "must": re.compile(r"AQI|chất lượng không khí", re.IGNORECASE)},
    # Off-topic: answer first, the weather-safety part, never "ask a repair worker" (2026-10-28 test).
    {"id": "en_repair_tomorrow", "lang": "en", "q": "Do I need to repair anything for tomorrow?", "min_temps": 0,
     "actions": False, "first_answers": True,
     "must_not": re.compile(r"repair (worker|person|professional)|contractor|handyman|professional", re.IGNORECASE)},
    # Reviewer's style: "Hãy" advice sentences, °F (°C), clothing once (2026-10-28 test).
    {"id": "vi_field_style", "lang": "vi",
     "q": "Sáng mai tôi làm ngoài đồng từ 6 giờ sáng đến 2 giờ chiều, cần mặc gì và mang theo gì?",
     "min_temps": 2, "actions": True, "vi_style": True},
    {"id": "en_cooling_place", "lang": "en", "q": "Where can I go to cool off today?", "min_temps": 0,
     "actions": False, "must": re.compile(re.escape(ask.HELP_211["en"]))},
]


def check(case: dict, r: dict) -> list[str]:
    text = r["answer"]
    fails = []
    if r["kind"] != "answer":
        fails.append(f"kind={r['kind']}")
    if DONT_KNOW.search(text):
        fails.append("says it doesn't know")
    if NO_HEALTH.search(text) and not re.search(r"health|sức khỏe|salud", case["q"], re.IGNORECASE):
        fails.append("unasked health advice")
    if DATA_OPENER.search(text.strip()):
        fails.append("starts with the data time")
    if len(TEMP.findall(text)) < case["min_temps"]:
        fails.append(f"fewer than {case['min_temps']} temperatures")
    if case["actions"] and len(set(m.lower() for m in ACTIONS.findall(text))) < 2:
        fails.append("fewer than 2 practical actions")
    if case.get("must_not") and case["must_not"].search(text):
        fails.append(f"says {case['must_not'].search(text).group(0)!r}")
    if case.get("first_answers") and TEMP.search(text.split(".")[0]):
        fails.append("starts with the forecast, not the answer")
    if case["lang"] != "en" and TEMP.search(text) and not re.search(r"°F \(-?\d+°C\)", text):
        fails.append("no °C next to °F")
    if case.get("vi_style"):
        sentences = [s.strip() for s in re.split(r"[.!?\n]", text) if s.strip()]
        if re.search(r"(^|[.!?\n]\s*)Bạn (mặc|mang|nên|đội|uống)", text):
            fails.append("advice starts with 'Bạn', not 'Hãy'")
        if sum(bool(re.search(r"mặc|áo", s)) for s in sentences) > 1:
            fails.append("clothing in more than one sentence")
    if case.get("must") and not case["must"].search(text):
        fails.append(f"missing {case['must'].pattern[:40]}")
    return fails


def main(argv: list[str]) -> None:
    efforts = [ask.ASK_REASONING_EFFORT]
    if "--effort" in argv:
        i = argv.index("--effort")
        efforts = [a for a in argv[i + 1:] if not a.startswith("--") and a in ask.MAX_ANSWER_TOKENS]
        argv = argv[:i]
    wanted = [a for a in argv if not a.startswith("--")]
    cases = [c for c in CASES if not wanted or c["id"] in wanted]
    config.CACHE_TTL_SECONDS = 0  # fresh samples, never a cached answer
    results = []
    for effort in efforts:
        ask.ASK_REASONING_EFFORT = effort
        for c in cases:
            r = ask.answer(c["q"], c["lang"], ZONE)
            fails = check(c, r)
            results.append({"effort": effort, "id": c["id"], "lang": c["lang"], "question": c["q"],
                            "answer": r["answer"], "passed": not fails, "fails": fails,
                            "ms": r["timings_ms"].get("total"), "model_ms": r["timings_ms"].get("model"),
                            "tokens": r.get("tokens"), "cost_usd": r.get("cost_usd")})
            print(f"[{effort}] {c['id']}: {'PASS' if not fails else 'FAIL ' + '; '.join(fails)} "
                  f"({r['timings_ms'].get('total')} ms)")

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(__file__).resolve().parents[1] / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"ask-{stamp}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Ask eval {stamp} (zone {ZONE}, live data)", ""]
    for effort in efforts:
        rs = [r for r in results if r["effort"] == effort]
        ms = [r["ms"] for r in rs if r["ms"]]
        lines += [f"## Effort `{effort}`: {sum(r['passed'] for r in rs)}/{len(rs)} passed, "
                  f"latency median {statistics.median(ms) / 1000:.1f} s, max {max(ms) / 1000:.1f} s, "
                  f"${sum(r['cost_usd'] or 0 for r in rs):.4f}", ""]
        for r in rs:
            tok = r["tokens"] or {}
            lines += [f"### {r['id']} ({r['lang']}): {'PASS' if r['passed'] else 'FAIL: ' + '; '.join(r['fails'])}",
                      f"Q: {r['question']}", "", "A: " + r["answer"].replace("\n", "  \n"), "",
                      f"{r['ms']} ms (model {r['model_ms']} ms), reasoning {tok.get('reasoning')} tokens, "
                      f"output {tok.get('out')}", ""]
    (out / f"ask-{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: eval/results/ask-{stamp}.md")


if __name__ == "__main__":
    main(sys.argv[1:])
