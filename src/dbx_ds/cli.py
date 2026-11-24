"""Command line: dbx-ds data | fixture | elo | mvp."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dbx_ds import data, dbxapi, elo, queries

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
    dbx = sub.add_parser("dbx", help="drive a Databricks workspace over the REST API")
    dbx.add_argument("action", choices=["whoami", "import", "capture"])
    dbx.add_argument("--profile", default="DEFAULT")
    dbx.add_argument("--cfg", type=Path, default=Path.home() / ".databrickscfg")
    dbx.add_argument("--remote-dir", default="/Shared/dbx-ds")
    dbx.add_argument("--out", type=Path, default=Path("captures"))
    return parser


def _import_all(client: dbxapi.Client, remote_dir: str) -> None:
    notebooks = sorted(nb for nb in Path("notebooks").glob("course*") if nb.suffix in dbxapi.LANGUAGES)
    stems = [nb.stem for nb in notebooks]
    if len(stems) != len(set(stems)):
        raise SystemExit("dbx import: two notebooks share a stem and would overwrite each other")
    if not notebooks:
        raise SystemExit("dbx import: no notebooks/course*.py or .sql found (run from the repo root)")
    client.mkdirs(remote_dir)
    for nb in notebooks:
        client.import_notebook(nb, f"{remote_dir}/{nb.stem}")
        print(f"imported {nb.name}")


# demo_parity.sql full-joins the Python tables py_elo and py_mvp, which exist only in a local DuckDB session.
NOT_ON_DATABRICKS = {"demo_parity.sql"}


def _capture_all(client: dbxapi.Client, out: Path) -> None:
    wh = client.warehouse_id()
    for sql in sorted(Path("sql").glob("demo_*.sql")):
        if sql.name in NOT_ON_DATABRICKS:
            continue
        for path in dbxapi.capture(client, wh, sql, out):
            print(f"captured {path}")


def _cmd_dbx(args: argparse.Namespace) -> None:
    client = dbxapi.Client(*dbxapi.load_auth(args.cfg, args.profile))
    if args.action == "whoami":
        print(f"auth OK: {client.whoami()}")
    elif args.action == "import":
        _import_all(client, args.remote_dir)
    else:
        _capture_all(client, args.out)


def _cmd_data(args: argparse.Namespace) -> None:
    data.fetch(DEFAULT_RAW)
    data.export_tables(DEFAULT_RAW, DEFAULT_PARQUET, data.full_queries())
    print(f"parquet written to {DEFAULT_PARQUET}")


def _cmd_fixture(args: argparse.Namespace) -> None:
    data.export_tables(DEFAULT_RAW, DEFAULT_FIXTURE, data.fixture_queries())
    data.write_notice(DEFAULT_FIXTURE)
    print(f"fixture written to {DEFAULT_FIXTURE}")


def _cmd_elo(args: argparse.Namespace) -> None:
    con = data.connect(args.data_dir)
    table = elo.current_table(elo.season_ratings(queries.load_results(con)))
    teams = dict(con.execute("SELECT team_api_id, team_long_name FROM Team").fetchall())
    for team, rating in table[: args.top]:
        print(f"{rating:8.1f}  {teams[team]}")


def _cmd_mvp(args: argparse.Namespace) -> None:
    """Print the MVP and MVP-adjacent rows, at most --top per season, best score first."""
    rows = [r for r in queries.python_mvp(data.connect(args.data_dir)) if r.is_mvp or r.is_adjacent]
    shown: dict[str, int] = {}
    for row in sorted(rows, key=lambda r: (r.season, r.score_rank)):
        if shown.get(row.season, 0) >= args.top:
            continue
        shown[row.season] = shown.get(row.season, 0) + 1
        label = "MVP" if row.is_mvp else "adj"
        print(f"{row.season}  {label}  {row.player_name}  score {row.score:.2f}")


COMMANDS = {"data": _cmd_data, "fixture": _cmd_fixture, "elo": _cmd_elo, "mvp": _cmd_mvp, "dbx": _cmd_dbx}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except dbxapi.DbxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
