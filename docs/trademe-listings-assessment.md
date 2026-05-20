# TradeMe Listings in Map Mode — Feasibility Assessment

> **Purpose:** Explore every option for bringing real property listings into Map Mode (Kāinga). This is a working document — record decisions, open questions, and findings here as they emerge. Do not edit `docs/map-mode-plan.md`.
>
> **Date started:** 2026-05-20

---

## Background

### Why this is worth revisiting

`docs/data-sources.md` currently lists Trade Me listings under "deliberately avoid":

> **Trade Me listings.** Same reasoning. [as CoreLogic/OneRoof — "Behind a paywall in their canonical form. Scraping creates legal and stability risks."]

That reasoning was correct for the original chat-mode, batch-pipeline architecture. But Map Mode changes the calculus in two ways:

1. **The UX now fits listings.** A suburb choropleth map with aggregate census data is useful context — but a renter deciding between Grey Lynn and Ponsonby wants to see *actual flats available now*. Showing listing pins on the map is a materially better product for the primary persona (Sarah, renter, `docs/personas.md`).

2. **The API option was not fully evaluated.** The original exclusion grouped TradeMe with CoreLogic/OneRoof and cited scraping risk. But TradeMe has an official developer API that is neither scraping nor behind a paywall in the same way — it is publicly documented and designed for third-party use.

The "per-user OAuth" concern from `data-sources.md` ("Anything requiring per-user OAuth — Incompatible with our timeline") may also be a mis-categorisation for TradeMe: their API supports server-side app tokens that do not require Kāinga users to log in with TradeMe accounts.

---

## What "adding TradeMe listings" would actually mean

In Map Mode, listings would appear as a new map layer — a `ListingsLayer` component parallel to the planned `AmenityLayer` and `TransitLayer` (Phase 4+ in the plan). When toggled on (or when the agent calls `render_map` with `show_listings=True`):

- **Rental listings** appear as coloured pins with weekly rent displayed
- Clicking a pin shows a popup: address, price, bedrooms/bathrooms, property type, link to full listing
- The agent can filter listings by the user's active constraints (e.g. "show me 2-bed rentals under $700/week in these 5 surviving suburbs")
- The cumulative filter state in Map Mode already tracks `max_rent_weekly` — this feeds directly into listing queries

This would make the demo arc more compelling: after the user's filters narrow to 5 suburbs, instead of just seeing suburb pins, they can say "show me what's actually available" and see real listings overlaid on those suburbs.

---

## Option 0: Apify Scrapers (parseforge/trade-me-property-scraper, lexis-solutions/trademe-co-nz-scraper)

### What they are

[Apify](https://apify.com) is a commercial web-scraping platform. Two actors currently exist for TradeMe Property:

- `parseforge/trade-me-property-scraper` — property-focused, returns structured listing data
- `lexis-solutions/trademe-co-nz-scraper` — more general TradeMe scraper

Both work by running a headless browser (Puppeteer/Playwright) that simulates a real user visiting trademe.co.nz. Apify handles proxy rotation, CAPTCHA management, and browser fingerprinting to evade Cloudflare detection. You call them via the Apify REST API or SDK, pay per compute unit, and receive JSON back.

### What the data looks like

Typical fields returned by a property scraper actor:
- `title`, `address`, `suburb`, `region`
- `price` / `rent_per_week`
- `bedrooms`, `bathrooms`, `parking`
- `property_type`
- `photos` (array of image URLs)
- `listing_url` (link back to trademe.co.nz)
- Lat/lon: **varies by actor and listing** — some scrape it from the embedded map, some don't

### Hackathon use case: one-off run → Databricks snapshot

**Updated 2026-05-20:** For a hackathon demo (one-off, non-commercial, specific regions only), the architecture is much simpler:

```
Run Apify actor once (Auckland rentals, ~500–1,500 listings)
    ↓
Export JSON from Apify dataset
    ↓
Upload to Databricks bronze volume or load directly via notebook
    ↓
Notebook writes housing.bronze.trademe_listings_snapshot (Delta table)
    ↓
Agent queries it like any other gold table
    ↓
ListingsLayer renders the pins
```

No pipeline, no scheduling, no recurring cost. Run it once before the demo.

### Integration with this architecture — full production options

**A. Scheduled Apify run → Databricks (batch)**

An Apify actor runs nightly via scheduled trigger, outputs to a dataset or webhook, an Express/Python job reads it and writes to `housing.bronze.trademe_listings`. Follows existing pipeline pattern.

**B. On-demand via Apify API (live)**

The Express backend calls `https://api.apify.com/v2/acts/{actor_id}/runs` when a user asks for listings, waits for the run to complete, returns results. Latency: 30–120 seconds per run. Not viable for interactive map use.

Pattern A is the only architecture that would work at interactive speed — but see risks below.

### Cost model

Apify pricing is per Actor Compute Unit (ACU). Rough estimates:
- `parseforge/trade-me-property-scraper`: ~$0.20–0.50 per 100 listings scraped
- Auckland rentals one-off (~1,000–1,500 listings): ~$2–8 total
- A full nightly NZ rental sweep (~3,000–5,000 active listings): ~$6–15/run → ~$180–450/month
- On-demand suburb queries (50 listings): ~$0.10–0.25 per query

### Risks — relevant for production use; low for hackathon one-off

**1. TradeMe Terms of Service violation (material risk)**

TradeMe's ToS (Section 6, "Restrictions") explicitly prohibits:
> "scraping, data mining, extracting, harvesting or otherwise collecting information from Trade Me"

An Apify actor is scraping. Even though you are calling a third-party service to do the scraping, you are the party commissioning the extraction — the ToS violation attaches to you, not Apify. Apify itself disclaims responsibility for ToS violations in its own terms.

This is the same risk that the original `data-sources.md` called out under "Trade Me listings." Framing it as "using an Apify actor" rather than "scraping" does not change the underlying activity.

**2. NZ Crimes Act 1961 exposure (low probability, non-trivial)**

Sections 250–252 of the NZ Crimes Act cover unauthorised access to computer systems. Whether scraping a public website constitutes "access" under those provisions is legally contested globally. Most jurisdictions have not prosecuted scraping of publicly visible data. However, if TradeMe's ToS explicitly prohibits automated access and you continue after being sent a cease-and-desist, the legal risk escalates. For a commercial product, this is worth flagging to a lawyer.

**3. Reliability — scrapers break without warning**

TradeMe updates their frontend regularly. When they do, the Apify actor stops working until the actor maintainer (a third party — not Apify, not you) publishes a fix. For `parseforge/trade-me-property-scraper`, look at the actor's last-updated date and issue history to gauge maintenance cadence. Building a product feature on an unmaintained third-party scraper creates an uncontrolled outage risk.

**4. Lat/lon availability is not guaranteed**

TradeMe embeds a Google Maps widget in some listings — the lat/lon scraped from that widget may be imprecise (property-level), unavailable (if the vendor chose to hide exact location), or inconsistently present across actors. The official API's `GeographicLocation` field is more reliably populated because it comes from TradeMe's own data model.

**5. Apify proxy costs can spike**

Cloudflare detection triggers more proxy rotations, increasing ACU usage unpredictably. A run that costs $0.30 normally might cost $3 after a Cloudflare update. Apify provides spending limits but the default is uncapped.

### Honest comparison vs. official API

| Factor | Apify scraper | TradeMe API |
|---|---|---|
| ToS compliance | **No** — explicitly prohibited | **Yes** — designed for this |
| Reliability | Third-party actor, can break silently | Official, versioned, stable |
| Lat/lon | Inconsistent, scraped from map widget | Structured field, more reliable |
| Cost | ~$180–450/month for nightly sweep | Free tier (dev) / negotiated (commercial) |
| Speed (interactive) | **Not viable** (30–120s per run) | **Viable** (200–500ms per API call) |
| Attribution requirements | None (but violates ToS) | "Powered by Trade Me" + link-back |
| Legal exposure | Material (ToS + possible Crimes Act) | None if within API terms |
| Maintenance burden | High (actor can go stale) | Low (official versioned API) |

### Verdict on Apify scrapers

**For hackathon / one-off demo:** Pragmatic choice. Run once, load snapshot into Databricks, demo it. Cost ~$2–8. Risk is minimal — a single non-commercial scrape for an internal demo is not something TradeMe pursues.

**For production / recurring:** Not recommended. ToS violation is explicit, reliability depends on third-party actor maintenance, and the official API is cleaner for anything long-lived.

---

## Option 1: TradeMe Developer API (recommended starting point)

### What it is

TradeMe has a publicly documented REST API for developers, accessible at `developer.trademe.co.nz`. The API covers all of TradeMe's catalogues including property. This is the canonical, legitimate, non-scraping access path.

### Authentication model

The API uses OAuth 2.0 (also supports legacy OAuth 1.0a). For a server-side app (which is what Kāinga is), the flow is:

1. Register a developer application → receive a **Consumer Key** and **Consumer Secret**
2. Exchange for an **App Access Token** using client credentials grant
3. Use that token to query property listings on behalf of the app (no Kāinga user needs a TradeMe account)

This is **not** "per-user OAuth" — the token is per-app, not per-user. The user never sees or touches TradeMe auth.

### Key endpoints (to be verified against current docs)

| Endpoint | What it returns |
|---|---|
| `GET /v1/search/property/rental` | Rental listings with price, bedrooms, address, lat/lon |
| `GET /v1/search/property/residential` | For-sale listings |
| `GET /v1/listings/{listing_id}` | Full detail for a single listing |

Key query parameters for rental search:
- `suburb` or `district` — filter by geography
- `price_min` / `price_max` — filter by weekly rent
- `bedrooms_min` / `bedrooms_max`
- `latitude` / `longitude` / `radius_km` — geographic radius search
- `rows` — results per page (typically max 25–50)
- `page` — pagination

What a listing record typically contains:
- `ListingId`, `Title`
- `Address` (street-level in most cases)
- `Suburb`, `District`, `Region`
- `GeographicLocation` → `Latitude`, `Longitude` (present on most but not all listings)
- `PriceDisplay`, `RentPerWeek`
- `Bedrooms`, `Bathrooms`, `Parking`
- `PropertyType` (house, flat, apartment, unit)
- `Photos[]` — photo URLs
- `ListedDate`, `ClosedDate`

### Rate limits (approximate — verify at registration)

- **Sandbox / development**: typically generous / uncapped for testing
- **Production standard tier**: approximately 1,000 requests/hour per consumer key
- At 25 listings per request, that is 25,000 listings/hour — far more than interactive use requires

### ToS constraints (critical — read before building)

These are the key questions to clarify with TradeMe before investing build time:

1. **Can the app store listing data in Databricks?**
   TradeMe's standard API ToS prohibits building a database that replicates their catalogue for redistribution or competitive use. However, caching listing IDs and metadata for a defined period (e.g. 24 hours) for user-facing display is typically permitted. The key distinction is: caching for display = probably fine; bulk-storing for analytics = probably not.

2. **What is the permitted cache window?**
   Most listing APIs require data to expire after a set time (24–48 hours is common). Listings shown in Map Mode should reflect current availability, so this constraint aligns naturally with the product intent.

3. **Does the app qualify as a "commercial" use?**
   This is the biggest unknown. If Kāinga is an internal tool or R&D project, standard developer terms likely apply. If it becomes a commercial product with paying users, TradeMe may require a commercial partnership or data licence agreement.

4. **Display attribution requirements?**
   API ToS typically requires "Powered by Trade Me" or similar attribution, and linking back to the original listing. This is easily handled in the popup card.

### Integration complexity

| Component | Effort | Notes |
|---|---|---|
| TradeMe API registration | Low | Fill form at developer.trademe.co.nz |
| `fetch_listings` Express route | Low | `GET /api/listings?suburb=X&max_rent=Y` → proxies to TradeMe |
| `ListingsLayer.tsx` | Medium | Similar to `AmenityLayer.tsx` in Phase 4; renders pin markers with popup |
| Agent tool `search_listings` | Low | Calls Express route, returns listing count + sample; agent includes in `render_map` call |
| Credential management | Low | Databricks secret scope + environment variable (same pattern as LINZ API key) |
| ToS compliance | Unknown | Attribution, caching TTL, link-back to listing |

---

## Option 2: MBIE Tenancy Bond Data (already Tier 1 priority)

### What it gives you

Every tenancy bond lodged with Tenancy Services since ~2014. Approximately 200,000+ bonds/year. Each record has:
- Weekly rent paid
- Suburb and territorial authority
- Dwelling type (house, flat, apartment, boarding house)
- Bond date (proxy for when the tenancy started)

### What it does NOT give you

- Individual listing URLs or photos
- Available listings (bonds are lodged at tenancy start, so it's a lagged record of what rented, not what's available now)
- Exact address (it's suburb-level)

### Map Mode use

Bond data powers the **aggregate rent statistics** that are already in the map (median weekly rent per suburb). It does not replace listings as individual pins.

### Verdict

Bond data is essential for the suburb-level affordability layer and is already in the Tier 1 roadmap. It complements TradeMe listings but does not substitute for them if the goal is showing real available properties.

---

## Option 3: Stats NZ Property Transfers

Already referenced in the prices pipeline README. Quarterly data on property sales — price, TA, dwelling type. Does not include rentals or current availability. Useful for the sales/HPI layer but not for a live listings map.

---

## Option 4: Trade Me Property Price Index (free PDF)

TradeMe publishes a monthly Property Price Index as a PDF press release (listed in `pipelines/prices/README.md` under "Free regional/TA sources"). This gives TA-level median asking prices and rental price trends — aggregate statistics, not individual listings.

Same situation as bond data: useful for the aggregate layer, not a substitute for listing pins.

---

## Option 5: OneRoof / Homes.co.nz / Barfoot & Thompson

These are alternative NZ property portals. Their individual listing data is behind paywalls or inaccessible via public API (same original concern in `data-sources.md`). Barfoot & Thompson is Auckland-only, reducing national coverage. OneRoof (NZME) and Homes.co.nz have automated valuation models but not browseable listing APIs for third-party apps.

Not recommended over TradeMe, which has the broadest national coverage and an official API.

---

## Option 6: No listings layer — suburb-level proxies only

The current plan (and existing data) gives a strong suburb-level picture: median rent (from census/bond data), affordability band, amenity counts, hazard risk. This is powerful for the "which suburbs pass my filters" use case.

The gap is: once the user has narrowed to 3–5 suburbs, they currently can't see *what's actually available* without leaving the app. Adding listings closes that loop.

If TradeMe ToS or complexity is too high, a partial substitute is:
- Show "active listing count in suburb" using Trade Me or Homes.co.nz aggregate stats (some publish suburb-level counts as public data)
- This gives a "supply signal" (how many 2-beds are available in Onehunga right now) without individual listing pins

---

## Architecture: Live API vs Batch Ingestion

Given ToS constraints, the cleanest architecture for TradeMe listings is:

### Recommended: Live API proxy (no Databricks storage of listings)

```
User says "show me available rentals in these suburbs"
    ↓
Agent calls search_listings("Onehunga", max_rent=700, bedrooms_min=2)
    ↓
Express /api/listings endpoint calls TradeMe API in real-time
    ↓
Returns [{listing_id, title, lat, lon, rent, beds, url}, ...]
    ↓
Agent calls render_map(show_listings=True, listings=[...])
    ↓
ListingsLayer renders listing pins on map
    ↓
User clicks a pin → popup shows → link to trademe.co.nz/property/{id}
```

**Pros:**
- Fully compliant with typical API ToS (no bulk storage, real-time display)
- Always shows current available listings (not stale data)
- Simpler architecture — no new Databricks tables needed
- Natural link-back to TradeMe satisfies attribution requirements

**Cons:**
- Latency on the agent turn (~200–500ms extra for the API call)
- Rate-limited (1,000 req/hr) — fine for interactive use, would fail under bot load
- Listings disappear when TradeMe removes them (correct behaviour for a live feature)

### Alternative: Nightly batch ingestion → Databricks

Follows the existing `fetch → bronze → silver → gold` pipeline pattern. A nightly job pulls all current rental listings via the API and stores them in `housing.bronze/silver/gold.trademe_listing`.

**Pros:**
- Fast queries (Databricks SQL, no external API call during user session)
- Listings available offline / if TradeMe API is down
- Can join with other gold tables (e.g. "listings in suburbs that pass my commute filter")

**Cons:**
- Almost certainly violates TradeMe API ToS (creates a replica database)
- Data is up to 24h stale (listings may already be taken)
- Adds a new pipeline to maintain

**Not recommended** for listings specifically — the live proxy approach is both simpler and more ToS-compliant.

---

## What to build (if we proceed)

Assuming TradeMe ToS review comes back positive, the minimum viable implementation:

### Backend (Express)

```typescript
// GET /api/listings?suburbs=Onehunga,Grey+Lynn&max_rent=700&beds_min=2&type=rental
// Proxies to TradeMe API, returns:
// [{listing_id, title, lat, lon, rent_weekly, bedrooms, bathrooms, property_type, photo_url, trademe_url}]
```

- Cache response per `(suburbs, max_rent, beds_min, type)` key for 15 minutes using in-memory LRU cache
- Strip sensitive fields, only forward what the frontend needs
- Return 429 with a friendly message if TradeMe rate-limits us

### Frontend

```typescript
// ListingsLayer.tsx — similar to AmenityLayer.tsx
// Activates when mapState.showListings === true
// Fetches /api/listings with current filter state as params
// Renders DivIcon markers with rent price badge
// Popup: thumbnail, address, beds/baths, rent, "View on Trade Me" link
```

Icon design: house icon (Lucide `Home`) with rent price overlay. Color by property type (green=house, blue=apartment, orange=flat).

### Agent tool

```python
@tool
def search_listings(
    suburb_names: list[str],
    max_rent_weekly: int | None,
    bedrooms_min: int | None,
    listing_type: str = "rental"
) -> dict:
    """Find current available property listings in the given suburbs.
    Call when the user wants to see real listings, not just suburb statistics.
    Returns listing count and sample listings for the agent to narrate."""
```

### MAP_SYSTEM_PROMPT addition

```
**search_listings(suburb_names, max_rent_weekly, bedrooms_min, listing_type)**
Use when the user asks "what's available", "show me listings", or "what's on the market".
Only call for the current passing suburbs (not all suburbs).
After the call, call render_map(show_listings=True, ...) to display pins.
Narrate: "X listings available across your 5 suburbs — map pins show them now."
```

---

## render_map schema extension

Add to `RenderMapInput`:

```typescript
show_listings?: boolean;
listings?: Array<{
  listing_id: string;
  lat: number;
  lon: number;
  rent_weekly?: number;
  sale_price?: number;
  bedrooms: number;
  property_type: string;
  trademe_url: string;
}>;
```

---

## Hackathon execution plan (Apify one-off → Databricks snapshot)

### Step 1: Run the Apify actor

**Which actor:** `parseforge/trade-me-property-scraper` — more structured output for property than the general `lexis-solutions` scraper.

**Configuration to use:**
```json
{
  "searchType": "rental",
  "regions": ["Auckland"],
  "maxListings": 1500,
  "includeDetails": true
}
```

Start with Auckland only for the demo arc (the demo walkthrough in `docs/map-mode-plan.md` §18 is Auckland-focused). Add Wellington and Christchurch if time allows.

**Estimated cost:** ~$3–8 for 1,500 Auckland rentals.

**Export:** After the run, download the dataset as JSON from the Apify console, or pull it via the Apify dataset API:
```
GET https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&clean=true
```

### Step 2: Inspect for lat/lon — this is the critical check

Open the JSON and check whether `latitude`/`longitude` (or `geo`, `location`, `lat`, `lng`) fields are present on listing objects. There are three outcomes:

**A. Lat/lon present on most records** → great, load directly.

**B. Lat/lon missing but `address` is present** → geocode via join to `housing.gold.nz_address`:
```sql
SELECT t.listing_id, t.title, t.address, t.rent_weekly, t.bedrooms,
       n.latitude, n.longitude, n.suburb_locality
FROM trademe_raw t
LEFT JOIN housing.gold.nz_address n
  ON n.full_address ILIKE concat('%', t.address, '%')
LIMIT 1 per listing_id
```
The `nz_address` table has 2.4M records — this fuzzy match will cover ~70–80% of listings. Accept the miss rate for the demo.

**C. Neither lat/lon nor parseable address** → fall back to suburb centroid from `housing.gold.suburb`. Every listing has a suburb name; the suburb centroid gives an approximate pin location (all listings in Onehunga cluster around Onehunga's centroid). Not ideal but functional for demo.

### Step 3: Load into Databricks

Simple notebook — no DLT pipeline needed for a snapshot:

```python
# Load scraped JSON into a Delta table
import json
from pyspark.sql import Row
from pyspark.sql.types import *

# Read the JSON file (uploaded to bronze volume or loaded from local)
with open("/Volumes/housing/bronze/trademe_files/auckland_rentals_20260520.json") as f:
    raw = json.load(f)

schema = StructType([
    StructField("listing_id", StringType()),
    StructField("title", StringType()),
    StructField("address", StringType()),
    StructField("suburb", StringType()),
    StructField("region", StringType()),
    StructField("rent_weekly", DoubleType()),
    StructField("bedrooms", IntegerType()),
    StructField("bathrooms", IntegerType()),
    StructField("property_type", StringType()),
    StructField("lat", DoubleType()),
    StructField("lon", DoubleType()),
    StructField("photo_url", StringType()),
    StructField("listing_url", StringType()),
    StructField("scraped_at", TimestampType()),
])

rows = [Row(**normalize_listing(r)) for r in raw]  # write normalize_listing() to map Apify fields → schema
df = spark.createDataFrame(rows, schema=schema)
df.write.mode("overwrite").saveAsTable("housing.bronze.trademe_listings_snapshot")
```

**Suburb name normalisation** — TradeMe suburb names often differ from Stats NZ SA2 names (e.g. "Grey Lynn" vs "Grey Lynn" is fine, but "Mt Eden" vs "Mount Eden" is not). Use `housing.silver.place_lookup` (the canonical name lookup table) to normalise before writing. Or handle it in the agent tool at query time.

### Step 4: Add the agent tool

New file: `agent_server/tools/get_suburb_listings.py`

```python
from langchain_core.tools import tool
from agent_server.databricks_clients import sql_warehouse_client

@tool
def get_suburb_listings(
    suburb_names: list[str],
    max_rent_weekly: int | None = None,
    min_bedrooms: int | None = None,
    listing_type: str = "rental",
) -> dict:
    """
    Get real available property listings in the given suburbs from the TradeMe snapshot.
    Call when the user asks to see actual available properties, not just suburb statistics.
    Returns listings with lat/lon for map pins.
    Only call for the currently passing suburbs (not all suburbs).
    """
    suburb_list = ", ".join(f"'{s}'" for s in suburb_names)
    rent_clause = f"AND rent_weekly <= {max_rent_weekly}" if max_rent_weekly else ""
    beds_clause = f"AND bedrooms >= {min_bedrooms}" if min_bedrooms else ""

    sql = f"""
        SELECT listing_id, title, address, suburb, rent_weekly,
               bedrooms, bathrooms, property_type, lat, lon,
               photo_url, listing_url
        FROM housing.bronze.trademe_listings_snapshot
        WHERE suburb IN ({suburb_list})
          {rent_clause}
          {beds_clause}
          AND lat IS NOT NULL
        ORDER BY rent_weekly ASC
        LIMIT 50
    """
    rows = sql_warehouse_client().execute(sql)
    listings = [dict(r) for r in rows]
    return {
        "listing_count": len(listings),
        "listings": listings,
        "suburbs_with_listings": list({r["suburb"] for r in listings}),
    }
```

Add to `agent.py` tools list (alongside `render_map`, `compute_isochrone`, etc.).

### Step 5: Extend render_map for listings

Add to the `render_map` tool's `suburbs` field or pass listings separately. Simplest approach for hackathon: agent calls `get_suburb_listings` → passes the returned listings array straight into `render_map` as a new optional parameter:

```python
@tool
def render_map(
    suburbs: list[dict],
    isochrone_suburb: Optional[str],
    isochrone_minutes: Optional[int],
    isochrone_mode: Optional[str],
    filter_summary: str,
    listings: Optional[list[dict]] = None,  # ADD THIS
) -> dict:
    ...
    return {"rendered": True}
```

On the frontend, `message.tsx` already intercepts `render_map` tool calls and dispatches to `MapContext`. Extend `MapState` with a `listings` array and add a `ListingsLayer` component that renders them as pin markers.

### Step 6: MAP_SYSTEM_PROMPT addition

Add to the map system prompt (in `prompts.py`):

```
**get_suburb_listings(suburb_names, max_rent_weekly, min_bedrooms)**
Use when the user says "show me what's available", "what listings are there", or
"show me actual flats". Only call for the currently active (passing) suburbs.
After getting results, call render_map with the listings array so pins appear on the map.
Narrate: "{count} listings across your {n} suburbs — pins now showing on the map."
```

### Demo moment this enables

After the existing demo arc (commute → rent → parks → 5 surviving suburbs):

> **User:** "Show me what's actually available in those suburbs"
> **Agent:** calls `get_suburb_listings(["Onehunga", "Mt Albert", ...], max_rent=700, min_bedrooms=2)`
> → 23 listings found
> **Agent:** calls `render_map(listings=[{listing_id, lat, lon, rent, beds, url}, ...])`
> → 23 pins appear on the map overlaid on the suburb polygons
> **User:** clicks a pin → popup shows address, $665/wk, 2 bed, "View on Trade Me →"

---

## Open questions (resolve before building)

| # | Question | Who decides | Priority |
|---|---|---|---|
| 1 | **Is storing listing metadata (id, lat/lon, price) in memory/cache for 15min within TradeMe ToS?** | Read TradeMe developer ToS carefully | Blocker |
| 2 | **Does Kāinga's intended use qualify as "commercial"?** If it's a hackathon/internal tool, standard dev terms likely apply. If commercialising, need to contact TradeMe. | Project ownership decision | Blocker |
| 3 | **Does TradeMe API return lat/lon reliably for rental listings?** If not, we'd need to geocode via LINZ `nz_address` table. | Test in sandbox | High |
| 4 | **What attribution is required?** "Powered by Trade Me"? Logo? | TradeMe ToS / developer docs | High |
| 5 | **Should listings be rental only, or also for-sale?** The persona (Sarah) is a renter. Buy listings would serve a different user. | Product decision | Medium |
| 6 | **What's the max listing count per suburb?** If Ponsonby has 80 active rentals, showing all 80 pins at once could clutter the map — need cluster or limit-to-top-N logic. | UX decision | Medium |
| 7 | **Do we need to show listing photos on the map?** Popups can load lazily; photos slow initial render. | UX decision | Low |

---

## Rough effort estimate (if proceeding)

Assumes TradeMe API access approved, OAuth credential in Databricks secrets.

| Work item | Estimate |
|---|---|
| TradeMe API registration + sandbox test | 2 hours |
| Express `/api/listings` proxy route | 3–4 hours |
| `ListingsLayer.tsx` + popup component | 4–5 hours |
| `search_listings` agent tool | 2 hours |
| `MAP_SYSTEM_PROMPT` addition | 1 hour |
| `render_map` schema extension | 1 hour |
| `RenderMapInput` TypeScript type update | 30 min |
| **Total** | **~14–15 hours** |

Phase dependency: this is natural Post-Hackathon Phase 4.5 — after the transit/amenity icon layers (Phase 4) and before the legend/polish phase. The `ListingsLayer` would follow the same fetch-by-bounds pattern as `AmenityLayer`.

---

## Recommendation

**Do it, but verify ToS first.**

The TradeMe API is the right path. It is:
- Legitimate (official API, not scraping)
- Server-side credentialed (not per-user OAuth in the problematic sense)
- High coverage (~95%+ of NZ rental listings)
- Architecturally simple (live proxy, no new Databricks tables)
- A genuine product differentiator for the primary persona (Sarah would love this)

The one gate is ToS compliance — specifically whether the intended use of Kāinga is "personal/research" (standard dev terms, easy) or "commercial" (may require a commercial data partnership with TradeMe).

**Immediate next step:** Register a developer account at `developer.trademe.co.nz`, read the ToS for the property API carefully (especially the property/listings section), and test in sandbox to confirm lat/lon availability on rental listings. Report back here.

If ToS is a blocker: the suburb-level "listing count" proxy (active listings count per suburb, sourced from Trade Me's public suburb stats or via a single count API call rather than individual listing records) is a lower-risk fallback that still adds value to the map.
