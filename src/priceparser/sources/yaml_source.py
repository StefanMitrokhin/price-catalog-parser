# ruff: noqa: RUF001
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from priceparser import clock
from priceparser.config import FieldSpec, YamlFields, YamlSourceConfig
from priceparser.crawl import walk_listings
from priceparser.dedup import dedupe_drafts
from priceparser.errors import ParseError
from priceparser.html_utils import abs_url, attr_of, make_soup, text_of
from priceparser.http_client import PageFetcher
from priceparser.models import (
    Availability,
    CollectResult,
    ListingParseResult,
    Product,
    ProductDraft,
)
from priceparser.prices import parse_availability, parse_price, parse_rating
from priceparser.sources.base import Source
from priceparser.urls import is_http_url

logger = logging.getLogger(__name__)


class YamlSource(Source):
    """Адаптер каталога по YAML-спецификации селекторов."""

    def __init__(
        self,
        *,
        source_id: str,
        spec: YamlSourceConfig,
        max_pages: int | None,
    ) -> None:
        self.source_id = source_id
        self._spec = spec
        self._max_pages = max_pages
        self._regexes: dict[str, re.Pattern[str] | None] = {}
        fields = spec.fields
        for name in YamlFields.model_fields:
            field_spec: FieldSpec | None = getattr(fields, name)
            if field_spec is None:
                self._regexes[name] = None
            elif field_spec.regex:
                self._regexes[name] = re.compile(field_spec.regex)
            else:
                self._regexes[name] = None
        self._in_phrases: tuple[str, ...] = ()
        self._out_phrases: tuple[str, ...] = ()
        if spec.availability_map is not None:
            self._in_phrases = tuple(spec.availability_map.in_stock)
            self._out_phrases = tuple(spec.availability_map.out_of_stock)

    def _extract(
        self,
        node: Any,
        spec: FieldSpec,
        pattern: re.Pattern[str] | None,
    ) -> str | None:
        found = node.select_one(spec.selector)
        if found is None:
            return None
        raw = attr_of(found, spec.attr) if spec.attr is not None else text_of(found)
        if raw is None:
            return None
        text = raw
        if pattern is not None:
            match = pattern.search(text)
            if match is None:
                return None
            text = match.group(1) if match.lastindex else match.group(0)
        text = text.strip()
        if not text:
            return None
        return text

    def parse_listing(self, page_url: str, html: str) -> ListingParseResult:
        """Разобрать одну страницу по spec. Без сети."""
        soup = make_soup(html)
        fields = self._spec.fields
        currency = self._spec.currency
        drafts: list[ProductDraft] = []

        for item in soup.select(self._spec.item):
            name = self._extract(item, fields.name, self._regexes.get("name"))
            if name is None:
                logger.warning("Пропущен товар на %s: нет name", page_url)
                continue

            url_raw = self._extract(item, fields.url, self._regexes.get("url"))
            if url_raw is None:
                logger.warning("Пропущен товар на %s: нет url", page_url)
                continue
            url = abs_url(page_url, url_raw) if fields.url.absolute else url_raw
            if url is None or not is_http_url(url):
                logger.warning("Пропущен товар на %s: нет url", page_url)
                continue

            price_raw = self._extract(item, fields.price, self._regexes.get("price"))
            if price_raw is None:
                logger.warning("Пропущен товар на %s: нет price", page_url)
                continue
            try:
                price = parse_price(price_raw)
            except ParseError:
                logger.warning("Пропущен товар на %s: нет price", page_url)
                continue

            old_price = None
            if fields.old_price is not None:
                old_raw = self._extract(item, fields.old_price, self._regexes.get("old_price"))
                if old_raw is not None:
                    try:
                        old_price = parse_price(old_raw)
                    except ParseError:
                        logger.warning(
                            "Не удалось разобрать старую цену на %s, поле опущено",
                            page_url,
                        )
                        old_price = None

            if fields.availability is None:
                availability = Availability.UNKNOWN
            else:
                avail_raw = self._extract(
                    item, fields.availability, self._regexes.get("availability")
                )
                if avail_raw is None:
                    availability = parse_availability(None)
                elif self._spec.availability_map is not None:
                    availability = parse_availability(
                        avail_raw,
                        in_phrases=self._in_phrases,
                        out_phrases=self._out_phrases,
                    )
                else:
                    availability = parse_availability(avail_raw)

            category = self._spec.category
            if fields.category is not None:
                cat_raw = self._extract(item, fields.category, self._regexes.get("category"))
                if cat_raw:
                    category = cat_raw

            rating = None
            if fields.rating is not None:
                rating_raw = self._extract(item, fields.rating, self._regexes.get("rating"))
                if rating_raw is None and fields.rating.count_selector:
                    count = len(item.select(fields.rating.count_selector))
                    if count > 0:
                        rating_raw = str(count)
                if rating_raw is not None:
                    rating = parse_rating(rating_raw)

            image_url = None
            if fields.image_url is not None:
                img_raw = self._extract(item, fields.image_url, self._regexes.get("image_url"))
                if img_raw is not None:
                    image_url = abs_url(page_url, img_raw) if fields.image_url.absolute else img_raw

            sku = None
            if fields.sku is not None:
                sku = self._extract(item, fields.sku, self._regexes.get("sku"))

            drafts.append(
                ProductDraft(
                    source_id=self.source_id,
                    name=name,
                    url=url,
                    price=price,
                    currency=currency,
                    old_price=old_price,
                    availability=availability,
                    category=category,
                    rating=rating,
                    image_url=image_url,
                    sku=sku,
                )
            )

        next_url: str | None = None
        pag = self._spec.pagination
        next_node = soup.select_one(pag.next_selector)
        if next_node is not None:
            href = attr_of(next_node, pag.attr)
            if href and href.strip():
                next_url = abs_url(page_url, href) if pag.absolute else href.strip()

        return ListingParseResult(products=drafts, next_url=next_url)

    async def collect(self, client: PageFetcher) -> CollectResult:
        """Собрать товары по YAML-spec через walk_listings."""
        started = clock.utc_now()
        drafts, pages_fetched, page_errors = await walk_listings(
            client,
            self._spec.start_urls,
            self.parse_listing,
            self._max_pages,
        )
        unique, dropped = dedupe_drafts(drafts)

        products: list[Product] = []
        for draft in unique:
            try:
                products.append(draft.to_product(started))
            except ValidationError as exc:
                logger.warning("Товар не прошёл валидацию %s: %s", draft.url, exc)
                continue

        return CollectResult(
            products=products,
            pages_fetched=pages_fetched,
            detail_pages_fetched=0,
            page_errors=page_errors,
            duplicates_dropped=dropped,
        )
