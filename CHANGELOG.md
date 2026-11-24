# Changelog

## Unreleased

- Scaffold, ODbL fixture, Elo and MVP in Python and SQL with a parity test, five course notebooks, CI gate.
- Fix: `sql/elo_dbx.sql` and the Course 5 `elo_sides` view replay a date on which a team plays twice one match per step in `match_api_id` order, as `elo.py` does (`tests/test_same_day.py`).
- Not yet verified on Databricks SQL / Free Edition (DuckDB only).
