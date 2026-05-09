# QR Production Chain

Use this reference when the user wants to go from a rough idea to an evaluated factor or strategy.

## 1. Idea Generation Or Intake

Produce an `IdeaCard` with:

- `factor_family`: short uppercase family name.
- `version`: exploratory versions start at `v0_1`.
- `title`: concise name.
- `hypothesis`: why the signal should predict returns.
- `economic_mechanism`: behavioral, risk-premium, flow, microstructure, fundamental, or event-driven rationale.
- `tradable_universe`: symbols, index members, sector, liquidity rules, and benchmark.
- `signal_timing`: when the signal is observable and when the trade can be executed.
- `expected_horizon`: intraday, event close-to-close, daily, weekly, monthly.
- `required_data`: Qlib fields plus any external data.
- `main_risks`: leakage, survivorship, turnover, liquidity, crowding, data revisions.

If generating multiple ideas, rank them by expected signal strength, data availability, implementation cost, and falsifiability.

## 2. ExperimentSpec

Before coding, write an `ExperimentSpec` with:

- `factor_name`: for example `ERT_v0_2_readthrough_breadth_topq`.
- `research_question`: the exact question this version answers.
- `formula`: factor components and weights, or rules if not yet parameterized.
- `universe`: explicit symbol source and bias caveat.
- `provider_uri`: local Qlib data root.
- `date_range`: start and end.
- `benchmark`: SPY, QQQ, CSI300, or another justified benchmark.
- `execution`: entry price, exit price, rebalance timing, order style, max weight, max positions.
- `cost_model`: commission, slippage, borrow assumptions if shorting.
- `parameter_policy`: fixed, train-only tuned, validation-selected, or exploratory.
- `outputs`: required artifacts from `artifact-contract.md`.

## 3. Data Build

Prefer local Qlib data for prices, volumes, calendars, and benchmark returns. Add external data only when the factor thesis requires it.

Required data checks:

- Symbol coverage over the requested period.
- Calendar alignment and missing bars.
- Point-in-time availability timestamp.
- External API schema and rate-limit handling.
- Cache location and cache invalidation policy.
- Survivorship and corporate-action caveats.

## 4. Factor Construction

Keep the economic signal auditable:

- Name raw inputs.
- Name transformed inputs.
- Name core alpha components separately from filters.
- Export intermediate features.
- Winsorize or robust-scale only with explicit parameters.
- Avoid full-period normalization unless it is computed inside each train window.

For Qlib supervised alpha, implement through `DataHandler`, `Dataset`, and `Model` where possible. For event studies, use Qlib for market data and calendar alignment, then keep event logic explicit.

## 5. Backtest

Run the smallest backtest that faithfully matches the execution assumption.

For Qlib-native workflows:

- Produce signals through `SignalRecord`.
- Run strategy/backtest through Qlib workflow.
- Persist `PortAnaRecord` artifacts.

For event strategies:

- Produce event-level selected trades.
- Produce daily portfolio returns.
- Produce benchmark-relative event returns over the same horizon.
- Export positions and event returns.

## 6. Validation

Run the validation checklist in `research-validation.md`.

Minimum additional gates:

- Review at least the top and bottom selected trades.
- Compare in-sample, validation, and out-of-sample periods if parameters were tuned.
- Compare absolute return and benchmark-excess return.
- Confirm the signal is known before trade entry.
- Re-run with at least one conservative cost assumption.

## 7. Report And Decision

The final report must make a research decision:

- `reject`: no evidence or invalid data.
- `revise`: promising but needs a targeted next version.
- `promote_to_v1_candidate`: robust enough to freeze spec and test more seriously.

Never promote a factor based only on one attractive full-period backtest.
