select
    driverid                            as driver_id,
    driverref                           as driver_ref,
    number                              as driver_number,
    code                                as driver_code,
    forename                            as first_name,
    surname                             as last_name,
    concat(forename, ' ', surname)      as driver_full_name,
    dob                                 as date_of_birth,
    nationality
from {{ source('silver', 'race_data_drivers') }}