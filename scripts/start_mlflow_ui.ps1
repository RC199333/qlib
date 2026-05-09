param(
    [string]$TrackingUri = ".tmp\mlruns_real",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$mlflow = Join-Path $repoRoot ".venv\Scripts\mlflow.exe"
if (-not (Test-Path $mlflow)) {
    throw "mlflow.exe was not found at $mlflow. Install the project dependencies first."
}

New-Item -ItemType Directory -Force $TrackingUri | Out-Null

Write-Host "Starting MLflow UI at http://127.0.0.1:$Port"
Write-Host "Tracking URI: $TrackingUri"
& $mlflow ui --backend-store-uri $TrackingUri --host 127.0.0.1 --port $Port
