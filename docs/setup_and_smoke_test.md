# Qlib Local Setup and Smoke Test

Last verified: 2026-05-07

Workspace: `F:\Desktop\Trading\My Codes\qlib`

## Final Status

Status: **PASS for real local Qlib deployment**

The local environment can now run the core Qlib path on both the deterministic toy smoke dataset and the GitHub README recommended community dataset:

`provider_uri -> DataHandler -> Dataset -> Model -> SignalRecord -> SigAnaRecord -> Strategy -> Backtest -> PortAnaRecord`

Verified pieces:

| Check | Status | Notes |
| --- | --- | --- |
| Detect Python/package manager | PASS | Selected Python 3.12.13 + `venv` + `pip` |
| Install Qlib editable | PASS | Installed as `pyqlib 0.9.8.dev31` |
| `import qlib` | PASS | Version prints `0.9.8.dev31` |
| Core imports | PASS | `qlib.data`, `qlib.workflow`, `qlib.backtest`, `qlib.contrib.strategy` |
| Compiled data ops | PASS | `rolling_slope` and `expanding_slope` import and execute |
| Minimal local dataset | PASS | Generated under `.tmp\qlib_smoke_data_ok` |
| Data API smoke | PASS | Calendar, instruments, and feature expressions work |
| `qrun` smoke workflow | PASS | `SignalRecord`, `SigAnaRecord`, and `PortAnaRecord` all completed |
| Community dataset deployment | PASS | Downloaded and extracted to `C:\Users\rexch\.qlib\qlib_data\cn_data` |
| Real Data API check | PASS | `csi300` universe returns 300 instruments |
| Official Linear Alpha158 benchmark | PASS | Full `qrun` completed on real `csi300` data |
| Official LightGBM Alpha158 benchmark | PASS | Full `qrun` completed on real `csi300` data |
| Recent US Yahoo dataset | PASS | Built `us_data_recent` with 550 symbols, calendar through `2026-05-07` |
| Recent US Linear Alpha158 benchmark | PASS | Full `qrun` completed on `us_data_recent` + `sp500` |
| Reusable local scripts | PASS | `scripts\setup_community_data.ps1` and `scripts\run_real_benchmark.ps1` |

The smoke dataset is intentionally tiny. It proves the local plumbing works; it is not a research dataset and its metrics should not be interpreted as benchmark performance.

The real community dataset is now the default usable research dataset for the official benchmark configs.

## Environment Assumptions

- OS/shell: Windows PowerShell.
- Repo root: `F:\Desktop\Trading\My Codes\qlib`.
- `pyproject.toml` declares `requires-python = ">=3.8.0"` and classifiers for Python 3.8 through 3.12.
- `conda` was not detected.
- Windows `python.exe` points to the Microsoft Store stub and was not used.
- `py -3.12` was listed by the launcher but failed to start with `A specified logon session does not exist`.
- Exact choice for this workspace: Codex bundled Python 3.12.13, `.venv`, and `pip`.
- Local MSVC compiler was not detected, so source-building Qlib's Cython extensions was not possible in this environment.
- README says the official Microsoft-hosted dataset download is temporarily disabled, but the GitHub README provides a community dataset release as the current workaround. The smoke test uses a local generated dataset because it is smaller, deterministic, and sufficient for local wiring verification.

## Root Cause and Smallest Fix

Initial `pip install -e .` failed because `setup.py` builds two Cython/C++ extensions:

- `qlib.data._libs.rolling`
- `qlib.data._libs.expanding`

On Windows these need Microsoft Visual C++ 14.0+ Build Tools. Without them, `qlib.data`, `qlib.backtest`, `qlib.contrib.strategy`, and `qrun` fail because `qlib.data.ops` cannot import `qlib.data._libs.rolling`.

Smallest maintainable fix used here:

1. Do not change Qlib runtime core logic.
2. Add an opt-in `QLIB_SKIP_EXT_BUILD` switch in `setup.py`.
3. Reuse compatible prebuilt Windows CPython 3.12 `.pyd` extension files from the public `pyqlib==0.9.7` wheel for local smoke testing.
4. Install this fork in editable mode with `QLIB_SKIP_EXT_BUILD=1`.

This is a local development workaround for a machine without MSVC. For production, CI, or release packaging, prefer installing MSVC Build Tools and running normal editable install without `QLIB_SKIP_EXT_BUILD`.

## Files Added or Changed

- `.gitignore`: ignores `.venv/` and `.tmp/`.
- `setup.py`: adds explicit opt-in `QLIB_SKIP_EXT_BUILD`; default behavior still builds extensions.
- `examples/smoke/prepare_smoke_data.ps1`: generates the local smoke dataset.
- `examples/smoke/workflow_config_smoke_linear.yaml`: minimal `qrun` workflow using `DataHandlerLP`, `DatasetH`, `LinearModel`, `SignalRecord`, `SigAnaRecord`, `TopkDropoutStrategy`, and `PortAnaRecord`.
- `docs/setup_and_smoke_test.md`: this setup and verification record.

## Reproducible Setup

Create the local environment:

```powershell
& 'C:\Users\rexch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' --version
& 'C:\Users\rexch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
```

Install dependencies used by the smoke path:

```powershell
.\.venv\Scripts\python.exe -m pip install pyyaml numpy pandas mlflow filelock redis dill fire ruamel.yaml python-redis-lock tqdm pymongo loguru lightgbm gym cvxpy joblib matplotlib jupyter nbconvert pyarrow pydantic-settings setuptools-scm cython setuptools
```

If MSVC Build Tools are installed, use the normal editable install:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

If MSVC Build Tools are not installed, use the local fallback:

```powershell
.\.venv\Scripts\python.exe -m pip download pyqlib==0.9.7 --only-binary=:all: --no-deps --dest .tmp\qlib_wheels
```

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$wheel = Get-ChildItem .tmp\qlib_wheels\pyqlib-0.9.7-cp312-cp312-win_amd64.whl | Select-Object -First 1
$zip = [System.IO.Compression.ZipFile]::OpenRead($wheel.FullName)
foreach ($name in @("qlib/data/_libs/rolling.cp312-win_amd64.pyd", "qlib/data/_libs/expanding.cp312-win_amd64.pyd")) {
    $entry = $zip.GetEntry($name)
    $target = Join-Path (Get-Location) ($name -replace "/", "\")
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
}
$zip.Dispose()
```

```powershell
$env:QLIB_SKIP_EXT_BUILD = '1'
.\.venv\Scripts\python.exe -m pip install -e . --no-build-isolation
```

Verify editable install:

```powershell
.\.venv\Scripts\python.exe -m pip show pyqlib
```

Expected result includes:

```text
Name: pyqlib
Version: 0.9.8.dev31
Editable project location: F:\Desktop\Trading\My Codes\qlib
```

## Official and Community Dataset Options

The GitHub README currently gives three data-preparation routes:

1. **Community release recommended by README while the official dataset is disabled**

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.qlib\qlib_data\cn_data" | Out-Null
Invoke-WebRequest -Uri "https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz" -OutFile ".tmp\qlib_bin.tar.gz"
tar -xzf ".tmp\qlib_bin.tar.gz" -C "$env:USERPROFILE\.qlib\qlib_data\cn_data" --strip-components=1
Remove-Item ".tmp\qlib_bin.tar.gz"
```

2. **Official CLI path, documented but currently behind the disabled official dataset**

```powershell
.\.venv\Scripts\python.exe -m qlib.cli.data qlib_data --target_dir "$env:USERPROFILE\.qlib\qlib_data\cn_data" --region cn
```

For 1-minute data:

```powershell
.\.venv\Scripts\python.exe -m qlib.cli.data qlib_data --target_dir "$env:USERPROFILE\.qlib\qlib_data\cn_data_1min" --region cn --interval 1min
```

3. **Source script path, also documented by README**

```powershell
.\.venv\Scripts\python.exe scripts\get_data.py qlib_data --target_dir "$env:USERPROFILE\.qlib\qlib_data\cn_data" --region cn
```

For full benchmark workflows, use a real Qlib-format dataset such as the community release above, then run a benchmark config:

```powershell
.\.venv\Scripts\qrun.exe examples\benchmarks\Linear\workflow_config_linear_Alpha158.yaml
```

This document's `.tmp\qlib_smoke_data_ok` dataset remains the default for smoke testing because it avoids a large external download and isolates environment problems from data availability problems.

In this local deployment, the community dataset has already been downloaded and extracted to:

```text
C:\Users\rexch\.qlib\qlib_data\cn_data
```

The downloaded archive was:

```text
F:\Desktop\Trading\My Codes\qlib\.tmp\qlib_bin.tar.gz
```

Observed archive size:

```text
549,965,251 bytes
```

Reusable setup command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_community_data.ps1
```

Reusable real benchmark commands:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Model Linear
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Model LightGBM
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Model All
```

The benchmark scripts write experiment artifacts under:

```text
.tmp\mlruns_real
```

Recent US dataset update:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_us_recent_data.ps1 -Start 2020-01-01 -ChunkSize 40 -MaxWorkers 1 -SymbolSource current
```

Recent US benchmark:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region USRecent -Model Linear
```

The recent US benchmark writes experiment artifacts under:

```text
.tmp\mlruns_us_recent
```

## Real Benchmark Results

Official Linear Alpha158 on `csi300`:

```powershell
.\.venv\Scripts\qrun.exe examples\benchmarks\Linear\workflow_config_linear_Alpha158.yaml --experiment_name=real_linear_alpha158 --uri_folder=.tmp\mlruns_real
```

Observed result:

- Exit code: `0`
- Prediction artifact: `pred.pkl`
- Portfolio artifact: `port_analysis_1day.pkl`
- Signal metrics:
  - `IC`: `0.03206268386422084`
  - `Rank IC`: `0.042527052747594246`
  - `Long-Short Ann Return`: `0.20468032`
  - `Long-Short Ann Sharpe`: `3.1142504`
- Excess return with cost:
  - `annualized_return`: `0.071228`
  - `information_ratio`: `0.917967`
  - `max_drawdown`: `-0.104358`

Official LightGBM Alpha158 on `csi300`:

```powershell
.\.venv\Scripts\qrun.exe examples\benchmarks\LightGBM\workflow_config_lightgbm_Alpha158.yaml --experiment_name=real_lightgbm_alpha158 --uri_folder=.tmp\mlruns_real
```

Observed result:

- Exit code: `0`
- LightGBM early stopping best iteration: `23`
- Prediction artifact: `pred.pkl`
- Portfolio artifact: `port_analysis_1day.pkl`
- Signal metrics:
  - `IC`: `0.04703019872499099`
  - `Rank IC`: `0.04869434960382118`
- Excess return with cost:
  - `annualized_return`: `0.110624`
  - `information_ratio`: `1.305132`
  - `max_drawdown`: `-0.085821`

Recent US Linear Alpha158 on current-constituent `sp500`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region USRecent -Model Linear
```

Observed result:

- Exit code: `0`
- Data path: `C:\Users\rexch\.qlib\qlib_data\us_data_recent`
- Calendar: `2020-01-02` to `2026-05-07`
- Feature directories: `550`
- Prediction artifact: `pred.pkl`
- Portfolio artifact: `port_analysis_1day.pkl`
- Signal metrics:
  - `IC`: `-0.0002751393926463491`
  - `Rank IC`: `0.005866803344877897`
  - `Long-Short Ann Return`: `-0.0033080338`
  - `Long-Short Ann Sharpe`: `-0.06307939`
- Excess return with cost:
  - `annualized_return`: `-0.056324`
  - `information_ratio`: `-0.653539`
  - `max_drawdown`: `-0.161463`

This validates the current US research plumbing. It is not a claim that the default Alpha158 Linear strategy is profitable on recent US data.

## Import Verification

Version check:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; print(getattr(qlib, '__version__', '<missing>'))"
```

Expected:

```text
0.9.8.dev31
```

Core imports:

```powershell
.\.venv\Scripts\python.exe -c "import qlib.data; import qlib.workflow; import qlib.backtest; import qlib.contrib.strategy; print('basic imports ok')"
```

Expected:

```text
basic imports ok
```

Compiled extension smoke:

```powershell
.\.venv\Scripts\python.exe -c "from qlib.data._libs.rolling import rolling_slope; from qlib.data._libs.expanding import expanding_slope; import numpy as np; print(rolling_slope(np.array([1.,2.,3.,4.]), 2).tolist()); print(expanding_slope(np.array([1.,2.,3.,4.])).tolist())"
```

Expected:

```text
[nan, 1.0, 1.0, 1.0]
[nan, 1.0, 1.0, 1.0]
```

## Minimal Local Dataset

The helper script creates two instruments, seven trading days, and simple OHLCV fields. The last day exists so backtest settlement can look beyond the final test date.

```powershell
powershell -ExecutionPolicy Bypass -File examples\smoke\prepare_smoke_data.ps1
```

Expected:

```text
Prepared Qlib smoke data at .tmp\qlib_smoke_data_ok
```

Generated directories:

- `.tmp\qlib_smoke_raw`
- `.tmp\qlib_smoke_data_ok`

The script calls:

```powershell
$env:PYTHONPATH = $repoRoot.Path
.\.venv\Scripts\python.exe scripts\dump_bin.py dump_all --data_path .tmp\qlib_smoke_raw --qlib_dir .tmp\qlib_smoke_data_ok --freq day --max_workers 1 --exclude_fields symbol
```

`--exclude_fields symbol` is required because the binary feature dumper expects numeric feature columns.

## Data API Smoke

Calendar and instruments:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='.tmp/qlib_smoke_data_ok', region='cn', kernels=1); from qlib.data import D; print(D.calendar(start_time='2020-01-01', end_time='2020-01-08', freq='day')); print(D.list_instruments(D.instruments('all'), start_time='2020-01-01', end_time='2020-01-08', freq='day'))"
```

Feature expressions:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='.tmp/qlib_smoke_data_ok', region='cn', kernels=1); from qlib.data import D; fields=[chr(36)+'close', 'Ref('+chr(36)+'close, 1)', 'Mean('+chr(36)+'close, 2)']; print(D.features(['SH000001','SH000002'], fields, start_time='2020-01-01', end_time='2020-01-08', freq='day'))"
```

PowerShell expands `$close` inside double quotes, so the command above uses `chr(36)` to avoid shell interpolation.

Avoid running Qlib feature queries through PowerShell stdin heredocs on Windows. Qlib's multiprocessing import path can try to reload `<stdin>` and fail. Use `python -c` with `kernels=1` or a real `.py` file.

## qrun Smoke Workflow

Run:

```powershell
.\.venv\Scripts\qrun.exe examples\smoke\workflow_config_smoke_linear.yaml --experiment_name=smoke_local --uri_folder=.tmp\mlruns
```

Expected result:

- `LinearModel` trains and predicts on the toy dataset.
- `SignalRecord` writes `pred.pkl`.
- `SigAnaRecord` writes signal analysis artifacts.
- `TopkDropoutStrategy` runs through `SimulatorExecutor`.
- `PortAnaRecord` writes portfolio analysis artifacts.
- Exit code is `0`.

Observed prediction excerpt:

```text
                          score
datetime   instrument
2020-01-07 SH000001    0.006986
           SH000002    0.020196
2020-01-08 SH000001    0.014529
           SH000002    0.015423
```

Observed portfolio analysis excerpt:

```text
benchmark return(1day)
mean               0.004714
annualized_return  1.121871
information_ratio  3.724881
max_drawdown      -0.009091
```

Artifacts are written under `.tmp\mlruns`, including:

- `pred.pkl`
- `label.pkl`
- `ic.pkl`
- `ric.pkl`
- `report_normal_1day.pkl`
- `positions_normal_1day.pkl`
- `port_analysis_1day.pkl`
- `indicator_analysis_1day.pkl`
- `params.pkl`

## Non-blocking Warnings

These warnings appeared but did not block the smoke test:

- `CatBoostModel`, `XGBModel`, and PyTorch contrib models are skipped because optional dependencies are not installed.
- `gym` warns that it is unmaintained and does not support NumPy 2.0. Qlib imports still pass.
- MLflow warns that the filesystem tracking backend is deprecated as of February 2026. Local smoke artifacts still write correctly.
- Qlib warns that future calendar data is unavailable and returns the current calendar. This is acceptable for the toy daily smoke dataset.
- Tiny dataset metrics can emit `RuntimeWarning: Mean of empty slice`. This is expected from a two-instrument, two-day backtest.
- In the Codex sandbox only, MLflow's git logging hits `dubious ownership` warnings because the sandbox user differs from the checkout owner. The workflow still exits `0`. A normal user PowerShell run does not need this workaround; if needed in sandbox, run:

```powershell
git config --global --add safe.directory "F:/Desktop/Trading/My Codes/qlib"
```

## Failures Diagnosed and Fixed

| Failed command | Root cause | Fix |
| --- | --- | --- |
| `py -3.12 --version` | Windows launcher could not create the process: `A specified logon session does not exist` | Used bundled Python 3.12.13 |
| `.\.venv\Scripts\python.exe -m pip install -e .` | Sandbox network was blocked | Reran with network permission |
| `.\.venv\Scripts\python.exe -m pip install -e .` | Missing Microsoft Visual C++ 14.0+ Build Tools | Added opt-in `QLIB_SKIP_EXT_BUILD` and used prebuilt `.pyd` files for local smoke |
| `.\.venv\Scripts\python.exe -m pip download pyqlib --only-binary=:all: --dest .tmp\qlib_wheels` | Dependency resolution tried to satisfy packages without compatible binary wheels | Used `pyqlib==0.9.7 --no-deps` |
| `.\.venv\Scripts\python.exe scripts\dump_bin.py dump_all --data_path .tmp\qlib_smoke_raw --qlib_dir .tmp\qlib_smoke_data --freq day --max_workers 1` | Source tree was not installed/importable yet | Set `PYTHONPATH` to repo root |
| `dump_bin.py` with raw CSV including `symbol` as a feature | `symbol` is string data and cannot be written to numeric `.bin` features | Added `--exclude_fields symbol` |
| Initial qrun smoke config | Passed unsupported `fit_start_time` and `fit_end_time` into `DataHandlerLP` | Removed unsupported kwargs |
| Initial six-day smoke dataset qrun | Backtest needed one more calendar day after `end_time` | Added `2020-01-09` to both instruments |
| PowerShell stdin heredoc data query | Windows multiprocessing tried to reload `<stdin>` | Use `python -c` or a real `.py` file with `kernels=1` |

## Exact Commands Run

Environment detection:

```powershell
Get-Command conda -ErrorAction SilentlyContinue | Select-Object Source,Version
Get-Command python -ErrorAction SilentlyContinue | Select-Object Source,Version
Get-Command py -ErrorAction SilentlyContinue | Select-Object Source,Version
py -0p
py -3.12 --version
Get-Content -Raw pyproject.toml
Get-Content -Raw setup.py
Get-Command cl -ErrorAction SilentlyContinue | Select-Object Source,Version
Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio\Installer" -Filter vswhere.exe -Recurse -ErrorAction SilentlyContinue | Select-Object FullName
```

Environment setup:

```powershell
& 'C:\Users\rexch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' --version
& 'C:\Users\rexch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pip --version
& 'C:\Users\rexch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip list --format=columns
.\.venv\Scripts\python.exe -m pip install pyyaml numpy pandas mlflow filelock redis dill fire ruamel.yaml python-redis-lock tqdm pymongo loguru lightgbm gym cvxpy joblib matplotlib jupyter nbconvert pyarrow pydantic-settings setuptools-scm cython setuptools
```

Editable install and extension fallback:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -e . --no-build-isolation --no-deps
.\.venv\Scripts\python.exe -m pip download pyqlib --only-binary=:all: --dest .tmp\qlib_wheels
.\.venv\Scripts\python.exe -m pip download pyqlib==0.9.7 --only-binary=:all: --no-deps --dest .tmp\qlib_wheels
$env:QLIB_SKIP_EXT_BUILD = '1'
.\.venv\Scripts\python.exe -m pip install -e . --no-build-isolation
.\.venv\Scripts\python.exe -m pip show pyqlib
```

Verification:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; print(getattr(qlib, '__version__', '<missing>'))"
.\.venv\Scripts\python.exe -c "import qlib.data; import qlib.workflow; import qlib.backtest; import qlib.contrib.strategy; print('basic imports ok')"
.\.venv\Scripts\python.exe -c "from qlib.data._libs.rolling import rolling_slope; from qlib.data._libs.expanding import expanding_slope; import numpy as np; print(rolling_slope(np.array([1.,2.,3.,4.]), 2).tolist()); print(expanding_slope(np.array([1.,2.,3.,4.])).tolist())"
Test-Path .\.venv\Scripts\qrun.exe
```

Dataset and workflow:

```powershell
powershell -ExecutionPolicy Bypass -File examples\smoke\prepare_smoke_data.ps1
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='.tmp/qlib_smoke_data_ok', region='cn', kernels=1); from qlib.data import D; print(D.calendar(start_time='2020-01-01', end_time='2020-01-08', freq='day')); print(D.list_instruments(D.instruments('all'), start_time='2020-01-01', end_time='2020-01-08', freq='day'))"
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='.tmp/qlib_smoke_data_ok', region='cn', kernels=1); from qlib.data import D; fields=[chr(36)+'close', 'Ref('+chr(36)+'close, 1)', 'Mean('+chr(36)+'close, 2)']; print(D.features(['SH000001','SH000002'], fields, start_time='2020-01-01', end_time='2020-01-08', freq='day'))"
.\.venv\Scripts\qrun.exe examples\smoke\workflow_config_smoke_linear.yaml --experiment_name=smoke_local --uri_folder=.tmp\mlruns
```

Non-blocking command failure:

```powershell
Get-CimInstance Win32_Process ...
```

This failed with access denied while checking sandbox processes. It was not needed for the final smoke path.
