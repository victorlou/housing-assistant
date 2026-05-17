# Open data sources

This is the canonical catalogue of open data sources Housing Assistant uses. Each source has a corresponding pipeline under `pipelines/`.

## Selection criteria

A source qualifies if it is:

1. **Open.** Published by a NZ government agency or under a permissive licence (CC-BY or similar).
2. **National in coverage.** Sources tied to a single region are de-prioritised, with transit GTFS feeds the deliberate exception.
3. **Refreshed at a useful cadence.** Quarterly at worst.
4. **Joinable.** Has a usable spatial or administrative key (suburb, SA2, territorial authority, electorate, address, or coordinates).

We deliberately avoid:

- **CoreLogic / OneRoof / homes.co.nz scraped sale prices.** Behind a paywall in their canonical form. Scraping creates legal and stability risks. Stats NZ HPI plus council valuations is sufficient for our purposes.
- **Trade Me listings.** Same reasoning.
- **Anything requiring per-user OAuth.** Incompatible with our timeline.

## Source catalogue

### Tier 1. Day-1 priorities

| Source | Publisher | What it gives us | Cadence | Target gold table |
|---|---|---|---|---|
| **Tenancy Bond data** | MBIE Tenancy Services | Rent paid, dwelling type, location for every bond lodged. The single most important source. | Monthly | `rent__month__suburb` |
| **Census 2023 income / dwellings / individuals** | Stats NZ | Median income, tenure, rent, crowding, dwelling quality, population by SA2. | Per census (2023) | `suburb__year` (wide-at-grain); enriches `gold.suburb` (places) with a current-snapshot subset |
| **NZ.Stat HPI / REINZ Monthly Property Report** | Stats NZ / REINZ | House price index by territorial authority and dwelling type. | Monthly | `house_price__month__territorial_authority` |
| **Auckland Transport GTFS** | Auckland Transport | Real transit network for ~1.7M people. Powers isochrones for the Auckland demo. | Weekly | `isochrone` |
| **Police recorded crime statistics** | NZ Police | Recorded crime by category and area unit, monthly. | Monthly | `suburb__year` (annual total, allocated via AU2013→SA2 bridge); long-format silver for ANZSOC breakdown |

### Tier 2. Second wave

| Source | Publisher | What it gives us | Cadence | Target gold table |
|---|---|---|---|---|
| **Education Counts schools directory + EQI** | Ministry of Education | Every school, year levels, roll, EQI (replaces decile), location. | Annual | `school` |
| **LINZ NZ Addresses** | LINZ Data Service | Authoritative address layer. Used for geocoding and place disambiguation. | Continuous | `address` |
| **Metlink GTFS** | Greater Wellington | Transit for Wellington region. | Weekly | `isochrone` |
| **Environment Canterbury GTFS** | ECan | Transit for Christchurch / Canterbury. | Weekly | `isochrone` |
| **NIWA flood hazard layers** | NIWA / regional councils | Flood risk extent. | Annual or per-event | `hazard` |
| **EQC / Toka Tū Ake natural hazard layers** | EQC | Liquefaction, coastal inundation, sea-level rise. | Annual | `hazard` |

### Tier 3. Stretch

| Source | Publisher | What it gives us | Cadence | Target gold table |
|---|---|---|---|---|
| **Council valuation rolls (CV/QV)** | Various councils | Per-property capital values. Auckland Council exposes via GeoMaps; smaller councils vary. | Triennial | `property_valuation` |
| **Other regional GTFS feeds** | Waikato, BOP, Otago, Tasman | Transit isochrones for remaining metros. | Weekly | `isochrone` |
| **Stats NZ tertiary education data** | Stats NZ | University and polytech locations and demographics. Useful for the student-renter persona. | Annual | `education_provider` |
| **Healthpoint / Te Whatu Ora facility list** | Te Whatu Ora | GP and ED locations. | Quarterly | `health_facility` |
| **Stats NZ employment / industry by area** | Stats NZ | Employment density and sector mix by suburb. Useful for "where can I get to my industry's jobs?" | Quarterly | `employment__quarter__suburb` |

## Ingestion pattern

Every source follows the same pattern:

1. **Land** raw files into the `housing.bronze.<source>_files` volume. Filename convention: `{source}_{YYYYMMDD}.{ext}`.
2. **Parse** in a Lakeflow pipeline into a typed `housing.bronze.<source>` table. No business logic at this stage. Only typing and basic structure.
3. **Conform** in the silver layer. Normalise place names to the canonical key, geocode where needed, deduplicate, validate.
4. **Materialise** into the relevant gold table(s).

For sources updated on a fixed cadence, ingestion is a scheduled job. For census-style snapshots, ingestion is one-shot and we just rerun on schema change.

## Place-name normalisation

A canonical lookup table `silver.place_lookup` maps every variant of a place name to `(canonical_suburb, ta_code, region_code)`. The agent uses this to disambiguate ("Newton" prompts "Auckland or Christchurch?"). Maintained from Stats NZ Statistical Area concordances plus manual overrides.

## Licensing

All Tier 1 and 2 sources are CC-BY, CC-BY-SA, or in the public domain by virtue of being NZ government data. Attribution is rolled up into a single `docs/attributions.md` file (TODO). We do not redistribute raw third-party data; we only publish derived aggregates and explanations.
