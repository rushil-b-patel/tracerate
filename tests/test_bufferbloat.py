import pytest

from tracerate.bufferbloat import _grade, _percentile


# --- _grade: each threshold boundary -----------------------------------------
# Thresholds are <5 A+, <30 A, <60 B, <200 C, <400 D, else F. The plan pins
# these to make the methodology change deterministic; do not relax them.

@pytest.mark.parametrize(
    "delta, expected",
    [
        (0, "A+"),
        (4.9, "A+"),
        (5, "A"),
        (29.9, "A"),
        (30, "B"),
        (59.9, "B"),
        (60, "C"),
        (199.9, "C"),
        (200, "D"),
        (399.9, "D"),
        (400, "F"),
        (10_000, "F"),
    ],
)
def test_grade_boundaries(delta, expected):
    assert _grade(delta) == expected


# --- _percentile: shape and edge cases ---------------------------------------

def test_percentile_p90_is_between_min_and_max():
    samples = [1.0, 5.0, 12.0, 18.0, 25.0, 33.0, 47.0, 80.0, 120.0, 250.0]
    result = _percentile(samples, 90)
    assert result > min(samples)
    assert result <= max(samples)


def test_percentile_constant_list_returns_constant():
    assert _percentile([10, 10, 10], 90) == 10


def test_percentile_p100_returns_max():
    assert _percentile([3, 1, 4, 1, 5, 9, 2, 6], 100) == 9


def test_percentile_p0_returns_min():
    assert _percentile([3, 1, 4, 1, 5, 9, 2, 6], 0) == 1


def test_percentile_single_element_returns_that_element():
    assert _percentile([42.0], 90) == 42.0
    assert _percentile([42.0], 50) == 42.0


def test_percentile_empty_returns_zero():
    # Callers treat "no samples" as 0.0; pin that contract here.
    assert _percentile([], 90) == 0.0
    assert _percentile([], 50) == 0.0


def test_percentile_p90_known_value_nearest_rank():
    # Nearest-rank p90 of [10,20,30,40]: rank = ceil(0.9*4) = 4 -> 40.
    assert _percentile([10, 20, 30, 40], 90) == 40


def test_percentile_p90_picks_loaded_sample_not_min():
    # The whole point of the methodology fix: under load, p90 must reflect the
    # inflated tail (queueing delay), not the best-case minimum.
    samples = [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 250.0]
    p90 = _percentile(samples, 90)
    assert p90 >= 28.0
    assert p90 != min(samples)
