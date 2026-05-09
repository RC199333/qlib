# Qlib Onboarding for an Alpha Research Agent

This note maps the parts of Qlib that matter for building an alpha research layer on top of this fork. It is intentionally extension-oriented: keep Qlib core stable, add custom research objects in a separate package, and connect them through Qlib's config/import interfaces.

## Architecture Map

Qlib is organized as a loose pipeline:

```text
qlib.init
  -> Config C and provider_uri
  -> qlib.data wrappers and expression operators
  -> qlib.workflow.R recorder

Data access
  -> qlib.data.D
  -> providers: calendar, instruments, features, expressions, datasets
  -> loaders and handlers

Research workflow
  -> DatasetH
  -> Model.fit / Model.predict
  -> SignalRecord / SigAnaRecord / PortAnaRecord

Trading workflow
  -> Signal
  -> Strategy.generate_trade_decision
  -> Executor / Exchange / Account
  -> portfolio metrics, indicators, risk analysis
```

Important modules:

| Area | Files | Role |
| --- | --- | --- |
| Initialization/config | `qlib/__init__.py`, `qlib/config.py` | `qlib.init(...)` resolves `provider_uri`, configures region, registers data wrappers, registers expression operators, and registers the workflow recorder. |
| Data API | `qlib/data/data.py`, `qlib/data/__init__.py` | Global `D` exposes calendars, instruments, feature expressions, and datasets. Local providers read Qlib binary data; client providers support remote/server mode. |
| Expression engine | `qlib/data/base.py`, `qlib/data/ops.py` | `$close`, `Ref(...)`, `Mean(...)`, `Rank(...)`, etc. are parsed into `Expression` objects and evaluated per instrument. |
| Loader/handler/dataset | `qlib/data/dataset/loader.py`, `qlib/data/dataset/handler.py`, `qlib/data/dataset/__init__.py` | Load expression fields, process data, and slice it into train/valid/test segments for models. |
| Contrib datasets | `qlib/contrib/data/handler.py`, `qlib/contrib/data/loader.py` | `Alpha158` and `Alpha360` are standard `DataHandlerLP` implementations backed by `QlibDataLoader`. |
| Model interface | `qlib/model/base.py`, `qlib/contrib/model/*` | Models implement `fit(dataset, ...)` and `predict(dataset, segment="test")`. |
| Workflow runner | `qlib/cli/run.py`, `qlib/model/trainer.py` | `qrun` renders YAML, calls `qlib.init`, initializes model/dataset from config, trains, saves artifacts, and generates records. |
| Experiment recorder | `qlib/workflow/__init__.py`, `qlib/workflow/expm.py`, `qlib/workflow/exp.py`, `qlib/workflow/recorder.py`, `qlib/workflow/record_temp.py` | `R` wraps MLflow-style experiments, recorders, metrics, params, tags, and artifacts. |
| Signal bridge | `qlib/backtest/signal.py` | Converts model+dataset, dataframe/series, or custom `Signal` implementations into `get_signal(start_time, end_time)`. |
| Strategies | `qlib/strategy/base.py`, `qlib/contrib/strategy/signal_strategy.py`, `qlib/contrib/strategy/rule_strategy.py` | Strategies transform signals or rules into trade decisions/orders. |
| Backtest | `qlib/backtest/__init__.py`, `qlib/backtest/backtest.py`, `qlib/backtest/executor.py`, `qlib/backtest/exchange.py`, `qlib/backtest/report.py` | Builds exchange/account, runs strategy/executor loop, records portfolio and trade indicator data. |
| Analysis/reporting | `qlib/contrib/evaluate.py`, `qlib/contrib/report/*`, `docs/component/report.rst` | Computes IC, rank IC, risk metrics, indicator analysis, and graphs. |

## Main Data Flow

The standard research-to-backtest flow is:

```text
provider_uri
  -> qlib.init(provider_uri=..., region=...)
  -> D.features / D.instruments / D.calendar
  -> QlibDataLoader
  -> DataHandlerLP
  -> DatasetH
  -> Model.fit and Model.predict
  -> SignalRecord(pred.pkl, label.pkl)
  -> SignalWCache / ModelSignal
  -> Strategy
  -> backtest(...)
  -> PortAnaRecord portfolio_analysis/*
```

### 1. provider_uri -> data providers

`qlib.init(provider_uri=..., region=...)` calls `C.set(...)`, resolves the data path through `QlibConfig.DataPathManager`, then registers wrappers in `qlib/data/data.py`.

After registration, `from qlib.data import D` gives access to:

- `D.calendar(...)`
- `D.instruments(...)`
- `D.list_instruments(...)`
- `D.features(instruments, fields, start_time, end_time, freq=...)`

For local mode, providers read Qlib-format files under a data root with directories such as `calendars`, `instruments`, and `features`. `LocalDatasetProvider.dataset(...)` uses instrument pools and expression fields to assemble a dataframe indexed by `datetime` and `instrument`.

### 2. DataHandler -> Dataset

`QlibDataLoader` receives a config such as:

```yaml
config:
  feature:
    - ["Ref($close, 5) / $close"]
    - ["ROC5"]
  label:
    - ["Ref($close, -2) / Ref($close, -1) - 1"]
    - ["LABEL0"]
```

It calls `D.features(...)` and returns grouped columns such as `feature` and `label`.

`DataHandlerLP` adds processor pipelines:

- `infer_processors`: transformations available for inference, usually cleaning and normalization.
- `learn_processors`: transformations for training labels/features, including learnable processors fitted on training dates.
- `process_type`: controls how infer/learn processors are applied.

`DatasetH` wraps a handler and named time segments:

```yaml
segments:
  train: [2008-01-01, 2014-12-31]
  valid: [2015-01-01, 2016-12-31]
  test:  [2017-01-01, 2020-08-01]
```

Models call:

- `dataset.prepare("train", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)`
- `dataset.prepare("test", col_set="feature", data_key=DataHandlerLP.DK_I)`

### 3. Dataset -> Model -> SignalRecord

Model classes inherit `qlib.model.base.Model` or `ModelFT` and implement:

- `fit(dataset, ...)`
- `predict(dataset, segment="test")`

Representative examples:

- `qlib/contrib/model/gbdt.py::LGBModel`
- `qlib/contrib/model/linear.py::LinearModel`
- `qlib/contrib/model/pytorch_nn.py::DNNModelPytorch`
- `qlib/contrib/model/pytorch_lstm.py::LSTM`

`SignalRecord(model, dataset, recorder).generate()` calls `model.predict(dataset)`, saves `pred.pkl`, and, for `DatasetH`, also saves raw `label.pkl`.

### 4. SignalRecord -> Strategy

Qlib converts predictions into strategy input through `qlib/backtest/signal.py`:

- `SignalWCache(pd.Series | pd.DataFrame)` stores prediction scores and serves the latest value for each decision interval.
- `ModelSignal(model, dataset)` calls `model.predict(dataset)` and wraps the result.
- `create_signal_from(...)` accepts a `Signal`, `(model, dataset)`, config dict, string config, or dataframe/series.

`TopkDropoutStrategy` and `WeightStrategyBase` inherit `BaseSignalStrategy`, which accepts `signal=...`. Older `model=..., dataset=...` kwargs still work but are deprecated.

### 5. Strategy -> Backtest

`qlib.backtest.backtest(...)` builds:

- an `Account` from initial cash/positions,
- an `Exchange` from `exchange_kwargs`,
- a strategy from config,
- an executor from config.

The core loop is in `qlib/backtest/backtest.py`:

```text
executor.reset(...)
strategy.reset(level_infra=executor.get_level_infra())
while not executor.finished():
    decision = strategy.generate_trade_decision(previous_execute_result)
    execute_result = executor.collect_data(decision)
    strategy.post_exe_step(execute_result)
```

`SimulatorExecutor` executes orders through `Exchange.deal_order(...)`, updates account state, and records portfolio metrics and indicators.

### 6. Backtest -> PortAnaRecord

`PortAnaRecord` depends on `SignalRecord`. It loads `pred.pkl`, replaces `<PRED>` placeholders in strategy/executor config, runs `qlib.backtest.backtest(...)`, and saves artifacts under `portfolio_analysis/`, including:

- `report_normal_<freq>.pkl`
- `positions_normal_<freq>.pkl`
- `indicators_normal_<freq>.pkl`
- `port_analysis_<freq>.pkl`
- `indicator_analysis_<freq>.pkl`

It also logs flattened metrics to the active recorder.

## Where Custom Factors and Signals Should Plug In

Preferred extension points, from least invasive to most specialized:

1. **Formulaic factors in loader config**
   - Use existing expression strings in a custom handler or task config.
   - Example: `Ref($close, 20) / $close - 1`, `Mean($volume, 20) / ($volume + 1e-12)`.
   - Best for most alpha ideas because it requires no Qlib core change.

2. **Custom DataHandler outside Qlib core**
   - Create a new class inheriting `DataHandlerLP`.
   - Use `QlibDataLoader` with custom `feature` and `label` groups.
   - Put it in an external package, then reference it by `module_path` in YAML.

3. **Custom Processor outside Qlib core**
   - Inherit `qlib.data.dataset.processor.Processor`.
   - Use when the transformation is not naturally expressible as a per-instrument expression.
   - Keep train-fit state inside processor attributes and pass `fit_start_time`/`fit_end_time` as needed.

4. **Custom expression operator**
   - Inherit from `ExpressionOps`, `ElemOperator`, or `PairOperator`.
   - Register with `qlib.init(custom_ops=[...])`.
   - Only use for reusable formula operations that must run inside `D.features(...)`.

5. **Rule-based signal adapter**
   - Implement `qlib.backtest.signal.Signal.get_signal(start_time, end_time)`.
   - Or return a `pd.Series`/`pd.DataFrame` indexed by `datetime, instrument` and let `SignalWCache` wrap it.
   - Best for an Alpha Research Agent that emits scores without training a Qlib `Model`.

## Where Custom Portfolio Strategy Should Plug In

Use `qlib.strategy.base.BaseStrategy` or `qlib.contrib.strategy.signal_strategy.WeightStrategyBase`.

Recommended path for a rotation strategy:

- Inherit `WeightStrategyBase`.
- Override `generate_target_weight_position(score, current, trade_start_time, trade_end_time)`.
- Let `OrderGenerator` translate target weights into executable orders.
- Keep signal scoring separate from portfolio construction.

Use direct `BaseStrategy.generate_trade_decision(...)` only if the strategy needs custom order logic that target weights cannot represent.

## How Experiments Are Recorded

The recorder system is centered on `qlib.workflow.R`.

Typical flow:

```python
with R.start(experiment_name="workflow"):
    R.log_params(...)
    model.fit(dataset)
    R.save_objects(**{"params.pkl": model})
    SignalRecord(model, dataset, R.get_recorder()).generate()
    PortAnaRecord(R.get_recorder(), config).generate()
```

`qrun` follows the same pattern through `qlib/model/trainer.py`:

1. `task_train(...)` starts a recorder.
2. `_log_task_info(...)` logs flattened task params and saves raw task config.
3. `_exe_task(...)` initializes model and dataset.
4. `model.fit(dataset)` trains the model.
5. `params.pkl` and `dataset` are saved.
6. Record templates generate predictions, signal analysis, portfolio analysis, and logged metrics.

The default backend is `MLflowExpManager`, with tracking URI configured by `exp_manager` or by `qrun` under `mlruns`.

## Safe Extension Points

Use these without touching core files:

| Extension need | Safe location/pattern |
| --- | --- |
| Alpha ideas and experiment specs | A new external package such as `alpha_lab/ideas.py` and config YAML generated for `qrun`. |
| Factor definitions | Config-driven expression lists, or a custom handler outside `qlib/`. |
| Reusable factor registry | External registry that emits `QlibDataLoader` feature config. |
| Rule-based signals | External class implementing `qlib.backtest.signal.Signal`. |
| Composite signal model | External class inheriting `qlib.model.base.Model`, or a plain signal dataframe passed to strategy. |
| Portfolio strategy | External class inheriting `WeightStrategyBase` or `BaseStrategy`. |
| Backtest runner | External code that calls `qlib.init`, builds configs, uses `R.start`, `SignalRecord`, and `PortAnaRecord`. |
| Validation checks | External code that reads predictions, labels, positions, reports, and recorder artifacts. |
| Report generator | External code using `qlib.contrib.report`, recorder artifacts, pandas, and markdown/HTML output. |

## Files to Avoid Touching

Avoid editing Qlib core unless there is a clear upstream-worthy bug fix:

- `qlib/config.py`
- `qlib/__init__.py`
- `qlib/data/data.py`
- `qlib/data/base.py`
- `qlib/data/ops.py`
- `qlib/data/cache.py`
- `qlib/data/dataset/handler.py`
- `qlib/data/dataset/loader.py`
- `qlib/data/dataset/__init__.py`
- `qlib/model/base.py`
- `qlib/model/trainer.py`
- `qlib/workflow/*`
- `qlib/backtest/*`
- `qlib/strategy/base.py`

Treat `qlib/contrib/*` as examples and upstream-compatible contrib modules, not as the first place for private agent code. A maintainable fork should keep custom research code outside `qlib/` and connect it through `module_path` config entries.

