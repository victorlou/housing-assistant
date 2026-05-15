with stg as (

  select * from {{ ref('stg_linz__addresses') }}

),

deduped as (

  select
    address_id,
    change_id,
    lifecycle_phase,
    full_address_ascii,
    suburb_locality_ascii,
    town_city_ascii,
    territorial_authority_ascii,
    latitude,
    longitude
  from stg
  where address_id is not null
  qualify row_number() over (
    partition by address_id
    order by change_id desc nulls last
  ) = 1

),

with_h3 as (

  select
    *,
    case
      when
        latitude is not null
        and longitude is not null
        and latitude between -47.5 and -34.0
        and longitude between 165.5 and 179.5
        then h3_longlatash3string(longitude, latitude, 8)
    end as h3_8
  from deduped

)

select * from with_h3
