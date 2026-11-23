from __future__ import annotations

import pytest

from dbx_ds import mvp


def test_season_of_both_sides_of_august() -> None:
    assert mvp.season_of("2015-09-21 00:00:00") == "2015/2016"
    assert mvp.season_of("2016-02-18 00:00:00") == "2015/2016"
    assert mvp.season_of("2015-08-01 00:00:00") == "2015/2016"
    assert mvp.season_of("2016-07-31 00:00:00") == "2015/2016"


def test_latest_ratings_keeps_newest_and_breaks_date_ties_on_row_id() -> None:
    rows = [
        (1, "2015-09-01 00:00:00", 5, 70.0),
        (1, "2016-01-01 00:00:00", 6, 75.0),
        (1, "2015-10-01 00:00:00", 7, 72.0),
        (2, "2015-09-01 00:00:00", 1, 60.0),
        (2, "2015-09-01 00:00:00", 2, 61.0),
        (2, "2015-09-01 00:00:00", 0, 59.0),
        (1, "2016-09-01 00:00:00", 9, 80.0),
    ]
    assert mvp.latest_ratings(rows) == {
        ("2015/2016", 1): 75.0,
        ("2015/2016", 2): 61.0,
        ("2016/2017", 1): 80.0,
    }


def test_points() -> None:
    assert (mvp.points(2, 1), mvp.points(1, 1), mvp.points(0, 1)) == (3, 1, 0)


def test_involvement_counts_starts_and_points_and_skips_empty_slots() -> None:
    out = mvp.involvement(
        [
            ("s", 2, 1, [1, None], [2]),
            ("s", 0, 0, [1], [2, 3]),
        ]
    )
    assert out == {("s", 1): (2, 4), ("s", 2): (2, 1), ("s", 3): (1, 1)}


def _field(season: str, n: int, starts: int, pts: int, rating: float = 70.0) -> tuple[dict, dict, dict]:
    ratings = {(season, p): rating for p in range(1, n + 1)}
    played = {(season, p): (starts, pts) for p in range(1, n + 1)}
    names = {p: f"P{p}" for p in range(1, n + 1)}
    return ratings, played, names


def test_score_is_weighted_rating_and_win_share() -> None:
    ratings, played, names = _field("s", 1, 10, 30, 80.0)
    (row,) = mvp.score_players(ratings, played, names)
    assert row.win_share == pytest.approx(100.0)
    assert row.score == pytest.approx(0.7 * 80.0 + 0.3 * 100.0)
    assert row.is_mvp and not row.is_adjacent
    assert (row.score_rank, row.rating_rank) == (1, 1)


def test_filters_unplayed_unnamed_and_part_time_players() -> None:
    ratings = {("s", 1): 70.0, ("s", 2): 70.0, ("s", 3): 70.0, ("s", 4): 70.0}
    played = {("s", 1): (10, 10), ("s", 2): (9, 9), ("s", 3): (10, 10)}
    names = {1: "One", 2: "Two", 4: "Four"}
    rows = mvp.score_players(ratings, played, names)
    assert [r.player_api_id for r in rows] == [1]


def test_ties_break_on_player_id() -> None:
    ratings, played, names = _field("s", 3, 20, 30)
    rows = mvp.score_players(ratings, played, names)
    assert [r.player_api_id for r in rows] == [1, 2, 3]


def test_adjacent_by_gap_not_mvp() -> None:
    ratings = {("s", p): 99.0 - p for p in range(1, 14)}  # ratings 98..86, rank = id
    played = {("s", p): (30, 0) for p in range(1, 14)}
    names = {p: f"P{p}" for p in range(1, 14)}
    # Player 13 is the lowest rated but wins the most: score rank 2 behind player 14.
    ratings[("s", 14)] = 99.0
    played[("s", 14)] = (30, 90)
    names[14] = "P14"
    played[("s", 13)] = (30, 90)
    rows = {r.player_api_id: r for r in mvp.score_players(ratings, played, names)}
    assert rows[14].is_mvp
    assert rows[13].score_rank == 2 and rows[13].rating_rank == 14
    assert rows[13].is_adjacent  # gap of 12 places
    assert not rows[1].is_adjacent


def test_adjacent_by_few_appearances_only_inside_top_rank() -> None:
    ratings, played, names = _field("s", 25, 30, 0)
    # Players 2..25 identical on score except for the tie-break on id; make 2 a part-timer.
    played[("s", 2)] = (15, 45)
    rows = {r.player_api_id: r for r in mvp.score_players(ratings, played, names)}
    assert rows[2].score_rank == 1 and rows[2].is_mvp and not rows[2].is_adjacent
    played[("s", 3)] = (15, 0)
    rows = {r.player_api_id: r for r in mvp.score_players(ratings, played, names)}
    assert rows[3].score_rank <= mvp.TOP_SCORE_RANK
    # player 3 scores the same as the other 0-point players at 70: ordered by id, rank 3 after 2 and 1
    assert rows[3].appearances == 15 and rows[3].is_adjacent
    played[("s", 25)] = (15, 0)
    rows = {r.player_api_id: r for r in mvp.score_players(ratings, played, names)}
    assert rows[25].score_rank > mvp.TOP_SCORE_RANK and not rows[25].is_adjacent
