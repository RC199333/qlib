param(
    [string]$DataDir = (Join-Path $env:USERPROFILE ".qlib\qlib_data\cn_data"),
    [string]$Archive = ".tmp\qlib_bin.tar.gz",
    [string]$Url = "https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Test-QlibDataDir {
    param([string]$Path)

    return (
        (Test-Path (Join-Path $Path "calendars\day.txt")) -and
        (Test-Path (Join-Path $Path "features")) -and
        (Test-Path (Join-Path $Path "instruments"))
    )
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if ((Test-QlibDataDir $DataDir) -and -not $Force) {
    Write-Host "Qlib community data already exists at $DataDir"
    exit 0
}

$archiveDir = Split-Path -Parent $Archive
if ($archiveDir) {
    New-Item -ItemType Directory -Force $archiveDir | Out-Null
}
New-Item -ItemType Directory -Force $DataDir | Out-Null

Write-Host "Downloading Qlib community data from $Url"
Invoke-WebRequest -Uri $Url -OutFile $Archive

$archiveItem = Get-Item $Archive
Write-Host ("Downloaded {0:N1} MB to {1}" -f ($archiveItem.Length / 1MB), $archiveItem.FullName)

Write-Host "Extracting to $DataDir"
tar -xzf $Archive -C $DataDir --strip-components=1

if (-not (Test-QlibDataDir $DataDir)) {
    throw "Extracted data does not look like a Qlib data directory: $DataDir"
}

Write-Host "Qlib community data is ready at $DataDir"
