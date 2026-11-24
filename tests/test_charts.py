"""Charts are deterministic and `show` degrades to a receipt line off Databricks."""

from __future__ import annotations

import builtins
import re

import numpy as np
import pytest
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from dbx_ds import charts

BINS = [(0.0, 0.1, 0.2, 5), (0.5, 0.55, 0.5, 9)]


EXPECTED_LABELS = [
    ("x", "y"),
    ("k", "share"),
    ("rest", "rate"),
    ("a", "b"),
    ("mean predicted probability", "observed rate"),
]


def _all() -> list[Figure]:
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
        assert (ax.get_xlabel(), ax.get_ylabel()) == EXPECTED_LABELS[i - 1]
        charts.svg(fig)


def test_svg_is_byte_identical_for_equal_data() -> None:
    a = charts.svg(charts.scatter_chart("t", "a", "b", [(1, 2), (3, 4)]))
    b = charts.svg(charts.scatter_chart("t", "a", "b", [(1, 2), (3, 4)]))
    assert a == b
    assert a.startswith(b"<?xml") and b"<svg" in a
    assert b"<dc:date>" not in a


def test_show_prints_a_receipt_without_display(capsys: pytest.CaptureFixture[str]) -> None:
    charts.show(charts.bar_chart("rest days", "r", "p", ["1"], [0.5]))
    assert re.fullmatch(r"chart rest days sha256:[0-9a-f]{12}\n", capsys.readouterr().out)


def test_show_calls_display_when_it_exists(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    seen: list[str] = []
    monkeypatch.setattr(builtins, "display", lambda fig: seen.append(fig.axes[0].get_title()), raising=False)
    charts.show(charts.line_chart("shown", "x", "y", [(1, 1)]))
    assert seen == ["shown"]
    assert capsys.readouterr().out == ""


def test_each_chart_draws_the_rows_it_was_given() -> None:
    line, grouped, bars, scatter, calib = _all()
    assert line.axes[0].lines[0].get_xydata().tolist() == [[10, 0.4], [20, 0.5]]
    heights = [p.get_height() for p in grouped.axes[0].patches]
    xs = [p.get_x() for p in grouped.axes[0].patches]
    assert heights == [0.3, 0.7, 0.4, 0.6]
    assert len(set(xs)) == 4 and xs[0] < xs[2] < xs[1] < xs[3]
    assert [p.get_height() for p in bars.axes[0].patches] == [0.4, 0.5]
    assert [t.get_text() for t in bars.axes[0].get_xticklabels()] == ["1", "2"]
    assert np.asarray(scatter.axes[0].collections[0].get_offsets()).tolist() == [[1, 2], [3, 4]]
    diag, model = calib.axes[0].lines
    assert diag.get_xydata().tolist() == [[0, 0], [1, 1]]
    assert model.get_xydata().tolist() == [[0.1, 0.2], [0.55, 0.5]]


def test_show_closes_the_figure_both_ways(monkeypatch: pytest.MonkeyPatch) -> None:
    plt.close("all")
    charts.show(charts.bar_chart("a", "x", "y", ["1"], [1]))
    assert plt.get_fignums() == []
    monkeypatch.setattr(builtins, "display", lambda fig: None, raising=False)
    charts.show(charts.bar_chart("b", "x", "y", ["1"], [1]))
    assert plt.get_fignums() == []


def test_display_is_found_in_the_ipython_user_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class Shell:
        user_ns = {"display": lambda fig: seen.append(fig.axes[0].get_title())}

    monkeypatch.setattr(builtins, "get_ipython", lambda: Shell(), raising=False)
    charts.show(charts.line_chart("ns", "x", "y", [(1, 1)]))
    assert seen == ["ns"]


def test_namespace_display_beats_the_builtin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ns: list[str] = []
    builtin: list[str] = []

    class Shell:
        user_ns = {"display": lambda fig: ns.append("ns")}

    monkeypatch.setattr(builtins, "get_ipython", lambda: Shell(), raising=False)
    monkeypatch.setattr(builtins, "display", lambda fig: builtin.append("builtin"), raising=False)
    charts.show(charts.line_chart("p", "x", "y", [(1, 1)]))
    assert (ns, builtin, capsys.readouterr().out) == (["ns"], [], "")


def test_legends_and_ticks_carry_the_series_names() -> None:
    _, grouped, _, _, calib = _all()
    assert [t.get_text() for t in grouped.axes[0].get_legend().get_texts()] == ["real", "poisson"]
    assert [t.get_text() for t in grouped.axes[0].get_xticklabels()] == ["0", "1"]
    assert [t.get_text() for t in calib.axes[0].get_legend().get_texts()] == ["perfect", "model"]


def test_grouped_bar_ticks_sit_at_the_middle_of_each_pair() -> None:
    ax = _all()[1].axes[0]
    xs = [p.get_x() + p.get_width() / 2 for p in ax.patches]
    assert ax.get_xticks().tolist() == pytest.approx([(xs[0] + xs[2]) / 2, (xs[1] + xs[3]) / 2])
