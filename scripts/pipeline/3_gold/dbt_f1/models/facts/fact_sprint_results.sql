select
    r.race_key,
    r.year,
    concat(d.forename, ' ', d.surname)      as driver_full_name,
    sr.driverid                             as driver_id,
    t.name                                  as team_name,
    sr.constructorid                        as team_id,
    sr.number                               as car_number,
    sr.grid                                 as grid_position,
    sr.position                             as finish_position,
    sr.positionorder                        as position_order,
    sr.points,
    sr.laps,
    sr.milliseconds                         as race_time_ms,
    sr.fastestlap                           as fastest_lap_number,
    sr.fastestlaptime                       as fastest_lap_time_ms,
    s.status,
    case
        when sr.positiontext not rlike '^[0-9]+$' then true
        else false
    end                                     as dnf_flag,
    sr.grid - sr.positionorder              as positions_gained
from {{ source('silver', 'race_data_sprint_results') }} sr
join {{ ref('dim_races') }} r
    on sr.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on sr.driverid = d.driverid
join {{ source('silver', 'race_data_constructors') }} t
    on sr.constructorid = t.constructorid
join {{ source('silver', 'race_data_status') }} s
    on sr.statusid = s.statusid