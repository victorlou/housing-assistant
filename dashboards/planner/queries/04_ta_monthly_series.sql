-- TA monthly time series: used for Price & Rent Series page
-- Sparse by design - Sales/Bonds rows only on HUD snapshot dates; MSD rows monthly
SELECT
  ta_name,
  date,
  current_hpi,
  current_annual_median_sales_nzd,
  annual_sales_volume,
  median_rent_nzd,
  lower_quartile_rent_nzd,
  housing_register,
  housing_register_per_10k_pop
FROM housing.gold.ta__month
WHERE ta_name != 'New Zealand'
ORDER BY ta_name, date
