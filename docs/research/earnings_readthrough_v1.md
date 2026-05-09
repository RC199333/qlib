# Earnings Read-Through V1

Last verified: 2026-05-07

## Thesis

The first Alpha Lab strategy tests whether earnings information from already reported technology peers can predict favorable setups for upcoming technology earnings events.

V1 is long-only and event-driven:

- buy at the close before the earnings event date;
- sell at the close after the first full post-event trading day;
- trade only when the read-through score is strong enough;
- leave unused capital in cash.

## Data

Market data comes from Qlib:

```text
C:\Users\rexch\.qlib\qlib_data\us_data_recent
```

Earnings data comes from Alpha Vantage `EARNINGS`, or from an offline CSV with the same normalized columns:

```text
symbol,reported_date,fiscal_date_ending,reported_eps,estimated_eps,surprise,surprise_percentage
```

Runtime caches are intentionally ignored under:

```text
data/alpha_lab/
```

## Signal

The V1 score combines:

- peer EPS surprise percentage from already completed peer events;
- peer close-to-close event return;
- target pre-event 20-day momentum;
- target abnormal volume;
- target 5-day pre-event run-up as a penalty;
- target 20-day realized volatility as a penalty.

Peer data is only eligible if the peer event has already completed by the target entry close. The target company's own actual surprise is not used in its pre-event signal.

## Run

With Alpha Vantage:

```powershell
$env:ALPHAVANTAGE_API_KEY = "<your-key>"
powershell -ExecutionPolicy Bypass -File scripts\run_earnings_readthrough_alpha.ps1 -Start 2024-01-01 -End 2026-05-07 -RequestDelaySeconds 12
```

With offline events CSV:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_earnings_readthrough_alpha.ps1 -EventsPath path\to\events.csv -Start 2024-01-01 -End 2026-05-07
```

Outputs:

```text
.tmp\alpha_lab_runs\earnings_readthrough_*
```

MLflow artifacts:

```text
.tmp\mlruns_alpha_lab
```

## Known Limits

- `us_data_recent` uses current constituents, so historical index-membership survivorship bias remains.
- Alpha Vantage earnings data is research-grade and may not provide full point-in-time estimate history.
- Daily close-to-close execution approximates announcement timing and does not distinguish before-open from after-close releases.
- V1 is not a shorting strategy; miss prediction is recorded only as diagnostics.
