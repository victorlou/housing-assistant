# Local amenity extraction

Pulls amenity POIs (supermarkets, schools, hospitals, etc.) out of the regional OSM PBFs and lands them in `housing.gold.amenity__h3`. Runs **outside Databricks** for the same reason as the isochrone compute: needs the `osmium` CLI tool, which is a one-shot Homebrew install.

This script intentionally **reuses the PBFs that the isochrone pipeline already downloaded** (`pipelines/isochrone/local/data/<region>-*.osm.pbf`). If you've run the isochrone compute on this machine, you're already 90% set up.

## One-time setup

### 1. osmium-tool

If you ran the isochrone compute, you already have it. Otherwise:

```bash
brew install osmium-tool
```

### 2. Python virtual environment

From this directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Databricks CLI profile

Uses the `hackathon` profile via the Databricks SDK. If you've run any other CLI command on this machine (`databricks --profile hackathon ...`), you're set. Otherwise: `databricks auth login --profile hackathon` once.

### 4. Regional OSM PBFs in place

The script reads PBFs from `../../isochrone/local/data/`. Specifically:

- `auckland-*.osm.pbf`
- `wellington-*.osm.pbf`
- `waikato-*.osm.pbf`
- `christchurch-*.osm.pbf`

These are the regional clips the isochrone compute produces via osmium-extract. If you haven't run the isochrone compute yet, follow [`../../isochrone/local/README.md`](../../isochrone/local/README.md) first — it'll download the NZ-wide extract and clip the four regions.

## Run

```bash
source .venv/bin/activate
python compute_amenities.py
```

What it does in order:

1. For each regional PBF — runs `osmium tags-filter` to strip down to just amenity-tagged features, then `osmium export -f geojson` to convert.
2. Parses the GeoJSON in Python, categorises into 8 amenity types, computes a centroid for ways/relations, and an H3 res-8 cell from (lat, lon).
3. Concatenates all regions into a single parquet (`amenity_all.parquet`).
4. Uploads the parquet to `/Volumes/housing/bronze/amenities_files/amenity_all.parquet`.
5. `CREATE OR REPLACE TABLE housing.gold.amenity__h3` materialises gold with `suburb_id` denormalised in via a LEFT JOIN against `housing.gold.h3_cell`.

Expected timing on a recent MacBook:

- `osmium tags-filter` + `export` per region: a few seconds each.
- Python parse + H3 compute: a few seconds.
- Total runtime: ~30 seconds. Tiny compared to the isochrone routing compute.

Expected output volume: 2-5k amenities total across the four metros, depending on OSM coverage. Per-type breakdown is printed at the end.

## Verify

After the run, in SQL:

```sql
-- Headline shape
SELECT amenity_type, COUNT(*) AS count
FROM housing.gold.amenity__h3
GROUP BY amenity_type
ORDER BY count DESC;
-- Expect roughly: school (most numerous), supermarket, park, gp_clinic,
-- pharmacy, early_childhood, library, hospital.

-- Coverage by region (via the suburb join)
SELECT u.region, a.amenity_type, COUNT(*) AS count
FROM housing.gold.amenity__h3 a
JOIN housing.gold.suburb u ON u.suburb_id = a.suburb_id
GROUP BY u.region, a.amenity_type
ORDER BY u.region, count DESC;

-- Auckland suburbs ranked by supermarket count
SELECT u.suburb_name, COUNT(*) AS supermarkets
FROM housing.gold.suburb u
JOIN housing.gold.amenity__h3 a ON a.suburb_id = u.suburb_id
WHERE u.region = 'Auckland Region' AND a.amenity_type = 'supermarket'
GROUP BY u.suburb_name ORDER BY supermarkets DESC LIMIT 15;
```

## Adding more amenity types

Edit two places in `compute_amenities.py`:

1. **`OSMIUM_FILTERS`** — add an `nwr/<tag>=<value>,<value>,...` line so osmium includes the new tags in its output.
2. **`AMENITY_TAG_MAP`** — add a `(key, value): "category_name"` entry so the categoriser knows what to call the new type.

Re-run; new type appears in gold automatically (the table is partitioned by `amenity_type` so adding a value is non-breaking).

## Adding more regions

Add a new entry to `REGIONS` with `key`, `display`, and `pbf_glob`. Ensure the corresponding PBF lives at `../../isochrone/local/data/<key>-*.osm.pbf` (or update `OSM_DATA_DIR` if you want a different layout).
