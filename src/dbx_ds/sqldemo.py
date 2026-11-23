"""Read a demo .sql file into named statements.

A section starts at a comment line that begins with a lesson number (`-- 2.1.4`) or the word
`capstone`. Comments are dropped and statements split on `;`, so the file stays plain SQL that
also runs in a Databricks SQL cell.
"""

from __future__ import annotations

import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
_SECTION = re.compile(r"^--\s*((?:\d+\.\d+\.\d+|capstone)\b.*)$")


def strip_comments(line: str) -> str:
    return line.split("--", 1)[0].rstrip()


def parse(text: str) -> list[tuple[str, str]]:
    """(section label, statement) pairs in file order. Statement text has no trailing `;`."""
    out: list[tuple[str, str]] = []
    label = ""
    buffer: list[str] = []
    for line in text.splitlines():
        match = _SECTION.match(line.strip())
        if match:
            label = match.group(1).strip()
            continue
        body = strip_comments(line)
        if ";" in body:
            head, _, _ = body.partition(";")
            buffer.append(head)
            out.append((label, "\n".join(buffer).strip()))
            buffer = []
        else:
            buffer.append(body)
    return out


def load(name: str) -> list[tuple[str, str]]:
    return parse((SQL_DIR / name).read_text())


def normalise(sql: str) -> str:
    """Collapse whitespace so a statement can be matched inside a notebook cell."""
    return " ".join(sql.split())
