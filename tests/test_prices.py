from __future__ import annotations

from decimal import Decimal

import pytest

from priceparser.errors import ParseError
from priceparser.models import Availability
from priceparser.prices import parse_availability, parse_price, parse_rating


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("£51.77", Decimal("51.77")),
        ("$416.99", Decimal("416.99")),
        ("$1,149.99", Decimal("1149.99")),
        ("1 149,99", Decimal("1149.99")),
        ("51,77", Decimal("51.77")),
        ("1.149", Decimal("1149.00")),
        ("1.149,50", Decimal("1149.50")),
        ("51.775", Decimal("51.78")),
        ("0", Decimal("0.00")),
        ("12.345.67", Decimal("12345.67")),
        ("1.2.3", Decimal("12.30")),
    ],
)
def test_parse_price_examples(raw: str, expected: Decimal) -> None:
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw", ["", "free", "-1.00"])
def test_parse_price_examples_errors(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_price(raw)


def test_parse_availability_in_stock() -> None:
    assert parse_availability("In stock (22 available)") == Availability.IN_STOCK


def test_parse_availability_out_before_in() -> None:
    assert parse_availability("not in stock") == Availability.OUT_OF_STOCK


def test_parse_availability_unknown() -> None:
    assert parse_availability("предзаказ") == Availability.UNKNOWN


def test_parse_availability_blank() -> None:
    assert parse_rating(None) is None
    assert parse_rating("   ") is None
    assert parse_availability(None) == Availability.UNKNOWN
    assert parse_availability("   ") == Availability.UNKNOWN


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3", 3.0), ("3,5", 3.5), ("0", 0.0)],
)
def test_parse_rating_numeric(raw: str, expected: float) -> None:
    assert parse_rating(raw) == expected


def test_parse_rating_out_of_range(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="priceparser.prices")
    assert parse_rating("6") is None
    assert parse_rating("nope") is None
    joined = " ".join(r.message for r in caplog.records).casefold()
    assert "рейтинг" in joined
