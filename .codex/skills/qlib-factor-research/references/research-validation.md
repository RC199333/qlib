# Research Validation Checklist

Use this checklist before interpreting any factor or strategy result.

## Required Specification

- Factor family/version name.
- Hypothesis and economic mechanism.
- Tradable universe and benchmark.
- Signal timestamp and data availability timestamp.
- Rebalance or event entry/exit rule.
- Holding horizon.
- Transaction cost and slippage assumption.
- Date range and train/validation/test split when parameters are tuned.
- External data source, cache path, and known data limitations.

## Leakage Checks

- No future event outcomes in pre-event features.
- No post-close data used for same-close trades unless explicitly executable.
- No use of final/current index constituents without survivorship-bias disclosure.
- No parameter selection on the same period used for final performance claims.
- No restated fundamentals treated as original point-in-time values unless the data source supports point-in-time history.

## Minimum Metrics

For daily portfolio backtests:

- Cumulative return, annualized return, Sharpe or information ratio, volatility, max drawdown.
- Benchmark-relative return and tracking error when applicable.
- Turnover, cost impact, average active names, and concentration.
- Yearly returns and drawdowns.

For event strategies:

- Total events, eligible events, selected events, and selection rate.
- Average and median event return after cost.
- Hit rate.
- Event return t-stat.
- Average excess return versus benchmark over the same event horizon.
- By-year selected count and average event return.
- Top and bottom selected trades.

## Interpretation Rules

- Tiny sample sizes are discovery evidence only. Treat fewer than 30 selected events as unstable unless there is strong out-of-sample support.
- A high Sharpe from sparse exposure needs trade-level review, not only daily return metrics.
- Prefer benchmark-excess event returns for sector strategies, especially tech strategies benchmarked to QQQ or SPY.
- Separate alpha quality from implementation quality: a useful signal can still fail under costs, liquidity, or timing assumptions.
- Report failed or inconclusive experiments; do not silently keep only attractive versions.
