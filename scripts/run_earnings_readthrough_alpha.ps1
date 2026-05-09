param(
    [string]$FactorName = "ERT_v0_4_target_quality_readthrough_band",
    [string]$ProviderUri = (Join-Path $env:USERPROFILE ".qlib\qlib_data\us_data_recent"),
    [string]$Start = "2020-01-02",
    [string]$End = "2026-05-07",
    [string]$Symbols = "",
    [int]$Limit = 0,
    [string]$EventsPath = "",
    [string]$ApiKey = "",
    [double]$RequestDelaySeconds = 0,
    [Nullable[double]]$ScoreThreshold = $null,
    [Nullable[double]]$SelectionQuantile = $null,
    [double]$SelectionMinQuantile = 0.0,
    [double]$SelectionMaxQuantile = 0.80,
    [int]$LookbackDays = 45,
    [int]$PeerHalfLifeDays = 20,
    [int]$MinPeerEvents = 3,
    [int]$MinHistoryEvents = 20,
    [double]$MaxRunup5 = 0.05,
    [double]$MaxVolatility20 = 0.08,
    [double]$MinAvgDollarVolume20 = 20000000,
    [double]$MinPeerExcessHitRate = 0.50,
    [int]$MinTargetPriorEvents = 4,
    [double]$MinTargetPriorExcessMedian = 0.0
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot
$env:PYTHONPATH = $repoRoot.Path

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python was not found at $python. Create .venv first."
}

$argsList = @(
    "scripts\run_earnings_readthrough_alpha.py",
    "--factor-name", $FactorName,
    "--provider-uri", $ProviderUri,
    "--start", $Start,
    "--end", $End,
    "--request-delay-seconds", [string]$RequestDelaySeconds,
    "--selection-min-quantile", [string]$SelectionMinQuantile,
    "--selection-max-quantile", [string]$SelectionMaxQuantile,
    "--lookback-days", [string]$LookbackDays,
    "--peer-half-life-days", [string]$PeerHalfLifeDays,
    "--min-peer-events", [string]$MinPeerEvents,
    "--min-history-events", [string]$MinHistoryEvents,
    "--max-runup-5", [string]$MaxRunup5,
    "--max-volatility-20", [string]$MaxVolatility20,
    "--min-avg-dollar-volume-20", [string]$MinAvgDollarVolume20,
    "--min-peer-excess-hit-rate", [string]$MinPeerExcessHitRate,
    "--min-target-prior-events", [string]$MinTargetPriorEvents,
    "--min-target-prior-excess-median", [string]$MinTargetPriorExcessMedian
)

if ($null -ne $ScoreThreshold) {
    $argsList += @("--score-threshold", [string]$ScoreThreshold)
}

if ($null -ne $SelectionQuantile) {
    $argsList += @("--selection-quantile", [string]$SelectionQuantile)
}

if ($Symbols -ne "") {
    $argsList += @("--symbols", $Symbols)
}

if ($Limit -gt 0) {
    $argsList += @("--limit", [string]$Limit)
}

if ($EventsPath -ne "") {
    $argsList += @("--events-path", $EventsPath)
}

if ($ApiKey -ne "") {
    $argsList += @("--api-key", $ApiKey)
}

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "Earnings read-through run failed with exit code $LASTEXITCODE"
}
