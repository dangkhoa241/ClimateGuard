"""Guardrails for everything the recovery agent's model writes (damage phrases, report, checklist details).

Three things the model must never say, checked in code in all 7 languages:
  1. whether a building is safe or unsafe to enter or live in (only an inspector can say that);
  2. medical advice (injuries go to 911, through fixed text);
  3. a repair cost, price or dollar amount ("Not an official damage estimate").
A line that breaks a rule is dropped; the caller decides whether to retry. Fixed text written in code
(questions, danger lines, checklist items) is not checked: "desde un sitio seguro" is ours.
"""
import re

from .ask import ANSWER_MEDICAL

SAFETY_VERDICT = re.compile(
    r"\b(un)?safe(ly|ty)?\b|structural(ly)? (sound|safe|unsound|stable|integrity)|\b(un)?inhabitable\b|"
    r"\b(un)?habitable\b|\b(un)?livable\b|condemn|\bok(ay)? to (enter|live|stay|go)|fine to (enter|live|stay)|"
    r"\bcan (safely )?(enter|go back|return|live)|should not (enter|go in|live)|"
    # es: "seguro" alone is also "insurance", so only the verdict phrases
    r"(in)?segur[oa]s? (para|de) (entrar|vivir|habitar|quedarse|regresar)|\bes (in)?segur[oa]\b|"
    r"\bno es segur|\bpeligros[oa] (entrar|vivir)|estructuralmente|\b(in)?habitable|"
    r"an toàn|kết cấu (vững|ổn|an)|ở được|vào được|"          # vi
    r"安全|可以居住|不宜居住|不能居住|结构稳|"                   # zh
    r"ligtas|matibay pa|"                                     # tl
    r"안전|거주 가능|거주할 수|구조적으로|"                       # ko
    r"آمن|آمنة|صالح للسكن|غير صالح",                          # ar
    re.IGNORECASE)

COST = re.compile(
    r"\$\s?\d|\d\s?(\$|usd|dollars?)\b|\bdollars?\b|\bcosts?\b|\bprice|\bestimate[sd]?\b|\bquote\b|"
    r"d[oó]lar|\bcost[oe]s?\b|\bcuesta|\bprecio|presupuesto|"
    r"đô la|chi phí|\bgiá\b|ước tính|"
    r"美元|费用|成本|价格|估价|"
    r"dolyar|halaga|gastos|presyo|"
    r"달러|비용|가격|견적|"
    r"دولار|تكلفة|سعر|تقدير",
    re.IGNORECASE)

# Injury care on top of Ask's medical list (symptoms, medicines...), in the reviewed languages.
INJURY_CARE = re.compile(
    r"first aid|bandage|\bwound|\bcpr\b|tetanus|antibiotic|disinfect (a|the) (cut|wound)|"
    r"primeros auxilios|vendaje|\bheridas?\b|t[eé]tanos|antibi[oó]tico|"
    r"sơ cứu|băng bó|vết thương|uốn ván|kháng sinh", re.IGNORECASE)

RULES = (("safety_verdict", SAFETY_VERDICT), ("repair_cost", COST), ("medical", ANSWER_MEDICAL),
         ("medical", INJURY_CARE))


def issues(text: str) -> list[str]:
    """Names of the rules this text breaks (empty = fine)."""
    return sorted({name for name, rx in RULES if rx.search(text or "")})


def keep_clean(lines: list[str]) -> tuple[list[str], list[str]]:
    """(lines that pass, rule names that removed the others)."""
    kept, broken = [], []
    for line in lines:
        found = issues(line)
        if found:
            broken += found
        else:
            kept.append(line)
    return kept, sorted(set(broken))
