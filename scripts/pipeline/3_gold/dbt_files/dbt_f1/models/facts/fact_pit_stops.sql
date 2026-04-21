select
    r.race_key,
    year(r.race_date)                   as year,
    concat(d.forename, ' ', d.surname)  as driver_full_name,
    ps.driverid                         as driver_id,
    ps.stop                             as stop_number,
    ps.lap,
    ps.duration                         as duration_ms,
    ps.milliseconds                     as total_elapsed_ms
from {{ source('silver', 'race_data_pit_stops') }} ps
join {{ ref('dim_races') }} r
    on ps.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on ps.driverid = d.driverid