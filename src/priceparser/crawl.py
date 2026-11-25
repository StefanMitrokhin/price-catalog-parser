# ruff: noqa: RUF001
from __future__ import annotations

import logging
from collections.abc import Callable

from priceparser.errors import FetchError, ParseError, RobotsDenied
from priceparser.http_client import PageFetcher
from priceparser.models import ListingParseResult, ProductDraft
from priceparser.urls import normalize_url

logger = logging.getLogger(__name__)


async def walk_listings(
    client: PageFetcher,
    start_urls: list[str],
    parse: Callable[[str, str], ListingParseResult],
    max_pages: int | None,
) -> tuple[list[ProductDraft], int, int]:
    """Вернуть (черновики, pages_fetched, page_errors)."""
    all_drafts: list[ProductDraft] = []
    pages_fetched = 0
    page_errors = 0
    seen: set[str] = set()
    warned_max_pages = False

    for start_url in start_urls:
        if max_pages is not None and pages_fetched >= max_pages:
            break
        url: str | None = start_url
        while url is not None:
            if max_pages is not None and pages_fetched >= max_pages:
                if not warned_max_pages:
                    logger.warning(
                        "Достигнут max_pages=%s, остальные страницы пропущены",
                        max_pages,
                    )
                    warned_max_pages = True
                return all_drafts, pages_fetched, page_errors

            norm = normalize_url(url)
            if norm in seen:
                break
            seen.add(norm)

            try:
                html = await client.get_text(url)
            except RobotsDenied:
                logger.warning("Пропуск %s: запрещено robots.txt", url)
                page_errors += 1
                break
            except FetchError as exc:
                logger.error("Не удалось загрузить %s: %s", url, exc.message)
                page_errors += 1
                break

            pages_fetched += 1
            try:
                result = parse(url, html)
            except ParseError as exc:
                logger.error("Ошибка разбора %s: %s", url, exc)
                page_errors += 1
                break
            except Exception as exc:
                logger.error("Ошибка разбора %s: %s", url, exc)
                page_errors += 1
                break

            if not result.products:
                logger.warning("На %s не найдено товаров", url)

            all_drafts.extend(result.products)
            url = result.next_url

    return all_drafts, pages_fetched, page_errors
