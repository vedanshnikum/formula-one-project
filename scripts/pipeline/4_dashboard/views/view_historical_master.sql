CREATE OR REPLACE VIEW formone.dashboard.historical_master AS
SELECT
  -- Race Info
  r.race_key                          AS `Race Key`,
  r.year                              AS `Season`,
  r.race_name                         AS `Race Name`,
  r.round                             AS `Round`,
  r.race_date                         AS `Race Date`,

  -- Circuit Info
  c.circuit_name                      AS `Circuit`,
  c.city                              AS `City`,
  c.country                           AS `Country`,
  c.latitude                          AS `Latitude`,
  c.longitude                         AS `Longitude`,
  c.altitude_meters                   AS `Altitude (m)`,

  -- Driver Info
  fr.driver_full_name                 AS `Driver`,
  fr.driver_id                        AS `Driver ID`,
  d.driver_code                       AS `Driver Code`,
  d.nationality                       AS `Driver Nationality`,
  d.date_of_birth                     AS `Date of Birth`,

  -- Team Info
  fr.team_name                        AS `Team`,
  fr.team_id                          AS `Team ID`,
  t.nationality                       AS `Team Nationality`,

  -- Race Result
  fr.car_number                       AS `Car Number`,
  fr.grid_position                    AS `Grid Position`,
  fr.finish_position                  AS `Finish Position`,
  fr.position_order                   AS `Position Order`,
  fr.points                           AS `Points`,
  fr.laps                             AS `Laps Completed`,
  fr.race_time_ms                     AS `Race Time (ms)`,
  fr.fastest_lap_number               AS `Fastest Lap Number`,
  fr.fastest_lap_rank                 AS `Fastest Lap Rank`,
  fr.fastest_lap_speed                AS `Fastest Lap Speed`,
  fr.status                           AS `Finish Status`,
  fr.dnf_flag                         AS `DNF`,
  fr.positions_gained                 AS `Positions Gained`,
  fr.pit_stop_count                   AS `Pit Stops`,
  fr.total_pit_time_ms                AS `Total Pit Time (ms)`,

  -- Driver Championship Standings (at that race)
  sd.points                           AS `Driver Championship Points`,
  sd.position                         AS `Driver Championship Position`,
  sd.wins                             AS `Driver Championship Wins`,

  -- Team Championship Standings (at that race)
  st.points                           AS `Team Championship Points`,
  st.position                         AS `Team Championship Position`,
  st.wins                             AS `Team Championship Wins`

FROM formone.gold.fact_results         fr
JOIN formone.gold.dim_races            r  ON fr.race_key   = r.race_key
JOIN formone.gold.dim_circuits         c  ON r.circuit_id  = c.circuit_id
JOIN formone.gold.dim_drivers          d  ON fr.driver_id  = d.driver_id
JOIN formone.gold.dim_teams            t  ON fr.team_id    = t.team_id
LEFT JOIN formone.gold.standings_drivers sd ON fr.race_key = sd.race_key AND fr.driver_id = sd.driver_id
LEFT JOIN formone.gold.standings_teams   st ON fr.race_key = st.race_key AND fr.team_id   = st.team_id;