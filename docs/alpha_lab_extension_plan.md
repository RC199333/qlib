# Alpha Lab Extension Plan

This plan builds an Alpha Research Agent on top of Qlib without changing Qlib core. The first milestone should be a thin external package that turns research ideas into Qlib-compatible configs, runs experiments, validates them, and produces reports.

## Design Rule

Do not add new alpha features to Qlib internals. Add a separate package, for example:

```text
alpha_lab/
  ideas.py
  specs.py
  factors.py
  handlers.py
  signals.py
  strategies.py
  runner.py
  validation.py
  reports.py
  configs/
```

All Qlib integration should happen through:

- config dictionaries with `class`, `module_path`, and `kwargs`,
- `qlib.init(...)`,
- `DatasetH`,
- `Model` or `Signal`,
- `WeightStrategyBase` or `BaseStrategy`,
- `R`, `SignalRecord`, `SigAnaRecord`, and `PortAnaRecord`.

## Target Flow

```text
IdeaCard
  -> ExperimentSpec
  -> FactorRegistry resolves features and labels
  -> DatasetH + custom handler config
  -> CompositeSignalModel or rule-based Signal adapter
  -> SignalRecord
  -> RotationMomentumStrategy
  -> PortAnaRecord
  -> red-team validation checks
  -> report generator
```

## 1. IdeaCard -> ExperimentSpec

### IdeaCard

Represent the human or agent idea in a stable, auditable form:

```python
@dataclass(frozen=True)
class IdeaCard:
    idea_id: str
    name: str
    thesis: str
    universe: str
    horizon: str
    rebalance: str
    factor_refs: list[str]
    constraints: dict
    risk_notes: list[str]
    expected_failure_modes: list[str]
```

Keep this independent of Qlib. It is a research object, not a backtest config.

### ExperimentSpec

Compile the IdeaCard into an executable Qlib spec:

```python
@dataclass(frozen=True)
class ExperimentSpec:
    experiment_name: str
    qlib_init: dict
    market: str
    benchmark: str
    dataset: dict
    model_or_signal: dict
    strategy: dict
    executor: dict
    backtest: dict
    records: list[dict]
    validation: dict
```

The compiler should:

1. Validate universe, benchmark, time ranges, frequency, and region.
2. Ask `FactorRegistry` for Qlib feature expressions.
3. Build a `DatasetH` config with a custom handler or standard `Alpha158`/`Alpha360`.
4. Choose signal path:
   - trainable `CompositeSignalModel`, or
   - direct rule-based signal adapter.
5. Build `PortAnaRecord` config with strategy and backtest settings.

## 2. FactorRegistry

Create a registry that owns factor metadata and emits Qlib loader config.

```python
@dataclass(frozen=True)
class FactorDef:
    name: str
    expression: str
    group: str = "feature"
    lookback: int | None = None
    frequency: str = "day"
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
```

Registry responsibilities:

- Map factor names to Qlib expression strings.
- Enforce unique output names.
- Reject expressions with future leakage unless explicitly marked as label.
- Track required lookback windows.
- Emit `(fields, names)` pairs for `QlibDataLoader`.
- Export a manifest into each recorder as an artifact.

Initial factor types:

- existing Qlib formula factors using `$close`, `$open`, `$high`, `$low`, `$volume`, `$vwap`;
- composite expressions built from existing operators;
- labels such as `Ref($close, -2) / Ref($close, -1) - 1`;
- later, custom operators registered through `custom_ops`, only when formula strings are insufficient.

Avoid modifying `qlib/contrib/data/loader.py`. Put private factor collections in `alpha_lab/factors.py`.

## 3. CompositeSignalModel or Rule-Based Signal Adapter

### CompositeSignalModel

Use when the agent combines factor columns into a score and should fit parameters on a train split.

```python
class CompositeSignalModel(Model):
    def fit(self, dataset: DatasetH, reweighter=None):
        df = dataset.prepare("train", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
        # fit simple weights, rank transforms, or calibration
        return self

    def predict(self, dataset: DatasetH, segment="test"):
        x = dataset.prepare(segment, col_set="feature", data_key=DataHandlerLP.DK_I)
        return pd.Series(score, index=x.index)
```

Good first implementation:

- rank-normalize each factor by date;
- winsorize or clip outliers;
- combine with declared weights from `ExperimentSpec`;
- optionally fit weights by linear/ridge regression;
- output one score per `(datetime, instrument)`.

### Rule-Based Signal Adapter

Use when no fitting is needed.

```python
class RuleBasedSignal(Signal):
    def __init__(self, dataset_config, scoring_rules):
        ...

    def get_signal(self, start_time, end_time):
        ...
```

Simpler alternative: compute a dataframe once and pass it as `signal=<PRED>` or `signal=pred_df`, letting `SignalWCache` serve the latest available score.

Decision rule:

- If the object learns from train data, implement `Model`.
- If it only transforms current features into scores, implement `Signal` or produce a signal dataframe.

## 4. RotationMomentumStrategy

Implement this outside Qlib by inheriting `WeightStrategyBase`.

```python
class RotationMomentumStrategy(WeightStrategyBase):
    def generate_target_weight_position(self, score, current, trade_start_time, trade_end_time):
        # score: pd.Series or first column of pd.DataFrame
        # return {instrument: target_weight}
```

Initial behavior:

- rank assets by signal score on each rebalance date;
- select top N or assets above threshold;
- apply equal weights or score-proportional weights;
- respect max position weight, max turnover, cash/risk degree, and optional blacklist;
- return a target weight dict;
- let `OrderGenerator` convert target weights to orders.

Important Qlib mechanics:

- `WeightStrategyBase.generate_trade_decision(...)` fetches scores by shifted decision time.
- It deep-copies current position, calls `generate_target_weight_position(...)`, then uses the order generator.
- The strategy should not call `model.predict(...)`; signal construction stays upstream.

## 5. Backtest Runner

Build a runner that can execute either code-first or config-first.

Code-first runner:

1. `qlib.init(**spec.qlib_init)`.
2. Create model/dataset/signal from spec.
3. Start `R.start(experiment_name=spec.experiment_name)`.
4. Save `IdeaCard`, `ExperimentSpec`, factor manifest, and resolved config.
5. Train model if needed.
6. Generate `SignalRecord`.
7. Generate `SigAnaRecord`.
8. Generate `PortAnaRecord`.
9. Run validation checks.
10. Generate report.

Config-first runner:

- Emit Qlib YAML equivalent to benchmark configs.
- Run through `task_train(...)` or `qrun`.
- This gives better alignment with standard Qlib examples.

Prefer code-first for early agent development because it can save richer artifacts and fail with clearer messages. Keep emitted YAML as an artifact so every run remains reproducible.

## 6. Red-Team Validation Checks

Validation should run after prediction and after portfolio analysis. It should write a structured validation artifact and fail the run when hard gates fail.

### Data and leakage checks

- Provider path exists and contains expected `calendars`, `instruments`, and `features`.
- Region matches dataset universe.
- Train/valid/test date ranges are ordered and non-overlapping.
- Feature expressions do not use negative `Ref(...)` unless they are labels.
- Fit processors use only `fit_start_time` to `fit_end_time`.
- Prediction index is exactly two-level `datetime, instrument`.
- No duplicate prediction index.
- Prediction dates stay inside test/backtest range.
- Prediction has sufficient non-null coverage per date.

### Signal checks

- Cross-sectional standard deviation is not near zero for most dates.
- Scores are finite after cleaning.
- IC and rank IC are not driven by one or two dates.
- Turnover implied by signal is not extreme before costs.
- Signal autocorrelation is measured, not assumed.

### Strategy and backtest checks

- No trade outside configured universe.
- No position exceeds max weight.
- Cash/risk degree stays within bounds.
- Turnover and cost are within declared constraints.
- Backtest benchmark exists for all report dates.
- Positions and report data have no missing dates in the trading calendar.
- Compare gross and net results; reject ideas that only work before realistic costs.

### Robustness checks

- Run at least one shifted-date or shortened-window sanity check.
- Run a shuffled-signal or sign-flipped-signal check for calibration.
- Run multi-pass backtest when initial-position randomness matters.
- Record all checks with pass/warn/fail status.

## 7. Report Generator

The report should be a generated markdown or HTML artifact that reads only recorder artifacts and validation outputs.

Minimum report sections:

- Idea summary: thesis, universe, horizon, rebalance, constraints.
- Resolved experiment config: provider URI, region, benchmark, train/valid/test/backtest windows.
- Factor manifest: names, expressions, labels, lookbacks.
- Signal diagnostics: IC, rank IC, coverage, distribution, autocorrelation.
- Portfolio diagnostics: annualized return, information ratio, max drawdown, turnover, cost impact.
- Holdings/rotation: top holdings over time, entry/exit counts, concentration.
- Red-team results: hard failures, warnings, residual risk.
- Reproducibility: recorder id, artifact names, generated YAML/spec hash.

Use Qlib's existing artifacts:

- `pred.pkl`
- `label.pkl`
- `sig_analysis/ic.pkl`
- `sig_analysis/ric.pkl`
- `portfolio_analysis/report_normal_1day.pkl`
- `portfolio_analysis/positions_normal_1day.pkl`
- `portfolio_analysis/port_analysis_1day.pkl`
- `portfolio_analysis/indicator_analysis_1day.pkl`

## Implementation Phases

### Phase 0: Skeleton only

- Create `alpha_lab` package outside `qlib/`.
- Define dataclasses for `IdeaCard`, `ExperimentSpec`, and `FactorDef`.
- Build `FactorRegistry` with a handful of existing Qlib expressions.
- Emit a resolved Qlib task config but do not run new alpha experiments yet.

### Phase 1: Baseline reproduction

- Reproduce a LightGBM `Alpha158` benchmark using generated config.
- Confirm artifacts match the normal Qlib workflow shape.
- Add validation that reads `pred.pkl`, `label.pkl`, and portfolio artifacts.

### Phase 2: Rule-based signal path

- Implement `CompositeSignalModel` with deterministic factor weights.
- Generate `SignalRecord` and `PortAnaRecord`.
- Add report generation.

### Phase 3: Rotation strategy

- Implement `RotationMomentumStrategy`.
- Add top-N, max weight, max turnover, and optional blacklist controls.
- Compare to `TopkDropoutStrategy` on the same signal.

### Phase 4: Agent integration

- Let the agent produce `IdeaCard` only.
- Compile `IdeaCard` into `ExperimentSpec` through deterministic code.
- Require red-team checks before accepting a candidate.
- Keep every generated idea/spec/report as recorder artifacts.

## Maintainability Boundaries

Safe to add:

- `alpha_lab/*`
- docs under `docs/`
- example YAML under an external examples folder, if needed later
- tests for the external package

Do not change for this project phase:

- `qlib/data/*`
- `qlib/workflow/*`
- `qlib/backtest/*`
- `qlib/model/base.py`
- `qlib/strategy/base.py`
- `qlib/contrib/model/*`
- `qlib/contrib/data/*`
- `qlib/contrib/strategy/*`

If a Qlib behavior blocks the Alpha Lab, first wrap it externally. Only patch Qlib core for a small, well-isolated upstream bug fix.

