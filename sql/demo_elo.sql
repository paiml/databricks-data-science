-- Course 5 Elo queries, by lesson. Run sql/c5_views.sql first (elo_state, elo_season, elo_prematch ...).
-- Plain ANSI plus count_if, which DuckDB and Databricks SQL both read. Verified on DuckDB; not yet run on Databricks.
-- Premier League is looked up by name, so the same text runs on the fixture and on the full database.

-- 1.2.4 one season as a table: the end-of-season Elo of every team that played in it
SELECT t.team_long_name, round(e.rating, 1) AS rating
FROM elo_season e
JOIN Team t ON t.team_api_id = e.team_api_id
WHERE e.season = '2015/2016'
ORDER BY e.rating DESC, e.team_api_id
LIMIT 5;

-- 1.2.5 check 1 of 5: one row per team per season it played
SELECT (SELECT count(*) FROM elo_season) AS team_seasons,
       (SELECT count(*) FROM (SELECT DISTINCT season, team FROM elo_sides) d) AS expected,
       (SELECT count(*) FROM elo_season) = (SELECT count(*) FROM (SELECT DISTINCT season, team FROM elo_sides) d) AS ok;

-- 1.2.5 check 2 of 5: conservation, every point one team wins another loses, so the ratings still sum to 1500 per team
SELECT round(sum(st.rating) - count(*) * 1500.0, 6) AS drift, abs(sum(st.rating) - count(*) * 1500.0) < 0.000001 AS ok
FROM elo_state st
WHERE st.pid = (SELECT min(pid) FROM elo_params) AND st.day = (SELECT max(day) FROM elo_sides);

-- 1.2.5 check 3 of 5: the first day by hand, 1500 plus or minus 20 * (actual - 0.6400649998)
SELECT sd.team, sd.is_home, round(st.rating, 6) AS replay,
       round(1500.0 + (CASE WHEN sd.is_home = 1 THEN 1.0 ELSE -1.0 END) * 20.0
             * (sd.actual - 1.0 / (1.0 + power(10.0, -100.0 / 400.0))), 6) AS by_hand
FROM elo_sides sd
JOIN elo_state st ON st.team = sd.team AND st.day = 1 AND st.pid = (SELECT min(pid) FROM elo_params)
WHERE sd.day = 1
ORDER BY sd.is_home DESC, sd.team;

-- 1.2.5 check 4 of 5: ratings stay in a sane range
SELECT round(min(rating), 1) AS lowest, round(max(rating), 1) AS highest, min(rating) > 1000 AND max(rating) < 2000 AS ok
FROM elo_season;

-- 1.2.5 check 5 of 5: no team plays twice on one date, so replaying a day at a time equals replaying by match
SELECT count(*) AS teams_twice_on_one_day FROM (SELECT team, day FROM elo_sides GROUP BY team, day HAVING count(*) > 1) d;

-- 1.3.3 home advantage: result shares and mean goals per side
SELECT count_if(home_team_goal > away_team_goal) AS home_wins,
       count_if(home_team_goal = away_team_goal) AS draws,
       count_if(home_team_goal < away_team_goal) AS away_wins,
       count(*) AS matches,
       round(100.0 * count_if(home_team_goal > away_team_goal) / count(*), 2) AS home_pct,
       round(100.0 * count_if(home_team_goal = away_team_goal) / count(*), 2) AS draw_pct,
       round(100.0 * count_if(home_team_goal < away_team_goal) / count(*), 2) AS away_pct,
       round(avg(home_team_goal), 3) AS home_goals,
       round(avg(away_team_goal), 3) AS away_goals
FROM Match
WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL;

-- 1.3.4 tuning, step 1: a grid of K and home-bonus pairs. Every pair is replayed in the same pass.
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT row_number() OVER (ORDER BY k, bonus) AS pid, k AS k_factor, bonus AS home_advantage,
       CAST(400.0 AS DOUBLE) AS scale, CAST(1500.0 AS DOUBLE) AS initial_rating
FROM (SELECT CAST(k AS DOUBLE) AS k, CAST(bonus AS DOUBLE) AS bonus
      FROM (VALUES (5), (10), (20), (30), (40), (60)) ks(k) CROSS JOIN (VALUES (0), (50), (100), (150)) bs(bonus)) grid;

-- 1.3.4 tuning, step 2: mean squared forecast error per pair, best first
SELECT p.k_factor, p.home_advantage, avg(power(e.expected_home - e.actual_home, 2)) AS mse
FROM elo_prematch e
JOIN elo_params p ON p.pid = e.pid
GROUP BY p.k_factor, p.home_advantage
ORDER BY mse, p.k_factor, p.home_advantage;

-- 1.3.4 tuning, step 3: put the single default pair back (K 20, bonus 100)
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT * FROM (VALUES (1, CAST(20.0 AS DOUBLE), CAST(100.0 AS DOUBLE), CAST(400.0 AS DOUBLE), CAST(1500.0 AS DOUBLE)))
  AS t(pid, k_factor, home_advantage, scale, initial_rating);

-- 1.3.5 standings check: Premier League 2015/2016, points table against Elo, and their Spearman correlation
WITH played AS (
  SELECT m.home_team_api_id AS team,
         CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts,
         home_team_goal - away_team_goal AS gd, home_team_goal AS gf
  FROM Match m JOIN League l ON l.id = m.league_id
  WHERE l.name = 'England Premier League' AND m.season = '2015/2016'
    AND m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL
  UNION ALL
  SELECT m.away_team_api_id,
         CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END,
         away_team_goal - home_team_goal, away_team_goal
  FROM Match m JOIN League l ON l.id = m.league_id
  WHERE l.name = 'England Premier League' AND m.season = '2015/2016'
    AND m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL
),
standings AS (
  SELECT team, sum(pts) AS points, sum(gd) AS goal_difference, sum(gf) AS goals_for FROM played GROUP BY team
),
ranked AS (
  SELECT x.team, x.points, x.goal_difference, e.rating,
         row_number() OVER (ORDER BY x.points DESC, x.goal_difference DESC, x.goals_for DESC, x.team) AS points_rank,
         row_number() OVER (ORDER BY e.rating DESC, x.team) AS elo_rank
  FROM standings x
  JOIN elo_season e ON e.team_api_id = x.team AND e.season = '2015/2016'
)
SELECT count(*) AS teams,
       1.0 - 6.0 * sum(power(points_rank - elo_rank, 2)) / (count(*) * (count(*) * count(*) - 1)) AS spearman
FROM ranked;

-- 1.3.5 standings check, the top of the table: points rank beside Elo rank
WITH played AS (
  SELECT m.home_team_api_id AS team,
         CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts,
         home_team_goal - away_team_goal AS gd, home_team_goal AS gf
  FROM Match m JOIN League l ON l.id = m.league_id
  WHERE l.name = 'England Premier League' AND m.season = '2015/2016'
    AND m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL
  UNION ALL
  SELECT m.away_team_api_id,
         CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END,
         away_team_goal - home_team_goal, away_team_goal
  FROM Match m JOIN League l ON l.id = m.league_id
  WHERE l.name = 'England Premier League' AND m.season = '2015/2016'
    AND m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL
),
standings AS (
  SELECT team, sum(pts) AS points, sum(gd) AS goal_difference, sum(gf) AS goals_for FROM played GROUP BY team
)
SELECT t.team_long_name, x.points, round(e.rating, 1) AS elo,
       row_number() OVER (ORDER BY x.points DESC, x.goal_difference DESC, x.goals_for DESC, x.team) AS points_rank,
       row_number() OVER (ORDER BY e.rating DESC, x.team) AS elo_rank
FROM standings x
JOIN Team t ON t.team_api_id = x.team
JOIN elo_season e ON e.team_api_id = x.team AND e.season = '2015/2016'
ORDER BY points_rank
LIMIT 5;

-- 3.1.1 filter the Elo table by league and season: the Premier League top five of 2015/2016
SELECT t.team_long_name, round(e.rating, 1) AS rating
FROM elo_season e
JOIN Team t ON t.team_api_id = e.team_api_id
WHERE e.league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND e.season = '2015/2016'
ORDER BY e.rating DESC, e.team_api_id
LIMIT 5;
