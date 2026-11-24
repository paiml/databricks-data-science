-- 3.1.3 Python against SQL, inside SQL: the Python tables py_elo and py_mvp (src/dbx_ds/course4.py) are
-- full-joined to the views; the count of differing rows must be 0. Tolerance 1e-9 on ratings, 1e-5 on scores.
-- Run sql/c5_views.sql first. Verified on DuckDB; not yet run on Databricks.

-- 3.1.3 Elo: season-end ratings, Python against elo_season
SELECT count(*) AS differing_rows
FROM py_elo p
FULL JOIN elo_season s ON s.season = p.season AND s.team_api_id = p.team_api_id
WHERE p.rating IS NULL OR s.rating IS NULL OR p.league_id <> s.league_id OR abs(p.rating - s.rating) > 0.000000001;

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
