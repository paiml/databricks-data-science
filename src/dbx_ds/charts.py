"""Deterministic charts for the notebook cells (matplotlib, Agg backend, fixed SVG hash salt).

Each builder takes plain rows and returns a Figure; `show` hands it to Databricks `display` when that exists and
otherwise prints a one-line receipt (title and the sha256 of the SVG), so a local run stays text-only and testable.
"""

from __future__ import annotations

import builtins
import hashlib
import io
from collections.abc import Callable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

_STYLE = {"svg.hashsalt": "dbx-ds", "svg.fonttype": "none", "figure.figsize": (6.0, 3.6)}


def _figure(title: str, xlabel: str, ylabel: str) -> tuple[Figure, Axes]:
    with matplotlib.rc_context(_STYLE):
        fig, ax = plt.subplots()
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return fig, ax


def line_chart(title: str, xlabel: str, ylabel: str, points: Sequence[tuple[float, float]]) -> Figure:
    """2.1.2: running home win rate against matches seen."""
    fig, ax = _figure(title, xlabel, ylabel)
    ax.plot([p[0] for p in points], [p[1] for p in points], marker="o")
    return fig


def grouped_bars(
    title: str, xlabel: str, ylabel: str, labels: Sequence[str], series: Sequence[tuple[str, Sequence[float]]]
) -> Figure:
    """2.2.4: observed share beside the Poisson share for each k."""
    fig, ax = _figure(title, xlabel, ylabel)
    width = 0.8 / len(series)
    for i, (name, values) in enumerate(series):
        ax.bar([j + i * width for j in range(len(labels))], values, width, label=name)
    ax.set_xticks([j + 0.4 - width / 2 for j in range(len(labels))], list(labels))
    ax.legend()
    return fig


def bar_chart(title: str, xlabel: str, ylabel: str, labels: Sequence[str], values: Sequence[float]) -> Figure:
    """1.3.4: home win rate for each rest-day value."""
    fig, ax = _figure(title, xlabel, ylabel)
    ax.bar(list(labels), list(values))
    return fig


def scatter_chart(title: str, xlabel: str, ylabel: str, points: Sequence[tuple[float, float]]) -> Figure:
    """2.3.2: one seeded scatter of attribute pairs."""
    fig, ax = _figure(title, xlabel, ylabel)
    ax.scatter([p[0] for p in points], [p[1] for p in points], s=8, alpha=0.6)
    return fig


def calibration_chart(title: str, bins: Sequence[tuple[float, float, float, int]]) -> Figure:
    """2.3.4: mean predicted against observed rate per bin, with the perfect-calibration diagonal."""
    fig, ax = _figure(title, "mean predicted probability", "observed rate")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="perfect")
    ax.plot([b[1] for b in bins], [b[2] for b in bins], marker="o", label="model")
    ax.legend()
    return fig


def svg(fig: Figure) -> bytes:
    """The figure as SVG with no timestamp, so equal data gives equal bytes."""
    buf = io.BytesIO()
    with matplotlib.rc_context(_STYLE):
        fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    return buf.getvalue()


def _display() -> Callable[[Figure], object] | None:
    """Databricks `display`: the kernel's user namespace first, then the builtin IPython installs."""
    ip = getattr(builtins, "get_ipython", lambda: None)()
    found = getattr(ip, "user_ns", {}).get("display") or getattr(builtins, "display", None)
    return found if callable(found) else None


def show(fig: Figure) -> None:
    """Databricks: `display(fig)`. Elsewhere: print `chart <title> sha256:<first 12 hex>`."""
    title = fig.axes[0].get_title()
    shown = _display()
    if shown is not None:
        shown(fig)
    else:
        print(f"chart {title} sha256:{hashlib.sha256(svg(fig)).hexdigest()[:12]}")
    plt.close(fig)
