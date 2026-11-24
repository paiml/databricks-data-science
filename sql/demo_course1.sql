-- Course 1 demo queries, by lesson. Copied from the course 1 authoring file DEMO-QUERIES.sql (catalogue).
-- Numbers in the comments were measured on the FULL database (sha256 4df85697...39a9); tests/test_full_data.py
-- checks them when `make data` has been run. Plain ANSI: runs on DuckDB and Databricks SQL.

-- 2.1.2
SELECT * FROM Match LIMIT 10;
SELECT date, home_team_goal, away_team_goal FROM Match LIMIT 10;

-- 2.1.4
SELECT count(*) FROM Match;                                        -- 25979
SELECT count(*) FROM Match WHERE season = '2015/2016';             -- 3326
SELECT date, home_team_goal, away_team_goal,
       home_team_goal + away_team_goal AS total_goals
FROM Match ORDER BY total_goals DESC, date LIMIT 5;                -- 12, 12, 11, 10, 10

-- 2.2.4
SELECT p.player_name, pa.overall_rating, pa.date
FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id
ORDER BY pa.overall_rating DESC, pa.date LIMIT 5;                  -- Lionel Messi 94 x5

-- 2.2.5
SELECT count(*) FROM Match;                                        -- 25979
SELECT count(*) FROM Match m JOIN Team t ON m.home_team_api_id = t.team_api_id;  -- 25979
SELECT count(*) FROM Player_Attributes;                            -- 183978
SELECT count(*) FROM Player_Attributes pa
JOIN Player p ON pa.player_api_id = p.player_api_id;               -- 183978
SELECT count(*), count(DISTINCT team_api_id) FROM Team;            -- 299, 299

-- 2.3.2
SELECT count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals FROM Match;  -- 25979, 70287
SELECT season, count(*) AS matches, sum(home_team_goal + away_team_goal) AS goals
FROM Match GROUP BY season ORDER BY season;                        -- 2015/2016: 3326, 9162

-- 2.3.3 and capstone question 1
SELECT l.name, count(*) AS matches, sum(m.home_team_goal + m.away_team_goal) AS goals,
       round(avg(m.home_team_goal + m.away_team_goal), 2) AS goals_per_match
FROM Match m JOIN League l ON m.league_id = l.id
GROUP BY l.name ORDER BY goals_per_match DESC;                     -- 11 rows, Eredivisie 3.08 first

-- capstone question 2: see 2.3.2 (goals per season)

-- capstone question 3
SELECT sum(CASE WHEN home_team_goal > away_team_goal THEN 1 ELSE 0 END) AS home_wins,   -- 11917
       sum(CASE WHEN home_team_goal = away_team_goal THEN 1 ELSE 0 END) AS draws,        -- 6596
       sum(CASE WHEN home_team_goal < away_team_goal THEN 1 ELSE 0 END) AS away_wins     -- 7466
FROM Match;

-- capstone question 4
SELECT t.team_long_name, sum(m.home_team_goal) AS home_goals
FROM Match m JOIN Team t ON m.home_team_api_id = t.team_api_id
GROUP BY t.team_long_name ORDER BY home_goals DESC LIMIT 5;        -- Real Madrid CF 505, FC Barcelona 495, Celtic 389, ...

-- capstone question 5
SELECT p.player_name, max(pa.overall_rating) AS best_rating
FROM Player p JOIN Player_Attributes pa ON pa.player_api_id = p.player_api_id
GROUP BY p.player_name ORDER BY best_rating DESC, p.player_name LIMIT 5;  -- Messi 94, Ronaldo 93, Buffon 93, Rooney 93, Coupet 92
