"""deploy.ps1 must pass every template parameter to SAM.

SAM keeps the stack's previous value for any parameter that is not in --parameter-overrides, so a changed
template Default never reaches the live stack (the $3 -> $10 spend cap stayed at $3 this way).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "template.yaml").read_text(encoding="utf-8")
DEPLOY = (ROOT / "deploy.ps1").read_text(encoding="utf-8")

# Dev-server origins: fixed, never changed, and the preflight warns if the live value ever differs from the default.
NOT_PASSED = {"LocalDevOrigin", "LocalDevOrigin2"}


def template_parameters() -> dict[str, str | None]:
    block = TEMPLATE.split("\nParameters:\n", 1)[1].split("\nConditions:", 1)[0]
    params: dict[str, str | None] = {}
    for m in re.finditer(r"(?m)^  (\w+):\n((?:    .*\n|\n)+)", block + "\n"):
        default = re.search(r"(?m)^    Default:\s*(\S+)", m.group(2))
        params[m.group(1)] = default.group(1).strip('"') if default else None
    return params


def passed_overrides() -> dict[str, str]:
    block = DEPLOY.split("$overrides = @(", 1)[1].split("\n)", 1)[0]
    return dict(re.findall(r'"(\w+)=([^"]*)"', block))


def script_defaults() -> dict[str, str]:
    block = DEPLOY.split("param(", 1)[1].split("\n)", 1)[0]
    return dict(re.findall(r"\[(?:int|double|string)\]\$(\w+)\s*=\s*([^\s,]+)", block))


def test_template_parameters_are_parsed():
    params = template_parameters()
    assert {"FrontendUrl", "MaxSubscribers", "MaxSubscriptionsPerEmail", "DailyModelBudgetUsd",
            "NwsUserAgent"} <= set(params)
    assert params["DailyModelBudgetUsd"] == "10"


def test_every_template_parameter_is_passed_to_sam():
    missing = set(template_parameters()) - set(passed_overrides()) - NOT_PASSED
    assert not missing, f"deploy.ps1 does not pass {sorted(missing)}: SAM would keep their old live values"


def test_budget_is_passed_explicitly_and_defaults_to_the_template_value():
    assert passed_overrides()["DailyModelBudgetUsd"] == "$DailyModelBudgetUsd"
    assert float(script_defaults()["DailyModelBudgetUsd"]) == float(template_parameters()["DailyModelBudgetUsd"]) == 10


def test_script_defaults_match_template_defaults_for_numeric_parameters():
    params, defaults = template_parameters(), script_defaults()
    for name in ("MaxSubscribers", "MaxSubscriptionsPerEmail", "DailyModelBudgetUsd"):
        assert float(defaults[name]) == float(params[name]), name


def test_preflight_prints_the_budget_being_deployed():
    assert 'Report "DailyModelBudgetUsd" "OK"' in DEPLOY
    assert "deploying" in DEPLOY and "live stack" in DEPLOY
