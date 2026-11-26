from __future__ import annotations

import re
from decimal import Decimal

import pytest
from tests.conftest import (
    BOOKS_HIMALAYAS,
    BOOKS_HOME,
    BOOKS_MYSTERY,
    BOOKS_SECOND,
    BOOKS_TRAVEL,
    LAPTOPS_PAGE1,
    LAPTOPS_PAGE2,
    read_fixture,
)
from tests.fakes import FakeClient

from priceparser.config import (
    FieldSpec,
    PaginationSpec,
    YamlFields,
    YamlSourceConfig,
)
from priceparser.crawl import walk_listings
from priceparser.errors import FetchError, ParseError, RobotsDenied
from priceparser.sources.books_toscrape import BooksToScrapeSource
from priceparser.sources.yaml_source import YamlSource

_SECOND_DETAIL = """
<html><body>
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="#">Travel</a></li>
</ul>
<div class="product_main"><h1>Second Travel Book</h1>
<p class="price_color">£10.00</p></div>
<table class="table table-striped">
  <tr><th>UPC</th><td>dddddddddddd0002</td></tr>
  <tr><th>Availability</th><td>Out of stock</td></tr>
</table>
</body></html>
"""


def _books_client(**extra: str) -> FakeClient:
    pages = {
        BOOKS_HOME: read_fixture("books_home.html"),
        BOOKS_TRAVEL: read_fixture("books_travel.html"),
        BOOKS_HIMALAYAS: read_fixture("books_detail_himalayas.html"),
        BOOKS_SECOND: _SECOND_DETAIL,
    }
    pages.update(extra)
    return FakeClient(pages=pages)


@pytest.mark.asyncio
async def test_books_collect_travel_only_with_details(
    monkeypatch: pytest.MonkeyPatch,
    fixed_now,
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    source = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Travel",),
        max_pages=1,
        fetch_details=True,
    )
    client = _books_client()
    result = await source.collect(client)
    assert BOOKS_HOME in client.calls
    assert BOOKS_TRAVEL in client.calls
    assert BOOKS_MYSTERY not in client.calls
    assert all("page-2" not in u for u in client.calls)
    assert len(result.products) == 2
    him = next(p for p in result.products if "Himalayas" in p.name)
    assert him.sku == "c0ffee0000000001"
    assert him.category == "Travel"
    assert him.price == Decimal("45.17")
    assert result.pages_fetched == 1
    assert result.detail_pages_fetched == 2
    assert result.page_errors == 0
    assert all(p.scraped_at == fixed_now for p in result.products)

    plain = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=(),
        max_pages=1,
        fetch_details=False,
    )
    home_result = await plain.collect(_books_client())
    assert len(home_result.products) == 2

    err_client = _books_client()
    err_client.errors[BOOKS_HIMALAYAS] = FetchError(BOOKS_HIMALAYAS, "down", status=503)
    err_result = await source.collect(err_client)
    assert err_result.page_errors == 1

    bad_detail = _books_client()
    bad_detail.pages[BOOKS_HIMALAYAS] = "<html><body>no table</body></html>"
    bad_result = await source.collect(bad_detail)
    assert bad_result.page_errors == 0
    assert bad_result.products[0].sku is None

    rob_client = _books_client()
    rob_client.errors[BOOKS_HIMALAYAS] = RobotsDenied(BOOKS_HIMALAYAS)
    rob_result = await source.collect(rob_client)
    assert rob_result.page_errors == 1

    def broken_detail(_url: str, _html: str, _draft):
        raise ParseError("broken detail")

    import priceparser.sources.books_toscrape as books_mod

    monkeypatch.setattr(books_mod, "parse_books_detail", broken_detail)
    parse_fail_client = _books_client()
    parse_fail_result = await source.collect(parse_fail_client)
    assert parse_fail_result.page_errors == 2
    assert parse_fail_result.detail_pages_fetched == 0


@pytest.mark.asyncio
async def test_max_pages_limit_applies_across_category_chains() -> None:
    source = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Travel", "Mystery"),
        max_pages=1,
        fetch_details=False,
    )
    client = _books_client()
    result = await source.collect(client)
    assert BOOKS_TRAVEL in client.calls
    assert BOOKS_MYSTERY not in client.calls
    assert len(result.products) == 2
    assert result.pages_fetched == 1


@pytest.mark.asyncio
async def test_max_pages_two_follows_second_page() -> None:
    pages = {
        BOOKS_HOME: read_fixture("books_home.html"),
        BOOKS_TRAVEL: read_fixture("books_travel.html"),
        "https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html": read_fixture(
            "books_travel_page2.html"
        ),
    }
    source = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Travel",),
        max_pages=2,
        fetch_details=False,
    )
    client = FakeClient(pages=pages)
    result = await source.collect(client)
    assert any("page-2" in u for u in client.calls)
    assert len(result.products) == 3
    assert result.pages_fetched == 2


@pytest.mark.asyncio
async def test_failed_category_does_not_drop_previous() -> None:
    source = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Travel", "Mystery"),
        max_pages=2,
        fetch_details=False,
    )
    travel_single_page = re.sub(
        r'<li class="next">.*?</li>',
        "",
        read_fixture("books_travel.html"),
        count=1,
        flags=re.DOTALL,
    )
    client = _books_client()
    client.pages[BOOKS_TRAVEL] = travel_single_page
    client.errors[BOOKS_MYSTERY] = FetchError(BOOKS_MYSTERY, "HTTP 404", status=404)
    result = await source.collect(client)
    assert result.page_errors == 1
    assert len(result.products) == 2
    assert any("Himalayas" in p.name for p in result.products)


@pytest.mark.asyncio
async def test_missing_category_raises() -> None:
    source = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Cookbook",),
        max_pages=1,
        fetch_details=False,
    )
    with pytest.raises(ParseError) as exc:
        await source.collect(FakeClient(pages={BOOKS_HOME: read_fixture("books_home.html")}))
    msg = str(exc.value)
    assert "Cookbook" in msg
    assert "Travel" in msg

    down = BooksToScrapeSource(
        source_id="books",
        start_url=BOOKS_HOME,
        currency="GBP",
        categories=("Travel",),
        max_pages=1,
        fetch_details=False,
    )
    fail_home = await down.collect(
        FakeClient(errors={BOOKS_HOME: FetchError(BOOKS_HOME, "down", status=503)})
    )
    assert fail_home.products == []
    assert fail_home.page_errors == 1

    def parse_fail(_url: str, _html: str):
        raise ParseError("bad page")

    _, _, p_err = await walk_listings(
        FakeClient(pages={BOOKS_TRAVEL: read_fixture("books_travel.html")}),
        [BOOKS_TRAVEL],
        parse_fail,
        1,
    )
    assert p_err == 1


@pytest.mark.asyncio
async def test_yaml_stops_at_max_pages() -> None:
    from pathlib import Path

    import yaml

    from priceparser.config import YamlSourceConfig

    root = Path(__file__).resolve().parents[1]
    spec = YamlSourceConfig.model_validate(
        yaml.safe_load((root / "sources/webscraper_laptops.yaml").read_text())
    )
    source = YamlSource(source_id="laptops", spec=spec, max_pages=1)
    client = FakeClient(
        pages={
            LAPTOPS_PAGE1: read_fixture("webscraper_laptops_page1.html"),
            LAPTOPS_PAGE2: read_fixture("webscraper_laptops_page2.html"),
        }
    )
    result = await source.collect(client)
    assert len(result.products) == 2
    assert LAPTOPS_PAGE2 not in client.calls


@pytest.mark.asyncio
async def test_cycle_guard() -> None:
    cycle_url = "https://example.com/list"
    html = f"""
    <div class="card thumbnail">
      <h4><a class="title" href="/p" title="Item">Item</a></h4>
      <h4 class="price"><span itemprop="price">$1.00</span></h4>
    </div>
    <a class="page-link next" rel="next" href="{cycle_url}">next</a>
    """
    spec = YamlSourceConfig(
        start_urls=[cycle_url],
        currency="USD",
        category="Test",
        item="div.card.thumbnail",
        fields=YamlFields(
            name=FieldSpec(selector="a.title", attr="title"),
            url=FieldSpec(selector="a.title", attr="href", absolute=True),
            price=FieldSpec(selector="span[itemprop=price]"),
        ),
        pagination=PaginationSpec(next_selector="a[rel=next]", attr="href", absolute=True),
    )
    source = YamlSource(source_id="loop", spec=spec, max_pages=10)
    client = FakeClient(pages={cycle_url: html})
    result = await source.collect(client)
    assert result.pages_fetched == 1

    def boom_parse(_url: str, _html: str) -> ListingParseResult:
        raise ValueError("boom")

    _, _, parse_err = await walk_listings(
        FakeClient(pages={cycle_url: html}),
        [cycle_url],
        boom_parse,
        2,
    )
    assert parse_err == 1

    from priceparser.models import ListingParseResult

    def empty_parse(_url: str, _html: str) -> ListingParseResult:
        return ListingParseResult(products=[], next_url=None)

    await walk_listings(
        FakeClient(pages={cycle_url: html}),
        [cycle_url],
        empty_parse,
        1,
    )
