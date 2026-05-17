# amenity

NZ amenity points (supermarkets, schools, hospitals, pharmacies, GP clinics, early-childhood centres, parks, libraries) extracted from OpenStreetMap and landed in `housing.gold.amenity__day__h3`. Joinable to `housing.gold.suburb` via the H3-cell bridge so the agent can answer "suburbs near a supermarket / hospital / school".

## Why this directory uses the local-compute pattern

Same reason as `pipelines/isochrone/`: extraction relies on the `osmium` CLI tool (osmium-tool), which is installed by Homebrew on a contributor's laptop. We already use it for the isochrone OSM clip step, so a local OSM toolchain is a one-time setup the team has done.

The architecture is:

```
   (local machine)                                       (Databricks)
   ─────────────────                                     ───────────
   compute_amenities.py  ───── upload ─────▶ Volume      ── CREATE OR REPLACE ─▶  housing.gold.amenity__day__h3
   osmium tags-filter +                                                            (Genie, agent read here)
   osmium export →
   pandas + h3
```

Refresh cadence is quarterly-ish — OSM evolves continuously but housing-relevant amenities (supermarkets, schools, hospitals) don't churn much month to month. A contributor runs `python compute_amenities.py` whenever we want to refresh.

## Contract — gold table

```sql
CREATE TABLE housing.gold.amenity__day__h3 (
  osm_id        STRING NOT NULL,   -- "node/123456" or "way/789012" — stable OSM identifier
  amenity_type  STRING NOT NULL,   -- "supermarket", "hospital", "school",
                                   -- "early_childhood", "pharmacy", "gp_clinic",
                                   -- "park", "library"
  name          STRING,            -- OSM "name" tag — often null for parks / minor amenities
  lat           DOUBLE NOT NULL,   -- WGS84
  lon           DOUBLE NOT NULL,   -- WGS84
  h3_cell       BIGINT NOT NULL,   -- res-8 cell, joins to gold.h3_cell.h3_cell
  suburb_id     STRING,            -- denormalised from gold.h3_cell.suburb_id at materialisation
                                   -- (cells outside any SA2 — water, EEZ — keep this null)
  _updated_at   TIMESTAMP NOT NULL
)
USING DELTA PARTITIONED BY (amenity_type);
```

`suburb_id` is precomputed via `LEFT JOIN housing.gold.h3_cell` at CREATE OR REPLACE time so consumer queries don't have to do the join themselves.

## What gets extracted

| `amenity_type` | OSM tag patterns | Notes |
|---|---|---|
| `supermarket` | `shop=supermarket` OR `amenity=supermarket` | Both tags used in NZ (Countdown / New World as `shop`; some smaller stores as `amenity`) |
| `hospital` | `amenity=hospital` | Public + private |
| `school` | `amenity=school`, `amenity=college`, `amenity=university` | School locations (points), **not** enrolment zones — those are a separate MoE source for a future PR |
| `early_childhood` | `amenity=kindergarten`, `amenity=childcare` | Daycares + pre-schools |
| `pharmacy` | `amenity=pharmacy` | |
| `gp_clinic` | `amenity=clinic`, `amenity=doctors` | General practice, primary-care clinics |
| `park` | `leisure=park` | |
| `library` | `amenity=library` | |

OSM coverage in NZ is good for the major cities (Auckland, Wellington, Christchurch, Hamilton). Rural amenities can be incomplete.

## Sample agent queries this unlocks

```sql
-- Auckland suburbs with at least one supermarket
SELECT u.suburb_name, COUNT(*) AS supermarket_count
FROM housing.gold.suburb u
JOIN housing.gold.amenity__day__h3 a ON a.suburb_id = u.suburb_id
WHERE u.region = 'Auckland Region' AND a.amenity_type = 'supermarket'
GROUP BY u.suburb_name ORDER BY supermarket_count DESC LIMIT 20;

-- Suburbs reachable from Britomart in 45 min AND with both a supermarket and a school
WITH britomart AS (SELECT h3_longlatash3(174.76682, -36.84393, 8) AS h3_cell)
SELECT DISTINCT u.suburb_name
FROM housing.gold.suburb u
JOIN housing.gold.isochrone i ON i.destination_h3 IN (
       SELECT h3_cell FROM housing.gold.h3_cell WHERE suburb_id = u.suburb_id
    )
JOIN britomart b ON i.origin_h3 = b.h3_cell
WHERE i.travel_minutes <= 45
  AND EXISTS (SELECT 1 FROM housing.gold.amenity__day__h3 a
              WHERE a.suburb_id = u.suburb_id AND a.amenity_type = 'supermarket')
  AND EXISTS (SELECT 1 FROM housing.gold.amenity__day__h3 a
              WHERE a.suburb_id = u.suburb_id AND a.amenity_type = 'school');

-- Per-TA amenity density (parks per 10k population)
SELECT u.territorial_authority,
       SUM(u.population_2023) AS pop,
       COUNT(a.osm_id) AS parks,
       ROUND(10000.0 * COUNT(a.osm_id) / NULLIF(SUM(u.population_2023), 0), 2) AS parks_per_10k
FROM housing.gold.suburb u
LEFT JOIN housing.gold.amenity__day__h3 a
       ON a.suburb_id = u.suburb_id AND a.amenity_type = 'park'
GROUP BY u.territorial_authority
ORDER BY parks_per_10k DESC LIMIT 15;
```

## How to refresh

See [`local/README.md`](local/README.md). Roughly: ensure regional OSM PBFs are in `pipelines/isochrone/local/data/` (the isochrone setup already places them there), then `python compute_amenities.py`. The script reads from the same PBFs the isochrone compute uses, so no duplicate OSM downloads.

## What's still TODO

- **Dedup near-duplicate POIs.** OSM occasionally has the same supermarket as both a node (POI point) and a way (building polygon). `compute_amenities.py` includes both; future work could dedupe by `(name, h3_cell, amenity_type)` keeping the way (better positional accuracy).
- **More amenity types**: gyms (`leisure=fitness_centre`), petrol stations (`amenity=fuel`), banks (`amenity=bank`), train/bus stations (we have these from GTFS already). Add to `AMENITY_TAG_MAP` in `compute_amenities.py`.
- **Schools as zones, not points.** OSM has school *locations*; for "is my house zoned for Mt Albert Grammar" we need Ministry of Education enrolment-zone polygons — separate future pipeline.
