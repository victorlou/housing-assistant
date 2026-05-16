# prices

NZ residential property price + housing-market indicators. Powers any "how is the market trending" question from Genie, the agent, and the consumer view.

## What this pipeline currently delivers — and what it doesn't

**Source:** RBNZ M10 Housing statistical series — four quarterly indicators **at NZ-aggregate level only**:

| Column | RBNZ series | Unit | What it is |
|---|---|---|---|
| `hpi` | HPI.Q.H01T0.ia | Index | House Price Index, base ≈ 1000 at Q4 2003 |
| `sales_count` | QVB.Q.MR0H01.na | count | Property transactions settled in the quarter |
| `total_value_nzdm` | HHAL.QC1 | NZD millions | Total value of NZ housing stock (one-quarter lag) |
| `residential_investment_nzdm_real` | GDE.Q.EI24.RA | NZD millions, real | Residential investment, GDP component |

**Time depth:** quarterly from 1990-Q1 to present (~140 quarters).

**What's not here yet:** regional / TA / suburb-level breakdown. M10 publishes country-wide aggregates only. The gold table keeps `region` as a discriminator column so future regional sources drop in additively (every row today says `region = "New Zealand"`).

### Why no regional data

Free regional HPI in NZ is genuinely scarce:

| Source | Granularity | Cost | Format |
|---|---|---|---|
| RBNZ M10 (what's wired here) | National only | Free | XLSX |
| REINZ Monthly Property Report | Region for HPI, TA for median | Free | PDF |
| REINZ HPI Report / Statistics Platform | TA | Paid membership | XLSX/API |
| Trade Me Property Price Index | TA | Free | PDF press release |
| QV House Price Index | Region | Free | PDF |
| CoreLogic NZ | TA/suburb | Paid | API |

The free regional/TA sources are all PDFs (REINZ Monthly Property Report being the most useful). Adding a PDF parser is a future PR — see [Coming next](#coming-next).

## Contract — gold table

```sql
CREATE TABLE housing.gold.house_price__quarter__region (
  region                            STRING NOT NULL,   -- "New Zealand" today; "Auckland Region" etc. when regional sources land
  quarter                           DATE   NOT NULL,   -- first day of quarter (2024-01-01 = Q1 2024)
  quarter_label                     STRING NOT NULL,   -- "2024-Q1"
  hpi                               DOUBLE,            -- index value (~1000 at Q4 2003)
  hpi_yoy_pct                       DOUBLE,            -- year-on-year % change (4-quarter LAG, derived in gold)
  sales_count                       INT,               -- transactions settled this quarter
  total_value_nzdm                  DOUBLE,            -- total value of housing stock, NZD millions
  residential_investment_nzdm_real  DOUBLE,            -- GDP residential investment component, NZD millions (chain-volume)
  _updated_at                       TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (region);
```

Joins to `housing.gold.suburb` on `region`. For now, all suburbs join to the same `"New Zealand"` row — every suburb sees the national trend. When regional data lands, individual regions get their own rows.

## How it works

```
fetch_rbnz_hpi  →  transform_bronze  →  transform_silver  →  transform_gold
   (notebook)        (DLT pipeline)        (DLT pipeline)        (DLT pipeline)
```

### Task 1: `fetch_rbnz_hpi`

Reads the most recently-uploaded RBNZ M10 XLSX from `/Volumes/housing/bronze/prices_files/_xlsx/rbnz_hpi/`, parses the `Data` sheet with pandas (header in row 0, data from row 5, column 0 is end-of-quarter date), and writes a wide-format CSV alongside at `/Volumes/housing/bronze/prices_files/rbnz_hpi/<date>.csv` for Auto Loader to stream.

Hash-dedup against `housing.bronze.ingest_runs` (`source = 'prices_rbnz_hpi'`) — re-runs after a successful upload skip cleanly.

**Why "fetch" reads from a volume instead of downloading:** RBNZ's CDN is fronted by **Cloudflare Bot Management**. The XLSX endpoint responds 403 with `Cf-Mitigated: challenge` to any client that can't pass a JavaScript challenge + TLS-fingerprint check — that rules out every standard Python HTTP library, regardless of where it runs. Manual quarterly upload is the path of least resistance (RBNZ refreshes M10 quarterly, ~4 months in arrears).

### Tasks 2–4: bronze → silver → gold

- `bronze.py` defines `prices_rbnz_hpi_raw` — streaming Auto Loader over the CSV with provenance columns attached.
- `silver.py` types the columns and produces `housing.silver.house_price_index`.
- `gold.py` computes `hpi_yoy_pct` via a 4-quarter `LAG` window and materialises `housing.gold.house_price__quarter__region`.

## Identity model

- **Job runs as:** `sp-housing-jobs`.
- **Pipelines run as:** same SP. Tables owned by the SP, not the deployer.
- **Compute:** serverless for the fetch task and all three DLT pipelines.
- **Failure alerts:** email to the address configured in `databricks.yml`.

## Schedule

- **Cron:** 10th of every month, 04:00 Pacific/Auckland.
- Since fetch is volume-read (not URL), scheduled runs only do real work when a fresh XLSX has been uploaded — otherwise the hash-check skips. The cron is for "pick up a manual upload automatically on the next tick"; you can also trigger immediately with `databricks bundle run prices_ingest --target dev`.

## Refreshing the RBNZ XLSX

Once per quarter (RBNZ publishes HPI ~4 months after the reference quarter):

1. Open [rbnz.govt.nz/statistics/series/economic-indicators/housing](https://www.rbnz.govt.nz/statistics/series/economic-indicators/housing) in a browser and download **HM10 Housing**. The file is `hm10.xlsx`.
2. Upload it to the bronze volume with today's date as the filename:

   ```bash
   # First-time only: create the directory.
   databricks --profile hackathon fs mkdirs \
     dbfs:/Volumes/housing/bronze/prices_files/_xlsx/rbnz_hpi

   # Every quarter:
   today=$(date +%Y-%m-%d)
   databricks --profile hackathon fs cp \
     ~/Downloads/hm10.xlsx \
     "dbfs:/Volumes/housing/bronze/prices_files/_xlsx/rbnz_hpi/${today}.xlsx"
   ```

3. Trigger the bundle (or wait for the next monthly cron tick):

   ```bash
   cd pipelines/prices
   databricks bundle run prices_ingest --target dev
   ```

The `fetch_rbnz_hpi` task picks the most-recently-uploaded XLSX (by mtime), parses it, and writes a CSV alongside. Bronze/silver/gold cascade from there.

## Deploy

```bash
cd pipelines/prices
databricks bundle validate --target dev
databricks bundle deploy --target dev
```

## Verify

```sql
-- Latest fetch attempt
SELECT source, status, content_hash, file_count, bytes_written, notes, fetched_at
FROM housing.bronze.ingest_runs
WHERE source LIKE 'prices_%' ORDER BY fetched_at DESC LIMIT 5;

-- Most recent quarter's reading
SELECT *
FROM housing.gold.house_price__quarter__region
WHERE quarter = (SELECT MAX(quarter) FROM housing.gold.house_price__quarter__region);

-- Full HPI time series with YoY
SELECT quarter_label, hpi, hpi_yoy_pct
FROM housing.gold.house_price__quarter__region
WHERE region = 'New Zealand'
ORDER BY quarter DESC LIMIT 20;

-- Cooled vs hot quarters (largest YoY drops + rises)
SELECT quarter_label, hpi, hpi_yoy_pct
FROM housing.gold.house_price__quarter__region
WHERE region = 'New Zealand' AND hpi_yoy_pct IS NOT NULL
ORDER BY ABS(hpi_yoy_pct) DESC LIMIT 10;
```

## Known limitations

- **No regional breakdown.** Every row is `region = "New Zealand"`. Joins to `gold.suburb` resolve to the same national trend for every suburb. Documented above; resolved by future PRs.
- **Manual quarterly upload.** Cloudflare blocks automated download from any Python client; we accept the manual step at quarterly cadence. If/when we ingest weekly or daily price data, we'll need a different ingestion approach (GitHub Action with `curl_cffi`, headless browser, or paid API).

## Coming next

- **REINZ Monthly Property Report PDF parser** (regional HPI + TA median sale price). Same manual-upload pattern as today's RBNZ M10, but parses PDF instead of XLSX. Adds rows to `gold.house_price__quarter__region` for individual regions, and a new `gold.house_price__month__ta` for TA-level median prices.
- **Trade Me Property Price Index** as an alternative TA-level source (monthly press release, free).
- **Paid REINZ Statistics Platform** if we ever get a membership — straight TA-level HPI via XLSX/API, removes the PDF-parsing fragility.
