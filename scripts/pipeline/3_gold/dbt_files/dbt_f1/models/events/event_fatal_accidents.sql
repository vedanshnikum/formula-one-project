select
    driver                  as name,
    age,
    date_of_accident,
    event,
    car,
    session,
    'Driver'                as type
from {{ source('silver', 'race_events_fatal_accidents_drivers') }}

union all

select
    name,
    age,
    date_of_accident,
    event,
    cast(null as string)    as car,
    cast(null as string)    as session,
    'Marshal'               as type
from {{ source('silver', 'race_events_fatal_accidents_marshalls') }}