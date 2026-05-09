$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

$rawDir = ".tmp\qlib_smoke_raw"
$qlibDir = ".tmp\qlib_smoke_data_ok"

New-Item -ItemType Directory -Force $rawDir | Out-Null

@'
date,symbol,open,close,high,low,volume,factor
2020-01-01,SH000001,10.0,10.2,10.4,9.9,1000000,1.0
2020-01-02,SH000001,10.2,10.4,10.6,10.1,1100000,1.0
2020-01-03,SH000001,10.4,10.3,10.5,10.0,900000,1.0
2020-01-06,SH000001,10.3,10.8,11.0,10.2,1300000,1.0
2020-01-07,SH000001,10.8,11.0,11.2,10.6,1250000,1.0
2020-01-08,SH000001,11.0,10.9,11.1,10.7,980000,1.0
2020-01-09,SH000001,10.9,11.1,11.3,10.8,1010000,1.0
'@ | Set-Content -Encoding UTF8 (Join-Path $rawDir "sh000001.csv")

@'
date,symbol,open,close,high,low,volume,factor
2020-01-01,SH000002,20.0,20.1,20.3,19.8,800000,1.0
2020-01-02,SH000002,20.1,20.0,20.2,19.7,850000,1.0
2020-01-03,SH000002,20.0,20.4,20.5,19.9,900000,1.0
2020-01-06,SH000002,20.4,20.6,20.8,20.2,920000,1.0
2020-01-07,SH000002,20.6,20.7,20.9,20.4,870000,1.0
2020-01-08,SH000002,20.7,21.0,21.2,20.5,940000,1.0
2020-01-09,SH000002,21.0,21.2,21.4,20.9,960000,1.0
'@ | Set-Content -Encoding UTF8 (Join-Path $rawDir "sh000002.csv")

$env:PYTHONPATH = $repoRoot.Path
.\.venv\Scripts\python.exe scripts\dump_bin.py dump_all `
    --data_path $rawDir `
    --qlib_dir $qlibDir `
    --freq day `
    --max_workers 1 `
    --exclude_fields symbol

Write-Host "Prepared Qlib smoke data at $qlibDir"
