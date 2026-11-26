# ruff: noqa: RUF002
from __future__ import annotations

from typing import Any, cast
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from priceparser.errors import ParseError


def make_soup(html: str) -> Any:
    """BeautifulSoup(html, "lxml"). Ошибка парсера -> ParseError."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception as exc:
        raise ParseError(f"не удалось разобрать HTML: {exc}") from exc


def text_of(node: Any) -> str:
    """get_text(' ', strip=True) либо пустая строка, если node is None."""
    if node is None:
        return ""
    return cast(str, node.get_text(" ", strip=True))


def attr_of(node: Any, name: str) -> str | None:
    """Атрибут строкой. Список (так бывает у class) -> первый элемент. Нет атрибута -> None."""
    if node is None:
        return None
    value = node.get(name)
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def abs_url(page_url: str, href: str | None) -> str | None:
    """urljoin. Пустой href -> None. Уже абсолютная ссылка остаётся абсолютной."""
    if href is None:
        return None
    text = href.strip()
    if not text:
        return None
    return urljoin(page_url, text)
