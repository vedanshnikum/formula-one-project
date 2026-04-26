select
    r.race_key,
    r.year,
    concat(d.forename, ' ', d.surname)  as driver_full_name,
    lt.driverid                         as driver_id,
    lt.lap,
    lt.position                         as lap_position,
    lt.milliseconds                     as lap_time_ms
from {{ source('silver', 'race_data_lap_times') }} lt
join {{ ref('dim_races') }} r
    on lt.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on lt.driverid = d.driverid