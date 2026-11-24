"""Make each statement of a demo file run alone: the views it reads become leading CTEs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_VIEW = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP|TEMPORARY)\s+VIEW\s+(\w+)\s+AS\s+(.*)", re.I | re.S)
_WITH = re.compile(r"WITH\s+(RECURSIVE\s+)?", re.I)
_SESSION = re.compile(r"\s*(?:SET|RESET|USE|CREATE|DROP|ALTER)\b", re.I)
_QUERY = re.compile(r"\s*(?:SELECT|WITH|\()", re.I)
_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def _needs(sql: str, views: Mapping[str, str]) -> list[str]:
    """Views that sql reads, directly or through other views, dependencies first."""
    order: list[str] = []
    active: set[str] = set()

    def visit(text: str) -> None:
        text = _LITERAL.sub("''", text)
        for name, body in views.items():
            if name not in order and re.search(rf"\b{name}\b", text, re.I):
                if name in active:
                    raise ValueError(f"view {name!r} reads itself, directly or through another view")
                active.add(name)
                visit(body)
                active.discard(name)
                order.append(name)

    visit(sql)
    return order


def _check(stmt: str, names: list[str]) -> None:
    if not _QUERY.match(stmt):
        raise ValueError(f"cannot inline views into a non-query statement: {stmt[:60]!r}")
    for n in names:
        if re.search(rf"\b{n}\s+AS\s*\(", stmt, re.I):
            raise ValueError(f"statement defines a CTE named like the view {n!r}")


def _prefixed(stmt: str, names: list[str], views: Mapping[str, str]) -> str:
    """stmt with the named views as leading CTEs, merged into its own WITH if it has one."""
    _check(stmt, names)
    ctes = ",\n".join(f"{n} AS (\n{views[n]}\n)" for n in names)
    head = _WITH.match(stmt)
    if head is None:
        return f"WITH {ctes}\n{stmt}"
    if head.group(1):  # a RECURSIVE list lets every CTE see every other, so keep the statement apart
        return f"WITH {ctes}\nSELECT * FROM (\n{stmt}\n) q"
    return f"WITH {ctes},\n{stmt[head.end() :]}"


def _record(stmt: str, views: dict[str, str], in_setup: bool) -> bool:
    """Remember a CREATE TEMP VIEW (True); refuse anything else that would change a session (setup: any non-view)."""
    m = _VIEW.fullmatch(stmt)
    if m:
        views[m.group(1)] = m.group(2)
    elif in_setup or _SESSION.match(stmt):
        raise ValueError(f"statement changes session state or an unparsed view, it would be lost: {stmt[:60]!r}")
    return m is not None


def standalone(statements: list[str], setup: Sequence[str] = ()) -> list[str | None]:
    """Rewrite statements so each runs alone on a fresh session.

    The Statement Execution API shares no session between calls, so a TEMP VIEW made by one statement is gone
    for the next. Each CREATE ... TEMP VIEW (from setup, then from statements) is recorded, not run (None in the
    result), and every other statement gets the views it reads, and theirs, as leading CTEs. A view redefined
    later in the file replaces the earlier one from that point on, as it would in a session. Anything that
    cannot be carried this way (a SET or other DDL, a view cycle, a non-query reading a view,
    a CTE named like a view) raises ValueError.
    Not covered: Databricks' recursion depth limit for the WITH RECURSIVE inside elo_state.
    """
    views: dict[str, str] = {}
    for stmt in setup:
        _record(stmt, views, True)
    out: list[str | None] = []
    for stmt in statements:
        if _record(stmt, views, False):
            out.append(None)
            continue
        names = _needs(stmt, views)
        out.append(_prefixed(stmt, names, views) if names else stmt)
    return out
