# Qlib Repo Map For Factor Research

Use this reference before choosing where to add code or how to connect a factor to Qlib.

## Core Flow

Canonical Qlib flow:

`provider_uri -> qlib.data -> DataHandler -> Dataset -> Model -> SignalRecord -> Strategy -> Backtest -> PortAnaRecord`

- `provider_uri`: local Qlib binary market data root, for example CN, legacy US, or recent US data.
- `qlib.data`: `D.features`, calendars, instruments, and provider access.
- `DataHandler`: feature/label construction and data cleaning.
- `Dataset`: train/valid/test segmentation over handler output.
- `Model`: fitted predictive model or wrapper around deterministic signals.
- `SignalRecord`: persisted predictions/signals under a Qlib experiment.
- `Strategy`: turns signals into orders and portfolio decisions.
- `Backtest`: simulates fills, costs, account, and positions.
- `PortAnaRecord`: records portfolio analysis metrics/artifacts.

## Safe Extension Points

- `examples/`: workflow configs, benchmark variations, and reproducible run examples.
- `scripts/`: local setup, data update, and one-command research runners.
- `docs/research/`: research notes and final factor reports.
- `tests/alpha_lab/`: focused tests for supplemental research utilities.
- `alpha_lab/`: external research helpers for data sources, event studies, reports, and factor prototypes. Keep this thin and factor-driven.
- Qlib config YAMLs: safe for new benchmark or workflow variants when they do not alter core behavior.

## Qlib Core Areas To Avoid

Avoid modifying these unless the user asks for a Qlib framework bug fix:

- `qlib/data/`
- `qlib/workflow/`
- `qlib/backtest/`
- `qlib/contrib/strategy/`
- `qlib/contrib/data/handler/`
- `qlib/contrib/model/`

Read these modules for architecture and extension patterns, but keep fork maintenance risk low by extending outside core.

## Event-Driven Research Pattern

For event factors such as earnings read-through:

1. Use Qlib data for tradable price, volume, benchmark, and calendar alignment.
2. Store supplemental event/fundamental data outside Qlib core.
3. Align all events to the tradable calendar before building signals.
4. Export intermediate features and selected trades for audit.
5. Use Qlib experiments or MLflow only for artifact tracking, not as a reason to force the event study into a supervised model shape.

## Data Boundaries

- Treat current-constituent US universes as survivorship-biased unless historical constituents are loaded.
- Treat community/Yahoo/Alpha Vantage data as research-grade.
- Document every external data source, API endpoint, cache path, and refresh command.
- Never commit raw API-key-bearing files or generated private caches.
