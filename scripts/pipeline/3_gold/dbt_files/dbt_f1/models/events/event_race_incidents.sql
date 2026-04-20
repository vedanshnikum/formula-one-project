select
    sc.race                                                         as race_name,
    'Safety Car'                                                    as incident_type,
    cast(null as int)                                               as lap,
    sc.cause                                                        as incident,
    sc.deployed                                                     as deployed_lap,
    sc.retreated                                                    as retreated_lap,
    sc.fulllaps                                                     as full_laps_under_sc,
    cast(null as string)                                            as resumed,
    cast(null as string)                                            as excluded
from {{ source('silver', 'race_events_safety_cars') }} sc

union all

select
    rf.race                                                         as race_name,
    'Red Flag'                                                      as incident_type,
    rf.lap,
    rf.incident,
    cast(null as int)                                               as deployed_lap,
    cast(null as double)                                            as retreated_lap,
    cast(null as int)                                               as full_laps_under_sc,
    rf.resumed,
    rf.excluded
from {{ source('silver', 'race_events_red_flags') }} rf