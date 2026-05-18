"""
Build dashboard.lvdash.json as a single scrollable page.

Run to regenerate the dashboard:
    python3 dashboards/planner/build_onepager.py

Then deploy:
    cd dashboards/planner
    databricks --profile hackathon bundle deploy -t dev
    databricks --profile hackathon lakeview publish 01f151d8662d110ebf581885bebf8df1 --warehouse-id f21913d784edd9ad

Layout (6-column grid, each unit ≈ 50px tall):
    y  0-1   two filter rows  (budget / region / TA | flood / schools / transit)
    y  2-9   main suburb table
    y 10-11  counters: avg rent | avg rent-to-income | matching suburb count
    y 12-16  scatter: rent vs crime by region (4w)  |  bar: least overcrowded (2w)
    y 17-21  hbar: cheapest suburbs (3w)             |  hbar: most schools (3w)
    y 22-26  hbar: best affordability ratio (3w)     |  hbar: best transit (3w)
    y 27-32  scatter: amenity locations (3w)         |  scatter: transit stops (3w)
"""

import json

PATH = r"C:\Users\IsabelBody-DataAnaly\housing-assistant\dashboards\planner\dashboard.lvdash.json"

# ── widget factory functions ───────────────────────────────────────────────

def pos(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def filter_widget(name, qname, dataset, col, display, title):
    return {
        "name": name,
        "queries": [{"name": qname, "query": {
            "datasetName": dataset,
            "disaggregated": False,
            "fields": [
                {"expression": f"`{col}`", "name": col},
                {"expression": "COUNT(*)", "name": "n"},
            ],
        }}],
        "spec": {
            "widgetType": "filter-multi-select",
            "version": 2,
            "encodings": {"fields": [{
                "displayName": display,
                "fieldName": col,
                "queryName": qname,
                "counterFieldName": "n",
            }]},
            "frame": {"showTitle": True, "title": title},
        },
    }


def table_widget(name, qname, dataset, col_specs, title):
    """col_specs: list of dicts with keys fieldName, title, type, and optional alignContent."""
    return {
        "name": name,
        "queries": [{"name": qname, "query": {
            "datasetName": dataset,
            "disaggregated": True,
            "fields": [{"expression": f"`{c['fieldName']}`", "name": c["fieldName"]}
                       for c in col_specs],
        }}],
        "spec": {
            "widgetType": "table",
            "version": 2,
            "condensed": True,
            "allowHTMLByDefault": False,
            "encodings": {"columns": [
                {**c, "visible": True, "order": i} for i, c in enumerate(col_specs)
            ]},
            "frame": {"showTitle": True, "title": title},
        },
    }


def counter_widget(name, qname, dataset, expr, field_name, display, title):
    return {
        "name": name,
        "queries": [{"name": qname, "query": {
            "datasetName": dataset,
            "disaggregated": False,
            "fields": [{"expression": expr, "name": field_name}],
        }}],
        "spec": {
            "widgetType": "counter",
            "version": 1,
            "encodings": {"value": {"fieldName": field_name, "displayName": display}},
            "frame": {"showTitle": True, "title": title},
        },
    }


def bar_widget(name, dataset, y_expr, y_name, y_display, title, horizontal=False):
    """Vertical bar by default; horizontal=True swaps axes for long suburb names."""
    if horizontal:
        # suburb on y-axis → bars run left-to-right
        x_enc = {"displayName": y_display, "fieldName": y_name,
                 "scale": {"type": "quantitative"}, "axis": {"title": y_display}}
        y_enc = {"displayName": "Suburb", "fieldName": "suburb_name",
                 "scale": {"type": "categorical"}, "axis": {"title": "Suburb"}}
    else:
        x_enc = {"displayName": "Suburb", "fieldName": "suburb_name",
                 "scale": {"type": "categorical"}, "axis": {"title": "Suburb"}}
        y_enc = {"displayName": y_display, "fieldName": y_name,
                 "scale": {"type": "quantitative"}, "axis": {"title": y_display}}
    return {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": dataset,
            "disaggregated": False,
            "fields": [
                {"expression": "`suburb_name`", "name": "suburb_name"},
                {"expression": y_expr, "name": y_name},
            ],
        }}],
        "spec": {
            "widgetType": "bar",
            "version": 3,
            "encodings": {"x": x_enc, "y": y_enc, "label": {"show": False}},
            "frame": {"showTitle": True, "title": title},
        },
    }


def scatter_widget(name, qname, dataset, x_col, y_col, color_col, group_col,
                   x_display, y_display, color_display, title):
    """
    disaggregated:false + explicit MAX aggregation on x/y, GROUP BY color_col + group_col.
    Field names in encoding must match the 'name' values in the query fields exactly.
    group_col provides enough cardinality to keep individual points distinct.
    """
    return {
        "name": name,
        "queries": [{"name": qname, "query": {
            "datasetName": dataset,
            "disaggregated": False,
            "fields": [
                {"expression": f"`{group_col}`",       "name": group_col},
                {"expression": f"`{color_col}`",       "name": color_col},
                {"expression": f"MAX(`{x_col}`)",      "name": f"max({x_col})"},
                {"expression": f"MAX(`{y_col}`)",      "name": f"max({y_col})"},
            ],
        }}],
        "spec": {
            "widgetType": "scatter",
            "version": 3,
            "encodings": {
                "x": {"fieldName": f"max({x_col})", "displayName": x_display,
                      "scale": {"type": "quantitative"}, "axis": {"title": x_display}},
                "y": {"fieldName": f"max({y_col})", "displayName": y_display,
                      "scale": {"type": "quantitative"}, "axis": {"title": y_display}},
                "color": {"fieldName": color_col, "displayName": color_display,
                          "scale": {"type": "categorical"}},
            },
            "frame": {"showTitle": True, "title": title},
        },
    }


# ── datasets ───────────────────────────────────────────────────────────────

DATASETS = [
    {
        "name": "ds_suburb_sarah",
        "displayName": "Suburb Comparison (rent, flood, amenities, transit, safety)",
        "query": (
            "WITH suburb_hazard AS (\n"
            "  SELECT\n"
            "    hc.suburb_id,\n"
            "    BOOL_OR(hz.in_flood_plain)              AS any_flood_plain,\n"
            "    BOOL_OR(hz.in_coastal_inundation_1_aep) AS any_coastal\n"
            "  FROM housing.gold.h3_cell hc\n"
            "  JOIN housing.gold.hazard hz ON hz.h3_cell = hc.h3_cell\n"
            "  GROUP BY hc.suburb_id\n"
            "),\n"
            "suburb_amenity AS (\n"
            "  SELECT\n"
            "    suburb_id,\n"
            "    COUNT(CASE WHEN amenity_type IN ('school','early_childhood') THEN 1 END) AS education_count,\n"
            "    COUNT(CASE WHEN amenity_type = 'supermarket'                 THEN 1 END) AS supermarket_count,\n"
            "    COUNT(CASE WHEN amenity_type = 'park'                        THEN 1 END) AS park_count,\n"
            "    COUNT(CASE WHEN amenity_type IN ('hospital','pharmacy','gp_clinic') THEN 1 END) AS health_count\n"
            "  FROM housing.gold.amenity__h3\n"
            "  GROUP BY suburb_id\n"
            "),\n"
            "suburb_transit AS (\n"
            "  SELECT\n"
            "    hc.suburb_id,\n"
            "    COUNT(DISTINCT ts.stop_id) AS transit_stops\n"
            "  FROM housing.gold.transit_stop ts\n"
            "  JOIN housing.gold.h3_cell hc ON hc.h3_cell = ts.h3_cell\n"
            "  GROUP BY hc.suburb_id\n"
            "),\n"
            "suburb_crime AS (\n"
            "  SELECT suburb_id, total_victimisations AS annual_crime\n"
            "  FROM housing.silver.crime_at_suburb_year\n"
            "  WHERE crime_year = 2025\n"
            ")\n"
            "SELECT\n"
            "  s.suburb_id,\n"
            "  s.suburb_name,\n"
            "  s.territorial_authority,\n"
            "  s.region,\n"
            "  s.population_2023,\n"
            "  sy.median_weekly_rent,\n"
            "  sy.median_household_income,\n"
            "  ROUND(sy.median_weekly_rent * 52 / NULLIF(sy.median_household_income, 0) * 100, 1) AS rent_to_income_pct,\n"
            "  ROUND(sy.owner_occupier_pct * 100, 1) AS owner_occupier_pct,\n"
            "  ROUND(sy.percent_crowded * 100, 1)    AS percent_crowded,\n"
            "  sy.dwellings_no_heating,\n"
            "  ROUND(sy.dwellings_always_damp * 100.0 / NULLIF(sy.dwellings_damp_total_stated, 0), 1) AS pct_always_damp,\n"
            "  CASE WHEN COALESCE(sh.any_flood_plain, FALSE) THEN 'Yes' ELSE 'No' END AS flood_plain,\n"
            "  CASE WHEN COALESCE(sh.any_coastal, FALSE)      THEN 'Yes' ELSE 'No' END AS coastal_risk,\n"
            "  COALESCE(sa.education_count, 0)      AS education_nearby,\n"
            "  COALESCE(sa.supermarket_count, 0)    AS supermarkets_nearby,\n"
            "  COALESCE(sa.park_count, 0)           AS parks_nearby,\n"
            "  COALESCE(sa.health_count, 0)         AS health_nearby,\n"
            "  COALESCE(st.transit_stops, 0)        AS transit_stops,\n"
            "  sc.annual_crime                       AS suburb_annual_crime,\n"
            "  CASE\n"
            "    WHEN sy.median_weekly_rent IS NULL  THEN '13. Not available'\n"
            "    WHEN sy.median_weekly_rent <= 300   THEN '01. Under $300 / week'\n"
            "    WHEN sy.median_weekly_rent <= 350   THEN '02. $300 to $350 / week'\n"
            "    WHEN sy.median_weekly_rent <= 400   THEN '03. $350 to $400 / week'\n"
            "    WHEN sy.median_weekly_rent <= 450   THEN '04. $400 to $450 / week'\n"
            "    WHEN sy.median_weekly_rent <= 500   THEN '05. $450 to $500 / week'\n"
            "    WHEN sy.median_weekly_rent <= 550   THEN '06. $500 to $550 / week'\n"
            "    WHEN sy.median_weekly_rent <= 600   THEN '07. $550 to $600 / week'\n"
            "    WHEN sy.median_weekly_rent <= 650   THEN '08. $600 to $650 / week'\n"
            "    WHEN sy.median_weekly_rent <= 700   THEN '09. $650 to $700 / week'\n"
            "    WHEN sy.median_weekly_rent <= 800   THEN '10. $700 to $800 / week'\n"
            "    WHEN sy.median_weekly_rent <= 1000  THEN '11. $800 to $1,000 / week'\n"
            "    ELSE                                     '12. Over $1,000 / week'\n"
            "  END                                  AS rent_bucket,\n"
            "  CASE WHEN COALESCE(sa.education_count,0) > 0 THEN 'Yes' ELSE 'No' END AS has_schools,\n"
            "  CASE WHEN COALESCE(st.transit_stops,0) >= 5  THEN 'Yes' ELSE 'No' END AS good_transit\n"
            "FROM housing.gold.suburb s\n"
            "LEFT JOIN housing.gold.suburb__year sy\n"
            "  ON sy.suburb_id = s.suburb_id AND sy.census_year = 2023\n"
            "LEFT JOIN suburb_hazard sh ON sh.suburb_id = s.suburb_id\n"
            "LEFT JOIN suburb_amenity sa ON sa.suburb_id = s.suburb_id\n"
            "LEFT JOIN suburb_transit st ON st.suburb_id = s.suburb_id\n"
            "LEFT JOIN suburb_crime sc ON sc.suburb_id = s.suburb_id\n"
            "WHERE s.population_2023 > 500\n"
            "ORDER BY s.territorial_authority, s.suburb_name"
        ),
    },
    {
        # GROUP BY (name, amenity_type) naturally deduplicates repeat-named amenities.
        # LIMIT caps total rows so Lakeview's scatter renderer doesn't time out.
        "name": "ds_amenities_scatter",
        "displayName": "Amenities geographic scatter (lat/lon, max 1000 rows)",
        "query": (
            "SELECT amenity_type, name, lat, lon\n"
            "FROM housing.gold.amenity__h3\n"
            "WHERE amenity_type IN ('school','early_childhood','supermarket','park','hospital','pharmacy','gp_clinic','library')\n"
            "  AND lat IS NOT NULL AND lon IS NOT NULL\n"
            "LIMIT 1000"
        ),
    },
    {
        "name": "ds_transit_scatter",
        "displayName": "Transit stops geographic scatter (lat/lon, max 1000 rows)",
        "query": (
            "SELECT feed_source, stop_name, stop_lat, stop_lon\n"
            "FROM housing.gold.transit_stop\n"
            "WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL\n"
            "LIMIT 1000"
        ),
    },
    {
        # Pre-filtered scatter dataset: suburbs with both rent affordability and crime data.
        # LIMIT 500 keeps the scatter readable; ORDER BY ensures deterministic sample.
        "name": "ds_scatter_rti_crime",
        "displayName": "Scatter: rent-to-income vs crime (500 suburbs)",
        "query": (
            "SELECT s.suburb_name, s.region,\n"
            "  ROUND(sy.median_weekly_rent * 52 / NULLIF(sy.median_household_income, 0) * 100, 1) AS rent_to_income_pct,\n"
            "  sc.total_victimisations AS suburb_annual_crime\n"
            "FROM housing.gold.suburb__year sy\n"
            "JOIN housing.gold.suburb s ON s.suburb_id = sy.suburb_id\n"
            "JOIN housing.silver.crime_at_suburb_year sc\n"
            "  ON sc.suburb_id = s.suburb_id AND sc.crime_year = 2025\n"
            "WHERE sy.census_year = 2023\n"
            "  AND sy.median_weekly_rent IS NOT NULL\n"
            "  AND sy.median_household_income IS NOT NULL\n"
            "  AND sc.total_victimisations IS NOT NULL\n"
            "  AND s.population_2023 > 500\n"
            "ORDER BY s.suburb_name\n"
            "LIMIT 500"
        ),
    },
    # Pre-aggregated 25-row datasets for bar charts (ORDER BY + LIMIT baked in)
    {
        "name": "ds_bar_rent",
        "displayName": "Bar: 25 cheapest suburbs by weekly rent",
        "query": (
            "SELECT s.suburb_name, sy.median_weekly_rent\n"
            "FROM housing.gold.suburb__year sy\n"
            "JOIN housing.gold.suburb s ON s.suburb_id = sy.suburb_id\n"
            "WHERE sy.census_year = 2023\n"
            "  AND sy.median_weekly_rent IS NOT NULL\n"
            "  AND s.population_2023 > 500\n"
            "ORDER BY sy.median_weekly_rent ASC\n"
            "LIMIT 25"
        ),
    },
    {
        "name": "ds_bar_afford",
        "displayName": "Bar: 25 most affordable suburbs (rent-to-income)",
        "query": (
            "SELECT s.suburb_name,\n"
            "  ROUND(sy.median_weekly_rent * 52 / NULLIF(sy.median_household_income, 0) * 100, 1) AS rent_to_income_pct\n"
            "FROM housing.gold.suburb__year sy\n"
            "JOIN housing.gold.suburb s ON s.suburb_id = sy.suburb_id\n"
            "WHERE sy.census_year = 2023\n"
            "  AND sy.median_weekly_rent IS NOT NULL\n"
            "  AND sy.median_household_income IS NOT NULL\n"
            "  AND s.population_2023 > 500\n"
            "ORDER BY 2 ASC\n"
            "LIMIT 25"
        ),
    },
    {
        "name": "ds_bar_crowd",
        "displayName": "Bar: 25 least crowded suburbs",
        "query": (
            "SELECT s.suburb_name,\n"
            "  ROUND(sy.percent_crowded * 100, 1) AS percent_crowded\n"
            "FROM housing.gold.suburb__year sy\n"
            "JOIN housing.gold.suburb s ON s.suburb_id = sy.suburb_id\n"
            "WHERE sy.census_year = 2023\n"
            "  AND sy.percent_crowded IS NOT NULL\n"
            "  AND s.population_2023 > 500\n"
            "ORDER BY 2 ASC\n"
            "LIMIT 25"
        ),
    },
    {
        "name": "ds_bar_crime",
        "displayName": "Bar: 25 safest suburbs by crime reports",
        "query": (
            "SELECT s.suburb_name, sc.total_victimisations AS suburb_annual_crime\n"
            "FROM housing.silver.crime_at_suburb_year sc\n"
            "JOIN housing.gold.suburb s ON s.suburb_id = sc.suburb_id\n"
            "WHERE sc.crime_year = 2025\n"
            "  AND sc.total_victimisations IS NOT NULL\n"
            "  AND s.population_2023 > 500\n"
            "ORDER BY 2 ASC\n"
            "LIMIT 25"
        ),
    },
    {
        "name": "ds_bar_schools",
        "displayName": "Bar: 25 suburbs with most schools nearby",
        "query": (
            "SELECT s.suburb_name,\n"
            "  COUNT(CASE WHEN a.amenity_type IN ('school','early_childhood') THEN 1 END) AS education_nearby\n"
            "FROM housing.gold.suburb s\n"
            "LEFT JOIN housing.gold.amenity__h3 a ON a.suburb_id = s.suburb_id\n"
            "WHERE s.population_2023 > 500\n"
            "GROUP BY s.suburb_name\n"
            "ORDER BY 2 DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "name": "ds_bar_transit",
        "displayName": "Bar: 25 suburbs with most transit stops",
        "query": (
            "SELECT s.suburb_name, COUNT(DISTINCT ts.stop_id) AS transit_stops\n"
            "FROM housing.gold.suburb s\n"
            "LEFT JOIN housing.gold.h3_cell hc ON hc.suburb_id = s.suburb_id\n"
            "LEFT JOIN housing.gold.transit_stop ts ON ts.h3_cell = hc.h3_cell\n"
            "WHERE s.population_2023 > 500\n"
            "GROUP BY s.suburb_name\n"
            "ORDER BY 2 DESC\n"
            "LIMIT 25"
        ),
    },
]

# ── page layout ────────────────────────────────────────────────────────────

DS = "ds_suburb_sarah"

layout = []

def place(x, y, w, h, widget):
    layout.append({"position": pos(x, y, w, h), "widget": widget})


# Row 0 — filters: budget | region | TA
place(0, 0, 2, 1, filter_widget("w_f_budget",  "q_f_budget",  DS, "rent_bucket",           "Weekly Rent Budget", "My budget"))
place(2, 0, 2, 1, filter_widget("w_f_region",  "q_f_region",  DS, "region",                "Region",             "Region"))
place(4, 0, 2, 1, filter_widget("w_f_ta",      "q_f_ta",      DS, "territorial_authority", "City / District",    "City / District"))

# Row 1 — filters: flood | schools | good transit
place(0, 1, 2, 1, filter_widget("w_f_flood",   "q_f_flood",   DS, "flood_plain",  "Flood Zone?",            "Flood zone?"))
place(2, 1, 2, 1, filter_widget("w_f_schools", "q_f_schools", DS, "has_schools",  "Schools nearby?",        "Schools nearby?"))
place(4, 1, 2, 1, filter_widget("w_f_transit", "q_f_transit", DS, "good_transit", "Good transit (5+ stops)?","Good transit?"))

# Row 2–9 — main sortable table
TABLE_COLS = [
    {"fieldName": "suburb_name",           "title": "Suburb",              "type": "string"},
    {"fieldName": "territorial_authority", "title": "City / District",     "type": "string"},
    {"fieldName": "region",                "title": "Region",              "type": "string"},
    {"fieldName": "median_weekly_rent",    "title": "Weekly Rent ($)",     "type": "float",   "alignContent": "right"},
    {"fieldName": "rent_to_income_pct",    "title": "Rent % of Income",    "type": "float",   "alignContent": "right"},
    {"fieldName": "flood_plain",           "title": "Flood Zone?",         "type": "string"},
    {"fieldName": "coastal_risk",          "title": "Coastal Risk?",       "type": "string"},
    {"fieldName": "suburb_annual_crime",   "title": "Crime (annual)",      "type": "float",   "alignContent": "right"},
    {"fieldName": "education_nearby",      "title": "Schools Nearby",      "type": "integer", "alignContent": "right"},
    {"fieldName": "supermarkets_nearby",   "title": "Supermarkets",        "type": "integer", "alignContent": "right"},
    {"fieldName": "transit_stops",         "title": "Transit Stops",       "type": "integer", "alignContent": "right"},
    {"fieldName": "owner_occupier_pct",    "title": "Owner Occupied (%)",  "type": "float",   "alignContent": "right"},
    {"fieldName": "percent_crowded",       "title": "Crowded Homes (%)",   "type": "float",   "alignContent": "right"},
    {"fieldName": "population_2023",       "title": "Population (2023)",   "type": "integer", "alignContent": "right"},
]
place(0, 2, 6, 8, table_widget(
    "w_main_tbl", "main_query", DS, TABLE_COLS,
    "Matching suburbs — click any column header to sort"
))

# Row 10–11 — counters: avg rent | avg rent-to-income | suburb count
place(0, 10, 2, 2, counter_widget(
    "w_c_rent", "q_c_rent", DS,
    "ROUND(AVG(`median_weekly_rent`), 0)", "avg_rent",
    "Avg weekly rent ($)", "Avg weekly rent"
))
place(2, 10, 2, 2, counter_widget(
    "w_c_afford", "q_c_afford", DS,
    "ROUND(AVG(`rent_to_income_pct`), 1)", "avg_afford",
    "Avg rent-to-income (%)", "Avg rent-to-income"
))
place(4, 10, 2, 2, counter_widget(
    "w_c_count", "q_c_count", DS,
    "COUNT(*)", "suburb_count",
    "Matching suburbs", "Suburbs matching filters"
))

# Row 12–16 — scatter: rent-to-income vs crime (shows affordability/safety tradeoff)
place(0, 12, 4, 5, scatter_widget(
    "w_scatter_rti_crime", "q_scatter_rti_crime", "ds_scatter_rti_crime",
    "rent_to_income_pct", "suburb_annual_crime", "region", "suburb_name",
    "Rent as % of income", "Annual crime reports", "Region",
    "Affordability vs safety by region (bottom-left = best)"
))
# Vertical bar: least overcrowded
place(4, 12, 2, 5, bar_widget(
    "w_bar_crowd", "ds_bar_crowd",
    "MAX(`percent_crowded`)", "max(percent_crowded)",
    "Crowded homes (%)", "Least overcrowded suburbs"
))

# Row 17–21 — horizontal bars: cheapest rent | most schools
place(0, 17, 3, 5, bar_widget(
    "w_bar_rent", "ds_bar_rent",
    "MAX(`median_weekly_rent`)", "max(median_weekly_rent)",
    "Weekly Rent ($)", "Cheapest suburbs", horizontal=True
))
place(3, 17, 3, 5, bar_widget(
    "w_bar_schools", "ds_bar_schools",
    "MAX(`education_nearby`)", "max(education_nearby)",
    "Schools & ECE centres", "Most schools nearby", horizontal=True
))

# Row 22–26 — horizontal bars: best affordability ratio | best transit
place(0, 22, 3, 5, bar_widget(
    "w_bar_afford", "ds_bar_afford",
    "MAX(`rent_to_income_pct`)", "max(rent_to_income_pct)",
    "Rent as % of income", "Most affordable (rent vs income)", horizontal=True
))
place(3, 22, 3, 5, bar_widget(
    "w_bar_transit", "ds_bar_transit",
    "MAX(`transit_stops`)", "max(transit_stops)",
    "Public transport stops", "Best connected suburbs", horizontal=True
))

# Row 27–32 — geographic scatter plots (lat/lon) replacing point-map
# point-map shows "Visualization has no fields selected" in this workspace despite valid spec.
# Scatter on raw lat/lon coordinates shows geographic distribution by type.
# group_col=name/stop_name keeps points distinct; disaggregated:false + MAX satisfies Lakeview.
place(0, 27, 3, 6, scatter_widget(
    "w_scatter_amenities", "q_scatter_amenities", "ds_amenities_scatter",
    "lon", "lat", "amenity_type", "name",
    "Longitude", "Latitude", "Amenity Type",
    "Amenity locations by type"
))
place(3, 27, 3, 6, scatter_widget(
    "w_scatter_transit", "q_scatter_transit", "ds_transit_scatter",
    "stop_lon", "stop_lat", "feed_source", "stop_name",
    "Longitude", "Latitude", "Transit Network",
    "Transit stop locations by network"
))

# ── assemble and write ─────────────────────────────────────────────────────

dashboard = {
    "datasets": DATASETS,
    "pages": [{
        "name": "p_main",
        "displayName": "Suburb Finder",
        "layout": layout,
    }],
}

with open(PATH, "w") as f:
    json.dump(dashboard, f, indent=2)

with open(PATH) as f:
    d = json.load(f)

widgets = d["pages"][0]["layout"]
types = {}
for item in widgets:
    w = item["widget"]
    wt = w.get("spec", {}).get("widgetType", "textbox")
    types[wt] = types.get(wt, 0) + 1

print(f"JSON valid — 1 page, {len(widgets)} widgets")
print("Widget types:", dict(sorted(types.items())))
