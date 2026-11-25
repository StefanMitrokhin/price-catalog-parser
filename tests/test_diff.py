from __future__ import annotations

from decimal import Decimal

from tests.fakes import make_product

from priceparser.diff import diff_products
from priceparser.models import ChangeKind


def _five_product_sets() -> tuple[list, list]:
    fixed = make_product().scraped_at
    common_up = make_product(
        name="Up",
        url="https://example.com/up",
        price=Decimal("100.00"),
        scraped_at=fixed,
    )
    common_up_new = make_product(
        name="Up",
        url="https://example.com/up",
        price=Decimal("110.00"),
        scraped_at=fixed,
    )
    common_down = make_product(
        name="Down",
        url="https://example.com/down",
        price=Decimal("50.00"),
        scraped_at=fixed,
    )
    common_down_new = make_product(
        name="Down",
        url="https://example.com/down",
        price=Decimal("40.00"),
        scraped_at=fixed,
    )
    common_same = make_product(
        name="Same",
        url="https://example.com/same",
        price=Decimal("5.00"),
        scraped_at=fixed,
    )
    fresh = make_product(
        name="Fresh",
        url="https://example.com/fresh",
        price=Decimal("1.00"),
        scraped_at=fixed,
    )
    gone = make_product(
        name="Gone",
        url="https://example.com/gone",
        price=Decimal("1.00"),
        scraped_at=fixed,
    )
    previous = [common_up, common_down, common_same, gone]
    current = [common_up_new, common_down_new, common_same, fresh]
    return previous, current


def test_kinds_and_counts() -> None:
    previous, current = _five_product_sets()
    report = diff_products(previous, current)
    assert report.new_count == 1
    assert report.removed_count == 1
    assert report.up_count == 1
    assert report.down_count == 1
    assert report.unchanged_count == 1
    assert len(report.changes) == 5
    dup_url = "https://example.com/dup"
    duplicate_prev = [
        make_product(url=dup_url, name="First"),
        make_product(url=dup_url, name="Second"),
    ]
    diff_products(duplicate_prev, [make_product(url=dup_url, name="Only")])


def test_sort_order() -> None:
    previous, current = _five_product_sets()
    report = diff_products(previous, current)
    names = [c.name for c in report.changes]
    assert names == ["Fresh", "Gone", "Up", "Down", "Same"]


def test_percent_half_up() -> None:
    prev = make_product(price=Decimal("3.00"), url="https://example.com/half")
    cur = make_product(price=Decimal("4.00"), url="https://example.com/half")
    change = diff_products([prev], [cur]).changes[0]
    assert change.delta_pct == Decimal("33.33")


def test_zero_old_price_percent_is_none() -> None:
    url = "https://example.com/zero"
    prev0 = make_product(price=Decimal("0.00"), url=url)
    cur0 = make_product(price=Decimal("0.00"), url=url)
    ch0 = diff_products([prev0], [cur0]).changes[0]
    assert ch0.kind == ChangeKind.UNCHANGED
    assert ch0.delta == Decimal("0.00")
    assert ch0.delta_pct is None

    prev = make_product(price=Decimal("0.00"), url="https://example.com/up")
    cur = make_product(price=Decimal("1.00"), url="https://example.com/up")
    ch1 = diff_products([prev], [cur]).changes[0]
    assert ch1.kind == ChangeKind.PRICE_UP
    assert ch1.delta_pct is None


def test_currency_mismatch_flag() -> None:
    url = "https://example.com/mismatch"
    prev = make_product(price=Decimal("100.00"), currency="USD", url=url)
    cur = make_product(price=Decimal("110.00"), currency="GBP", url=url)
    change = diff_products([prev], [cur]).changes[0]
    assert change.currency_mismatch is True
    assert change.currency == "GBP"
    assert change.kind == ChangeKind.PRICE_UP


def test_sku_and_url_do_not_match() -> None:
    prev = make_product(
        sku="abc",
        url="https://example.com/1",
        price=Decimal("10.00"),
    )
    cur = make_product(
        sku=None,
        url="https://example.com/1",
        price=Decimal("20.00"),
    )
    report = diff_products([prev], [cur])
    assert report.new_count == 1
    assert report.removed_count == 1
    assert report.up_count == 0
