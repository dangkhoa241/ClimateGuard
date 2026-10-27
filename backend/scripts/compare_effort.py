"""Compare Muse Spark Open reasoning_effort levels on a monitoring-style decision.

Usage: python scripts/compare_effort.py [low medium high xhigh]
Uncached live calls — costs roughly $0.01–0.03 per level.
"""
import sys
import time

import _path  # noqa: F401

from climateguard import config
from climateguard.llm import chat

CASES = [
    # Clear-cut: should alert
    "Stockton, CA. Forecast today: high 108F at 3 PM, heat index 112F, low 74F. AQI 62 (moderate). "
    "Active NWS alert: Excessive Heat Warning until 9 PM. Alerts already sent today: none.",
    # Duplicate: should skip
    "Stockton, CA. Forecast today: high 107F. AQI 55. Active NWS alert: Excessive Heat Warning "
    "(re-issued, same area and end time). Alerts already sent today: 'Excessive Heat Warning' at 7 AM, severity high.",
]
PROMPT = (
    "You are a climate-risk monitoring agent for farmworkers. Given the data, decide whether to send a new alert. "
    "Reply with JSON only: {\"send\": true|false, \"severity\": \"low|moderate|high|extreme\", \"reason\": \"...\", "
    "\"messages\": {\"en\": \"...\", \"es\": \"...\", \"vi\": \"...\"}}. Messages: max 2 short sentences, practical "
    "protective actions (water, shade, rest, avoid peak hours), no medical advice. Empty messages if send is false."
)

levels = sys.argv[1:] or ["low", "medium", "high"]
for level in levels:
    for i, case in enumerate(CASES, 1):
        t0 = time.time()
        res = chat("baseten", config.MONITOR_MODEL,
                   [{"role": "system", "content": PROMPT}, {"role": "user", "content": case}],
                   max_tokens=4000, reasoning_effort=level, use_cache=False, purpose=f"effort_eval_{level}")
        print(f"=== {level} / case {i}: {time.time() - t0:.1f}s  out={res.completion_tokens} "
              f"(reasoning={res.reasoning_tokens})  ${res.cost_usd:.4f}")
        print(res.text, "\n")
