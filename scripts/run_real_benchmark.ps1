param(
    [ValidateSet("CN", "US", "USRecent")]
    [string]$Region = "CN",
    [ValidateSet("Linear", "LightGBM", "All")]
    [string]$Model = "LightGBM",
    [string]$ExperimentUri = ".tmp\mlruns_real",
    [string]$DataDir = (Join-Path $env:USERPROFILE ".qlib\qlib_data\cn_data")
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$qrun = Join-Path $repoRoot ".venv\Scripts\qrun.exe"
if (-not (Test-Path $qrun)) {
    throw "qrun was not found at $qrun. Create .venv and install this fork in editable mode first."
}

if ($Region -eq "US" -and $PSBoundParameters.ContainsKey("DataDir") -eq $false) {
    $DataDir = Join-Path $env:USERPROFILE ".qlib\qlib_data\us_data"
    $ExperimentUri = ".tmp\mlruns_us"
}

if ($Region -eq "USRecent" -and $PSBoundParameters.ContainsKey("DataDir") -eq $false) {
    $DataDir = Join-Path $env:USERPROFILE ".qlib\qlib_data\us_data_recent"
    $ExperimentUri = ".tmp\mlruns_us_recent"
}

if (-not (Test-Path (Join-Path $DataDir "calendars\day.txt"))) {
    if ($Region -eq "USRecent") {
        throw "Qlib data was not found at $DataDir. Run scripts\update_us_recent_data.ps1 first."
    } elseif ($Region -eq "US") {
        throw "Qlib data was not found at $DataDir. Run scripts\setup_us_data.ps1 first."
    }
    throw "Qlib data was not found at $DataDir. Run scripts\setup_community_data.ps1 first."
}

$configsByRegion = @{
    CN = @{
        Linear = @{
            Config = "examples\benchmarks\Linear\workflow_config_linear_Alpha158.yaml"
            Experiment = "real_linear_alpha158"
        }
        LightGBM = @{
            Config = "examples\benchmarks\LightGBM\workflow_config_lightgbm_Alpha158.yaml"
            Experiment = "real_lightgbm_alpha158"
        }
    }
    US = @{
        Linear = @{
            Config = "examples\us\workflow_config_us_linear_Alpha158_sp500.yaml"
            Experiment = "us_linear_alpha158_sp500"
        }
    }
    USRecent = @{
        Linear = @{
            Config = "examples\us\workflow_config_us_recent_linear_Alpha158_sp500.yaml"
            Experiment = "us_recent_linear_alpha158_sp500"
        }
    }
}

$configs = $configsByRegion[$Region]

if ($Model -eq "All") {
    $models = @($configs.Keys)
} else {
    $models = @($Model)
}

foreach ($modelName in $models) {
    if (-not $configs.ContainsKey($modelName)) {
        throw "$Region $modelName benchmark is not configured yet."
    }
    $item = $configs[$modelName]
    Write-Host "Running $Region $modelName benchmark with $($item.Config)"
    & $qrun $item.Config "--experiment_name=$($item.Experiment)" "--uri_folder=$ExperimentUri"
    if ($LASTEXITCODE -ne 0) {
        throw "$modelName benchmark failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Benchmark run complete. Artifacts are under $ExperimentUri"
