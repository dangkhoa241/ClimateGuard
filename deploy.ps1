<#
Deploy the ClimateGuard backend with SAM (Windows PowerShell 5.1+).

  .\deploy.ps1 -PreflightOnly                        # dry run: permission + free-tier checks only
  .\deploy.ps1 -Contact you@example.com              # preflight, sam build, then sam deploy (shows the change set first)
  .\deploy.ps1 -Contact you@example.com -FrontendUrl https://your-app.vercel.app
  .\deploy.ps1 -Contact you@example.com -SkipBuild   # deploy the existing .aws-sam build as is

sam build needs the same Python as the Lambda runtime (3.12). The script finds Python 3.12 itself
(py launcher, then the usual install folders) and puts it first on PATH for the build only, so it
works even when PATH or an active .venv points to another version. Your PATH is restored afterwards.

The preflight checks, in the target region and without creating anything, every service the stack
uses. An explicitly denied action (e.g. an Organizations SCP) is reported as
"DENIED -> service 'x', action 'x:Y'" and the deploy stops before SAM runs. It also checks that the
SSM SecureStrings exist (value lengths only, never values) and that DynamoDB provisioned capacity,
summed over every table in every region, stays within the free 25 RCU / 25 WCU.
Safe to re-run: sam deploy only applies differences.
#>
param(
    [string]$Contact = "",                    # NWS asks for contact info in the User-Agent
    [string]$FrontendUrl = "http://localhost:5173",
    [string]$StackName = "climateguard",
    [string]$Region = "us-east-2",            # this account's SCP denies us-west-2 and us-east-1
    [int]$MaxSubscribers = 500,
    [switch]$PreflightOnly,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$FreeRcu = 25; $FreeWcu = 25
$BasetenParam = "/climateguard/baseten-api-key"
$AirNowParam = "/climateguard/airnow-api-key"
$MetaParam = "/climateguard/meta-model-api-key"
$PythonVersion = "3.12"   # must match Runtime: python3.12 in template.yaml

# Folder of a Python $PythonVersion python.exe, or $null. The py launcher knows every registered install.
function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try { $exe = & py "-$PythonVersion" -c "import sys; print(sys.executable)" 2>$null } finally { $ErrorActionPreference = $prev }
        if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += "$exe".Trim() }
    }
    $folder = "Python" + $PythonVersion.Replace(".", "")
    $candidates += @((Join-Path $env:LOCALAPPDATA "Programs\Python\$folder\python.exe"),
                     (Join-Path $env:ProgramFiles "$folder\python.exe"))
    foreach ($c in $candidates) {
        if (-not (Test-Path $c)) { continue }
        $v = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])"
        if ("$v".Trim() -eq $PythonVersion) { return (Split-Path $c) }
    }
    return $null
}

# Run the AWS CLI without ever throwing. (In PowerShell 5.1, redirecting a native command's stderr
# while ErrorActionPreference is Stop raises a terminating error: that was the old report's crash.)
function Invoke-Aws([string[]]$AwsArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $out = & aws @AwsArgs 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $prev }
    [pscustomobject]@{ Ok = ($LASTEXITCODE -eq 0); Text = (($out | Where-Object { $_ }) -join "`n").Trim() }
}

function Get-Denial([string]$text) {
    if ($text -notmatch "AccessDenied|not authorized|UnauthorizedOperation") { return $null }
    $action = if ($text -match "perform: ([a-z0-9-]+:[A-Za-z0-9]+)") { $Matches[1] } else { "unknown action" }
    $why = if ($text -match "service control policy") { "Organizations SCP, explicit deny" } else { "IAM policy" }
    [pscustomobject]@{ Service = $action.Split(":")[0]; Action = $action; Why = $why }
}

$script:failures = 0; $script:warnings = 0
function Report([string]$check, [string]$status, [string]$detail = "") {
    $color = @{ OK = "Green"; WARN = "Yellow"; FAIL = "Red"; DENIED = "Red" }[$status]
    if ($status -in "FAIL", "DENIED") { $script:failures++ } elseif ($status -eq "WARN") { $script:warnings++ }
    Write-Host ("  {0,-6} {1,-34} {2}" -f $status, $check, $detail) -ForegroundColor $color
}

# Probe one permission. $allowedIf: a regex for an error that proves the call got past authorization
# (e.g. a validation error), so nothing is ever created.
function Test-Permission([string]$check, [string[]]$awsArgs, [string]$allowedIf = "") {
    $r = Invoke-Aws $awsArgs
    if ($r.Ok -or ($allowedIf -and $r.Text -match $allowedIf)) { Report $check "OK"; return }
    $d = Get-Denial $r.Text
    if ($d) { Report $check "DENIED" "-> service '$($d.Service)', action '$($d.Action)' ($($d.Why))"; return }
    Report $check "FAIL" (($r.Text -split "`n")[0])
}

Write-Host "`nPreflight for stack '$StackName' in $Region" -ForegroundColor Cyan
$who = Invoke-Aws @("sts", "get-caller-identity", "--query", "Arn", "--output", "text")
if (-not $who.Ok) { Write-Host "  Not signed in to AWS: $($who.Text)" -ForegroundColor Red; exit 1 }
Write-Host ("  as {0}" -f ($who.Text -replace "\d{12}", "<account>"))

Write-Host "`n[1/4] Template parameters"
# Origins are compared exactly (API Gateway rejects duplicates), so normalize before deciding.
$FrontendUrl = $FrontendUrl.Trim().TrimEnd("/").ToLowerInvariant()
$tpl = Get-Content (Join-Path $PSScriptRoot "template.yaml") -Raw
$localDev = @([regex]::Matches($tpl, "LocalDevOrigin2?:\s*\r?\n\s*Type: String\s*\r?\n\s*Default:\s*(\S+)") |
    ForEach-Object { $_.Groups[1].Value.ToLowerInvariant() })
if (-not $localDev) { $localDev = @("http://localhost:5173", "http://localhost:5174") }
if ($FrontendUrl -notmatch "^https?://[a-z0-9.-]+(:\d{1,5})?$") {
    Report "FrontendUrl" "FAIL" "'$FrontendUrl' must be a bare origin like https://app.vercel.app (no path)"
}
elseif ($tpl -notmatch "CorsConfiguration: !If\s*\r?\n\s*- FrontendIsLocalDev") {
    Report "CORS AllowOrigins" "FAIL" "template.yaml lost the FrontendIsLocalDev condition; origins could be duplicated"
}
else {
    $origins = if ($localDev -contains $FrontendUrl) { $localDev } else { @($FrontendUrl) + $localDev }
    $dupes = $origins | Group-Object | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name }
    if ($dupes) { Report "CORS AllowOrigins" "FAIL" "duplicate origin(s): $($dupes -join ', ')" }
    else { Report "CORS AllowOrigins" "OK" ($origins -join ", ") }
}

Write-Host "`n[2/4] Permissions (nothing is created)"
Test-Permission "cloudformation:CreateChangeSet" @("cloudformation", "create-change-set", "--region", $Region,
    "--stack-name", "$StackName-preflight-probe", "--change-set-name", "probe", "--change-set-type", "CREATE",
    "--template-body", '{\"Resources\":{}}') "Template format error|ValidationError"
Test-Permission "cloudformation:DescribeStacks" @("cloudformation", "describe-stacks", "--region", $Region,
    "--stack-name", $StackName) "does not exist"
Test-Permission "s3:ListBuckets (SAM uploads)" @("s3api", "list-buckets", "--region", $Region, "--max-items", "1")
Test-Permission "iam:GetRole (roles for Lambda)" @("iam", "get-role", "--role-name", "climateguard-preflight-nonexistent") "NoSuchEntity"
Test-Permission "lambda:ListFunctions" @("lambda", "list-functions", "--region", $Region, "--max-items", "1")
Test-Permission "dynamodb:ListTables" @("dynamodb", "list-tables", "--region", $Region, "--max-items", "1")
Test-Permission "sns:ListTopics" @("sns", "list-topics", "--region", $Region)
Test-Permission "scheduler:ListSchedules" @("scheduler", "list-schedules", "--region", $Region, "--max-results", "1")
Test-Permission "apigateway:GET (HTTP APIs)" @("apigatewayv2", "get-apis", "--region", $Region, "--max-results", "1")
Test-Permission "logs:DescribeLogGroups" @("logs", "describe-log-groups", "--region", $Region, "--limit", "1")
Test-Permission "ssm:DescribeParameters" @("ssm", "describe-parameters", "--region", $Region, "--max-items", "1")

Write-Host "`n[3/4] API keys in SSM Parameter Store (lengths only, never values)"
foreach ($p in @(@{ Name = $BasetenParam; Required = $true },
                 @{ Name = $AirNowParam; Required = $false; IfMissing = "AQI will use Open-Meteo instead of AirNow" },
                 @{ Name = $MetaParam; Required = $false; IfMissing = "zh/tl/ko/ar alerts go out in English with a note" })) {
    $r = Invoke-Aws @("ssm", "get-parameter", "--region", $Region, "--name", $p.Name, "--with-decryption",
        "--query", "[Parameter.Type, length(Parameter.Value)]", "--output", "text")
    if ($r.Ok) {
        $type, $len = $r.Text -split "\s+"
        if ($type -eq "SecureString") { Report $p.Name "OK" "SecureString, $len characters" }
        else { Report $p.Name "WARN" "type is $type, expected SecureString" }
    }
    elseif ($r.Text -match "ParameterNotFound") {
        if ($p.Required) { Report $p.Name "FAIL" "missing: store it first (README, Deploy step 3)" }
        else { Report $p.Name "WARN" "missing: $($p.IfMissing)" }
    }
    elseif ($d = Get-Denial $r.Text) { Report $p.Name "DENIED" "-> service '$($d.Service)', action '$($d.Action)' ($($d.Why))" }
    else { Report $p.Name "FAIL" (($r.Text -split "`n")[0]) }
}

Write-Host "`n[4/4] DynamoDB free tier: provisioned capacity across ALL tables in ALL regions"
$regions = Invoke-Aws @("account", "list-regions", "--region-opt-status-contains", "ENABLED", "ENABLED_BY_DEFAULT",
    "--query", "Regions[].RegionName", "--output", "text")
if ($regions.Ok) { $regionList = $regions.Text -split "\s+" }
else {
    $regionList = "us-east-1 us-east-2 us-west-1 us-west-2 ca-central-1 sa-east-1 eu-west-1 eu-west-2 eu-west-3 eu-central-1 eu-north-1 ap-south-1 ap-northeast-1 ap-northeast-2 ap-northeast-3 ap-southeast-1 ap-southeast-2" -split " "
    Write-Host "  (account:ListRegions unavailable; checking the 17 default regions)"
}
$otherRcu = 0; $otherWcu = 0; $blocked = @()
foreach ($reg in $regionList) {
    $t = Invoke-Aws @("dynamodb", "list-tables", "--region", $reg, "--query", "TableNames", "--output", "text")
    if (-not $t.Ok) { $blocked += $reg; continue }
    foreach ($name in ($t.Text -split "\s+" | Where-Object { $_ -and $_ -ne "None" })) {
        if ($name -like "climateguard-*" -and $reg -eq $Region) { continue }  # replaced by the template's values
        $d = Invoke-Aws @("dynamodb", "describe-table", "--region", $reg, "--table-name", $name, "--output", "json")
        if (-not $d.Ok) { continue }
        $tbl = ($d.Text | ConvertFrom-Json).Table
        $mode = if ($tbl.BillingModeSummary) { $tbl.BillingModeSummary.BillingMode } else { "PROVISIONED" }
        if ($mode -ne "PROVISIONED") { continue }
        $r = [int]$tbl.ProvisionedThroughput.ReadCapacityUnits; $w = [int]$tbl.ProvisionedThroughput.WriteCapacityUnits
        foreach ($g in @($tbl.GlobalSecondaryIndexes)) { if ($g) { $r += [int]$g.ProvisionedThroughput.ReadCapacityUnits; $w += [int]$g.ProvisionedThroughput.WriteCapacityUnits } }
        Write-Host ("         {0,-28} {1,-10} RCU {2,3}  WCU {3,3}" -f $name, $reg, $r, $w)
        $otherRcu += $r; $otherWcu += $w
    }
}
# ($tpl was read in step 1)
$cgRcu = ([regex]::Matches($tpl, "ReadCapacityUnits:\s*(\d+)") | ForEach-Object { [int]$_.Groups[1].Value } | Measure-Object -Sum).Sum
$cgWcu = ([regex]::Matches($tpl, "WriteCapacityUnits:\s*(\d+)") | ForEach-Object { [int]$_.Groups[1].Value } | Measure-Object -Sum).Sum
Write-Host ("         {0,-28} {1,-10} RCU {2,3}  WCU {3,3}" -f "climateguard-* (template)", $Region, $cgRcu, $cgWcu)
$totR = $otherRcu + $cgRcu; $totW = $otherWcu + $cgWcu
$msg = "total RCU $totR / $FreeRcu, WCU $totW / $FreeWcu"
if ($totR -le $FreeRcu -and $totW -le $FreeWcu) { Report "DynamoDB provisioned capacity" "OK" $msg }
else { Report "DynamoDB provisioned capacity" "WARN" "${msg}: over the free tier (paid from Free plan credits)" }
if ($blocked) { Write-Host ("         not readable (SCP region deny, so no tables can be created there): {0}" -f ($blocked -join ", ")) }

Write-Host ""
if ($script:failures) {
    Write-Host "Preflight: $($script:failures) problem(s). Nothing was deployed." -ForegroundColor Red
    exit 1
}
Write-Host "Preflight passed ($($script:warnings) warning(s))." -ForegroundColor Green
if ($PreflightOnly) { exit 0 }

if (-not $Contact -or $Contact -match "\s") { throw "Pass -Contact you@example.com (no spaces) for the NWS User-Agent." }

if ($SkipBuild) {
    if (-not (Test-Path (Join-Path $PSScriptRoot ".aws-sam\build\template.yaml"))) { throw "-SkipBuild, but there is no .aws-sam build yet: run without it." }
    Write-Host "`nSkipping sam build (-SkipBuild): deploying the existing .aws-sam build." -ForegroundColor Yellow
}
else {
    $pyDir = Find-Python
    if (-not $pyDir) {
        Write-Host "`nPython $PythonVersion not found (needed by sam build for the python$PythonVersion Lambda runtime)." -ForegroundColor Red
        Write-Host "  Install it: winget install --id Python.Python.$PythonVersion -e"
        exit 1
    }
    Write-Host "`nsam build with Python $PythonVersion from $pyDir" -ForegroundColor Cyan
    $savedPath = $env:Path
    try {
        # first on PATH for this build only (beats PATH order and an active .venv)
        $env:Path = "$pyDir;$(Join-Path $pyDir 'Scripts');$savedPath"
        Push-Location $PSScriptRoot
        try { sam build } finally { Pop-Location }
        $buildCode = $LASTEXITCODE
    }
    finally { $env:Path = $savedPath }
    if ($buildCode -ne 0) { Write-Host "`nsam build failed (exit $buildCode). Nothing was deployed." -ForegroundColor Red; exit $buildCode }
}
$overrides = @(
    "FrontendUrl=$FrontendUrl",
    "MaxSubscribers=$MaxSubscribers",
    "NwsUserAgent=ClimateGuard/0.1(+mailto:$Contact)"   # no spaces: survives argument parsing
)
Write-Host "`nDeploying '$StackName' to $Region (SAM shows the change set and waits for 'y')`n" -ForegroundColor Cyan
Push-Location $PSScriptRoot
sam deploy --stack-name $StackName --region $Region --resolve-s3 --capabilities CAPABILITY_IAM `
    --confirm-changeset --no-fail-on-empty-changeset --tags Project=climateguard --parameter-overrides $overrides
$code = $LASTEXITCODE
Pop-Location

if ($code -ne 0) {
    Write-Host "`nDeploy failed (exit $code)." -ForegroundColor Red
    foreach ($stack in @($StackName, "aws-sam-cli-managed-default")) {
        $ev = Invoke-Aws @("cloudformation", "describe-stack-events", "--region", $Region, "--stack-name", $stack,
            "--query", "StackEvents[?contains(ResourceStatus, 'FAILED')].[LogicalResourceId, ResourceStatusReason]",
            "--output", "json")
        if (-not $ev.Ok) {
            if ($ev.Text -match "does not exist") { Write-Host "  [$stack] stack does not exist: nothing was created there." }
            elseif ($d = Get-Denial $ev.Text) { Write-Host "  [$stack] cannot read events: DENIED -> service '$($d.Service)', action '$($d.Action)' ($($d.Why))" -ForegroundColor Yellow }
            else { Write-Host "  [$stack] cannot read events: $(($ev.Text -split "`n")[0])" }
            continue
        }
        foreach ($e in @($ev.Text | ConvertFrom-Json)) {
            if (-not $e) { continue }
            $reason = [string]$e[1]
            Write-Host "  [$stack] $($e[0]): $reason"
            if ($d = Get-Denial $reason) { Write-Host "     DENIED -> service '$($d.Service)', action '$($d.Action)' ($($d.Why))" -ForegroundColor Yellow }
        }
    }
    Write-Host "  If the denial came before CloudFormation started, it is in the sam output above (look for 'not authorized to perform')."
    Write-Host "  A failed FIRST deploy leaves the stack in ROLLBACK_COMPLETE: run 'sam delete --stack-name $StackName --region $Region --no-prompts' before retrying."
    exit $code
}

$api = Invoke-Aws @("cloudformation", "describe-stacks", "--region", $Region, "--stack-name", $StackName,
    "--query", "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue", "--output", "text")
Write-Host "`nDeployed. API URL: $($api.Text)" -ForegroundColor Green
