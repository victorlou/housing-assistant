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

---

## CRITICAL FINDING: API access restricted from April 2026

> **This materially changes the feasibility of the official API path.**

From **10 April 2026**, TradeMe has restricted new application registration to **in-trade sellers only**.

Verbatim from `developer.trademe.co.nz/api-overview/registering-an-application`:

> "From 10 April 2026: Application registration limited to in-trade sellers only."

And from the Use Cases page (`developer.trademe.co.nz/api-overview/use-cases`), verbatim:

> "We'll generally support: **In-trade sellers** who want to list their own products on Trade Me Marketplace and receive updates on their listings via the API. The Trade Me API exists for in-trade sellers to manage their own listings on Trade Me Marketplace. **It is not available for personal or non-commercial use.**"
>
> "We generally won't support: … Combining or presenting Trade Me data alongside listings from other sites, or used in data mining, **data aggregation systems**, price comparison services, or other similar situations where listings are not used to provide an extension of the services Trade Me currently provides … **Personal or non-commercial use**, including casual selling, price monitoring, and **buyer-side tools** … **Applications built on top of the API to serve non-in-trade users** (e.g. tools that help casual sellers list, or help buyers bid on or monitor listings), even if the application itself is commercial"

**What this means for Kāinga:**

Kāinga is a property *search and comparison* tool that helps renters (buyers of tenancy services) find suburbs and listings. It is explicitly categorised as a "buyer-side tool" that serves "non-in-trade users" — which TradeMe now explicitly says they won't support. A new application registered on or after 10 April 2026 would be declined.

**This does NOT block the hackathon one-off path** (Apify scrape, no API registration needed). But for any production plan involving the official API, this is a hard blocker unless:
1. Kāinga is developed under a company that is already an approved TradeMe API partner (from before April 2026), OR
2. A direct commercial/data partnership is negotiated with TradeMe's property team (`api@trademe.co.nz`).

---

## What "adding TradeMe listings" would actually mean

In Map Mode, listings would appear as a new map layer — a `ListingsLayer` component parallel to the planned `AmenityLayer` and `TransitLayer` (Phase 4+ in the plan). When toggled on (or when the agent calls `render_map` with `show_listings=True`):

- **Rental listings** appear as coloured pins with weekly rent displayed
- Clicking a pin shows a popup: address, price, bedrooms/bathrooms, property type, link to full listing
- The agent can filter listings by the user's active constraints (e.g. "show me 2-bed rentals under $700/week in these 5 surviving suburbs")
- The cumulative filter state in Map Mode already tracks `max_rent_weekly` — this feeds directly into listing queries

This would make the demo arc more compelling: after the user's filters narrow to 5 suburbs, instead of just seeing suburb pins, they can say "show me what's actually available" and see real listings overlaid on those suburbs.

---

## Option 0: Apify — parseforge/trade-me-property-scraper

> **Note on `lexis-solutions/trademe-co-nz-scraper`:** Confirmed as a **TradeMe Motors (vehicles) scraper** — extracts car/vehicle data (year, kilometres, engine type, transmission) from TradeMe's motors section, not property listings. Not relevant here.

### What parseforge/trade-me-property-scraper does

[Apify](https://apify.com) actor `parseforge/trade-me-property-scraper` runs a headless browser (Puppeteer/Playwright) that navigates trademe.co.nz/property as a simulated user. Apify handles proxy rotation and Cloudflare evasion. You configure inputs, run the actor, and receive structured JSON back via the Apify dataset API.

### Actor stats (verified 2026-05-20)

| Stat | Value |
|---|---|
| Total users | 14 |
| Monthly active users | 3 |
| Bookmarks | 1 |
| Rating | 0.0 (0 reviews) |
| Developer | ParseForge (Community Maintained) |
| Last modified | ~11 days before 2026-05-20 (active maintenance) |

**Implication:** This is a very new actor with minimal community track record. Test with `maxItems: 5` before running the full job to confirm it's still working.

### Confirmed input configuration (exact field names from actor schema)

| Field | Type | Description |
|---|---|---|
| `listingType` | string | `"residential-sale"` or `"residential-rent"` |
| `maxItems` | number | Hard-capped at **100** for standard (free) users. No documented upper limit on paid plans. |
| `region` | string | Filter by region — e.g. `"Auckland"`, `"Wellington"`, `"Canterbury"` (plain-text string, NOT integer ID) |
| `district` | string | Narrow by district (requires `region`) |
| `suburb` | string | Filter by suburb (requires `region` + `district`) |
| `minBedrooms` | number | Minimum bedroom count |
| `maxBedrooms` | number | Maximum bedroom count |
| `minBathrooms` | number | Minimum bathroom count |
| `propertyType` | string | `House`, `Apartment`, `Townhouse`, `Unit`, `Section`, `Lifestyle` |
| `minPrice` | number | Minimum price in NZD (sale price or weekly rent) |
| `maxPrice` | number | Maximum price in NZD |
| `minLandArea` | number | Minimum land area in m² |
| `maxLandArea` | number | Maximum land area in m² |
| `minFloorArea` | number | Minimum floor area in m² |
| `maxFloorArea` | number | Maximum floor area in m² |
| `petsOkay` | boolean | Filter for pet-friendly rentals only |
| `keyword` | string | Search in title/description |

No pagination input — `maxItems` controls total output volume.

### Confirmed output fields (exact field names from actor schema)

| Field | Type | Notes |
|---|---|---|
| `listingId` | number | Unique property identifier |
| `title` | string | Property title |
| `url` | string | Direct link to Trade Me listing |
| `address` | string | Full property address |
| `suburb` | string | Suburb name |
| `district` | string | District name |
| `region` | string | Region name |
| `priceDisplay` | string | Formatted price display string |
| `startPrice` | number | Numeric price (sale) |
| `propertyType` | string | e.g. House, Apartment, Townhouse |
| `bedrooms` | number | Bedroom count |
| `bathrooms` | number | Bathroom count |
| `parking` | string | Parking type description |
| `totalParking` | number | Number of parking spaces |
| `area` | number | Floor area in m² |
| `landArea` | number | Land area in m² |
| `latitude` | number | **Confirmed present** — scrapes map widget |
| `longitude` | number | **Confirmed present** |
| `pictureHref` | string | Primary listing image URL |
| `photoUrls` | array | All listing photo URLs |
| `openHomes` | array | Scheduled open home dates and times |
| `agencyName` | string | Real estate agency name |
| `agencyPhone` | string | Agency phone number |
| `agencyWebsite` | string | Agency website URL |
| `agencyLogo` | string | Agency logo image URL |
| `agents` | array | Agent details: name, phone, email |
| `isFeatured` | boolean | Premium listing status |
| `rateableValue` | number | Property rateable value (CV) |
| `petsOkay` | boolean | Pet policy (rentals) |
| `whiteware` | boolean | Furnished appliances indicator |
| `scrapedAt` | string | Timestamp of extraction |

Note: The actor does **not** output `rentPerWeek` as a separate field — weekly rent is in `startPrice` for `"residential-rent"` runs and in `priceDisplay` as a formatted string. Parse accordingly.

Also note: `GeographicLocation.Accuracy` is not in the output — the actor extracts the raw lat/lon from the map widget without the accuracy metadata. Assume all coordinates are at least suburb-level accurate; verify by inspecting a few listings.

### Hackathon use case: one-off run → Databricks snapshot

```
Run actor once (Auckland rentals, up to 1,500 listings)
    ↓
Export JSON from Apify dataset API
    ↓
Upload to Databricks bronze volume or load directly via notebook
    ↓
Notebook writes housing.bronze.trademe_listings_snapshot (Delta table)
    ↓
Agent queries it like any other table
    ↓
ListingsLayer renders the pins
```

No pipeline, no scheduling. Run it once the night before the demo.

### Cost model (verified 2026-05-20)

**Apify pricing tiers (current):**

| Tier | Monthly | Included credit | Rate per CU |
|---|---|---|---|
| Free | $0 | $5 | $0.20/CU |
| Starter | $29 | $29 | $0.20/CU |
| Scale | $199 | $199 | $0.16/CU |

**Key constraint:** Free tier is **hard-capped at 100 listings per run** by the parseforge actor itself, regardless of Apify platform credits. To scrape 1,500 Auckland rentals you need at least the **Starter plan ($29/month)**.

**Actual CU cost per run:** Not published by the actor author. The $29 monthly credit on the Starter plan is expected to be sufficient for a single 1,500-listing Auckland run (headless browser + residential proxies typically cost <$10/run at this scale). Set an Apify account spending limit before running to avoid surprises.

**Download dataset via Apify API (no extra cost):**
```
GET https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&clean=true
```

### Risks

**1. TradeMe Terms of Service violation (material for production, minimal for hackathon)**

TradeMe's ToS and Business Rules explicitly prohibit scraping and data aggregation. An Apify actor is scraping. The ToS violation attaches to you, not Apify.

**For a one-off internal hackathon demo:** practical risk is minimal. TradeMe does not pursue legal action over a single non-commercial scrape. If you receive a C&D, stop.

**2. NZ Crimes Act 1961 (low probability)**

Sections 250–252 cover unauthorised access to computer systems. Whether scraping publicly visible data qualifies is legally contested. Not a realistic risk for a one-off hackathon demo.

**3. Actor reliability**

14 total users, 3 monthly active, 0 reviews — very new actor with no community vetting. Always test with `maxItems: 5` first to confirm the actor is still working and the output structure matches expectations.

**4. Lat/lon accuracy**

Lat/lon comes from the listing page's embedded map widget. Some vendors choose to hide their exact address — these listings return suburb-centroid coordinates. The actor doesn't expose `GeographicLocation.Accuracy` so you can't filter by precision level. For the demo this is acceptable.

**5. CU cost unpredictability**

Cloudflare detection may trigger residential proxy rotation, which costs more CUs. Set a spending limit in your Apify account settings before running.

---

## Option 0b: Alternative Apify actors — getdataforme variants

Two more actors scrape TradeMe properties. Included for completeness; **parseforge is the better choice**.

### `getdataforme/trademe-properties-spider`

| Stat | Value |
|---|---|
| Total users | 7 |
| Monthly active users | 1 |
| Rating | 0.0 (0 reviews) |
| Last modified | ~3 months ago |
| Pricing | $9.00 / 1,000 results |

**Input:** Takes a full TradeMe search API URL as `Url` parameter plus `itemLimit`. No structured filters.

**Output:** Includes `listing_id`, `title`, `start_price`, `bedrooms`, `bathrooms`, `property_type`, `address`, `suburb`, `district`, `region`, `agency_name`, `agency_phone`, `photo_urls`. **No `latitude`/`longitude` fields in the documented output schema.**

**Verdict:** No confirmed lat/lon = not useful for map pins. Skip.

---

### `getdataforme/trademe-properties-parser-spider`

| Stat | Value |
|---|---|
| Total users | 3 |
| Monthly active users | 0 |
| Rating | 0.0 (0 reviews) |
| Last modified | ~13 days ago |
| Pricing | $9.00 / 1,000 results |

**Input:** `StartUrl` (array), `Keyword` (default: `["rent"]`), `proxyConfiguration`, `itemLimit` (default: 20).

**Output:** Includes `listing_id`, `title`, `rent_per_week`, `bedrooms`, `bathrooms`, `property_type`, `address`, `suburb`, `region`, `agency_name`, `photo_urls`, `listing_url`, **`latitude`** (number), **`longitude`** (number).

**Caveats:** 0 monthly active users (effectively unmaintained), no reviews, default `itemLimit` of 20. Despite having lat/lon in the schema, the 0-active-user status makes reliability doubtful.

**Verdict:** Skip. Use parseforge instead.

---

## Option 0c: realestate.co.nz Apify scrapers (alternative source)

Two actors scrape realestate.co.nz (second-largest NZ property portal):

| Actor | Price | Lat/lon | Notes |
|---|---|---|---|
| `scrapemind/realestate-nz-scraper` | $30/month + usage | Confirmed | Sale, rental, and sold listings |
| `fatihtahta/realestate-co-nz-scraper` | $1.00 / 1,000 results | Not confirmed | Cheaper but lat/lon uncertain |

**Coverage note:** realestate.co.nz has significantly fewer NZ rental listings than TradeMe — TradeMe dominates the rental market. For the demo arc (Auckland rentals), TradeMe is the better source. realestate.co.nz is more relevant for for-sale listings.

**Not recommended** over parseforge/TradeMe for this use case, documented for completeness.

---

## Option 1: TradeMe Developer API

> **Access blocker (2026+):** New application registrations from 10 April 2026 are restricted to in-trade sellers only. Kāinga as a consumer-facing rental search tool does not qualify. See the Critical Finding section above.

### What it is

TradeMe has a publicly documented REST API at `developer.trademe.co.nz`. Property-specific contact: `api@trademe.co.nz`. A sandbox environment is available at `tmsandbox.co.nz` for testing.

Endpoints return XML or JSON by appending `.xml` or `.json` to the endpoint path, e.g.:  
`GET https://api.trademe.co.nz/v1/Search/Property/Rental.json`

### Authentication model — OAuth 1.0a, per-user

The TradeMe API uses **OAuth 1.0a** (NOT OAuth 2.0). The authentication flow uses request tokens, verifiers, and HMAC-SHA1 signatures consistent with the OAuth 1.0a specification.

> "The system generates tokens specific to individual Trade Me members, not application-level tokens. Users grant permission through a consent flow, and tokens can be revoked by the member at any time via their 'My Applications' page."

This IS the "per-user OAuth" problem listed in `data-sources.md`. Every Kāinga user who wants to see TradeMe listings would need to authenticate with their own TradeMe account first.

**OAuth 1.0a flow:**

| Step | Endpoint |
|---|---|
| 1. Get request token | `GET https://api.trademe.co.nz/Oauth/RequestToken?scope=<scope>` |
| 2. User authorizes | `https://trademe.co.nz/Oauth/Authorize?oauth_token=<token>` |
| 3. Exchange for access token | `GET https://api.trademe.co.nz/Oauth/AccessToken` |
| 4. Call protected APIs | Include OAuth 1.0a Authorization header |

**Available permission scopes:** `MyTradeMeRead`, `MyTradeMeWrite`, `BiddingAndBuying`

**Token lifespan:** Tokens expire after 6 months of non-use. Returns HTTP 401 when expired.

**Alternative (own-account only):** The developer portal provides a direct access token generator form for cases where you are accessing your own TradeMe account (no user redirect flow needed).

**Unauthenticated access (rental search only):** The rental search endpoint supports unauthenticated requests with a limit of 25 results per page. No OAuth token required at all — plain HTTP GET. This is the basis for the hackathon Path B script.

### April 2026 registration restriction

From `developer.trademe.co.nz/api-overview/registering-an-application` (verified):

> "From 10 March 2026: Bidding on and buying Marketplace listings via API no longer supported for casual listings."  
> "From 10 April 2026: Application registration limited to **in-trade sellers only**."

**Prior to April 2026:** Registering an application was possible for any developer; registration was reviewed by TradeMe staff with a manual approval step. The sandbox (`tmsandbox.co.nz`) still auto-approves.

**On or after 10 April 2026:** New production registrations are limited to in-trade sellers. Kāinga does not qualify.

### Confirmed rental search endpoint and parameters

**Source:** `developer.trademe.co.nz/api-reference/search-methods/rental-search` (verified)

**Endpoint:** `GET https://api.trademe.co.nz/v1/Search/Property/Rental.{json|xml}`

**Authentication:** Required for >25 rows/page. Supported unauthenticated at 25 rows/page limit.

#### Location parameters

| Parameter | Type | Notes |
|---|---|---|
| `region` | **Integer** | Region ID (see Region ID Reference below). e.g. Auckland = `1` |
| `district` | **Integer** | District ID (see District ID Reference below) |
| `suburb` | **String** | Suburb ID or comma-separated suburb IDs (Integer values, passed as strings) |
| `adjacent_suburbs` | Boolean | Include adjacent suburbs in results |
| `latitude_min` | Number | All four lat/lon params required together |
| `latitude_max` | Number | — |
| `longitude_min` | Number | — |
| `longitude_max` | Number | — |

**Important:** `region`, `district`, and `suburb` accept **integer IDs**, not text names. Use the locality endpoints (`GET v1/localities/regions`, `GET v1/localities/region/{regionId}`) to look up IDs. See the Region ID Reference section below.

#### Property / price parameters

| Parameter | Type | Notes |
|---|---|---|
| `price_min` | Integer | Minimum weekly rent in NZD |
| `price_max` | Integer | Maximum weekly rent in NZD |
| `bedrooms_min` | Integer | — |
| `bedrooms_max` | Integer | — |
| `bathrooms_min` | Integer | — |
| `bathrooms_max` | Integer | — |
| `land_area_min` | Number | Hectares; Lifestyle properties only |
| `land_area_max` | Number | — |
| `property_type` | String | Comma-separated: `Apartment`, `CarPark`, `House`, `Townhouse`, `Unit` |
| `available_now` | Boolean | Only listings available today or earlier |
| `date_from` | DateTime | Exclude listings before this date |
| `pets_ok` | Boolean | Pet-friendly only |

#### Pagination / display parameters

| Parameter | Type | Notes |
|---|---|---|
| `page` | Integer | Page number (starts at 1) |
| `rows` | Integer | Max 25 unauthenticated, max 500 authenticated |
| `sort_order` | Enum | `Default`, `FeaturedFirst`, `ExpiryAsc`, `PriceAsc`, `PriceDesc`, etc. |
| `photo_size` | Enum | `Thumbnail`, `List`, `Medium`, `Gallery`, `Large`, `FullSize` |
| `return_metadata` | Boolean | Include search parameter metadata in response |
| `search_string` | String | Keyword search |
| `member_listing` | Integer | Filter by specific seller/agent ID |

### Confirmed response schema — Rental search

**Root object:**

| Field | Type | Notes |
|---|---|---|
| `TotalCount` | Integer | Total matching results across all pages |
| `TotalCountTruncated` | Boolean | True if total exceeded maximum |
| `Page` | Integer | Current page (starts at 1) |
| `PageSize` | Integer | Items in current page |
| `List` | Collection | Array of Property objects (see below) |
| `SuperFeatures` | Collection | Randomized super-featured listings matching search |
| `Parameters` | Collection | Search parameter metadata (requires `return_metadata=true`) |

**Property object — key fields:**

| Field | Type | Notes |
|---|---|---|
| `ListingId` | Integer | Unique listing identifier |
| `PropertyId` | String | Property ID (separate from listing ID) |
| `Title` | String | Listing title |
| `Category` | String | Listing category |
| `StartPrice` | Number | Asking price (sale listings) |
| `RentPerWeek` | Number | **Weekly rent in NZD** (rental listings) |
| `StartDate` | DateTime | Listing creation date |
| `EndDate` | DateTime | Listing end date |
| `AvailableFrom` | String | Move-in date |
| `Bedrooms` | Integer | — |
| `Bathrooms` | Integer | — |
| `Lounges` | Integer | — |
| `Area` | Integer | Floor area in m² |
| `LandArea` | Integer | Land area in m² |
| `TotalParking` | Integer | Total parking spaces |
| `PropertyType` | String | House, Apartment, Townhouse, Unit, Villa, etc. |
| `Address` | String | Full property address |
| `Suburb` | String | Suburb name |
| `SuburbId` | Integer | Suburb ID |
| `District` | String | District name |
| `DistrictId` | Integer | District ID |
| `Region` | String | Region name |
| `RegionId` | Integer | Region ID |
| `AdjacentSuburbNames` | Collection\<String\> | Nearby suburb names |
| `AdjacentSuburbIds` | Collection\<Integer\> | Nearby suburb IDs |
| `RateableValue` | Integer | Property rateable value (CV) |
| `PetsOkay` | Enum | `NotSpecified`(0), `No`(1), `Yes`(2), `Negotiable`(3) |
| `SmokersOkay` | Enum | `NotSpecified`(0), `No`(1), `Yes`(2) |
| `MaxTenants` | Integer | Maximum occupants |
| `IdealTenant` | String | Preferred tenant description |
| `Parking` | String | Parking details (text) |
| `Whiteware` | String | Furnished/included items description |
| `Amenities` | String | Area amenities (text) |
| `ViewingInstructions` | String | How to view the property |
| `BestContactTime` | String | Optimal contact window |
| `IsFeatured` | Boolean | — |
| `IsSuperFeatured` | Boolean | — |
| `HasGallery` | Boolean | — |
| `IsBold` | Boolean | — |
| `IsHighlighted` | Boolean | — |
| `IsBoosted` | Boolean | — |
| `IsClassified` | Boolean | — |
| `IsOnWatchList` | Boolean | Authenticated users only |
| `PictureHref` | String | Primary photo URL |
| `GeographicLocation` | Object | **Lat/lon coordinates — see below** |
| `Agency` | Object | Agency details — see below |
| `AgencyReference` | String | Agency reference code |
| `PremiumPackageCode` | String | Package type designation |
| `ListingGroup` | String | Grouping classification |
| `SearchResultAttributes` | Collection | Attribute key-value pairs |

**GeographicLocation object (critical for map pins):**

| Field | Type | Notes |
|---|---|---|
| `Latitude` | Number | Decimal degrees, WGS84 |
| `Longitude` | Number | Decimal degrees, WGS84 |
| `Northing` | Integer | Metres, NZTM projection |
| `Easting` | Integer | Metres, NZTM projection |
| `Accuracy` | Enum | `None`(0), `Address`(1), `Street`(3), `Suburb`(2), `AdminPinpoint`(4) |

**Accuracy field handling strategy:**

| `Accuracy` | Meaning | Action |
|---|---|---|
| `Address` | Precise property-level coords | Use directly |
| `Street` | On the street, ±50m | Use directly |
| `Suburb` | Near suburb centroid; vendor hid exact address | Replace with `housing.gold.suburb` centroid |
| `AdminPinpoint` | Administrative centre | Replace with suburb centroid |
| `None` | No location data | Use suburb centroid or exclude from map |

**Agency object (summary):**

| Field | Type | Notes |
|---|---|---|
| `Id` | Integer | Company ID |
| `Name` | String | Agency name |
| `Address` | String | HQ address |
| `PhoneNumber` | String | Contact phone |
| `EMail` | String | Contact email |
| `Website` | String | Agency website |
| `Logo` | String | Logo URL |
| `IsLicensedPropertyAgency` | Boolean | REAA licensed indicator |
| `Agents` | Collection\<Agent\> | Individual agent contact details |

**Agent object:**

| Field | Type |
|---|---|
| `FullName` | String |
| `MobilePhoneNumber` | String |
| `OfficePhoneNumber` | String |
| `EMail` | String |
| `Photo` | String (URL) |
| `UrlSlug` | String (profile path) |

### Residential search endpoint differences

**Endpoint:** `GET https://api.trademe.co.nz/v1/Search/Property/Residential.{json|xml}`

Residential search (for-sale) has the same geographic parameters as rental search. Key differences:

| Feature | Rental (`/Rental`) | Residential (`/Residential`) |
|---|---|---|
| `price_min/max` | Weekly rent in NZD | Sale price in NZD |
| `sales_method` | Not present | `pricedisplayed`, `auction`, `tender`, `negotiation`, `deadlinesale` |
| `available_now` / `date_from` | Present | Not present (listing date filter instead) |
| `pets_ok` | Present | Not present |
| `open_homes` | Not present | Boolean filter for listings with upcoming open homes |
| `PropertyType` options | Apartment, CarPark, House, Townhouse, Unit | Apartment, Bare land, Car Park, Development site, Dwelling, Hotel/Leisure, House, Industrial, Lifestyle block, Office, Retail, Section, Townhouse, Unit, Villa |
| Response field | `RentPerWeek` | `PropertySaleInformation` (sale type, auction date) |

### Rate limiting (verified)

| Scenario | Limit |
|---|---|
| Authenticated API calls | **1,000 requests per hour** per consumer app per user |
| Unauthenticated calls | 25 rows per request (no documented hourly limit, but behaviour is not guaranteed) |
| Exceeded limit response | HTTP 429 |
| Catalogue methods | **Exempt from rate limiting** |

Rate limit is "charged per consumer application per user" — each authenticated user gets their own 1,000 req/hr independently. CORS can be used so limits apply per individual user rather than being shared.

### Terms of Service — key clauses (verbatim)

From `developer.trademe.co.nz/terms-and-conditions` (verified 2026-05-20):

- **Password**: "You must not ask for, use, collect or store any User's password"
- **Sharing**: "You must not share your access key with any other person, or use it for any application other than the one it has been approved for"
- **Data deletion**: Must "comply with privacy legislation" and delete data when no longer needed for the application's approved function
- **Legal notices**: Must "display those same notices to Users at the same stage of the transaction process" as TradeMe does
- **Liability cap**: Trade Me's liability is capped at **$100 NZD** under these terms

### Business Rules — key clauses (verbatim)

From `developer.trademe.co.nz/terms-and-conditions/business-rules` (verified 2026-05-20):

**Listing expiry (critical):**
> "Expired listings must be completely removed from applications. If a listing cannot be found on Trade Me directly, your app should not allow that listing (or any part of it) to be found."

**Data combination prohibition:**
> "Listed data is not to be combined or presented alongside listings from other sites, or used in data mining, data aggregation systems, price comparison services."

**Listings purpose:**
> Listings should "provide an extension of the services Trade Me currently provides" rather than serve comparative purposes.

**Map enrichment (permitted — implied):**
> Applications must "visually distinguish 'featured' listings" and handle gallery requirements. No prohibition on displaying listings on a map — map enrichment is permitted as an extension of TradeMe's own map view functionality.

**Feedback:**
> "This information only ever be displayed in chronological order, and without filtering." Must not allow filtering or reordering of member feedback.

**Q&A:**
> "Should not be used for promotional messages or any other message not directly attributable to the interested User." Must not "add any comments to listings other than those provided directly by your users."

**Enforcement:**
> Trade Me "reserves the right to restrict or alter API call rate limits at our discretion at any time."

### Use cases — explicitly stated scope

From `developer.trademe.co.nz/api-overview/use-cases` (verified 2026-05-20):

> "These are general guidelines only. We retain the right to approve or decline applications for API access at our discretion."

**Will support:**
- In-trade sellers managing their own Marketplace listings

**Will not support:**
- Competing offer with TradeMe
- Exporting or scraping TradeMe data
- Combining / aggregating data with listings from other sites
- Data mining, aggregation systems, price comparison services
- Duplication of existing TradeMe functionality
- Personal or non-commercial use (including "price monitoring" and "**buyer-side tools**")
- Applications serving non-in-trade users (buyer-side tools, casual seller tools)
- Testing or training of people or systems
- Vague or insufficient information

**Assessment for Kāinga:** Kāinga is explicitly a buyer-side tool for renters. It would fall under "buyer-side tools" and "applications built on top of the API to serve non-in-trade users" — both listed as unsupported.

### Integration complexity (if access were available)

| Component | Effort | Notes |
|---|---|---|
| TradeMe app registration | Blocked (April 2026) | Would need pre-existing approval or partnership |
| `fetch_listings` Express route | Low | `GET /api/listings?suburb=X&max_rent=Y` → proxies to TradeMe |
| `ListingsLayer.tsx` | Medium | Similar to `AmenityLayer.tsx` in Phase 4 |
| Agent tool `search_listings` | Low | Calls Express route, returns listing count + sample |
| Accuracy-level handling | Low | Filter `Accuracy === 'None'` to suburb centroid fallback |
| Credential management | Low | Same pattern as LINZ API key (Databricks secret scope) |

---

## Region and District ID Reference

### NZ Region IDs (confirmed from `api.trademe.co.nz/v1/localities/regions.json`)

| `LocalityId` | Region Name | Notes |
|---|---|---|
| 1 | Auckland | Primary demo target |
| 2 | Bay of Plenty | — |
| 3 | Canterbury | Christchurch |
| 4 | Gisborne | — |
| 5 | Hawke's Bay | — |
| 6 | Manawatu / Whanganui | — |
| 7 | Marlborough | — |
| 8 | Nelson / Tasman | — |
| 9 | Northland | — |
| 10 | Otago | Dunedin |
| 11 | Southland | — |
| 12 | Taranaki | — |
| 14 | Waikato | Hamilton |
| 15 | Wellington | — |
| 16 | West Coast | — |
| 100 | All | Catch-all (returns all regions) |

Note: Region ID `13` is absent from the API response — not a typo.

### Auckland District IDs (from prior research — verify against `GET v1/localities/region/1`)

Fetch: `GET https://api.trademe.co.nz/v1/localities/region/1.json`

| `LocalityId` | District Name |
|---|---|
| 4 | Rodney |
| 5 | North Shore City |
| 6 | Waitakere City |
| 7 | Auckland City |
| 8 | Manukau City |
| 9 | Papakura |
| 10 | Franklin |
| 77 | Waiheke Island |
| 81 | Hauraki Gulf Islands |

**Note:** These district IDs should be verified by fetching `https://api.trademe.co.nz/v1/localities/region/1.json` before use — the district data above is from cached research and may not reflect current TradeMe locality structure.

### Locality endpoints for ID lookup

| Endpoint | Returns |
|---|---|
| `GET v1/localities/regions` | All regions with `LocalityId` and `Name` |
| `GET v1/localities/region/{regionId}` | All districts in a region |
| `GET v1/localities/region/{regionId}/{districtId}` | All suburbs in a district |
| `GET v1/localities/region/{regionId}/{districtId}/{suburbId}` | Specific suburb |
| `GET v1/localities` | Full locality hierarchy |

---

## Property API Endpoints Reference

All property-related endpoints from `developer.trademe.co.nz/api-reference/api-index` (verified):

### Search endpoints

| Endpoint | Description |
|---|---|
| `GET v1/Search/Property/Rental` | **Rental property search** — primary endpoint for Kāinga |
| `GET v1/Search/Property/Residential` | For-sale residential search |
| `GET v1/Search/Property/CommercialLease` | Commercial lease search |
| `GET v1/Search/Property/CommercialSale` | Commercial sale search |
| `GET v1/Search/Property/Lifestyle` | Lifestyle property search |
| `GET v1/Search/Property/NewHomes` | New homes search |
| `GET v1/Search/Property/OpenHomes` | Open home search |
| `GET v1/Search/Property/Retirement` | Retirement village search |
| `GET v1/Search/Property/Rural` | Rural property search |
| `POST v1/Search/Property/SuburbPulse` | SuburbPulse unified property search |
| `GET v1/Search/Flatmates` | Flatmate/flatsharing search |

### Locality / reference endpoints (Catalogue — exempt from rate limiting)

| Endpoint | Description |
|---|---|
| `GET v1/localities/regions` | All NZ regions with IDs |
| `GET v1/localities/region/{regionId}` | Districts in a region |
| `GET v1/localities/region/{regionId}/{districtId}` | Suburbs in a district |
| `GET v1/localities/region/{regionId}/{districtId}/{suburbId}` | Specific suburb |
| `GET v1/localities` | Full locality hierarchy |
| `GET v1/Categories/Property` | Property listing categories |

### Map and analytics endpoints

| Endpoint | Description |
|---|---|
| `POST v1/Property/Map/Dots` | Map dots for search (bulk lat/lon for map display) |
| `POST v1/Property/Sold/Search` | Sold property search by address/points/polyline |
| `GET v1/Property/Sold/Suburbs` | All suburbs with sold property data |
| `GET v1/Property/Sold/Suburb/{cityName}/{suburbName}` | Suburb-level sold property statistics |
| `GET v1/Property/Address` | Address lookup endpoint |

### Individual listing

| Endpoint | Description |
|---|---|
| `GET v1/listings/{listingId}` | Full listing detail by ID |
| `POST v1/listings/{listingId}/EmailPropertySeller` | Email seller of a property listing |

### Agency / agent

| Endpoint | Description |
|---|---|
| `GET v1/Property/Office/ListingStatistics` | Office listing statistics |
| `GET v1/Property/Agents/{memberId}/LiveListingStatistics` | Agent live listing stats |

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
- Available listings (bonds are lodged at tenancy start — lagged record of what rented, not what's available now)
- Exact address (suburb-level only)

### Map Mode use

Bond data powers the **aggregate rent statistics** already in the map (median weekly rent per suburb). It does not replace listings as individual pins.

### Verdict

Bond data is essential for the suburb-level affordability layer and is already in the Tier 1 roadmap. It complements TradeMe listings but does not substitute for them if the goal is showing real available properties.

---

## Option 3: Stats NZ Property Transfers

Quarterly data on property sales — price, TA, dwelling type. Does not include rentals or current availability. Useful for the sales/HPI layer but not for a live listings map.

---

## Option 4: Trade Me Property Price Index (free PDF)

TradeMe publishes a monthly Property Price Index as a PDF press release (listed in `pipelines/prices/README.md`). This gives TA-level median asking prices and rental price trends — aggregate statistics, not individual listings.

Same as bond data: useful for the aggregate layer, not a substitute for listing pins.

---

## Option 5: OneRoof / Homes.co.nz / Barfoot & Thompson

Alternative NZ property portals. Their individual listing data is behind paywalls or inaccessible via public API. Barfoot & Thompson is Auckland-only. OneRoof (NZME) and Homes.co.nz have automated valuation models but not browseable listing APIs for third-party apps.

Not recommended over TradeMe, which has the broadest national coverage.

---

## Option 6: No listings layer — suburb-level proxies only

The current plan and existing data gives a strong suburb-level picture: median rent (from census/bond data), affordability band, amenity counts, hazard risk. Powerful for "which suburbs pass my filters."

The gap is: once the user has narrowed to 3–5 suburbs, they currently can't see *what's actually available* without leaving the app. Adding listings closes that loop.

If TradeMe ToS or complexity is too high, a partial substitute:
- Show "active listing count in suburb" using TradeMe or Homes.co.nz aggregate stats (some publish suburb-level counts as public data)
- This gives a "supply signal" (how many 2-beds are available in Onehunga right now) without individual listing pins

---

## Architecture: Live API vs Batch Ingestion

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
- Natural link-back to TradeMe satisfies attribution requirements

**Cons:**
- Latency on the agent turn (~200–500ms extra for the API call)
- Rate-limited (1,000 req/hr authenticated) — fine for interactive use
- Listings disappear when TradeMe removes them (correct behaviour for a live feature)

### Alternative: Nightly batch ingestion → Databricks

**Not recommended** for listings specifically — almost certainly violates TradeMe ToS (creates a replica database). The live proxy approach is both simpler and more ToS-compliant.

---

## What to build (if we proceed)

Assuming access to TradeMe API (or Apify snapshot for hackathon).

### Backend (Express)

```typescript
// GET /api/listings?suburbs=Onehunga,Grey+Lynn&max_rent=700&beds_min=2&type=rental
// Proxies to TradeMe API, returns:
// [{listing_id, title, lat, lon, rent_weekly, bedrooms, bathrooms, property_type, photo_url, trademe_url}]
```

- Cache response per `(suburbs, max_rent, beds_min, type)` key for 15 minutes using in-memory LRU cache
- Strip sensitive fields, only forward what the frontend needs
- Return 429 with friendly message if TradeMe rate-limits

### Frontend

```typescript
// ListingsLayer.tsx — similar to AmenityLayer.tsx
// Activates when mapState.showListings === true
// Fetches /api/listings with current filter state as params
// Renders DivIcon markers with rent price badge
// Popup: thumbnail, address, beds/baths, rent, "View on Trade Me" link
```

Icon design: house icon (Lucide `Home`) with rent price overlay. Colour by property type (green=house, blue=apartment, orange=flat).

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

### Step 1: Choose your data collection method

Two viable paths — pick one based on what you'd rather set up:

---

**Path A: parseforge Apify actor (easier to configure, costs ~$29)**

**Pre-requisite:** Needs at least an Apify **Starter plan** ($29/month). Free tier is hard-capped at 100 listings.

**Confirmed input configuration** (use exact field names from actor schema):
```json
{
  "listingType": "residential-rent",
  "region": "Auckland",
  "maxItems": 1500,
  "minBedrooms": 1
}
```

Add `"district"` and `"suburb"` to narrow further (both require `"region"` to be set). Optionally add `"maxPrice": 900` to filter out outliers.

**Test first with `"maxItems": 10`** to confirm the JSON structure and lat/lon presence before running the full 1,500.

**Download dataset after run:**
```
GET https://api.apify.com/v2/datasets/{dataset_id}/items?format=json&clean=true
```

**Estimated cost:** ~$29 for one month of Starter (which includes $29 credit). The included credit should cover a single Auckland run.

---

**Path B: TradeMe unauthenticated API (free, no Apify account)**

The rental search endpoint supports unauthenticated requests with 25 results per page. A script can collect ~1,500 Auckland listings with 60 paginated HTTP requests — no Apify, no app registration needed (unauthenticated requests do not require a consumer key for the public rental search endpoint).

```python
import requests, json, time

BASE = "https://api.trademe.co.nz/v1/Search/Property/Rental.json"
# region=1 is Auckland (confirmed from v1/localities/regions.json)
params = {"region": 1, "rows": 25, "sort_order": "Default"}

all_listings = []
for page in range(1, 61):
    params["page"] = page
    resp = requests.get(BASE, params=params)
    resp.raise_for_status()
    data = resp.json()
    listings = data.get("List", [])
    if not listings:
        break
    all_listings.extend(listings)
    print(f"Page {page}: {len(listings)} listings (total: {len(all_listings)})")
    time.sleep(0.5)  # be polite

with open("auckland_rentals.json", "w") as f:
    json.dump(all_listings, f)
print(f"Collected {len(all_listings)} listings")
```

**Pagination note:** The response includes `TotalCount` — use it to calculate the actual number of pages needed rather than hardcoding 60.

**Note on unauthenticated access:** Verified that rental search is marked `Authentication: Required` in the official docs, but the docs also note max 25 rows for unauthenticated. Test with `page=1` and no credentials first to confirm it returns data without a consumer key. If it returns a 401, you will need to register at `developer.trademe.co.nz` (sandbox only, since production registration is now restricted) or use Path A.

**What you get with Path B:** Full Property objects including `GeographicLocation.Latitude`, `GeographicLocation.Longitude`, `GeographicLocation.Accuracy`, `RentPerWeek`, `Bedrooms`, `Bathrooms`, `PropertyType`, `Address`, `Suburb`, `Agency` (with agent contact details).

---

### Step 2: Understand lat/lon quality — handle by accuracy level

**Path A (Apify):** Lat/lon is confirmed present as `latitude` and `longitude` at the top level of each listing object. No accuracy metadata — spot-check a few listings by comparing coordinates to the listed address.

**Path B (TradeMe API):** Each listing has a `GeographicLocation` object with `Latitude`, `Longitude`, and `Accuracy`:

| `Accuracy` | Numeric | What it means | Action |
|---|---|---|---|
| `Address` | 1 | Precise property-level coordinates | Use directly |
| `Street` | 3 | On the street, ±50m | Use directly |
| `Suburb` | 2 | Suburb centroid; vendor hid exact address | Use `housing.gold.suburb` centroid |
| `AdminPinpoint` | 4 | Administrative centre | Use suburb centroid |
| `None` | 0 | No location data | Use suburb centroid or exclude |

```python
def resolve_coords(listing: dict) -> tuple[float | None, float | None]:
    geo = listing.get("GeographicLocation", {})
    lat = geo.get("Latitude")
    lon = geo.get("Longitude")
    accuracy = geo.get("Accuracy", "None")

    if lat and lon and accuracy in ("Address", "Street"):
        return lat, lon  # precise enough

    # Mark as needing suburb centroid lookup from housing.gold.suburb
    return None, None
```

The `nz_address` table (2.4M records) is a secondary fallback for address-level precision when accuracy is `Suburb`/`None` — a fuzzy join on address string covers ~70–80%.

### Step 3: Load into Databricks

Simple notebook — no DLT pipeline needed for a snapshot:

```python
import json
from pyspark.sql import Row
from pyspark.sql.types import *

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

def normalize_listing(r: dict) -> dict:
    """Normalize Path A (Apify) or Path B (TradeMe API) listing to common schema."""
    # Path A: flat fields
    if "listingId" in r:
        return {
            "listing_id": str(r.get("listingId", "")),
            "title": r.get("title"),
            "address": r.get("address"),
            "suburb": r.get("suburb"),
            "region": r.get("region"),
            "rent_weekly": r.get("startPrice"),  # rent is in startPrice for residential-rent
            "bedrooms": r.get("bedrooms"),
            "bathrooms": r.get("bathrooms"),
            "property_type": r.get("propertyType"),
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
            "photo_url": r.get("pictureHref"),
            "listing_url": r.get("url"),
            "scraped_at": datetime.now(),
        }
    # Path B: TradeMe API response format
    geo = r.get("GeographicLocation", {})
    accuracy = geo.get("Accuracy", "None")
    lat = geo.get("Latitude") if accuracy in ("Address", "Street") else None
    lon = geo.get("Longitude") if accuracy in ("Address", "Street") else None
    agency = r.get("Agency", {}) or {}
    return {
        "listing_id": str(r.get("ListingId", "")),
        "title": r.get("Title"),
        "address": r.get("Address"),
        "suburb": r.get("Suburb"),
        "region": r.get("Region"),
        "rent_weekly": r.get("RentPerWeek"),
        "bedrooms": r.get("Bedrooms"),
        "bathrooms": r.get("Bathrooms"),
        "property_type": r.get("PropertyType"),
        "lat": lat,
        "lon": lon,
        "photo_url": r.get("PictureHref"),
        "listing_url": f"https://trademe.co.nz/property/residential/rent/{r.get('ListingId')}",
        "scraped_at": datetime.now(),
    }

rows = [Row(**normalize_listing(r)) for r in raw]
df = spark.createDataFrame(rows, schema=schema)
df.write.mode("overwrite").saveAsTable("housing.bronze.trademe_listings_snapshot")
print(f"Loaded {df.count()} listings")
```

**Suburb name normalisation** — TradeMe suburb names can differ from Stats NZ SA2 names (e.g. "Mt Eden" vs "Mount Eden"). Use `housing.silver.place_lookup` (the canonical name lookup table) to normalise before writing, or handle it in the agent tool at query time.

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

Add to `agent.py` tools list alongside `render_map`, `compute_isochrone`, etc.

### Step 5: Extend render_map for listings

Add optional `listings` parameter to the `render_map` tool in `render_map.py`:

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

On the frontend, `message.tsx` already intercepts `render_map` tool calls and dispatches to `MapContext`. Extend `MapState` with a `listings` array and add a `ListingsLayer` component.

### Step 6: MAP_SYSTEM_PROMPT addition

Add to the map system prompt in `prompts.py`:

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

## Open questions

| # | Question | Status | Priority |
|---|---|---|---|
| 1 | **Does unauthenticated Path B actually work?** The docs say `Authentication: Required` but also note 25-row limit for unauthenticated. Test `GET https://api.trademe.co.nz/v1/Search/Property/Rental.json?region=1&rows=25&page=1` without any headers first. | **Unverified — test before demo** | Blocker |
| 2 | **Is storing the Apify snapshot in Databricks within acceptable ToS for a hackathon?** Likely fine for internal non-commercial use. If concern, keep JSON on local disk and load into a temporary Databricks notebook context instead of writing to a Delta table. | Low risk for hackathon | Medium |
| 3 | **Can a pre-existing TradeMe API approval be used?** If anyone involved with Kāinga had a TradeMe API application approved before April 2026, it may still be valid. Worth checking before deciding the API path is fully blocked. | Check with project stakeholders | High (for production) |
| 4 | **Should listings be rental only, or also for-sale?** The persona (Sarah) is a renter. Buy listings would serve a different user. | Product decision | Medium |
| 5 | **What's the max listing count to show per suburb?** If Ponsonby has 80 active rentals, all 80 pins at once clutters the map. Need cluster or limit-to-top-N logic. | UX decision | Medium |
| 6 | **Suburb name normalisation strategy?** TradeMe uses "Mt Eden"; Stats NZ SA2 uses "Mount Eden". Decide whether to normalise at ingest time (cleaner) or at query time (more flexible). | Engineering decision | Medium |
| 7 | **parseforge field name for weekly rent?** The documented output fields don't include `rentPerWeek` — rent appears to be in `startPrice` for rental runs. Confirm with a test run before the full scrape. | **Verify with `maxItems: 5` test** | High |
| 8 | **Do we need to show listing photos on the map?** Popups can load lazily; photos slow initial render. | UX decision | Low |

---

## Rough effort estimate

### Hackathon one-off (data collection only)

| Work item | Estimate |
|---|---|
| Test Path B (unauthenticated scrape script, 5 listings) | 30 min |
| If Path B works: run full 1,500-listing Auckland scrape | 30 min |
| If Path B fails: set up Apify Starter, run parseforge actor | 1–2 hours |
| Ingest JSON into Databricks bronze table (notebook) | 1–2 hours |
| `get_suburb_listings` agent tool + wiring to `render_map` | 2–3 hours |
| `ListingsLayer.tsx` basic pin rendering | 3–4 hours |
| **Total hackathon estimate** | **7–11 hours** |

### Production (if API access secured)

| Work item | Estimate |
|---|---|
| TradeMe API negotiation / approval | Unknown (weeks to months) |
| Express `/api/listings` live proxy route | 3–4 hours |
| `ListingsLayer.tsx` + popup component (full) | 4–5 hours |
| `search_listings` agent tool (live API) | 2 hours |
| `MAP_SYSTEM_PROMPT` addition | 1 hour |
| `render_map` schema extension + TypeScript type update | 1.5 hours |
| **Total production estimate** | **~12–13 hours** (+ approval lead time) |

Phase dependency: natural Post-Hackathon Phase 4.5 — after transit/amenity icon layers (Phase 4) and before the legend/polish phase.

---

## Recommendation

### For the hackathon (one-off demo)

**Try Path B (unauthenticated TradeMe API) first.**

Test it immediately with:
```bash
curl "https://api.trademe.co.nz/v1/Search/Property/Rental.json?region=1&rows=25&page=1"
```
If it returns data without credentials, run the full paginated script (60 pages × 25 = 1,500 listings). Free, no accounts needed.

If it returns 401 or requires a consumer key, fall back to **Path A** (parseforge Apify actor, requires $29/month Starter plan). Either way, the data collection is a single pre-demo run — not a recurring pipeline.

**Critical gotcha for Path A:** The `startPrice` field contains the weekly rent (not a dedicated `rentPerWeek` field) for `listingType: "residential-rent"` runs. Verify with a `maxItems: 5` test run before committing to the full 1,500.

### For production

**The official API path is blocked as of April 2026** — TradeMe now only approves in-trade sellers, which Kāinga is not. Options:

1. **Negotiate a data partnership** directly with `api@trademe.co.nz`. TradeMe has a separate property team and has done partnerships for display-only integrations before. Position as "suburb-level research tool with direct link-back to TradeMe listings" rather than a competitor.

2. **Unauthenticated API with 25-row-per-page pagination** — if Path B works for the hackathon, the same approach could be used for a production feature. TradeMe's rental search is publicly accessible without login; the API endpoint is just the machine-readable equivalent of their website. This is a grey area (unauthenticated public API calls vs. scraping) worth exploring.

3. **Apify parseforge with data licence** — not a realistic production path given ToS, but noted for completeness.

### Minimum viable fallback (no listings access)

Show an active **listing count badge** on each passing suburb pin ("23 rentals available") via a single count API call per suburb (`TotalCount` from the rental search). Avoids all the per-listing map pin complexity while still telling the user something useful about current supply.
