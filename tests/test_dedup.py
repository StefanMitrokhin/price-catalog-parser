from __future__ import annotations

import pytest
from tests.fakes import make_draft

from priceparser.dedup import dedupe_drafts


def test_keeps_first_by_url(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="priceparser.dedup")
    url = "https://example.com/p"
    first = make_draft(name="First", url=url)
    second = make_draft(name="Second", url=url)
    unique, dropped = dedupe_drafts([first, second])
    assert len(unique) == 1
    assert unique[0].name == "First"
    assert dropped == 1
    assert "Отброшено дублей" in caplog.text


def test_sku_key_collapses_different_urls() -> None:
    first = make_draft(url="https://example.com/a", sku="sku1")
    second = make_draft(url="https://example.com/b", sku="sku1")
    unique, dropped = dedupe_drafts([first, second])
    assert len(unique) == 1
    assert unique[0].url == "https://example.com/a"
    assert dropped == 1


def test_no_duplicates_returns_same_length() -> None:
    drafts = [
        make_draft(url="https://example.com/1", sku="a"),
        make_draft(url="https://example.com/2", sku="b"),
    ]
    unique, dropped = dedupe_drafts(drafts)
    assert dropped == 0
    assert [d.url for d in unique] == [d.url for d in drafts]
