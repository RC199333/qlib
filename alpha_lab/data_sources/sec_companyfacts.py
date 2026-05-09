"""SEC companyfacts adapter for Alpha Lab fundamentals research."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


class SECCompanyFactsError(RuntimeError):
    """Raised when SEC companyfacts data cannot be loaded."""


DEFAULT_SEC_USER_AGENT = "AlphaLabResearch/0.1 qlib-local-research"
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

FIELD_TAGS: Mapping[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "diluted_eps": ("EarningsPerShareDiluted",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "assets": ("Assets",),
    "liabilities": ("Liabilities",),
    "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "shares_outstanding": ("EntityCommonStockSharesOutstanding",),
}

FIELD_UNITS: Mapping[str, tuple[str, ...]] = {
    "diluted_eps": ("USD/shares", "USD / shares", "USD/sh", "USD"),
    "shares_outstanding": ("shares",),
}

DEFAULT_FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}
QUARTERLY_PERIODS = {"Q1", "Q2", "Q3", "Q4"}
PERIOD_FIELDS = {
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "diluted_eps",
    "operating_cash_flow",
    "capex",
}


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").upper()


def _cik10(value: int | str) -> str:
    try:
        return f"{int(value):010d}"
    except (TypeError, ValueError) as exc:
        raise SECCompanyFactsError(f"Invalid CIK: {value}") from exc


def _to_date(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return pd.Timestamp(parsed).normalize()


def _to_number(value: Any) -> float:
    return float(pd.to_numeric(value, errors="coerce")) if value is not None else np.nan


def _preferred_units(field: str, units: Mapping[str, Any]) -> list[str]:
    preferred = list(FIELD_UNITS.get(field, ("USD",)))
    return [unit for unit in preferred if unit in units] or list(units)


def _flatten_field_facts(
    symbol: str,
    payload: Mapping[str, Any],
    field: str,
    tags: Iterable[str],
    taxonomy: str = "us-gaap",
    forms: set[str] = DEFAULT_FORMS,
) -> pd.DataFrame:
    taxonomy_facts = payload.get("facts", {}).get(taxonomy, {})
    rows: list[dict[str, Any]] = []
    for tag_priority, tag in enumerate(tags):
        tag_payload = taxonomy_facts.get(tag)
        if not tag_payload:
            continue
        units = tag_payload.get("units", {})
        for unit in _preferred_units(field, units):
            for fact in units.get(unit, []):
                form = str(fact.get("form", "")).upper()
                fp = str(fact.get("fp", "")).upper()
                if forms and form not in forms:
                    continue
                if fp not in QUARTERLY_PERIODS:
                    continue
                end = _to_date(fact.get("end"))
                start = _to_date(fact.get("start"))
                filed = _to_date(fact.get("filed"))
                if pd.isna(end) or pd.isna(filed):
                    continue
                duration_days = (end - start).days if pd.notna(start) else np.nan
                if field in PERIOD_FIELDS and (pd.isna(duration_days) or duration_days < 45 or duration_days > 130):
                    continue
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "field": field,
                        "tag": tag,
                        "tag_priority": tag_priority,
                        "unit": unit,
                        "value": _to_number(fact.get("val")),
                        "fiscal_year": pd.to_numeric(fact.get("fy"), errors="coerce"),
                        "fiscal_period": fp,
                        "start_date": start,
                        "fiscal_date_ending": end,
                        "duration_days": duration_days,
                        "filed_date": filed,
                        "form": form,
                        "accn": fact.get("accn"),
                        "frame": fact.get("frame"),
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _latest_field_values(long_facts: pd.DataFrame) -> pd.DataFrame:
    if long_facts.empty:
        return pd.DataFrame()
    out = long_facts.copy()
    out["is_amendment"] = out["form"].astype(str).str.endswith("/A")
    out = out.sort_values(
        [
            "symbol",
            "fiscal_year",
            "fiscal_period",
            "field",
            "tag_priority",
            "filed_date",
            "is_amendment",
        ]
    )
    return out.groupby(["symbol", "fiscal_year", "fiscal_period", "field"], as_index=False).tail(1)


def normalize_companyfacts_quarterly(symbol: str, payload: Mapping[str, Any]) -> pd.DataFrame:
    """Normalize SEC companyfacts JSON into one row per fiscal quarter.

    The output is revised-history fundamentals. For point-in-time research,
    consumers must use `filed_date <= signal_date` when joining features.
    """

    frames = [
        _flatten_field_facts(symbol=symbol, payload=payload, field=field, tags=tags)
        for field, tags in FIELD_TAGS.items()
    ]
    non_empty_frames = [frame for frame in frames if not frame.empty]
    long_facts = pd.concat(non_empty_frames, ignore_index=True) if non_empty_frames else pd.DataFrame()
    latest = _latest_field_values(long_facts)
    if latest.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "cik",
                "entity_name",
                "fiscal_year",
                "fiscal_period",
                "fiscal_date_ending",
                "filed_date",
                "form",
                "accn",
                *FIELD_TAGS.keys(),
                "selected_tag_map_json",
            ]
        )

    values = latest.pivot_table(
        index=["symbol", "fiscal_year", "fiscal_period"],
        columns="field",
        values="value",
        aggfunc="last",
    ).reset_index()
    meta = (
        latest.sort_values(["symbol", "fiscal_year", "fiscal_period", "filed_date"])
        .groupby(["symbol", "fiscal_year", "fiscal_period"], as_index=False)
        .tail(1)[
            [
                "symbol",
                "fiscal_year",
                "fiscal_period",
                "fiscal_date_ending",
                "filed_date",
                "form",
                "accn",
            ]
        ]
    )
    tag_maps = []
    for keys, group in latest.groupby(["symbol", "fiscal_year", "fiscal_period"], dropna=False):
        selected = {
            row["field"]: {"tag": row["tag"], "unit": row["unit"], "filed_date": str(row["filed_date"].date())}
            for row in group.to_dict("records")
        }
        tag_maps.append(
            {
                "symbol": keys[0],
                "fiscal_year": keys[1],
                "fiscal_period": keys[2],
                "selected_tag_map_json": json.dumps(selected, sort_keys=True),
            }
        )
    tag_map = pd.DataFrame(tag_maps)
    out = meta.merge(values, on=["symbol", "fiscal_year", "fiscal_period"], how="left").merge(
        tag_map, on=["symbol", "fiscal_year", "fiscal_period"], how="left"
    )
    out["cik"] = _cik10(payload.get("cik", ""))
    out["entity_name"] = payload.get("entityName", "")
    for field in FIELD_TAGS:
        if field not in out:
            out[field] = np.nan
    cols = [
        "symbol",
        "cik",
        "entity_name",
        "fiscal_year",
        "fiscal_period",
        "fiscal_date_ending",
        "filed_date",
        "form",
        "accn",
        *FIELD_TAGS.keys(),
        "selected_tag_map_json",
    ]
    return out[cols].sort_values(["symbol", "fiscal_date_ending", "filed_date"]).reset_index(drop=True)


def attach_fundamental_quality_features(fundamentals: pd.DataFrame) -> pd.DataFrame:
    out = fundamentals.copy()
    if out.empty:
        return out
    out["fiscal_date_ending"] = pd.to_datetime(out["fiscal_date_ending"], errors="coerce")
    out = out.sort_values(["symbol", "fiscal_date_ending"]).reset_index(drop=True)

    def prior_year(col: str) -> pd.Series:
        keys = ["symbol", "fiscal_year", "fiscal_period"]
        base = out[keys].reset_index().rename(columns={"index": "_row"})
        prior = out[keys + [col]].copy()
        prior["fiscal_year"] = pd.to_numeric(prior["fiscal_year"], errors="coerce") + 1
        prior = prior.rename(columns={col: "_prior_year_value"})
        merged = base.merge(prior, on=keys, how="left").sort_values("_row")
        return pd.to_numeric(merged["_prior_year_value"], errors="coerce").reset_index(drop=True)

    for col in ["revenue", "diluted_eps", "assets", "shares_outstanding"]:
        if col in out:
            prior = prior_year(col)
            out[f"{col}_yoy"] = out[col] / prior - 1.0

    out["gross_margin"] = out["gross_profit"] / out["revenue"]
    out["operating_margin"] = out["operating_income"] / out["revenue"]
    out["net_margin"] = out["net_income"] / out["revenue"]
    out["gross_margin_delta_yoy"] = out["gross_margin"] - prior_year("gross_margin")
    out["operating_margin_delta_yoy"] = out["operating_margin"] - prior_year("operating_margin")
    out["net_margin_delta_yoy"] = out["net_margin"] - prior_year("net_margin")
    out["free_cash_flow"] = out["operating_cash_flow"] - out["capex"].abs()
    out["fcf_margin"] = out["free_cash_flow"] / out["revenue"]
    avg_assets = (out["assets"] + prior_year("assets")) / 2.0
    out["accruals_to_assets"] = (out["net_income"] - out["operating_cash_flow"]) / avg_assets
    return out.replace([np.inf, -np.inf], np.nan)


@dataclass
class SECCompanyFactsClient:
    cache_dir: Path = Path("data/alpha_lab/fundamentals/raw/sec_companyfacts")
    user_agent: Optional[str] = None
    timeout: int = 60

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.user_agent = self.user_agent or os.getenv("SEC_USER_AGENT") or DEFAULT_SEC_USER_AGENT

    def _request_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "User-Agent": str(self.user_agent),
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urlopen(request, timeout=self.timeout) as resp:  # noqa: S310
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))

    def company_tickers(self, force: bool = False) -> pd.DataFrame:
        cache_path = self.cache_dir / "company_tickers.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = self._request_json(SEC_TICKER_URL)
            cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        rows = list(payload.values()) if isinstance(payload, dict) else payload
        out = pd.DataFrame(rows)
        if out.empty:
            raise SECCompanyFactsError("SEC company_tickers mapping is empty.")
        out["symbol"] = out["ticker"].astype(str).str.upper()
        out["cik"] = out["cik_str"].map(_cik10)
        out["title"] = out["title"].astype(str)
        return out[["symbol", "cik", "title"]].sort_values("symbol").reset_index(drop=True)

    def ticker_to_cik(self, symbol: str, force_mapping: bool = False) -> str:
        mapping = self.company_tickers(force=force_mapping)
        match = mapping[mapping["symbol"] == symbol.upper()]
        if match.empty:
            raise SECCompanyFactsError(f"No SEC CIK found for symbol {symbol}.")
        return str(match.iloc[0]["cik"])

    def companyfacts_by_cik(self, cik: int | str, force: bool = False) -> dict[str, Any]:
        cik10 = _cik10(cik)
        cache_path = self.cache_dir / "companyfacts" / f"CIK{cik10}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.exists() and not force:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        payload = self._request_json(SEC_COMPANYFACTS_URL.format(cik=cik10))
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def companyfacts(self, symbol: str, force: bool = False, force_mapping: bool = False) -> dict[str, Any]:
        cik = self.ticker_to_cik(symbol, force_mapping=force_mapping)
        return self.companyfacts_by_cik(cik, force=force)

    def quarterly_fundamentals(self, symbol: str, force: bool = False, force_mapping: bool = False) -> pd.DataFrame:
        payload = self.companyfacts(symbol, force=force, force_mapping=force_mapping)
        return attach_fundamental_quality_features(normalize_companyfacts_quarterly(symbol, payload))


def load_sec_quarterly_fundamentals(
    client: SECCompanyFactsClient,
    symbols: Iterable[str],
    delay_seconds: float = 0.11,
    force: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    frames = []
    failed = []
    symbol_list = [str(symbol).upper() for symbol in symbols]
    for idx, symbol in enumerate(symbol_list):
        try:
            frame = client.quarterly_fundamentals(symbol, force=force)
            if not frame.empty:
                frames.append(frame)
            else:
                failed.append(symbol)
        except Exception as exc:  # noqa: BLE001
            failed.append(symbol)
            print(f"{symbol}: {exc}")
        if delay_seconds > 0 and idx < len(symbol_list) - 1:
            time.sleep(delay_seconds)
    if not frames:
        return pd.DataFrame(), failed
    out = pd.concat(frames, ignore_index=True).sort_values(["symbol", "fiscal_date_ending"]).reset_index(drop=True)
    return out, failed
