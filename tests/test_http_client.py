from __future__ import annotations

import httpx
import pytest
from tests.conftest import read_fixture

from priceparser.config import HttpSettings
from priceparser.errors import FetchError, RobotsDenied
from priceparser.http_client import PoliteClient


def _settings(**kwargs) -> HttpSettings:
    base = dict(
        user_agent="test-agent/1.0",
        timeout_seconds=5.0,
        max_retries=3,
        backoff_base_seconds=0.5,
        backoff_max_seconds=8.0,
        retry_statuses=(429, 500, 502, 503, 504),
        concurrency=1,
        delay_seconds=1.0,
        respect_robots=False,
    )
    base.update(kwargs)
    return HttpSettings(**base)


@pytest.mark.asyncio
async def test_retry_then_success_backoff() -> None:
    calls: list[str] = []
    sleeps: list[float] = []
    state = {"t": 0.0}

    async def sleeper(seconds: float) -> None:
        state["t"] += seconds
        sleeps.append(seconds)

    def monotonic() -> float:
        return state["t"]

    attempt = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        attempt["n"] += 1
        if attempt["n"] <= 2:
            return httpx.Response(500, text="err")
        return httpx.Response(200, text="ok")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        monotonic=monotonic,
        jitter=lambda: 0.0,
    ) as client:
        text = await client.get_text("https://example.com/page")
    assert text == "ok"
    assert sleeps == [0.5, 1.0]


@pytest.mark.asyncio
async def test_retry_exhausted() -> None:
    sleeps: list[float] = []
    state = {"t": 0.0}

    async def sleeper(seconds: float) -> None:
        state["t"] += seconds
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="err")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        monotonic=lambda: state["t"],
        jitter=lambda: 0.0,
    ) as client:
        with pytest.raises(FetchError) as exc_info:
            await client.get_text("https://example.com/fail")
    assert exc_info.value.status == 500
    assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_404_no_retry() -> None:
    sleeps: list[float] = []
    hits = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(404, text="missing")

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        jitter=lambda: 0.0,
    ) as client:
        with pytest.raises(FetchError) as exc_info:
            await client.get_text("https://example.com/missing")
    assert exc_info.value.status == 404
    assert hits["n"] == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_retry_after_capped() -> None:
    sleeps: list[float] = []
    state = {"t": 0.0, "n": 0}

    async def sleeper(seconds: float) -> None:
        state["t"] += seconds
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "100"}, text="wait")
        return httpx.Response(200, text="ok")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        monotonic=lambda: state["t"],
        jitter=lambda: 0.0,
    ) as client:
        text = await client.get_text("https://example.com/rate")
    assert text == "ok"
    assert sleeps == [8.0]


@pytest.mark.asyncio
async def test_delay_between_requests() -> None:
    sleeps: list[float] = []
    state = {"t": 0.0, "n": 0}

    async def sleeper(seconds: float) -> None:
        state["t"] += seconds
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        return httpx.Response(200, text=f"body{state['n']}")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        monotonic=lambda: state["t"],
        jitter=lambda: 0.0,
    ) as client:
        await client.get_text("https://example.com/one")
        await client.get_text("https://example.com/two")
    assert sleeps == [1.0]


@pytest.mark.asyncio
async def test_robots_denied_does_not_get_page() -> None:
    robots = read_fixture("robots_disallow_private.txt")
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(200, text="page")

    async with PoliteClient(
        _settings(respect_robots=True),
        transport=httpx.MockTransport(handler),
        jitter=lambda: 0.0,
    ) as client:
        with pytest.raises(RobotsDenied):
            await client.get_text("https://example.com/private/item")
        text = await client.get_text("https://example.com/ok")
    assert text == "page"
    assert "/private/item" not in paths


@pytest.mark.asyncio
async def test_timeout_retried() -> None:
    sleeps: list[float] = []
    state = {"t": 0.0, "n": 0}

    async def sleeper(seconds: float) -> None:
        state["t"] += seconds
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, text="done")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        monotonic=lambda: state["t"],
        jitter=lambda: 0.0,
    ) as client:
        text = await client.get_text("https://example.com/slow")
    assert text == "done"
    assert sleeps == [0.5]

    state2 = {"t": 0.0, "n": 0}
    sleeps2: list[float] = []

    async def sleeper2(seconds: float) -> None:
        state2["t"] += seconds
        sleeps2.append(seconds)

    def handler2(_request: httpx.Request) -> httpx.Response:
        state2["n"] += 1
        if state2["n"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, text="ok")

    async with PoliteClient(
        _settings(),
        transport=httpx.MockTransport(handler2),
        sleeper=sleeper2,
        monotonic=lambda: state2["t"],
        jitter=lambda: 0.0,
    ) as client2:
        text2 = await client2.get_text("https://example.com/conn")
    assert text2 == "ok"
    assert sleeps2 == [0.5]

    state3 = {"n": 0}

    def redirect_boom(_request: httpx.Request) -> httpx.Response:
        state3["n"] += 1
        raise httpx.TooManyRedirects("too many")

    async with PoliteClient(
        _settings(max_retries=1),
        transport=httpx.MockTransport(redirect_boom),
        jitter=lambda: 0.0,
    ) as client3:
        with pytest.raises(FetchError):
            await client3.get_text("https://example.com/redir")
