from __future__ import annotations

from decimal import Decimal

import pytest
from tests.conftest import (
    BOOKS_ATTIC,
    BOOKS_HOME,
    BOOKS_TRAVEL,
    BOOKS_TRAVEL_PAGE2,
    read_fixture,
)
from tests.fakes import make_draft

from priceparser.models import Availability
from priceparser.sources.books_toscrape import (
    parse_books_categories,
    parse_books_detail,
    parse_books_listing,
)


def test_listing_homepage_two_products_and_next() -> None:
    html = read_fixture("books_home.html")
    result = parse_books_listing(BOOKS_HOME, html, source_id="books", currency="GBP")
    assert len(result.products) == 2
    first = result.products[0]
    assert first.name == "A Light in the Attic"
    assert first.price == Decimal("51.77")
    assert first.currency == "GBP"
    assert first.rating == 3.0
    second = result.products[1]
    assert second.rating == 1.0
    assert first.availability == Availability.IN_STOCK
    assert first.sku is None
    assert first.category is None
    assert first.old_price is None
    assert first.url == BOOKS_ATTIC
    assert first.image_url == "https://books.toscrape.com/media/cache/attic.jpg"
    assert result.next_url == "https://books.toscrape.com/catalogue/page-2.html"


def test_listing_category_relative_links(caplog: pytest.LogCaptureFixture) -> None:
    html = read_fixture("books_travel.html")
    result = parse_books_listing(BOOKS_TRAVEL, html, source_id="books", currency="GBP")
    assert len(result.products) == 2
    first = result.products[0]
    assert first.url == (
        "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html"
    )
    assert first.image_url == "https://books.toscrape.com/media/cache/himalayas.jpg"
    second = result.products[1]
    assert second.availability == Availability.OUT_OF_STOCK
    assert second.price == Decimal("10.00")
    assert second.rating == 5.0
    assert result.next_url == (
        "https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html"
    )
    joined = " ".join(r.message for r in caplog.records).casefold()
    assert "нет цены" in joined


def test_listing_last_page_has_no_next() -> None:
    html = read_fixture("books_travel_page2.html")
    result = parse_books_listing(BOOKS_TRAVEL_PAGE2, html, source_id="books", currency="GBP")
    assert len(result.products) == 1
    assert result.products[0].price == Decimal("20.00")
    assert result.next_url is None


def test_categories_from_sidebar() -> None:
    html = read_fixture("books_home.html")
    categories = parse_books_categories(BOOKS_HOME, html)
    assert categories == [
        (
            "Travel",
            "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        ),
        (
            "Mystery",
            "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
        ),
    ]


def test_detail_fills_sku_category_and_image() -> None:
    draft = make_draft(
        name="A Light in the ...",
        url=BOOKS_ATTIC,
        price=Decimal("51.77"),
        currency="GBP",
        rating=3.0,
    )
    html = read_fixture("books_detail_attic.html")
    detail = parse_books_detail(BOOKS_ATTIC, html, draft)
    assert detail.name == "A Light in the Attic"
    assert detail.sku == "a897fe39b1053632"
    assert detail.category == "Poetry"
    assert detail.availability == Availability.IN_STOCK
    assert detail.rating == 3.0
    assert detail.image_url == (
        "https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg"
    )
    assert detail.price == Decimal("51.77")


def test_detail_out_of_stock_inline() -> None:
    from unittest.mock import patch

    from bs4 import BeautifulSoup

    from priceparser.errors import ParseError
    from priceparser.html_utils import abs_url, attr_of, make_soup, text_of

    draft = make_draft(currency="GBP")
    html = """
    <table class="table table-striped">
      <tr><th>Availability</th><td>Out of stock</td></tr>
    </table>
    """
    detail = parse_books_detail("https://books.toscrape.com/x", html, draft)
    assert detail.availability == Availability.OUT_OF_STOCK
    assert text_of(None) == ""
    assert attr_of(None, "href") is None
    assert abs_url("https://books.toscrape.com/", "") is None
    node = BeautifulSoup('<a class="x y" href="/z"></a>', "lxml").a
    assert attr_of(node, "class") == "x"
    with (
        patch("priceparser.html_utils.BeautifulSoup", side_effect=ValueError("bad")),
        pytest.raises(ParseError),
    ):
        make_soup("<html></html>")


def test_unknown_star_class_sets_rating_none(caplog: pytest.LogCaptureFixture) -> None:
    html = """
    <article class="product_pod">
      <p class="star-rating Ten"></p>
      <h3><a href="catalogue/x/index.html" title="Book">Book</a></h3>
      <div class="product_price"><p class="price_color">£10.00</p></div>
    </article>
    """
    result = parse_books_listing(BOOKS_HOME, html, source_id="books", currency="GBP")
    assert len(result.products) == 1
    assert result.products[0].rating is None
    joined = " ".join(r.message for r in caplog.records).casefold()
    assert "оценк" in joined or "рейтинг" in joined or "unknown" in joined or "ten" in joined
