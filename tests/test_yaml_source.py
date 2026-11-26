from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from tests.conftest import LAPTOPS_PAGE1, LAPTOPS_PAGE2, read_fixture
from tests.fakes import FakeClient

from priceparser.config import YamlSourceConfig
from priceparser.sources.yaml_source import YamlSource

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _laptops_source(max_pages: int = 2) -> YamlSource:
    spec = YamlSourceConfig.model_validate(
        yaml.safe_load((_REPO_ROOT / "sources/webscraper_laptops.yaml").read_text())
    )
    return YamlSource(source_id="laptops", spec=spec, max_pages=max_pages)


@pytest.mark.asyncio
async def test_parse_laptops_page_with_old_price_and_rating() -> None:
    html = read_fixture("webscraper_laptops_page1.html")
    result = _laptops_source().parse_listing(LAPTOPS_PAGE1, html)
    assert len(result.products) == 2
    first = result.products[0]
    assert first.name == "Packard 255 G2"
    assert first.price == Decimal("416.99")
    assert first.old_price == Decimal("499.99")
    assert first.currency == "USD"
    assert first.rating == 2.0
    assert first.category == "Laptops"
    assert first.sku is None
    assert first.availability.value == "unknown"
    assert first.url == "https://webscraper.io/test-sites/e-commerce/static/product/31"
    assert first.image_url == "https://webscraper.io/images/test-sites/e-commerce/items/cart2.png"
    second = result.products[1]
    assert second.price == Decimal("306.99")
    assert second.old_price is None
    assert second.rating == 3.0
    assert result.next_url == LAPTOPS_PAGE2
    collected = await _laptops_source(max_pages=1).collect(FakeClient(pages={LAPTOPS_PAGE1: html}))
    assert len(collected.products) == 2


def test_page_without_next_counts_stars() -> None:
    html = read_fixture("webscraper_laptops_page2.html")
    result = _laptops_source().parse_listing(LAPTOPS_PAGE2, html)
    assert len(result.products) == 1
    assert result.products[0].rating == 4.0
    assert result.products[0].category == "Laptops"
    assert result.next_url is None


def test_zero_stars_without_attribute_is_none() -> None:
    html = """
    <div class="card thumbnail">
      <div class="product-wrapper card-body">
        <h4 class="price"><span itemprop="price">$10.00</span></h4>
        <h4><a class="title" href="/p/1" title="Laptop">Laptop</a></h4>
        <div class="ratings"><p></p></div>
      </div>
    </div>
    """
    result = _laptops_source().parse_listing(LAPTOPS_PAGE1, html)
    assert result.products[0].rating is None


def test_selector_category_overrides_static() -> None:
    html = """
    <div class="card thumbnail">
      <div class="product-wrapper card-body">
        <span class="category">Gaming</span>
        <h4 class="price"><span itemprop="price">$10.00</span></h4>
        <h4><a class="title" href="/p/2" title="Gaming Laptop">Gaming Laptop</a></h4>
      </div>
    </div>
    """
    result = _laptops_source().parse_listing(LAPTOPS_PAGE1, html)
    assert result.products[0].category == "Gaming"

    sku_html = """
    <div class="card thumbnail">
      <div class="product-wrapper card-body">
        <span class="availability">in stock</span>
        <span itemprop="sku">SKU-1</span>
        <h4 class="price"><span itemprop="price">$11.00</span></h4>
        <h4><a class="title" href="/p/3" title="With Sku">With Sku</a></h4>
      </div>
    </div>
    """
    sku_result = _laptops_source().parse_listing(LAPTOPS_PAGE1, sku_html)
    assert sku_result.products[0].sku == "SKU-1"
    assert sku_result.products[0].availability.value == "in_stock"
