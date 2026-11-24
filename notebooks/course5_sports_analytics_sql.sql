-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Course 5: Sports Analytics on Databricks in SQL
-- MAGIC Same Elo and MVP as Course 4, in SQL (sql/elo_dbx.sql, sql/c5_views.sql, sql/demo_*.sql).
-- MAGIC Data: European Soccer Database (ODbL 1.0). See the repo README.
-- MAGIC The cells use season 2015/2016 (the committed sample); change it to 2008/2009 on the full database.

-- COMMAND ----------

-- databricks-only: create the views over your Volume (the tests skip this cell)
CREATE OR REPLACE TEMP VIEW Match AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Match.parquet`;
CREATE OR REPLACE TEMP VIEW Player AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Player.parquet`;
CREATE OR REPLACE TEMP VIEW Player_Attributes AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Player_Attributes.parquet`;
CREATE OR REPLACE TEMP VIEW Team AS SELECT * FROM parquet.`/Volumes/main/default/soccer/Team.parquet`;
CREATE OR REPLACE TEMP VIEW League AS SELECT * FROM parquet.`/Volumes/main/default/soccer/League.parquet`;

-- COMMAND ----------

SELECT season, count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals
FROM Match
GROUP BY season
ORDER BY season;

-- COMMAND ----------

SELECT t.team_long_name, count(*) AS home_wins
FROM Match m
JOIN Team t ON t.team_api_id = m.home_team_api_id
WHERE m.home_team_goal > m.away_team_goal
GROUP BY t.team_long_name
ORDER BY home_wins DESC, t.team_long_name
LIMIT 5;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Elo without MAP (1.2.3)
-- MAGIC Databricks form of sql/elo.sql: one recursion step per match day, no MAP, no LATERAL.

-- COMMAND ----------

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

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### The views (3.1.2)
-- MAGIC Every query below reads these; the parity cell checks them against the Python of Course 4.

-- COMMAND ----------

-- 3.1.2 view elo_params: one row per (K, home bonus) pair; the tuning cell swaps in a grid of pairs
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT * FROM (VALUES (1, CAST(20.0 AS DOUBLE), CAST(100.0 AS DOUBLE), CAST(400.0 AS DOUBLE), CAST(1500.0 AS DOUBLE)))
  AS t(pid, k_factor, home_advantage, scale, initial_rating);

-- COMMAND ----------

-- 3.1.2 view elo_sides: one row per team per match with its replay step; a date on which a team plays twice goes one match per step, in match_api_id order
CREATE OR REPLACE TEMP VIEW elo_sides AS
WITH raw AS (
  SELECT match_api_id, league_id, season, date, home_team_api_id AS home, away_team_api_id AS away,
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
  SELECT match_api_id, league_id, season, home, away, actual_home,
         dense_rank() OVER (ORDER BY raw.date, CASE WHEN r.date IS NOT NULL THEN match_api_id ELSE 0 END) AS day
  FROM raw
  LEFT JOIN repeat_dates r ON r.date = raw.date
)
SELECT match_api_id, league_id, season, day, home AS team, 1 AS is_home, actual_home AS actual FROM played
UNION ALL
SELECT match_api_id, league_id, season, day, away AS team, 0 AS is_home, actual_home AS actual FROM played;

-- COMMAND ----------

-- 3.1.2 view elo_state: every team's rating after every replay day, for every parameter pair
CREATE OR REPLACE TEMP VIEW elo_state AS
WITH RECURSIVE
last_day AS (SELECT max(day) AS n FROM elo_sides),
state(day, pid, team, rating) AS (
  SELECT 0, p.pid, t.team, p.initial_rating
  FROM (SELECT DISTINCT team FROM elo_sides) t CROSS JOIN elo_params p
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
    JOIN elo_params p ON p.pid = s.pid
    LEFT JOIN elo_sides sd ON sd.team = s.team AND sd.day = s.day + 1
    WHERE s.day < (SELECT n FROM last_day)
  ) x
)
SELECT day, pid, team, rating FROM state;

-- COMMAND ----------

-- 3.1.2 view elo_season: end-of-season rating of every (season, team); filter it by league_id and season
CREATE OR REPLACE TEMP VIEW elo_season AS
SELECT l.season, l.league_id, l.team AS team_api_id, st.rating
FROM (SELECT season, league_id, team, max(day) AS day FROM elo_sides GROUP BY season, league_id, team) l
JOIN elo_state st ON st.team = l.team AND st.day = l.day
WHERE st.pid = (SELECT min(pid) FROM elo_params);

-- COMMAND ----------

-- 3.1.2 view elo_prematch: what the ratings said before each match (the forecast), for every parameter pair
CREATE OR REPLACE TEMP VIEW elo_prematch AS
SELECT
  m.match_api_id, m.pid, m.league_id, m.season, m.home_team, m.away_team, m.home_rating, m.away_rating,
  1.0 / (1.0 + power(10.0, (m.away_rating - (m.home_rating + p.home_advantage)) / p.scale)) AS expected_home,
  m.actual_home
FROM (
  SELECT
    sd.match_api_id, st.pid, sd.league_id, sd.season,
    max(CASE WHEN sd.is_home = 1 THEN sd.team END) AS home_team,
    max(CASE WHEN sd.is_home = 0 THEN sd.team END) AS away_team,
    max(CASE WHEN sd.is_home = 1 THEN st.rating END) AS home_rating,
    max(CASE WHEN sd.is_home = 0 THEN st.rating END) AS away_rating,
    max(CASE WHEN sd.is_home = 1 THEN sd.actual END) AS actual_home
  FROM elo_sides sd
  JOIN elo_state st ON st.team = sd.team AND st.day = sd.day - 1
  GROUP BY sd.match_api_id, st.pid, sd.league_id, sd.season
) m
JOIN elo_params p ON p.pid = m.pid;

-- COMMAND ----------

-- 3.1.2 view mvp_inputs: one row per (league, season, player) before the minimum-starts filter
CREATE OR REPLACE TEMP VIEW mvp_inputs AS
WITH
attrs AS (
  SELECT
    player_api_id, id, date, overall_rating,
    CASE WHEN CAST(substr(date, 6, 2) AS INTEGER) >= 8
         THEN substr(date, 1, 4) || '/' || CAST(CAST(substr(date, 1, 4) AS INTEGER) + 1 AS VARCHAR)
         ELSE CAST(CAST(substr(date, 1, 4) AS INTEGER) - 1 AS VARCHAR) || '/' || substr(date, 1, 4)
    END AS season
  FROM Player_Attributes
  WHERE overall_rating IS NOT NULL AND date IS NOT NULL
),
latest AS (
  SELECT season, player_api_id, overall_rating AS rating
  FROM (
    SELECT *, row_number() OVER (PARTITION BY season, player_api_id ORDER BY date DESC, id DESC) AS rn
    FROM attrs
  )
  WHERE rn = 1
),
lineup AS (
  SELECT
    m.league_id, m.season, m.match_api_id, h.is_home, s.slot,
    CASE h.is_home WHEN 1 THEN m.home_team_api_id ELSE m.away_team_api_id END AS team,
    CASE h.is_home
      WHEN 1 THEN CASE s.slot
        WHEN 1 THEN m.home_player_1
        WHEN 2 THEN m.home_player_2
        WHEN 3 THEN m.home_player_3
        WHEN 4 THEN m.home_player_4
        WHEN 5 THEN m.home_player_5
        WHEN 6 THEN m.home_player_6
        WHEN 7 THEN m.home_player_7
        WHEN 8 THEN m.home_player_8
        WHEN 9 THEN m.home_player_9
        WHEN 10 THEN m.home_player_10
        WHEN 11 THEN m.home_player_11
      END
      ELSE CASE s.slot
        WHEN 1 THEN m.away_player_1
        WHEN 2 THEN m.away_player_2
        WHEN 3 THEN m.away_player_3
        WHEN 4 THEN m.away_player_4
        WHEN 5 THEN m.away_player_5
        WHEN 6 THEN m.away_player_6
        WHEN 7 THEN m.away_player_7
        WHEN 8 THEN m.away_player_8
        WHEN 9 THEN m.away_player_9
        WHEN 10 THEN m.away_player_10
        WHEN 11 THEN m.away_player_11
      END
    END AS player_api_id,
    CASE WHEN h.is_home = 1 THEN m.home_team_goal ELSE m.away_team_goal END AS own_goals,
    CASE WHEN h.is_home = 1 THEN m.away_team_goal ELSE m.home_team_goal END AS other_goals
  FROM Match m
  CROSS JOIN (VALUES (1), (0)) h(is_home)
  CROSS JOIN (VALUES (1), (2), (3), (4), (5), (6), (7), (8), (9), (10), (11)) s(slot)
  WHERE m.home_team_goal IS NOT NULL AND m.away_team_goal IS NOT NULL
),
starts AS (
  SELECT
    l.league_id, l.season, l.team, l.slot, l.player_api_id,
    CASE WHEN l.own_goals > l.other_goals THEN 3 WHEN l.own_goals = l.other_goals THEN 1 ELSE 0 END AS pts,
    CASE WHEN l.own_goals > l.other_goals THEN 1.0 WHEN l.own_goals = l.other_goals THEN 0.5 ELSE 0.0 END AS actual,
    CASE WHEN l.is_home = 1 THEN e.expected_home ELSE 1.0 - e.expected_home END AS expected,
    CASE WHEN l.slot = 1 THEN 'GK' WHEN l.slot <= 5 THEN 'DEF' WHEN l.slot <= 8 THEN 'MID' ELSE 'FWD' END AS position
  FROM lineup l
  JOIN elo_prematch e ON e.match_api_id = l.match_api_id AND e.pid = (SELECT min(pid) FROM elo_params)
  WHERE l.player_api_id IS NOT NULL
),
totals AS (
  SELECT league_id, season, player_api_id, count(*) AS appearances, sum(pts) AS pts, sum(actual - expected) AS surplus
  FROM starts
  GROUP BY league_id, season, player_api_id
),
team_counts AS (
  SELECT league_id, season, player_api_id, team, count(*) AS n FROM starts GROUP BY league_id, season, player_api_id, team
),
modal_team AS (
  SELECT league_id, season, player_api_id, team
  FROM (SELECT *, row_number() OVER (PARTITION BY league_id, season, player_api_id ORDER BY n DESC, team) AS rn FROM team_counts)
  WHERE rn = 1
),
position_counts AS (
  SELECT league_id, season, player_api_id, position, count(*) AS n
  FROM starts GROUP BY league_id, season, player_api_id, position
),
modal_position AS (
  SELECT league_id, season, player_api_id, position
  FROM (
    SELECT *, row_number() OVER (
      PARTITION BY league_id, season, player_api_id
      ORDER BY n DESC, CASE position WHEN 'GK' THEN 1 WHEN 'DEF' THEN 2 WHEN 'MID' THEN 3 ELSE 4 END) AS rn
    FROM position_counts)
  WHERE rn = 1
)
SELECT
  t.league_id, t.season, t.player_api_id, pl.player_name, mt.team AS team_api_id, mp.position,
  CAST(l.rating AS DOUBLE) AS rating, CAST(t.appearances AS BIGINT) AS appearances,
  CAST(100.0 AS DOUBLE) * t.pts / (CAST(3.0 AS DOUBLE) * t.appearances) AS win_share,
  CAST(50.0 AS DOUBLE) + CAST(100.0 AS DOUBLE) * t.surplus / t.appearances AS adj_win_share
FROM totals t
JOIN latest l ON l.season = t.season AND l.player_api_id = t.player_api_id
JOIN Player pl ON pl.player_api_id = t.player_api_id
JOIN modal_team mt ON mt.league_id = t.league_id AND mt.season = t.season AND mt.player_api_id = t.player_api_id
JOIN modal_position mp ON mp.league_id = t.league_id AND mp.season = t.season AND mp.player_api_id = t.player_api_id;

-- COMMAND ----------

-- 3.1.2 view mvp_scores: score, ranks and flags per league-season, plus position z-score and Elo-adjusted views
CREATE OR REPLACE TEMP VIEW mvp_scores AS
WITH
params AS (
  SELECT CAST(0.7 AS DOUBLE) AS quality_weight, CAST(0.3 AS DOUBLE) AS impact_weight, 10 AS min_appearances,
         15 AS few_appearances, 20 AS top_score_rank, 10 AS rank_gap, CAST(1000000.0 AS DOUBLE) AS score_scale
),
scored AS (
  SELECT i.*,
    avg(i.rating) OVER (PARTITION BY i.league_id, i.season, i.position) AS pos_mean,
    stddev_pop(i.rating) OVER (PARTITION BY i.league_id, i.season, i.position) AS pos_sd
  FROM mvp_inputs i, params p
  WHERE i.appearances >= p.min_appearances
),
scaled AS (
  SELECT s.*,
    CASE WHEN s.pos_sd = 0 THEN 0.0 ELSE (s.rating - s.pos_mean) / s.pos_sd END AS z_rating,
    floor((p.quality_weight * s.rating + p.impact_weight * s.win_share) * p.score_scale + 0.5) / p.score_scale AS score
  FROM scored s CROSS JOIN params p
),
alt AS (
  SELECT s.*,
    floor((p.quality_weight * s.rating + p.impact_weight * s.adj_win_share) * p.score_scale + 0.5) / p.score_scale AS score_adj,
    floor((p.quality_weight * (50.0 + 10.0 * s.z_rating) + p.impact_weight * s.win_share) * p.score_scale + 0.5) / p.score_scale AS score_z
  FROM scaled s CROSS JOIN params p
),
ranked AS (
  SELECT *,
    row_number() OVER (PARTITION BY league_id, season ORDER BY score DESC, player_api_id) AS score_rank,
    rank() OVER (PARTITION BY league_id, season ORDER BY rating DESC) AS rating_rank,
    row_number() OVER (PARTITION BY league_id, season ORDER BY score_adj DESC, player_api_id) AS adj_rank,
    row_number() OVER (PARTITION BY league_id, season ORDER BY score_z DESC, player_api_id) AS z_rank
  FROM alt
)
SELECT
  season, league_id, player_api_id, player_name, team_api_id, position,
  rating AS overall_rating, appearances, win_share, adj_win_share, z_rating,
  score, score_rank, rating_rank,
  score_rank = 1 AS is_mvp,
  (score_rank <> 1 AND score_rank <= p.top_score_rank
     AND (rating_rank - score_rank >= p.rank_gap OR appearances <= p.few_appearances)) AS is_adjacent,
  score_adj, adj_rank, score_z, z_rank,
  rating_rank - score_rank AS gap
FROM ranked CROSS JOIN params p;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Elo and MVP in SQL alone
-- MAGIC Course 4 computes both in Python. Elo ran in SQL above (standalone query and the `elo_season` view; the 1.2.5 checks below test it).
-- MAGIC This cell checks the MVP table by itself, with no Python tables: every league-season has exactly one MVP.

-- COMMAND ----------

-- SQL only: one MVP per league-season
SELECT count(*) AS league_seasons, sum(CASE WHEN mvps = 1 THEN 1 ELSE 0 END) AS with_one_mvp,
       sum(CASE WHEN mvps = 1 THEN 1 ELSE 0 END) = count(*) AS ok
FROM (SELECT league_id, season, sum(CASE WHEN is_mvp THEN 1 ELSE 0 END) AS mvps FROM mvp_scores GROUP BY league_id, season) m;

-- COMMAND ----------

-- 1.2.4 one season as a table: the end-of-season Elo of every team that played in it
SELECT t.team_long_name, round(e.rating, 1) AS rating
FROM elo_season e
JOIN Team t ON t.team_api_id = e.team_api_id
WHERE e.season = '2015/2016'
ORDER BY e.rating DESC, e.team_api_id
LIMIT 5;

-- COMMAND ----------

-- 1.2.5 check 1 of 5: one row per team per season it played
SELECT (SELECT count(*) FROM elo_season) AS team_seasons,
       (SELECT count(*) FROM (SELECT DISTINCT season, team FROM elo_sides) d) AS expected,
       (SELECT count(*) FROM elo_season) = (SELECT count(*) FROM (SELECT DISTINCT season, team FROM elo_sides) d) AS ok;

-- COMMAND ----------

-- 1.2.5 check 2 of 5: conservation, every point one team wins another loses, so the ratings still sum to 1500 per team
SELECT round(sum(st.rating) - count(*) * 1500.0, 6) AS drift, abs(sum(st.rating) - count(*) * 1500.0) < 0.000001 AS ok
FROM elo_state st
WHERE st.pid = (SELECT min(pid) FROM elo_params) AND st.day = (SELECT max(day) FROM elo_sides);

-- COMMAND ----------

-- 1.2.5 check 3 of 5: the first day by hand, 1500 plus or minus 20 * (actual - 0.6400649998)
SELECT sd.team, sd.is_home, round(st.rating, 6) AS replay,
       round(1500.0 + (CASE WHEN sd.is_home = 1 THEN 1.0 ELSE -1.0 END) * 20.0
             * (sd.actual - 1.0 / (1.0 + power(10.0, -100.0 / 400.0))), 6) AS by_hand
FROM elo_sides sd
JOIN elo_state st ON st.team = sd.team AND st.day = 1 AND st.pid = (SELECT min(pid) FROM elo_params)
WHERE sd.day = 1
ORDER BY sd.is_home DESC, sd.team;

-- COMMAND ----------

-- 1.2.5 check 4 of 5: ratings stay in a sane range
SELECT round(min(rating), 1) AS lowest, round(max(rating), 1) AS highest, min(rating) > 1000 AND max(rating) < 2000 AS ok
FROM elo_season;

-- COMMAND ----------

-- 1.2.5 check 5 of 5: how many team-dates have a team playing twice; those dates replay one match per step, so day-by-day equals match-by-match
SELECT count(*) AS team_dates_with_two_matches
FROM (SELECT team, date FROM (SELECT home_team_api_id AS team, date FROM Match WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL
                              UNION ALL
                              SELECT away_team_api_id, date FROM Match WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL) t
      GROUP BY team, date HAVING count(*) > 1) d;

-- COMMAND ----------

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

-- COMMAND ----------

-- 1.3.4 tuning, step 1: a grid of K and home-bonus pairs. Every pair is replayed in the same pass.
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT row_number() OVER (ORDER BY k, bonus) AS pid, k AS k_factor, bonus AS home_advantage,
       CAST(400.0 AS DOUBLE) AS scale, CAST(1500.0 AS DOUBLE) AS initial_rating
FROM (SELECT CAST(k AS DOUBLE) AS k, CAST(bonus AS DOUBLE) AS bonus
      FROM (VALUES (5), (10), (20), (30), (40), (60)) ks(k) CROSS JOIN (VALUES (0), (50), (100), (150)) bs(bonus)) grid;

-- COMMAND ----------

-- 1.3.4 tuning, step 2: mean squared forecast error per pair, best first
SELECT p.k_factor, p.home_advantage, avg(power(e.expected_home - e.actual_home, 2)) AS mse
FROM elo_prematch e
JOIN elo_params p ON p.pid = e.pid
GROUP BY p.k_factor, p.home_advantage
ORDER BY mse, p.k_factor, p.home_advantage;

-- COMMAND ----------

-- 1.3.4 tuning, step 3: put the single default pair back (K 20, bonus 100)
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT * FROM (VALUES (1, CAST(20.0 AS DOUBLE), CAST(100.0 AS DOUBLE), CAST(400.0 AS DOUBLE), CAST(1500.0 AS DOUBLE)))
  AS t(pid, k_factor, home_advantage, scale, initial_rating);

-- COMMAND ----------

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

-- COMMAND ----------

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

-- COMMAND ----------

-- 3.1.1 filter the Elo table by league and season: the Premier League top five of 2015/2016
SELECT t.team_long_name, round(e.rating, 1) AS rating
FROM elo_season e
JOIN Team t ON t.team_api_id = e.team_api_id
WHERE e.league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND e.season = '2015/2016'
ORDER BY e.rating DESC, e.team_api_id
LIMIT 5;

-- COMMAND ----------

-- 2.1.3 standardise by position: rating, mean and spread per position group, then the best z-scores
SELECT position, count(*) AS players, round(avg(overall_rating), 2) AS mean_rating,
       round(stddev_pop(overall_rating), 2) AS spread
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
GROUP BY position
ORDER BY position;

-- COMMAND ----------

-- 2.1.3 the five best players by z-score inside their own position
SELECT player_name, position, overall_rating, round(z_rating, 2) AS z_rating, z_rank
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY z_rating DESC, player_api_id
LIMIT 5;

-- COMMAND ----------

-- 2.2.2 how many players qualify (10 or more starts) in each season
SELECT season, count(*) AS qualified FROM mvp_scores GROUP BY season ORDER BY season;

-- COMMAND ----------

-- 2.2.3 the top six by score with their team's Elo, and win share raw against Elo-adjusted
WITH team_elo AS (
  SELECT team_api_id, rating, row_number() OVER (ORDER BY rating DESC, team_api_id) AS elo_rank
  FROM elo_season
  WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
)
SELECT s.score_rank, s.player_name, t.team_long_name, round(e.rating, 1) AS team_elo, e.elo_rank,
       round(s.win_share, 2) AS win_share, round(s.adj_win_share, 2) AS adj_win_share
FROM mvp_scores s
JOIN team_elo e ON e.team_api_id = s.team_api_id
JOIN Team t ON t.team_api_id = s.team_api_id
WHERE s.league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND s.season = '2015/2016'
  AND s.score_rank <= 6
ORDER BY s.score_rank;

-- COMMAND ----------

-- 2.2.4 the MVP of every season, Premier League
SELECT season, player_name, round(score, 2) AS score
FROM mvp_scores
WHERE is_mvp AND league_id = (SELECT id FROM League WHERE name = 'England Premier League')
ORDER BY season;

-- COMMAND ----------

-- 2.2.5 sweep the weights and the minimum starts in a params CTE: how many seasons change MVP against 0.7 / 10
WITH settings(quality_weight, min_starts) AS (
  VALUES (CAST(0.9 AS DOUBLE), 10), (CAST(0.9 AS DOUBLE), 20), (CAST(0.9 AS DOUBLE), 25),
         (CAST(0.7 AS DOUBLE), 10), (CAST(0.7 AS DOUBLE), 20), (CAST(0.7 AS DOUBLE), 25),
         (CAST(0.5 AS DOUBLE), 10), (CAST(0.5 AS DOUBLE), 20), (CAST(0.5 AS DOUBLE), 25)
),
scored AS (
  SELECT st.quality_weight, st.min_starts, i.season, i.player_api_id,
         floor((st.quality_weight * i.rating + (1.0 - st.quality_weight) * i.win_share) * 1000000.0 + 0.5) / 1000000.0 AS score
  FROM settings st
  JOIN mvp_inputs i ON i.appearances >= st.min_starts
  WHERE i.league_id = (SELECT id FROM League WHERE name = 'England Premier League')
),
winners AS (
  SELECT quality_weight, min_starts, season, player_api_id
  FROM (SELECT *, row_number() OVER (PARTITION BY quality_weight, min_starts, season ORDER BY score DESC, player_api_id) AS rn
        FROM scored)
  WHERE rn = 1
)
SELECT w.quality_weight, w.min_starts, count(*) AS seasons, count_if(w.player_api_id <> b.player_api_id) AS changed
FROM winners w
JOIN winners b ON b.season = w.season AND b.quality_weight = 0.7 AND b.min_starts = 10
GROUP BY w.quality_weight, w.min_starts
ORDER BY w.quality_weight DESC, w.min_starts;

-- COMMAND ----------

-- 2.3.3 the shortlist with its gap column (rating rank minus score rank)
SELECT player_name, score_rank, rating_rank, rating_rank - score_rank AS gap, appearances
FROM mvp_scores
WHERE is_adjacent AND league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY score_rank;

-- COMMAND ----------

-- 2.3.4 the capstone's alternative: the five adjacent players with the biggest gap
SELECT player_name, score_rank, rating_rank, rating_rank - score_rank AS gap
FROM mvp_scores
WHERE is_adjacent AND league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY gap DESC, score_rank
LIMIT 5;

-- COMMAND ----------

-- 3.1.1 filter the MVP table by league and season: top ten of the Premier League 2015/2016
SELECT score_rank, player_name, overall_rating, appearances, round(win_share, 2) AS win_share, round(score, 2) AS score, rating_rank
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016' AND score_rank <= 10
ORDER BY score_rank;

-- COMMAND ----------

-- 3.1.4 one report: the Elo top five, the MVP and the five-name shortlist, Premier League 2015/2016
WITH picked AS (
  SELECT (SELECT id FROM League WHERE name = 'England Premier League') AS league_id, '2015/2016' AS season
),
elo_top AS (
  SELECT 'elo' AS section, row_number() OVER (ORDER BY e.rating DESC, e.team_api_id) AS place,
         t.team_long_name AS name, round(e.rating, 1) AS value
  FROM elo_season e JOIN Team t ON t.team_api_id = e.team_api_id JOIN picked p ON p.league_id = e.league_id AND p.season = e.season
  QUALIFY row_number() OVER (ORDER BY e.rating DESC, e.team_api_id) <= 5
),
card AS (
  SELECT 'mvp' AS section, 1 AS place, s.player_name AS name, round(s.score, 2) AS value
  FROM mvp_scores s JOIN picked p ON p.league_id = s.league_id AND p.season = s.season
  WHERE s.is_mvp
),
short AS (
  SELECT 'shortlist' AS section, row_number() OVER (ORDER BY s.gap DESC, s.score_rank) AS place,
         s.player_name AS name, CAST(s.gap AS DOUBLE) AS value
  FROM mvp_scores s JOIN picked p ON p.league_id = s.league_id AND p.season = s.season
  WHERE s.is_adjacent
  QUALIFY row_number() OVER (ORDER BY s.gap DESC, s.score_rank) <= 5
)
SELECT section, place, name, value FROM (
  SELECT * FROM elo_top UNION ALL SELECT * FROM card UNION ALL SELECT * FROM short
) report
ORDER BY CASE section WHEN 'elo' THEN 1 WHEN 'mvp' THEN 2 ELSE 3 END, place;

-- COMMAND ----------

-- needs py_elo and py_mvp (course4.register_python_tables on DuckDB; write the same tables from Python on Databricks)
-- 3.1.3 Elo: season-end ratings, Python against elo_season
SELECT count(*) AS differing_rows
FROM py_elo p
FULL JOIN elo_season s ON s.season = p.season AND s.team_api_id = p.team_api_id
WHERE p.rating IS NULL OR s.rating IS NULL OR p.league_id <> s.league_id OR abs(p.rating - s.rating) > 0.000000001;

-- COMMAND ----------

-- needs py_elo and py_mvp (course4.register_python_tables on DuckDB; write the same tables from Python on Databricks)
-- 3.1.3 MVP: every column of the player-season table, Python against mvp_scores
SELECT count(*) AS differing_rows
FROM py_mvp p
FULL JOIN mvp_scores s ON s.league_id = p.league_id AND s.season = p.season AND s.player_api_id = p.player_api_id
WHERE p.score IS NULL OR s.score IS NULL
   OR p.team_api_id <> s.team_api_id OR p.position <> s.position OR p.appearances <> s.appearances
   OR abs(p.overall_rating - s.overall_rating) > 0.000000001 OR abs(p.win_share - s.win_share) > 0.000000001
   OR abs(p.adj_win_share - s.adj_win_share) > 0.000000001 OR abs(p.z_rating - s.z_rating) > 0.000000001
   OR abs(p.score - s.score) > 0.00001 OR abs(p.score_adj - s.score_adj) > 0.00001 OR abs(p.score_z - s.score_z) > 0.00001
   OR p.score_rank <> s.score_rank OR p.rating_rank <> s.rating_rank OR p.adj_rank <> s.adj_rank OR p.z_rank <> s.z_rank
   OR p.is_mvp <> s.is_mvp OR p.is_adjacent <> s.is_adjacent;
