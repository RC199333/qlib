"""Earnings event normalization and trading-day alignment."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


REQUIRED_EVENT_COLUMNS = {"symbol", "reported_date"}


def load_events_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return normalize_event_frame(df)


def normalize_event_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_EVENT_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required event columns: {sorted(missing)}")

    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.upper()
    out["reported_date"] = pd.to_datetime(out["reported_date"], errors="coerce").dt.normalize()
    if "fiscal_date_ending" in out:
        out["fiscal_date_ending"] = pd.to_datetime(out["fiscal_date_ending"], errors="coerce").dt.normalize()

    for col in ["reported_eps", "estimated_eps", "surprise", "surprise_percentage"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = pd.NA

    out = out.dropna(subset=["symbol", "reported_date"])
    return out.sort_values(["reported_date", "symbol"]).reset_index(drop=True)


def _previous_trading_day(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> Optional[pd.Timestamp]:
    candidates = calendar[calendar < date]
    if len(candidates) == 0:
        return None
    return pd.Timestamp(candidates[-1])


def _next_trading_day(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> Optional[pd.Timestamp]:
    candidates = calendar[calendar > date]
    if len(candidates) == 0:
        return None
    return pd.Timestamp(candidates[0])


def prepare_earnings_events(
    events: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    out = normalize_event_frame(events)
    calendar = pd.DatetimeIndex(pd.DatetimeIndex(pd.to_datetime(calendar)).sort_values().normalize().unique())

    if start:
        out = out[out["reported_date"] >= pd.Timestamp(start)]
    if end:
        out = out[out["reported_date"] <= pd.Timestamp(end)]

    aligned = []
    for row in out.to_dict("records"):
        reported_date = pd.Timestamp(row["reported_date"])
        entry_date = _previous_trading_day(calendar, reported_date)
        exit_date = _next_trading_day(calendar, reported_date)
        if entry_date is None or exit_date is None:
            continue
        row["entry_date"] = entry_date
        row["exit_date"] = exit_date
        row["event_id"] = f"{row['symbol']}_{reported_date:%Y%m%d}"
        aligned.append(row)

    if not aligned:
        return pd.DataFrame(columns=list(out.columns) + ["entry_date", "exit_date", "event_id"])
    return pd.DataFrame(aligned).sort_values(["entry_date", "symbol"]).reset_index(drop=True)
