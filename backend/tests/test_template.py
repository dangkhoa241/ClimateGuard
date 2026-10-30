"""template.yaml checks that cfn-lint can't catch: run SAM's own transform locally."""
from pathlib import Path

import pytest

samtranslator = pytest.importorskip("samtranslator")
from samtranslator.translator.transform import transform  # noqa: E402
from samtranslator.yaml_helper import yaml_parse  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[2] / "template.yaml"


class _PolicyLoader:  # managed-policy lookup without calling IAM
    def load(self):
        return {"AWSLambdaBasicExecutionRole": "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"}


@pytest.fixture(scope="module")
def transformed():
    tpl = yaml_parse(TEMPLATE.read_text(encoding="utf-8"))
    tpl["Globals"]["Function"]["CodeUri"] = "s3://placeholder/code.zip"  # sam deploy uploads the real code
    return transform(tpl, {}, _PolicyLoader())


def _true(cond, params):
    if "Fn::Or" in cond:
        return any(_true(c, params) for c in cond["Fn::Or"])
    a, b = (params[x["Ref"]] if isinstance(x, dict) else x for x in cond["Fn::Equals"])
    return a == b


def _resolve(value, params, conditions):
    if isinstance(value, dict) and "Fn::If" in value:
        cond, yes, no = value["Fn::If"]
        return _resolve(yes if _true(conditions[cond], params) else no, params, conditions)
    if isinstance(value, list):
        return [_resolve(v, params, conditions) for v in value]
    if isinstance(value, dict) and set(value) == {"Ref"}:
        return params[value["Ref"]]
    if isinstance(value, dict):
        return {k: _resolve(v, params, conditions) for k, v in value.items()}
    return value


@pytest.mark.parametrize("frontend", ["http://localhost:5173", "http://localhost:5174",
                                      "https://example-demo.vercel.app"])
def test_cors_origins_never_duplicated(transformed, frontend):
    api = next(r for r in transformed["Resources"].values() if r["Type"] == "AWS::ApiGatewayV2::Api")
    cors = _resolve(api["Properties"]["Body"]["x-amazon-apigateway-cors"],
                    {"FrontendUrl": frontend, "LocalDevOrigin": "http://localhost:5173",
                     "LocalDevOrigin2": "http://localhost:5174"},
                    transformed["Conditions"])
    origins = cors["allowOrigins"]
    assert len(origins) == len(set(origins)) and frontend in origins
    assert {"http://localhost:5173", "http://localhost:5174"} <= set(origins)
    assert cors["allowMethods"] == ["GET", "POST", "DELETE", "OPTIONS"]  # SAM must not drop the rest of the block


def test_log_groups_keep_seven_days(transformed):
    groups = [r for r in transformed["Resources"].values() if r["Type"] == "AWS::Logs::LogGroup"]
    assert len(groups) == 2 and all(g["Properties"]["RetentionInDays"] == 7 for g in groups)


def test_collector_can_write_daily_counters(transformed):
    # stats.record() runs UpdateItem on the rate-limit table; the deployed role lacked it (AccessDenied
    # on every run, so the public history showed zero checks).
    import json
    role = json.dumps(transformed["Resources"]["CollectFunctionRole"]["Properties"]["Policies"])
    assert "RateLimitTable" in role and "dynamodb:UpdateItem" in role


def test_api_can_claim_signup_counters_atomically(transformed):
    import json
    role = json.dumps(transformed["Resources"]["ApiFunctionRole"]["Properties"]["Policies"])
    assert "RateLimitTable" in role and "dynamodb:TransactWriteItems" in role


def test_recovery_photos_private_and_cleaned_up(transformed):
    import json
    bucket = transformed["Resources"]["RecoveryBucket"]["Properties"]
    assert bucket["PublicAccessBlockConfiguration"] == {"BlockPublicAcls": True, "BlockPublicPolicy": True,
                                                        "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
    assert not any(r["Type"] == "AWS::S3::BucketPolicy" for r in transformed["Resources"].values())
    # photos never leave S3 through a URL (no presigned links): only the Lambdas read them, with their roles;
    # the app shows the person's own copy from the phone
    src = Path(__file__).resolve().parents[1] / "src"
    code = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    assert "presigned" not in code and "generate_presigned_url" not in code and "s3.amazonaws.com" not in code
    assert bucket["LifecycleConfiguration"]["Rules"][0]["ExpirationInDays"] == 1
    # the collector deletes photos older than 24 h; the recovery function invokes itself for the worker
    assert "RecoveryBucket" in json.dumps(transformed["Resources"]["CollectFunctionRole"]["Properties"]["Policies"])
    role = json.dumps(transformed["Resources"]["RecoveryFunctionRole"]["Properties"]["Policies"])
    assert "lambda:InvokeFunction" in role and "function:climateguard-recovery" in role
    fn = transformed["Resources"]["RecoveryFunction"]["Properties"]
    assert fn["FunctionName"] == "climateguard-recovery" and fn["Environment"]["Variables"]["USE_CONTRIBUTOR"] == "false"
    retry = next(r for r in transformed["Resources"].values() if r["Type"] == "AWS::Lambda::EventInvokeConfig")
    assert retry["Properties"]["MaximumRetryAttempts"] == 0
