"""Price loading helpers for Qlib-backed earnings research."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd


def load_qlib_ohlcv(
    symbols: Iterable[str],
    provider_uri: str | Path,
    start_time: str,
    end_time: str,
    region: str = "us",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    import qlib
    from qlib.data import D

    provider_path = Path(provider_uri).expanduser()
    symbol_list = sorted({str(symbol).upper() for symbol in symbols})
    features_dir = provider_path / "features"
    if features_dir.exists():
        available = {path.name.upper() for path in features_dir.iterdir() if path.is_dir()}
        symbol_list = [symbol for symbol in symbol_list if symbol.upper() in available]
    if not symbol_list:
        raise ValueError("No requested symbols are available in the Qlib provider.")

    qlib.init(provider_uri=str(provider_path), region=region, kernels=1)
    raw = D.features(
        symbol_list,
        ["$close", "$volume"],
        start_time=start_time,
        end_time=end_time,
        freq="day",
    )
    if raw.empty:
        raise ValueError("Qlib returned no price data for the requested symbols and dates.")
    frame = raw.reset_index()
    close = frame.pivot(index="datetime", columns="instrument", values="$close").sort_index()
    volume = frame.pivot(index="datetime", columns="instrument", values="$volume").sort_index()
    close.index = pd.DatetimeIndex(close.index).normalize()
    volume.index = pd.DatetimeIndex(volume.index).normalize()
    return close, volume, pd.DatetimeIndex(close.index)
