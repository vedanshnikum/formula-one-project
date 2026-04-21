select
    circuitid                as circuit_id,
    circuitref               as circuit_ref,
    name                     as circuit_name,
    location                 as city,
    country,
    lat                      as latitude,
    lng                      as longitude,
    alt                      as altitude_meters
from {{ source('silver', 'race_data_circuits') }}