-- Cliff Watch: TAs where rent affordability has worsened fastest over the trailing 4 quarters
-- Uses the rent_affordability_index from ta__quarter (higher index = rent takes larger share of income)
-- Z-score > 2 = CLIFF (>2 SD above national mean change), 1-2 = WATCH, <-1 = EASING
WITH indexed AS (
  SELECT
    ta_name,
    quarter,
    rent_affordability_index,
    LAG(rent_affordability_index, 4) OVER (
      PARTITION BY ta_name ORDER BY quarter
    ) AS index_4q_ago
  FROM housing.gold.ta__quarter
  WHERE ta_name != 'New Zealand'
    AND rent_affordability_index IS NOT NULL
),
changes AS (
  SELECT
    ta_name,
    quarter,
    rent_affordability_index,
    index_4q_ago,
    rent_affordability_index - index_4q_ago AS trailing_4q_change
  FROM indexed
  WHERE index_4q_ago IS NOT NULL
),
latest AS (
  SELECT
    ta_name,
    MAX_BY(rent_affordability_index, quarter) AS current_index,
    MAX_BY(trailing_4q_change, quarter)       AS trailing_4q_change,
    MAX(quarter)                              AS latest_quarter
  FROM changes
  GROUP BY ta_name
),
stats AS (
  SELECT
    AVG(trailing_4q_change)    AS mean_change,
    STDDEV(trailing_4q_change) AS stddev_change
  FROM latest
)
SELECT
  l.ta_name,
  l.current_index,
  l.trailing_4q_change,
  l.latest_quarter,
  s.mean_change,
  s.stddev_change,
  ROUND((l.trailing_4q_change - s.mean_change) / NULLIF(s.stddev_change, 0), 2) AS z_score,
  CASE
    WHEN (l.trailing_4q_change - s.mean_change) / NULLIF(s.stddev_change, 0) > 2  THEN 'CLIFF'
    WHEN (l.trailing_4q_change - s.mean_change) / NULLIF(s.stddev_change, 0) > 1  THEN 'WATCH'
    WHEN (l.trailing_4q_change - s.mean_change) / NULLIF(s.stddev_change, 0) < -1 THEN 'EASING'
    ELSE 'STABLE'
  END AS cliff_status
FROM latest l
CROSS JOIN stats s
ORDER BY z_score DESC NULLS LAST
