from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Текущий момент в UTC, микросекунды обнулены."""
    return datetime.now(timezone.utc).replace(microsecond=0)  # noqa: UP017