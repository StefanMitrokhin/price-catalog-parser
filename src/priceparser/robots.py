from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from priceparser.errors import FetchError

logger = logging.getLogger(__name__)

_FetchFn = Callable[[str], Awaitable[tuple[int, str]]]

# origin -> (allow_origin, parser or None); allow_origin False means entire origin denied
_CacheEntry = tuple[bool, RobotFileParser | None]


class RobotsCache:
    def __init__(self, *, respect: bool, user_agent: str) -> None:
        self._respect = respect
        self._user_agent = user_agent
        self._cache: dict[str, _CacheEntry] = {}

    async def allowed(
        self,
        fetch: _FetchFn,
        url: str,
    ) -> bool:
        """Можно ли качать url."""
        if not self._respect:
            return True

        parts = urlsplit(url)
        netloc = (parts.netloc or "").lower()
        origin = f"{parts.scheme.lower()}://{netloc}"

        if origin in self._cache:
            allow_origin, parser = self._cache[origin]
            if not allow_origin:
                return False
            if parser is None:
                return True
            return parser.can_fetch(self._user_agent, url)

        robots_url = f"{origin}/robots.txt"
        try:
            status, text = await fetch(robots_url)
        except FetchError as exc:
            logger.error("robots.txt для %s: %s", origin, exc.message)
            self._cache[origin] = (False, None)
            return False

        if status in (404, 410):
            self._cache[origin] = (True, None)
            return True

        if status >= 400:
            logger.error("robots.txt для %s вернул HTTP %s", origin, status)
            self._cache[origin] = (False, None)
            return False

        parser = RobotFileParser()
        parser.parse(text.splitlines())
        self._cache[origin] = (True, parser)
        return parser.can_fetch(self._user_agent, url)