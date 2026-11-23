-- Course 3 examples in SQL, by lesson. Each has a Python twin in src/dbx_ds/features.py;
-- tests/test_demo_sql_parity.py checks they agree.

-- 1.1.3 the target: home_win = home goals > away goals
SELECT count(*) AS matches, sum(CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END) AS home_wins
FROM Match;

-- 1.3.2 form: points per game over the last 5 earlier matches of the team in the season (NULL at season start)
WITH t AS (
  SELECT match_api_id, season, date, home_team_api_id AS team, 'home' AS side,
         CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts
  FROM Match
  UNION ALL
  SELECT match_api_id, season, date, away_team_api_id, 'away',
         CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END
  FROM Match
)
SELECT match_api_id, side,
       avg(pts) OVER (PARTITION BY season, team ORDER BY date, match_api_id
                      ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS form
FROM t ORDER BY match_api_id, side;

-- 1.3.4 rest days since the team's previous match, capped at 10
WITH t AS (
  SELECT match_api_id, date, home_team_api_id AS team, 'home' AS side FROM Match
  UNION ALL
  SELECT match_api_id, date, away_team_api_id, 'away' FROM Match
)
SELECT match_api_id, side,
       least(10, coalesce(date_diff('day', CAST(lag(date) OVER w AS DATE), CAST(date AS DATE)), 10)) AS rest_days
FROM t WINDOW w AS (PARTITION BY team ORDER BY date, match_api_id)
ORDER BY match_api_id, side;

-- 2.1.3 time-based split: train up to 2013/2014, test after
SELECT CASE WHEN season <= '2013/2014' THEN 'train' ELSE 'test' END AS part, count(*) AS matches
FROM Match GROUP BY part ORDER BY part DESC;
