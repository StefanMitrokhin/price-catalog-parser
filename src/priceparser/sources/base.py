from __future__ import annotations

from abc import ABC, abstractmethod

from priceparser.http_client import PageFetcher
from priceparser.models import CollectResult


class Source(ABC):
    """Базовый адаптер источника каталога."""

    source_id: str

    @abstractmethod
    async def collect(self, client: PageFetcher) -> CollectResult:
        """Собрать товары источника. Внутри вызвать walk_listings и dedupe_drafts."""
