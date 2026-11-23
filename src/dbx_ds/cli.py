"""Command line: dbx-ds data | fixture | elo | mvp."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from dbx_ds import data, elo, queries

DEFAULT_RAW = Path("data/raw/database.sqlite")
DEFAULT_PARQUET = Path("data/parquet")
DEFAULT_FIXTURE = Path("data/fixture")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dbx-ds", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data", help="download the database (sha256 checked) and export full Parquet")
    sub.add_parser("fixture", help="rebuild the small committed fixture from the downloaded file")
    for name in ("elo", "mvp"):
        cmd = sub.add_parser(name, help=f"print the {name} table")
        cmd.add_argument("--data-dir", type=Path, default=DEFAULT_FIXTURE)
        cmd.add_argument("--top", type=int, default=10)
    return parser


def _cmd_data(args: argparse.Namespace) -> None:
    data.fetch(DEFAULT_RAW)
    data.export_tables(DEFAULT_RAW, DEFAULT_PARQUET, data.full_queries())
    print(f"parquet written to {DEFAULT_PARQUET}")


def _cmd_fixture(args: argparse.Namespace) -> None:
    data.export_tables(DEFAULT_RAW, DEFAULT_FIXTURE, data.fixture_queries())
    print(f"fixture written to {DEFAULT_FIXTURE}")


def _cmd_elo(args: argparse.Namespace) -> None:
    con = data.connect(args.data_dir)
    table = elo.current_table(elo.season_ratings(queries.load_results(con)))
    teams = dict(con.execute("SELECT team_api_id, team_long_name FROM Team").fetchall())
    for team, rating in table[: args.top]:
        print(f"{rating:8.1f}  {teams[team]}")


def _cmd_mvp(args: argparse.Namespace) -> None:
    for row in queries.python_mvp(data.connect(args.data_dir)):
        if row.is_mvp or row.is_adjacent:
            label = "MVP" if row.is_mvp else "adj"
            print(f"{row.season}  {label}  {row.player_name}  score {row.score:.2f}")


COMMANDS = {"data": _cmd_data, "fixture": _cmd_fixture, "elo": _cmd_elo, "mvp": _cmd_mvp}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    COMMANDS[args.command](args)
    return 0
