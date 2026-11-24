-- The views behind Course 5: the Elo replay (no MAP) and the MVP tables, per league and season.
-- Same rules as src/dbx_ds/{elo,eloplus,mvp,mvpplus}.py; tests/test_views.py checks them against Python.
-- Every view reads only Match, Player and Player_Attributes, so the cells run on a Databricks SQL warehouse once
-- those three tables (or temp views over the Parquet files) exist. Verified on DuckDB; NOT yet run on Databricks.
-- elo_state is a WITH RECURSIVE query: Databricks limits recursion depth, so raise that limit to cover the number
-- of distinct match dates (about 1,700 on the full database) before running it there.

-- 3.1.2 view elo_params: one row per (K, home bonus) pair; the tuning cell swaps in a grid of pairs
CREATE OR REPLACE TEMP VIEW elo_params AS
SELECT * FROM (VALUES (1, CAST(20.0 AS DOUBLE), CAST(100.0 AS DOUBLE), CAST(400.0 AS DOUBLE), CAST(1500.0 AS DOUBLE)))
  AS t(pid, k_factor, home_advantage, scale, initial_rating);

-- 3.1.2 view elo_sides: one row per team per match, with the replay day (distinct dates, in order)
CREATE OR REPLACE TEMP VIEW elo_sides AS
WITH played AS (
  SELECT match_api_id, league_id, season, home_team_api_id AS home, away_team_api_id AS away,
         CASE WHEN home_team_goal > away_team_goal THEN 1.0
              WHEN home_team_goal = away_team_goal THEN 0.5
              ELSE 0.0 END AS actual_home,
         dense_rank() OVER (ORDER BY date) AS day
  FROM Match
  WHERE home_team_goal IS NOT NULL AND away_team_goal IS NOT NULL
)
SELECT match_api_id, league_id, season, day, home AS team, 1 AS is_home, actual_home AS actual FROM played
UNION ALL
SELECT match_api_id, league_id, season, day, away AS team, 0 AS is_home, actual_home AS actual FROM played;

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

-- 3.1.2 view elo_season: end-of-season rating of every (season, team); filter it by league_id and season
CREATE OR REPLACE TEMP VIEW elo_season AS
SELECT l.season, l.league_id, l.team AS team_api_id, st.rating
FROM (SELECT season, league_id, team, max(day) AS day FROM elo_sides GROUP BY season, league_id, team) l
JOIN elo_state st ON st.team = l.team AND st.day = l.day
WHERE st.pid = (SELECT min(pid) FROM elo_params);

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
