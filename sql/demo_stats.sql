-- Course 2 examples in SQL (DuckDB; plain enough for Databricks SQL), by lesson. Course 5 reuses them.
-- Each query has a Python twin in src/dbx_ds/course2.py; tests/test_demo_sql.py checks they agree.

-- 1.1.5 percentiles of overall_rating
SELECT count(overall_rating) AS n,
       quantile_cont(overall_rating, 0.25) AS p25, quantile_cont(overall_rating, 0.50) AS p50,
       quantile_cont(overall_rating, 0.75) AS p75, quantile_cont(overall_rating, 0.95) AS p95,
       quantile_cont(overall_rating, 0.99) AS p99,
       quantile_cont(overall_rating, 0.75) - quantile_cont(overall_rating, 0.25) AS iqr
FROM Player_Attributes;

-- 1.3.2 leagues side by side
SELECT l.name, count(*) AS matches, avg(m.home_team_goal + m.away_team_goal) AS goals_per_match
FROM Match m JOIN League l ON m.league_id = l.id
GROUP BY l.name ORDER BY goals_per_match DESC, l.name;

-- 1.3.3 home, draw and away shares
SELECT avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END) AS home_win,
       avg(CASE WHEN home_team_goal = away_team_goal THEN 1.0 ELSE 0.0 END) AS draw,
       avg(CASE WHEN home_team_goal < away_team_goal THEN 1.0 ELSE 0.0 END) AS away_win
FROM Match;

-- 1.3.3 home win rate per league
SELECT l.name, avg(CASE WHEN m.home_team_goal > m.away_team_goal THEN 1.0 ELSE 0.0 END) AS home_win_rate
FROM Match m JOIN League l ON m.league_id = l.id
GROUP BY l.name ORDER BY home_win_rate DESC, l.name;

-- 2.1.3 independent events
SELECT avg(CASE WHEN home_team_goal = 0 THEN 1.0 ELSE 0.0 END) AS p_home0,
       avg(CASE WHEN away_team_goal = 0 THEN 1.0 ELSE 0.0 END) AS p_away0,
       avg(CASE WHEN home_team_goal = 0 AND away_team_goal = 0 THEN 1.0 ELSE 0.0 END) AS p_0_0,
       corr(home_team_goal, away_team_goal) AS corr_goals
FROM Match;

-- 2.1.4 conditional probability
SELECT avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END) AS p_win,
       avg(CASE WHEN home_team_goal >= 1 THEN 1.0 ELSE 0.0 END) AS p_scored,
       sum(CASE WHEN home_team_goal > away_team_goal AND home_team_goal >= 1 THEN 1.0 ELSE 0.0 END)
         / sum(CASE WHEN home_team_goal >= 1 THEN 1.0 ELSE 0.0 END) AS p_win_given_scored
FROM Match;

-- 2.1.5 fair decimal odds
SELECT outcome, rate, 1.0 / rate AS fair_odds FROM (
  SELECT 'home win' AS outcome, avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END) AS rate FROM Match
  UNION ALL
  SELECT 'draw', avg(CASE WHEN home_team_goal = away_team_goal THEN 1.0 ELSE 0.0 END) FROM Match
  UNION ALL
  SELECT 'away win', avg(CASE WHEN home_team_goal < away_team_goal THEN 1.0 ELSE 0.0 END) FROM Match
) ORDER BY rate DESC;

-- 2.2.3 Poisson probabilities for k = 0 to 7 home goals
SELECT k, exp(-lam) * pow(lam, k) / factorial(CAST(k AS INTEGER)) AS poisson_p
FROM (SELECT avg(home_team_goal) AS lam FROM Match), generate_series(0, 7) AS t(k)
ORDER BY k;

-- 2.2.4 observed share of home goals by k, 0 to 7
SELECT k, (SELECT count(*) FROM Match WHERE home_team_goal = k) * 1.0 / (SELECT count(*) FROM Match) AS observed
FROM generate_series(0, 7) AS t(k) ORDER BY k;

-- 2.3.2 correlations
SELECT corr(overall_rating, potential) AS rating_potential,
       corr(overall_rating, sprint_speed) AS rating_sprint_speed,
       corr(overall_rating, finishing) AS rating_finishing
FROM Player_Attributes;

-- 2.3.4 z-score of a rating of 84
SELECT avg(overall_rating) AS mean, stddev_samp(overall_rating) AS sd,
       (84 - avg(overall_rating)) / stddev_samp(overall_rating) AS z_84
FROM Player_Attributes;

-- 3.1.3 league mean goals with z
SELECT name, goals_per_match, (goals_per_match - avg(goals_per_match) OVER ()) / stddev_samp(goals_per_match) OVER () AS z
FROM (SELECT l.name, avg(m.home_team_goal + m.away_team_goal) AS goals_per_match
      FROM Match m JOIN League l ON m.league_id = l.id GROUP BY l.name)
ORDER BY goals_per_match DESC, name;

-- 3.1.4 typical error of the home win rate
SELECT count(*) AS n, avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END) AS rate,
       sqrt(avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END)
            * (1 - avg(CASE WHEN home_team_goal > away_team_goal THEN 1.0 ELSE 0.0 END)) / count(*)) AS std_error
FROM Match;
