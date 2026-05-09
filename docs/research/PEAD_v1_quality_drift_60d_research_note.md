# PEAD_v1_quality_drift_60d Research Note

## Conclusion

`PEAD_v1_quality_drift_60d` is the current best earnings-season candidate in this fork. It is not a pre-earnings prediction factor. It is a post-announcement drift factor: buy liquid, non-mega-cap technology names after the company reports a positive EPS surprise and the first full post-announcement trading day confirms the surprise with positive QQQ-relative price action, then hold for 60 trading days.

The current backtest is research-grade only because the local earnings history is incomplete and the universe is not point-in-time. Still, this version is economically cleaner than the earlier pre-earnings draft because it avoids trying to predict the surprise before the announcement with insufficient fundamentals data.

## Factor Definition

Factor name: `PEAD_v1_quality_drift_60d`

Family: `PEAD` / Post-Earnings-Announcement Drift

Universe: curated US technology, TMT, and semiconductor names available in local Qlib price data. Mega-cap indicator symbols are used for context but excluded from holdings:

- Indicator-only: `AAPL`, `MSFT`, `GOOG`, `GOOGL`, `AMZN`, `META`, `NVDA`, `ORCL`
- Excluded from holdings: `PLTR`

Execution:

- Entry: close of the first full trading day after reported earnings date.
- Exit: 60 trading days after entry.
- Direction: long-only.
- Benchmark: `QQQ`; excess return is exposure-matched to active strategy exposure.
- Risk controls: maximum 30 active positions, maximum 5% weight per position, 10 bps one-way transaction cost.

## Formula

For each earnings event:

```text
PEAD_score =
    0.34 * surprise_component
  + 0.36 * announcement_excess_component
  + 0.15 * prior_excess_component
  + 0.10 * prior_beat_component
  - 0.05 * runup_penalty
```

Component definitions:

```text
surprise_component =
    clip(surprise_percentage / 25.0, -3.0, 3.0)

announcement_excess_component =
    clip(first_post_announcement_event_return_excess_vs_QQQ / 0.06, -3.0, 3.0)

prior_excess_component =
    clip(target_prior_event_excess_median_4 / 0.03, -3.0, 3.0)

prior_beat_component =
    clip(2 * (target_prior_surprise_beat_rate_4 - 0.5), -1.0, 1.0)

runup_penalty =
    clip(runup_5 / 0.10, 0.0, 3.0)
```

Selection rule:

```text
selected =
    surprise_percentage > 0
and first_post_announcement_event_return_excess_vs_QQQ > 0
and avg_dollar_volume_20 >= 20,000,000
and volatility_20 <= 10%
and runup_5 <= max(max_runup_5, 15%)
and rolling_score_percentile >= 45% once enough prior history exists
and symbol is holdable
```

The rolling percentile filter is intentionally weak. It removes the lowest-quality signals without reducing event count into a tiny threshold-fit sample.

## Economic Meaning

The factor is built around investor underreaction after earnings announcements.

Positive EPS surprise alone is not enough. A company can beat consensus while selling off because guidance, margin mix, or valuation context is poor. The factor therefore requires both:

1. Accounting confirmation: reported EPS exceeds estimate.
2. Market confirmation: the first full post-announcement trading day beats `QQQ`.

The 60-trading-day holding period is designed to capture the drift phase, not only the announcement jump. This directly addresses the earlier pre-earnings strategy problem: many real earnings winners do not produce most of their return in the first post-announcement day; the drift can continue over the next one to three months.

The prior-event components proxy for persistent earnings quality and repeat underreaction. They do not assume the company will always beat. They say that when this issuer has recently generated positive QQQ-relative post-earnings drift, a new confirmed beat is more likely to remain under-absorbed.

The runup penalty reduces exposure to names where a strong result may already have been anticipated before the report. Mega-cap indicator names are excluded from holdings because their analyst coverage, liquidity, and information incorporation speed make PEAD weaker; they can still be useful as sector indicators.

## Literature Support

- Bernard and Thomas, "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", Journal of Accounting Research, 1989. URL: https://econpapers.repec.org/RePEc:bla:joares:v:27:y:1989:i::p:1-36. This is the base PEAD anomaly: stock prices continue moving in the direction of standardized unexpected earnings after earnings announcements.
- Jegadeesh and Livnat, "Revenue Surprises and Stock Returns", 2006. URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=903767. This supports extending the surprise idea beyond EPS alone and is relevant for future versions that add revenue surprise and guidance quality.
- Savor and Wilson, "Earnings Announcements and Systematic Risk", Journal of Finance, 2016. URL: https://econpapers.repec.org/article/blajfinan/v_3a71_3ay_3a2016_3ai_3a1_3ap_3a83-138.htm. This is relevant to the event-risk premium side of earnings announcements and is a useful caution when separating alpha from compensation for announcement risk.

## Current Local Result

Latest run:

```text
.tmp/factor_runs/PEAD_v1_quality_drift_60d/20260508_123018
```

Key metrics:

| Metric | Value |
| --- | ---: |
| Total signals | 417 |
| Tradable / eligible events | 192 |
| Selected events | 125 |
| Strategy cumulative return | 65.07% |
| Strategy annualized return | 8.25% |
| Strategy Sharpe | 0.85 |
| Max drawdown | -12.98% |
| Exposure-matched excess vs QQQ | 16.62% |
| Excess IR vs QQQ | 0.60 |
| Average selected event return after cost | 8.15% |
| Average selected event excess vs QQQ | 2.59% |
| Selected rank IC vs QQQ-excess event return | 0.115 |

Cost robustness:

| Cost model | Cumulative return | Sharpe | Excess vs QQQ |
| --- | ---: | ---: | ---: |
| 10 bps one-way | 65.07% | 0.85 | 16.62% |
| 25 bps one-way | 62.24% | 0.83 | 14.62% |
| 50 bps one-way | 57.65% | 0.78 | 11.37% |

## Current Caveats

- The local earnings history covers only cached Alpha Vantage symbols. This creates a sample-selection problem.
- The curated universe is current-membership based and therefore survivorship-biased.
- Alpha Vantage earnings history may not be point-in-time revised history.
- Daily close-to-close execution approximates announcement timing. It does not distinguish after-market vs pre-market reports.
- No revenue surprise, guidance surprise, analyst revision, option-implied move, or intraday liquidity data is included yet.
- The signal is not capacity-tested and should not be treated as production-ready.

## Next Research Extensions

The next meaningful improvements should be data improvements, not more scoring complexity:

- Add a broader earnings history source or complete the Alpha Vantage cache incrementally.
- Add revenue surprise and guidance-quality proxies.
- Split after-market and pre-market reports when timestamps are available.
- Add point-in-time universe membership or at least historical index membership snapshots.
- Add sector-neutral and cluster-neutral diagnostics.
- Compare 20d, 40d, 60d, and 90d horizons after the data coverage improves.
