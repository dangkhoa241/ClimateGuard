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

# Phone test: reports said "the owned home" / "the house you own". The home is always "your home" ("su casa",
# "nhà của bạn"); owning or renting is mentioned only in the checklist items that need it.
OWNERSHIP = re.compile(
    r"\b(owned|rented|rental) (home|house|property)\b|\b(home|house|property) (that )?you (own|rent)\b|"
    r"\byou (own|rent)\b|\bhomeowner|\brenter\b|"
    r"(casa|vivienda) (propia|alquilada|que (usted )?(posee|alquila|renta))|\b(es dueñ[oa]|alquila|renta) (la|su) (casa|vivienda)|"
    r"nhà (riêng|thuê|sở hữu)|nhà (mà )?bạn (sở hữu|thuê)|bạn (là chủ|thuê) nhà|"
    r"自有住房|您拥有的房|租住的房|您租的房|sariling bahay|inuupahang bahay|소유한 집|임차한 집|자가 주택|"
    r"المنزل المملوك|المنزل المستأجر",
    re.IGNORECASE)
OWNERSHIP_OK_ITEMS = {"landlord", "flood_policy"}  # checklist items whose detail may mention owning or renting

RULES = (("safety_verdict", SAFETY_VERDICT), ("repair_cost", COST), ("medical", ANSWER_MEDICAL),
         ("medical", INJURY_CARE), ("ownership", OWNERSHIP))


def issues(text: str, ownership_ok: bool = False) -> list[str]:
    """Names of the rules this text breaks (empty = fine). `ownership_ok`: a landlord / flood-policy detail."""
    return sorted({name for name, rx in RULES if rx.search(text or "") and not (ownership_ok and name == "ownership")})


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
