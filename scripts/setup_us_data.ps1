param(
    [string]$DataDir = (Join-Path $env:USERPROFILE ".qlib\qlib_data\us_data"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python was not found at $python. Create .venv first."
}

if ((Test-Path (Join-Path $DataDir "calendars\day.txt")) -and -not $Force) {
    Write-Host "Qlib US data already exists at $DataDir"
    exit 0
}

New-Item -ItemType Directory -Force $DataDir | Out-Null

& $python scripts\get_data.py qlib_data `
    --target_dir $DataDir `
    --region us `
    --interval 1d `
    --exists_skip True `
    --delete_old False

if ($LASTEXITCODE -ne 0) {
    throw "US Qlib data download failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path (Join-Path $DataDir "calendars\day.txt"))) {
    throw "Downloaded data does not look like a Qlib data directory: $DataDir"
}

Write-Host "Qlib US data is ready at $DataDir"
