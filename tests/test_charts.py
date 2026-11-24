"""Charts are deterministic and `show` degrades to a receipt line off Databricks."""

from __future__ import annotations

import builtins
import re

import pytest

from dbx_ds import charts

BINS = [(0.0, 0.1, 0.2, 5), (0.5, 0.55, 0.5, 9)]


def _all():
    return [
        charts.line_chart("t1", "x", "y", [(10, 0.4), (20, 0.5)]),
        charts.grouped_bars("t2", "k", "share", ["0", "1"], [("real", [0.3, 0.7]), ("poisson", [0.4, 0.6])]),
        charts.bar_chart("t3", "rest", "rate", ["1", "2"], [0.4, 0.5]),
        charts.scatter_chart("t4", "a", "b", [(1, 2), (3, 4)]),
        charts.calibration_chart("t5", BINS),
    ]


def test_every_builder_has_a_title_and_labelled_axes() -> None:
    for i, fig in enumerate(_all(), start=1):
        ax = fig.axes[0]
        assert ax.get_title() == f"t{i}"
        assert ax.get_xlabel() and ax.get_ylabel()
        charts.svg(fig)


def test_svg_is_byte_identical_for_equal_data() -> None:
    a = charts.svg(charts.scatter_chart("t", "a", "b", [(1, 2), (3, 4)]))
    b = charts.svg(charts.scatter_chart("t", "a", "b", [(1, 2), (3, 4)]))
    assert a == b
    assert a.startswith(b"<?xml") and b"<svg" in a


def test_show_prints_a_receipt_without_display(capsys: pytest.CaptureFixture[str]) -> None:
    charts.show(charts.bar_chart("rest days", "r", "p", ["1"], [0.5]))
    assert re.fullmatch(r"chart rest days sha256:[0-9a-f]{12}\n", capsys.readouterr().out)


def test_show_calls_display_when_it_exists(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    seen: list[str] = []
    monkeypatch.setattr(builtins, "display", lambda fig: seen.append(fig.axes[0].get_title()), raising=False)
    charts.show(charts.line_chart("shown", "x", "y", [(1, 1)]))
    assert seen == ["shown"]
    assert capsys.readouterr().out == ""
