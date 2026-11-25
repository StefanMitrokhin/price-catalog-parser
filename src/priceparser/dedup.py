from __future__ import annotations

import logging

from priceparser.models import ProductDraft
from priceparser.urls import draft_key

logger = logging.getLogger(__name__)


def dedupe_drafts(drafts: list[ProductDraft]) -> tuple[list[ProductDraft], int]:
    """Оставить первое вхождение draft_key. Вернуть (уникальные, сколько отброшено)."""
    seen: set[str] = set()
    unique: list[ProductDraft] = []
    dropped = 0
    for draft in drafts:
        key = draft_key(draft)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        unique.append(draft)
    if dropped > 0:
        logger.info("Отброшено дублей: %s", dropped)
    return unique, dropped
