-- MVP and MVP-adjacent players, per season.
-- Same rules as src/dbx_ds/mvp.py: score = 0.7 * rating + 0.3 * win_share, players
-- with at least 10 starts only; MVP = score rank 1; adjacent = top 20 on score, not the
-- MVP, and either 10+ places under-rated by overall_rating or at most 15 starts.
-- Constants must match mvp.py (tests/test_parity.py checks them).
WITH
params AS (
  SELECT 0.7 AS quality_weight, 0.3 AS impact_weight, 10 AS min_appearances,
         15 AS few_appearances, 20 AS top_score_rank, 10 AS rank_gap
),
attrs AS (
  SELECT
    player_api_id, id, date, overall_rating,
    CASE WHEN CAST(substr(date, 6, 2) AS INTEGER) >= 8
         THEN substr(date, 1, 4) || '/' || CAST(CAST(substr(date, 1, 4) AS INTEGER) + 1 AS VARCHAR)
         ELSE CAST(CAST(substr(date, 1, 4) AS INTEGER) - 1 AS VARCHAR) || '/' || substr(date, 1, 4)
    END AS season
  FROM Player_Attributes
  WHERE overall_rating IS NOT NULL
),
latest AS (
  SELECT season, player_api_id, overall_rating AS rating
  FROM (
    SELECT *, row_number() OVER (PARTITION BY season, player_api_id ORDER BY date DESC, id DESC) AS rn
    FROM attrs
  )
  WHERE rn = 1
),
starts AS (
  SELECT season, home_player_1 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_1 IS NOT NULL
  UNION ALL
  SELECT season, home_player_2 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_2 IS NOT NULL
  UNION ALL
  SELECT season, home_player_3 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_3 IS NOT NULL
  UNION ALL
  SELECT season, home_player_4 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_4 IS NOT NULL
  UNION ALL
  SELECT season, home_player_5 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_5 IS NOT NULL
  UNION ALL
  SELECT season, home_player_6 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_6 IS NOT NULL
  UNION ALL
  SELECT season, home_player_7 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_7 IS NOT NULL
  UNION ALL
  SELECT season, home_player_8 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_8 IS NOT NULL
  UNION ALL
  SELECT season, home_player_9 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_9 IS NOT NULL
  UNION ALL
  SELECT season, home_player_10 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_10 IS NOT NULL
  UNION ALL
  SELECT season, home_player_11 AS player_api_id, CASE WHEN home_team_goal > away_team_goal THEN 3 WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE home_player_11 IS NOT NULL
  UNION ALL
  SELECT season, away_player_1 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_1 IS NOT NULL
  UNION ALL
  SELECT season, away_player_2 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_2 IS NOT NULL
  UNION ALL
  SELECT season, away_player_3 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_3 IS NOT NULL
  UNION ALL
  SELECT season, away_player_4 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_4 IS NOT NULL
  UNION ALL
  SELECT season, away_player_5 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_5 IS NOT NULL
  UNION ALL
  SELECT season, away_player_6 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_6 IS NOT NULL
  UNION ALL
  SELECT season, away_player_7 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_7 IS NOT NULL
  UNION ALL
  SELECT season, away_player_8 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_8 IS NOT NULL
  UNION ALL
  SELECT season, away_player_9 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_9 IS NOT NULL
  UNION ALL
  SELECT season, away_player_10 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_10 IS NOT NULL
  UNION ALL
  SELECT season, away_player_11 AS player_api_id, CASE WHEN away_team_goal > home_team_goal THEN 3 WHEN away_team_goal = home_team_goal THEN 1 ELSE 0 END AS pts FROM Match WHERE away_player_11 IS NOT NULL
),
involvement AS (
  SELECT season, player_api_id, count(*) AS appearances, sum(pts) AS pts
  FROM starts
  GROUP BY season, player_api_id
),
scored AS (
  SELECT
    l.season, l.player_api_id, pl.player_name, l.rating, i.appearances,
    100.0 * i.pts / (3.0 * i.appearances) AS win_share,
    round(p.quality_weight * l.rating + p.impact_weight * (100.0 * i.pts / (3.0 * i.appearances)), 6) AS score
  FROM latest l
  JOIN involvement i ON i.season = l.season AND i.player_api_id = l.player_api_id
  JOIN Player pl ON pl.player_api_id = l.player_api_id
  CROSS JOIN params p
  WHERE i.appearances >= p.min_appearances
),
ranked AS (
  SELECT *,
    row_number() OVER (PARTITION BY season ORDER BY score DESC, player_api_id) AS score_rank,
    row_number() OVER (PARTITION BY season ORDER BY rating DESC, player_api_id) AS rating_rank
  FROM scored
)
SELECT
  season, player_api_id, player_name,
  CAST(rating AS DOUBLE) AS overall_rating,
  CAST(appearances AS BIGINT) AS appearances,
  win_share, score, score_rank, rating_rank,
  score_rank = 1 AS is_mvp,
  (score_rank <> 1 AND score_rank <= p.top_score_rank
     AND (rating_rank - score_rank >= p.rank_gap OR appearances <= p.few_appearances)) AS is_adjacent
FROM ranked
CROSS JOIN params p
ORDER BY season, score_rank;
