CREATE OR REPLACE VIEW formone.dashboard.historical_overview AS
SELECT
  `Race Key`,
  `Season`,
  `Race Name`,
  `Round`,
  `Race Date`,
  `Circuit`,
  `City`,
  `Country`,
  `Latitude`,
  `Longitude`,
  `Altitude (m)`,
  `Driver`,
  `Team`,
  `Grid Position`,
  `Finish Position`,
  `Points`,
  `Finish Status`,
  `DNF`,
  `Pit Stops`
FROM formone.dashboard.historical_master;