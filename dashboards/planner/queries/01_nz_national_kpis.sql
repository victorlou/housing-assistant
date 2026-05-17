-- NZ national KPIs: single row with latest values for the 4 dashboard counters
-- Source: housing.gold.ta__month (ta_name = 'New Zealand' rollup row)
SELECT
  MAX_BY(current_annual_median_sales_nzd, date) AS median_price_nzd,
  MAX_BY(median_rent_nzd, date)                 AS median_rent_nzd,
  MAX_BY(housing_register, date)                AS housing_register,
  MAX_BY(housing_register_per_10k_pop, date)    AS register_per_10k
FROM housing.gold.ta__month
WHERE ta_name = 'New Zealand'
