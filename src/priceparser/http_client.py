# ruff: noqa: RUF001, RUF002
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from priceparser.config import HttpSettings
from priceparser.errors import FetchError, RobotsDenied
from priceparser.robots import RobotsCache

logger = logging.getLogger(__name__)

_RETRY_AFTER_RE = re.compile(r"^\d+$")


class PageFetcher(Protocol):
    """Протокол клиента для загрузки HTML-страниц."""

    async def get_text(self, url: str, *, check_robots: bool = True) -> str: ...


class PoliteClient:
    """HTTP-клиент с паузой на хост, повторами и robots.txt.

    Инвариант: ``get_text`` проверяет robots **до** захвата семафора. Запрос
    ``robots.txt`` идёт через ``_fetch_with_retries`` и сам берёт семафор.
    ``RobotsCache.allowed`` нельзя вызывать, держа семафор: ``Semaphore`` не
    реентерабельный.
    """

    def __init__(
        self,
        settings: HttpSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleeper = sleeper or asyncio.sleep
        self._monotonic = monotonic or time.monotonic
        self._jitter = jitter or (lambda: random.uniform(0.0, 0.05))
        self._sem = asyncio.Semaphore(settings.concurrency)
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._next_at: dict[str, float] = {}
        self._robots = RobotsCache(
            respect=settings.respect_robots,
            user_agent=settings.user_agent,
        )
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PoliteClient:
        limits = httpx.Limits(
            max_connections=self._settings.concurrency,
            max_keepalive_connections=self._settings.concurrency,
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.timeout_seconds),
            follow_redirects=True,
            max_redirects=20,
            headers={
                "User-Agent": self._settings.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
            limits=limits,
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_text(self, url: str, *, check_robots: bool = True) -> str:
        """Текст ответа. После исчерпания попыток или на 4xx вне списка повторов — FetchError.

        Запрет robots — RobotsDenied, без HTTP на сам url.
        """
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise FetchError(url, "некорректный URL")

        if check_robots and not await self._robots.allowed(self._fetch_status, url):
            raise RobotsDenied(url)

        async with self._sem:
            await self._wait_host(url)
            response = await self._fetch_with_retries(url)
            status = response.status_code
            if status in self._settings.retry_statuses:
                raise FetchError(url, f"HTTP {status}", status=status)
            if status >= 400:
                raise FetchError(url, f"HTTP {status}", status=status)
            content_type = response.headers.get("content-type", "")
            logger.debug("GET %s content-type: %s", url, content_type)
            return response.text

    async def _fetch_status(self, url: str) -> tuple[int, str]:
        response = await self._fetch_with_retries(url)
        return response.status_code, response.text

    async def _wait_host(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        if host not in self._host_locks:
            self._host_locks[host] = asyncio.Lock()
        lock = self._host_locks[host]
        async with lock:
            now = self._monotonic()
            wait = self._next_at.get(host, now) - now
            if wait > 0:
                await self._sleeper(wait)
                now = self._monotonic()
            self._next_at[host] = now + self._settings.delay_seconds

    async def _fetch_with_retries(self, url: str) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("PoliteClient не открыт: используйте async with")

        settings = self._settings
        last_exc: Exception | None = None
        for attempt in range(1, settings.max_retries + 1):
            started = self._monotonic()
            try:
                response = await self._client.get(url)
            except (httpx.TimeoutException, httpx.TransportError, httpx.TooManyRedirects) as exc:
                last_exc = exc
                if attempt == settings.max_retries:
                    raise FetchError(url, str(exc)) from exc
                delay = self._backoff(attempt)
                logger.warning("Повтор %s через %.2f с: %s", url, delay, exc)
                await self._sleeper(delay)
                continue

            elapsed_ms = int((self._monotonic() - started) * 1000)
            status = response.status_code
            if status in settings.retry_statuses:
                if attempt == settings.max_retries:
                    return response
                delay = self._retry_after(response) or self._backoff(attempt)
                logger.warning("Повтор %s через %.2f с: HTTP %s", url, delay, status)
                await self._sleeper(delay)
                continue

            logger.info(
                "GET %s -> %s за %s мс (попытка %s)",
                url,
                status,
                elapsed_ms,
                attempt,
            )
            return response

        raise FetchError(url, str(last_exc or "неизвестная ошибка"))

    def _backoff(self, attempt: int) -> float:
        """attempt — номер неудачной попытки, начиная с 1.

        min(backoff_max, backoff_base * 2 ** (attempt - 1)) + jitter().
        """
        base = self._settings.backoff_base_seconds * (2 ** (attempt - 1))
        capped = min(self._settings.backoff_max_seconds, base)
        return capped + self._jitter()

    def _retry_after(self, response: httpx.Response) -> float | None:
        """Заголовок Retry-After: целое число секунд -> min(число, backoff_max).

        HTTP-даты не разбирать.
        """
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        value = raw.strip()
        if not _RETRY_AFTER_RE.match(value):
            return None
        seconds = int(value)
        return float(min(seconds, int(self._settings.backoff_max_seconds)))