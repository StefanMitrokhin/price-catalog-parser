from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

BOOKS_HOME = "https://books.toscrape.com/"
BOOKS_TRAVEL = "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"
BOOKS_TRAVEL_PAGE2 = "https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html"
BOOKS_MYSTERY = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"
BOOKS_ATTIC = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
BOOKS_HIMALAYAS = "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html"
BOOKS_SECOND = "https://books.toscrape.com/catalogue/second-travel-book_100/index.html"
LAPTOPS_PAGE1 = "https://webscraper.io/test-sites/e-commerce/static/computers/laptops"
LAPTOPS_PAGE2 = "https://webscraper.io/test-sites/e-commerce/static/computers/laptops?page=2"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 11, 25, 22, 15, tzinfo=UTC)
