-- Affordability indices by TA, quarterly from 2001-Q1 to present
-- Used for Affordability Trends page line charts
-- Higher index = less affordable
SELECT
  ta_name,
  quarter,
  quarter_label,
  deposit_affordability_index,
  mortgage_affordability_index,
  rent_affordability_index,
  median_to_median_ratio
FROM housing.gold.ta__quarter
WHERE ta_name != 'New Zealand'
ORDER BY ta_name, quarter
