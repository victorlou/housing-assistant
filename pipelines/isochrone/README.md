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
| `origin_h3` | BIGINT | H3 cell (resolution 8) of an origin centre (e.g. Britomart). |
| `destination_h3` | BIGINT | H3 cell of a reachable destination. |
| `mode` | STRING | `transit`, `drive`, `walk`. Currently only `transit`. |
| `travel_minutes` | INT | Total trip time, bucketed to nearest 5. |
| `feed_source` | STRING | Which GTFS feed produced this row (`auckland_transport`, ...). |
| `departure_time` | STRING | Assumed departure clock time (e.g. `08:30`). |
| `service_date` | DATE | Service date used. |
| `computed_at` | TIMESTAMP | When this row was produced. |
| `computation_version` | STRING | `r5py-v1`, etc. Lets us version the algorithm. |

Partitioned by `(mode, feed_source)`. Created on the first compute run via `CREATE OR REPLACE TABLE ... AS SELECT * FROM parquet.\`/Volumes/.../isochrone_all.parquet\``.

## Refresh process

1. A contributor with JDK 21 + osmium + Python env follows [`local/README.md`](local/README.md) and runs `python compute_isochrones.py`.
2. The script clips OSM, computes per-region matrices, concatenates, uploads to `/Volumes/housing/bronze/osm_files/isochrone_all.parquet`, and refreshes `housing.gold.isochrone` via SQL warehouse.
3. The agent's `compute_isochrone` tool returns rows from there.

## Currently covered

- **Auckland** (`auckland_transport`): 7 origin centres.
- **Wellington** (`metlink`): 6 origin centres.
- **Waikato / Hamilton** (`busit`): 4 origin centres.
- **Christchurch** (`metroinfo`): 5 origin centres.

All regions: H3 resolution 8 destinations (stop cells + 1-ring neighbours), Wednesday 08:30 NZT departure, 90-min cap, 5-min travel-time buckets.

## Coming next

- Drive-time isochrones as a fallback for regions without GTFS (using a separate routing engine).
- Off-peak time slices (e.g. 22:00) to catch weekend / late-evening accessibility gaps.
