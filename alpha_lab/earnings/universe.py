"""Default US technology and AI research universe."""

from __future__ import annotations

from typing import Dict, Iterable, List


DEFAULT_TECH_CLUSTERS: Dict[str, str] = {
    "AAPL": "mega_platform",
    "MSFT": "mega_platform",
    "GOOGL": "mega_platform",
    "GOOG": "mega_platform",
    "AMZN": "mega_platform",
    "META": "mega_platform",
    "NFLX": "mega_platform",
    "CRM": "enterprise_software",
    "NOW": "enterprise_software",
    "ORCL": "enterprise_software",
    "ADBE": "enterprise_software",
    "INTU": "enterprise_software",
    "SNOW": "enterprise_software",
    "DDOG": "enterprise_software",
    "PLTR": "enterprise_software",
    "PANW": "cybersecurity",
    "CRWD": "cybersecurity",
    "ZS": "cybersecurity",
    "FTNT": "cybersecurity",
    "NVDA": "semiconductor",
    "AMD": "semiconductor",
    "AVGO": "semiconductor",
    "INTC": "semiconductor",
    "QCOM": "semiconductor",
    "MU": "semiconductor",
    "TXN": "semiconductor",
    "AMAT": "semiconductor_equipment",
    "LRCX": "semiconductor_equipment",
    "KLAC": "semiconductor_equipment",
    "ASML": "semiconductor_equipment",
    "TSM": "semiconductor_foundry",
    "SMCI": "ai_infrastructure",
    "DELL": "ai_infrastructure",
    "HPE": "ai_infrastructure",
    "ANET": "ai_infrastructure",
    "CSCO": "networking",
    "IBM": "legacy_infra",
    "HPQ": "hardware",
    "DE": "industrial_ai",
    "TSLA": "ai_adjacent",
}


def default_tech_symbols() -> List[str]:
    return sorted(DEFAULT_TECH_CLUSTERS)


def clusters_for(symbols: Iterable[str]) -> Dict[str, str]:
    return {symbol.upper(): DEFAULT_TECH_CLUSTERS.get(symbol.upper(), "unclassified") for symbol in symbols}
