from __future__ import annotations

import logging
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from priceparser.errors import ParseError
from priceparser.models import Availability

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")

DEFAULT_OUT_PHRASES: tuple[str, ...] = (
    "out of stock",
    "not in stock",
    "sold out",
    "unavailable",
    "нет в наличии",
)
DEFAULT_IN_PHRASES: tuple[str, ...] = (
    "in stock",
    "available",
    "в наличии",
)


def parse_price(raw: str) -> Decimal:
    """Вытащить цену из текста узла."""
    if re.search(r"-\s*[\d,.\s\u00A0]", raw):
        raise ParseError(f"отрицательная цена {raw!r}")
    cleaned = re.sub(r"[^\d,.\s\u00A0]", "", raw)
    cleaned = cleaned.replace("\u00a0", "").replace(" ", "")
    if not cleaned or not re.search(r"\d", cleaned):
        raise ParseError(f"нет цены в {raw!r}")

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        whole, frac = cleaned.rsplit(",", 1)
        if whole.count(",") == 0 and 1 <= len(frac) <= 2 and frac.isdigit():
            cleaned = whole.replace(",", "") + "." + frac
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        head, frac = cleaned.rsplit(".", 1)
        if 1 <= len(frac) <= 2 and frac.isdigit():
            cleaned = head.replace(".", "") + "." + frac
        else:
            cleaned = cleaned.replace(".", "")
    elif cleaned.count(".") == 1:
        whole, frac = cleaned.split(".")
        if len(frac) == 3 and frac.isdigit() and len(whole) <= 1:
            cleaned = whole + frac

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"нет цены в {raw!r}") from exc
    if value < 0:
        raise ParseError(f"отрицательная цена {raw!r}")
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def parse_availability(
    text: str | None,
    *,
    out_phrases: tuple[str, ...] = DEFAULT_OUT_PHRASES,
    in_phrases: tuple[str, ...] = DEFAULT_IN_PHRASES,
) -> Availability:
    """Сначала фразы отсутствия, потом наличия: подстрока, casefold, пробелы схлопнуты."""
    if text is None:
        return Availability.UNKNOWN
    norm = " ".join(text.casefold().split())
    if not norm:
        return Availability.UNKNOWN
    if any(phrase in norm for phrase in out_phrases):
        return Availability.OUT_OF_STOCK
    if any(phrase in norm for phrase in in_phrases):
        return Availability.IN_STOCK
    return Availability.UNKNOWN


def parse_rating(raw: str | None) -> float | None:
    """Число 0..5 включительно. Пусто -> None. Вне диапазона -> None и warning, не исключение."""
    if raw is None:
        return None
    text = raw.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        logger.warning("Непонятный рейтинг: %s", raw)
        return None
    if value < 0 or value > 5:
        logger.warning("Рейтинг вне шкалы 0..5: %s", raw)
        return None
    return value
