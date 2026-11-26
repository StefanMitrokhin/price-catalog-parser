from __future__ import annotations

import pytest
from tests.conftest import read_fixture

from priceparser.errors import FetchError
from priceparser.robots import RobotsCache


@pytest.fixture
def fetch_counter() -> dict[str, int]:
    return {"n": 0}


async def test_disallow_rule(fetch_counter: dict[str, int]) -> None:
    body = read_fixture("robots_disallow_private.txt")

    async def fetch(_url: str) -> tuple[int, str]:
        fetch_counter["n"] += 1
        return 200, body

    cache = RobotsCache(respect=True, user_agent="TestBot")
    assert not await cache.allowed(fetch, "https://example.com/private/x")
    assert await cache.allowed(fetch, "https://example.com/ok")

    async def fetch_err(_url: str) -> tuple[int, str]:
        raise FetchError(_url, "down")

    cache2 = RobotsCache(respect=True, user_agent="TestBot")
    assert not await cache2.allowed(fetch_err, "https://example.net/x")


async def test_404_allows_all() -> None:
    async def fetch(_url: str) -> tuple[int, str]:
        return 404, ""

    cache = RobotsCache(respect=True, user_agent="TestBot")
    assert await cache.allowed(fetch, "https://example.com/anything")

    async def fetch410(_url: str) -> tuple[int, str]:
        return 410, ""

    cache410 = RobotsCache(respect=True, user_agent="TestBot")
    assert await cache410.allowed(fetch410, "https://example.com/retired")


async def test_500_denies_all(fetch_counter: dict[str, int]) -> None:
    async def fetch(_url: str) -> tuple[int, str]:
        fetch_counter["n"] += 1
        return 500, "error"

    cache = RobotsCache(respect=True, user_agent="TestBot")
    assert not await cache.allowed(fetch, "https://example.com/ok")
    assert not await cache.allowed(fetch, "https://example.com/ok2")
    assert fetch_counter["n"] == 1


async def test_respect_false_allows_without_fetch(fetch_counter: dict[str, int]) -> None:
    async def fetch(_url: str) -> tuple[int, str]:
        fetch_counter["n"] += 1
        return 200, ""

    cache = RobotsCache(respect=False, user_agent="TestBot")
    assert await cache.allowed(fetch, "https://example.com/x")
    assert fetch_counter["n"] == 0


async def test_cache_fetches_robots_once(fetch_counter: dict[str, int]) -> None:
    async def fetch(_url: str) -> tuple[int, str]:
        fetch_counter["n"] += 1
        return 404, ""

    cache = RobotsCache(respect=True, user_agent="TestBot")
    await cache.allowed(fetch, "https://example.com/a")
    await cache.allowed(fetch, "https://example.com/b")
    assert fetch_counter["n"] == 1
