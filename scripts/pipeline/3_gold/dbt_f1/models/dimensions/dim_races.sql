select
    raceid                                              as race_id,
    concat(
        cast(year(date) as string), '_',
        replace(name, ' ', '_')
    )                                                   as race_key,
    year(date)                                          as year,
    name                                                as race_name,
    round,
    date                                                as race_date,
    time                                                as race_time,
    circuitid                                           as circuit_id,
    fp1_date,
    fp1_time,
    fp2_date,
    fp2_time,
    fp3_date,
    fp3_time,
    quali_date,
    quali_time,
    sprint_date,
    sprint_time
from {{ source('silver', 'race_data_races') }}