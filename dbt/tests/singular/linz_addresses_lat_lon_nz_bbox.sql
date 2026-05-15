-- Fails if any row has coordinates outside an approximate NZ bounding box.
select *
from {{ ref('linz_addresses') }}
where
  latitude is not null
  and longitude is not null
  and (
    latitude < -47.5
    or latitude > -34.0
    or longitude < 165.5
    or longitude > 179.5
  )
