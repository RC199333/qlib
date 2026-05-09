# SEC Companyfacts and SimFin Evaluation

## Conclusion

Neither SEC companyfacts nor SimFin directly replaces Alpha Vantage `EARNINGS` for PEAD, because neither gives a clean analyst consensus EPS surprise field equivalent to:

```text
reported_eps, estimated_eps, surprise, surprise_percentage
```

They are still useful. The right role is:

1. Alpha Vantage remains the EPS surprise source.
2. SEC companyfacts becomes the free, auditable actual-fundamentals source.
3. SimFin becomes an optional normalized-fundamentals source if we accept its account, history, and data-use constraints.

For the current `PEAD_v1_quality_drift_60d`, these sources should improve quality filters and feature richness, not replace the event surprise label.

## SEC Companyfacts

Official source:

- SEC API overview: https://data.sec.gov/
- SEC EDGAR API docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC developer resources and fair-access policy: https://www.sec.gov/about/developer-resources

### Access

No API key is required. The SEC says `data.sec.gov` hosts RESTful JSON APIs and currently includes submissions history and XBRL financial-statement data. Main endpoints:

```text
https://data.sec.gov/submissions/CIK##########.json
https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/AccountsPayableCurrent.json
https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
https://data.sec.gov/api/xbrl/frames/us-gaap/AccountsPayableCurrent/USD/CY2019Q1I.json
```

The CIK must be 10 digits with leading zeros. Bulk `companyfacts.zip` is also available and updated nightly.

Fair access:

- keep requests efficient;
- use a clear `User-Agent`;
- stay under SEC fair-access guidance, currently no more than 10 requests per second;
- prefer bulk ZIP for large jobs.

### Available Data

`companyfacts` returns all non-custom taxonomy facts for a company in one JSON call. Practical columns after normalization:

```text
symbol
cik
entity_name
taxonomy
tag
unit
val
start
end
fy
fp
form
filed
accn
frame
```

Useful US-GAAP tags for our factors:

| Feature family | Candidate tags |
| --- | --- |
| Revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` |
| Net income | `NetIncomeLoss` |
| Diluted EPS | `EarningsPerShareDiluted` |
| Operating income | `OperatingIncomeLoss` |
| Gross profit | `GrossProfit` |
| Operating cash flow | `NetCashProvidedByUsedInOperatingActivities` |
| Capex | `PaymentsToAcquirePropertyPlantAndEquipment` |
| Assets | `Assets` |
| Liabilities | `Liabilities` |
| Equity | `StockholdersEquity` |
| Shares | `CommonStocksIncludingAdditionalPaidInCapital`, `EntityCommonStockSharesOutstanding` |

Tag normalization is the hard part. Revenue alone can appear under several tags depending on issuer and year. The adapter must use explicit fallback order and record which tag was selected.

### What It Can Add To PEAD

SEC can add actual-fundamentals quality controls:

```text
revenue_yoy
eps_yoy
gross_margin_delta_yoy
operating_margin_delta_yoy
fcf_margin
accruals_to_assets
asset_growth
share_count_growth
```

For `PEAD_v1_quality_drift_60d`, a reasonable extension is:

```text
fundamental_quality_score =
    0.30 * z(revenue_yoy)
  + 0.20 * z(eps_yoy)
  + 0.20 * z(operating_margin_delta_yoy)
  + 0.15 * z(fcf_margin)
  - 0.15 * z(accruals_to_assets)
```

Then use it as a filter or small score term:

```text
selected =
    existing_PEAD_selection
and fundamental_quality_score >= rolling_sector_median
```

Do not use SEC actuals to construct analyst surprise. It has reported actuals but not consensus estimates.

### Timing And Point-In-Time Risk

The most important field is `filed`, not `end`.

- `end` is the fiscal period end.
- `filed` is when the filing was submitted to SEC.
- Earnings press releases can occur before the 10-Q/10-K filing.

For backtests:

1. If merging with Alpha Vantage earnings events, use Alpha Vantage `reported_date` for event timing and SEC facts only when `filed <= entry_date`.
2. If using SEC alone, conservatively set availability to the first trading day after `filed`.
3. Never use fiscal `end` as the market-availability date.

### Fit For This Project

Best use:

- free fundamentals augmentation;
- data auditability;
- long history;
- quality filters after earnings.

Bad use:

- replacing EPS surprise;
- exact earnings announcement timing;
- guidance or analyst revisions;
- clean cross-company factor without tag-mapping work.

Recommended implementation:

```text
alpha_lab/data_sources/sec_companyfacts.py
data/alpha_lab/fundamentals/raw/sec_companyfacts/
data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv
```

Keep it dependency-light with stdlib `urllib` plus `pandas`, matching the existing Alpha Vantage adapter style.

## SimFin

Official sources:

- SimFin data page: https://www.simfin.com/en/fundamental-data-download/
- SimFin Python API docs: https://simfin.readthedocs.io/en/stable/
- SimFin Python package: https://github.com/SimFin/simfin
- SimFin prices and plan limits: https://www.simfin.com/en/prices/

### Access

SimFin requires an API key. The Python package can download data, cache it locally, and load it into Pandas DataFrames. The public package README states that the free datasets contain less data than paid SimFin+ datasets and that some datasets require SimFin+.

Current plan limits shown on SimFin pricing:

| Plan | Fundamentals API history | Bulk CSV history | Web API rate |
| --- | ---: | ---: | ---: |
| Free | 7 years | 5 years delayed | 2/sec |
| Start | 10 years | 10 years | 5/sec |
| Basic | 15 years | 20+ years | 10/sec |
| Pro | 20+ years | 20+ years | 20/sec |

Important license point: SimFin's pricing page says downloaded data must be deleted after cancellation. This means we should not treat SimFin data as a permanently redistributable open dataset.

### Available Data

SimFin is useful because it normalizes financial statements into consistent tables:

```text
income statement / profit and loss
balance sheet
cash flow statement
derived ratios and indicators
share prices
shares outstanding
company metadata
```

The public material advertises about 5,000 US stocks, quarterly and annual statements, ratios, and long history depending on plan.

### What It Can Add To PEAD

SimFin can provide faster fundamentals feature engineering than raw SEC:

```text
revenue_yoy
gross_margin
operating_margin
net_margin
free_cash_flow
roic
roe
asset_turnover
share_count_growth
valuation ratios
```

For this strategy, the best role is quality gating:

```text
PEAD_quality_gate =
    revenue_yoy > 0
and operating_margin_delta_yoy >= 0
and fcf_margin >= 0
and share_count_growth <= 5%
```

That is economically cleaner than adding many noisy variables into the PEAD score. First use SimFin to reject low-quality beats; only later test it as a score component.

### Risks

- Not a direct EPS surprise source.
- Requires registration and API key.
- Free plan history may be too short for the 2020-2026 backtest if we need full coverage from 2020.
- Data is proprietary and tied to account/subscription terms.
- Adding the `simfin` package is an extra dependency; avoid doing that until we confirm the user's account/data access.

### Fit For This Project

Best use:

- quick normalized fundamentals prototype;
- quality filters and sanity checks;
- comparing SEC-derived features against normalized vendor data.

Bad use:

- open-source permanent data layer;
- replacing Alpha Vantage EPS surprise;
- production-grade backtest without reviewing data terms.

Recommended implementation, only after getting a SimFin API key:

```text
alpha_lab/data_sources/simfin_fundamentals.py
data/alpha_lab/fundamentals/raw/simfin/
data/alpha_lab/fundamentals/processed/simfin_quarterly.csv
```

Keep `simfin` dependency optional. If missing, the script should fail with a clear setup message instead of adding it to Qlib core requirements.

## Recommended Sequence

## Implementation Status

Implemented in this fork:

```text
alpha_lab/data_sources/sec_companyfacts.py
scripts/backfill_sec_companyfacts.py
tests/alpha_lab/test_sec_companyfacts.py
data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv
```

The current SEC backfill uses the expanded technology universe and writes one row per `(symbol, fiscal_year, fiscal_period)` when quarterly companyfacts can be normalized.

Current local coverage:

```text
requested_symbols = 51
processed_symbols = 49
processed_rows = 1932
missing_or_empty_symbols = ASML, TSM
rows_with_revenue_yoy = 1715
rows_with_operating_margin_delta_yoy = 1623
rows_with_fcf_margin = 575
```

`fcf_margin` coverage is intentionally lower. The parser rejects cash-flow facts whose XBRL duration is not approximately one quarter, because many SEC cash-flow disclosures are year-to-date rather than discrete quarter values. YTD-to-quarter differencing should be a separate, explicitly tested improvement.

Backfill command:

```powershell
$env:SEC_USER_AGENT = "<project/contact user agent>"
.\.venv\Scripts\python.exe scripts\backfill_sec_companyfacts.py --sleep 0.12 --output data\alpha_lab\fundamentals\processed\sec_companyfacts_quarterly.csv
```

For a small validation sample:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_sec_companyfacts.py --symbols AMD,NVDA --limit 2 --sleep 0.2 --output .tmp\sec_companyfacts_sample.csv
```

### Phase 1: SEC first

SEC is the better next step because it is official, free, and does not require adding a dependency. Build:

```text
scripts/backfill_sec_companyfacts.py
alpha_lab/data_sources/sec_companyfacts.py
```

Minimum output:

```text
data/alpha_lab/fundamentals/processed/sec_companyfacts_quarterly.csv
```

Minimum schema:

```text
symbol
cik
fiscal_period_end
filed_date
form
accn
revenue
net_income
diluted_eps
operating_income
gross_profit
operating_cash_flow
capex
assets
liabilities
equity
selected_tag_map_json
```

Then join into earnings features using:

```text
symbol match
fiscal_date_ending match when available
otherwise nearest prior filed_date <= entry_date
```

### Phase 2: SimFin as validation

Use SimFin only if we get a key and accept its terms. Build a separate optional adapter and compare:

```text
SEC revenue_yoy vs SimFin revenue_yoy
SEC operating_margin_delta vs SimFin operating_margin_delta
coverage overlap
missing symbols
revision differences
```

### Phase 3: Factor experiment

Create a PEAD variant with a small, testable change:

```text
PEAD_v2_actual_quality_60d
```

Do not create a new platform. Only add a fundamentals feature join and one variant:

```text
PEAD_v2_score =
    PEAD_v1_score
  + 0.10 * clipped_fundamental_quality_score
```

or, more conservatively:

```text
selected =
    PEAD_v1_selected
and fundamental_quality_score >= rolling_universe_median
```

The filter version should be tested first because the current data sample is still small.

## Final Decision

SEC companyfacts should be integrated next. It is the best free source for auditable actual fundamentals.

SimFin should be treated as optional validation and convenience data. It may save normalization time, but its free history and account terms make it less suitable as the core open research dataset.

Neither source solves the missing analyst consensus surprise problem. The current Alpha Vantage incremental cache remains necessary for EPS surprise until a better free consensus-estimate dataset is found.
