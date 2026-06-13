import pytest

from tracerate.cli import bar


def test_bar_max_value_zero_returns_all_empty():
    out = bar(value=50, max_value=0, width=20)
    assert out == "▱" * 20  # ▱ * 20
    assert len(out) == 20


def test_bar_max_value_negative_returns_all_empty():
    out = bar(value=50, max_value=-10, width=15)
    assert out == "▱" * 15
    assert len(out) == 15


def test_bar_value_equals_max_is_all_filled():
    out = bar(value=100, max_value=100, width=20)
    assert out == "▰" * 20  # ▰ * 20


def test_bar_value_zero_is_all_empty():
    out = bar(value=0, max_value=100, width=20)
    assert out == "▱" * 20


def test_bar_value_greater_than_max_clamps_and_does_not_overflow():
    out = bar(value=500, max_value=100, width=20)
    assert out == "▰" * 20
    assert len(out) == 20


@pytest.mark.parametrize(
    "value, max_value, width",
    [
        (0, 100, 20),
        (50, 100, 20),
        (100, 100, 20),
        (150, 100, 20),
        (3, 10, 7),
        (7, 10, 13),
        (1, 1, 1),
    ],
)
def test_bar_length_always_equals_width(value, max_value, width):
    assert len(bar(value, max_value, width)) == width


def test_bar_mid_value_rounds_correctly():
    # value=50, max=100, width=20 -> ratio=0.5 -> n=int(round(10))=10
    out = bar(value=50, max_value=100, width=20)
    assert out == "▰" * 10 + "▱" * 10
