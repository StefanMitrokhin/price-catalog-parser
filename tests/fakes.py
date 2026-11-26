from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from priceparser.errors import FetchError
from priceparser.models import Availability, Product, ProductDraft

_FIXED = datetime(2026, 11, 25, 22, 15, tzinfo=UTC)


def make_product(**overrides: Any) -> Product:
    defaults: dict[str, Any] = {
        "source_id": "books",
        "name": "Item",
        "url": "https://example.com/p",
        "price": Decimal("10.00"),
        "currency": "USD",
        "availability": Availability.IN_STOCK,
        "scraped_at": _FIXED,
    }
    defaults.update(overrides)
    return Product.model_validate(defaults)


def make_draft(**overrides: Any) -> ProductDraft:
    defaults: dict[str, Any] = {
        "source_id": "books",
        "name": "Item",
        "url": "https://example.com/p",
        "price": Decimal("10.00"),
        "currency": "USD",
        "availability": Availability.UNKNOWN,
    }
    defaults.update(overrides)
    return ProductDraft(**defaults)


class FakeClient:
    def __init__(
        self,
        pages: Mapping[str, str] | None = None,
        errors: Mapping[str, Exception] | None = None,
    ) -> None:
        self.pages = dict(pages or {})
        self.errors = dict(errors or {})
        self.calls: list[str] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get_text(self, url: str, *, check_robots: bool = True) -> str:
        del check_robots
        self.calls.append(url)
        if url in self.errors:
            exc = self.errors[url]
            raise exc
        if url in self.pages:
            return self.pages[url]
        raise FetchError(url, "HTTP 404", status=404)
