# ruff: noqa: RUF001
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal

from priceparser.models import ChangeKind, DiffReport, PriceChange, Product
from priceparser.urls import product_key

logger = logging.getLogger(__name__)

_MONEY = Decimal("0.01")

_KIND_RANK: dict[ChangeKind, int] = {
    ChangeKind.NEW: 0,
    ChangeKind.REMOVED: 1,
    ChangeKind.PRICE_UP: 2,
    ChangeKind.PRICE_DOWN: 3,
    ChangeKind.UNCHANGED: 4,
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _build_map(products: list[Product], label: str) -> dict[str, Product]:
    result: dict[str, Product] = {}
    for product in products:
        key = product_key(product)
        if key in result:
            logger.warning("Повтор ключа в %s снимке: %s", label, key)
            continue
        result[key] = product
    return result


def diff_products(previous: list[Product], current: list[Product]) -> DiffReport:
    """Сравнить уже дедуплицированные списки одного источника."""
    prev_map = _build_map(previous, "предыдущем")
    curr_map = _build_map(current, "текущем")
    changes: list[PriceChange] = []

    for product in current:
        key = product_key(product)
        prev = prev_map.get(key)
        if prev is None:
            changes.append(
                PriceChange(
                    kind=ChangeKind.NEW,
                    identity_key=key,
                    name=product.name,
                    url=product.url,
                    sku=product.sku,
                    category=product.category,
                    old_price=None,
                    new_price=product.price,
                    delta=None,
                    delta_pct=None,
                    currency=product.currency,
                    currency_mismatch=False,
                    source_id=product.source_id,
                )
            )
            continue

        mismatch = False
        if prev.currency != product.currency:
            mismatch = True
            logger.warning(
                "Разные валюты у %s: %s и %s",
                key,
                prev.currency,
                product.currency,
            )

        if product.price > prev.price:
            kind = ChangeKind.PRICE_UP
        elif product.price < prev.price:
            kind = ChangeKind.PRICE_DOWN
        else:
            kind = ChangeKind.UNCHANGED

        delta = _money(product.price - prev.price)
        if prev.price == 0:
            delta_pct: Decimal | None = None
        else:
            delta_pct = _money(delta / prev.price * Decimal(100))

        changes.append(
            PriceChange(
                kind=kind,
                identity_key=key,
                name=product.name,
                url=product.url,
                sku=product.sku,
                category=product.category,
                old_price=prev.price,
                new_price=product.price,
                delta=delta,
                delta_pct=delta_pct,
                currency=product.currency,
                currency_mismatch=mismatch,
                source_id=product.source_id,
            )
        )

    for product in previous:
        key = product_key(product)
        if key not in curr_map:
            changes.append(
                PriceChange(
                    kind=ChangeKind.REMOVED,
                    identity_key=key,
                    name=product.name,
                    url=product.url,
                    sku=product.sku,
                    category=product.category,
                    old_price=product.price,
                    new_price=None,
                    delta=None,
                    delta_pct=None,
                    currency=product.currency,
                    currency_mismatch=False,
                    source_id=product.source_id,
                )
            )

    changes.sort(
        key=lambda c: (_KIND_RANK[c.kind], c.name.casefold(), c.url),
    )

    new_count = sum(1 for c in changes if c.kind == ChangeKind.NEW)
    removed_count = sum(1 for c in changes if c.kind == ChangeKind.REMOVED)
    up_count = sum(1 for c in changes if c.kind == ChangeKind.PRICE_UP)
    down_count = sum(1 for c in changes if c.kind == ChangeKind.PRICE_DOWN)
    unchanged_count = sum(1 for c in changes if c.kind == ChangeKind.UNCHANGED)

    return DiffReport(
        changes=changes,
        new_count=new_count,
        removed_count=removed_count,
        up_count=up_count,
        down_count=down_count,
        unchanged_count=unchanged_count,
    )
