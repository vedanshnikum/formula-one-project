CREATE OR REPLACE VIEW formone.dashboard.historical_seasons AS
SELECT DISTINCT
  `Season`,
  `Driver`,
  `Driver ID`,
  `Driver Nationality`,
  `Team`,
  `Team ID`,
  `Driver Championship Points`,
  `Driver Championship Position`,
  `Driver Championship Wins`,
  `Team Championship Points`,
  `Team Championship Position`,
  `Team Championship Wins`,
  `Race Key`
FROM formone.dashboard.master;