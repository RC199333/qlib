# ERT_v0_3_balanced_readthrough_no_runup

Status: `revise`, research-use only.

Run directory: `.tmp/factor_runs/ERT_v0_3_balanced_readthrough_no_runup/20260508_021333`

## Research Question

Can recent tech peer earnings surprises and benchmark-excess event reactions identify favorable pre-earnings long setups when the target has not already run up?

The first `ERT_v0_2_readthrough_breadth_topq` draft tested the naive thesis that stronger peer read-through should be bought. Full-window diagnostics rejected that direction: the highest peer read-through bucket was weak. `v0_3` changes the selection rule to a balanced read-through band and a stricter no-runup setup filter.

## Formula

Core alpha:

```text
alpha_score =
  0.38 * peer_surprise_component
+ 0.34 * peer_excess_component
+ 0.18 * peer_breadth_component
+ 0.05 * peer_count_component
+ 0.03 * sector_excess_component
+ 0.02 * sector_breadth_component
```

Setup score is exported for audit and rank tie-breaks, but it is not the main alpha:

```text
setup_score =
  0.45 * momentum_component
+ 0.25 * abnormal_volume_component
- 0.20 * positive_runup_component
- 0.10 * volatility_component
```

Selection:

```text
eligible
and setup_filter_pass
and peer_breadth_filter_pass
and 0.30 <= rolling historical alpha percentile <= 0.80
```

The rolling percentile uses only earlier tradable events, not future events in the same quarter.

## Backtest Setup

- Date range: `2020-01-02` to `2026-05-07`
- Universe: 25 curated US large-cap tech/TMT/semi names
- Benchmark: `QQQ`, with `^GSPC` also recorded
- Entry: previous trading-day close before reported earnings date
- Exit: next trading-day close after reported earnings date
- Long only, no shorting
- Max active positions: 10
- Baseline max single-name weight: 10%
- Cost: 10 bps one-way
- Price data: local Qlib `~/.qlib/qlib_data/us_data_recent`
- Earnings data: cached Alpha Vantage `EARNINGS`

## Headline Results

Event-level:

- Total candidate signals: 638
- Eligible events: 331
- Tradable signals: 129
- Selected events: 49
- Hit rate: 55.10%
- Average event return after cost: 1.12%
- Median event return after cost: 0.72%
- Average event excess vs QQQ: 0.89%
- Average event excess vs S&P 500: 1.00%
- Event return t-stat: 0.79

Portfolio-level, 10% max single-name weight:

- Net cumulative return: 5.29%
- Net annualized return: 0.82%
- Net Sharpe/IR: 0.31
- Max drawdown: -5.88%
- Exposure-matched excess vs QQQ cumulative return: 3.18%

Sizing sensitivity, 20% max single-name weight:

- Net cumulative return: 10.32%
- Net annualized return: 1.57%
- Net Sharpe/IR: 0.31
- Max drawdown: -11.52%

## By-Year Notes

The signal is not stable enough to promote:

- 2021 was negative.
- 2022 and 2023 were positive.
- 2024 was negative despite a strong tech market.
- 2025 was approximately flat.
- 2026 is positive but has only one selected event in the tested window.

## Interpretation

This version is a usable research artifact, not a production factor. It fixes the earlier engineering and measurement problems: longer sample, event-level excess return, Sharpe/yearly metrics, charts, run manifest, and traceable features/signals/trades.

The economic result is weaker: the event-level average return is positive, but the t-stat is low and yearly behavior is uneven. The current evidence supports `revise`, not `promote_to_v1_candidate`.

## Main Limitations

- Current-constituent universe creates survivorship bias.
- Alpha Vantage earnings history is research-grade and may not be true point-in-time.
- Daily close-to-close approximates after-close and before-open earnings timing.
- Sample size is still moderate: 49 selected events over 2021-2026.
- The factor is sensitive to PLTR and a few high-magnitude events.

## Next Version

The next targeted version should test one change at a time:

- Add target-specific prior earnings reaction quality as a filter.
- Separate software, semis, and mega-cap platform clusters more strictly.
- Use historical index membership or a fixed tradability universe snapshot to reduce survivorship bias.
- Add analyst estimate revision or revenue surprise data if a reliable point-in-time source is available.
