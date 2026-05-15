with source as (

  select * from {{ source('bronze', 'linz_nz_addresses_features') }}

),

normalised as (

  select
    try_cast(address_id as bigint) as address_id,
    try_cast(change_id as bigint) as change_id,
    nullif(trim(lifecycle_phase), '') as lifecycle_phase,
    nullif(trim(full_address_ascii), '') as full_address_ascii,
    nullif(trim(suburb_locality_ascii), '') as suburb_locality_ascii,
    nullif(trim(town_city_ascii), '') as town_city_ascii,
    nullif(trim(territorial_authority_ascii), '') as territorial_authority_ascii,
    try_cast(latitude as double) as latitude,
    try_cast(longitude as double) as longitude

  from source

)

select * from normalised
