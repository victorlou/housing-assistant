-- Suburb profile from 2023 Census: joined income, tenure, and dwelling quality
-- Excludes low-population SA2s (population <= 500) to filter out water/EEZ cells
SELECT
  s.suburb_id,
  s.suburb_name,
  s.territorial_authority,
  s.region,
  s.population_2023,
  s.median_age_2023,
  s.land_area_km2,
  i.median_household_income,
  t.owner_occupier_pct,
  d.percent_crowded,
  d.dwellings_no_heating,
  d.dwellings_mean_rooms,
  ROUND(
    d.dwellings_always_damp * 100.0
      / NULLIF(d.dwellings_damp_total_stated, 0),
    1
  ) AS pct_always_damp
FROM housing.gold.suburb s
LEFT JOIN housing.gold.income__year__suburb  i
  ON i.sa2_code = s.suburb_id AND i.census_year = 2023
LEFT JOIN housing.gold.tenure__year__suburb  t
  ON t.sa2_code = s.suburb_id AND t.census_year = 2023
LEFT JOIN housing.gold.dwelling__year__suburb d
  ON d.sa2_code = s.suburb_id AND d.census_year = 2023
WHERE s.population_2023 > 500
ORDER BY s.region, s.territorial_authority, s.suburb_name
