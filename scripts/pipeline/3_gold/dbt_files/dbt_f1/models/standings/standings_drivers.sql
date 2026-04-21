select
    r.race_key,
    year(r.race_date)                       as year,
    concat(d.forename, ' ', d.surname)      as driver_full_name,
    ds.driverid                             as driver_id,
    ds.points,
    ds.position,
    ds.wins
from {{ source('silver', 'race_data_driver_standings') }} ds
join {{ ref('dim_races') }} r
    on ds.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on ds.driverid = d.driverid