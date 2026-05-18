"""Rewrite all bar chart widgets to use dedicated small datasets + disaggregated:false + explicit aggregation."""
import json

path = r"C:\Users\IsabelBody-DataAnaly\housing-assistant\dashboards\planner\dashboard.lvdash.json"

with open(path) as f:
    dash = json.load(f)

# --- Bar chart widget replacements ---
# Each entry: (widget_name, query_name, dataset, x_col, y_expr, y_name, y_display, title)
BAR_SPECS = [
    (
        "w_p1_bar_rent",
        "main_query",
        "ds_bar_rent",
        "suburb_name",
        "MAX(`median_weekly_rent`)", "max(median_weekly_rent)",
        "Weekly Rent ($)", "Weekly Rent ($)",
        "Most affordable suburbs (cheapest first)",
    ),
    (
        "w_p2_bar_rent",
        "main_query",
        "ds_bar_rent",
        "suburb_name",
        "MAX(`median_weekly_rent`)", "max(median_weekly_rent)",
        "Weekly Rent ($)", "Weekly Rent ($)",
        "Cheapest suburbs first",
    ),
    (
        "w_p2_bar_afford",
        "main_query",
        "ds_bar_afford",
        "suburb_name",
        "MAX(`rent_to_income_pct`)", "max(rent_to_income_pct)",
        "Rent as % of local income", "Rent as % of local income",
        "Most affordable suburbs (lower % = better value)",
    ),
    (
        "w_p2_bar_crowd",
        "main_query",
        "ds_bar_crowd",
        "suburb_name",
        "MAX(`percent_crowded`)", "max(percent_crowded)",
        "% of homes overcrowded", "% of homes overcrowded",
        "Least overcrowded suburbs (lower = better)",
    ),
    (
        "w_p2_bar_damp",
        "main_query",
        "ds_bar_damp",
        "suburb_name",
        "MAX(`pct_always_damp`)", "max(pct_always_damp)",
        "% of homes with damp issues", "% of homes with damp issues",
        "Suburbs with fewest damp homes (lower = better quality)",
    ),
    (
        "w_p3_bar_crime",
        "main_query",
        "ds_bar_crime",
        "suburb_name",
        "MAX(`suburb_annual_crime`)", "max(suburb_annual_crime)",
        "Crime reports (2025)", "Crime reports (2025)",
        "Suburbs with fewest crime reports (2025, lowest = safer)",
    ),
    (
        "w_p4_bar_schools",
        "main_query",
        "ds_bar_schools",
        "suburb_name",
        "MAX(`education_nearby`)", "max(education_nearby)",
        "Schools and early childhood centres", "Schools and early childhood centres",
        "Suburbs with the most schools nearby",
    ),
    (
        "w_p4_bar_transit",
        "main_query",
        "ds_bar_transit",
        "suburb_name",
        "MAX(`transit_stops`)", "max(transit_stops)",
        "Public transport stops", "Public transport stops",
        "Best connected suburbs for public transport",
    ),
]

def make_bar_widget(name, qname, dataset, x_col, y_expr, y_name, y_display, y_axis, title):
    return {
        "name": name,
        "queries": [
            {
                "name": qname,
                "query": {
                    "datasetName": dataset,
                    "disaggregated": False,
                    "fields": [
                        {"expression": f"`{x_col}`", "name": x_col},
                        {"expression": y_expr, "name": y_name},
                    ],
                },
            }
        ],
        "spec": {
            "widgetType": "bar",
            "version": 3,
            "encodings": {
                "x": {
                    "displayName": "Suburb",
                    "fieldName": x_col,
                    "scale": {"type": "categorical"},
                    "axis": {"title": "Suburb"},
                },
                "y": {
                    "displayName": y_display,
                    "fieldName": y_name,
                    "scale": {"type": "quantitative"},
                    "axis": {"title": y_axis},
                },
                "label": {"show": False},
            },
            "frame": {"showTitle": True, "title": title},
        },
    }

# Build lookup of desired widgets by name
desired = {}
for spec in BAR_SPECS:
    name, qname, dataset, x_col, y_expr, y_name, y_display, y_axis, title = spec
    desired[name] = make_bar_widget(name, qname, dataset, x_col, y_expr, y_name, y_display, y_axis, title)

replaced = 0
for page in dash["pages"]:
    for item in page["layout"]:
        widget = item["widget"]
        wname = widget.get("name")
        if wname in desired:
            item["widget"] = desired[wname]
            replaced += 1
            print(f"  Replaced {wname}")

print(f"\nReplaced {replaced} / {len(desired)} bar chart widgets")

with open(path, "w") as f:
    json.dump(dash, f, indent=2)

# Validate
with open(path) as f:
    json.load(f)
print("JSON valid")
