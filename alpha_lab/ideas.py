"""Stable research objects for Alpha Lab experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class IdeaCard:
    idea_id: str
    name: str
    thesis: str
    universe: str
    horizon: str
    rebalance: str
    factor_refs: List[str]
    constraints: Dict[str, Any] = field(default_factory=dict)
    risk_notes: List[str] = field(default_factory=list)
    expected_failure_modes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_name: str
    qlib_init: Dict[str, Any]
    market: str
    benchmark: str
    dataset: Dict[str, Any]
    signal: Dict[str, Any]
    strategy: Dict[str, Any]
    backtest: Dict[str, Any]
    validation: Dict[str, Any]


def earnings_readthrough_idea() -> IdeaCard:
    return IdeaCard(
        idea_id="ERT_v0_4_target_quality_readthrough_band",
        name="US tech target-quality earnings read-through long-only",
        thesis=(
            "Use already reported technology peers' EPS surprise breadth and moderate benchmark-excess event reactions "
            "to identify upcoming technology earnings events when the target has historically reacted well to earnings."
        ),
        universe="us_tech_ai_large_cap",
        horizon="close-to-close around earnings",
        rebalance="event-driven",
        factor_refs=[
            "peer_eps_surprise_winsorized",
            "peer_event_excess_vs_qqq",
            "peer_positive_readthrough_breadth",
            "rolling_historical_alpha_percentile_band",
            "target_prior_earnings_reaction_quality",
            "pre_event_liquidity_filter",
            "pre_event_runup_filter",
            "pre_event_volatility_filter",
        ],
        constraints={
            "long_only": True,
            "max_active_positions": 10,
            "max_weight": 0.10,
            "selection": "rolling historical alpha percentile band, no future quarter ranking",
        },
        risk_notes=[
            "Current-constituent universe has survivorship bias.",
            "Alpha Vantage data is research-grade and may not include point-in-time revisions.",
            "Daily close-to-close execution approximates earnings release timing.",
        ],
        expected_failure_modes=[
            "Peer read-through may be stale when sector dispersion is high.",
            "Pre-event run-up may already price in expected beats.",
            "API coverage and rate limits can restrict historical depth.",
        ],
    )
