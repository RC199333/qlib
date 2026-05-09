param(
    [string]$TargetDir = (Join-Path $env:USERPROFILE ".qlib\qlib_data\us_data_recent"),
    [string]$RawDir = (Join-Path $env:USERPROFILE ".qlib\stock_data\source\us_recent"),
    [string]$Start = "2020-01-01",
    [string]$End = "",
    [int]$Limit = 0,
    [int]$ChunkSize = 40,
    [int]$MaxWorkers = 1,
    [ValidateSet("current", "legacy")]
    [string]$SymbolSource = "current",
    [string]$SymbolsFile = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python was not found at $python. Create .venv first."
}

$argsList = @(
    "scripts\update_us_recent_data.py",
    "--target-qlib-dir", $TargetDir,
    "--raw-dir", $RawDir,
    "--start", $Start,
    "--chunk-size", [string]$ChunkSize,
    "--max-workers", [string]$MaxWorkers,
    "--symbol-source", $SymbolSource
)

if ($End -ne "") {
    $argsList += @("--end", $End)
}

if ($Limit -gt 0) {
    $argsList += @("--limit", [string]$Limit)
}

if ($SymbolsFile -ne "") {
    $argsList += @("--symbols-file", $SymbolsFile)
}

& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "US recent data update failed with exit code $LASTEXITCODE"
}
