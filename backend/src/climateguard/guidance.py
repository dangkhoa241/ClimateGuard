"""Retrieval over official safety guidance (Cal/OSHA, NWS, CDC, EPA, FEMA).

An internal component the agents call as a tool, not a user-facing feature.
BM25 keyword search over a small curated corpus: free, instant, no model call.
"""
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "data" / "guidance.json"
_STOP = set("a an and are as at be by can for from if in is it its of on or that the this to with your you "
            "when what how should".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP]


@lru_cache(maxsize=1)
def _index():
    docs = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    toks = [_tokens(" ".join([d["title"], d["text"], " ".join(d["hazards"])])) for d in docs]
    df = Counter(t for doc in toks for t in set(doc))
    avgdl = sum(map(len, toks)) / len(toks)
    return docs, toks, df, avgdl


def search(query: str, k: int = 3, k1: float = 1.5, b: float = 0.75) -> list[dict]:
    docs, toks, df, avgdl = _index()
    n, q = len(docs), _tokens(query)
    scored = []
    for doc, dt in zip(docs, toks):
        tf, score = Counter(dt), 0.0
        for term in q:
            if term in tf:
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(dt) / avgdl))
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    return [{"id": d["id"], "source": d["source"], "url": d["url"], "title": d["title"], "text": d["text"]}
            for _, d in scored[:k]]
