<#
Deploy the ClimateGuard backend with SAM (Windows PowerShell 5.1+). Run `sam build` first.

Reads BASETEN_API_KEY (required) and AIRNOW_API_KEY (optional) from .env and passes them as
NoEcho CloudFormation parameters, so keys never appear in the command line you type, in
samconfig.toml, or in your shell history.

  .\deploy.ps1 -Contact you@example.com
  .\deploy.ps1 -Contact you@example.com -FrontendUrl https://your-app.vercel.app

On failure it lists every denied AWS action (e.g. an Organizations SCP) from the stack events.
#>
param(
    [Parameter(Mandatory = $true)][string]$Contact,          # NWS asks for contact info in the User-Agent
    [string]$FrontendUrl = "http://localhost:5173",
    [string]$StackName = "climateguard",
    [string]$Region = "us-west-2",
    [int]$MaxSubscribers = 500
)
$ErrorActionPreference = "Stop"

function Read-EnvValue([string]$name) {
    $line = Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if ($line) { return ($line -replace "^$name=", "").Trim().Trim('"') }
    return ""
}

$baseten = Read-EnvValue "BASETEN_API_KEY"
$airnow = Read-EnvValue "AIRNOW_API_KEY"
if (-not $baseten) { throw "BASETEN_API_KEY is missing from .env" }
if ($Contact -match "\s") { throw "-Contact must not contain spaces (e.g. you@example.com)" }

$overrides = @(
    "BasetenApiKey=$baseten",
    "AirNowApiKey=$airnow",
    "FrontendUrl=$FrontendUrl",
    "MaxSubscribers=$MaxSubscribers",
    "NwsUserAgent=ClimateGuard/0.1(+mailto:$Contact)"   # no spaces: survives argument parsing
)

Write-Host "Deploying stack '$StackName' to $Region (keys from .env: Baseten=set, AirNow=$(if ($airnow) {'set'} else {'empty -> Open-Meteo'}))"
sam deploy --stack-name $StackName --region $Region --resolve-s3 --capabilities CAPABILITY_IAM `
    --confirm-changeset --no-fail-on-empty-changeset --parameter-overrides $overrides
$code = $LASTEXITCODE
Remove-Variable baseten, airnow, overrides

if ($code -ne 0) {
    Write-Host "`nDeploy failed (exit $code). Failed resources and denied actions:" -ForegroundColor Red
    foreach ($stack in @($StackName, "aws-sam-cli-managed-default")) {
        $events = aws cloudformation describe-stack-events --stack-name $stack --region $Region `
            --query "StackEvents[?contains(ResourceStatus, 'FAILED')].[Timestamp, LogicalResourceId, ResourceStatusReason]" `
            --output json 2>$null | ConvertFrom-Json
        foreach ($e in $events) {
            $reason = [string]$e[2]
            $denied = [regex]::Matches($reason, "perform: ([a-z0-9-]+:[A-Za-z0-9]+)") | ForEach-Object { $_.Groups[1].Value }
            Write-Host ("[{0}] {1}: {2}" -f $stack, $e[1], $reason)
            foreach ($d in $denied) {
                $scp = if ($reason -match "service control policy") { " (blocked by an Organizations SCP)" } else { "" }
                Write-Host "   DENIED -> service '$($d.Split(':')[0])', action '$d'$scp" -ForegroundColor Yellow
            }
        }
    }
    exit $code
}

$api = aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
Write-Host "`nDeployed. API URL: $api" -ForegroundColor Green
