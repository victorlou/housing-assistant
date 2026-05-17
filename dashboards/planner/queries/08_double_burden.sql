-- Double burden: suburbs in the bottom income quartile that also have flood-plain exposure
-- Joins suburb + income (census 2023) + h3_cell bridge + hazard tables
-- Income quartile 1 = lowest 25% of NZ suburbs by median household income
WITH suburb_income AS (
  SELECT
    s.suburb_id,
    s.suburb_name,
    s.territorial_authority,
    s.region,
    s.population_2023,
    i.median_household_income
  FROM housing.gold.suburb s
  JOIN housing.gold.income__year__suburb i
    ON i.sa2_code = s.suburb_id AND i.census_year = 2023
  WHERE s.population_2023 > 500
    AND i.median_household_income IS NOT NULL
),
with_quartile AS (
  SELECT
    *,
    NTILE(4) OVER (ORDER BY median_household_income) AS income_quartile
  FROM suburb_income
),
suburb_flood AS (
  SELECT
    hc.suburb_id,
    COUNT(*)                                               AS total_h3_cells,
    SUM(CASE WHEN hz.in_flood_plain THEN 1 ELSE 0 END)    AS flood_h3_cells
  FROM housing.gold.h3_cell hc
  JOIN housing.gold.hazard hz ON hz.h3_cell = hc.h3_cell
  GROUP BY hc.suburb_id
)
SELECT
  wq.suburb_id,
  wq.suburb_name,
  wq.territorial_authority,
  wq.region,
  wq.population_2023,
  wq.median_household_income,
  wq.income_quartile,
  COALESCE(sf.flood_h3_cells, 0)  AS flood_h3_cells,
  COALESCE(sf.total_h3_cells, 0)  AS total_h3_cells,
  CASE WHEN COALESCE(sf.flood_h3_cells, 0) > 0 THEN TRUE ELSE FALSE END AS has_flood_exposure,
  CASE
    WHEN wq.income_quartile = 1
      AND COALESCE(sf.flood_h3_cells, 0) > 0 THEN TRUE
    ELSE FALSE
  END AS double_burden
FROM with_quartile wq
LEFT JOIN suburb_flood sf ON sf.suburb_id = wq.suburb_id
ORDER BY double_burden DESC, wq.income_quartile, wq.median_household_income
