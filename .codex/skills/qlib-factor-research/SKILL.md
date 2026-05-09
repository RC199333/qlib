---
name: qlib-factor-research
description: Qlib-based alpha factor research workflow for this fork. Use when Codex is asked to research, implement, backtest, validate, iterate, or review quant factors, event strategies, signals, datasets, Qlib workflow configs, alpha_lab research code, or local US/CN market data in this repository while avoiding unnecessary platform engineering.
---

# Qlib Factor Research

Use this skill to behave like a disciplined quant developer working on this Qlib fork. The goal is alpha research, not building a separate platform. Keep Qlib core stable, make factor changes traceable, and produce a complete research run: idea, spec, data, factor, backtest, validation, report, manifest, and charts.

## Operating Rules

- Treat this repo's Qlib install and data layout as the base system. Do not modify `qlib/` core unless the user explicitly asks for a core fix.
- Prefer small factor-version iterations over broad abstractions. A factor version should answer a research question.
- Keep research artifacts reproducible: exact universe, date range, data source, feature formula, execution rule, cost model, benchmark, and command.
- Separate economic signal from filters. Do not bury liquidity, momentum, event timing, or volatility guards inside one opaque score unless the research question requires it.
- Never report a backtest as good without event count, turnover/costs, benchmark-relative performance, drawdown, Sharpe/IR, by-year behavior, and known data caveats.
- Preserve API keys and paid/raw data hygiene. Do not save secrets in configs, reports, MLflow artifacts, or committed files.

## Workflow

1. Define or generate the research idea.
   - If the user gives a rough idea, convert it into an `IdeaCard`.
   - If the user asks for ideas, generate a short ranked list with mechanism, data availability, expected failure mode, and implementation cost.
   - Name the factor family and version, for example `ERT_v0_2_readthrough_breadth_topq`.

2. Write the `ExperimentSpec`.
   - Include hypothesis, universe, provider URI, benchmark, signal timestamp, holding horizon, costs, train/validation/test split, and external data assumptions.
   - State the exact output artifacts before implementation.

3. Map the Qlib integration point.
   - For standard supervised alpha: use Qlib `DataHandler -> Dataset -> Model -> SignalRecord -> Strategy -> Backtest -> PortAnaRecord`.
   - For event-driven research: keep supplemental event data outside Qlib core, use Qlib market data for point-in-time prices, and make the event runner explicit.
   - Read `references/qlib-repo-map.md` when choosing files or extension points.

4. Implement the smallest production-grade research slice.
   - Add or edit only the relevant factor module, script, test, or report template.
   - Reuse existing `alpha_lab/` utilities when they directly fit; do not create a generic subsystem for one idea.
   - Keep factor formula components named and export intermediate columns for audit.
   - Generate the full artifact set described in `references/artifact-contract.md`.

5. Backtest and validate before interpreting.
   - Run focused unit tests for data alignment and formula logic.
   - Run at least one reproducible backtest command.
   - Inspect selected trades/events, missing data, survivorship bias, and benchmark-relative returns.
   - Read `references/research-validation.md` before finalizing results.

6. Report in QR format.
   - Lead with pass/fail or research status.
   - Include exact formula, parameters, date range, universe, costs, benchmark, metrics, charts/artifacts, commands, and failure modes.
   - Distinguish confirmed results from hypotheses and next experiments.
   - Run `scripts/check_qr_run_artifacts.py <run_dir>` when a run directory is produced.

## Naming

- Use family/version names for factor iterations: `<FAMILY>_v<major>_<minor>_<short_description>`.
- Use `v0_x` for exploratory iterations, `v1_0` only after the spec is locked and reproducible.
- Encode the meaningful research change in the suffix, for example:
  - `ERT_v0_1_readthrough_close2close`
  - `ERT_v0_2_readthrough_breadth_topq`
  - `ERT_v0_3_peer_excess_revision_filter`

## Common Anti-Patterns

- Adding a platform layer when a factor-version script or report is enough.
- Ending at a notebook, partial smoke test, or ad hoc printout instead of a complete run directory.
- Selecting thresholds after seeing full-period results without train/validation/test separation.
- Mixing future earnings data into pre-event signals.
- Reporting raw absolute return for tech names without QQQ or SPY-relative event return.
- Treating Yahoo or Alpha Vantage data as institutional-grade without caveats.
- Optimizing for high Sharpe on tiny event counts.
- Producing charts without the underlying CSV/JSON used to make them.

## References

- `references/qlib-repo-map.md`: local Qlib architecture, extension points, and files to avoid.
- `references/qr-production-chain.md`: end-to-end QR chain from idea generation to research decision.
- `references/artifact-contract.md`: required run directory, manifest, report, and chart outputs.
- `references/research-validation.md`: minimum validation checklist for factor and event-strategy work.

## Utilities

- `scripts/check_qr_run_artifacts.py`: validates that a factor run directory contains the required manifest, report, metrics, commands, and chart artifacts.
