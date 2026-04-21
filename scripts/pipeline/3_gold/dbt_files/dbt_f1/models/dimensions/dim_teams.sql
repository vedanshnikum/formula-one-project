select
    constructorid           as team_id,
    constructorref          as team_ref,
    name                    as team_name,
    nationality
from {{ source('silver', 'race_data_constructors') }}