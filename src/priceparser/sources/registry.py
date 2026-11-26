from __future__ import annotations

from priceparser.config import ResolvedSource
from priceparser.errors import ConfigError
from priceparser.sources.base import Source
from priceparser.sources.books_toscrape import BooksToScrapeSource
from priceparser.sources.yaml_source import YamlSource


def create_source(
    source: ResolvedSource,
    *,
    max_pages: int | None,
    fetch_details: bool,
) -> Source:
    """Собрать адаптер. Неизвестный type -> ConfigError."""
    if source.type == "books_toscrape":
        if source.start_url is None or source.currency is None:
            raise ConfigError(f"Источник {source.id}: некорректные поля books_toscrape")
        return BooksToScrapeSource(
            source_id=source.id,
            start_url=source.start_url,
            currency=source.currency,
            categories=source.categories,
            max_pages=max_pages,
            fetch_details=fetch_details,
        )
    if source.type == "yaml":
        if source.yaml_spec is None:
            raise ConfigError(f"Источник {source.id}: нет yaml_spec")
        return YamlSource(
            source_id=source.id,
            spec=source.yaml_spec,
            max_pages=max_pages,
        )
    raise ConfigError(f"Неизвестный тип источника: {source.type}")
