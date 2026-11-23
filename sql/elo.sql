-- Elo team ranking: end-of-season rating for every (season, team).
-- Same rules as src/dbx_ds/elo.py: replay matches by date then match_api_id,
-- draw = 0.5, ratings carry over between seasons. Constants must match elo.py
-- (tests/test_parity.py checks them).
-- Verified on DuckDB. Written in standard recursive-CTE and MAP style for Databricks SQL (not yet run there).
WITH RECURSIVE
params AS (
  SELECT 1500.0 AS initial_rating, 20.0 AS k_factor, 100.0 AS home_advantage, 400.0 AS scale
),
ordered AS (
  SELECT
    row_number() OVER (ORDER BY date, match_api_id) AS n,
    season,
    home_team_api_id AS home,
    away_team_api_id AS away,
    CASE WHEN home_team_goal > away_team_goal THEN 1.0
         WHEN home_team_goal = away_team_goal THEN 0.5
         ELSE 0.0 END AS actual_home
  FROM Match
),
steps(n, season, home, away, new_home, new_away, ratings) AS (
  SELECT 0, CAST(NULL AS VARCHAR), CAST(NULL AS BIGINT), CAST(NULL AS BIGINT),
         CAST(NULL AS DOUBLE), CAST(NULL AS DOUBLE),
         CAST(MAP {} AS MAP(BIGINT, DOUBLE))
  UNION ALL
  SELECT n, season, home, away, new_home, new_away,
         map_concat(ratings, MAP {home: new_home, away: new_away})
  FROM (
    SELECT
      o.n, o.season, o.home, o.away, s.ratings,
      h.r + p.k_factor * (o.actual_home - 1.0 / (1.0 + power(10.0, (a.r - (h.r + p.home_advantage)) / p.scale))) AS new_home,
      a.r - p.k_factor * (o.actual_home - 1.0 / (1.0 + power(10.0, (a.r - (h.r + p.home_advantage)) / p.scale))) AS new_away
    FROM steps s
    JOIN ordered o ON o.n = s.n + 1
    CROSS JOIN params p
    CROSS JOIN LATERAL (SELECT coalesce(s.ratings[o.home], p.initial_rating) AS r) h
    CROSS JOIN LATERAL (SELECT coalesce(s.ratings[o.away], p.initial_rating) AS r) a
  )
),
events AS (
  SELECT n, season, home AS team, new_home AS rating FROM steps WHERE n > 0
  UNION ALL
  SELECT n, season, away AS team, new_away AS rating FROM steps WHERE n > 0
),
last_event AS (
  SELECT season, team, rating,
         row_number() OVER (PARTITION BY season, team ORDER BY n DESC) AS rn
  FROM events
)
SELECT season, team AS team_api_id, rating
FROM last_event
WHERE rn = 1
ORDER BY season, team_api_id;
