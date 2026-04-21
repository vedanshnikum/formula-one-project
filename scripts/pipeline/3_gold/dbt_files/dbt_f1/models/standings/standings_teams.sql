select
    r.race_key,
    year(r.race_date)                       as year,
    t.name                                  as team_name,
    cs.constructorid                        as team_id,
    cs.points,
    cs.position,
    cs.wins
from {{ source('silver', 'race_data_constructor_standings') }} cs
join {{ ref('dim_races') }} r
    on cs.raceid = r.race_id
join {{ source('silver', 'race_data_constructors') }} t
    on cs.constructorid = t.constructorid