"""Rebuild dashboard.lvdash.json as a single-page layout."""
import json, copy

path = r"C:\Users\IsabelBody-DataAnaly\housing-assistant\dashboards\planner\dashboard.lvdash.json"

with open(path) as f:
    dash = json.load(f)

# ── helpers ────────────────────────────────────────────────────────────────

def pos(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}

def textbox(name, md):
    return {"name": name, "textbox_spec": md}

def filter_widget(name, qname, dataset, col, display, title, disagg=False):
    return {
        "name": name,
        "queries": [{
            "name": qname,
            "query": {
                "datasetName": dataset,
                "disaggregated": disagg,
                "fields": [
                    {"expression": f"`{col}`", "name": col},
                    {"expression": "COUNT(*)", "name": "n"},
                ],
            },
        }],
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

def table_widget(name, qname, dataset, fields, columns, title):
    """fields: list of col names; columns: list of dicts with fieldName/title/type/etc."""
    return {
        "name": name,
        "queries": [{
            "name": qname,
            "query": {
                "datasetName": dataset,
                "disaggregated": True,
                "fields": [{"expression": f"`{f}`", "name": f} for f in fields],
            },
        }],
        "spec": {
            "widgetType": "table",
            "version": 2,
            "condensed": True,
            "allowHTMLByDefault": False,
            "encodings": {"columns": columns},
            "frame": {"showTitle": True, "title": title},
        },
    }

def bar_widget(name, dataset, y_expr, y_name, y_display, title):
    return {
        "name": name,
        "queries": [{
            "name": "main_query",
            "query": {
                "datasetName": dataset,
                "disaggregated": False,
                "fields": [
                    {"expression": "`suburb_name`", "name": "suburb_name"},
                    {"expression": y_expr, "name": y_name},
                ],
            },
        }],
        "spec": {
            "widgetType": "bar",
            "version": 3,
            "encodings": {
                "x": {"displayName": "Suburb", "fieldName": "suburb_name",
                      "scale": {"type": "categorical"}, "axis": {"title": "Suburb"}},
                "y": {"displayName": y_display, "fieldName": y_name,
                      "scale": {"type": "quantitative"}, "axis": {"title": y_display}},
                "label": {"show": False},
            },
            "frame": {"showTitle": True, "title": title},
        },
    }

def map_widget(name, qname, dataset, lat_expr, lon_expr, color_col, color_display,
               label_col, title):
    return {
        "name": name,
        "queries": [{
            "name": qname,
            "query": {
                "datasetName": dataset,
                "disaggregated": True,
                "fields": [
                    {"expression": lat_expr, "name": "latitude"},
                    {"expression": lon_expr, "name": "longitude"},
                    {"expression": f"`{color_col}`", "name": color_col},
                    {"expression": f"`{label_col}`", "name": label_col},
                ],
            },
        }],
        "spec": {
            "widgetType": "point-map",
            "version": 1,
            "encodings": {
                "latitude":  {"fieldName": "latitude",  "queryName": qname},
                "longitude": {"fieldName": "longitude", "queryName": qname},
                "color":     {"fieldName": color_col, "displayName": color_display,
                              "queryName": qname},
                "label":     {"fieldName": label_col, "queryName": qname},
            },
            "frame": {"showTitle": True, "title": title},
        },
    }

# ── layout ─────────────────────────────────────────────────────────────────
# Grid: 6 columns.  y grows downward.

layout = []

def place(x, y, w, h, widget):
    layout.append({"position": pos(x, y, w, h), "widget": widget})

DS = "ds_suburb_sarah"

# Row 0 — title
place(0, 0, 6, 1, textbox("w_title",
    "## NZ Housing Affordability — Suburb Finder\n"
    "Filter by budget, region or hazard to narrow the suburb table. "
    "Scroll down for rent, affordability, safety and amenity charts."
))

# Row 1 — filters: budget | region | TA
place(0, 1, 2, 1, filter_widget("w_f_budget",   "q_f_budget",   DS, "rent_bucket",          "Weekly Rent Budget",  "My budget"))
place(2, 1, 2, 1, filter_widget("w_f_region",   "q_f_region",   DS, "region",               "Region",              "Region"))
place(4, 1, 2, 1, filter_widget("w_f_ta",       "q_f_ta",       DS, "territorial_authority","City / District",     "City / District"))

# Row 2 — filters: flood | schools | transit
place(0, 2, 2, 1, filter_widget("w_f_flood",    "q_f_flood",    DS, "flood_plain",          "Flood Zone?",         "Flood zone?"))
place(2, 2, 2, 1, filter_widget("w_f_schools",  "q_f_schools",  DS, "has_schools",          "Schools nearby?",     "Schools nearby?"))
place(4, 2, 2, 1, filter_widget("w_f_transit",  "q_f_transit",  DS, "good_transit",         "Good transit?",       "Good transit (5+ stops)?"))

# Row 3–10 — main table (all key columns)
main_cols = [
    {"fieldName": "suburb_name",          "title": "Suburb",                 "type": "string",  "visible": True, "order": 0},
    {"fieldName": "territorial_authority","title": "City / District",         "type": "string",  "visible": True, "order": 1},
    {"fieldName": "region",               "title": "Region",                  "type": "string",  "visible": True, "order": 2},
    {"fieldName": "median_weekly_rent",   "title": "Weekly Rent ($)",         "type": "float",   "visible": True, "order": 3,  "alignContent": "right"},
    {"fieldName": "rent_to_income_pct",   "title": "Rent % of Income",        "type": "float",   "visible": True, "order": 4,  "alignContent": "right"},
    {"fieldName": "flood_plain",          "title": "Flood Zone?",             "type": "string",  "visible": True, "order": 5},
    {"fieldName": "coastal_risk",         "title": "Coastal Risk?",           "type": "string",  "visible": True, "order": 6},
    {"fieldName": "suburb_annual_crime",  "title": "Crime (annual)",          "type": "float",   "visible": True, "order": 7,  "alignContent": "right"},
    {"fieldName": "education_nearby",     "title": "Schools Nearby",          "type": "integer", "visible": True, "order": 8,  "alignContent": "right"},
    {"fieldName": "supermarkets_nearby",  "title": "Supermarkets",            "type": "integer", "visible": True, "order": 9,  "alignContent": "right"},
    {"fieldName": "transit_stops",        "title": "Transit Stops",           "type": "integer", "visible": True, "order": 10, "alignContent": "right"},
    {"fieldName": "owner_occupier_pct",   "title": "Owner Occupied (%)",      "type": "float",   "visible": True, "order": 11, "alignContent": "right"},
    {"fieldName": "percent_crowded",      "title": "Crowded Homes (%)",       "type": "float",   "visible": True, "order": 12, "alignContent": "right"},
    {"fieldName": "population_2023",      "title": "Population (2023)",       "type": "integer", "visible": True, "order": 13, "alignContent": "right"},
]
main_fields = [c["fieldName"] for c in main_cols]

place(0, 3, 6, 8, table_widget(
    "w_main_tbl", "main_query", DS, main_fields, main_cols,
    "Matching suburbs — click any column header to sort"
))

# Row 11–15 — rent | affordability
place(0, 11, 3, 5, bar_widget("w_bar_rent",   "ds_bar_rent",   "MAX(`median_weekly_rent`)", "max(median_weekly_rent)", "Weekly Rent ($)",          "Cheapest suburbs"))
place(3, 11, 3, 5, bar_widget("w_bar_afford", "ds_bar_afford", "MAX(`rent_to_income_pct`)", "max(rent_to_income_pct)", "Rent as % of income",      "Most affordable (rent vs income)"))

# Row 16–20 — crime | crowding
place(0, 16, 3, 5, bar_widget("w_bar_crime",  "ds_bar_crime",  "MAX(`suburb_annual_crime`)","max(suburb_annual_crime)","Crime reports (2025)",     "Safest suburbs"))
place(3, 16, 3, 5, bar_widget("w_bar_crowd",  "ds_bar_crowd",  "MAX(`percent_crowded`)",   "max(percent_crowded)",    "Crowded homes (%)",        "Least overcrowded"))

# Row 21–27 — amenities map (4) | transit map (2)
place(0, 21, 4, 7, map_widget(
    "w_map_am", "q_map_am", "ds_amenities_map",
    "`lat`", "`lon`", "amenity_type", "Amenity Type", "name",
    "Schools, shops, parks and health services"
))
place(4, 21, 2, 7, map_widget(
    "w_map_tr", "q_map_tr", "ds_transit_map",
    "`stop_lat`", "`stop_lon`", "feed_source", "Transit Network", "stop_name",
    "Public transport stops"
))

# Row 28–32 — schools | transit
place(0, 28, 3, 5, bar_widget("w_bar_schools", "ds_bar_schools", "MAX(`education_nearby`)", "max(education_nearby)", "Schools & ECE centres",  "Most schools nearby"))
place(3, 28, 3, 5, bar_widget("w_bar_transit", "ds_bar_transit", "MAX(`transit_stops`)",    "max(transit_stops)",    "Public transport stops", "Best connected suburbs"))

# ── write ──────────────────────────────────────────────────────────────────

dash["pages"] = [{
    "name": "p_main",
    "displayName": "Suburb Finder",
    "layout": layout,
}]

with open(path, "w") as f:
    json.dump(dash, f, indent=2)

# validate
with open(path) as f:
    d = json.load(f)
print(f"JSON valid — {len(d['pages'])} page, {len(d['pages'][0]['layout'])} widgets")
