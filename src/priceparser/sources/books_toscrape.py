# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from pydantic import ValidationError

from priceparser import clock
from priceparser.crawl import walk_listings
from priceparser.dedup import dedupe_drafts
from priceparser.errors import FetchError, ParseError, RobotsDenied
from priceparser.html_utils import abs_url, attr_of, make_soup, text_of
from priceparser.http_client import PageFetcher
from priceparser.models import CollectResult, ListingParseResult, Product, ProductDraft
from priceparser.prices import parse_availability, parse_price
from priceparser.sources.base import Source

logger = logging.getLogger(__name__)

_STAR_WORDS: dict[str, float] = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
}


def _norm_category_name(name: str) -> str:
    return " ".join(name.casefold().split())


def _rating_from_star_node(node: object, page_url: str) -> float | None:
    if node is None:
        return None
    classes = getattr(node, "get", lambda _k, default=None: default)("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    for cls in classes:
        if cls == "star-rating":
            continue
        word = cls.casefold()
        if word in _STAR_WORDS:
            return _STAR_WORDS[word]
        logger.warning("Неизвестная оценка %s на %s", cls, page_url)
        return None
    return None


def parse_books_categories(page_url: str, html: str) -> list[tuple[str, str]]:
    """Список (имя, абсолютный URL) из div.side_categories ul li ul li a."""
    soup = make_soup(html)
    result: list[tuple[str, str]] = []
    for anchor in soup.select("div.side_categories ul li ul li a"):
        name = text_of(anchor)
        if not name:
            continue
        href = attr_of(anchor, "href")
        url = abs_url(page_url, href)
        if url is None:
            continue
        result.append((name, url))
    return result


def parse_books_listing(
    page_url: str,
    html: str,
    *,
    source_id: str,
    currency: str,
) -> ListingParseResult:
    """Разобрать страницу списка books.toscrape.com."""
    soup = make_soup(html)
    drafts: list[ProductDraft] = []

    for article in soup.select("article.product_pod"):
        link = article.select_one("h3 a")
        if link is None:
            logger.warning("Пропущен товар на %s: нет ссылки", page_url)
            continue

        title_attr = attr_of(link, "title")
        name = title_attr.strip() if title_attr and title_attr.strip() else text_of(link)
        if not name:
            logger.warning("Пропущен товар на %s: нет названия", page_url)
            continue

        href = attr_of(link, "href")
        url = abs_url(page_url, href)
        if url is None:
            logger.warning("Пропущен товар на %s: нет ссылки", page_url)
            continue

        price_node = article.select_one("p.price_color")
        if price_node is None:
            logger.warning("Пропущен товар на %s: нет цены", page_url)
            continue
        try:
            price = parse_price(text_of(price_node))
        except ParseError:
            logger.warning("Пропущен товар на %s: нет цены", page_url)
            continue

        availability_text = text_of(article.select_one("p.availability"))
        availability = parse_availability(availability_text if availability_text else None)

        rating_node = article.select_one("p.star-rating")
        rating = _rating_from_star_node(rating_node, page_url)

        image_src = None
        img = article.select_one("div.image_container img")
        if img is not None:
            image_src = abs_url(page_url, attr_of(img, "src"))
            if image_src is not None:
                image_src = image_src.replace("/catalogue/media/", "/media/")

        drafts.append(
            ProductDraft(
                source_id=source_id,
                name=name,
                url=url,
                price=price,
                currency=currency,
                old_price=None,
                availability=availability,
                category=None,
                rating=rating,
                image_url=image_src,
                sku=None,
            )
        )

    next_url: str | None = None
    next_anchor = soup.select_one("li.next a")
    if next_anchor is not None:
        next_url = abs_url(page_url, attr_of(next_anchor, "href"))

    return ListingParseResult(products=drafts, next_url=next_url)


def parse_books_detail(page_url: str, html: str, draft: ProductDraft) -> ProductDraft:
    """Дополнить черновик карточкой товара."""
    soup = make_soup(html)

    name = draft.name
    h1 = soup.select_one("h1")
    if h1 is not None:
        h1_text = text_of(h1)
        if h1_text:
            name = h1_text

    price = draft.price
    price_node = soup.select_one("p.price_color")
    if price_node is not None:
        try:
            price = parse_price(text_of(price_node))
        except ParseError:
            logger.warning(
                "Не удалось разобрать цену на карточке %s, оставлена цена списка",
                page_url,
            )

    rating = draft.rating
    rating_node = soup.select_one("p.star-rating")
    if rating_node is not None:
        rating = _rating_from_star_node(rating_node, page_url)

    sku = draft.sku
    availability = draft.availability
    table = soup.select_one("table.table-striped")
    if table is not None:
        for row in table.select("tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th is None or td is None:
                continue
            key = text_of(th).casefold()
            value = text_of(td)
            if key == "upc" and value:
                sku = value
            elif key == "availability":
                availability = parse_availability(value if value else None)

    category = draft.category
    crumbs: list[str] = []
    for item in soup.select("ul.breadcrumb li"):
        text = text_of(item)
        if text:
            crumbs.append(text)
    if len(crumbs) >= 3:
        category = crumbs[-2]

    image_url = draft.image_url
    gallery_img = soup.select_one("#product_gallery img")
    if gallery_img is not None:
        resolved = abs_url(page_url, attr_of(gallery_img, "src"))
        if resolved is not None:
            image_url = resolved

    return replace(
        draft,
        name=name,
        price=price,
        rating=rating,
        sku=sku,
        availability=availability,
        category=category,
        image_url=image_url,
    )


class BooksToScrapeSource(Source):
    """Адаптер books.toscrape.com."""

    def __init__(
        self,
        *,
        source_id: str,
        start_url: str,
        currency: str,
        categories: tuple[str, ...],
        max_pages: int | None,
        fetch_details: bool,
    ) -> None:
        self.source_id = source_id
        self._start_url = start_url
        self._currency = currency
        self._categories = categories
        self._max_pages = max_pages
        self._fetch_details = fetch_details

    async def collect(self, client: PageFetcher) -> CollectResult:
        """Собрать книги: списки, опционально карточки, дедуп."""
        started = clock.utc_now()
        page_errors = 0
        detail_pages_fetched = 0
        duplicates_dropped = 0

        if self._categories:
            try:
                html = await client.get_text(self._start_url)
            except (FetchError, RobotsDenied) as exc:
                logger.error("Не удалось загрузить главную %s: %s", self._start_url, exc)
                return CollectResult(
                    products=[],
                    pages_fetched=0,
                    detail_pages_fetched=0,
                    page_errors=1,
                    duplicates_dropped=0,
                )

            found = parse_books_categories(self._start_url, html)
            by_name = {_norm_category_name(name): url for name, url in found}
            available_names = [name for name, _ in found]
            start_urls: list[str] = []
            for requested in self._categories:
                key = _norm_category_name(requested)
                if key not in by_name:
                    raise ParseError(
                        f"Категория не найдена: {requested}. Доступны: {', '.join(available_names)}"
                    )
                start_urls.append(by_name[key])
        else:
            start_urls = [self._start_url]

        def parse_listing(page_url: str, html: str) -> ListingParseResult:
            return parse_books_listing(
                page_url,
                html,
                source_id=self.source_id,
                currency=self._currency,
            )

        drafts, pages_fetched, listing_errors = await walk_listings(
            client,
            start_urls,
            parse_listing,
            self._max_pages,
        )
        page_errors += listing_errors

        unique, dropped = dedupe_drafts(drafts)
        duplicates_dropped += dropped

        if self._fetch_details:
            detail_errors = 0

            async def fetch_one(draft: ProductDraft) -> ProductDraft:
                nonlocal detail_errors, detail_pages_fetched
                try:
                    html = await client.get_text(draft.url)
                except RobotsDenied:
                    logger.warning("Пропуск карточки %s: запрещено robots.txt", draft.url)
                    detail_errors += 1
                    return draft
                except FetchError as exc:
                    logger.error("Не удалось загрузить карточку %s: %s", draft.url, exc.message)
                    detail_errors += 1
                    return draft
                try:
                    parsed = parse_books_detail(draft.url, html, draft)
                except ParseError as exc:
                    logger.warning("Ошибка разбора карточки %s: %s", draft.url, exc)
                    detail_errors += 1
                    return draft
                detail_pages_fetched += 1
                return parsed

            unique = list(await asyncio.gather(*(fetch_one(d) for d in unique)))
            page_errors += detail_errors
        else:
            detail_pages_fetched = 0

        unique, dropped2 = dedupe_drafts(unique)
        duplicates_dropped += dropped2

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
            detail_pages_fetched=detail_pages_fetched,
            page_errors=page_errors,
            duplicates_dropped=duplicates_dropped,
        )
