"""The multi-photo damage report: one summary across all photos, damage by area, and the fixed checklist.

One text-only Muse Spark 1.3 call (the photos were already read in the analysis step, so they aren't sent
again): it writes the summary, groups the per-photo damage by area, and adds detail sentences to the
checklist items that take one, in English plus the person's language. Everything it writes goes through
recovery_guard (no safe/unsafe verdicts, no costs, no medical advice): if a line breaks a rule, the model
is told which rule and gets one retry; anything still breaking a rule is dropped.
Facts the model never touches: danger lines, questions and answers, checklist items (all fixed text).
"""
import logging
import re

from . import guardrails, llm, recovery_checklist as checklist
from .languages import LANGS
from .recovery_data import CONCEPTS, DISASTER_LABELS, OPTIONS, QUESTIONS
from .recovery_guard import OWNERSHIP_OK_ITEMS, issues

log = logging.getLogger(__name__)

MODEL = "muse-spark-1.3"
DEADLINE_S = 60
MAX_TOKENS = 4000  # two languages of JSON, reasoning included
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])\s*")  # not inside "2.5 feet"

PROMPT = """You write a short, plain-language home damage report for a person after a disaster. They will give it to their insurance company, FEMA or a helper. Use only the facts below.

Disaster: {disaster}
What each photo shows (from an earlier look at the photos; "outlined" items were found by a segmentation model):
{photo_lines}
The person's answers:
{answer_lines}
Checklist items you may add a detail to: {detail_items}

Write in English:
- "summary": 2 or 3 short sentences: what happened and the main damage seen, in plain words.
- "areas": the damage grouped by area of the home, merging photos of the same area: [{{"area": "...", "photos": [photo numbers], "damage": ["short phrase", ...]}}]. Only damage listed above.
- "details": for each checklist item above, at most one short sentence that makes it specific to this home (for example which rooms or items to photograph, or what to tell the insurer); leave an item out if there is nothing specific.
Rules: only the facts above; never say whether the home or any room is safe or unsafe to enter or live in; never give repair costs, prices or estimates; nothing about health, injuries or medicine; no blame; no markdown.
Always call it "your home" (Spanish "su casa", Vietnamese "nhà của bạn", the plain equivalent in other languages), never "the owned home", "the house you own", "the rented home" or similar; never say whether the person owns or rents it, except in a detail for the landlord item.
{lang_rule}Return only JSON: {json_shape}"""

STYLE = {"es": ' Spanish: address the person as "usted".',
         "vi": ' Vietnamese: address the person as "bạn"; start advice with "Hãy", never "Bạn nên".'}


def _prompt(disaster: str, photos: list[dict], answers: dict, lang: str, detail_ids: list[str]) -> str:
    photo_lines = []
    for p in photos:
        outlined = ", ".join(f"{CONCEPTS[f['concept']]['en'].lower()} x{f['count']}" for f in p.get("found") or [])
        photo_lines.append(f"Photo {p['index'] + 1}: area: {p['area']}; damage: {'; '.join(p['damage']) or 'none seen'}"
                           + (f"; outlined: {outlined}" if outlined else ""))
    # not "hurt" (911 is fixed text) and not "own_rent" (it only picks the landlord item, in code): the model
    # wrote "the owned home" from it
    answer_lines = [f"- {QUESTIONS[q]['en']} {OPTIONS[a]['en']}" for q, a in answers.items()
                    if q not in ("hurt", "own_rent")]
    shape = '{"en": {"summary": "...", "areas": [...], "details": {"item_id": "..."}}'
    rule = ""
    if lang != "en":
        name = LANGS[lang]["name"]
        rule = (f'Then give the same report in {name} under "{lang}", with the same structure, the same photo '
                f'numbers and the same checklist ids.{STYLE.get(lang, "")}\n')
        shape += f', "{lang}": {{...same structure in {name}...}}'
    return PROMPT.format(disaster=DISASTER_LABELS[disaster]["en"], photo_lines="\n".join(photo_lines),
                         answer_lines="\n".join(answer_lines) or "- (no answers)", lang_rule=rule,
                         detail_items=", ".join(f"{i} ({checklist.ITEMS[i]['en'][:60]}...)" for i in detail_ids) or "none",
                         json_shape=shape + "}")


def _clean_text(text, lang: str) -> str:
    text = " ".join(str(text or "").replace("**", "").split())[:600]
    return guardrails.fix_vi_advice(text) if lang == "vi" else text


def _part(raw: dict, lang: str, n_photos: int, detail_ids: list[str]) -> tuple[dict, list[str]]:
    """One language of the model's report, checked line by line. Returns (part, broken rule names)."""
    broken = []

    def ok(text, ownership_ok=False):
        found = issues(text, ownership_ok)
        broken.extend(found)
        return text if text and not found else None

    summary = [s for s in (ok(_clean_text(x, lang)) for x in _sentences(raw.get("summary"))) if s]
    areas = []
    for a in raw.get("areas") or []:
        if not isinstance(a, dict):
            continue
        name = ok(_clean_text(a.get("area"), lang)[:60])
        damage = [d for d in (ok(_clean_text(x, lang)[:160]) for x in (a.get("damage") or [])[:6]) if d]
        nums = sorted({int(n) for n in a.get("photos") or [] if str(n).isdigit() and 1 <= int(n) <= n_photos})
        if name and damage:
            areas.append({"area": name, "photos": nums, "damage": damage})
    details = {}
    for i, d in (raw.get("details") or {}).items():
        if i in detail_ids and (text := ok(_clean_text(d, lang)[:200], i in OWNERSHIP_OK_ITEMS)):
            details[i] = text
    return {"summary": " ".join(summary), "areas": areas, "details": details}, sorted(set(broken))


def _sentences(text) -> list[str]:
    return [s for s in _SENTENCE_END.split(str(text or "").strip()) if s]


def write(disaster: str, photos: list[dict], answers: dict, lang: str) -> dict:
    """{en: part, <lang>: part, checklist_ids, cost_usd, attempts, guard_removed}. Raises if no usable JSON."""
    from .recovery import _parse_json  # shared JSON reader

    ids = checklist.pick(disaster, answers)
    detail_ids = [i for i in ids if checklist.ITEMS[i].get("detail")]
    messages = [{"role": "user", "content": _prompt(disaster, photos, answers, lang, detail_ids)}]
    cost, removed = 0.0, []
    for attempt in (1, 2):
        res = llm.chat("meta", MODEL, messages, max_tokens=MAX_TOKENS, purpose=f"recovery-report:{lang}",
                       use_cache=False, reasoning_effort="low", deadline_s=DEADLINE_S)
        cost += res.cost_usd
        raw = _parse_json(res.text)
        parts, broken = {}, []
        for code in dict.fromkeys(["en", lang]):
            part, b = _part(raw.get(code) or {}, code, len(photos), detail_ids)
            parts[code] = part
            broken += b
        if not broken or attempt == 2:
            removed = sorted(set(broken))
            break
        log.info("recovery report broke %s; retrying once", sorted(set(broken)))
        messages += [{"role": "assistant", "content": res.text},
                     {"role": "user", "content": f"Some lines broke the rules ({', '.join(sorted(set(broken)))}): "
                      "never safe/unsafe verdicts, never costs, prices or estimates, nothing about health or "
                      "injuries, and always \"your home\", never whether it is owned or rented. "
                      "Rewrite the whole JSON without them."}]
    return {**parts, "checklist_ids": ids, "cost_usd": round(cost, 6), "attempts": attempt,
            "guard_removed": removed}
