# Changelog

## Unreleased

- Scaffold, ODbL fixture, Elo and MVP in Python and SQL with a parity test, five course notebooks, CI gate.
- Fix: `sql/elo_dbx.sql` and the Course 5 `elo_sides` view replay a date on which a team plays twice one match per step in `match_api_id` order, as `elo.py` does (`tests/test_same_day.py`).
- Chart cells (matplotlib, deterministic SVG, `dbx_ds.charts`) for c2 2.1.2, 2.2.4, 2.3.2 and c3 1.3.4, 2.3.4.
- Not yet verified on Databricks SQL / Free Edition (DuckDB only).
- Courses 4 and 5: all-league current Elo table in Python (`course4.current_top`) and SQL (`demo_elo.sql` 3.1.1), full-data test pinning SL Benfica 1868.8 at #1 in both, and report parity (MVP and shortlist) between the two languages.
