# isochrone

Computes door-to-door transit travel times across New Zealand cities and lands them in `housing.gold.isochrone`. The resulting table powers the agent's `compute_isochrone` tool ("can I get from X to Y in N minutes by public transport?") and any "commute-distance" filter in the consumer view.

## Why this directory looks different from `pipelines/gtfs/`

GTFS ingestion is a streaming pattern that fits Databricks Serverless cleanly. Isochrone computation isn't — it needs a routing engine (r5py + R5 + OSM road network) that requires JDK 21. Databricks Serverless ships an older JVM and won't let us install JDK 21 via init scripts (Serverless-only workspaces don't permit them).

So the compute happens locally on a contributor's laptop with JDK 21 + r5py installed. The same script also clips its OSM extracts via `osmium`, uploads the output Parquet to the bronze volume, and refreshes the gold table — so refreshing isochrones is one `python compute_isochrones.py` invocation. The architecture is:

```
   (local machine)                                       (Databricks)
   ─────────────────                                     ───────────
   compute_isochrones.py  ───── upload ─────▶ Volume     ── CREATE OR REPLACE ─▶  housing.gold.isochrone
   r5py + JDK 21                                                                   (Genie, agent read here)
   osmium + OSM + GTFS feeds
```

Refreshing is a manual quarterly-ish task. Fine because:

- OSM doesn't change much month-to-month.
- GTFS schedules update weekly, but a Wednesday 08:30 commute time doesn't shift meaningfully for the affordability question.
- The hot path (Genie, agent, dashboard) only reads the gold table — it doesn't care where compute happened.

## Layout

```
pipelines/isochrone/
├── README.md                 ← you are here
└── local/                    ← runs on a developer machine, not Databricks
    ├── README.md             ← setup + how to run
    ├── compute_isochrones.py ← the r5py script (clip + compute + upload + load)
    ├── requirements.txt
    ├── .gitignore
    └── data/                 ← user-supplied (gitignored)
        ├── new-zealand-*.osm.pbf   ← source extract from Geofabrik
        └── <region_key>-*.osm.pbf  ← per-region clips, produced on first run
```

## Schema (`housing.gold.isochrone`)

| Column | Type | Notes |
|---|---|---|
| `origin_h3` | BIGINT | H3 cell (resolution 8) of an origin. Drawn from the same cell set as `destination_h3` — any cell hosting a transit stop or adjacent to one. |
| `destination_h3` | BIGINT | H3 cell of a reachable destination. Same set as `origin_h3`. |
| `mode` | STRING | `transit`, `drive`, `walk`. Currently only `transit`. |
| `travel_minutes` | INT | Total trip time, bucketed to nearest 5. Self-reach rows report 0. |
| `feed_source` | STRING | Which GTFS feed produced this row (`auckland_transport`, ...). |
| `departure_time` | STRING | Assumed departure clock time (e.g. `08:30`). |
| `service_date` | DATE | Service date used. |
| `computed_at` | TIMESTAMP | When this row was produced. |
| `computation_version` | STRING | `r5py-v2` (symmetric matrix); `r5py-v1` was the older 22-hub run. Lets us version the algorithm + origin/destination set. |

Partitioned by `(mode, feed_source)`. Created on the first compute run via `CREATE OR REPLACE TABLE ... AS SELECT * FROM parquet.\`/Volumes/.../isochrone_all.parquet\``.

**Semantic.** The matrix is symmetric: `origin_h3` and `destination_h3` are drawn from the same set per region — every H3 res-8 cell hosting a transit stop in `housing.gold.transit_stop` plus a 1-ring expansion. That means the agent can answer "from this workplace lat/lon to anywhere in the region" for any workplace near transit (not only from a handful of named CBD hubs), via `WHERE origin_h3 = h3_longlatash3(<lon>, <lat>, 8)`.

## Refresh process

1. A contributor with JDK 21 + osmium + Python env follows [`local/README.md`](local/README.md) and runs `python compute_isochrones.py`.
2. The script clips OSM, computes per-region matrices, concatenates, uploads to `/Volumes/housing/bronze/osm_files/isochrone_all.parquet`, and refreshes `housing.gold.isochrone` via SQL warehouse.
3. The agent's `compute_isochrone` tool returns rows from there.

## Currently covered

Four metro regions, each with a fully symmetric cell-to-cell matrix: every H3 res-8 cell hosting a transit stop in that region (plus a 1-ring of neighbours) is an origin *and* a destination.

- **Auckland** (`auckland_transport`)
- **Wellington** (`metlink`)
- **Waikato / Hamilton** (`busit`)
- **Christchurch** (`metroinfo`)

All regions: H3 resolution 8, Wednesday 08:30 NZT departure, 90-min cap, 5-min travel-time buckets.

## Coming next

- Drive-time isochrones as a fallback for regions without GTFS (using a separate routing engine).
- Off-peak time slices (e.g. 22:00) to catch weekend / late-evening accessibility gaps.
