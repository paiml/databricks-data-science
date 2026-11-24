"""A change log for data cleaning: every step that drops or alters rows is written down."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Change:
    step: str
    rows_before: int
    rows_after: int
    reason: str

    @property
    def rows_changed(self) -> int:
        return self.rows_before - self.rows_after


@dataclass
class ChangeLog:
    """Append-only list of cleaning steps."""

    entries: list[Change] = field(default_factory=list)

    def record(self, step: str, rows_before: int, rows_after: int, reason: str) -> Change:
        change = Change(step, rows_before, rows_after, reason)
        self.entries.append(change)
        return change

    def rows(self) -> list[tuple[str, int, int, int, str]]:
        return [(c.step, c.rows_before, c.rows_after, c.rows_changed, c.reason) for c in self.entries]

    def columns(self) -> list[str]:
        return ["step", "rows_before", "rows_after", "rows_dropped", "reason"]


def drop_nulls(values: list[float | None], step: str, reason: str, log: ChangeLog) -> list[float]:
    """Remove None values and write the step to the log."""
    kept = [v for v in values if v is not None]
    log.record(step, len(values), len(kept), reason)
    return kept
