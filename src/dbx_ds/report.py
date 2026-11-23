"""Plain-text output helpers so notebook cells stay one line long."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import duckdb


def table_lines(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    """A left-aligned text table: header, rule, then one line per row."""
    cells = [[_cell(v) for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    lines = ["  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    lines.extend("  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)).rstrip() for r in cells)
    return lines


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}" if abs(value) < 1e4 else f"{value:,.0f}"
    return "" if value is None else str(value)


def show(con: duckdb.DuckDBPyConnection, sql: str, limit: int = 20) -> None:
    """Run a query and print its first `limit` rows as a table."""
    result = con.execute(sql)
    columns = [d[0] for d in result.description]
    rows = result.fetchall()
    print("\n".join(table_lines(columns, rows[:limit])))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more rows")


def pairs(items: Sequence[tuple[str, Any]]) -> None:
    """Print `label value` lines, labels padded to one width."""
    width = max(len(label) for label, _ in items)
    for label, value in items:
        print(f"{label:<{width}}  {_cell(value)}")
