from __future__ import annotations

from typing import Protocol


class PageFetcher(Protocol):
    """Протокол клиента для загрузки HTML-страниц."""

    async def get_text(self, url: str, *, check_robots: bool = True) -> str: ...