# PEAD_v2_actual_quality_60d Research Note

## Conclusion

`PEAD_v2_actual_quality_60d` adds a SEC companyfacts rank-based actual-quality gate to `PEAD_v1_quality_drift_60d`.

It improves signal cleanliness but currently reduces event count too much. The result is a higher Sharpe and hit rate, but lower cumulative return and lower total QQQ-excess return because the strategy is under-exposed.

This version should be treated as a quality-filter experiment, not as a final production factor.

## Definition

Base score is unchanged from `PEAD_v1`:

```text
PEAD_score =
    0.34 * surprise_component
  + 0.36 * announcement_excess_component
  + 0.15 * prior_excess_component
  + 0.10 * prior_beat_component
  - 0.05 * runup_penalty
```

The current v2 selection rule is:

```text
selected =
    PEAD_v1_selected
and fundamental_quality_component_count >= 2
and (
       fundamental_quality_rank_score is unavailable because early history is insufficient
    or fundamental_quality_rank_score >= 20th percentile
)
```

The rank score is the average expanding historical percentile rank of available SEC quality components:

- `sec_revenue_yoy`
- `sec_operating_margin_delta_yoy`
- `sec_gross_margin_delta_yoy`
- `sec_fcf_margin`
- `-sec_accruals_to_assets`

This avoids fixed scale assumptions across fundamentals fields. The 20th percentile threshold is deliberately loose: it filters the worst actual-quality reports without starving the already-small earnings sample.

## Data Mode

SEC companyfacts filing dates usually occur after the earnings announcement. Therefore this version uses SEC facts as a `reported_quarter_proxy` for earnings-release actual fundamentals.

This is not strict SEC-filed point-in-time data. It assumes the actual revenue and margin information was known from the earnings release before the first post-announcement close, while SEC companyfacts is used as a normalized after-the-fact source for those actuals.

Strict PIT alternative:

```text
selected =
    PEAD_v1_selected
and latest_prior_filed_sec_quality_is_positive
```

That is cleaner from a filing-date perspective, but it measures prior-quarter quality rather than the newly reported quarter.

## Current Result

Original hard-gate run:

```text
.tmp/factor_runs/PEAD_v2_actual_quality_60d/20260508_155248
```

Current rank-gate run:

```text
.tmp/factor_runs/PEAD_v2_actual_quality_60d/20260509_001406
```

Current key metrics:

| Metric | Value |
| --- | ---: |
| Total signals | 417 |
| Fundamental quality gate pass | 132 |
| Eligible events | 65 |
| Selected events | 52 |
| Strategy cumulative return | 33.04% |
| Strategy annualized return | 4.62% |
| Strategy Sharpe | 1.20 |
| Max drawdown | -5.81% |
| Exposure-matched excess vs QQQ | 8.64% |
| Excess IR vs QQQ | 0.59 |
| Average selected event return after cost | 11.21% |
| Selected hit rate | 80.77% |

Comparison to `PEAD_v1_quality_drift_60d`:

| Metric | PEAD v1 | PEAD v2 hard gate | PEAD v2 rank gate |
| --- | ---: | ---: | ---: |
| Selected events | 125 | 29 | 52 |
| Strategy cumulative return | 65.07% | 15.85% | 33.04% |
| Strategy Sharpe | 0.85 | 1.07 | 1.20 |
| Max drawdown | -12.98% | -3.10% | -5.81% |
| Exposure-matched excess vs QQQ | 16.62% | 2.97% | 8.64% |
| Average event return after cost | 8.15% | 9.59% | 11.21% |
| Hit rate | 65.60% | 86.21% | 80.77% |

## Interpretation

The rank-based quality gate is directionally useful:

- It raises average selected event return.
- It raises hit rate.
- It lowers drawdown.
- It improves Sharpe.

It is still narrower than v1:

- selected events are 52 versus 125 in v1;
- portfolio exposure is still lower than v1;
- total QQQ-excess return is lower than v1, but risk-adjusted quality is better.

The current best interpretation is:

```text
SEC actual-quality rank filter improves precision and risk-adjusted return, but current Alpha Vantage earnings coverage still limits total deployable exposure.
```

## Next Iteration

The next version should test whether the 20th percentile threshold remains stable after Alpha Vantage earnings coverage improves.

```text
quality_rank_threshold_grid = 15%, 20%, 25%, 35%, 45%
primary acceptance = stable QQQ-excess IR with selected events > 75 after earnings coverage expands
```

If coverage improves, a stricter PIT variant should also be tested:

```text
quality_data_mode = latest SEC filing available before entry_date
```

That version is cleaner from a filed-date perspective, but it measures prior-quarter quality rather than the newly reported quarter.
