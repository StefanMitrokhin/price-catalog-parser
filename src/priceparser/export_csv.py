# ruff: noqa: RUF001, RUF002
from __future__ import annotations

import csv
from pathlib import Path

from priceparser.errors import ExportError
from priceparser.models import AVAILABILITY_RU, Product

PRODUCT_HEADERS: tuple[str, ...] = (
    "Название",
    "Цена",
    "Старая цена",
    "Валюта",
    "Наличие",
    "Категория",
    "Рейтинг",
    "Артикул",
    "URL",
    "Картинка",
    "Источник",
    "Снято",
)


def sort_products(products: list[Product]) -> list[Product]:
    """Категория None в конце. Дальше category.casefold(), name.casefold(), url."""

    def key(product: Product) -> tuple[int, str, str, str]:
        if product.category is None:
            cat_rank = 1
            cat_key = ""
        else:
            cat_rank = 0
            cat_key = product.category.casefold()
        return (cat_rank, cat_key, product.name.casefold(), product.url)

    return sorted(products, key=key)


def export_products_csv(
    products: list[Product],
    path: Path,
    *,
    delimiter: str = ",",
) -> None:
    """Записать CSV в utf-8-sig с разделителем delimiter."""
    if len(delimiter) != 1:
        raise ExportError("delimiter должен быть ровно один символ")

    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sort_products(products)
    try:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(
                handle,
                delimiter=delimiter,
                quoting=csv.QUOTE_MINIMAL,
                lineterminator="\r\n",
            )
            writer.writerow(PRODUCT_HEADERS)
            for product in ordered:
                old_price = f"{product.old_price:.2f}" if product.old_price is not None else ""
                rating = f"{product.rating:.1f}" if product.rating is not None else ""
                writer.writerow(
                    [
                        product.name,
                        f"{product.price:.2f}",
                        old_price,
                        product.currency,
                        AVAILABILITY_RU[product.availability],
                        product.category or "",
                        rating,
                        product.sku or "",
                        product.url,
                        product.image_url or "",
                        product.source_id,
                        product.scraped_at.isoformat(timespec="seconds"),
                    ]
                )
    except OSError as exc:
        raise ExportError(f"Не удалось записать CSV: {path}: {exc}") from exc
