from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError
from tests.conftest import BOOKS_HOME
from tests.fakes import make_draft, make_product

from priceparser.urls import draft_key, normalize_url, product_key, product_key_parts


def test_normalize_drops_fragment_and_trailing_slash() -> None:
    assert normalize_url("https://Example.com/a/b/#x") == "https://example.com/a/b"


def test_normalize_sorts_query() -> None:
    assert normalize_url("https://example.com/a?b=2&a=1") == "https://example.com/a?a=1&b=2"


def test_normalize_drops_default_port() -> None:
    assert normalize_url("https://example.com:443/a") == "https://example.com/a"
    assert normalize_url("http://example.com:8080/a") == "http://example.com:8080/a"


def test_product_key_prefers_sku() -> None:
    product = make_product(sku="AbC", url="https://example.com/other")
    assert product_key(product) == "sku:books:abc"
    draft = make_draft(sku="AbC", url="https://example.com/x")
    assert draft_key(draft) == product_key_parts("books", "https://example.com/y", "AbC")


def test_product_key_uses_url_when_sku_missing() -> None:
    u1 = "https://example.com/item"
    u2 = "https://example.com/item/"
    assert product_key(make_product(url=u1, sku=None)) == product_key(
        make_product(url=u2, sku=None)
    )
    assert product_key(make_product(url=BOOKS_HOME)) == product_key_parts("books", BOOKS_HOME, None)
    with pytest.raises(ValidationError):
        make_product(price=Decimal("-1"))
    with pytest.raises(ValidationError):
        make_product(name="   ")
