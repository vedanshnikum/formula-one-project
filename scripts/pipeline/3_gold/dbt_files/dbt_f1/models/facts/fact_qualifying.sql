select
    r.race_key,
    year(r.race_date)                   as year,
    concat(d.forename, ' ', d.surname)  as driver_full_name,
    q.driverid                          as driver_id,
    t.name                              as team_name,
    q.constructorid                     as team_id,
    q.number                            as car_number,
    q.position                          as qualifying_position,
    q.q1                                as q1_ms,
    q.q2                                as q2_ms,
    q.q3                                as q3_ms
from {{ source('silver', 'race_data_qualifying') }} q
join {{ ref('dim_races') }} r
    on q.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on q.driverid = d.driverid
join {{ source('silver', 'race_data_constructors') }} t
    on q.constructorid = t.constructorid