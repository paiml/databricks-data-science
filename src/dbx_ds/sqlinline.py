"""Make each statement of a demo file run alone: the views it reads become leading CTEs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_VIEW = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP|TEMPORARY)\s+VIEW\s+(\w+)\s+AS\s+(.*)", re.I | re.S)
_WITH = re.compile(r"WITH\s+(RECURSIVE\s+)?", re.I)


def _needs(sql: str, views: Mapping[str, str]) -> list[str]:
    """Views that sql reads, directly or through other views, dependencies first."""
    order: list[str] = []
    active: set[str] = set()

    def visit(text: str) -> None:
        for name, body in views.items():
            if name not in order and name not in active and re.search(rf"\b{name}\b", text, re.I):
                active.add(name)
                visit(body)
                active.discard(name)
                order.append(name)

    visit(sql)
    return order


def _prefixed(stmt: str, names: list[str], views: Mapping[str, str]) -> str:
    """stmt with the named views as leading CTEs, merged into its own WITH if it has one."""
    ctes = ",\n".join(f"{n} AS (\n{views[n]}\n)" for n in names)
    head = _WITH.match(stmt)
    if head is None:
        return f"WITH {ctes}\n{stmt}"
    return f"WITH {head.group(1) or ''}{ctes},\n{stmt[head.end() :]}"


def standalone(statements: list[str], setup: Sequence[str] = ()) -> list[str | None]:
    """Rewrite statements so each runs alone on a fresh session.

    The Statement Execution API shares no session between calls, so a TEMP VIEW made by one statement is gone
    for the next. Each CREATE ... TEMP VIEW (from setup, then from statements) is recorded, not run (None in the
    result), and every other statement gets the views it reads, and theirs, as leading CTEs. A view redefined
    later in the file replaces the earlier one from that point on, as it would in a session.
    """
    views: dict[str, str] = {}
    for stmt in setup:
        if m := _VIEW.fullmatch(stmt):
            views[m.group(1)] = m.group(2)
    out: list[str | None] = []
    for stmt in statements:
        m = _VIEW.fullmatch(stmt)
        if m:
            views[m.group(1)] = m.group(2)
        names = [] if m else _needs(stmt, views)
        out.append(None if m else _prefixed(stmt, names, views) if names else stmt)
    return out
