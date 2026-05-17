-- Latest snapshot per TA: used for Overview page bar charts
-- Returns one row per TA with the most recent non-null value for each metric
-- Excludes the synthetic 'New Zealand' rollup row
SELECT
  ta_name,
  MAX(date)                                          AS snapshot_date,
  MAX_BY(current_annual_median_sales_nzd, date)      AS median_price_nzd,
  MAX_BY(current_annual_lower_q_sales_nzd, date)     AS lower_q_price_nzd,
  MAX_BY(annual_sales_volume, date)                  AS sales_volume,
  MAX_BY(median_rent_nzd, date)                      AS median_rent_nzd,
  MAX_BY(lower_quartile_rent_nzd, date)              AS lower_q_rent_nzd,
  MAX_BY(housing_register, date)                     AS housing_register,
  MAX_BY(housing_register_per_10k_pop, date)         AS register_per_10k
FROM housing.gold.ta__month
WHERE ta_name != 'New Zealand'
  AND (current_annual_median_sales_nzd IS NOT NULL
    OR median_rent_nzd IS NOT NULL
    OR housing_register IS NOT NULL)
GROUP BY ta_name
ORDER BY median_price_nzd DESC NULLS LAST
