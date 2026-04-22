with pit_aggregates as (
    select
        race_key,
        driver_id,
        count(*)            as pit_stop_count,
        sum(duration_ms)    as total_pit_time_ms
    from {{ ref('fact_pit_stops') }}
    group by race_key, driver_id
)

select
    r.race_key,
    r.year,
    concat(d.forename, ' ', d.surname)      as driver_full_name,
    res.driverid                            as driver_id,
    t.name                                  as team_name,
    res.constructorid                       as team_id,
    res.number                              as car_number,
    res.grid                                as grid_position,
    res.position                            as finish_position,
    res.positionorder                       as position_order,
    res.points,
    res.laps,
    res.milliseconds                        as race_time_ms,
    res.fastestlap                          as fastest_lap_number,
    res.rank                                as fastest_lap_rank,
    res.fastestlapspeed                     as fastest_lap_speed,
    s.status,
    case
        when res.positiontext not rlike '^[0-9]+$' then true
        else false
    end                                     as dnf_flag,
    res.grid - res.positionorder            as positions_gained,
    coalesce(pa.pit_stop_count, 0)          as pit_stop_count,
    coalesce(pa.total_pit_time_ms, 0)       as total_pit_time_ms
from {{ source('silver', 'race_data_results') }} res
join {{ ref('dim_races') }} r
    on res.raceid = r.race_id
join {{ source('silver', 'race_data_drivers') }} d
    on res.driverid = d.driverid
join {{ source('silver', 'race_data_constructors') }} t
    on res.constructorid = t.constructorid
join {{ source('silver', 'race_data_status') }} s
    on res.statusid = s.statusid
left join pit_aggregates pa
    on r.race_key = pa.race_key
    and res.driverid = pa.driver_id