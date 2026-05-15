select
  address_id,
  full_address_ascii,
  suburb_locality_ascii,
  town_city_ascii,
  territorial_authority_ascii,
  latitude,
  longitude,
  h3_8,
  lifecycle_phase
from {{ ref('linz_addresses') }}
