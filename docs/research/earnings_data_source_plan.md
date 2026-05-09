# Earnings Data Source Plan

## Current Local State

The immediate bottleneck is earnings data coverage, not Qlib price data.

Current local Alpha Vantage earnings cache:

```text
data/alpha_lab/earnings/raw/alpha_vantage/earnings
```

Cached symbols as of 2026-05-08:

```text
AAPL, ADBE, AMAT, AMD, AMZN, AVGO, CRM, CRWD, FTNT, GOOGL, INTC, INTU,
KLAC, LRCX, META, MSFT, MU, NFLX, NOW, NVDA, ORCL, PANW, PLTR, QCOM, TXN
```

Count: 25 symbols.

Latest PEAD run diagnostics:

```text
available_price_symbol_count = 49
requested_symbol_count = 51
missing_earnings_symbols = 24
missing_price_symbols = SNOW, TSM
```

Missing earnings symbols within the currently price-available Qlib universe:

```text
ADI, ADSK, ANET, ASML, CSCO, DDOG, DE, DELL, GOOG, HPE, HPQ, IBM, MPWR,
MRVL, NXPI, ON, PYPL, SHOP, SMCI, TSLA, TTD, UBER, WDAY, ZS
```

The full expanded symbol list has 26 uncached symbols because it also includes `SNOW` and `TSM`. Those two should not affect the current PEAD backtest until local Qlib price data is added for them.

## Recommended Near-Term Solution

Use Alpha Vantage as an incremental daily cache. The free key is capped, so the right workflow is to request the next missing batch each day, write responses to local JSON, and never re-request cached symbols unless explicitly forced.

Dry run:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_alpha_vantage_earnings_incremental.py --dry-run --limit 25
```

Run:

```powershell
$env:ALPHAVANTAGE_API_KEY = "<your key>"
.\.venv\Scripts\python.exe scripts\backfill_alpha_vantage_earnings_incremental.py --limit 20 --sleep 13
```

The script skips cached symbols, downloads missing symbols, and stops early if Alpha Vantage returns a rate-limit response. `--sleep 13` keeps the request rate conservative.

Use `--force` only when deliberately refreshing already-cached files:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_alpha_vantage_earnings_incremental.py --symbols DDOG,ZS --force --limit 2 --sleep 13
```

For the current PEAD backtest, the most efficient command is to request only the 24 price-available missing earnings symbols:

```powershell
$env:ALPHAVANTAGE_API_KEY = "<your key>"
.\.venv\Scripts\python.exe scripts\backfill_alpha_vantage_earnings_incremental.py --limit 24 --sleep 13 --symbols ADI,ADSK,ANET,ASML,CSCO,DDOG,DE,DELL,GOOG,HPE,HPQ,IBM,MPWR,MRVL,NXPI,ON,PYPL,SHOP,SMCI,TSLA,TTD,UBER,WDAY,ZS
```

## Source Assessment

### Alpha Vantage

Alpha Vantage `EARNINGS` gives quarterly historical fields that are directly useful for PEAD:

```text
reportedDate, reportedEPS, estimatedEPS, surprise, surprisePercentage
```

Strengths:

- Best immediate fit for `surprise_percentage`.
- Easy to cache by symbol.
- Already integrated in `alpha_lab.data_sources.alpha_vantage`.

Weaknesses:

- Free-tier request cap is binding.
- Research-grade only; not guaranteed point-in-time.
- Coverage quality varies by symbol.

Decision: keep it as the primary free EPS surprise source for now, but cache incrementally and record coverage gaps in every run manifest.

### SEC companyfacts

SEC companyfacts is official and free, and it can provide actual reported fundamentals through XBRL tags.

Strengths:

- Official issuer filings source.
- Free and broad for US-listed companies.
- Useful for actual revenue, EPS-related facts, margins, and balance sheet quality proxies.

Weaknesses:

- No analyst consensus estimate.
- No direct `surprise_percentage`.
- Earnings announcement timestamp must be joined from another source.
- XBRL taxonomy and restatement handling require careful normalization.

Decision: use as a second-stage actual fundamentals source, especially for revenue growth, margin quality, and balance sheet filters. Do not use it alone as PEAD surprise data.

Local implementation status:

```text
adapter = alpha_lab/data_sources/sec_companyfacts.py
backfill = scripts/backfill_sec_companyfacts.py
processed = data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv
coverage = 49 processed symbols, 1932 quarterly rows
missing_or_empty = ASML, TSM
```

The first PEAD extension should use SEC fields conservatively:

```text
PEAD_v2_selected =
    PEAD_v1_selected
and revenue_yoy > 0
and operating_margin_delta_yoy >= 0
```

`fcf_margin` should remain diagnostic for now because SEC cash-flow facts are often reported year-to-date; the adapter only accepts facts whose duration looks like a discrete quarter.

### SimFin

SimFin provides company financial statements and share-price data through a documented API and bulk downloads.

Strengths:

- More convenient normalized fundamentals than raw SEC XBRL.
- Useful for actual fundamentals and quality proxies.

Weaknesses:

- Free access and licensing must be checked before using it as a persistent research dataset.
- It is not a clean replacement for analyst consensus surprise unless the specific needed fields are available in the chosen plan.

Decision: evaluate as a supplemental fundamentals source, not as the primary earnings-surprise source.

### Yahoo earnings calendar GitHub scrapers

There are GitHub projects that scrape Yahoo earnings calendars.

Strengths:

- Useful for future calendar events.
- Good for building a local calendar cache when no paid vendor is available.

Weaknesses:

- Scrapers are fragile because Yahoo page/API behavior can change.
- Historical depth and actual/estimate/surprise coverage are not guaranteed.
- License and maintenance quality vary by repository.

Decision: acceptable for future earnings calendar enrichment, but not reliable enough as the main historical PEAD backtest source without validation.

### Static GitHub / Kaggle-style CSV datasets

Open static datasets exist, but the usual problems are severe:

- stale snapshots;
- unclear license;
- incomplete ticker coverage;
- missing exact announcement date or consensus estimate;
- unclear revision history;
- no point-in-time guarantee.

Decision: do not use an unverified static GitHub CSV as the main research dataset. It can be used only as a temporary comparison sample after source, license, and schema are recorded.

## Target Data Stack

Recommended free / low-cost stack for this fork:

1. Alpha Vantage incremental cache for EPS surprise.
2. SEC companyfacts or SimFin for actual fundamentals and quality controls.
3. Yahoo calendar scraper only for future calendar dates and missing event-date checks.
4. Qlib US daily prices for return, liquidity, volatility, and benchmark-relative features.
5. Optional paid source later if this strategy graduates from research:
   - historical earnings timestamp,
   - consensus EPS and revenue estimates,
   - guidance,
   - analyst revisions,
   - point-in-time universe membership.

## Validation Rules

Every earnings-data import must record:

- source name and URL;
- fetch date;
- raw file path;
- symbol coverage;
- min and max reported date;
- rows with missing actual EPS, estimated EPS, or reported date;
- duplicate `(symbol, reported_date)` rows;
- whether the data is point-in-time or revised history;
- whether report timing is after-market, pre-market, or unknown.

Every factor report should include:

- total requested universe;
- available price symbols;
- available earnings symbols;
- missing earnings symbols;
- missing price symbols;
- selected event count;
- selected symbol concentration;
- benchmark-exposure-matched excess return.

## References

- Alpha Vantage API documentation: https://www.alphavantage.co/documentation/
- Alpha Vantage support and API key limits: https://www.alphavantage.co/support/
- SEC EDGAR API documentation: https://www.sec.gov/edgar/sec-api-documentation
- SimFin documentation: https://simfin.readthedocs.io/
- Yahoo earnings calendar scraper example: https://github.com/wenboyu2/yahoo-earnings-calendar
- Finance calendar scraper example: https://github.com/s-kerin/finance_calendars
