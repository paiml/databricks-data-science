-- Elo season-end ratings, Databricks-runnable form of sql/elo.sql (no MAP, no LATERAL, no DuckDB-only calls).
-- Idea: the rating of a team only changes on a day it plays. Replay the calendar one DAY per recursion step,
-- carrying one row per (parameter set, team), so the recursion is about 1,700 steps (plus, on each date where a team plays twice, one step per match that day instead of one) instead of 26,000 matches.
-- Same rules as src/dbx_ds/elo.py (date, then match_api_id): a date on which no team plays twice is one step; a date
-- on which some team does is replayed one match per step in match_api_id order (tests/test_same_day.py checks it).
-- Verified on DuckDB. Written for Databricks SQL (WITH RECURSIVE and window
-- functions in the recursive step are in its documentation; NOT yet run there: raise its recursion-depth limit
-- to cover the number of replay steps (distinct match dates, and on a date where a team plays twice one step per match that day) before running on the full data).
-- Several (k_factor, home_advantage) pairs may be listed in params: every pair is replayed in the same pass
-- (the tuning loop in sql/demo_elo.sql, lesson 1.3.4, does that through the elo_params view).
WITH RECURSIVE
params(pid, k_factor, home_advantage, scale, initial_rating) AS (
  VALUES (1, CAST(20.0 AS DOUBLE), CAST(100.0 AS DOUBLE), CAST(400.0 AS DOUBLE), CAST(1500.0 AS DOUBLE))
),
raw AS (
  SELECT
    match_api_id, season, date,
    home_team_api_id AS home, away_team_api_id AS away,
    CASE WHEN home_team_goal > away_team_goal THEN 1.0
         WHEN home_team_goal = away_team_goal THEN 0.5
         ELSE 0.0 END AS actual_home
  FROM Match
  WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL
),
repeat_dates AS (
  SELECT DISTINCT date FROM (
    SELECT date, home AS team FROM raw UNION ALL SELECT date, away FROM raw
  ) t
  GROUP BY date, team
  HAVING count(*) > 1
),
played AS (
  SELECT
    match_api_id, season, home, away, actual_home,
    dense_rank() OVER (ORDER BY raw.date, CASE WHEN r.date IS NOT NULL THEN match_api_id ELSE 0 END) AS day
  FROM raw
  LEFT JOIN repeat_dates r ON r.date = raw.date
),
sides AS (
  SELECT match_api_id, season, day, home AS team, 1 AS is_home, actual_home AS actual FROM played
  UNION ALL
  SELECT match_api_id, season, day, away AS team, 0 AS is_home, actual_home AS actual FROM played
),
last_day AS (SELECT max(day) AS n FROM played),
state(day, pid, team, rating) AS (
  SELECT 0, p.pid, t.team, p.initial_rating
  FROM (SELECT DISTINCT team FROM sides) t CROSS JOIN params p
  UNION ALL
  SELECT
    x.day, x.pid, x.team,
    CASE WHEN x.match_api_id IS NULL THEN x.rating
         ELSE x.rating + (CASE WHEN x.is_home = 1 THEN 1.0 ELSE -1.0 END) * x.k_factor
              * (x.actual - 1.0 / (1.0 + power(10.0, (x.away_rating - (x.home_rating + x.home_advantage)) / x.scale)))
    END
  FROM (
    SELECT
      s.day + 1 AS day, s.pid, s.team, s.rating, sd.match_api_id, sd.is_home, sd.actual,
      p.k_factor, p.home_advantage, p.scale,
      max(CASE WHEN sd.is_home = 1 THEN s.rating END) OVER (PARTITION BY s.pid, sd.match_api_id) AS home_rating,
      max(CASE WHEN sd.is_home = 0 THEN s.rating END) OVER (PARTITION BY s.pid, sd.match_api_id) AS away_rating
    FROM state s
    JOIN params p ON p.pid = s.pid
    LEFT JOIN sides sd ON sd.team = s.team AND sd.day = s.day + 1
    WHERE s.day < (SELECT n FROM last_day)
  ) x
),
season_last AS (
  SELECT season, team, max(day) AS day FROM sides GROUP BY season, team
)
SELECT l.season, l.team AS team_api_id, st.rating
FROM season_last l
JOIN state st ON st.team = l.team AND st.day = l.day
ORDER BY l.season, l.team;
