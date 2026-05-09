# Qlib Data Sources and Usage

Last verified: 2026-05-07

## Local Data Inventory

### China A-share dataset

Path:

```text
C:\Users\rexch\.qlib\qlib_data\cn_data
```

Source:

- GitHub README recommended community release: `https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz`

Local coverage:

- Frequency: daily
- Calendar: `2000-01-04` to `2026-05-07`
- Feature directories: `6091`
- Universes:
  - `all`
  - `csi300`
  - `csi500`
  - `csi800`
  - `csi1000`
  - `csiall`
- Example fields:
  - `$open`
  - `$high`
  - `$low`
  - `$close`
  - `$adjclose`
  - `$volume`
  - `$amount`
  - `$vwap`
  - `$factor`
  - `$change`

### US dataset

Path:

```text
C:\Users\rexch\.qlib\qlib_data\us_data
```

Source:

- Qlib `scripts/get_data.py qlib_data --region us --interval 1d`
- The downloaded data is collected from Yahoo Finance and distributed as ready-made Qlib `.bin` data.

Local coverage:

- Frequency: daily
- Calendar: `1999-12-31` to `2020-11-10`
- Feature directories: `8994`
- `all` universe active count on `2020-01-02`: `8128`
- Universes:
  - `all`
  - `sp500`
  - `nasdaq100`
- Confirmed available ETFs/stocks:
  - `SPY`
  - `QQQ`
  - `IWM`
  - `DIA`
  - `AAPL`
  - `MSFT`
  - `NVDA`
  - `TSLA`
- Example benchmark symbols:
  - `^GSPC`
  - `^NDX`
  - `^DJI`
- Example fields:
  - `$open`
  - `$high`
  - `$low`
  - `$close`
  - `$volume`
  - `$factor`
  - `$change`

Important limitation: the ready-made US dataset is not current. Use it for reproducible historical research and benchmark development. For latest US data, use Qlib's Yahoo collector or another API-backed data adapter.

### Recent US dataset

Path:

```text
C:\Users\rexch\.qlib\qlib_data\us_data_recent
```

Raw CSV cache:

```text
C:\Users\rexch\.qlib\stock_data\source\us_recent
```

Source:

- Current S&P 500 constituents from Wikipedia.
- Current NASDAQ 100 constituents from Wikipedia.
- Core liquid ETFs listed in `scripts/update_us_recent_data.py`.
- Benchmarks: `^GSPC`, `^NDX`, `^DJI`.
- Daily OHLCV downloaded from Yahoo Finance through `yahooquery`.
- Converted to Qlib `.bin` format through `scripts/dump_bin.py`.

Local coverage:

- Frequency: daily
- Calendar: `2020-01-02` to `2026-05-07`
- Feature directories: `550`
- Universes:
  - `all`
  - `sp500`
  - `nasdaq100`
  - `etf_core`
  - `benchmarks`
- Confirmed available ETFs/stocks/indexes:
  - `SPY`
  - `QQQ`
  - `AAPL`
  - `MSFT`
  - `NVDA`
  - `^GSPC`

Important limitations:

- This dataset uses **current** index constituents, not point-in-time historical membership. It is suitable for local research iteration and agent development, but it is not a production-grade survivorship-bias-free index backtest dataset.
- Yahoo Finance data is research-grade. For institutional production, use a licensed market data source with corporate actions, delistings, and point-in-time universe membership.
- OHLC prices are adjusted by the Yahoo `adjclose / close` ratio. Volume is left unadjusted.

## Setup Commands

China dataset:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_community_data.ps1
```

US dataset:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_us_data.ps1
```

Yahoo collector dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts\data_collector\yahoo\requirements.txt
```

Recent US dataset:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_us_recent_data.ps1 -Start 2020-01-01 -ChunkSize 40 -MaxWorkers 1 -SymbolSource current
```

Retry only failed symbols, if Yahoo has a temporary network failure:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_us_recent_data.ps1 -Start 2020-01-01 -ChunkSize 10 -MaxWorkers 1 -SymbolSource current -SymbolsFile "$env:USERPROFILE\.qlib\stock_data\source\us_recent\_failed_symbols.txt"
```

## Run Benchmarks

China Linear or LightGBM:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region CN -Model Linear
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region CN -Model LightGBM
```

US SP500 Linear:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region US -Model Linear
```

Recent US SP500 Linear:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region USRecent -Model Linear
```

Direct US workflow:

```powershell
.\.venv\Scripts\qrun.exe examples\us\workflow_config_us_linear_Alpha158_sp500.yaml --experiment_name=us_linear_alpha158_sp500 --uri_folder=.tmp\mlruns_us
```

Verified US run result:

- Exit code: `0`
- Universe: `sp500`
- Benchmark: `^GSPC`
- Model: `LinearModel`
- Handler: `Alpha158`
- Artifacts: `.tmp\mlruns_us`
- Signal metrics:
  - `IC`: `0.007827875830258716`
  - `Rank IC`: `0.011057758052253978`
  - `Long-Short Ann Return`: `0.07195256`
  - `Long-Short Ann Sharpe`: `0.91818875`
- Excess return with cost:
  - `annualized_return`: `-0.034260`
  - `information_ratio`: `-0.560766`
  - `max_drawdown`: `-0.207737`

This is a working pipeline check, not a claim that the default Alpha158 Linear US strategy is profitable after costs.

Verified recent US run result:

- Exit code: `0`
- Dataset: `C:\Users\rexch\.qlib\qlib_data\us_data_recent`
- Universe: `sp500`
- Benchmark: `^GSPC`
- Model: `LinearModel`
- Handler: `Alpha158`
- Backtest window: `2024-01-02` to `2026-05-05`
- Artifacts: `.tmp\mlruns_us_recent`
- Signal metrics:
  - `IC`: `-0.0002751393926463491`
  - `Rank IC`: `0.005866803344877897`
  - `Long-Short Ann Return`: `-0.0033080338`
  - `Long-Short Ann Sharpe`: `-0.06307939`
- Excess return with cost:
  - `annualized_return`: `-0.056324`
  - `information_ratio`: `-0.653539`
  - `max_drawdown`: `-0.161463`

This is a baseline functionality run on current-constituent US data. It is useful as a platform check and comparison baseline, not as an alpha claim.

## Query Data By Code

China:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='~/.qlib/qlib_data/cn_data', region='cn', kernels=1); from qlib.data import D; print(len(D.list_instruments(D.instruments('csi300'), start_time='2020-01-02', end_time='2020-01-02', freq='day')))"
```

US:

```powershell
.\.venv\Scripts\python.exe -c "import qlib; qlib.init(provider_uri='~/.qlib/qlib_data/us_data', region='us', kernels=1); from qlib.data import D; print(D.features(['AAPL','MSFT','SPY','QQQ'], [chr(36)+'close', chr(36)+'volume'], start_time='2020-01-02', end_time='2020-01-08', freq='day'))"
```

## UI and Interfaces

Qlib itself is not a standalone GUI application.

The main interfaces are:

- `qrun`: command-line workflow runner for YAML configs.
- Python API: `qlib.init`, `D.features`, `DatasetH`, model training, records, backtests.
- Notebook: best for interactive research and charts.
- MLflow UI: web UI for experiments, params, metrics, and artifacts.
- Chat-driven agent workflow: use this repo through Codex by describing factor ideas and asking the agent to implement, run, diagnose, and summarize experiments.

Start MLflow UI:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_mlflow_ui.ps1 -TrackingUri .tmp\mlruns_real -Port 5000
```

Open:

```text
http://127.0.0.1:5000
```

For US experiments:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_mlflow_ui.ps1 -TrackingUri .tmp\mlruns_us -Port 5001
```

Open:

```text
http://127.0.0.1:5001
```

For recent US experiments:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_mlflow_ui.ps1 -TrackingUri .tmp\mlruns_us_recent -Port 5002
```

Open:

```text
http://127.0.0.1:5002
```

## Data Extension Options

### Qlib Yahoo collector

This is the most native path for US OHLCV data because Qlib already includes it:

```powershell
.\.venv\Scripts\python.exe scripts\data_collector\yahoo\collector.py download_data --source_dir "$env:USERPROFILE\.qlib\stock_data\source\us_data" --start 2020-01-01 --end 2020-12-31 --delay 1 --interval 1d --region US
.\.venv\Scripts\python.exe scripts\data_collector\yahoo\collector.py normalize_data --source_dir "$env:USERPROFILE\.qlib\stock_data\source\us_data" --normalize_dir "$env:USERPROFILE\.qlib\stock_data\source\us_1d_nor" --region US --interval 1d
.\.venv\Scripts\python.exe scripts\dump_bin.py dump_all --data_path "$env:USERPROFILE\.qlib\stock_data\source\us_1d_nor" --qlib_dir "$env:USERPROFILE\.qlib\qlib_data\us_data_custom" --freq day --exclude_fields date,symbol --file_suffix .csv
```

Use this when the ready-made US data is too stale.

### FinanceDataReader

FinanceDataReader is useful for global listings and OHLCV ingestion, including NASDAQ, NYSE, AMEX, S&P 500, indexes, FX, crypto, and Korea ETFs. It is not native to Qlib, so it would need a small adapter:

`FinanceDataReader -> normalized CSV -> scripts/dump_bin.py -> Qlib provider_uri`

### Financial Datasets API

Financial Datasets is better suited for fundamentals, filings, insider trades, ownership, news, and structured company data. It requires an API key. It can complement Qlib OHLCV data, but should be integrated as a separate fundamental/news data layer rather than mixed blindly into daily OHLCV files.
