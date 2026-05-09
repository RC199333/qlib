# Artifact Contract

Every serious factor run should produce a self-contained run directory. Use this contract for both Qlib-native and event-driven research.

## Run Directory

Use a stable directory name:

`<artifact_root>/<factor_name>/<YYYYMMDD_HHMMSS>/`

For exploratory work, `.tmp/factor_runs/` is acceptable. For curated research notes, write the final markdown summary under `docs/research/`.

## Required Files

- `manifest.json`: machine-readable run manifest.
- `idea_card.json`: original or generated research idea.
- `experiment_spec.json`: exact experiment parameters.
- `report.md`: human-readable QR report.
- `commands.txt`: exact commands run, including failures.
- `metrics_summary.json`: headline metrics.
- `metrics_by_year.csv`: yearly return, drawdown, Sharpe or IR, selected-event count if applicable.
- `data_diagnostics.json`: coverage, missing data, symbol count, benchmark coverage, data caveats.
- `features.csv` or `features.parquet`: factor inputs and transformed components.
- `signals.csv` or `signals.parquet`: final score/signal and selection flag.

## Conditional Files

For event strategies:

- `events.csv`: all normalized candidate events.
- `selected_events.csv`: selected tradable events.
- `event_returns.csv`: realized event-level returns and benchmark-excess returns.
- `positions.csv`: daily or event-level positions.
- `daily_returns.csv`: strategy and benchmark daily returns.

For Qlib-native workflows:

- Qlib recorder URI or MLflow run ID in `manifest.json`.
- `pred.pkl` or exported prediction table if available.
- `portfolio_analysis.csv` or equivalent Qlib analysis artifact.

## Required Charts

Place charts under `plots/`:

- `cumulative_return.png`
- `drawdown.png`
- `yearly_returns.png`
- `signal_distribution.png`
- `turnover_or_event_count.png`

For event strategies also produce:

- `event_return_distribution.png`
- `selected_trade_timeline.png`
- `top_bottom_trades.png`

## Manifest Schema

`manifest.json` should include at least:

```json
{
  "factor_name": "ERT_v0_2_readthrough_breadth_topq",
  "factor_family": "ERT",
  "version": "v0_2",
  "status": "revise",
  "created_at": "2026-05-08T00:00:00",
  "provider_uri": "C:/Users/rexch/.qlib/qlib_data/us_data_recent",
  "universe": {
    "name": "tech_tmt_semis_curated",
    "symbols": ["AAPL", "MSFT"]
  },
  "date_range": {
    "start": "2020-01-02",
    "end": "2026-05-07"
  },
  "benchmark": "QQQ",
  "execution": {
    "entry": "close_before_event",
    "exit": "first_full_trading_day_close",
    "cost_bps_one_way": 10
  },
  "data_sources": [
    {
      "name": "qlib_us_recent",
      "type": "qlib_bin",
      "path": "C:/Users/rexch/.qlib/qlib_data/us_data_recent"
    }
  ],
  "artifacts": {
    "report": "report.md",
    "metrics_summary": "metrics_summary.json",
    "plots": ["plots/cumulative_return.png"]
  },
  "validation": {
    "leakage_checks_passed": false,
    "unit_tests": [],
    "known_limitations": []
  },
  "commands": []
}
```

Do not store API keys, tokens, or raw secrets in this file.
