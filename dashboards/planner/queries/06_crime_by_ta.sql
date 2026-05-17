-- Crime aggregated to TA + month + ANZSOC division
-- Source: housing.gold.crime__month__area_unit (area-unit grain rolled up to TA)
SELECT
  report_month,
  territorial_authority,
  anzsoc_division,
  SUM(victimisation_count) AS victimisations
FROM housing.gold.crime__month__area_unit
GROUP BY report_month, territorial_authority, anzsoc_division
ORDER BY territorial_authority, report_month
