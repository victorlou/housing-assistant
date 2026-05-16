# Local isochrone compute

This directory holds the **r5py**-based routing script that computes NZ-wide transit travel-time matrices. It runs **outside Databricks** because r5py requires JDK 21 — see [`../README.md`](../README.md) for the architectural reasoning.

The script processes all four regions we ingest GTFS for (Auckland, Wellington, Waikato, Christchurch), clips its own OSM extracts, writes a per-region Parquet plus a combined `isochrone_all.parquet`, uploads that to our bronze volume, and refreshes `housing.gold.isochrone` — all from a single `python compute_isochrones.py` invocation.

## One-time setup

### 1. JDK 21 via SDKMAN

```bash
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"
sdk install java 21.0.5-tem    # answer N to "set as default" if you want
                               # Java 17 to remain your daily driver
```

Verify:

```bash
sdk use java 21.0.5-tem        # this shell only
java -version                  # → openjdk 21.x ... Temurin
```

### 2. Python virtual environment

From this directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify:

```bash
python -c "import r5py; print(r5py.__version__)"
```

### 3. osmium-tool

The script shells out to `osmium extract` to clip the NZ-wide OSM PBF into regional pieces (mandatory because R5 can't handle the antimeridian — the full NZ extract includes the Chatham Islands east of 180°). Install it once:

```bash
brew install osmium-tool
```

### 4. Databricks CLI profile

The script pulls each region's GTFS zip (from `dbfs:/Volumes/housing/bronze/gtfs_files/_zip/<feed>/`), queries the destination grid live from `housing.gold.transit_stop`, uploads the output Parquet to `dbfs:/Volumes/housing/bronze/osm_files/`, and refreshes `housing.gold.isochrone` — all via the same Databricks SDK + SQL connector flow we use elsewhere.

It uses the profile named in `DATABRICKS_PROFILE` (defaults to `hackathon`). If you've already been running `databricks --profile hackathon ...` from this machine, you're set. Otherwise: `databricks auth login --profile hackathon` once.

### 5. NZ OSM extract

Download `new-zealand-latest.osm.pbf` from Geofabrik (~378 MB) once. The script clips this into per-region PBFs on first run:

```bash
curl -L -o data/new-zealand-260515.osm.pbf \
  https://download.geofabrik.de/australia-oceania/new-zealand-latest.osm.pbf
```

Any filename matching `data/new-zealand-*.osm.pbf` is picked up. Re-download with a new date suffix when you want fresher road data — the script will notice and produce freshly-named regional clips, which forces r5py to rebuild its routing graph cache.

## Run

```bash
sdk use java 21.0.5-tem
source .venv/bin/activate

python compute_isochrones.py
```

That's the whole flow. The script iterates `REGIONS` in order, prints a banner per region, and skips past per-region failures (e.g. a missing GTFS feed) so partial runs are still useful. At the end it:

1. Concatenates everything into `isochrone_all.parquet`.
2. Uploads that file to `/Volumes/housing/bronze/osm_files/isochrone_all.parquet`.
3. Runs `CREATE OR REPLACE TABLE housing.gold.isochrone ... AS SELECT * FROM parquet.\`...\`` against the SQL warehouse.
4. Prints the resulting row count.

Expected timing on a recent MacBook (all four regions):

- OSM clipping: ~30 s per region (first run only, cached after).
- Graph build: 2–4 min per region (first run; cached via `.mapdb` files next to each PBF).
- Matrix compute: 30–90 s per region for ~5 origins × thousands of destinations.
- Upload + gold refresh: a few seconds total.

Sanity-check the printed per-feed summary: reachable pair counts should be in the thousands per region, min should be near zero (origin reaches its own cell), max should be close to 90.

## What the script does

For each region in `REGIONS`:

1. **OSM clip**: ensures a regional PBF exists at `data/<region_key>-*.osm.pbf` — if not, runs `osmium extract -b <clip_bbox> ...` against the NZ-wide source.
2. **GTFS fetch + clean**: pulls the latest GTFS zip for that feed from the bronze volume and strips header-only tables (e.g. AT's empty `fare_attributes.txt`) that R5 refuses to parse.
3. **Destinations**: queries every distinct H3 cell hosting a stop in `housing.gold.transit_stop` for that feed, then expands the set with a ring of H3 neighbours (`DESTINATION_RING = 1`, ~3–5× more cells after dedup) so residential cells next to transit are routable too.
4. **Routing**: builds a `TransportNetwork` (OSM walking + GTFS transit), then computes door-to-door travel time from each origin centre to every destination cell, with a 90-minute cap and a Wednesday 08:30 NZT departure.
5. **Bucket + tag**: rounds travel times to nearest 5 minutes (compresses well, matches the granularity Genie cares about) and tags rows with `mode`, `feed_source`, `departure_time`, `service_date`, `computed_at`, `computation_version`.
6. **Write**: `isochrone_<feed>.parquet` per region.

After the loop: concatenate, upload to the bronze volume, and `CREATE OR REPLACE TABLE housing.gold.isochrone` from that Parquet.

## Adding origins later

Edit the `origins` list inside the relevant region in `REGIONS` (in `compute_isochrones.py`). Each entry is `(id, display_name, lat, lon)`. Re-run the script.

## Adding regions later (Tauranga, Dunedin, etc.)

1. Add a new entry to `REGIONS` with `feed_source`, `display_name`, `region_key`, `clip_bbox`, `gtfs_volume`, and `origins`.
2. Make sure the corresponding GTFS feed is already landing in `dbfs:/Volumes/housing/bronze/gtfs_files/_zip/<feed>/`.
3. Re-run. The script clips the OSM, builds the graph, and the gold table picks up the new feed automatically (it's partitioned by `feed_source`).
