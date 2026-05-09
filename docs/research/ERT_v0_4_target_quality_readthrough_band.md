# ERT_v0_4_target_quality_readthrough_band

Status: `revise`, best current research candidate, not production-approved.

Baseline run directory: `.tmp/factor_runs/ERT_v0_4_target_quality_readthrough_band/20260508_022513`

Aggressive sizing run: `.tmp/factor_runs/ERT_v0_4_target_quality_readthrough_band_w20/20260508_022603`

## Research Verdict

I do not have 100% confidence in this factor. That standard is not attainable for empirical alpha research.

This is the strongest version in the current loop because it fixes the largest defect in `ERT_v0_3`: peer read-through alone was not enough. The added target-quality gate requires the target stock to have a positive median QQQ-excess reaction over its prior four earnings events. This is causal, point-in-time under the available event history, and economically plausible.

The result is improved but still not ready for production: selected sample size is only 34 events, event t-stat is 1.71, and the data still has survivorship and point-in-time limitations.

## Formula

Peer read-through alpha:

```text
alpha_score =
  0.38 * peer_surprise_component
+ 0.34 * peer_excess_component
+ 0.18 * peer_breadth_component
+ 0.05 * peer_count_component
+ 0.03 * sector_excess_component
+ 0.02 * sector_breadth_component
```

Target earnings quality:

```text
target_quality_score =
  0.65 * target_prior_excess_component
+ 0.35 * target_prior_hit_component
```

Setup score:

```text
setup_score =
  0.45 * momentum_component
+ 0.25 * abnormal_volume_component
- 0.20 * positive_runup_component
- 0.10 * volatility_component
```

Selection rule:

```text
eligible
and setup_filter_pass
and peer_breadth_filter_pass
and target_quality_filter_pass
and 0.00 <= rolling_alpha_percentile <= 0.80
```

The rolling percentile is computed from earlier pre-target-filter tradable events, not future events.

## Parameters

- Date range: `2020-01-02` to `2026-05-07`
- Universe: 25 curated US large-cap tech/TMT/semi names
- Benchmark: `QQQ`; `^GSPC` recorded as secondary benchmark
- Entry: previous trading-day close before reported earnings date
- Exit: next trading-day close after reported earnings date
- Long-only
- One-way cost: 10 bps
- Peer lookback: 45 trading days
- Peer half-life: 20 trading days
- Minimum peer events: 3
- Minimum peer excess hit-rate: 50%
- Maximum 5-day pre-event runup: 5%
- Maximum 20-day volatility: 8%
- Minimum 20-day dollar volume: 20 million
- Minimum target prior earnings events: 4
- Minimum target prior QQQ-excess median: 0

## Results

Baseline portfolio, 10% max single-name weight:

- Selected events: 34
- Hit rate: 52.94%
- Average event return after cost: 2.91%
- Median event return after cost: 1.48%
- Average event excess vs QQQ: 2.63%
- Event return t-stat: 1.71
- QQQ-excess event t-stat: 1.62
- Net cumulative return: 10.28%
- Net annualized return: 1.56%
- Net Sharpe/IR: 0.65
- Max drawdown: -4.30%
- Exposure-matched QQQ excess cumulative return: 8.52%

Aggressive portfolio, 20% max single-name weight:

- Net cumulative return: 21.18%
- Net annualized return: 3.08%
- Net Sharpe/IR: 0.65
- Max drawdown: -8.45%

The 20% version is only sizing leverage on the same signal. It is not a stronger alpha.

## Robustness Follow-up

Additional checks were run after the baseline result to test whether the result
survives simple institutional-quality objections.

Higher transaction cost sensitivity:

- 25 bps one-way cost: net cumulative return 9.16%, net Sharpe/IR 0.58, max drawdown -4.52%.
- 50 bps one-way cost: net cumulative return 7.32%, net Sharpe/IR 0.47, max drawdown -4.87%.

The signal remains positive under higher cost assumptions, but statistical
strength deteriorates quickly.

Single-name concentration test:

- Excluding `PLTR`: selected events 29, net cumulative return 2.75%, net Sharpe/IR 0.28.
- Excluding `PLTR`: average event return after cost 0.92%, average excess vs QQQ 0.13%.
- Excluding `PLTR`: exposure-matched excess vs QQQ cumulative return -0.13%.
- Excluding `PLTR`: validation 2024 average event return -2.17%, average excess vs QQQ -1.81%.

This is a material failure. The baseline result depends too much on several
large `PLTR` post-earnings moves. The factor cannot be called robust until it
survives broader universe, sector, and single-name exclusion tests.

Parameter-search note:

- A constrained no-`PLTR` search over percentile band, runup cap, peer hit-rate,
  and target-prior filters did not find a version with convincing train,
  validation, and test performance.
- Continuing to optimize parameters on the current local sample would mainly
  increase overfitting risk rather than improve research quality.

## Split Diagnostics

Selected event returns:

- Train 2020-2023: 21 events, avg after cost 1.32%, avg excess vs QQQ 0.73%
- Validation 2024: 7 events, avg after cost 6.25%, avg excess vs QQQ 6.50%
- Test 2025-2026: 6 events, avg after cost 4.58%, avg excess vs QQQ 4.74%

By-year portfolio result:

- 2021: -1.31%, 3 events
- 2022: +4.75%, 10 events
- 2023: -0.72%, 8 events
- 2024: +4.56%, 7 events
- 2025: +2.28%, 4 events
- 2026: +0.48%, 2 events through May 7

## IC

Event-level rank IC is mixed:

- Eligible universe, target_quality_score vs QQQ-excess return: 0.057
- Tradable universe, target_quality_score vs QQQ-excess return: 0.152
- Selected events, target_quality_score vs QQQ-excess return: 0.385
- Selected events, rank_score vs event return: 0.262
- Selected events, rank_score vs QQQ-excess return: 0.105

Interpretation: target quality is doing useful work after filtering, but raw peer read-through is not a robust monotonic IC signal. This is an event-selection strategy, not a clean cross-sectional daily factor yet.

## Main Failure Modes

- Sample is small: only 34 selected events.
- Test set has only 6 selected events.
- Current-constituent universe introduces survivorship bias.
- Alpha Vantage earnings history is research-grade and may not be fully point-in-time.
- Close-to-close execution approximates exact after-close and before-open earnings timing.
- PLTR contributes several top positive trades, so concentration must be monitored.
- Raw peer read-through score has negative IC before target-quality filtering, meaning the factor works through gated selection rather than simple monotonic ranking.

## Decision

Do not promote to production.

Keep `ERT_v0_4_target_quality_readthrough_band` as the current best research
candidate, but mark it as `research_only`. The stopping condition for this
iteration is not that the factor is perfect; it is that the available local data
has exposed a real robustness limit and further local tuning would not be
scientifically defensible.

Next required work before promotion:

- Historical point-in-time universe membership.
- More robust earnings timing, separating after-close and before-open reports.
- Additional target-quality features: analyst revisions, revenue surprise, and guidance tone if reliable PIT data is available.
- Cluster-specific validation: semis, enterprise software, mega-cap platforms.
- Single-name and cluster leave-one-out tests.
- Paper-trading style forward validation before using capital.
