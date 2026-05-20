# Map Feature Layers — Implementation Plan

> **Purpose:** Planning doc for the "show all features on the map" feature. This adds a layer-toggle panel and choropleth colouring to Map Mode so users — and the agent — can overlay any data layer from `housing.gold` on the map at will, independent of the agent's cumulative filter flow.
>
> **Status:** Not started. Depends on Map Mode base implementation being complete first (map-mode-plan.md).
>
> **Confirmed gold schema tables** (verified against Databricks workspace `dbc-c3095737-46ec`, housing-assistant-dev warehouse `f21913d784edd9ad`, 2026-05-20):
> `suburb`, `suburb__year`, `amenity__h3`, `transit_stop`, `transit_route`, `isochrone`, `hazard`, `h3_cell`, `nz_address`, `ta__month`, `ta__quarter`, `region__quarter`

---

## Table of Contents

1. [What We're Building](#1-what-were-building)
2. [Full Layer Inventory](#2-full-layer-inventory)
3. [Current Codebase Baseline](#3-current-codebase-baseline)
4. [State Management — MapContext Extensions](#4-state-management--mapcontext-extensions)
5. [render_map Tool Extension](#5-render_map-tool-extension)
6. [Backend API Changes](#6-backend-api-changes)
7. [Frontend Layer Components](#7-frontend-layer-components)
8. [LayerControlPanel Component](#8-layercontrolpanel-component)
9. [MapLegend Component](#9-maplegend-component)
10. [MapPanel Wiring](#10-mappanel-wiring)
11. [message.tsx — Feature Layer Dispatch](#11-messagetsx--feature-layer-dispatch)
12. [Performance & Rendering Notes](#12-performance--rendering-notes)
13. [Known Issues with Existing Backend Routes](#13-known-issues-with-existing-backend-routes)
14. [Phased Delivery](#14-phased-delivery)
15. [Full SQL Reference](#15-full-sql-reference)
16. [File Changelist](#16-file-changelist)

---

## 1. What We're Building

A **layer control panel** — a collapsible floating panel on the map letting the user toggle any data layer from `housing.gold` on and off, plus choropleth suburb colouring by any census or price metric. Layers are additive and work independently from the agent's cumulative suburb filter.

The agent can also activate layers programmatically via the `render_map` tool (e.g., "I've turned on the flood risk layer for you"). The frontend keeps both paths in sync.

### UI Sketch

```
╔═══════════════════════════════════╗
║  MAP                    [Layers▾] ║  ← Layers button top-right, badge shows active count
║                                   ║
║                                   ║
║                                   ║
║              [filter legend]      ║
╚═══════════════════════════════════╝

Layers panel (open):
┌─────────────────────────────────────────┐
│  ⟨ LAYERS                    (3 active) │
│  ─────────────────────────────────────  │
│  CHOROPLETH (suburb fill)               │
│  ○ None                                 │
│  ● Median rent              ✓  active   │
│  ○ Household income                     │
│  ○ Crime rate                           │
│  ○ Crowding rate                        │
│  ○ Owner-occupier %                     │
│  ○ Population density                   │
│  ○ Median age                           │
│  ○ Damp/mould housing                   │
│  ○ House price index                    │
│  ○ Median sale price                    │
│  ○ Rent affordability index             │
│  ─────────────────────────────────────  │
│  AMENITIES (points)                     │
│  ● Schools              ✓               │
│  ● Supermarkets         ✓               │
│  ○ GP clinics                           │
│  ○ Parks                                │
│  ○ Pharmacies                           │
│  ○ Hospitals                            │
│  ○ Libraries                            │
│  ○ ECE / Early childhood                │
│  ─────────────────────────────────────  │
│  TRANSIT (points)                       │
│  ○ All stops                            │
│  ─────────────────────────────────────  │
│  FLOOD HAZARD (H3 cells)                │
│  ○ Flood plains                         │
│  ○ Flood-prone areas                    │
│  ○ Flood-sensitive areas                │
│  ○ Coastal inundation 1% AEP            │
│  ○ Coastal inundation 100yr             │
│  ○ Regional flood zones                 │
└─────────────────────────────────────────┘
```

---

## 2. Full Layer Inventory

All sourced from `housing.gold` (confirmed 2026-05-20).

### 2.1 Choropleth Layers — Suburb Polygon Fill

Colour suburb polygon fill (or circle marker fill, since current `SuburbLayer` uses `CircleMarker`) by a continuous metric. **One active at a time** (radio, not checkbox). The choropleth overrides the agent's `status`-based green/grey colouring when active — the suburb ring/weight still shows filter pass/fail, but the fill colour becomes the metric.

| Layer ID | Label | Source table(s) | SQL expression | Unit | Colour scheme |
|---|---|---|---|---|---|
| `income` | Median household income | `suburb__year` | `median_household_income` | NZD/yr | Sequential blue (low→high) |
| `rent` | Median weekly rent | `suburb__year` | `median_weekly_rent` | NZD/wk | Sequential yellow→red |
| `owner_occ` | Owner-occupier rate | `suburb__year` | `owner_occupier_pct * 100` | % | Diverging blue↔orange |
| `crowding` | Crowding rate | `suburb__year` | `percent_crowded * 100` | % | Sequential white→red |
| `crime` | Crime rate (per 1k) | `suburb__year` | `total_victimisations_2023 * 1000.0 / NULLIF(population_total, 0)` | per 1k pop | Sequential white→red |
| `age` | Median age | `suburb__year` | `median_age` | years | Sequential grey→purple |
| `damp` | Damp/mould housing | `suburb__year` | `(dwellings_always_damp + dwellings_sometimes_damp) * 100.0 / NULLIF(households_total, 0)` | % | Sequential white→red |
| `pop_density` | Population density | `suburb` | `population_2023 / NULLIF(land_area_km2, 0)` | people/km² | Sequential white→blue |
| `hpi` | House Price Index | `ta__month` JOIN `suburb` via `territorial_authority` | `current_hpi` (latest snapshot per TA) | index | Sequential blue→red |
| `median_price` | Median sale price | `ta__month` JOIN `suburb` | `current_annual_median_sales_nzd` (latest per TA) | NZD | Sequential blue→red |
| `rent_affordability` | Rent affordability index | `ta__quarter` JOIN `suburb` | `rent_affordability_index` (latest per TA) | index | Sequential green→red (affordable→stressed) |

**Data shape returned by API:** `{ suburb_id: string, value: number | null }[]` — ~2,379 rows per metric.

**Null suburbs:** Render as grey (`#d1d5db`) — typically offshore/harbour SA2s with no population.

**Quantile buckets for legend:** Compute 5 quantile boundaries on the frontend using the fetched value array. Display as a horizontal gradient bar with 5 labelled tick marks.

### 2.2 Amenity Point Layers

From `housing.gold.amenity__h3`. All 8 OSM categories, independently togglable checkboxes.

| Layer ID | `amenity_type` value | Label | Row count | Lucide icon | Colour |
|---|---|---|---|---|---|
| `amenity_school` | `school` | Schools | ~2,463 | `GraduationCap` | `#3b82f6` (blue-500) |
| `amenity_ece` | `early_childhood` | ECE centres | ~2,045 | `Baby` | `#60a5fa` (blue-400) |
| `amenity_gp` | `gp_clinic` | GP clinics | ~890 | `Stethoscope` | `#ef4444` (red-500) |
| `amenity_supermarket` | `supermarket` | Supermarkets | ~746 | `ShoppingCart` | `#22c55e` (green-500) |
| `amenity_pharmacy` | `pharmacy` | Pharmacies | ~506 | `Pill` | `#f97316` (orange-500) |
| `amenity_hospital` | `hospital` | Hospitals | ~238 | `Hospital` | `#dc2626` (red-600, larger marker) |
| `amenity_library` | `library` | Libraries | ~324 | `BookOpen` | `#8b5cf6` (violet-500) |
| `amenity_park` | `park` | Parks | ~11,619 | `Trees` | `#16a34a` (green-600) |

**Parks zoom-gate:** Only render at zoom ≥ 12. At lower zoom, parks are too numerous to be meaningful and tank canvas performance. Add a UI note "Parks visible at zoom ≥ 12" when parks is checked and zoom < 12.

**Clustering:** Use `react-leaflet-cluster` (already installed as a dependency). Cluster radius 60px at zoom < 13, expand to individual markers at zoom ≥ 13.

**Click popup:** Name, amenity_type, suburb_locality (from suburb_id lookup not needed — name and type are enough).

### 2.3 Transit Stop Layer

From `housing.gold.transit_stop`. Single toggle ("All stops"), with optional per-feed sub-filter. ~13,239 stops across 4 feeds.

| Feed | Label | Count | Default icon |
|---|---|---|---|
| `auckland_transport` | Auckland | ~6,455 | Bus/Train/Ferry (inferred) |
| `metlink` | Wellington | ~3,148 | Bus |
| `metroinfo` | Christchurch | ~2,064 | Bus |
| `busit` | Hamilton | ~1,572 | Bus |

**Route type inference:** `transit_stop` and `transit_route` share `feed_source` but there is no stop→route join key in the gold schema (stop_times are not materialised). Infer route type from stop name patterns:

```sql
CASE
  WHEN stop_name ILIKE '%train%' OR stop_name ILIKE '% station%' THEN 'rail'
  WHEN stop_name ILIKE '%ferry%' OR stop_name ILIKE '%wharf%' THEN 'ferry'
  ELSE 'bus'
END AS route_type
```

Icons: `Train` (Lucide) for rail, `Anchor` for ferry, `Bus` for bus. Colours: rail=`#f97316`, ferry=`#06b6d4`, bus=`#6366f1`.

**Clustering:** Use `react-leaflet-cluster`. Cluster radius 80px at zoom < 12, individual markers at zoom ≥ 12.

**Click popup:** stop_name, feed_source, inferred route type.

### 2.4 Flood Hazard H3 Cell Layers

From `housing.gold.hazard`. One row per H3 res-8 cell. Six boolean columns, each independently toggleable.

| Layer ID | Column | Label | Fill colour | Notes |
|---|---|---|---|---|
| `hazard_flood_plain` | `in_flood_plain` | Flood plains | `rgba(59, 130, 246, 0.4)` | Modelled 1% AEP river flood / floodplain |
| `hazard_flood_prone` | `in_flood_prone_area` | Flood-prone areas | `rgba(99, 102, 241, 0.4)` | Catchment-level flood-prone (Auckland-specific) |
| `hazard_flood_sensitive` | `in_flood_sensitive_area` | Flood-sensitive areas | `rgba(139, 92, 246, 0.35)` | Planning overlay |
| `hazard_coastal_1pct` | `in_coastal_inundation_1_aep` | Coastal inundation 1% AEP | `rgba(239, 68, 68, 0.45)` | Highest coastal risk |
| `hazard_coastal_100yr` | `in_coastal_inundation_100yr` | Coastal inundation 100yr | `rgba(249, 115, 22, 0.45)` | Common planning threshold |
| `hazard_regional` | `in_regional_flood_zone` | Regional flood zones | `rgba(234, 179, 8, 0.4)` | Other regional council layers |

**H3 res-8 cell area:** ~0.74 km². At zoom < 10, individual cells are sub-pixel — fallback to suburb-level hazard choropleth below zoom 10 (see Section 7.4).

**Rendering:** Convert H3 bigint → hex string → GeoJSON polygon using `cellToBoundary` from `h3-js` (same pattern as `isochrone-layer.tsx`). Return H3 hex IDs from API, compute boundaries client-side.

**Query shape returned by API:** `{ h3_hex: string }[]` filtered to cells matching the requested flags.

### 2.5 Isochrone Layer (already exists, documented for completeness)

From `housing.gold.isochrone`. Rendered by existing `IsochroneLayer` component. Not a user-togglable feature layer — agent-driven only, via `render_map`'s `isochrone_suburb` parameter. Documented here so the layer panel can show it as a read-only "active" indicator when an isochrone is loaded.

---

## 3. Current Codebase Baseline

This section documents what already exists as of 2026-05-20 so the feature implementation can be written as clean diffs.

### 3.1 Files Already Implemented

```
client/src/
├── contexts/MapContext.tsx             ← EXISTS. MapState, MapAction, MapProvider
├── components/map-panel.tsx            ← EXISTS. MapContainer + layers
├── components/suburb-layer.tsx         ← EXISTS. CircleMarker pins
├── components/isochrone-layer.tsx      ← EXISTS. H3 GeoJSON via cellToBoundary
├── components/fly-to-controller.tsx    ← EXISTS. flyToBounds / flyTo imperative
├── components/suburb-info-panel.tsx    ← EXISTS. Suburb profile card
├── components/map-chat.tsx             ← EXISTS. Map+chat split layout
├── components/elements/message.tsx     ← EXISTS. render_map interception at line 271

server/src/
├── routes/map-data.ts                  ← EXISTS. /api/map/centroids, /isochrone, /suburb

agent_server/tools/
├── render_map.py                       ← EXISTS. Simple passthrough tool
```

### 3.2 Current MapContext Schema

```typescript
// client/src/contexts/MapContext.tsx — CURRENT STATE

export type SuburbStatus = 'active' | 'dimmed' | 'highlighted';

export interface SuburbEntry {
  name: string;
  status: SuburbStatus;
  lat?: number;
  lng?: number;
}

export interface IsochroneState {
  suburb: string;
  minutes: number;
  mode: 'transit' | 'walking' | 'driving';
}

export interface MapState {
  suburbs: SuburbEntry[];
  isochrone: IsochroneState | null;
  filterSummary: string;
  zoomToSuburb: string | null;
  // ← NEW: featureLayers will be added here (Section 4)
}

export type MapAction =
  | { type: 'RENDER_MAP'; suburbs: SuburbEntry[]; isochrone: IsochroneState | null; filterSummary: string; }
  | { type: 'ZOOM_TO_SUBURB'; name: string }
  | { type: 'CLEAR_ZOOM' }
  | { type: 'RESET' };
  // ← NEW: TOGGLE_FEATURE_LAYER, SET_CHOROPLETH will be added (Section 4)
```

### 3.3 Current render_map Tool Signature

```python
# agent_server/tools/render_map.py — CURRENT STATE
@tool
def render_map(
    suburbs: list[dict],              # [{name: str, status: 'active'|'dimmed'|'highlighted'}]
    isochrone_suburb: Optional[str],
    isochrone_minutes: Optional[int],
    isochrone_mode: Optional[str],
    filter_summary: str,
) -> dict:
    return {"rendered": True}
    # ← NEW: feature_layers parameter will be added (Section 5)
```

### 3.4 Current message.tsx Intercept (render_map block, line 271)

```typescript
// Existing interception pattern in message.tsx
if (toolName === 'render_map') {
  if (mapDispatch && (state === 'input-available' || state === 'output-available')) {
    const mapInput = input as {
      suburbs: SuburbEntry[];
      isochrone_suburb: string | null;
      isochrone_minutes: number | null;
      isochrone_mode: string | null;
      filter_summary: string;
      // ← NEW: feature_layers field will be read here (Section 11)
    };
    mapDispatch({
      type: 'RENDER_MAP',
      suburbs: mapInput.suburbs ?? [],
      isochrone,
      filterSummary: mapInput.filter_summary ?? '',
    });
  }
  return null;
}
```

### 3.5 Current Backend runSql Helper

```typescript
// server/src/routes/map-data.ts — existing helper
async function runSql(statement: string): Promise<unknown[][]> {
  // Uses DATABRICKS_WAREHOUSE_ID env var
  // Uses getDatabricksToken() from @chat-template/auth
  // Uses getWorkspaceHostname() from @chat-template/ai-sdk-providers
  // Returns data_array from /api/2.0/sql/statements
}
```

All new routes in Section 6 use this same `runSql` helper. No new helper needed.

### 3.6 Installed Dependencies

All required packages are already in `client/package.json` — no new npm installs needed for Phase 1–4:

| Package | Version | Purpose |
|---|---|---|
| `react-leaflet` | ^4.2.1 | Map rendering |
| `leaflet` | ^1.9.4 | Underlying map library |
| `react-leaflet-cluster` | ^2.1.0 | Point clustering (amenity + transit) |
| `h3-js` | ^4.4.0 | H3 cell → GeoJSON conversion |
| `swr` | ^2.2.5 | Data fetching with caching |
| `lucide-react` | ^0.446.0 | Icons |
| `@radix-ui/react-collapsible` | ^1.1.12 | Accordion for layer panel |

---

## 4. State Management — MapContext Extensions

### 4.1 New Types

Add these types to `client/src/contexts/MapContext.tsx`:

```typescript
// New type aliases
export type ChoroplethMetric =
  | 'income' | 'rent' | 'owner_occ' | 'crowding' | 'crime'
  | 'age' | 'damp' | 'pop_density' | 'hpi' | 'median_price'
  | 'rent_affordability';

export type AmenityLayerId =
  | 'amenity_school' | 'amenity_ece' | 'amenity_gp' | 'amenity_supermarket'
  | 'amenity_pharmacy' | 'amenity_hospital' | 'amenity_library' | 'amenity_park';

export type HazardLayerId =
  | 'hazard_flood_plain' | 'hazard_flood_prone' | 'hazard_flood_sensitive'
  | 'hazard_coastal_1pct' | 'hazard_coastal_100yr' | 'hazard_regional';

export type FeatureLayerId = AmenityLayerId | HazardLayerId | 'transit_stops';

export interface FeatureLayerState {
  choropleth: ChoroplethMetric | null;    // one at a time (radio)
  active: Set<FeatureLayerId>;            // amenity + transit + hazard (checkboxes)
}
```

### 4.2 MapState Extension

```typescript
export interface MapState {
  suburbs: SuburbEntry[];
  isochrone: IsochroneState | null;
  filterSummary: string;
  zoomToSuburb: string | null;
  featureLayers: FeatureLayerState;       // NEW
}

export const initialMapState: MapState = {
  suburbs: [],
  isochrone: null,
  filterSummary: '',
  zoomToSuburb: null,
  featureLayers: {                        // NEW
    choropleth: null,
    active: new Set(),
  },
};
```

### 4.3 New Actions

```typescript
export type MapAction =
  | { type: 'RENDER_MAP'; suburbs: SuburbEntry[]; isochrone: IsochroneState | null; filterSummary: string; featureLayers?: Partial<FeatureLayerState> }
  | { type: 'ZOOM_TO_SUBURB'; name: string }
  | { type: 'CLEAR_ZOOM' }
  | { type: 'RESET' }
  | { type: 'SET_CHOROPLETH'; metric: ChoroplethMetric | null }        // NEW
  | { type: 'TOGGLE_FEATURE_LAYER'; layerId: FeatureLayerId }          // NEW
  | { type: 'SET_FEATURE_LAYERS'; featureLayers: FeatureLayerState };  // NEW (agent-driven bulk update)
```

### 4.4 Reducer Cases

```typescript
case 'SET_CHOROPLETH':
  return {
    ...state,
    featureLayers: { ...state.featureLayers, choropleth: action.metric },
  };

case 'TOGGLE_FEATURE_LAYER': {
  const next = new Set(state.featureLayers.active);
  if (next.has(action.layerId)) {
    next.delete(action.layerId);
  } else {
    next.add(action.layerId);
  }
  return { ...state, featureLayers: { ...state.featureLayers, active: next } };
}

case 'SET_FEATURE_LAYERS':
  return { ...state, featureLayers: action.featureLayers };

case 'RENDER_MAP': {
  const highlighted = action.suburbs.find((s) => s.status === 'highlighted');
  const nextFeatureLayers = action.featureLayers
    ? {
        choropleth: action.featureLayers.choropleth ?? state.featureLayers.choropleth,
        active: action.featureLayers.active ?? state.featureLayers.active,
      }
    : state.featureLayers;
  return {
    ...state,
    suburbs: action.suburbs,
    isochrone: action.isochrone,
    filterSummary: action.filterSummary,
    zoomToSuburb: highlighted ? highlighted.name : null,
    featureLayers: nextFeatureLayers,
  };
}
```

**Note:** `Set` is not serialisable in React DevTools — consider using `string[]` and converting to `Set` inside components for devtools friendliness, but `Set` is fine for runtime.

---

## 5. render_map Tool Extension

### 5.1 Python Tool Signature

```python
# agent_server/tools/render_map.py — NEW VERSION

from typing import Optional
from langchain_core.tools import tool


VALID_AMENITY_TYPES = {
    'amenity_school', 'amenity_ece', 'amenity_gp', 'amenity_supermarket',
    'amenity_pharmacy', 'amenity_hospital', 'amenity_library', 'amenity_park',
}

VALID_HAZARD_LAYERS = {
    'hazard_flood_plain', 'hazard_flood_prone', 'hazard_flood_sensitive',
    'hazard_coastal_1pct', 'hazard_coastal_100yr', 'hazard_regional',
}

VALID_CHOROPLETH = {
    'income', 'rent', 'owner_occ', 'crowding', 'crime',
    'age', 'damp', 'pop_density', 'hpi', 'median_price', 'rent_affordability',
}


@tool
def render_map(
    suburbs: list[dict],
    isochrone_suburb: Optional[str],
    isochrone_minutes: Optional[int],
    isochrone_mode: Optional[str],
    filter_summary: str,
    choropleth: Optional[str] = None,
    feature_layers_add: Optional[list[str]] = None,
    feature_layers_remove: Optional[list[str]] = None,
) -> dict:
    """
    Update the frontend map with the current filter state and optional feature layers.
    Call this after every filtering step (commute, rent, hazard) and whenever the user
    asks to focus on a specific suburb or toggle a data layer.

    Args:
        suburbs: List of {name: str, status: "active"|"dimmed"|"highlighted"} dicts.
            active = passes all filters (green pin)
            dimmed = eliminated by a filter (grey, still visible)
            highlighted = single suburb the user wants to zoom into (teal ring)
        isochrone_suburb: The commute-origin suburb name, or null if no commute filter.
        isochrone_minutes: Integer travel time cap, or null.
        isochrone_mode: "transit" | "walking" | "driving" | null
        filter_summary: 1-2 sentence plain-English summary of active filters shown as
            the map legend. E.g. "Within 30 min transit of Auckland CBD · Rent ≤ $700/wk"
        choropleth: Choropleth metric to colour suburb fills by, or null to clear.
            Valid values: income, rent, owner_occ, crowding, crime, age, damp,
            pop_density, hpi, median_price, rent_affordability
        feature_layers_add: Feature layer IDs to turn ON. Valid values:
            Amenities: amenity_school, amenity_ece, amenity_gp, amenity_supermarket,
                       amenity_pharmacy, amenity_hospital, amenity_library, amenity_park
            Transit:   transit_stops
            Hazard:    hazard_flood_plain, hazard_flood_prone, hazard_flood_sensitive,
                       hazard_coastal_1pct, hazard_coastal_100yr, hazard_regional
        feature_layers_remove: Feature layer IDs to turn OFF.

    Returns:
        {"rendered": True} — the frontend intercepts the tool INPUT before this runs.
    """
    return {"rendered": True}
```

### 5.2 When the Agent Should Use feature_layers_add

Add these examples to the Map Mode system prompt (`MAP_SYSTEM_PROMPT` in `agent_server/prompts.py`):

```
**Activating feature layers via render_map:**

When the user mentions flood risk, hazard, or coastal safety:
→ add feature_layers_add=["hazard_flood_plain", "hazard_coastal_100yr"]

When the user mentions schools, GP, or healthcare:
→ add feature_layers_add=["amenity_school", "amenity_gp"]

When the user mentions transit, buses, or train access:
→ add feature_layers_add=["transit_stops"]

When the user mentions rent trends or affordability:
→ add choropleth="rent" or choropleth="rent_affordability"

When the user mentions crime:
→ add choropleth="crime"

Always pass feature_layers_add/remove as additions to current state — do NOT set
feature_layers_remove unless the user explicitly says to turn something off.
```

---

## 6. Backend API Changes

All routes go into the **existing** `server/src/routes/map-data.ts`. The `runSql` helper and `CATALOG`/`SCHEMA`/`WAREHOUSE_ID` constants are already there — new routes just add more handlers to the existing `mapDataRouter`.

### 6.1 In-memory Cache Pattern (extend existing)

```typescript
// Add these alongside the existing centroidsCache at top of map-data.ts

interface ChoroplethRow { suburb_id: string; value: number | null; }
interface AmenityRow { osm_id: string; amenity_type: string; name: string | null; lat: number; lon: number; }
interface TransitStopRow { stop_id: string; stop_name: string; lat: number; lon: number; feed_source: string; route_type: string; }

const choroplethCache = new Map<string, { data: ChoroplethRow[]; ts: number }>();
const amenityCache = new Map<string, { data: AmenityRow[]; ts: number }>();
let transitCache: { data: TransitStopRow[]; ts: number } | null = null;

const CHOROPLETH_TTL = 4 * 60 * 60 * 1000; // 4 hours — census data doesn't change
const AMENITY_TTL = 60 * 60 * 1000;         // 1 hour
const TRANSIT_TTL = 5 * 60 * 1000;          // 5 min — GTFS feed could refresh
```

### 6.2 `GET /api/map/choropleth/:metric`

Returns `{ suburb_id, value }[]` for all residential suburbs. Frontend joins to suburb centroid by name.

```typescript
mapDataRouter.get('/choropleth/:metric', requireAuth, async (req: Request, res: Response) => {
  const { metric } = req.params;

  const METRIC_SQL: Record<string, string> = {
    income: `
      SELECT suburb_id, median_household_income AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023 AND median_household_income IS NOT NULL`,

    rent: `
      SELECT suburb_id, median_weekly_rent AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023 AND median_weekly_rent IS NOT NULL`,

    owner_occ: `
      SELECT suburb_id, ROUND(owner_occupier_pct * 100, 1) AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023 AND owner_occupier_pct IS NOT NULL`,

    crowding: `
      SELECT suburb_id, ROUND(percent_crowded * 100, 1) AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023 AND percent_crowded IS NOT NULL`,

    crime: `
      SELECT suburb_id,
        ROUND(total_victimisations_2023 * 1000.0 / NULLIF(population_total, 0), 1) AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023
        AND total_victimisations_2023 IS NOT NULL
        AND population_total > 100`,

    age: `
      SELECT suburb_id, median_age AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023 AND median_age IS NOT NULL`,

    damp: `
      SELECT suburb_id,
        ROUND((dwellings_always_damp + dwellings_sometimes_damp) * 100.0
          / NULLIF(households_total, 0), 1) AS value
      FROM ${CATALOG}.${SCHEMA}.suburb__year
      WHERE census_year = 2023
        AND dwellings_always_damp IS NOT NULL
        AND households_total > 0`,

    pop_density: `
      SELECT suburb_id,
        ROUND(population_2023 / NULLIF(land_area_km2, 0), 0) AS value
      FROM ${CATALOG}.${SCHEMA}.suburb
      WHERE population_2023 > 500 AND land_area_km2 > 0`,

    hpi: `
      SELECT s.suburb_id, tm.current_hpi AS value
      FROM ${CATALOG}.${SCHEMA}.suburb s
      JOIN (
        SELECT ta_name, current_hpi
        FROM ${CATALOG}.${SCHEMA}.ta__month
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ta_name ORDER BY date DESC) = 1
      ) tm ON s.territorial_authority = tm.ta_name
      WHERE tm.current_hpi IS NOT NULL`,

    median_price: `
      SELECT s.suburb_id, tm.current_annual_median_sales_nzd AS value
      FROM ${CATALOG}.${SCHEMA}.suburb s
      JOIN (
        SELECT ta_name, current_annual_median_sales_nzd
        FROM ${CATALOG}.${SCHEMA}.ta__month
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ta_name ORDER BY date DESC) = 1
      ) tm ON s.territorial_authority = tm.ta_name
      WHERE tm.current_annual_median_sales_nzd IS NOT NULL`,

    rent_affordability: `
      SELECT s.suburb_id, tq.rent_affordability_index AS value
      FROM ${CATALOG}.${SCHEMA}.suburb s
      JOIN (
        SELECT ta_name, rent_affordability_index
        FROM ${CATALOG}.${SCHEMA}.ta__quarter
        QUALIFY ROW_NUMBER() OVER (PARTITION BY ta_name ORDER BY quarter DESC) = 1
      ) tq ON s.territorial_authority = tq.ta_name
      WHERE tq.rent_affordability_index IS NOT NULL`,
  };

  const sql = METRIC_SQL[metric];
  if (!sql) return res.status(400).json({ error: `Unknown metric: ${metric}` });

  try {
    const cached = choroplethCache.get(metric);
    if (cached && Date.now() - cached.ts < CHOROPLETH_TTL) {
      return res.json(cached.data);
    }

    const rows = await runSql(sql);
    const data: ChoroplethRow[] = rows.map((r) => ({
      suburb_id: String(r[0]),
      value: r[1] != null ? Number(r[1]) : null,
    }));

    choroplethCache.set(metric, { data, ts: Date.now() });
    return res.json(data);
  } catch (err) {
    console.error(`[map-data] choropleth/${metric} error:`, err);
    return res.status(500).json({ error: String(err) });
  }
});
```

**Security note:** `metric` is validated against `METRIC_SQL` keys before use in SQL — no user input is interpolated into the query directly.

### 6.3 `GET /api/map/amenities`

Query param: `types` — comma-separated `amenity_type` values. Validated against allowlist before SQL interpolation.

```typescript
const VALID_AMENITY_TYPES = new Set([
  'supermarket', 'hospital', 'school', 'early_childhood',
  'pharmacy', 'gp_clinic', 'park', 'library',
]);

mapDataRouter.get('/amenities', requireAuth, async (req: Request, res: Response) => {
  const typesParam = String(req.query.types ?? '');
  const requestedTypes = typesParam
    .split(',')
    .map((t) => t.trim())
    .filter((t) => VALID_AMENITY_TYPES.has(t));

  if (requestedTypes.length === 0) {
    return res.status(400).json({ error: 'No valid amenity types specified' });
  }

  const cacheKey = [...requestedTypes].sort().join(',');

  try {
    const cached = amenityCache.get(cacheKey);
    if (cached && Date.now() - cached.ts < AMENITY_TTL) {
      return res.json(cached.data);
    }

    // Safe: requestedTypes is validated against allowlist
    const typeList = requestedTypes.map((t) => `'${t}'`).join(', ');
    const rows = await runSql(`
      SELECT osm_id, amenity_type, name, lat, lon
      FROM ${CATALOG}.${SCHEMA}.amenity__h3
      WHERE amenity_type IN (${typeList})
        AND lat IS NOT NULL AND lon IS NOT NULL
    `);

    const data: AmenityRow[] = rows.map((r) => ({
      osm_id: String(r[0]),
      amenity_type: String(r[1]),
      name: r[2] != null ? String(r[2]) : null,
      lat: Number(r[3]),
      lon: Number(r[4]),
    }));

    amenityCache.set(cacheKey, { data, ts: Date.now() });
    return res.json(data);
  } catch (err) {
    console.error('[map-data] amenities error:', err);
    return res.status(500).json({ error: String(err) });
  }
});
```

### 6.4 `GET /api/map/transit-stops`

No query params needed for Phase 3 — return all stops. Optional `?feeds=` filter can be added later.

```typescript
mapDataRouter.get('/transit-stops', requireAuth, async (req: Request, res: Response) => {
  try {
    if (transitCache && Date.now() - transitCache.ts < TRANSIT_TTL) {
      return res.json(transitCache.data);
    }

    const rows = await runSql(`
      SELECT
        stop_id,
        stop_name,
        stop_lat,
        stop_lon,
        feed_source,
        CASE
          WHEN stop_name ILIKE '%train%' OR stop_name ILIKE '% station%' THEN 'rail'
          WHEN stop_name ILIKE '%ferry%' OR stop_name ILIKE '%wharf%'    THEN 'ferry'
          ELSE 'bus'
        END AS route_type
      FROM ${CATALOG}.${SCHEMA}.transit_stop
      WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
    `);

    const data: TransitStopRow[] = rows.map((r) => ({
      stop_id: String(r[0]),
      stop_name: String(r[1]),
      lat: Number(r[2]),
      lon: Number(r[3]),
      feed_source: String(r[4]),
      route_type: String(r[5]),
    }));

    transitCache = { data, ts: Date.now() };
    return res.json(data);
  } catch (err) {
    console.error('[map-data] transit-stops error:', err);
    return res.status(500).json({ error: String(err) });
  }
});
```

### 6.5 `GET /api/map/hazard`

Query param: `flags` — comma-separated column names from the `hazard` table. Validated against allowlist.

```typescript
const VALID_HAZARD_FLAGS: Record<string, string> = {
  flood_plain:      'in_flood_plain',
  flood_prone:      'in_flood_prone_area',
  flood_sensitive:  'in_flood_sensitive_area',
  coastal_1pct:     'in_coastal_inundation_1_aep',
  coastal_100yr:    'in_coastal_inundation_100yr',
  regional:         'in_regional_flood_zone',
};

mapDataRouter.get('/hazard', requireAuth, async (req: Request, res: Response) => {
  const flagsParam = String(req.query.flags ?? '');
  const requestedFlags = flagsParam
    .split(',')
    .map((f) => f.trim())
    .filter((f) => f in VALID_HAZARD_FLAGS);

  if (requestedFlags.length === 0) {
    return res.status(400).json({ error: 'No valid hazard flags specified' });
  }

  const columnNames = requestedFlags.map((f) => VALID_HAZARD_FLAGS[f]);
  const whereClause = columnNames.map((c) => `${c} = true`).join(' OR ');

  try {
    // conv(cast(h3_cell as string), 10, 16) converts bigint to hex string
    const rows = await runSql(`
      SELECT conv(cast(h3_cell as string), 10, 16) AS h3_hex
      FROM ${CATALOG}.${SCHEMA}.hazard
      WHERE ${whereClause} AND h3_cell IS NOT NULL
    `);

    const data = rows.map((r) => ({
      h3_hex: String(r[0]).padStart(15, '0'),
    }));

    return res.json(data);
  } catch (err) {
    console.error('[map-data] hazard error:', err);
    return res.status(500).json({ error: String(err) });
  }
});
```

**Note:** The `whereClause` uses only validated column names from `VALID_HAZARD_FLAGS` — no user input is interpolated directly.

### 6.6 `GET /api/map/choropleth-suburb-ids`

Helper endpoint used by the choropleth layer to join `suburb_id` → suburb name (since `SuburbLayer` works by name, not suburb_id). Returns `{ suburb_id, suburb_name, centroid_lat, centroid_lng }[]`.

```typescript
let suburbDimCache: { data: { suburb_id: string; suburb_name: string; lat: number; lng: number }[]; ts: number } | null = null;

mapDataRouter.get('/suburb-dim', requireAuth, async (_req: Request, res: Response) => {
  try {
    if (suburbDimCache && Date.now() - suburbDimCache.ts < CHOROPLETH_TTL) {
      return res.json(suburbDimCache.data);
    }

    const rows = await runSql(`
      SELECT
        suburb_id,
        suburb_name,
        ST_Y(ST_GeomFromGeoJSON(h3_centerasgeojson(centroid_h3))) AS lat,
        ST_X(ST_GeomFromGeoJSON(h3_centerasgeojson(centroid_h3))) AS lng
      FROM ${CATALOG}.${SCHEMA}.suburb
      WHERE centroid_h3 IS NOT NULL AND population_2023 > 100
    `);

    const data = rows
      .map((r) => ({
        suburb_id: String(r[0]),
        suburb_name: String(r[1]),
        lat: Number(r[2]),
        lng: Number(r[3]),
      }))
      .filter((s) => !Number.isNaN(s.lat) && !Number.isNaN(s.lng));

    suburbDimCache = { data, ts: Date.now() };
    return res.json(data);
  } catch (err) {
    console.error('[map-data] suburb-dim error:', err);
    return res.status(500).json({ error: String(err) });
  }
});
```

---

## 7. Frontend Layer Components

All new files go under `client/src/components/`. They follow the same patterns as existing `isochrone-layer.tsx` and `suburb-layer.tsx`.

### 7.1 `choropleth-layer.tsx`

Overlays a choropleth fill on the suburb `CircleMarker` pins. Uses `useSWR` to fetch from `/api/map/choropleth/:metric`.

The existing `SuburbLayer` renders suburb pins coloured by `status` (active=green, dimmed=grey, highlighted=teal). The `ChoroplethLayer` runs **in parallel** and overrides the fill colour with the choropleth metric — the stroke/border still shows filter status.

```typescript
// client/src/components/choropleth-layer.tsx

import useSWR from 'swr';
import { CircleMarker, Tooltip } from 'react-leaflet';
import { useMapState } from '@/contexts/MapContext';

interface ChoroplethRow {
  suburb_id: string;
  value: number | null;
}

interface SuburbDimRow {
  suburb_id: string;
  suburb_name: string;
  lat: number;
  lng: number;
}

const COLOUR_SCHEMES: Record<string, string[]> = {
  // Low → high
  income:       ['#f0f9ff', '#bae6fd', '#38bdf8', '#0284c7', '#0c4a6e'],
  pop_density:  ['#f0f9ff', '#bae6fd', '#38bdf8', '#0284c7', '#0c4a6e'],
  hpi:          ['#eff6ff', '#bfdbfe', '#3b82f6', '#1d4ed8', '#1e3a8a'],
  median_price: ['#eff6ff', '#bfdbfe', '#3b82f6', '#1d4ed8', '#1e3a8a'],
  age:          ['#faf5ff', '#e9d5ff', '#a855f7', '#7e22ce', '#3b0764'],
  // Low=affordable, high=stressed
  rent:               ['#f0fdf4', '#fef9c3', '#fde68a', '#f97316', '#dc2626'],
  rent_affordability: ['#f0fdf4', '#fef9c3', '#fde68a', '#f97316', '#dc2626'],
  // Low=low risk, high=high risk
  crime:   ['#fff', '#fee2e2', '#fca5a5', '#f87171', '#dc2626'],
  crowding:['#fff', '#fee2e2', '#fca5a5', '#f87171', '#dc2626'],
  damp:    ['#fff', '#fee2e2', '#fca5a5', '#f87171', '#dc2626'],
  // Diverging: low=renters, high=owners
  owner_occ: ['#1d4ed8', '#93c5fd', '#e5e7eb', '#fbbf24', '#b45309'],
};

function quantileColor(value: number, values: number[], colors: string[]): string {
  const sorted = [...values].sort((a, b) => a - b);
  const n = colors.length;
  const quantileIndex = Math.floor((value / sorted[sorted.length - 1]) * (n - 1));
  return colors[Math.min(quantileIndex, n - 1)];
}

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function ChoroplethLayer() {
  const { featureLayers } = useMapState();
  const metric = featureLayers.choropleth;

  const { data: choroplethData } = useSWR<ChoroplethRow[]>(
    metric ? `/api/map/choropleth/${metric}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: CHOROPLETH_TTL_MS },
  );

  const { data: suburbDim } = useSWR<SuburbDimRow[]>(
    metric ? '/api/map/suburb-dim' : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: CHOROPLETH_TTL_MS },
  );

  if (!metric || !choroplethData || !suburbDim) return null;

  // Build lookup maps
  const valueMap = new Map(choroplethData.map((r) => [r.suburb_id, r.value]));
  const idMap = new Map(suburbDim.map((s) => [s.suburb_id, s]));

  // Compute non-null values for quantile calculation
  const values = choroplethData.filter((r) => r.value != null).map((r) => r.value as number);
  const colors = COLOUR_SCHEMES[metric] ?? COLOUR_SCHEMES.income;

  return (
    <>
      {suburbDim.map((suburb) => {
        const value = valueMap.get(suburb.suburb_id);
        if (value == null) return null;

        const fillColor = quantileColor(value, values, colors);
        return (
          <CircleMarker
            key={`choropleth-${suburb.suburb_id}`}
            center={[suburb.lat, suburb.lng]}
            radius={7}
            pathOptions={{
              color: '#374151',
              weight: 0.5,
              fillColor,
              fillOpacity: 0.85,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
              <span className="text-sm font-medium">{suburb.suburb_name}</span>
              <br />
              <span className="text-xs text-muted-foreground">
                {CHOROPLETH_LABELS[metric]}: {formatChoroplethValue(metric, value)}
              </span>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

const CHOROPLETH_LABELS: Record<string, string> = {
  income: 'Median income', rent: 'Median rent', owner_occ: 'Owner-occupier',
  crowding: 'Crowding', crime: 'Crime/1k', age: 'Median age',
  damp: 'Damp housing', pop_density: 'Pop density', hpi: 'HPI',
  median_price: 'Median price', rent_affordability: 'Rent affordability',
};

function formatChoroplethValue(metric: string, value: number): string {
  if (['income', 'median_price'].includes(metric)) return `$${value.toLocaleString()}`;
  if (metric === 'rent') return `$${value}/wk`;
  if (['owner_occ', 'crowding', 'damp'].includes(metric)) return `${value}%`;
  if (metric === 'crime') return `${value} per 1k`;
  if (metric === 'age') return `${value} yrs`;
  if (metric === 'pop_density') return `${value}/km²`;
  return String(value);
}

const CHOROPLETH_TTL_MS = 4 * 60 * 60 * 1000;
```

**Rendering strategy:** `ChoroplethLayer` renders its own `CircleMarker` set (not replacing `SuburbLayer`'s), positioned at the same centroid. `SuburbLayer` pins show filter status (ring colour); choropleth pins show metric. They'll overlap — order them in `MapPanel` so choropleth is on top. For a cleaner approach in Phase 1, suppress `SuburbLayer` fill when a choropleth is active by passing a `useMapState()` check.

### 7.2 `amenity-layer.tsx`

Uses `react-leaflet-cluster` (already installed). Fetches amenities for all currently active amenity layers in a single batched request.

```typescript
// client/src/components/amenity-layer.tsx

import MarkerClusterGroup from 'react-leaflet-cluster';
import { Marker, Tooltip, useMapEvents } from 'react-leaflet';
import { useState, useMemo } from 'react';
import useSWR from 'swr';
import L from 'leaflet';
import { useMapState } from '@/contexts/MapContext';

const AMENITY_LAYER_TO_TYPE: Record<string, string> = {
  amenity_school: 'school',
  amenity_ece: 'early_childhood',
  amenity_gp: 'gp_clinic',
  amenity_supermarket: 'supermarket',
  amenity_pharmacy: 'pharmacy',
  amenity_hospital: 'hospital',
  amenity_library: 'library',
  amenity_park: 'park',
};

const AMENITY_COLORS: Record<string, string> = {
  school: '#3b82f6', early_childhood: '#60a5fa', gp_clinic: '#ef4444',
  supermarket: '#22c55e', pharmacy: '#f97316', hospital: '#dc2626',
  library: '#8b5cf6', park: '#16a34a',
};

// Creates an SVG circle icon for a given amenity type
function createAmenityIcon(amenityType: string, zoom: number): L.DivIcon {
  const color = AMENITY_COLORS[amenityType] ?? '#6b7280';
  const size = amenityType === 'hospital' ? 14 : 10;
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:1.5px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3)"></div>`,
  });
}

const fetcher = (url: string) => fetch(url).then((r) => r.json());

interface AmenityRow {
  osm_id: string; amenity_type: string; name: string | null; lat: number; lon: number;
}

export function AmenityLayer() {
  const { featureLayers } = useMapState();
  const [zoom, setZoom] = useState(11);

  useMapEvents({ zoomend: (e) => setZoom(e.target.getZoom()) });

  // Collect active amenity layer IDs
  const activeAmenityLayers = useMemo(
    () => [...featureLayers.active].filter((id) => id.startsWith('amenity_')),
    [featureLayers.active],
  );

  // Map to amenity_type values, excluding parks below zoom 12
  const activeTypes = useMemo(() => {
    return activeAmenityLayers
      .map((id) => AMENITY_LAYER_TO_TYPE[id])
      .filter((t): t is string => t != null)
      .filter((t) => t !== 'park' || zoom >= 12);
  }, [activeAmenityLayers, zoom]);

  const url = activeTypes.length > 0
    ? `/api/map/amenities?types=${activeTypes.join(',')}`
    : null;

  const { data: amenities } = useSWR<AmenityRow[]>(url, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60 * 60 * 1000,
  });

  if (!amenities || amenities.length === 0) return null;

  return (
    <MarkerClusterGroup
      chunkedLoading
      maxClusterRadius={60}
      showCoverageOnHover={false}
    >
      {amenities.map((a) => (
        <Marker
          key={a.osm_id}
          position={[a.lat, a.lon]}
          icon={createAmenityIcon(a.amenity_type, zoom)}
        >
          <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
            <div className="text-sm">
              <div className="font-medium">{a.name ?? a.amenity_type}</div>
              <div className="text-xs text-muted-foreground capitalize">{a.amenity_type.replace('_', ' ')}</div>
            </div>
          </Tooltip>
        </Marker>
      ))}
    </MarkerClusterGroup>
  );
}
```

**Parks zoom note:** The `filter` on line `filter((t) => t !== 'park' || zoom >= 12)` silently drops parks from the fetch URL when zoomed out. The `LayerControlPanel` should show a tooltip "Parks visible at zoom ≥ 12" when parks is enabled and zoom < 12.

### 7.3 `transit-layer.tsx`

```typescript
// client/src/components/transit-layer.tsx

import MarkerClusterGroup from 'react-leaflet-cluster';
import { Marker, Tooltip } from 'react-leaflet';
import { useMemo } from 'react';
import useSWR from 'swr';
import L from 'leaflet';
import { useMapState } from '@/contexts/MapContext';

const ROUTE_TYPE_COLORS: Record<string, string> = {
  rail:  '#f97316', // orange-500
  ferry: '#06b6d4', // cyan-500
  bus:   '#6366f1', // indigo-500
};

function createTransitIcon(routeType: string): L.DivIcon {
  const color = ROUTE_TYPE_COLORS[routeType] ?? '#6b7280';
  const emoji = routeType === 'rail' ? '🚂' : routeType === 'ferry' ? '⛴' : '🚌';
  return L.divIcon({
    className: '',
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    html: `<div style="font-size:12px;line-height:16px;text-align:center;filter:drop-shadow(0 1px 1px rgba(0,0,0,0.4))">${emoji}</div>`,
  });
}

interface TransitStopRow {
  stop_id: string; stop_name: string; lat: number; lon: number; feed_source: string; route_type: string;
}

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function TransitLayer() {
  const { featureLayers } = useMapState();
  const isActive = featureLayers.active.has('transit_stops');

  const { data: stops } = useSWR<TransitStopRow[]>(
    isActive ? '/api/map/transit-stops' : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 5 * 60 * 1000 },
  );

  if (!isActive || !stops || stops.length === 0) return null;

  return (
    <MarkerClusterGroup chunkedLoading maxClusterRadius={80} showCoverageOnHover={false}>
      {stops.map((s) => (
        <Marker
          key={`${s.feed_source}-${s.stop_id}`}
          position={[s.lat, s.lon]}
          icon={createTransitIcon(s.route_type)}
        >
          <Tooltip direction="top" offset={[0, -6]} opacity={0.95}>
            <div className="text-sm">
              <div className="font-medium">{s.stop_name}</div>
              <div className="text-xs text-muted-foreground capitalize">
                {s.route_type} · {s.feed_source.replace('_', ' ')}
              </div>
            </div>
          </Tooltip>
        </Marker>
      ))}
    </MarkerClusterGroup>
  );
}
```

### 7.4 `hazard-layer.tsx`

Renders H3 res-8 cells as filled GeoJSON polygons, using the same `cellToBoundary` + `h3-js` pattern as the existing `IsochroneLayer`.

Includes a zoom-gate: only render at zoom ≥ 10. Below zoom 10, show a suburb-level choropleth fallback instead (optional — can start with a simple "zoom in to see hazard cells" tooltip on the legend).

```typescript
// client/src/components/hazard-layer.tsx

import { useState, useEffect, useMemo } from 'react';
import { GeoJSON, useMapEvents } from 'react-leaflet';
import { cellToBoundary } from 'h3-js';
import type { FeatureCollection } from 'geojson';
import { useMapState } from '@/contexts/MapContext';

const MIN_ZOOM = 10;

const HAZARD_LAYER_TO_FLAG: Record<string, string> = {
  hazard_flood_plain:     'flood_plain',
  hazard_flood_prone:     'flood_prone',
  hazard_flood_sensitive: 'flood_sensitive',
  hazard_coastal_1pct:    'coastal_1pct',
  hazard_coastal_100yr:   'coastal_100yr',
  hazard_regional:        'regional',
};

const HAZARD_FILL_COLORS: Record<string, string> = {
  flood_plain:     'rgba(59, 130, 246, 0.4)',
  flood_prone:     'rgba(99, 102, 241, 0.4)',
  flood_sensitive: 'rgba(139, 92, 246, 0.35)',
  coastal_1pct:    'rgba(239, 68, 68, 0.45)',
  coastal_100yr:   'rgba(249, 115, 22, 0.45)',
  regional:        'rgba(234, 179, 8, 0.4)',
};

interface HazardCell { h3_hex: string; }

function hexesToGeoJSON(hexes: string[], fillColor: string): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: hexes
      .map((id) => {
        try {
          const boundary = cellToBoundary(id, true);
          return {
            type: 'Feature' as const,
            properties: { fillColor },
            geometry: {
              type: 'Polygon' as const,
              coordinates: [[...boundary, boundary[0]]],
            },
          };
        } catch {
          return null;
        }
      })
      .filter((f): f is NonNullable<typeof f> => f != null),
  };
}

export function HazardLayer() {
  const { featureLayers } = useMapState();
  const [zoom, setZoom] = useState(11);
  const [layerData, setLayerData] = useState<Record<string, HazardCell[]>>({});

  useMapEvents({ zoomend: (e) => setZoom(e.target.getZoom()) });

  const activeHazardLayers = useMemo(
    () => [...featureLayers.active].filter((id) => id.startsWith('hazard_')),
    [featureLayers.active],
  );

  // Fetch each active hazard layer independently (separate cache entries)
  useEffect(() => {
    if (zoom < MIN_ZOOM) return;
    for (const layerId of activeHazardLayers) {
      if (layerData[layerId]) continue; // already fetched
      const flag = HAZARD_LAYER_TO_FLAG[layerId];
      if (!flag) continue;

      fetch(`/api/map/hazard?flags=${flag}`)
        .then((r) => r.json())
        .then((data: HazardCell[]) => {
          setLayerData((prev) => ({ ...prev, [layerId]: data }));
        })
        .catch((e) => console.error(`[HazardLayer] ${layerId} fetch failed:`, e));
    }
  }, [activeHazardLayers, zoom, layerData]);

  if (zoom < MIN_ZOOM || activeHazardLayers.length === 0) return null;

  return (
    <>
      {activeHazardLayers.map((layerId) => {
        const cells = layerData[layerId];
        if (!cells || cells.length === 0) return null;
        const flag = HAZARD_LAYER_TO_FLAG[layerId];
        const fillColor = HAZARD_FILL_COLORS[flag] ?? 'rgba(100, 100, 100, 0.3)';
        const geojson = hexesToGeoJSON(cells.map((c) => c.h3_hex), fillColor);

        return (
          <GeoJSON
            key={layerId}
            data={geojson}
            style={{
              color: 'transparent',
              weight: 0,
              fillColor,
              fillOpacity: 0.4,
            }}
          />
        );
      })}
    </>
  );
}
```

**Performance note:** Hazard cell counts are unknown but could be 50k+. Each layer fetches independently so they don't block each other. The `layerData` cache persists for the session — not cleared on zoom change, so data loads once per session per active flag.

---

## 8. LayerControlPanel Component

New file: `client/src/components/layer-control-panel.tsx`

```typescript
// client/src/components/layer-control-panel.tsx

import { useState } from 'react';
import { Layers } from 'lucide-react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { useMapState, useMapDispatch, type ChoroplethMetric, type FeatureLayerId } from '@/contexts/MapContext';
import { cn } from '@/lib/utils';

// ---- Configuration objects ----

const CHOROPLETH_OPTIONS: { id: ChoroplethMetric; label: string }[] = [
  { id: 'rent',               label: 'Median weekly rent' },
  { id: 'income',             label: 'Household income' },
  { id: 'crime',              label: 'Crime rate (per 1k)' },
  { id: 'owner_occ',          label: 'Owner-occupier %' },
  { id: 'crowding',           label: 'Crowding rate' },
  { id: 'age',                label: 'Median age' },
  { id: 'damp',               label: 'Damp/mould housing' },
  { id: 'pop_density',        label: 'Population density' },
  { id: 'hpi',                label: 'House Price Index' },
  { id: 'median_price',       label: 'Median sale price' },
  { id: 'rent_affordability', label: 'Rent affordability' },
];

const AMENITY_OPTIONS: { id: FeatureLayerId; label: string; icon: string }[] = [
  { id: 'amenity_school',      label: 'Schools',         icon: '🏫' },
  { id: 'amenity_ece',         label: 'ECE centres',     icon: '🎒' },
  { id: 'amenity_gp',          label: 'GP clinics',      icon: '🩺' },
  { id: 'amenity_supermarket', label: 'Supermarkets',    icon: '🛒' },
  { id: 'amenity_pharmacy',    label: 'Pharmacies',      icon: '💊' },
  { id: 'amenity_hospital',    label: 'Hospitals',       icon: '🏥' },
  { id: 'amenity_library',     label: 'Libraries',       icon: '📚' },
  { id: 'amenity_park',        label: 'Parks',           icon: '🌿' },
];

const HAZARD_OPTIONS: { id: FeatureLayerId; label: string }[] = [
  { id: 'hazard_flood_plain',     label: 'Flood plains' },
  { id: 'hazard_flood_prone',     label: 'Flood-prone areas' },
  { id: 'hazard_flood_sensitive', label: 'Flood-sensitive areas' },
  { id: 'hazard_coastal_1pct',    label: 'Coastal inundation 1% AEP' },
  { id: 'hazard_coastal_100yr',   label: 'Coastal inundation 100yr' },
  { id: 'hazard_regional',        label: 'Regional flood zones' },
];

// ---- Component ----

export function LayerControlPanel() {
  const [open, setOpen] = useState(false);
  const { featureLayers } = useMapState();
  const dispatch = useMapDispatch();

  const activeCount =
    (featureLayers.choropleth ? 1 : 0) + featureLayers.active.size;

  return (
    <div className="absolute right-3 top-3 z-[1000]">
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        {/* Toggle button */}
        <Collapsible.Trigger asChild>
          <button
            type="button"
            className={cn(
              'flex items-center gap-1.5 rounded-lg border border-border bg-background/95 px-3 py-1.5 text-sm font-medium shadow-sm backdrop-blur-sm transition-colors',
              open && 'bg-primary text-primary-foreground',
            )}
          >
            <Layers className="size-3.5" />
            Layers
            {activeCount > 0 && (
              <span className={cn(
                'ml-0.5 rounded-full px-1.5 py-0 text-xs font-semibold',
                open ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-primary text-primary-foreground',
              )}>
                {activeCount}
              </span>
            )}
          </button>
        </Collapsible.Trigger>

        {/* Panel */}
        <Collapsible.Content>
          <div className="mt-1.5 w-64 rounded-xl border border-border bg-background/98 shadow-xl backdrop-blur-sm">
            <div className="max-h-[70vh] overflow-y-auto p-3">

              {/* CHOROPLETH */}
              <Section title="Choropleth (suburb fill)">
                <RadioOption
                  label="None"
                  checked={featureLayers.choropleth === null}
                  onChange={() => dispatch({ type: 'SET_CHOROPLETH', metric: null })}
                />
                {CHOROPLETH_OPTIONS.map(({ id, label }) => (
                  <RadioOption
                    key={id}
                    label={label}
                    checked={featureLayers.choropleth === id}
                    onChange={() => dispatch({ type: 'SET_CHOROPLETH', metric: id })}
                  />
                ))}
              </Section>

              <Divider />

              {/* AMENITIES */}
              <Section title="Amenities">
                {AMENITY_OPTIONS.map(({ id, label, icon }) => (
                  <CheckOption
                    key={id}
                    label={`${icon} ${label}`}
                    checked={featureLayers.active.has(id)}
                    onChange={() => dispatch({ type: 'TOGGLE_FEATURE_LAYER', layerId: id })}
                  />
                ))}
              </Section>

              <Divider />

              {/* TRANSIT */}
              <Section title="Transit">
                <CheckOption
                  label="🚌 All stops"
                  checked={featureLayers.active.has('transit_stops')}
                  onChange={() => dispatch({ type: 'TOGGLE_FEATURE_LAYER', layerId: 'transit_stops' })}
                />
              </Section>

              <Divider />

              {/* FLOOD HAZARD */}
              <Section title="Flood hazard (zoom ≥ 10)">
                {HAZARD_OPTIONS.map(({ id, label }) => (
                  <CheckOption
                    key={id}
                    label={label}
                    checked={featureLayers.active.has(id)}
                    onChange={() => dispatch({ type: 'TOGGLE_FEATURE_LAYER', layerId: id })}
                  />
                ))}
              </Section>

            </div>
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
}

// ---- Sub-components ----

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-1">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Divider() {
  return <div className="my-2 border-t border-border" />;
}

function RadioOption({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors hover:bg-secondary',
        checked && 'bg-primary/10 font-medium text-primary',
      )}
    >
      <span className={cn(
        'size-3 rounded-full border',
        checked ? 'border-primary bg-primary' : 'border-border bg-background',
      )} />
      {label}
    </button>
  );
}

function CheckOption({ label, checked, onChange }: { label: string; checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={cn(
        'flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors hover:bg-secondary',
        checked && 'bg-primary/10 font-medium text-primary',
      )}
    >
      <span className={cn(
        'size-3 rounded-sm border',
        checked ? 'border-primary bg-primary' : 'border-border bg-background',
      )} />
      {label}
    </button>
  );
}
```

**Placement:** `absolute right-3 top-3 z-[1000]` — top-right of the map container. The existing "Map Mode" badge is `absolute left-4 top-4`, so they don't overlap.

---

## 9. MapLegend Component

New file: `client/src/components/map-legend.tsx`

Shows active layer colours at the bottom-left of the map.

```typescript
// client/src/components/map-legend.tsx

import { useMapState } from '@/contexts/MapContext';

const HAZARD_COLORS: Record<string, { label: string; color: string }> = {
  hazard_flood_plain:     { label: 'Flood plain',       color: 'rgba(59, 130, 246, 0.6)' },
  hazard_flood_prone:     { label: 'Flood-prone',       color: 'rgba(99, 102, 241, 0.6)' },
  hazard_flood_sensitive: { label: 'Flood-sensitive',   color: 'rgba(139, 92, 246, 0.55)' },
  hazard_coastal_1pct:    { label: 'Coastal 1% AEP',    color: 'rgba(239, 68, 68, 0.65)' },
  hazard_coastal_100yr:   { label: 'Coastal 100yr',     color: 'rgba(249, 115, 22, 0.65)' },
  hazard_regional:        { label: 'Regional flood',    color: 'rgba(234, 179, 8, 0.6)' },
};

const CHOROPLETH_GRADIENTS: Record<string, { colors: string[]; label: string; lowLabel: string; highLabel: string }> = {
  income:        { colors: ['#f0f9ff','#0c4a6e'], label: 'Income', lowLabel: 'Low', highLabel: 'High' },
  rent:          { colors: ['#f0fdf4','#dc2626'], label: 'Rent', lowLabel: 'Cheap', highLabel: 'Expensive' },
  crime:         { colors: ['#fff','#dc2626'], label: 'Crime', lowLabel: 'Low', highLabel: 'High' },
  crowding:      { colors: ['#fff','#dc2626'], label: 'Crowding', lowLabel: 'Low', highLabel: 'High' },
  owner_occ:     { colors: ['#1d4ed8','#b45309'], label: 'Owner-occ', lowLabel: 'Renters', highLabel: 'Owners' },
  age:           { colors: ['#faf5ff','#3b0764'], label: 'Age', lowLabel: 'Young', highLabel: 'Older' },
  damp:          { colors: ['#fff','#dc2626'], label: 'Damp', lowLabel: 'Low', highLabel: 'High' },
  pop_density:   { colors: ['#f0f9ff','#0c4a6e'], label: 'Density', lowLabel: 'Sparse', highLabel: 'Dense' },
  hpi:           { colors: ['#eff6ff','#1e3a8a'], label: 'HPI', lowLabel: 'Low', highLabel: 'High' },
  median_price:  { colors: ['#eff6ff','#1e3a8a'], label: 'Sale price', lowLabel: 'Low', highLabel: 'High' },
  rent_affordability: { colors: ['#f0fdf4','#dc2626'], label: 'Affordability', lowLabel: 'Affordable', highLabel: 'Stressed' },
};

export function MapLegend() {
  const { featureLayers } = useMapState();
  const { choropleth, active } = featureLayers;

  const activeHazardLayers = [...active].filter((id) => id.startsWith('hazard_'));
  const hasAnything = choropleth || activeHazardLayers.length > 0;

  if (!hasAnything) return null;

  return (
    <div className="absolute bottom-8 left-3 z-[1000] flex flex-col gap-1.5">
      {/* Choropleth legend */}
      {choropleth && CHOROPLETH_GRADIENTS[choropleth] && (() => {
        const g = CHOROPLETH_GRADIENTS[choropleth];
        const gradient = `linear-gradient(to right, ${g.colors.join(', ')})`;
        return (
          <div className="rounded-lg border border-border bg-background/95 px-3 py-2 shadow-sm backdrop-blur-sm">
            <p className="mb-1 text-xs font-semibold">{g.label}</p>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground">{g.lowLabel}</span>
              <div className="h-2 w-24 rounded-full" style={{ background: gradient }} />
              <span className="text-[10px] text-muted-foreground">{g.highLabel}</span>
            </div>
          </div>
        );
      })()}

      {/* Hazard layers legend */}
      {activeHazardLayers.length > 0 && (
        <div className="rounded-lg border border-border bg-background/95 px-3 py-2 shadow-sm backdrop-blur-sm">
          <p className="mb-1.5 text-xs font-semibold">Flood hazard</p>
          <div className="space-y-1">
            {activeHazardLayers.map((id) => {
              const info = HAZARD_COLORS[id];
              if (!info) return null;
              return (
                <div key={id} className="flex items-center gap-1.5">
                  <div className="size-3 rounded-sm" style={{ background: info.color }} />
                  <span className="text-[10px] text-muted-foreground">{info.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## 10. MapPanel Wiring

Modify `client/src/components/map-panel.tsx` to add the new layers and panels:

```typescript
// client/src/components/map-panel.tsx — NEW VERSION

import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer } from 'react-leaflet';
import { SuburbLayer } from './suburb-layer';
import { FlyToController } from './fly-to-controller';
import { IsochroneLayer } from './isochrone-layer';
import { ChoroplethLayer } from './choropleth-layer';     // NEW
import { AmenityLayer } from './amenity-layer';             // NEW
import { TransitLayer } from './transit-layer';             // NEW
import { HazardLayer } from './hazard-layer';               // NEW
import { LayerControlPanel } from './layer-control-panel'; // NEW
import { MapLegend } from './map-legend';                   // NEW
import { useMapState } from '@/contexts/MapContext';

const DEFAULT_CENTER: [number, number] = [-36.86, 174.76];
const DEFAULT_ZOOM = 11;

export function MapPanel() {
  const { featureLayers } = useMapState();

  return (
    // Outer div is relative so absolute-positioned controls are correctly anchored
    <div className="relative h-full w-full">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        className="h-full w-full"
        style={{ zIndex: 0 }}
        zoomControl={false} // we'll add custom zoom controls later
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Layer draw order — bottom to top:
            1. Isochrone (H3 fill, lowest)
            2. Hazard H3 cells (fill, semi-transparent)
            3. Choropleth suburb pins (fill by metric)
            4. Suburb filter pins (ring/outline shows filter status) — on top so always clickable
            5. Amenity + transit markers (always on top for clickability) */}

        <IsochroneLayer />

        {featureLayers.active.size > 0 && <HazardLayer />}

        {featureLayers.choropleth && <ChoroplethLayer />}
        <SuburbLayer />

        {featureLayers.active.has('transit_stops') && <TransitLayer />}
        {[...featureLayers.active].some((id) => id.startsWith('amenity_')) && <AmenityLayer />}

        <FlyToController />
      </MapContainer>

      {/* Controls outside MapContainer (still within relative parent) */}
      <LayerControlPanel />
      <MapLegend />
    </div>
  );
}
```

**Note:** `LayerControlPanel` and `MapLegend` are positioned using `absolute` inside the `relative h-full w-full` wrapper div, **not** inside the `MapContainer`. This avoids Leaflet's z-index management. The existing filter summary legend and suburb info panel in `map-chat.tsx` are already positioned this way too — keep them there.

---

## 11. message.tsx — Feature Layer Dispatch

Extend the existing `render_map` interception block in `client/src/components/message.tsx` (currently around line 271). The key change is reading the new `choropleth`, `feature_layers_add`, and `feature_layers_remove` fields from the tool input:

```typescript
// In message.tsx, replace the existing render_map block:

if (toolName === 'render_map') {
  if (
    mapDispatch &&
    (state === 'input-available' || state === 'output-available')
  ) {
    const mapInput = input as {
      suburbs: SuburbEntry[];
      isochrone_suburb: string | null;
      isochrone_minutes: number | null;
      isochrone_mode: string | null;
      filter_summary: string;
      choropleth?: string | null;                  // NEW
      feature_layers_add?: string[];               // NEW
      feature_layers_remove?: string[];            // NEW
    };

    const isochrone: IsochroneState | null =
      mapInput.isochrone_suburb && mapInput.isochrone_minutes
        ? {
            suburb: mapInput.isochrone_suburb,
            minutes: mapInput.isochrone_minutes,
            mode: (mapInput.isochrone_mode ?? 'transit') as IsochroneState['mode'],
          }
        : null;

    mapDispatch({
      type: 'RENDER_MAP',
      suburbs: mapInput.suburbs ?? [],
      isochrone,
      filterSummary: mapInput.filter_summary ?? '',
    });

    // NEW: apply choropleth if provided
    if (mapInput.choropleth !== undefined) {
      mapDispatch({
        type: 'SET_CHOROPLETH',
        metric: (mapInput.choropleth as ChoroplethMetric) ?? null,
      });
    }

    // NEW: toggle individual feature layers on/off
    for (const layerId of mapInput.feature_layers_add ?? []) {
      mapDispatch({ type: 'TOGGLE_FEATURE_LAYER', layerId: layerId as FeatureLayerId });
    }
    // Note: for removes, we need a REMOVE action — simplest is to toggle only if currently active
    for (const layerId of mapInput.feature_layers_remove ?? []) {
      mapDispatch({ type: 'TOGGLE_FEATURE_LAYER', layerId: layerId as FeatureLayerId });
      // TOGGLE_FEATURE_LAYER removes if already active; add a SET_FEATURE_LAYER_OFF action
      // for correctness, or check state before dispatch
    }
  }
  return null;
}
```

**Refinement:** The toggle approach for removes has a race condition if the layer wasn't active. A cleaner approach is two separate actions: `ENABLE_FEATURE_LAYER` and `DISABLE_FEATURE_LAYER`. But for an initial implementation, checking state before toggle is fine.

---

## 12. Performance & Rendering Notes

| Concern | Detail | Mitigation |
|---|---|---|
| Parks (11k points) | At zoom < 12, 11k markers tank canvas | Exclude parks from fetch URL when zoom < 12 via `useMapEvents`. Already coded into `AmenityLayer`. |
| Transit (13k stops) | All at once is fine for `react-leaflet-cluster` with `chunkedLoading` | `chunkedLoading` on `MarkerClusterGroup` spreads DOM insertion across animation frames |
| Hazard H3 cells | Unknown count — potentially 50k+ | Fetched per-flag. `cellToBoundary` is fast (~0.1ms per cell). 50k cells × 6 boundary points ≈ 300k GeoJSON coordinates. Leaflet handles this but may be slow on mobile. Consider debouncing until zoom ≥ 10. |
| Choropleth re-renders | Every MapState update re-renders all `CircleMarker` | Memo-ize `ChoroplethLayer` with `React.memo`. Cache computed quantile color per (value, sorted-values) with a simple FIFO. |
| Layer draw order | Choropleth pins overlap suburb filter pins | Choropleth rendered below SuburbLayer via `MapPanel` import order. SuburbLayer pins have `weight: 2` stroke; choropleth has `weight: 0.5` — visually distinct. |
| SWR deduplication | Toggling a layer off then on refetches | SWR's `dedupingInterval` prevents refetch within window. Set 4 hours for census, 1 hour for amenities, 5 min for transit. |
| H3 GeoJSON computation | `cellToBoundary` per render | Memoize with `useMemo` keyed on the hexes array (same pattern as `IsochroneLayer`). |
| `react-leaflet-cluster` import | Uses a default export | Import as `import MarkerClusterGroup from 'react-leaflet-cluster'` — already in package.json, no install needed. |

---

## 13. Known Issues with Existing Backend Routes

The current `map-data.ts` has queries that reference tables not present in `housing.gold`:

```typescript
// CURRENT (BROKEN) — references non-existent views:
FROM ${CATALOG}.${SCHEMA}.suburb_metrics_latest   // ← Does not exist
FROM ${CATALOG}.${SCHEMA}.suburb_hazard            // ← Does not exist
```

The existing `GET /api/map/centroids` route queries `suburb_metrics_latest` and the `GET /api/map/suburb/:name` route queries both `suburb_metrics_latest` and `suburb_hazard`. These will fail at runtime.

**Fix required before this feature work begins:**

Update the existing routes in `map-data.ts` to query the actual gold tables:

```typescript
// /api/map/centroids — fix to use housing.gold.suburb
const rows = await runSql(`
  SELECT
    suburb_name,
    ST_Y(ST_GeomFromGeoJSON(h3_centerasgeojson(centroid_h3))) AS lat,
    ST_X(ST_GeomFromGeoJSON(h3_centerasgeojson(centroid_h3))) AS lng
  FROM ${CATALOG}.${SCHEMA}.suburb
  WHERE centroid_h3 IS NOT NULL
`);

// /api/map/suburb/:name — fix to use housing.gold.suburb__year + hazard
// (use the lookup_hazards Python tool logic as reference — it already works)
```

The isochrone route in `map-data.ts` also has a SQL issue — it queries `isochrone` with a `suburb_name` column that doesn't exist (the gold schema uses `origin_h3`, not suburb name directly). The correct join goes through `h3_cell`. The `map-mode-plan.md` Section 5.3 has the correct SQL — use that.

---

## 14. Phased Delivery

### Phase 0 — Fix broken existing routes (prerequisite)

Before any feature layer work, fix the broken `map-data.ts` routes to use correct gold table names (Section 13). Otherwise the base map won't work.

Deliverables:
- [ ] Fix `/api/map/centroids` to query `housing.gold.suburb`
- [ ] Fix `/api/map/suburb/:name` to query `housing.gold.suburb__year` + derive hazard from `housing.gold.hazard`
- [ ] Fix `/api/map/isochrone/:suburb/:minutes/:mode` to use correct H3-based join (see `map-mode-plan.md` §5.3)
- [ ] Smoke test: map loads and suburb pins appear on the screen

### Phase 1 — Choropleth panel

Build the `LayerControlPanel` with choropleth radio options only. No point layers yet.

Deliverables:
- [ ] Extend `MapContext.tsx`: add `FeatureLayerState`, `ChoroplethMetric` type, `featureLayers` to `MapState`, `SET_CHOROPLETH` action and reducer case
- [ ] Add `/api/map/choropleth/:metric` route to `map-data.ts` (11 metrics, all SQL in Section 6.2)
- [ ] Add `/api/map/suburb-dim` route to `map-data.ts` (suburb_id → name + centroid lookup)
- [ ] Create `choropleth-layer.tsx` component
- [ ] Create `layer-control-panel.tsx` (choropleth section only, stub out other sections)
- [ ] Create `map-legend.tsx` (choropleth gradient legend only)
- [ ] Update `map-panel.tsx`: add `ChoroplethLayer`, `LayerControlPanel`, `MapLegend`, wrap in `relative` div
- [ ] Manual test: toggle rent choropleth on, verify suburb fills update, legend appears

### Phase 2 — Amenity point layers

Deliverables:
- [ ] Extend `MapContext.tsx`: add `AmenityLayerId` type, `TOGGLE_FEATURE_LAYER` action and reducer case
- [ ] Add `/api/map/amenities` route to `map-data.ts`
- [ ] Create `amenity-layer.tsx` component (with `react-leaflet-cluster`, zoom-gating for parks)
- [ ] Update `layer-control-panel.tsx`: add amenity checkboxes section
- [ ] Update `map-panel.tsx`: add `AmenityLayer`
- [ ] Manual test: toggle schools on, verify clustered markers appear and expand on click

### Phase 3 — Transit layer

Deliverables:
- [ ] Add `/api/map/transit-stops` route to `map-data.ts`
- [ ] Create `transit-layer.tsx` component
- [ ] Update `layer-control-panel.tsx`: add transit section
- [ ] Update `map-panel.tsx`: add `TransitLayer`
- [ ] Manual test: toggle transit stops on, verify 13k stops cluster correctly

### Phase 4 — Hazard H3 layers

Deliverables:
- [ ] Add `/api/map/hazard` route to `map-data.ts`
- [ ] Create `hazard-layer.tsx` component (zoom-gated at zoom ≥ 10)
- [ ] Update `layer-control-panel.tsx`: add hazard section
- [ ] Update `map-panel.tsx`: add `HazardLayer`
- [ ] Update `map-legend.tsx`: add hazard colour swatches
- [ ] Manual test: toggle flood plain on, zoom to Auckland, verify H3 cells render

### Phase 5 — Agent integration (render_map extension)

Deliverables:
- [ ] Update `render_map.py`: add `choropleth`, `feature_layers_add`, `feature_layers_remove` parameters (Section 5.1)
- [ ] Extend `message.tsx` render_map interception block (Section 11)
- [ ] Add feature_layers examples to `MAP_SYSTEM_PROMPT` in `agent_server/prompts.py` (Section 5.2)
- [ ] Add `SET_FEATURE_LAYERS` action to `MapContext.tsx` for bulk agent-driven updates
- [ ] Manual test: ask agent "show me flood risk" — verify flood layer activates on map

---

## 15. Full SQL Reference

### Choropleth: all metrics joined in one query (for info panel enrichment)

```sql
SELECT
  y.suburb_id,
  s.suburb_name,
  y.median_household_income,
  y.median_weekly_rent,
  ROUND(y.owner_occupier_pct * 100, 1)                                          AS owner_occ_pct,
  ROUND(y.percent_crowded * 100, 1)                                             AS crowding_pct,
  ROUND(y.total_victimisations_2023 * 1000.0 / NULLIF(y.population_total, 0), 1) AS crime_per_1k,
  y.median_age,
  ROUND((y.dwellings_always_damp + y.dwellings_sometimes_damp) * 100.0
    / NULLIF(y.households_total, 0), 1)                                         AS damp_pct,
  ROUND(s.population_2023 / NULLIF(s.land_area_km2, 0), 0)                     AS pop_density_km2,
  tm.current_hpi,
  tm.current_annual_median_sales_nzd,
  tq.rent_affordability_index
FROM housing.gold.suburb__year y
JOIN housing.gold.suburb s USING (suburb_id)
LEFT JOIN (
  SELECT ta_name, current_hpi, current_annual_median_sales_nzd
  FROM housing.gold.ta__month
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ta_name ORDER BY date DESC) = 1
) tm ON s.territorial_authority = tm.ta_name
LEFT JOIN (
  SELECT ta_name, rent_affordability_index
  FROM housing.gold.ta__quarter
  QUALIFY ROW_NUMBER() OVER (PARTITION BY ta_name ORDER BY quarter DESC) = 1
) tq ON s.territorial_authority = tq.ta_name
WHERE y.census_year = 2023
```

### Suburb hazard exposure (% of cells at risk, used for suburb-level choropleth fallback)

```sql
SELECT
  c.suburb_id,
  s.suburb_name,
  COUNT(*)                                                                        AS total_cells,
  SUM(CAST(h.in_flood_plain           AS INT))                                   AS flood_plain_cells,
  ROUND(SUM(CAST(h.in_flood_plain AS INT)) * 100.0 / COUNT(*), 1)               AS pct_flood_plain,
  SUM(CAST(h.in_coastal_inundation_100yr AS INT))                                AS coastal_100yr_cells,
  ROUND(SUM(CAST(h.in_coastal_inundation_100yr AS INT)) * 100.0 / COUNT(*), 1)  AS pct_coastal_100yr
FROM housing.gold.h3_cell c
JOIN housing.gold.hazard h USING (h3_cell)
JOIN housing.gold.suburb s USING (suburb_id)
GROUP BY c.suburb_id, s.suburb_name
ORDER BY pct_flood_plain DESC
```

### Transit stop count per suburb (for SuburbInfoPanel)

```sql
SELECT
  c.suburb_id,
  COUNT(DISTINCT t.stop_id) AS transit_stop_count
FROM housing.gold.transit_stop t
JOIN housing.gold.h3_cell c ON c.h3_cell = t.h3_cell
GROUP BY c.suburb_id
```

### Amenity counts per suburb (for SuburbInfoPanel)

```sql
SELECT
  suburb_id,
  amenity_type,
  COUNT(*) AS count
FROM housing.gold.amenity__h3
WHERE suburb_id IS NOT NULL
GROUP BY suburb_id, amenity_type
```

### Verify hazard table row counts by flag (run once to check data volume)

```sql
SELECT
  SUM(CAST(in_flood_plain AS INT))             AS flood_plain_count,
  SUM(CAST(in_flood_prone_area AS INT))        AS flood_prone_count,
  SUM(CAST(in_flood_sensitive_area AS INT))    AS flood_sensitive_count,
  SUM(CAST(in_coastal_inundation_1_aep AS INT)) AS coastal_1pct_count,
  SUM(CAST(in_coastal_inundation_100yr AS INT)) AS coastal_100yr_count,
  SUM(CAST(in_regional_flood_zone AS INT))     AS regional_count,
  COUNT(*)                                      AS total_cells
FROM housing.gold.hazard
```

---

## 16. File Changelist

### New files to create

```
client/src/components/
├── choropleth-layer.tsx      (new — Section 7.1)
├── amenity-layer.tsx         (new — Section 7.2)
├── transit-layer.tsx         (new — Section 7.3)
├── hazard-layer.tsx          (new — Section 7.4)
├── layer-control-panel.tsx   (new — Section 8)
└── map-legend.tsx            (new — Section 9)
```

### Files to modify

```
client/src/contexts/
└── MapContext.tsx             ← Add FeatureLayerState, new actions (Section 4)

client/src/components/
├── map-panel.tsx              ← Add new layers + panel + legend (Section 10)
└── elements/message.tsx       ← Extend render_map interception (Section 11)

server/src/routes/
└── map-data.ts                ← Fix broken routes + add new endpoints (Sections 6, 13)

agent_server/tools/
└── render_map.py              ← Add choropleth + feature_layers params (Section 5)

agent_server/
└── prompts.py                 ← Add feature_layers examples to MAP_SYSTEM_PROMPT (Section 5.2)
```

---

**Last updated:** 2026-05-20
