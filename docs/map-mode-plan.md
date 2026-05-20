# Map Mode — Implementation Plan

> **Purpose:** This document is the single source of truth for designing and building Map Mode in Kāinga. It covers every layer: data, backend tools, system prompt, frontend architecture, component specs, and phased delivery. Use it to plan, assign, and execute.

---

## Table of Contents

1. [Vision & Concept](#1-vision--concept)
2. [Data Inventory](#2-data-inventory)
3. [Architecture Overview](#3-architecture-overview)
4. [Communication Protocol (Agent → Map)](#4-communication-protocol-agent--map)
5. [Backend: New Tools](#5-backend-new-tools)
6. [Map Mode System Prompt](#6-map-mode-system-prompt)
7. [Frontend: Layout & Components](#7-frontend-layout--components)
8. [Map Library & Dependencies](#8-map-library--dependencies)
9. [MapContext & State Schema](#9-mapcontext--state-schema)
10. [Data Layer Specifications](#10-data-layer-specifications)
11. [Suburb Info Panel Spec](#11-suburb-info-panel-spec)
12. [Address Search Spec](#12-address-search-spec)
13. [Routing & App Integration](#13-routing--app-integration)
14. [SQL Reference Queries](#14-sql-reference-queries)
15. [Phased Delivery](#15-phased-delivery)
16. [File Changelist](#16-file-changelist)
17. [Confirmed Brainstorm Features (Post-Hackathon Roadmap)](#17-confirmed-brainstorm-features-post-hackathon-roadmap)
18. [Hackathon Scope — What to Build, What to Cut](#18-hackathon-scope--what-to-build-what-to-cut)
19. [Technical Gotchas & Research Findings](#19-technical-gotchas--research-findings)

---

## 1. Vision & Concept

### The Core Idea

Map Mode turns Kāinga from a text-based housing Q&A into a **spatial navigator**. The map occupies the full window; the chat panel sits on the right as a sidebar. As the user adds housing priorities through conversation, the map responds: it flies to relevant areas, highlights matching suburbs, overlays travel times, and layers hazard or amenity data.

The fundamental interaction loop is **cumulative filtering**:

```
User: "I commute to Auckland CBD"
→ Map highlights all 28 suburbs within 30min transit
→ Map flies to Auckland and centers on the reachable zone

User: "I need rent under $700/week"
→ Map dims suburbs that are too expensive
→ 12 suburbs remain highlighted (green)

User: "No flood risk please"
→ Map dims medium/high flood-risk suburbs
→ 8 suburbs remain highlighted

User: "I need a school nearby"
→ Map shows school icons, dims suburbs with no school
→ 5 suburbs remain, all green
→ Map flies to fit those 5 in view
```

Each answer **accumulates**. The map always shows **current survivors** — suburbs that pass every filter applied so far — without the user needing to ask "what passes all my criteria".

### Auto-Zoom Behaviour

The map is not static. It zooms and pans automatically to keep the relevant area front and centre:

**Survivor zoom (cumulative filter in progress):**
After every `render_map` call where `fit_bounds=True`, the map calls `flyToBounds` over all passing suburbs. As filters narrow the set, the camera tightens:
- 80 survivors scattered nationwide → wide NZ view
- 25 survivors in Auckland → Auckland zoom
- 8 survivors all in central Auckland → zoom in to central suburbs
- 3 survivors all south of the motorway → zoom to that corridor

Padding is always applied (60px all sides) so the outermost suburb pins are never clipped at the edge. The camera never over-zooms past zoom 14 in this mode.

**Single suburb zoom (user selects a suburb):**
When the user says "let's look at Onehunga" or clicks a suburb pin, the map calls `flyTo(centroid, zoom=14)` — street level. This is close enough to read street names and see the suburb's shape in context. Amenity icons and transit stops become meaningful at this zoom. The Resident Profile and Qualities panel in the right panel updates for this suburb simultaneously.

The intent: **the map always shows exactly as much as is relevant**. If all remaining candidates are in a 3-suburb band in Avondale, you see Avondale. If the user picks one, you see that one street layout.

### What the Map Shows

| Layer | How it looks | When shown |
|---|---|---|
| Suburb polygons | Coloured by metric, outlined | Always |
| Suburb centroids | Coloured circle pins | When zoomed out |
| Isochrone overlay | H3 hexagons coloured by travel time | After commute question |
| Transit stops | Bus/Rail/Ferry icons | When toggled or suburb selected |
| Amenities | Icons by category | When toggled or suburb selected |
| Selected suburb | Pulsing outline, info panel opens | On click or agent focus |

### The Right Panel

The right panel has two fixed sections above the chat. Both describe **the suburb** — its demographic and amenity character. These are not the user's profile; they are the suburb's facts as drawn from census, amenity, transit, and hazard data.

```
┌───────────────────────────┐
│  RESIDENT PROFILE         │  ← Describes the suburb's population
│  ─────────────────────    │
│  Pop: 4,200 · Age: 34     │  (census: who lives there)
│  Renters: 62% · Own: 38%  │
│  Rent: $680/wk            │
│  Income: $72,000/yr       │
│  Crowded: 8%              │
├───────────────────────────┤
│  QUALITIES                │  ← Describes the suburb's amenities/risks
│  ─────────────────────    │
│  🏪 4 supermarkets        │  (what the suburb has)
│  🏫 3 schools (nearest 0.4km) │
│  🚌 12 transit stops      │
│  🌊 Flood: medium         │
│  🏝️ Coastal: low          │
│  Affordability: moderate  │
├───────────────────────────┤
│  CHAT                     │  ← User communicates only via natural language
│  [messages...]            │
│  ─────────────────────    │
│  [Input: Add a priority…] │
└───────────────────────────┘
```

The user never fills in the Resident Profile or Qualities panels — those populate automatically from data when a suburb is focused. The user's only input surface is the chat text field.

---

## 2. Data Inventory

All data lives in `housing.gold` on Databricks. Queried by both the agent (via SQL Warehouse) and the Express backend (same SDK, for non-agent requests like suburb profile lookups).

### 2.1 suburb

The master spatial table. 2,379 suburbs (Stats NZ SA2 2023).

| Column | Type | Notes |
|---|---|---|
| `suburb_id` | string | Stats NZ SA2 code (6 digits). PK. |
| `suburb_name` | string | Official SA2 name |
| `territorial_authority` | string | e.g. "Auckland" |
| `region` | string | e.g. "Auckland Region" |
| `centroid_h3` | bigint | H3 res-8 cell at polygon centroid |
| `geometry` | binary | SA2 polygon as WKB |
| `population_2023` | int | Total population |
| `median_age_2023` | double | |
| `median_household_income_2023` | double | |
| `household_count_2023` | int | |
| `owner_occupier_pct_2023` | double | |
| `median_weekly_rent_2023` | double | |
| `percent_crowded_2023` | double | |

**Map use:** Polygon boundaries (`geometry` decoded to GeoJSON), centroids from `h3_centerasgeojson(centroid_h3)`.

### 2.2 suburb__year

Full census demographics per suburb. Used for the Resident Profile panel.

Key columns beyond `suburb`:
- `tenure_owned`, `tenure_not_owned`, `tenure_total_stated` → renter/owner split
- `median_household_income`
- `median_weekly_rent`, `renting_households_total`
- `owner_occupier_pct`
- `percent_crowded`
- `total_victimisations_2023`
- `households_total`

### 2.3 amenity__h3

~18,831 amenities from OpenStreetMap.

| `amenity_type` | Count |
|---|---|
| park | 11,619 |
| school | 2,463 |
| early_childhood | 2,045 |
| gp_clinic | 890 |
| supermarket | 746 |
| pharmacy | 506 |
| library | 324 |
| hospital | 238 |

Columns: `osm_id`, `amenity_type`, `name`, `lat`, `lon`, `h3_cell`, `suburb_id`.

**Map use:** Togglable icon layers by amenity_type. Also aggregated per suburb for Qualities panel (counts + nearest distance).

### 2.4 transit_stop

~13,239 transit stops from GTFS feeds.

| Feed | Count |
|---|---|
| auckland_transport | 6,455 |
| metlink (Wellington) | 3,148 |
| metroinfo (Christchurch) | 2,064 |
| busit (Hamilton/Waikato) | 1,572 |

Columns: `feed_source`, `stop_id`, `stop_name`, `stop_code`, `stop_lat`, `stop_lon`, `h3_cell`.

**Map use:** Marker icons (bus/rail/ferry) with clustering. Joined to `transit_route` via GTFS stop_times (not in gold schema — route type can be inferred from feed_source or stop naming).

### 2.5 transit_route

GTFS routes. Columns: `route_type` (0=tram, 1=subway, 2=rail, 3=bus, 4=ferry), `route_type_label`, `route_short_name`, `route_long_name`, `agency_name`.

**Map use:** Icon style per stop (bus vs rail vs ferry).

### 2.6 isochrone

Travel time data as H3 cell pairs.

| Column | Type | Notes |
|---|---|---|
| `origin_h3` | bigint | H3 res-8 origin cell |
| `destination_h3` | bigint | H3 res-8 destination cell |
| `mode` | string | Currently "transit" only |
| `travel_minutes` | bigint | Travel time in minutes |
| `feed_source` | string | GTFS feed used |
| `service_date` | date | Schedule date |
| `computation_version` | string | "r5py-v2" |

**Map use:** For a given origin suburb, query all destination H3 cells with their `travel_minutes`. Return as `{h3_cell_index, travel_minutes}` pairs. Frontend uses `h3-js` to compute hexagon boundaries, colours by time band.

Travel time colour bands:
- 0–15 min → `#22c55e` (green)
- 15–30 min → `#eab308` (yellow)
- 30–45 min → `#f97316` (orange)
- 45–60 min → `#ef4444` (red)
- 60+ min → excluded (too far)

### 2.7 hazard

Flood and coastal risk per H3 cell. Columns: `in_flood_plain`, `in_flood_prone_area`, `in_flood_sensitive_area`, `in_coastal_inundation_1_aep`, `in_coastal_inundation_100yr`, `in_regional_flood_zone`, `hazard_sources`.

**Map use:** Suburb-level risk via `lookup_hazards` tool (already built). Can also overlay raw H3 hazard cells.

### 2.8 nz_address

2,402,786 addresses from LINZ. Columns: `full_address`, `suburb_locality`, `town_city`, `territorial_authority`, `latitude`, `longitude`, `h3_cell`.

**Map use:** Address search. User types an address → backend searches this table → map flies to that point, resolves to containing suburb.

### 2.9 ta__month

Monthly TA-level rent trends. Used for time-series in info panel or planner queries.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + Vite)                                            │
│                                                                     │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐ │
│  │         MAP PANEL            │  │       RIGHT PANEL            │ │
│  │  (react-leaflet)             │  │                              │ │
│  │  ┌──────────────────────┐    │  │  SuburbInfoPanel             │ │
│  │  │  SuburbLayer         │    │  │  ├─ ResidentProfile          │ │
│  │  │  IsochroneLayer      │    │  │  └─ Qualities                │ │
│  │  │  TransitLayer        │    │  │                              │ │
│  │  │  AmenityLayer        │    │  │  ChatPanel                   │ │
│  │  │  AddressMarker       │    │  │  └─ existing chat UI         │ │
│  │  └──────────────────────┘    │  │                              │ │
│  │  MapControls (layer toggle)   │  │  ChatInput                   │ │
│  └──────────────────────────────┘  └──────────────────────────────┘ │
│                          ↑                  ↑                        │
│                    MapContext         DataStreamProvider              │
│                (global map state)    (intercepts tool outputs)       │
└─────────────────────────────────────────────────────────────────────┘
         ↕ HTTP (chat stream)              ↕ REST (suburb profiles)
┌─────────────────────────────────────────────────────────────────────┐
│  BACKEND (Express + FastAPI)                                        │
│                                                                     │
│  Express routes:                                                    │
│  ├─ /api/suburb/:name/profile  → SuburbProfile + Qualities          │
│  ├─ /api/suburb/:name/isochrone → H3 cells + travel_minutes        │
│  └─ /api/address/search?q=     → Address lat/lon from nz_address    │
│                                                                     │
│  Agent (LangGraph):                                                 │
│  ├─ render_map (NEW)           → updates map via tool output stream  │
│  ├─ compute_isochrone (existing) → now also triggers render_map     │
│  ├─ score_affordability (existing)                                  │
│  ├─ lookup_hazards (existing)                                       │
│  └─ suggest_saved_search / render_visualization (existing)         │
└─────────────────────────────────────────────────────────────────────┘
         ↕ Databricks SQL Warehouse (f21913d784edd9ad)
┌─────────────────────────────────────────────────────────────────────┐
│  housing.gold (Databricks Delta Lake)                               │
│  suburb · suburb__year · amenity__h3 · transit_stop · transit_route │
│  isochrone · hazard · h3_cell · nz_address · ta__month             │
└─────────────────────────────────────────────────────────────────────┘
```

### Mode Separation

Map Mode is a **separate route** from the existing chat. The app has:
- `/` and `/chat/:id` — existing chat mode (unchanged)
- `/map` and `/map/:id` — new Map Mode

Map Mode has its own:
- Layout (`MapChatLayout`)
- Page (`MapChatPage`)
- System prompt (`MAP_SYSTEM_PROMPT`)
- Agent server route (different `system_prompt` param, or separate agent config)

The backend agent logic stays in the same `agent.py` file; we add the `render_map` tool and extend the system prompt handling.

---

## 4. Communication Protocol (Agent → Map)

### How Tool Outputs Reach the Frontend

The existing pattern (established by `render_visualization` and `suggest_saved_search`):

1. Agent calls a Python `@tool` function
2. The tool is part of the LangGraph tool call stream
3. Vercel AI SDK streams the tool call as a `dynamic-tool` message part
4. `message.tsx` intercepts specific `toolName` values and renders custom UI instead of the generic tool card

For Map Mode, we add a **new intercept** in `message.tsx` for `toolName === 'render_map'`. Instead of rendering any visible UI in the chat, it **dispatches to MapContext** to update the map.

### render_map Tool Output Schema

```typescript
interface RenderMapInput {
  action: 'fly_to' | 'highlight_suburbs' | 'show_isochrone' | 'clear_filters' | 'full_update';
  
  // Suburb data (for highlight_suburbs, full_update)
  suburbs?: Array<{
    suburb_name: string;
    lat: number;
    lon: number;
    affordability_band?: 'affordable' | 'moderate stress' | 'housing stressed';
    hazard_overall?: 'low' | 'medium' | 'high';
    median_rent_weekly?: number;
    commute_minutes?: number;
    passes_all_filters: boolean;  // true = highlighted, false = greyed out
  }>;
  
  // Map view
  center?: { lat: number; lon: number };
  zoom?: number;
  fit_bounds?: boolean;  // if true, auto-fit to show all suburbs
  
  // Isochrone (for show_isochrone)
  isochrone_origin?: string;       // suburb name
  isochrone_minutes?: number;      // travel time limit shown
  
  // Layer visibility
  show_transit?: boolean;
  amenity_types?: string[];        // [] = hide all, ['school', 'supermarket'] = show those
  
  // Color mode (what suburb colour encodes)
  color_by?: 'affordability' | 'hazard' | 'commute' | 'none';
  
  // Summary for narration (shown in chat, not on map)
  summary?: string;
}
```

The backend `render_map` tool returns this as its output dict. The frontend intercepts `toolName === 'render_map'` and reads `input` (the tool's arguments, available before execution completes) to update the map.

**Why read `input` not `output`:** Tool `input` is available when `state === 'input-available'` (before the backend has processed). Since `render_map` just constructs data and returns immediately, we can update the map as soon as the tool is called, without waiting for a roundtrip. This mirrors how `render_visualization` reads from `vizInput` (the tool input).

---

## 5. Backend: New Tools

### 5.1 render_map

**File:** `agent_server/tools/render_map.py`

This is the primary agent→map communication tool. The agent calls it after computing isochrones, scoring affordability, and looking up hazards.

```python
from langchain_core.tools import tool
from agent_server.tools.utils import execute_statement, resolve_suburb_fuzzy, CATALOG, SCHEMA
import json

@tool
def render_map(
    action: str,
    suburb_names: list[str] = [],
    color_by: str = "affordability",
    passes_filter_list: list[str] = [],
    fly_to_suburb: str = "",
    fit_bounds: bool = True,
    commute_origin: str = "",
    commute_minutes: int = 30,
    show_transit: bool = False,
    amenity_types: list[str] = [],
) -> dict:
    """
    Update the map panel. Call this after EVERY spatial result to keep the map in sync.

    Call after compute_isochrone to show the reachable suburbs.
    Call after score_affordability to colour suburbs by affordability band.
    Call after lookup_hazards to colour suburbs by risk level.
    Call when the user mentions a suburb by name to fly to it.

    Args:
        action: One of:
            "fly_to"           - fly to a specific suburb, no layer change
            "highlight_suburbs" - update the highlighted suburb set
            "show_isochrone"   - fetch and display H3 travel-time cells from commute_origin
            "full_update"      - update everything at once (preferred)
            "clear_filters"    - reset all highlights
        suburb_names: All suburbs in the current candidate set (both passing and failing).
        color_by: What suburb colour encodes: "affordability", "hazard", or "none".
        passes_filter_list: Subset of suburb_names that pass ALL active filters.
                            Suburbs in suburb_names but NOT here are shown greyed out.
                            If empty and suburb_names is non-empty, all suburbs pass.
        fly_to_suburb: Suburb to centre the map on. Leave empty to auto-fit.
        fit_bounds: If True, map zooms to contain all highlighted suburbs.
        commute_origin: Origin suburb for isochrone overlay. Empty = don't show isochrone.
        commute_minutes: Max travel time for the isochrone display.
        show_transit: Whether to show transit stop icons.
        amenity_types: List of amenity types to show icons for.
                       Valid: "supermarket", "school", "early_childhood", "gp_clinic",
                              "pharmacy", "library", "hospital", "park".

    Returns:
        Structured map update payload consumed by the frontend MapContext.
    """
    result = {
        "action": action,
        "color_by": color_by,
        "show_transit": show_transit,
        "amenity_types": amenity_types,
        "fit_bounds": fit_bounds,
    }

    # Resolve suburb coordinates
    if suburb_names:
        suburb_data = _get_suburb_centroids_with_metadata(suburb_names, color_by)
        # Mark which ones pass the filter
        passing_set = set(passes_filter_list) if passes_filter_list else set(suburb_names)
        for s in suburb_data:
            s["passes_all_filters"] = s["suburb_name"] in passing_set
        result["suburbs"] = suburb_data

    # Fly-to coordinates
    if fly_to_suburb:
        coords = _get_suburb_centroid(fly_to_suburb)
        if coords:
            result["center"] = coords
            result["zoom"] = 12 if not fit_bounds else None

    # Isochrone
    if commute_origin and action in ("show_isochrone", "full_update"):
        result["isochrone_origin"] = commute_origin
        result["isochrone_minutes"] = commute_minutes

    return result


def _get_suburb_centroids_with_metadata(suburb_names: list[str], color_by: str) -> list[dict]:
    """Query lat/lon centroids and relevant metadata for a list of suburb names."""
    if not suburb_names:
        return []

    # Build IN clause
    placeholders = ", ".join(f":sn{i}" for i in range(len(suburb_names)))
    params = [{"name": f"sn{i}", "value": v, "type": "STRING"} for i, v in enumerate(suburb_names)]

    rows = execute_statement(
        f"""
        SELECT
            s.suburb_name,
            h3_centerasgeojson(s.centroid_h3) AS centroid_geojson,
            sy.median_weekly_rent,
            sy.owner_occupier_pct,
            s.population_2023
        FROM {CATALOG}.{SCHEMA}.suburb s
        LEFT JOIN {CATALOG}.{SCHEMA}.suburb__year sy
            ON s.suburb_id = sy.suburb_id
            AND sy.census_year = (SELECT MAX(census_year) FROM {CATALOG}.{SCHEMA}.suburb__year)
        WHERE s.suburb_name IN ({placeholders})
        """,
        params,
    )

    result = []
    for row in rows:
        if not row[1]:
            continue
        try:
            coords = json.loads(row[1])["coordinates"]
        except Exception:
            continue
        result.append({
            "suburb_name": row[0],
            "lat": coords[1],
            "lon": coords[0],
            "median_rent_weekly": int(row[2]) if row[2] else None,
            "owner_occupier_pct": float(row[3]) if row[3] else None,
        })
    return result


def _get_suburb_centroid(suburb_name: str) -> dict | None:
    rows = resolve_suburb_fuzzy(suburb_name)
    if not rows:
        return None
    rows2 = execute_statement(
        f"""
        SELECT h3_centerasgeojson(centroid_h3)
        FROM {CATALOG}.{SCHEMA}.suburb
        WHERE suburb_id = :sid
        """,
        [{"name": "sid", "value": rows[0][0], "type": "STRING"}],
    )
    if not rows2 or not rows2[0][0]:
        return None
    try:
        coords = json.loads(rows2[0][0])["coordinates"]
        return {"lat": coords[1], "lon": coords[0]}
    except Exception:
        return None
```

### 5.2 get_suburb_profile (Express API, not agent tool)

This is an **Express REST endpoint** (not a LangGraph tool) because it's called by the frontend directly when a user clicks a suburb — not by the agent.

**File:** `server/src/routes/suburb.ts`

```typescript
// GET /api/suburb/:name/profile
// Returns: ResidentProfile + Qualities data for the info panel
```

The endpoint queries:
- `suburb__year` for demographics (income, tenure, rent, crowding)
- `amenity__h3` for amenity counts and nearest amenity by type
- Nearest transit stop count (from `transit_stop` via H3 join)
- `hazard` for flood/coastal risk summary (re-uses `lookup_hazards` logic)

Response shape:

```typescript
interface SuburbProfileResponse {
  suburb_name: string;
  territorial_authority: string;
  
  // Resident Profile
  population: number;
  median_age: number;
  renter_pct: number;       // tenure_not_owned / tenure_total_stated
  owner_pct: number;        // owner_occupier_pct
  median_rent_weekly: number;
  median_household_income: number;
  percent_crowded: number;
  total_victimisations_2023: number | null;
  
  // Qualities
  amenities: {
    supermarket: number;
    school: number;
    early_childhood: number;
    gp_clinic: number;
    pharmacy: number;
    library: number;
    hospital: number;
    park: number;
    nearest_school_km: number | null;
    nearest_supermarket_km: number | null;
  };
  transit_stop_count: number;
  flood_risk: 'low' | 'medium' | 'high';
  coastal_risk: 'low' | 'medium' | 'high';
  overall_risk: 'low' | 'medium' | 'high';
  
  // Affordability (from ta__month for currency)
  affordability_band: 'affordable' | 'moderate stress' | 'housing stressed' | null;
}
```

### 5.3 get_isochrone_cells (Express API)

**File:** `server/src/routes/suburb.ts` (same file, additional route)

```
GET /api/suburb/:name/isochrone?minutes=30
```

Returns H3 cell indices with travel times:

```typescript
interface IsochroneResponse {
  origin_suburb: string;
  mode: string;
  minutes: number;
  cells: Array<{
    h3_index: string;  // hex string of bigint, e.g. "88283082a9fffff"
    travel_minutes: number;
  }>;
}
```

The frontend uses `h3-js` to compute hex boundaries from `h3_index`, then renders as GeoJSON polygons coloured by `travel_minutes`.

SQL:

```sql
SELECT DISTINCT
    CAST(iso.destination_h3 AS STRING) AS h3_index,
    MIN(iso.travel_minutes) AS travel_minutes
FROM housing.gold.h3_cell origin_hc
JOIN housing.gold.isochrone iso ON origin_hc.h3_cell = iso.origin_h3
WHERE origin_hc.suburb_id IN (
    SELECT suburb_id FROM housing.gold.suburb WHERE suburb_name ILIKE :origin
)
  AND iso.mode = 'transit'
  AND iso.travel_minutes <= :minutes
  AND iso.computation_version = 'r5py-v2'
GROUP BY iso.destination_h3
ORDER BY travel_minutes
```

### 5.4 address search (Express API)

**File:** `server/src/routes/address.ts`

```
GET /api/address/search?q=123+Queen+Street+Auckland
```

Queries `nz_address` with ILIKE, returns top 5 matches with lat/lon:

```typescript
interface AddressSearchResult {
  address_id: string;
  full_address: string;
  suburb_locality: string;
  town_city: string;
  territorial_authority: string;
  latitude: number;
  longitude: number;
}
```

---

## 6. Map Mode System Prompt

Map Mode uses a **completely separate system prompt** from the existing Kāinga chat prompt. The agent in Map Mode thinks spatially first and always closes each turn with a `render_map` call.

### Key Differences from the Existing Prompt

| Dimension | Chat Mode (existing) | Map Mode |
|---|---|---|
| Primary output | Text recommendations | Map update + narration |
| Visualization tool | `render_visualization` (Mermaid) | `render_map` (live map) |
| Suburb info panel | Not applicable | `render_map` drives it |
| State model | Stateless per response | Cumulative: each filter narrows survivors |
| Tone | Conversational | Navigator: brief, spatial, action-oriented |
| Response length | 150-250 words | 40-80 words max (map does the heavy lifting) |

### The Prompt

```python
MAP_SYSTEM_PROMPT = """You are Kāinga Map — an AI navigator for NZ housing. \
You operate the interactive map on the left. The user adds housing priorities one at a time; \
your job is to narrow the map's highlighted suburbs with each new constraint.

**Always call get_user_memory at the start of every conversation** before asking questions.

---

## Your job in Map Mode

You are a navigator. The map is the primary output. Text is short narration explaining \
what changed on the map. Each message narrows the suburb set:

1. User adds a priority → you call the tools to evaluate it → you call render_map \
   with the current surviving suburbs + the colour mode that best shows the new constraint.
2. Suburbs that pass ALL active filters are shown in full colour (green/amber/red by metric).
3. Suburbs that fail any filter are shown in grey.
4. Always fit the map bounds to contain the passing suburbs unless the user is zooming in.

---

## Tool usage in Map Mode

**compute_isochrone(suburb_name, mode, minutes)**
Use when a commute origin is mentioned. Returns reachable suburbs. \
Then call render_map with action="full_update", suburb_names=all reachable suburbs, \
passes_filter_list=same list, color_by="none" (no filter applied yet beyond reachability), \
commute_origin=the origin suburb.

**score_affordability(suburb_name, household_income)**
Use to get rent data for each passing suburb. \
You MAY call this for up to 10 suburbs individually. \
For larger sets, use the Genie ask tool for bulk rent data first, then score the survivors.
After scoring, call render_map with color_by="affordability", \
passes_filter_list=suburbs that are within budget.

**lookup_hazards(suburb_name)**
Use to check flood/coastal risk for the passing suburbs (not all suburbs). \
After checking, call render_map with color_by="hazard", \
passes_filter_list=suburbs with acceptable risk level.

**render_map(action, suburb_names, passes_filter_list, color_by, ...)**
ALWAYS call at the end of every response that involves spatial data. \
This updates the map — your text narration is secondary.

Rules:
- suburb_names = the full current candidate set (all suburbs being tracked)
- passes_filter_list = the subset that currently passes every active filter
- If a filter ADDS to the criteria, keep the previous passing list and filter further
- If the user REMOVES a constraint ("forget the commute"), recompute from scratch
- fit_bounds=True unless user is drilling into a single suburb

**suggest_saved_search(suburb_name, ...)**
Same as chat mode: call once per concrete recommendation with full data.

**get_user_memory / save_user_memory**
Same as chat mode.

---

## Cumulative filter state

You maintain this across the conversation (via checkpointer memory):
- commute_origin + mode + minutes (set when user mentions commute)
- max_rent_weekly (set when user mentions budget)
- affordability_band (set when user mentions affordability preference)  
- hazard_max: "low" | "medium" | "high" (set when user mentions flood/safety)
- required_amenities: list[str] (set when user mentions needing a school, GP, etc.)
- location_preference: suburb or TA the user wants to be near

Each new filter intersects with all previous filters. \
passes_filter_list is always the intersection of all active filters.

---

## Example 1 — First commute constraint

User: "I work in Auckland CBD and commute by train, about 30 minutes"

Your steps:
1. get_user_memory("commute budget constraints")
2. compute_isochrone("Auckland CBD", "transit", 30)
   → returns ~25 suburbs
3. render_map(
       action="full_update",
       suburb_names=[all 25 suburbs],
       passes_filter_list=[all 25 suburbs],  # no budget filter yet
       color_by="none",
       commute_origin="Auckland CBD",
       commute_minutes=30,
       fit_bounds=True
   )
4. save_user_memory("constraints", {"commute_origin": "Auckland CBD", "mode": "transit", "minutes": 30})

Your text (under 60 words):
"25 suburbs are within 30 minutes by train from Auckland CBD — shown on the map. \
Closest are Newmarket, Parnell, and Grafton. What matters most to you next: \
rent budget, flood safety, or schools?"

---

## Example 2 — Adding a rent filter

User: "I need to keep rent under $650/week"

Your steps:
1. Take the current passing suburbs from memory (the 25 from the isochrone).
2. For suburbs ≤ 10: call score_affordability on each.
   For > 10: call Genie ask tool: "Give me median weekly rent for [suburb list]. \
   Which are under $650/week? Order by rent ascending."
3. passing = [suburbs with median rent ≤ 650]
4. render_map(
       action="full_update",
       suburb_names=[all 25 suburbs],
       passes_filter_list=passing,   # only affordable ones highlighted
       color_by="affordability",
       commute_origin="Auckland CBD",
       commute_minutes=30,
       fit_bounds=True
   )
5. save_user_memory("constraints", {... add "max_rent_weekly": 650})

Your text (under 60 words):
"8 of those 25 suburbs have median rent under $650/week — highlighted in green. \
Avondale ($610/wk), Onehunga ($630/wk), and Otahuhu ($590/wk) lead on price. \
The grey suburbs are too expensive. Want me to check flood risk on these 8?"

---

## Example 3 — Clicking a suburb

User: "Tell me about Onehunga"

Your steps:
1. score_affordability("Onehunga")
2. lookup_hazards("Onehunga")
3. render_map(
       action="fly_to",
       fly_to_suburb="Onehunga",
       suburb_names=[current candidate set, unchanged],
       passes_filter_list=[current passing set, unchanged],
       color_by=[current color_by],
       show_transit=True,
       amenity_types=["supermarket", "school", "gp_clinic"]
   )

Your text (under 80 words):
"Onehunga: $630/wk median rent, 22 min to Auckland CBD by train. \
Medium flood risk on the southern fringe near the harbour, \
but the main residential area is low risk. \
4 supermarkets, 3 schools, 2 GP clinics within 1km. \
Strong transit access — 3 train stations plus frequent buses. \
Want to save Onehunga or look at its neighbours?"

---

## Output format rules in Map Mode

1. **Lead with what changed on the map**, not the reasoning.
2. **Max 80 words** per response. The map shows the detail; text narrates it.
3. Do NOT list all suburbs in text — the map shows them. Name only the top 2-3.
4. Always end with ONE concrete next question or offer.
5. If a tool returns an error (suburb not found, no data), say so in one sentence.
6. Do NOT call render_visualization (Mermaid) — the map replaces it.
7. Do NOT use markdown tables — too verbose for a side panel.

---

## Memory rules

Same as chat mode. Save commute, budget, hazard preference, and required amenities \
after any turn where they first appear or change.
"""
```

---

## 7. Frontend: Layout & Components

### 7.1 Overall Layout

Map Mode uses a new layout file and page. The main container is a horizontal split:

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Kāinga logo · Map Mode]  ←← header (48px fixed) ←←  [Layers ▾] │
├──────────────────────────────┬───────────────────────────────────────┤
│                              │                                       │
│                              │  ┌───────────────────────────────┐   │
│                              │  │  SuburbInfoPanel               │   │
│                              │  │  (ResidentProfile + Qualities) │   │
│      LeafletMap              │  │  Fixed height: 320px           │   │
│   (fill remaining height)    │  └───────────────────────────────┘   │
│                              │                                       │
│                              │  ChatMessages                         │
│                              │  (fills remaining height,             │
│                              │   scroll inside)                      │
│                              │                                       │
│                              │  ──────────────────────────────────── │
│                              │  ChatInput (fixed bottom, 64px)       │
└──────────────────────────────┴───────────────────────────────────────┘
  65% width                        35% width
```

The map occupies 65% of viewport width, full height minus header.
The right panel occupies 35%, with SuburbInfoPanel fixed at top, chat below.

No resizable drag handle (YAGNI). Fixed split.

### 7.2 File Structure

New files to create:

```
client/src/
├── contexts/
│   └── MapContext.tsx              # MapState + dispatch
├── hooks/
│   ├── use-map-state.ts            # MapContext consumer
│   └── use-suburb-profile.ts      # SWR hook for /api/suburb/:name/profile
├── layouts/
│   └── MapChatLayout.tsx           # New layout: map + right panel
├── pages/
│   └── MapChatPage.tsx             # Route /map/:id
├── components/
│   └── map/
│       ├── MapPanel.tsx            # Leaflet map container + all layers
│       ├── SuburbLayer.tsx         # GeoJSON layer for suburb polygons
│       ├── IsochroneLayer.tsx      # H3 hexagon GeoJSON layer
│       ├── TransitLayer.tsx        # Transit stop markers with clustering
│       ├── AmenityLayer.tsx        # Amenity icon markers
│       ├── AddressSearch.tsx       # Address search input (top-left of map)
│       ├── MapControls.tsx         # Layer toggle buttons (top-right of map)
│       ├── SuburbInfoPanel.tsx     # Right panel top: profile + qualities
│       └── MapLegend.tsx           # Colour legend (bottom-left of map)
```

Files to modify:

```
client/src/
├── App.tsx                         # Add /map route
├── components/message.tsx          # Add render_map tool interception
└── components/app-sidebar.tsx      # Add Map Mode link
```

Backend new files:

```
agent_server/tools/
└── render_map.py                   # New agent tool

server/src/routes/
├── suburb.ts                       # /api/suburb/:name/profile + /isochrone
└── address.ts                      # /api/address/search

agent_server/
└── prompts.py                      # Add MAP_SYSTEM_PROMPT constant
```

### 7.3 MapContext

```typescript
// client/src/contexts/MapContext.tsx

export interface SuburbFeature {
  suburb_name: string;
  lat: number;
  lon: number;
  passes_all_filters: boolean;
  affordability_band?: 'affordable' | 'moderate stress' | 'housing stressed';
  hazard_overall?: 'low' | 'medium' | 'high';
  median_rent_weekly?: number;
  commute_minutes?: number;
}

export interface IsochroneCell {
  h3_index: string;      // bigint as hex string: "88283082a9fffff"
  travel_minutes: number;
}

export type ColorMode = 'affordability' | 'hazard' | 'commute' | 'none';

export interface MapState {
  // View
  center: [number, number];         // [lat, lon]
  zoom: number;
  fitBoundsTo: SuburbFeature[] | null;  // non-null triggers flyToBounds

  // Suburb layer
  suburbs: SuburbFeature[];
  colorMode: ColorMode;

  // Isochrone layer
  isochroneOrigin: string | null;   // suburb name, triggers /api/isochrone fetch
  isochroneMinutes: number;
  isochroneCells: IsochroneCell[];  // populated after fetch

  // Other layers
  showTransit: boolean;
  activeAmenityTypes: string[];

  // Selected suburb (for info panel)
  selectedSuburb: string | null;
}

export type MapAction =
  | { type: 'RENDER_MAP'; payload: RenderMapInput }       // from agent tool
  | { type: 'SELECT_SUBURB'; suburb: string | null }      // from map click
  | { type: 'TOGGLE_TRANSIT' }
  | { type: 'TOGGLE_AMENITY'; amenityType: string }
  | { type: 'SET_ISOCHRONE_CELLS'; cells: IsochroneCell[] }  // after API fetch
  | { type: 'CLEAR' };

export const initialMapState: MapState = {
  center: [-36.8509, 174.7645],  // Auckland CBD default
  zoom: 11,
  fitBoundsTo: null,
  suburbs: [],
  colorMode: 'none',
  isochroneOrigin: null,
  isochroneMinutes: 30,
  isochroneCells: [],
  showTransit: false,
  activeAmenityTypes: [],
  selectedSuburb: null,
};
```

### 7.4 MapPanel Component

```typescript
// client/src/components/map/MapPanel.tsx

import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import { useMapState } from '@/hooks/use-map-state';
import SuburbLayer from './SuburbLayer';
import IsochroneLayer from './IsochroneLayer';
import TransitLayer from './TransitLayer';
import AmenityLayer from './AmenityLayer';
import AddressSearch from './AddressSearch';
import MapControls from './MapControls';
import MapLegend from './MapLegend';
import FlyToController from './FlyToController';

export function MapPanel() {
  const { mapState } = useMapState();

  return (
    <MapContainer
      center={mapState.center}
      zoom={mapState.zoom}
      style={{ height: '100%', width: '100%' }}
      zoomControl={false}
    >
      {/* Free OSM tiles via OpenFreeMap */}
      <TileLayer
        url="https://tiles.openfreemap.org/styles/liberty/{z}/{x}/{y}.png"
        attribution='© <a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        maxZoom={18}
      />

      {/* Data layers */}
      <SuburbLayer />
      {mapState.isochroneCells.length > 0 && <IsochroneLayer />}
      {mapState.showTransit && <TransitLayer />}
      {mapState.activeAmenityTypes.length > 0 && <AmenityLayer />}

      {/* Controls (outside map data) */}
      <AddressSearch />    {/* top-left */}
      <MapControls />      {/* top-right */}
      <MapLegend />        {/* bottom-left */}

      {/* Imperative map control (flyTo, fitBounds) */}
      <FlyToController />
    </MapContainer>
  );
}
```

**Tile provider:** [OpenFreeMap](https://openfreemap.org) — free, no API key, uses OSM data, good quality. Fallback: standard OSM `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.

### 7.5 SuburbLayer

Renders suburb polygons from WKB geometry OR centroid pins, depending on data availability and zoom level.

**Two modes:**
1. **Centroid pins** (default) — coloured circle markers. Fast, no WKB decoding needed.
2. **Polygon mode** (when user has drilled in, zoom ≥ 12) — GeoJSON polygons fetched from `/api/suburb/:name/geometry` endpoint.

**For Phase 1, use centroid pins only.** Polygon rendering adds complexity; centroid pins are already spatially accurate.

Colour logic:

```typescript
function getSuburbColor(suburb: SuburbFeature, colorMode: ColorMode): string {
  if (!suburb.passes_all_filters) return '#94a3b8';  // slate-400 = greyed out

  switch (colorMode) {
    case 'affordability':
      return { affordable: '#22c55e', 'moderate stress': '#f59e0b', 'housing stressed': '#ef4444' }
        [suburb.affordability_band ?? 'none'] ?? '#6366f1';
    case 'hazard':
      return { low: '#22c55e', medium: '#f59e0b', high: '#ef4444' }
        [suburb.hazard_overall ?? 'none'] ?? '#6366f1';
    case 'commute':
      if (!suburb.commute_minutes) return '#6366f1';
      if (suburb.commute_minutes <= 15) return '#22c55e';
      if (suburb.commute_minutes <= 30) return '#86efac';
      if (suburb.commute_minutes <= 45) return '#fde68a';
      return '#fca5a5';
    default:
      return '#6366f1';  // indigo = "in candidate set"
  }
}
```

### 7.6 IsochroneLayer

Fetches H3 cells from `/api/suburb/:name/isochrone?minutes=N` and renders as hexagons using `h3-js`.

```typescript
// IsochroneLayer.tsx
import { cellToBoundary } from 'h3-js';
import { GeoJSON } from 'react-leaflet';
import { useMapState } from '@/hooks/use-map-state';
import useSWR from 'swr';

export function IsochroneLayer() {
  const { mapState, dispatch } = useMapState();
  const { isochroneOrigin, isochroneMinutes } = mapState;

  const { data } = useSWR(
    isochroneOrigin ? `/api/suburb/${encodeURIComponent(isochroneOrigin)}/isochrone?minutes=${isochroneMinutes}` : null,
    fetcher,
  );

  // Convert H3 cells to GeoJSON
  const geojson = useMemo(() => {
    if (!data?.cells) return null;
    return {
      type: 'FeatureCollection',
      features: data.cells.map((cell: IsochroneCell) => {
        const boundary = cellToBoundary(cell.h3_index, true);  // true = GeoJSON order [lon, lat]
        return {
          type: 'Feature',
          properties: { travel_minutes: cell.travel_minutes },
          geometry: { type: 'Polygon', coordinates: [boundary] },
        };
      }),
    };
  }, [data]);

  if (!geojson) return null;

  return (
    <GeoJSON
      data={geojson}
      style={(feature) => ({
        fillColor: travelTimeColor(feature?.properties?.travel_minutes ?? 60),
        fillOpacity: 0.35,
        color: 'transparent',
        weight: 0,
      })}
    />
  );
}

function travelTimeColor(minutes: number): string {
  if (minutes <= 15) return '#22c55e';
  if (minutes <= 30) return '#eab308';
  if (minutes <= 45) return '#f97316';
  return '#ef4444';
}
```

**Performance note:** H3 res-8 hexagons are ~0.7 km² each. A 30-min Auckland isochrone covers ~150-300 cells. This is well within Leaflet's rendering capacity.

### 7.7 TransitLayer

Fetches transit stops for the visible map bounds. Uses Leaflet marker clustering to avoid overloading at low zoom.

```typescript
// TransitLayer.tsx
// Uses react-leaflet-cluster for clustering
// Fetches: GET /api/transit-stops?bounds=lat1,lon1,lat2,lon2
```

Stop icons differ by route type:
- Bus (3) → small blue bus icon (Lucide `Bus`)
- Rail (2) → orange train icon (Lucide `Train`)
- Ferry (4) → teal anchor icon (Lucide `Anchor`)

Each stop popup shows: stop name, routes serving it, feed source.

**Performance:** 13,239 total stops nationwide. Fetching by visible bounds keeps it manageable. Cluster at zoom < 13.

### 7.8 AmenityLayer

Similar to TransitLayer: fetches amenities for map bounds, icons by type.

Icon mapping:
- `supermarket` → `ShoppingCart` (green)
- `school` → `GraduationCap` (blue)
- `early_childhood` → `Baby` (light blue)
- `gp_clinic` → `Stethoscope` (red)
- `pharmacy` → `Pill` (orange)
- `library` → `BookOpen` (purple)
- `hospital` → `Hospital` (red, larger)
- `park` → `Trees` (green)

Fetches: `GET /api/amenities?bounds=...&types=supermarket,school`

### 7.9 SuburbInfoPanel

Sits at the top of the right panel. Shows profile for `mapState.selectedSuburb` (set on map click) or the most recently agent-focused suburb.

```typescript
// SuburbInfoPanel.tsx

interface SuburbInfoPanelProps {
  suburbName: string | null;
}

// Uses useSWR to fetch /api/suburb/:name/profile
// Shows skeleton loader while fetching
```

**Resident Profile section:**

| Field | Source |
|---|---|
| Population | `suburb__year.population_total` |
| Median age | `suburb__year.median_age` |
| Renters | `tenure_not_owned / tenure_total_stated` (%) |
| Owners | `owner_occupier_pct` (%) |
| Median rent | `suburb__year.median_weekly_rent` |
| Median income | `suburb__year.median_household_income` |
| % crowded | `suburb__year.percent_crowded` |

**Qualities section:**

| Field | Source |
|---|---|
| Supermarkets | `COUNT(*) FROM amenity__h3 WHERE suburb_id = ? AND amenity_type = 'supermarket'` |
| Schools | same pattern |
| GPs | same pattern |
| Parks | same pattern |
| Transit stops | `COUNT(*) FROM transit_stop JOIN h3_cell WHERE suburb_id = ?` |
| Flood risk | `lookup_hazards` logic |
| Coastal risk | same |

### 7.10 AddressSearch

A search box at top-left of the map. User types an address → debounced fetch → dropdown of results → selecting one flies the map to that point and resolves to the suburb.

```typescript
// AddressSearch.tsx
// Uses /api/address/search?q=...
// On select: dispatch({ type: 'SELECT_SUBURB', suburb: result.suburb_locality })
// And map.flyTo([result.latitude, result.longitude], 15)
```

### 7.11 MapControls

Positioned top-right of map. Layer toggle buttons:

```
[Transit] [Isochrone] 
[🏪 Markets] [🏫 Schools] [🏥 GPs] [🌳 Parks] [💊 Pharmacy] [📚 Library] [🏨 Hospital]
```

Each button toggles the corresponding layer in MapContext. Active buttons have a filled background.

### 7.12 MapLegend

Bottom-left of map. Shows colour key for the active `colorMode`:

- `affordability`: green=affordable, amber=moderate stress, red=stressed, grey=filtered out
- `hazard`: green=low, amber=medium, red=high, grey=filtered out
- `commute`: gradient from green (0-15 min) to red (45+ min)
- `none`: indigo=in candidate set, grey=filtered out

### 7.13 FlyToController

An invisible component that uses the Leaflet `useMap()` hook to respond to `fitBoundsTo` and `center` changes in MapState:

```typescript
function FlyToController() {
  const map = useMap();
  const { mapState } = useMapState();

  // Survivor zoom: called after each render_map with fit_bounds=True.
  // Pads 60px so outermost pins never clip at the edge.
  // maxZoom:14 prevents over-zooming when survivors collapse to a tight cluster.
  useEffect(() => {
    if (mapState.fitBoundsTo?.length) {
      const bounds = mapState.fitBoundsTo.map(s => [s.lat, s.lon] as [number, number]);
      map.flyToBounds(bounds, { padding: [60, 60], maxZoom: 14, duration: 1.2 });
    }
  }, [mapState.fitBoundsTo]);

  // Single-suburb zoom: when the user selects a suburb (via click or "let's look at X").
  // zoom=14 = street level, suburb fits in viewport with street names readable.
  useEffect(() => {
    if (mapState.center && mapState.zoomToSuburb) {
      map.flyTo(mapState.center, 14, { duration: 1.0 });
    } else if (mapState.center) {
      map.flyTo(mapState.center, mapState.zoom ?? 12, { duration: 1.0 });
    }
  }, [mapState.center, mapState.zoomToSuburb]);

  return null;
}
```

**Two distinct camera modes:**

| Trigger | Camera behaviour | Zoom |
|---|---|---|
| `render_map(fit_bounds=True, passes_filter_list=[...])` | `flyToBounds` over all passing suburbs + 60px padding | Auto, max 14 |
| `render_map(action="fly_to", fly_to_suburb="X")` | `flyTo` suburb centroid | 14 (street level) |
| User clicks suburb pin | `flyTo` suburb centroid | 14 (street level) |

The `zoomToSuburb: boolean` field is added to `MapState` (see §9). It is `true` when action is `"fly_to"` or `SELECT_SUBURB` is dispatched, and `false` otherwise.

### 7.14 message.tsx modification

Add the `render_map` interception:

```typescript
// In the tool rendering section of message.tsx:

if (toolName === 'render_map') {
  if (state === 'input-available' || state === 'output-available') {
    const mapInput = input as RenderMapInput;
    // Dispatch to MapContext — no visible UI in chat
    dispatch({ type: 'RENDER_MAP', payload: mapInput });
  }
  return null;  // render nothing in chat stream
}
```

The `dispatch` comes from `useMapDispatch()` hook (MapContext consumer).

---

## 8. Map Library & Dependencies

### Core: react-leaflet + leaflet

```bash
npm install leaflet react-leaflet --workspace=client
npm install @types/leaflet --workspace=client --save-dev
```

- `leaflet`: 1.9.x (stable)
- `react-leaflet`: 4.x

Leaflet CSS must be imported in the client entry (`index.css` or `main.tsx`):
```typescript
import 'leaflet/dist/leaflet.css';
```

Also fix the default icon path issue (Leaflet webpack quirk):
```typescript
// In MapPanel.tsx or a map-utils.ts setup file:
import L from 'leaflet';
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: '/leaflet-icons/marker-icon-2x.png',
  iconUrl: '/leaflet-icons/marker-icon.png',
  shadowUrl: '/leaflet-icons/marker-shadow.png',
});
```

Copy the three PNG files from `node_modules/leaflet/dist/images/` to `client/public/leaflet-icons/`.

### H3 Hexagon Support: h3-js

```bash
npm install h3-js --workspace=client
```

Used in `IsochroneLayer` only. Small API surface:
- `cellToBoundary(h3Index, formatAsGeoJSON)` → `[[lat,lon], ...]` or `[[lon,lat], ...]`

H3 indices come from the backend as hex strings (e.g. `"88283082a9fffff"`). The backend must `CAST(h3_cell AS BIGINT)` and then convert to hex format. Databricks SQL: `conv(cast(h3_cell as string), 10, 16)` converts bigint decimal to hex.

**Important:** H3-js expects the hex index as a string without `0x` prefix, 15 hex chars for res-8.

### Clustering: react-leaflet-cluster

```bash
npm install react-leaflet-cluster --workspace=client
```

Wraps transit stop and amenity markers into clusters at low zoom. Zero config required.

### Tile Provider

**OpenFreeMap** (https://openfreemap.org):
- Free, no API key
- Hosts OSM-derived vector tiles
- Raster tiles URL: `https://tiles.openfreemap.org/styles/liberty/{z}/{x}/{y}.png`
- Good quality, maintained

Fallback: standard OSM raster `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png` (rate-limited for production).

### No Additional Map Libraries Needed

- No Mapbox (requires API token)
- No deck.gl (overkill for this data volume)
- No turf.js (H3 boundary computation handled by h3-js)

---

## 9. MapContext & State Schema

Full TypeScript definition:

```typescript
// client/src/contexts/MapContext.tsx

import React, { createContext, useContext, useReducer, type ReactNode } from 'react';

export interface SuburbFeature {
  suburb_name: string;
  lat: number;
  lon: number;
  passes_all_filters: boolean;
  affordability_band?: 'affordable' | 'moderate stress' | 'housing stressed';
  hazard_overall?: 'low' | 'medium' | 'high';
  median_rent_weekly?: number;
  commute_minutes?: number;
}

export interface IsochroneCell {
  h3_index: string;
  travel_minutes: number;
}

export type ColorMode = 'affordability' | 'hazard' | 'commute' | 'none';

export interface MapState {
  center: [number, number];
  zoom: number;
  zoomToSuburb: boolean;       // true = flyTo centroid at zoom 14 (single suburb focus)
  fitBoundsTo: SuburbFeature[] | null;  // non-null = flyToBounds over these survivors
  suburbs: SuburbFeature[];
  colorMode: ColorMode;
  isochroneOrigin: string | null;
  isochroneMinutes: number;
  isochroneCells: IsochroneCell[];
  showTransit: boolean;
  activeAmenityTypes: string[];
  selectedSuburb: string | null;
}

// This is the shape of the render_map tool's input parameters (from agent)
export interface RenderMapInput {
  action: string;
  suburbs?: SuburbFeature[];
  center?: { lat: number; lon: number };
  zoom?: number;
  fit_bounds?: boolean;
  isochrone_origin?: string;
  isochrone_minutes?: number;
  show_transit?: boolean;
  amenity_types?: string[];
  color_by?: ColorMode;
}

export type MapAction =
  | { type: 'RENDER_MAP'; payload: RenderMapInput }
  | { type: 'SELECT_SUBURB'; suburb: string | null }
  | { type: 'TOGGLE_TRANSIT' }
  | { type: 'TOGGLE_AMENITY'; amenityType: string }
  | { type: 'SET_ISOCHRONE_CELLS'; cells: IsochroneCell[] }
  | { type: 'CLEAR' };

export const initialMapState: MapState = {
  center: [-36.8509, 174.7645],
  zoom: 11,
  zoomToSuburb: false,
  fitBoundsTo: null,
  suburbs: [],
  colorMode: 'none',
  isochroneOrigin: null,
  isochroneMinutes: 30,
  isochroneCells: [],
  showTransit: false,
  activeAmenityTypes: [],
  selectedSuburb: null,
};

function mapReducer(state: MapState, action: MapAction): MapState {
  switch (action.type) {
    case 'RENDER_MAP': {
      const p = action.payload;
      const next: MapState = { ...state, fitBoundsTo: null, zoomToSuburb: false };

      if (p.suburbs?.length) {
        next.suburbs = p.suburbs;
      }
      if (p.color_by) next.colorMode = p.color_by;
      if (p.center) next.center = [p.center.lat, p.center.lon];
      if (p.zoom) next.zoom = p.zoom;
      if (p.show_transit !== undefined) next.showTransit = p.show_transit;
      if (p.amenity_types !== undefined) next.activeAmenityTypes = p.amenity_types;

      if (p.isochrone_origin) {
        next.isochroneOrigin = p.isochrone_origin;
        next.isochroneMinutes = p.isochrone_minutes ?? 30;
        next.isochroneCells = [];  // clear stale cells; IsochroneLayer will fetch fresh
      }

      // action="fly_to" means single suburb focus → zoom to street level
      if (p.action === 'fly_to' && p.center) {
        next.zoomToSuburb = true;
        next.selectedSuburb = p.fly_to_suburb ?? state.selectedSuburb;
      }

      // fit_bounds=True → camera fits all passing suburbs
      if (p.fit_bounds !== false && p.action !== 'fly_to' && p.suburbs?.length) {
        next.fitBoundsTo = p.suburbs.filter(s => s.passes_all_filters);
      }

      return next;
    }
    case 'SELECT_SUBURB':
      return {
        ...state,
        selectedSuburb: action.suburb,
        fitBoundsTo: null,
        zoomToSuburb: !!action.suburb,  // triggers zoom=14 flyTo in FlyToController
      };
    case 'TOGGLE_TRANSIT':
      return { ...state, showTransit: !state.showTransit };
    case 'TOGGLE_AMENITY':
      return {
        ...state,
        activeAmenityTypes: state.activeAmenityTypes.includes(action.amenityType)
          ? state.activeAmenityTypes.filter(t => t !== action.amenityType)
          : [...state.activeAmenityTypes, action.amenityType],
      };
    case 'SET_ISOCHRONE_CELLS':
      return { ...state, isochroneCells: action.cells };
    case 'CLEAR':
      return { ...initialMapState };
    default:
      return state;
  }
}

interface MapContextValue {
  mapState: MapState;
  dispatch: React.Dispatch<MapAction>;
}

const MapContext = createContext<MapContextValue | null>(null);

export function MapProvider({ children }: { children: ReactNode }) {
  const [mapState, dispatch] = useReducer(mapReducer, initialMapState);
  return (
    <MapContext.Provider value={{ mapState, dispatch }}>
      {children}
    </MapContext.Provider>
  );
}

export function useMapState() {
  const ctx = useContext(MapContext);
  if (!ctx) throw new Error('useMapState must be used within MapProvider');
  return ctx;
}
```

---

## 10. Data Layer Specifications

### 10.1 Suburb centroid data flow

```
Agent calls render_map(suburb_names=[...])
    ↓
render_map.py queries:
    SELECT suburb_name, h3_centerasgeojson(centroid_h3), median_weekly_rent, owner_occupier_pct
    FROM housing.gold.suburb JOIN suburb__year
    WHERE suburb_name IN (...)
    ↓
Returns: [{suburb_name, lat, lon, median_rent_weekly, passes_all_filters}, ...]
    ↓
Tool output streamed via Vercel AI SDK
    ↓
message.tsx intercepts toolName === 'render_map'
    ↓
dispatch({ type: 'RENDER_MAP', payload: input })
    ↓
MapReducer updates mapState.suburbs
    ↓
SuburbLayer re-renders with new CircleMarkers
    ↓
FlyToController calls map.flyToBounds() if fitBoundsTo set
```

### 10.2 Isochrone data flow

```
User: "30 min commute from Henderson"
    ↓
Agent calls compute_isochrone("Henderson", "transit", 30)
    ↓
Agent calls render_map(action="full_update", commute_origin="Henderson", commute_minutes=30, ...)
    ↓
message.tsx → dispatch(RENDER_MAP) → sets mapState.isochroneOrigin = "Henderson"
    ↓
IsochroneLayer: useSWR('/api/suburb/Henderson/isochrone?minutes=30') fires
    ↓
Express route queries isochrone table, returns [{h3_index, travel_minutes}]
    ↓
IsochroneLayer: h3-js converts h3_index → GeoJSON polygon boundaries
    ↓
Leaflet GeoJSON layer renders hexagons coloured by travel_minutes band
```

### 10.3 Transit stops data flow

```
User toggles transit layer OR agent calls render_map(show_transit=True)
    ↓
mapState.showTransit = true
    ↓
TransitLayer renders, fetches:
    GET /api/transit-stops?bounds={sw_lat},{sw_lon},{ne_lat},{ne_lon}
    ↓
Express queries:
    SELECT stop_name, stop_lat, stop_lon, feed_source
    FROM housing.gold.transit_stop
    WHERE stop_lat BETWEEN :sw_lat AND :ne_lat
      AND stop_lon BETWEEN :sw_lon AND :ne_lon
    LIMIT 500
    ↓
TransitLayer renders markers with react-leaflet-cluster
    ↓
On map pan/zoom: re-fetches for new bounds
```

### 10.4 Amenity data flow

```
User asks "show me schools" OR agent calls render_map(amenity_types=["school"])
    ↓
mapState.activeAmenityTypes = ["school"]
    ↓
AmenityLayer renders, fetches:
    GET /api/amenities?bounds=...&types=school
    ↓
Express queries:
    SELECT name, lat, lon, amenity_type
    FROM housing.gold.amenity__h3
    WHERE lat BETWEEN :sw_lat AND :ne_lat
      AND lon BETWEEN :sw_lon AND :ne_lon
      AND amenity_type IN ('school')
    LIMIT 300
    ↓
Renders icon markers (GraduationCap icon for school)
```

### 10.5 Address search data flow

```
User types "14 Dominion Road Auckland"
    ↓
AddressSearch: debounce 300ms → GET /api/address/search?q=14+Dominion+Road+Auckland
    ↓
Express queries:
    SELECT full_address, suburb_locality, town_city, latitude, longitude
    FROM housing.gold.nz_address
    WHERE full_address ILIKE '%14 Dominion Road%Auckland%'
    LIMIT 5
    ↓
Dropdown shows results
    ↓
User selects → map.flyTo([lat, lon], 15)
    ↓
Dispatch SELECT_SUBURB with suburb_locality → SuburbInfoPanel updates
```

---

## 11. Suburb Info Panel Spec

### SQL for Resident Profile

```sql
-- Resident Profile query
SELECT
    sy.population_total,
    sy.median_age,
    ROUND(100.0 * sy.tenure_not_owned / NULLIF(sy.tenure_total_stated, 0), 1) AS renter_pct,
    ROUND(100.0 * sy.owner_occupier_pct, 1) AS owner_pct,
    ROUND(sy.median_weekly_rent, 0) AS median_rent_weekly,
    ROUND(sy.median_household_income, 0) AS median_household_income,
    ROUND(100.0 * sy.percent_crowded, 1) AS percent_crowded,
    sy.total_victimisations_2023,
    s.territorial_authority
FROM housing.gold.suburb s
JOIN housing.gold.suburb__year sy ON s.suburb_id = sy.suburb_id
WHERE s.suburb_name = :suburb_name
  AND sy.census_year = (SELECT MAX(census_year) FROM housing.gold.suburb__year)
LIMIT 1
```

### SQL for Qualities: Amenity Counts

```sql
-- Amenity counts per type for a suburb
SELECT amenity_type, COUNT(*) AS count
FROM housing.gold.amenity__h3
WHERE suburb_id = (
    SELECT suburb_id FROM housing.gold.suburb WHERE suburb_name = :suburb_name LIMIT 1
)
GROUP BY amenity_type
```

### SQL for Qualities: Nearest Amenity Distance

```sql
-- Nearest school to a suburb centroid (using H3 lat/lon)
SELECT
    a.name,
    a.lat,
    a.lon,
    -- Haversine approximation in SQL (returns km)
    6371 * 2 * ASIN(SQRT(
        POWER(SIN(RADIANS(a.lat - s_lat) / 2), 2) +
        COS(RADIANS(s_lat)) * COS(RADIANS(a.lat)) * POWER(SIN(RADIANS(a.lon - s_lon) / 2), 2)
    )) AS distance_km
FROM housing.gold.amenity__h3 a
CROSS JOIN (
    SELECT
        CAST(JSON_VALUE(h3_centerasgeojson(centroid_h3), '$.coordinates[1]') AS DOUBLE) AS s_lat,
        CAST(JSON_VALUE(h3_centerasgeojson(centroid_h3), '$.coordinates[0]') AS DOUBLE) AS s_lon
    FROM housing.gold.suburb WHERE suburb_name = :suburb_name
) centroid
WHERE a.amenity_type = :amenity_type
ORDER BY distance_km ASC
LIMIT 1
```

### SQL for Qualities: Transit Stop Count

```sql
SELECT COUNT(*) AS transit_stop_count
FROM housing.gold.transit_stop ts
JOIN housing.gold.h3_cell hc ON ts.h3_cell = hc.h3_cell
WHERE hc.suburb_id = (
    SELECT suburb_id FROM housing.gold.suburb WHERE suburb_name = :suburb_name LIMIT 1
)
```

### SQL for Qualities: Hazard Summary

Reuse `lookup_hazards` logic from `agent_server/tools/lookup_hazards.py`. Call it directly from the Express route via Python (or duplicate the logic in TypeScript using the Databricks Node SDK).

**Recommendation:** Add a dedicated `/api/suburb/:name/hazard` endpoint that calls the same SQL.

### Component UI

```tsx
// SuburbInfoPanel.tsx (simplified)
function SuburbInfoPanel({ suburbName }: { suburbName: string | null }) {
  const { data, isLoading } = useSuburbProfile(suburbName);

  if (!suburbName) return <EmptyState message="Click a suburb on the map" />;
  if (isLoading) return <ProfileSkeleton />;
  if (!data) return null;

  return (
    <div className="border-b bg-card">
      {/* Header */}
      <div className="px-4 py-3 border-b">
        <h2 className="font-semibold">{suburbName}</h2>
        <p className="text-xs text-muted-foreground">{data.territorial_authority}</p>
      </div>

      {/* Resident Profile */}
      <div className="px-4 py-3 border-b">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Resident Profile
        </h3>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <StatRow label="Population" value={data.population.toLocaleString()} />
          <StatRow label="Median age" value={`${data.median_age}`} />
          <StatRow label="Renters" value={`${data.renter_pct}%`} />
          <StatRow label="Owners" value={`${data.owner_pct}%`} />
          <StatRow label="Median rent" value={`$${data.median_rent_weekly}/wk`} />
          <StatRow label="Median income" value={`$${(data.median_household_income/1000).toFixed(0)}k/yr`} />
        </div>
      </div>

      {/* Qualities */}
      <div className="px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Qualities
        </h3>
        <div className="space-y-1 text-sm">
          <QualityRow icon="🏪" label="Supermarkets" value={data.amenities.supermarket} />
          <QualityRow icon="🏫" label="Schools" value={data.amenities.school}
            detail={data.amenities.nearest_school_km ? `nearest ${data.amenities.nearest_school_km.toFixed(1)}km` : undefined} />
          <QualityRow icon="🏥" label="GP clinics" value={data.amenities.gp_clinic} />
          <QualityRow icon="🚌" label="Transit stops" value={data.transit_stop_count} />
          <HazardRow label="Flood risk" level={data.flood_risk} />
          <HazardRow label="Coastal risk" level={data.coastal_risk} />
          <AffordabilityRow band={data.affordability_band} rent={data.median_rent_weekly} />
        </div>
      </div>
    </div>
  );
}
```

---

## 12. Address Search Spec

```typescript
// AddressSearch.tsx
// Position: absolute top-left of map, z-index: 1000 (above map tiles)

function AddressSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AddressResult[]>([]);
  const map = useMap();
  const dispatch = useMapDispatch();

  const debouncedSearch = useDebouncedCallback(async (q: string) => {
    if (q.length < 3) return;
    const res = await fetch(`/api/address/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    setResults(data);
  }, 300);

  function handleSelect(result: AddressResult) {
    map.flyTo([result.latitude, result.longitude], 15, { duration: 1.0 });
    dispatch({ type: 'SELECT_SUBURB', suburb: result.suburb_locality });
    setQuery(result.full_address);
    setResults([]);
  }

  return (
    <div className="leaflet-top leaflet-left" style={{ zIndex: 1000, margin: '10px' }}>
      <div className="leaflet-control bg-white rounded-lg shadow-md p-1">
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); debouncedSearch(e.target.value); }}
          placeholder="Search address or suburb…"
          className="w-64 px-3 py-2 text-sm outline-none"
        />
        {results.length > 0 && (
          <ul className="mt-1 max-h-48 overflow-y-auto">
            {results.map(r => (
              <li key={r.address_id}
                  onClick={() => handleSelect(r)}
                  className="px-3 py-1.5 text-sm hover:bg-slate-100 cursor-pointer">
                {r.full_address}
                <span className="text-xs text-muted-foreground ml-1">· {r.suburb_locality}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

---

## 13. Routing & App Integration

### New route in App.tsx

```typescript
import MapChatPage from '@/pages/MapChatPage';
import MapChatLayout from '@/layouts/MapChatLayout';

// Add to Routes:
<Route path="/map" element={<MapChatLayout />}>
  <Route index element={<MapChatPage />} />
  <Route path=":id" element={<MapChatPage />} />
</Route>
```

### MapChatLayout.tsx

```typescript
// layouts/MapChatLayout.tsx

import { MapProvider } from '@/contexts/MapContext';
import { SidebarProvider } from '@/components/ui/sidebar';
import { AppSidebar } from '@/components/app-sidebar';
import { MapPanel } from '@/components/map/MapPanel';
import { SuburbInfoPanel } from '@/components/map/SuburbInfoPanel';
import { useMapState } from '@/hooks/use-map-state';
import { Outlet } from 'react-router-dom';

function MapChatLayoutInner() {
  const { mapState } = useMapState();

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="h-12 flex items-center px-4 border-b bg-background shrink-0">
        <span className="font-semibold text-sm">Kāinga · Map Mode</span>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Map: 65% */}
        <div className="flex-[65] relative overflow-hidden">
          <MapPanel />
        </div>

        {/* Right panel: 35% */}
        <div className="flex-[35] flex flex-col border-l overflow-hidden">
          <SuburbInfoPanel suburbName={mapState.selectedSuburb} />
          {/* Chat takes remaining space */}
          <div className="flex-1 overflow-hidden">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MapChatLayout() {
  return (
    <MapProvider>
      <MapChatLayoutInner />
    </MapProvider>
  );
}
```

### MapChatPage.tsx

Nearly identical to `ChatPage.tsx`, with two differences:
1. Uses `MAP_SYSTEM_PROMPT` (passed as a custom input to the agent)
2. No `render_visualization` output (maps replace Mermaid)

The agent receives the mode via `custom_inputs`:
```typescript
sendMessage({
  content: userText,
  options: { body: { custom_inputs: { mode: 'map' } } }
});
```

In `agent.py`, read `custom_inputs.get('mode')` to select `SYSTEM_PROMPT` vs `MAP_SYSTEM_PROMPT`.

### Sidebar link

Add to `app-sidebar.tsx`:
```typescript
<SidebarMenuItem>
  <SidebarMenuButton asChild>
    <Link to="/map">
      <MapIcon className="size-4" />
      Map Mode
    </Link>
  </SidebarMenuButton>
</SidebarMenuItem>
```

---

## 14. SQL Reference Queries

### Get suburb centroid as lat/lon

```sql
SELECT
    suburb_name,
    CAST(JSON_VALUE(h3_centerasgeojson(centroid_h3), '$.coordinates[1]') AS DOUBLE) AS lat,
    CAST(JSON_VALUE(h3_centerasgeojson(centroid_h3), '$.coordinates[0]') AS DOUBLE) AS lon
FROM housing.gold.suburb
WHERE suburb_name = :name
```

### Get isochrone H3 cells (for heatmap)

```sql
SELECT
    conv(cast(iso.destination_h3 as string), 10, 16) AS h3_hex_index,
    MIN(iso.travel_minutes) AS travel_minutes
FROM housing.gold.h3_cell origin_hc
JOIN housing.gold.isochrone iso ON origin_hc.h3_cell = iso.origin_h3
WHERE origin_hc.suburb_id IN (
    SELECT suburb_id FROM housing.gold.suburb
    WHERE suburb_name ILIKE :origin_pattern
)
  AND iso.mode = 'transit'
  AND iso.travel_minutes <= :max_minutes
  AND iso.computation_version = 'r5py-v2'
GROUP BY iso.destination_h3
ORDER BY travel_minutes
```

**Note on H3 index format:**
- Databricks stores H3 cells as bigint (decimal).
- h3-js expects hex string, e.g. `"88283082a9fffff"`.
- `conv(cast(iso.destination_h3 as string), 10, 16)` converts decimal bigint to hex.
- Result may be < 15 chars — left-pad with zeros to 15 chars in the API response.

### Get transit stops within bounds

```sql
SELECT stop_name, stop_lat, stop_lon, feed_source
FROM housing.gold.transit_stop
WHERE stop_lat BETWEEN :sw_lat AND :ne_lat
  AND stop_lon BETWEEN :sw_lon AND :ne_lon
LIMIT 500
```

### Get amenities within bounds by type

```sql
SELECT name, lat, lon, amenity_type
FROM housing.gold.amenity__h3
WHERE lat BETWEEN :sw_lat AND :ne_lat
  AND lon BETWEEN :sw_lon AND :ne_lon
  AND amenity_type IN ({type_placeholders})
LIMIT 300
```

### Address search

```sql
SELECT address_id, full_address, suburb_locality, town_city, territorial_authority,
       latitude, longitude
FROM housing.gold.nz_address
WHERE full_address ILIKE :query_pattern
  AND latitude IS NOT NULL
LIMIT 5
```

### Suburb amenity counts

```sql
SELECT amenity_type, COUNT(*) AS count
FROM housing.gold.amenity__h3
WHERE suburb_id = :suburb_id
GROUP BY amenity_type
```

### Suburb transit stop count

```sql
SELECT COUNT(*) AS transit_stop_count
FROM housing.gold.transit_stop ts
JOIN housing.gold.h3_cell hc ON ts.h3_cell = hc.h3_cell
WHERE hc.suburb_id = :suburb_id
```

---

## 15. Phased Delivery

> **Hackathon scope:** Build phases 1–3 only (~10 hours total). Everything beyond that is the post-hackathon roadmap. See §18 for the full cut rationale and demo arc.

---

### Phase 1 — Map skeleton + agent control (4–6 hours)

**Goal:** The map loads, the agent drives it. Typing a commute destination makes suburb pins appear and the camera auto-zooms.

Deliverables:
- `MapChatLayout.tsx` with 65/35 split
- `MapPanel.tsx` with OSM tiles
- `MapContext.tsx` with reducer (includes `zoomToSuburb` flag)
- `SuburbLayer.tsx` with centroid `CircleMarker`s coloured by `passes_all_filters` / `colorMode`
- `FlyToController.tsx` — survivor zoom (`flyToBounds`, 60px padding, maxZoom 14) + single-suburb zoom (`flyTo`, zoom 14)
- `render_map.py` backend tool — returns centroids + filter state, no isochrone/amenity support yet
- `message.tsx` modification — intercept `render_map`, dispatch to MapContext
- `MAP_SYSTEM_PROMPT` in `prompts.py`
- New `/map` and `/map/:id` routes in `App.tsx`
- Agent selects `MAP_SYSTEM_PROMPT` when `custom_inputs.mode === 'map'`
- Sidebar "Map Mode" link

**Milestone:** "I commute to Auckland CBD by train" → ~25 green suburb pins appear → camera auto-zooms to fit them.

---

### Phase 2 — Isochrone heatmap (2–3 hours)

**Goal:** Travel time shown as a coloured H3 hex overlay behind the suburb pins.

Deliverables:
- `IsochroneLayer.tsx` with h3-js (`cellToBoundary`)
- `/api/suburb/:name/isochrone?minutes=N` Express route
- H3 decimal→hex conversion in SQL (`conv(cast(h3 as string), 10, 16)`) + `padStart(15, '0')` in API response

**Milestone:** After commute question, coloured hexagons appear (green near origin → yellow → orange → red). Suburb pins sit on top.

---

### Phase 3 — Suburb info panel (2–3 hours)

**Goal:** Clicking a suburb or asking "tell me about X" fills the Resident Profile and Qualities panels and zooms to street level.

Deliverables:
- `SuburbInfoPanel.tsx` (Resident Profile + Qualities sections)
- `use-suburb-profile.ts` SWR hook
- `/api/suburb/:name/profile` Express route — queries `suburb__year` (demographics), `amenity__h3` (amenity counts), `transit_stop` (stop count), hazard logic
- `SuburbLayer.tsx` click handler → `dispatch({ type: 'SELECT_SUBURB', suburb })` → `FlyToController` zooms to 14

**Milestone:** Click Grey Lynn → camera flies to zoom 14 → Resident Profile fills (population, rent, renter %) → Qualities fills (parks, schools, transit stops, flood risk).

---

### Post-Hackathon Phase 4 — Transit and amenity icon layers

Toggleable transit stop icons (bus/rail/ferry) and amenity icons on the map, with react-leaflet-cluster and MapControls toggle buttons. Routes: `/api/transit-stops?bounds=`, `/api/amenities?bounds=&types=`.

### Post-Hackathon Phase 5 — Address search

`AddressSearch.tsx` input at top-left of map, queries `/api/address/search?q=` against `nz_address`, flies map to selected address.

### Post-Hackathon Phase 6 — Legend and polish

`MapLegend.tsx`, suburb hover tooltips, greyed-out opacity tuning, mobile-free cleanup.

---

## 16. File Changelist

### New files

**Hackathon build (Phases 1–3):**

| File | Purpose |
|---|---|
| `agent_server/tools/render_map.py` | Agent tool: map update |
| `client/src/contexts/MapContext.tsx` | Global map state + reducer |
| `client/src/hooks/use-map-state.ts` | MapContext consumer hook |
| `client/src/hooks/use-suburb-profile.ts` | SWR hook for /api/suburb/:name/profile |
| `client/src/layouts/MapChatLayout.tsx` | Split-screen layout |
| `client/src/pages/MapChatPage.tsx` | /map route page |
| `client/src/components/map/MapPanel.tsx` | Leaflet container |
| `client/src/components/map/SuburbLayer.tsx` | Suburb centroid pins |
| `client/src/components/map/IsochroneLayer.tsx` | H3 hexagon travel time |
| `client/src/components/map/SuburbInfoPanel.tsx` | Resident Profile + Qualities |
| `client/src/components/map/FlyToController.tsx` | Survivor zoom + suburb zoom |
| `server/src/routes/suburb.ts` | /api/suburb/:name/profile + /isochrone |

**Post-hackathon (Phases 4–6):**

| File | Purpose |
|---|---|
| `client/src/components/map/TransitLayer.tsx` | Transit stop markers with clustering |
| `client/src/components/map/AmenityLayer.tsx` | Amenity icon markers |
| `client/src/components/map/AddressSearch.tsx` | Address search box |
| `client/src/components/map/MapControls.tsx` | Layer toggle buttons |
| `client/src/components/map/MapLegend.tsx` | Colour legend |
| `server/src/routes/address.ts` | /api/address/search |
| `server/src/routes/transit.ts` | /api/transit-stops |
| `server/src/routes/amenities.ts` | /api/amenities |

### Modified files

| File | Change |
|---|---|
| `agent_server/tools/__init__.py` | Export `render_map` |
| `agent_server/agent.py` | Add `render_map` to tools list; select prompt by `custom_inputs.mode` |
| `agent_server/prompts.py` | Add `MAP_SYSTEM_PROMPT` constant |
| `client/src/App.tsx` | Add `/map` and `/map/:id` routes |
| `client/src/components/message.tsx` | Add `render_map` tool interception + MapContext dispatch |
| `client/src/components/app-sidebar.tsx` | Add Map Mode link |
| `client/src/components/elements/tool.tsx` | Add `render_map` to TOOL_LABELS |
| `server/src/index.ts` | Register new routes |
| `client/package.json` | Add leaflet, react-leaflet, h3-js, react-leaflet-cluster |
| `client/src/main.tsx` (or `index.css`) | Import `leaflet/dist/leaflet.css` |
| `client/public/` | Add `leaflet-icons/` directory with 3 PNG files |

---

## Appendix: Key Design Decisions

### Why centroid pins not polygons (Phase 1)

Suburb polygon WKB is stored as binary. Decoding it to GeoJSON for all ~25 visible suburbs requires either:
a) A backend endpoint that decodes WKB (using shapely or similar Python lib), or
b) A frontend WKB parser

Neither is in the current stack. Centroid lat/lon derived from H3 requires only `h3_centerasgeojson()` — a single SQL function already available in Databricks. Polygon support is a Phase 2+ enhancement.

### Why react-leaflet not mapbox/deck.gl

Mapbox requires an API token. deck.gl requires mapbox or maplibre as basemap and has a steeper learning curve. react-leaflet with OSM tiles requires zero setup, is fully open source, handles 10,000 markers comfortably (via clustering), and the team already uses Lucide icons that can be embedded in Leaflet DivIcons. For the data volumes in this app (< 300 visible suburbs, < 500 transit stops in view), Leaflet is more than sufficient.

### Why the agent calls render_map (not frontend auto-detecting tool results)

The alternative would be: frontend watches for `compute_isochrone` tool outputs and automatically updates the map. This is simpler but less powerful — the agent has context (affordability, hazard, user constraints) that the frontend doesn't. By having the agent call `render_map` explicitly, it can pass:
- Which suburbs pass ALL filters (not just isochrone)
- Which metric to colour by
- Whether to show the isochrone overlay
- Which amenity types are relevant

The agent's `passes_filter_list` parameter is the key feature — it lets the agent communicate the cumulative filter state in a single call.

### Why a separate MAP_SYSTEM_PROMPT

The existing Kāinga prompt is optimised for text responses: 150-250 words, numbered lists, markdown tables. Map Mode needs the opposite: 40-80 words max, no lists (the map shows them), always end with render_map. These are incompatible response formats — separate prompts are the clean solution.

### H3 index format conversion

Databricks stores H3 cells as bigint (decimal). h3-js expects a 15-character lowercase hex string. The SQL `conv(cast(h3_cell as string), 10, 16)` converts decimal to hex, but the result may be fewer than 15 characters. The Express API must left-pad: `h3hex.padStart(15, '0')`. Failing to pad will cause h3-js to silently fail or produce wrong polygons.

---

## 17. Confirmed Brainstorm Features (Post-Hackathon Roadmap)

These features were confirmed as wanted. They are **not** in the hackathon build but belong in the post-demo roadmap.

### 17.1 GTFS Route Geometry Overlay

Draw actual bus and train lines on the map as polylines, sourced from `housing.silver.gtfs_shapes`.

**Data:** `gtfs_shapes` has trip shape polylines as sequences of lat/lon points per shape_id. Each shape can be decoded into a GeoJSON LineString.

**Frontend:** Toggle-able layer (button in `MapControls`). When on, fetches `/api/transit-routes?bounds=...` → renders coloured LineString features by route_type (bus=blue, rail=orange, ferry=teal).

**Agent:** Agent can say "toggling on route overlay" and call `render_map(show_routes=True)`.

### 17.2 Multi-Modal Isochrone Comparison

Render two overlapping heatmaps simultaneously — walk (blue) and transit (orange) — to show the gap between modes visually.

**Data:** Isochrone table has `mode` column. Query twice: once for `mode='transit'`, once for `mode='walk'` (if populated).

**Frontend:** Two `GeoJSON` layers with different fill colours. Semi-transparent so overlap is visible. Toggle: "Walk vs Transit" button.

**Agent prompt addition:** "show me where transit doesn't help vs walking" → `render_map(show_isochrone_walk=True, show_isochrone_transit=True, commute_origin=...)`.

### 17.3 Rent Burden Filter

Filter suburbs where renters are not rent-stressed. Uses `housing.silver.housing_indicator` Rent Proportion theme — stores % of households spending 25/30/40/50%+ of income on rent per suburb per quarter.

**Backend:** New `score_rent_burden(suburb_names)` tool. Queries `housing_indicator` for the most recent quarter, returns `{suburb_name, pct_over_40pct_income}` list.

**Agent:** After budget filter, apply: "show me suburbs where fewer than 20% of renters are spending over 40% of income on rent."

**Why powerful:** Rent burden is a better affordability signal than raw rent — it accounts for local incomes. A $600/wk suburb in a low-income area is more stressed than a $700/wk suburb in a high-income area.

### 17.4 Housing Supply Signal

Combine `building_consents_per_10k_pop` vs `msd_register_per_10k_pop` from `housing_indicator` to surface supply/demand pressure.

High consents + low MSD waitlist = supply coming online. Low consents + rising MSD waitlist = pressure building.

**Agent use:** "show me suburbs where housing supply is growing faster than demand."

### 17.5 Damp & Mould Risk Layer

`census_sa2_metric` (households_sa2 dataset) contains `% of dwellings with damp or mould` per suburb.

**Backend:** Add `damp_pct` to suburb profile query.

**Frontend:** Add "Damp risk" field to Qualities panel.

**Agent use:** "avoid suburbs with high damp rates" → filter by `damp_pct < 15%`.

### 17.6 Timeline Slider

Housing indicator data is quarterly from ~2020. A slider on the map lets users scrub through time to see rent affordability, crime rate, or building consent activity change.

**Especially powerful for crime** — watch which suburbs improved or worsened over the 4-year monthly crime series.

**Data:** `housing.silver.crime_victimisation_monthly` (48 months, 2022-2026), `housing.silver.housing_indicator` (quarterly).

**Frontend:** Range input at bottom of map panel. On change, dispatches `SET_TIME_PERIOD` → all layers re-colour by that period's data.

---

## 18. Hackathon Scope — What to Build, What to Cut

This is a hackathon. The demo is a single 5-minute walkthrough showing one user finding one suburb. Ruthlessly cut anything that doesn't appear in that walkthrough.

### The Demo Arc

```
1. Map loads — all Auckland suburbs as grey pins
2. "I commute to Britomart by train, 30 minutes"
   → Isochrone heatmap appears over Auckland
   → ~25 suburbs highlight green
   → Camera auto-zooms to fit those 25 suburbs
3. "My rent budget is $2,200/month"
   → 12 suburbs remain highlighted (rent filter applied)
   → Camera tightens further — survivors are all central/west
4. "I want a park nearby for my dog"
   → Park amenity icons appear on the map
   → 8 suburbs survive
   → Camera zooms to the 8 survivors
5. "Tell me about Grey Lynn"
   → Camera zooms to zoom=14, Grey Lynn street level
   → Resident Profile panel: Pop 4,200 · Renters 64% · Rent $750/wk
   → Qualities panel: 2 parks, 3 supermarkets, 12 transit stops, Flood: low
6. "Why isn't Ponsonby showing?"
   → Agent: "Ponsonby passes commute and park filters but median rent is $920/wk — over your $550/wk budget."
```

That's the whole demo. Everything else is roadmap.

### BUILD for hackathon

| Feature | Phase | Why essential |
|---|---|---|
| Map skeleton, suburb pins, MapContext | 1 | Everything else builds on this |
| `render_map` agent tool + `message.tsx` intercept | 1 | Core protocol |
| `MAP_SYSTEM_PROMPT` + mode switching | 1 | Map mode won't work without it |
| `FlyToController` with survivor zoom + suburb zoom | 1 | The "zooms in" vision |
| Isochrone heatmap | 2 | Most visually dramatic step in demo |
| Suburb info panel (Resident Profile + Qualities) | 3 | The "tell me about X" step in demo |
| Cumulative filter state in agent | 1 | "Why not X?" only works with this |

### CUT for hackathon

| Feature | Why cut |
|---|---|
| Address search (`nz_address`) | Nice, but demo uses suburb names only. Half a day for zero demo value. |
| Transit stop icon layer | Qualities panel shows stop *count* — visible icons aren't needed for the 5-min demo. |
| Amenity icon layer on map | Same — Qualities panel covers it. Icons are Phase 4 polish. |
| GTFS route geometry overlay | Exciting but complex. Not in demo arc. |
| Multi-modal isochrone comparison | Two overlapping layers is complex. Single transit isochrone is the demo. |
| Rent burden filter | Powerful but adds query complexity. Use raw rent filter for demo. |
| Timeline slider | Full feature, not in demo arc. |
| MapLegend component | Colour coding is self-evident for the demo; legend is polish. |
| MapControls toggle buttons | Agent controls layers via `render_map` tool — manual toggles aren't needed for the demo. |
| Demographic matching | Requires multi-turn profile questions, complex. Post-hackathon. |
| "Compare these two" visualization | Not in demo arc. |
| Damp/mould filter | Not in demo arc. |

### Hackathon Phases (Revised)

**Phase 1 — Map skeleton + agent control (4-6 hours)**

Everything needed for steps 1-2 of the demo arc:
- `MapChatLayout.tsx`, `MapPanel.tsx`, `MapContext.tsx`
- `SuburbLayer.tsx` (centroid pins, colour by filter pass/fail)
- `FlyToController.tsx` (survivor zoom + suburb zoom)
- `render_map.py` backend tool
- `message.tsx` intercept
- `MAP_SYSTEM_PROMPT`, mode switching in `agent.py`
- `/map` route in `App.tsx`

Milestone: "I commute to Britomart" → green pins appear → map zooms to fit them.

**Phase 2 — Isochrone overlay (2-3 hours)**

Steps 2-4 of demo arc:
- `IsochroneLayer.tsx` with h3-js
- `/api/suburb/:name/isochrone` Express route
- H3 hex conversion in SQL

Milestone: Travel time hexagons appear behind suburb pins.

**Phase 3 — Suburb info panel (2-3 hours)**

Steps 5-6 of demo arc:
- `SuburbInfoPanel.tsx` (Resident Profile + Qualities)
- `use-suburb-profile.ts` SWR hook
- `/api/suburb/:name/profile` Express route

Milestone: Click Grey Lynn → panel fills with census and amenity data.

**Total estimated: ~10 hours of focused work.**

Everything beyond this is the post-hackathon roadmap from §17.

---

## 19. Technical Gotchas & Research Findings

This section documents everything discovered from a full codebase audit. Read this before touching a single file — most implementation pain is predictable from this list.

---

### 19.1 rolldown-vite (NOT standard Vite)

**The single biggest risk.** `client/package.json` has:
```json
"vite": "npm:rolldown-vite@latest"
```

This is the experimental Rust-based Vite rewrite, not the standard `vite` package. Implications:

- **Leaflet CSS import**: `import 'leaflet/dist/leaflet.css'` may behave differently in rolldown-vite vs standard Vite. Add it to `client/src/index.css` via `@import` instead of a JS import as a fallback:
  ```css
  @import "leaflet/dist/leaflet.css";
  ```
  Add this BEFORE `@import "tailwindcss"` so Tailwind doesn't override Leaflet styles.

- **h3-js WebAssembly**: `h3-js` v4+ uses WASM internally. rolldown-vite's WASM handling may differ. If `cellToBoundary` silently returns wrong results, it's a WASM load timing issue. Workaround: import h3-js in a `useEffect` rather than at the module top level.

- **Leaflet is CommonJS**: `leaflet` is a CJS module. rolldown-vite auto-converts CJS to ESM for bundling, but watch for `__esModule` interop issues. If you see `L.default is not a constructor`, use `import * as L from 'leaflet'` or a dynamic import.

- **Do not run `npm install vite`** as a fix — that would create a version conflict with the rolldown-vite alias.

---

### 19.2 Tailwind v4 — no config file

The app uses Tailwind v4 with `@import "tailwindcss"` syntax in `index.css`. There is **no `tailwind.config.js`**.

Key differences that affect map implementation:

- **No `theme.extend`**: Custom colours for the map are added as CSS variables directly in `index.css`, not via a config file.
  ```css
  /* Add to :root in index.css */
  --color-map-pass: #22c55e;
  --color-map-grey: #94a3b8;
  --color-map-iso-15: #22c55e;
  ```

- **Leaflet style conflicts**: Tailwind v4's preflight reset clears `box-sizing`, `margin`, and `padding`. Leaflet relies on these defaults. The `.leaflet-container` and internal panes need explicit styles. Add after the Leaflet CSS import:
  ```css
  /* Guard Leaflet from Tailwind v4 reset */
  .leaflet-container * {
    box-sizing: content-box;
  }
  ```

- **Utility classes still work**: `h-full`, `w-full`, `flex`, `flex-col` etc. all work the same as v3 in JSX. No change to component markup needed.

---

### 19.3 AI SDK v6 — the exact tool part type and state names

Confirmed from reading `message.tsx` and `tool.tsx`:

- Tool part type is **`dynamic-tool`** (not `tool-call`, not `tool_call`). The check is `part.type === 'dynamic-tool'`.
- Fields on a dynamic-tool part: `toolCallId`, `input`, `state`, `errorText`, `output`, `toolName`, `callProviderMetadata`.
- State enum (from `ToolUIPart['state']`):
  ```
  'input-streaming' | 'input-available' | 'output-available' |
  'output-error' | 'output-denied' | 'approval-requested' | 'approval-responded'
  ```
- For `render_map`: intercept at `state === 'input-available'` (fires as soon as the agent has decided on the tool call, before the backend executes it). No need to wait for `output-available`. Return `null` after dispatching to suppress any visible UI in chat.

The existing `effectiveState` logic (converting `input-available` → `output-available` when `providerExecuted && !isLoading`) is **only applied to the generic Tool card render path**, not to the custom intercept blocks. Our code reads `state` directly.

---

### 19.4 MapContext guard — message.tsx is shared between chat and map

`message.tsx` renders in BOTH regular chat mode (no `MapProvider`) and map mode (with `MapProvider`). If `useMapState()` throws when called outside `MapProvider`, it will crash regular chat.

**Fix: use a null-safe context accessor:**

```typescript
// In MapContext.tsx — export a nullable version
export function useOptionalMapDispatch(): React.Dispatch<MapAction> | null {
  const ctx = useContext(MapContext);
  return ctx?.dispatch ?? null;
}
```

Then in `message.tsx`:
```typescript
import { useOptionalMapDispatch } from '@/contexts/MapContext';

// Inside the component (hooks must be called unconditionally):
const mapDispatch = useOptionalMapDispatch();

// In the render_map block:
if (toolName === 'render_map') {
  if (state === 'input-available' || state === 'output-available') {
    if (mapDispatch) {
      mapDispatch({ type: 'RENDER_MAP', payload: input as RenderMapInput });
    }
  }
  return null;
}
```

`useOptionalMapDispatch` must be called unconditionally at the top of the component (React hooks rule), but the dispatch is only called if non-null.

---

### 19.5 `custom_inputs` — how to pass `mode: 'map'` to the agent

**The flow:** Browser → Express `/api/chat` → `streamText` → `databricksFetch` (in `providers-server.ts`) → Databricks serving endpoint (FastAPI agent) → `request.custom_inputs`

**The gap:** `custom_inputs` is not currently in the `postRequestBodySchema` and not injected anywhere in the chain.

**The fix** — three changes:

**1. Add `mode` to `postRequestBodySchema`** (`packages/core/src/schemas/chat.ts`):
```typescript
export const postRequestBodySchema = z.object({
  // ...existing fields...
  mode: z.enum(['chat', 'map']).optional(),
  nextMessageId: z.string().uuid().optional(),
});
```

**2. In `databricksFetch`** (`packages/ai-sdk-providers/src/providers-server.ts`), inject `custom_inputs` alongside `context`:
```typescript
const mapMode = headers.get('x-map-mode');
const enhancedBody = {
  ...body,
  context: { ...body.context, conversation_id: conversationId, user_id: userId },
  ...(mapMode ? { custom_inputs: { mode: mapMode } } : {}),
};
```

**3. In `server/src/routes/chat.ts`**, extract `mode` from the request body and add a header:
```typescript
const { id, message, selectedChatModel, selectedVisibilityType, mode } = requestBody;

const requestHeaders = {
  [CONTEXT_HEADER_CONVERSATION_ID]: id,
  [CONTEXT_HEADER_USER_ID]: session.user.email ?? session.user.id,
  ...(mode === 'map' ? { 'x-map-mode': 'map' } : {}),
  // ...existing OBO token header...
};
```

**4. In `agent.py`**, read from `custom_inputs` before calling `create_agent`:
```python
custom_inputs = dict(request.custom_inputs or {})
mode = custom_inputs.get('mode', 'chat')
system_prompt = MAP_SYSTEM_PROMPT if mode == 'map' else SYSTEM_PROMPT

agent = await init_agent(store=store, checkpointer=checkpointer, system_prompt=system_prompt)
```

And update `init_agent` signature:
```python
async def init_agent(store, checkpointer=None, system_prompt=SYSTEM_PROMPT):
    ...
    return create_agent(model=model, tools=tools, system_prompt=system_prompt, ...)
```

**5. In the frontend `MapChat` component**, add `mode` to the request body via `prepareSendMessagesRequest`:
```typescript
prepareSendMessagesRequest({ messages, id, body }) {
  return {
    body: {
      ...existingFields,
      mode: 'map',  // ← this is the key addition
      ...body,
    },
  };
}
```

---

### 19.6 `postRequestBodySchema` uses Zod v4

The package uses `zod: "^4.3.5"` (Zod v4, confirmed in `client/package.json`). The schema syntax `z.object`, `z.enum`, `z.string`, `.optional()` is the same in v4, so no changes needed for the additions above. However, if you use `z.union`, `z.discriminatedUnion`, or `z.record`, note the v4 API changes.

---

### 19.7 Leaflet icon paths — use direct imports, not `/public/`

The plan originally said to copy PNGs to `client/public/leaflet-icons/`. With rolldown-vite, it's cleaner to import them directly:

```typescript
// In MapPanel.tsx or a map-setup.ts file:
import L from 'leaflet';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});
```

If rolldown-vite doesn't handle PNG imports, fallback: copy the 3 files to `client/public/leaflet-icons/` and reference them with absolute paths (`/leaflet-icons/marker-icon.png`).

---

### 19.8 MapContainer needs explicit CSS height

`react-leaflet`'s `MapContainer` requires a concrete pixel or percentage height, not just `h-full`. `h-full` only works if every ancestor in the DOM chain has an explicit height.

In `MapChatLayout.tsx`, the parent chain must be:
```
html, body         → h-screen (set globally, already done in index.css)
<div> (flex root)  → h-screen flex flex-col
<div> (body split) → flex-1 overflow-hidden flex flex-row
<div> (map col)    → flex-[65] relative overflow-hidden h-full
<MapPanel>         → h-full w-full
<MapContainer>     → style={{ height: '100%', width: '100%' }}
```

Do NOT use `h-dvh` on `MapContainer` — it causes double-scrollbar issues on desktop. Use `height: '100%'` as an inline style.

---

### 19.9 react-leaflet-cluster — use correct version

`react-leaflet-cluster` has version-specific compatibility with `react-leaflet`:

| react-leaflet | react-leaflet-cluster |
|---|---|
| v3 | v1.x |
| v4 | v2.x |

Install explicitly: `npm install react-leaflet-cluster@2 --workspace=client`

Also: `react-leaflet-cluster` doesn't have TypeScript types bundled — no `@types/react-leaflet-cluster` exists. Use `// @ts-ignore` above the import until types are added, or create a minimal `.d.ts` shim:
```typescript
// client/src/types/react-leaflet-cluster.d.ts
declare module 'react-leaflet-cluster' {
  import type { ComponentProps } from 'react';
  export default function MarkerClusterGroup(props: ComponentProps<any>): JSX.Element;
}
```

---

### 19.10 Route structure — map routes go inside RootLayout

Current routing in `App.tsx`:
```
<Route path="/" element={<RootLayout />}>
  <Route element={<ChatLayout />}>
    <Route index element={<NewChatPage />} />
    <Route path="chat/:id" element={<ChatPage />} />
  </Route>
</Route>
```

Map routes must be inside `<Route path="/" element={<RootLayout />}>` (NOT inside `<Route element={<ChatLayout />}>`):
```typescript
<Route path="/" element={<RootLayout />}>
  <Route element={<ChatLayout />}>
    <Route index element={<NewChatPage />} />
    <Route path="chat/:id" element={<ChatPage />} />
    <Route path="saved" element={<SavedSearchesPage />} />
    <Route path="dashboard" element={<DashboardPage />} />
  </Route>
  {/* Map mode — separate layout, NOT inside ChatLayout */}
  <Route element={<MapChatLayout />}>
    <Route path="map" element={<NewMapChatPage />} />
    <Route path="map/:id" element={<MapChatPage />} />
  </Route>
</Route>
```

`MapChatLayout` must NOT include `<AppSidebar>` since the sidebar is already provided by `ChatLayout`. Actually, check what `RootLayout` provides — it may or may not include the sidebar. If `RootLayout` is just a bare `<Outlet>`, then `MapChatLayout` needs its own auth check (copy the session guard from `ChatLayout`).

---

### 19.11 `useSession()` auth check in MapChatLayout

`ChatLayout` checks `session?.user` and shows an auth error if not logged in. `MapChatLayout` must do the same — it will not inherit that check automatically.

Copy the session loading guard from `ChatLayout`:
```typescript
const { session, loading } = useSession();
if (loading) return <LoadingScreen />;
if (!session?.user) return <AuthRequiredScreen />;
```

---

### 19.12 `VisualizationModalTrigger` is not a modal

The plan references `VisualizationModalTrigger` — in the codebase this is just an alias for `VisualizationCard` (confirmed: `export const VisualizationModalTrigger = VisualizationCard;`). It renders inline, not in a dialog. This is fine for our purposes — `render_map` returns `null` (no inline UI), which is simpler.

---

### 19.13 `create_agent` — system prompt is set at init, not per-message

`langchain.agents.create_agent` takes `system_prompt` once at construction. The agent re-initializes on every request (inside `lakebase_context`), so we CAN vary the system prompt per request — but it must be passed BEFORE `create_agent` is called. The `custom_inputs` dict is available at the top of `stream_handler`, before `init_agent` is called, so the pattern in §19.5 works.

---

### 19.14 Zod v4 — `nextMessageId` not in postRequestBodySchema

The `Chat` component sends `nextMessageId: generateUUID()` in the request body (visible in `prepareSendMessagesRequest`), but `postRequestBodySchema` doesn't include it. Zod v4 by default uses `z.object` which strips unrecognised keys (`.strip()` mode). So `nextMessageId` is currently being stripped server-side — this is fine, it's not used there.

When we add `mode` to the schema, Zod's `.strip()` mode means other extra fields from the client are still ignored. No change needed for unknown fields.

---

### 19.15 Biome formatting rules

The codebase uses Biome (not ESLint/Prettier). Rules from `CLAUDE.md`:
- Single quotes for strings: `'my string'`
- Double quotes for JSX attributes: `className="my-class"`
- Semicolons: always required
- Trailing commas: always (all contexts)
- Arrow function parens: always: `(x) => x`
- 2-space indentation

Run `npm run lint --workspace=client` after writing new files to catch issues before they become merge conflicts.

---

### 19.16 `useDataStream()` call in message.tsx

`message.tsx` calls `useDataStream()` at line 96 but doesn't use the return value. It's called for its side effects (subscribing to the data stream). Our `render_map` tool won't interfere with this.

However, `useDataStream` is provided by `DataStreamProvider` which wraps the whole app in `App.tsx`. This is fine — `MapChatLayout` sits inside `App.tsx`, so `useDataStream()` is always available.

---

### 19.17 `sendMessage` API (not `append`)

The AI SDK v6 `useChat` hook uses `sendMessage` (not `append` from v3). The correct API:
```typescript
sendMessage({ role: 'user', parts: [{ type: 'text', text: userInput }] });
```

The `Chat` component's `MultimodalInput` already uses this — copy the same pattern in `MapChat`.

---

### 19.18 Express server port handling

In development, the Express server runs on port 3001. The Vite dev server (frontend) runs on port 3000 and proxies `/api/*` to `localhost:3001`. New routes like `/api/suburb/:name/profile` are automatically proxied — no changes needed to `vite.config.ts`.

---

### 19.19 `RootLayout` and provider hierarchy — confirmed

**`RootLayout.tsx` is trivially thin** — it returns `<Outlet />` plus a single `useEffect` that keeps `<meta name="theme-color">` in sync with the dark-mode class. No providers, no auth guards, no context.

**All global providers live in `App.tsx`**, wrapping `AppRoutes` (the router) from the outside:
```tsx
<ThemeProvider> → <SessionProvider> → <AppConfigProvider> → <DataStreamProvider>
  <AppRoutes />   // ← Router lives here; all routes get every provider for free
```

This means `MapChatLayout` and its child pages automatically inherit `useSession()`, `useAppConfig()`, and `DataStreamProvider` without any extra wrapping. No providers need to move.

**Route tree** — map routes sit inside `RootLayout` as a sibling of `ChatLayout`:
```tsx
<Route path="/" element={<RootLayout />}>
  <Route element={<ChatLayout />}>
    <Route index element={<NewChatPage />} />
    <Route path="chat/:id" element={<ChatPage />} />
    <Route path="saved" element={<SavedSearchesPage />} />
    <Route path="dashboard" element={<DashboardPage />} />
  </Route>
  {/* MAP — add here, outside ChatLayout so no sidebar */}
  <Route element={<MapChatLayout />}>
    <Route path="map" element={<NewMapChatPage />} />
    <Route path="map/:id" element={<MapChatPage />} />
  </Route>
</Route>
```

---

### 19.20 Summary — ordered implementation checklist

Before writing any component:

1. **Install deps** (workspace-specific):
   ```bash
   npm install leaflet react-leaflet h3-js --workspace=client
   npm install @types/leaflet --workspace=client --save-dev
   npm install react-leaflet-cluster@2 --workspace=client
   ```

2. **Add Leaflet CSS** to `client/src/index.css` (before `@import "tailwindcss"`):
   ```css
   @import "leaflet/dist/leaflet.css";
   .leaflet-container * { box-sizing: content-box; }
   ```

3. **Add `mode` to `postRequestBodySchema`** (`packages/core/src/schemas/chat.ts`)

4. **Inject `custom_inputs.mode`** in `databricksFetch` (`packages/ai-sdk-providers/src/providers-server.ts`) — extract `x-map-mode` header, delete it, then replace the existing `conversationId && userId` gated block with the dual-concern pattern from §19.22 so map mode injection runs independently

5. **Read `mode` and pass header** in `server/src/routes/chat.ts`

6. **Update `init_agent`** and `stream_handler` in `agent_server/agent.py` to select prompt by mode

7. **Add `MAP_SYSTEM_PROMPT`** to `agent_server/prompts.py`

8. **Add `render_map` tool** to `agent_server/tools/render_map.py`; register in `agent.py`

9. **Build `MapContext.tsx`** (with `useOptionalMapDispatch`)

10. **Add `render_map` intercept** to `message.tsx` (uses `useOptionalMapDispatch`)

11. **Build layout + page** (`MapChatLayout`, `MapChatPage`, `NewMapChatPage`) — follow `NewChatPage` pattern: `generateUUID()` in state, re-generate on `location.key`, `if (!session?.user) return null`, no `useNavigate`

12. **Add routes** in `App.tsx` (inside `RootLayout`, outside `ChatLayout`)

13. **Build `MapPanel`** with Leaflet icon fix and height chain

14. **Build `SuburbLayer`** with centroid pins

15. **Build `FlyToController`**

16. **Test Phase 1 milestone**: "I commute to Britomart" → pins appear → map zooms

17. **Build `IsochroneLayer`** + Express route

18. **Test Phase 2 milestone**: hexagon overlay appears

19. **Build `SuburbInfoPanel`** + Express route

20. **Test Phase 3 milestone**: click a suburb → panel fills

This order minimises integration risk — each phase has a testable milestone before the next begins.

---

### 19.21 `NewChatPage.tsx` pattern — how to replicate for map

`NewChatPage` does **not** navigate to `/chat/:id`. It stays at `/` and renders `<Chat key={id} ...>` directly. The UUID is generated in component state:

```tsx
const [id, setId] = useState(() => generateUUID());
// Re-generates on back-navigation to the same route:
useEffect(() => { setId(generateUUID()); }, [location.key]);
```

The `key={id}` prop forces a full re-mount of `Chat` (resetting all hook state) whenever `id` changes. Model preference is read from localStorage key `'chat-model'`.

Auth guard pattern is minimal — `if (!session?.user) return null;`.

**`NewMapChatPage` template:**

```tsx
export default function NewMapChatPage() {
  const { session } = useSession();
  const [id, setId] = useState(() => generateUUID());
  const location = useLocation();

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-mount on nav
  useEffect(() => { setId(generateUUID()); }, [location.key]);

  if (!session?.user) return null;

  return (
    <MapChat
      key={id}
      id={id}
      initialMessages={[]}
      session={session}
    />
  );
}
```

The URL stays at `/map` for new sessions — no `useNavigate` needed. If saved-search history requires a stable `/map/:id` URL, add a `navigate` call on first user message (post-hackathon concern).

---

### 19.22 `custom_inputs` body injection — VALIDATED

The `request.custom_inputs` path from frontend to Python agent is **fully confirmed**:

1. `StatefulAgentState` in `agent.py` already declares `custom_inputs: dict[str, Any]` (line 114)
2. `stream_handler` already reads `dict(request.custom_inputs or {})` into `input_state` (line 183)
3. This is a standard field in the MLflow Responses API — the Databricks serving endpoint passes it through to the handler automatically

**The only design issue** is that the existing injection block in `databricksFetch` is gated on `conversationId && userId`:

```typescript
if (conversationId && userId && requestInit?.body && ...) {
  if (shouldInjectContext()) {
    // injects context
  }
}
```

Map mode injection must be **independent of that gate** — it should run whenever the `x-map-mode` header is present, regardless of whether context IDs are set.

**Correct implementation** — replace the gated block with two independent concerns:

```typescript
const mapMode = headers.get('x-map-mode');
headers.delete('x-map-mode');
// (keep existing deletes for conversation/user id headers)

if (requestInit?.body && typeof requestInit.body === 'string') {
  const hasContext = conversationId && userId && shouldInjectContext();
  const hasMapMode = Boolean(mapMode);

  if (hasContext || hasMapMode) {
    try {
      const body = JSON.parse(requestInit.body as string);
      const enhancedBody = {
        ...body,
        ...(hasContext ? {
          context: { ...body.context, conversation_id: conversationId, user_id: userId },
        } : {}),
        ...(hasMapMode ? { custom_inputs: { mode: mapMode } } : {}),
      };
      requestInit = { ...requestInit, body: JSON.stringify(enhancedBody) };
    } catch {
      // pass through unchanged
    }
  }
}
```

This replaces the entire original conditional block and handles both concerns cleanly. The agent then reads `request.custom_inputs['mode']` to select `MAP_SYSTEM_PROMPT`.
