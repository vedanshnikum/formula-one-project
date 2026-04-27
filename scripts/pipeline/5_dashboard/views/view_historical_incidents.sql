CREATE OR REPLACE VIEW formone.dashboard.historical_incidents AS

-- Race incidents (red flags, safety cars)
SELECT
  race_name                           AS `Race Name`,
  incident_type                       AS `Incident Type`,
  lap                                 AS `Lap`,
  incident                            AS `Incident Description`,
  deployed_lap                        AS `SC Deployed Lap`,
  retreated_lap                       AS `SC Retreated Lap`,
  full_laps_under_sc                  AS `Full Laps Under SC`,
  resumed                             AS `Resumed`,
  excluded                            AS `Excluded Drivers`,
  CAST(NULL AS string)                AS `Person`,
  CAST(NULL AS integer)               AS `Age`,
  CAST(NULL AS date)                  AS `Date of Accident`,
  CAST(NULL AS string)                AS `Car`,
  CAST(NULL AS string)                AS `Session`,
  CAST(NULL AS string)                AS `Fatal Accident Type`
FROM formone.gold.event_race_incidents

UNION ALL

-- Fatal accidents (drivers and marshals combined)
SELECT
  event                               AS `Race Name`,
  'Fatal Accident'                    AS `Incident Type`,
  CAST(NULL AS integer)               AS `Lap`,
  CAST(NULL AS string)                AS `Incident Description`,
  CAST(NULL AS integer)               AS `SC Deployed Lap`,
  CAST(NULL AS double)                AS `SC Retreated Lap`,
  CAST(NULL AS integer)               AS `Full Laps Under SC`,
  CAST(NULL AS string)                AS `Resumed`,
  CAST(NULL AS string)                AS `Excluded Drivers`,
  name                                AS `Person`,
  age                                 AS `Age`,
  date_of_accident                    AS `Date of Accident`,
  car                                 AS `Car`,
  session                             AS `Session`,
  type                                AS `Fatal Accident Type`
FROM formone.gold.event_fatal_accidents;