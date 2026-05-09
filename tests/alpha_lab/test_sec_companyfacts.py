from __future__ import annotations

import pandas as pd

from alpha_lab.data_sources.sec_companyfacts import attach_fundamental_quality_features
from alpha_lab.data_sources.sec_companyfacts import normalize_companyfacts_quarterly


def _fact(tag: str, values: list[dict]):
    return {tag: {"units": {"USD": values}}}


def _eps(values: list[dict]):
    return {"EarningsPerShareDiluted": {"units": {"USD/shares": values}}}


def _base_fact(fy: int, fp: str, end: str, filed: str, val: float, form: str = "10-Q", start: str = "2024-01-01"):
    return {
        "fy": fy,
        "fp": fp,
        "start": start,
        "end": end,
        "filed": filed,
        "form": form,
        "val": val,
        "accn": f"{fy}-{fp}",
    }


def test_sec_companyfacts_quarterly_normalization_and_quality_features():
    revenue = [
        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 100.0, start="2023-01-01"),
        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 120.0),
    ]
    payload = {
        "cik": 2488,
        "entityName": "ADVANCED MICRO DEVICES INC",
        "facts": {
            "us-gaap": {
                **_fact("RevenueFromContractWithCustomerExcludingAssessedTax", revenue),
                **_fact(
                    "GrossProfit",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 45.0, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 60.0),
                    ],
                ),
                **_fact(
                    "OperatingIncomeLoss",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 10.0, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 18.0),
                    ],
                ),
                **_fact(
                    "NetIncomeLoss",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 8.0, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 14.0),
                    ],
                ),
                **_eps(
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 0.40, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 0.56),
                    ]
                ),
                **_fact(
                    "NetCashProvidedByUsedInOperatingActivities",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 15.0, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 22.0),
                    ],
                ),
                **_fact(
                    "PaymentsToAcquirePropertyPlantAndEquipment",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 5.0, start="2023-01-01"),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 6.0),
                    ],
                ),
                **_fact(
                    "Assets",
                    [
                        _base_fact(2023, "Q1", "2023-03-31", "2023-04-28", 1000.0),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-26", 1100.0),
                    ],
                ),
            }
        },
    }

    fundamentals = normalize_companyfacts_quarterly("AMD", payload)
    assert list(fundamentals["symbol"]) == ["AMD", "AMD"]
    assert fundamentals.loc[1, "cik"] == "0000002488"
    assert fundamentals.loc[1, "revenue"] == 120.0
    assert fundamentals.loc[1, "diluted_eps"] == 0.56
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in fundamentals.loc[1, "selected_tag_map_json"]

    features = attach_fundamental_quality_features(fundamentals)
    latest = features.iloc[-1]
    assert round(latest["revenue_yoy"], 6) == 0.2
    assert round(latest["diluted_eps_yoy"], 6) == 0.4
    assert round(latest["operating_margin_delta_yoy"], 6) == round(18 / 120 - 10 / 100, 6)
    assert round(latest["fcf_margin"], 6) == round((22 - 6) / 120, 6)


def test_sec_companyfacts_prefers_latest_filing_for_same_period():
    payload = {
        "cik": 1,
        "entityName": "TEST",
        "facts": {
            "us-gaap": {
                **_fact(
                    "Revenues",
                    [
                        _base_fact(2024, "Q1", "2024-03-31", "2024-04-20", 100.0),
                        _base_fact(2024, "Q1", "2024-03-31", "2024-05-01", 105.0, form="10-Q/A"),
                    ],
                )
            }
        },
    }
    fundamentals = normalize_companyfacts_quarterly("TST", payload)
    assert len(fundamentals) == 1
    assert fundamentals.loc[0, "revenue"] == 105.0
    assert fundamentals.loc[0, "form"] == "10-Q/A"
