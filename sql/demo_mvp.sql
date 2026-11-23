-- Course 5 MVP queries, by lesson. Run sql/c5_views.sql first (mvp_inputs, mvp_scores, elo_season).
-- Rankings are per league and season. Premier League is looked up by name, so the text runs on the fixture
-- and on the full database. Verified on DuckDB; not yet run on Databricks.

-- 2.1.3 standardise by position: rating, mean and spread per position group, then the best z-scores
SELECT position, count(*) AS players, round(avg(overall_rating), 2) AS mean_rating,
       round(stddev_pop(overall_rating), 2) AS spread
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
GROUP BY position
ORDER BY position;

-- 2.1.3 the five best players by z-score inside their own position
SELECT player_name, position, overall_rating, round(z_rating, 2) AS z_rating, z_rank
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY z_rating DESC, player_api_id
LIMIT 5;

-- 2.2.2 how many players qualify (10 or more starts) in each season
SELECT season, count(*) AS qualified FROM mvp_scores GROUP BY season ORDER BY season;

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

-- 2.2.4 the MVP of every season, Premier League
SELECT season, player_name, round(score, 2) AS score
FROM mvp_scores
WHERE is_mvp AND league_id = (SELECT id FROM League WHERE name = 'England Premier League')
ORDER BY season;

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

-- 2.3.3 the shortlist with its gap column (rating rank minus score rank)
SELECT player_name, score_rank, rating_rank, rating_rank - score_rank AS gap, appearances
FROM mvp_scores
WHERE is_adjacent AND league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY score_rank;

-- 2.3.4 the capstone's alternative: the five adjacent players with the biggest gap
SELECT player_name, score_rank, rating_rank, rating_rank - score_rank AS gap
FROM mvp_scores
WHERE is_adjacent AND league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016'
ORDER BY gap DESC, score_rank
LIMIT 5;

-- 3.1.1 filter the MVP table by league and season: top ten of the Premier League 2015/2016
SELECT score_rank, player_name, overall_rating, appearances, round(win_share, 2) AS win_share, round(score, 2) AS score, rating_rank
FROM mvp_scores
WHERE league_id = (SELECT id FROM League WHERE name = 'England Premier League') AND season = '2015/2016' AND score_rank <= 10
ORDER BY score_rank;

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
