# Earnings Read-Through V1 Results

Run date: 2026-05-08

## Universe

Selected 25 US technology/TMT/semiconductor names from local `us_data_recent`:

```text
AAPL, MSFT, GOOGL, AMZN, META, NFLX,
NVDA, AMD, AVGO, QCOM, MU, INTC, TXN, AMAT, LRCX, KLAC,
ORCL, CRM, NOW, ADBE, INTU, PLTR, PANW, CRWD, FTNT
```

Excluded from V1: data-center infrastructure and upstream/power-adjacent names such as `SMCI`, `DELL`, `HPE`, `ANET`, utilities, and power-chain names.

## Data And Window

- Market data: `C:\Users\rexch\.qlib\qlib_data\us_data_recent`
- Earnings data: Alpha Vantage `EARNINGS`, cached under ignored runtime data
- Backtest window: `2024-01-01` to `2026-05-07`
- Events loaded: `240`
- Eligible events with enough completed peer read-through: `87`
- Execution: buy at pre-event close, sell at first full post-event trading-day close
- Long-only, equal-weight event book, max active positions `10`, max single-name weight `10%`
- Transaction cost assumption: `10 bps` one-way

## Signal Formula

For each target event:

```text
score =
  0.40 * clip(peer_surprise_pct_mean / 10, -3, 3)
+ 0.30 * clip(peer_event_return_mean / 0.05, -3, 3)
+ 0.15 * clip(momentum_20 / 0.10, -3, 3)
+ 0.10 * clip(abnormal_volume_10 / 1.00, -3, 3)
- 0.05 * clip(runup_5 / 0.05, -3, 3)
- 0.05 * clip(volatility_20 / 0.03, 0, 3)
```

Eligibility:

```text
peer_event_count >= 2
entry_close and exit_close are available
score >= threshold
```

Peer read-through only uses peer events whose `exit_date <= target entry_date`. The target company's own actual surprise is not used before the event.

## Parameter Sweep

| Threshold | Selected events | Hit rate | Avg event return after cost | Avg event excess vs QQQ | Net cumulative return | Net IR | Max drawdown |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.25 | 48 | 39.6% | -0.15% | n/a | -1.84% | -0.160 | -8.65% |
| 0.50 | 33 | 42.4% | -0.04% | n/a | -0.95% | -0.092 | -4.71% |
| 0.75 | 26 | 50.0% | 1.06% | n/a | 2.09% | 0.275 | -4.04% |
| 1.00 | 20 | 50.0% | -0.03% | n/a | -0.55% | -0.086 | -4.38% |
| 1.25 | 8 | 50.0% | 3.42% | 3.89% | 2.71% | 0.787 | -1.21% |
| 1.50 | 4 | 75.0% | 9.13% | 8.06% | 3.65% | 1.138 | -0.15% |

Recommendation for next iteration: use `threshold=1.25` as the balanced baseline, and keep `threshold=1.50` as a high-conviction diagnostic because it has only four selected events.

## Balanced Baseline: threshold=1.25

Artifact directory:

```text
.tmp\alpha_lab_runs\earnings_readthrough_20260508_003115_191158
```

Selected events:

| Symbol | Reported | Entry | Exit | Score | Net event return | Excess vs QQQ | Peer count | Peer surprise mean | Peer event return mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AMD | 2026-05-05 | 2026-05-04 | 2026-05-06 | 2.481 | 23.18% | 19.98% | 3 | 942.80 | 20.33% |
| QCOM | 2026-04-30 | 2026-04-29 | 2026-05-01 | 2.261 | 13.27% | 11.57% | 2 | 1412.41 | 23.76% |
| CRWD | 2024-08-28 | 2024-08-27 | 2024-08-29 | 1.935 | 0.48% | 1.96% | 2 | 23.03 | 18.20% |
| QCOM | 2025-11-05 | 2025-11-04 | 2025-11-06 | 1.279 | 0.01% | 1.43% | 2 | 1102.68 | -0.63% |
| ADBE | 2025-09-11 | 2025-09-10 | 2025-09-12 | 1.589 | -0.43% | -1.25% | 3 | 24.76 | 9.65% |
| AMD | 2025-05-06 | 2025-05-05 | 2025-05-07 | 1.287 | -0.43% | 0.31% | 3 | 405.81 | -0.03% |
| AMD | 2025-11-04 | 2025-11-03 | 2025-11-05 | 1.484 | -1.48% | 0.11% | 2 | 1102.68 | -0.63% |
| ORCL | 2025-03-10 | 2025-03-07 | 2025-03-11 | 1.258 | -7.28% | -2.97% | 2 | 52.66 | 3.34% |

Portfolio metrics:

- Net cumulative return: `2.71%`
- Net annualized return: `1.61%`
- Net information ratio: `0.787`
- Max drawdown: `-1.21%`
- Average event return after cost: `3.42%`
- Average event excess vs QQQ: `3.89%`
- Average event excess vs S&P 500: `3.81%`

## Red-Team Notes

- The strategy is low-exposure and event-driven, so full-period comparison to QQQ buy-and-hold is not the right primary evaluation metric.
- Alpha Vantage `surprisePercentage` can be extremely large when estimates are close to zero. The score clips the surprise component, but V2 should add a cleaner outlier and denominator policy.
- Current universe uses current constituents and local Yahoo-derived Qlib data, so survivorship bias remains.
- V1 does not distinguish before-open versus after-close release timing; close-to-close is a daily approximation.
