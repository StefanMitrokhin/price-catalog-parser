# ruff: noqa: RUF001
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

_MONEY = Decimal("0.01")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class ChangeKind(StrEnum):
    NEW = "new"
    REMOVED = "removed"
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    UNCHANGED = "unchanged"


AVAILABILITY_RU: dict[Availability, str] = {
    Availability.IN_STOCK: "В наличии",
    Availability.OUT_OF_STOCK: "Нет в наличии",
    Availability.UNKNOWN: "Неизвестно",
}

CHANGE_KIND_RU: dict[ChangeKind, str] = {
    ChangeKind.NEW: "Новый",
    ChangeKind.REMOVED: "Пропавший",
    ChangeKind.PRICE_UP: "Цена выросла",
    ChangeKind.PRICE_DOWN: "Цена упала",
    ChangeKind.UNCHANGED: "Без изменений",
}

CHANGE_KIND_FONT: dict[ChangeKind, str] = {
    ChangeKind.NEW: "196F3D",
    ChangeKind.REMOVED: "922B21",
    ChangeKind.PRICE_UP: "C0392B",
    ChangeKind.PRICE_DOWN: "1A7F37",
    ChangeKind.UNCHANGED: "666666",
}


def _money_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value.quantize(_MONEY):.2f}"


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _coerce_money(value: Any) -> Decimal | None:
    if value is None:
        return None
    dec = value if isinstance(value, Decimal) else Decimal(str(value))
    if dec < 0:
        raise ValueError("цена не может быть отрицательной")
    return _quantize_money(dec)


def _is_http_url(url: str) -> bool:
    parts = urlsplit(url.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


class Product(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: str
    price: Decimal = Field(ge=0)
    currency: str
    old_price: Decimal | None = Field(default=None, ge=0)
    availability: Availability = Availability.UNKNOWN
    category: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    image_url: str | None = None
    sku: str | None = None
    scraped_at: datetime

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("source_id", mode="before")
    @classmethod
    def _strip_source_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if not _CURRENCY_RE.match(value):
            raise ValueError("валюта должна быть трёхбуквенным кодом ISO в верхнем регистре")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        if not _is_http_url(value):
            raise ValueError("url должен быть абсолютным http или https")
        return value

    @field_validator("image_url")
    @classmethod
    def _validate_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not _is_http_url(text):
            raise ValueError("image_url должен быть абсолютным http или https")
        return text

    @field_validator("category", mode="before")
    @classmethod
    def _empty_category(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("sku", mode="before")
    @classmethod
    def _normalize_sku(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text if text else None
        return value

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, value: Any) -> Decimal:
        result = _coerce_money(value)
        if result is None:
            raise ValueError("цена обязательна")
        return result

    @field_validator("old_price", mode="before")
    @classmethod
    def _coerce_old_price(cls, value: Any) -> Decimal | None:
        return _coerce_money(value)

    @field_validator("scraped_at")
    @classmethod
    def _aware_scraped_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scraped_at должен быть timezone-aware")
        return value

    @field_serializer("price", "old_price")
    def _serialize_money(self, value: Decimal | None) -> str | None:
        return _money_to_json(value)


@dataclass
class ProductDraft:
    source_id: str
    name: str
    url: str
    price: Decimal
    currency: str
    old_price: Decimal | None = None
    availability: Availability = Availability.UNKNOWN
    category: str | None = None
    rating: float | None = None
    image_url: str | None = None
    sku: str | None = None

    def to_product(self, scraped_at: datetime) -> Product:
        """Собрать Product. Валидация pydantic здесь и есть проверка черновика."""
        return Product(
            source_id=self.source_id,
            name=self.name,
            url=self.url,
            price=self.price,
            currency=self.currency,
            old_price=self.old_price,
            availability=self.availability,
            category=self.category,
            rating=self.rating,
            image_url=self.image_url,
            sku=self.sku,
            scraped_at=scraped_at,
        )


@dataclass(frozen=True)
class ListingParseResult:
    products: list[ProductDraft]
    next_url: str | None


@dataclass(frozen=True)
class CollectResult:
    products: list[Product]
    pages_fetched: int
    detail_pages_fetched: int
    page_errors: int
    duplicates_dropped: int


class RunMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    source_id: str
    started_at: datetime
    finished_at: datetime
    product_count: int
    pages_fetched: int
    detail_pages_fetched: int
    page_errors: int
    config_path: str


class RunSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: RunMeta
    products: list[Product]


class PriceChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ChangeKind
    identity_key: str
    name: str
    url: str
    sku: str | None
    category: str | None
    old_price: Decimal | None
    new_price: Decimal | None
    delta: Decimal | None
    delta_pct: Decimal | None
    currency: str | None
    currency_mismatch: bool
    source_id: str

    @field_serializer("old_price", "new_price", "delta", "delta_pct")
    def _serialize_money_fields(self, value: Decimal | None) -> str | None:
        return _money_to_json(value)


@dataclass(frozen=True)
class DiffReport:
    changes: list[PriceChange]
    new_count: int
    removed_count: int
    up_count: int
    down_count: int
    unchanged_count: int