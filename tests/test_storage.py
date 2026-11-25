from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes import make_product

from priceparser.errors import ExportError
from priceparser.models import RunMeta, RunSnapshot
from priceparser.storage import (
    latest_pair,
    list_snapshots,
    load_snapshot,
    make_run_id,
    save_snapshot,
    snapshot_path,
)


def test_roundtrip_snapshot_decimal_and_datetime(
    tmp_path: Path, fixed_now: datetime, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = make_product(price=Decimal("51.77"), scraped_at=fixed_now)
    meta = RunMeta(
        run_id="20261125T221500Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=1,
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path="config.yaml",
    )
    snapshot = RunSnapshot(meta=meta, products=[product])
    path = tmp_path / "books" / "20261125T221500Z.json"
    save_snapshot(path, snapshot)
    loaded = load_snapshot(path)

    def fail_write(self, *args, **kwargs):
        if "blocked.json" in str(self):
            raise OSError("deny")
        return Path.write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(ExportError):
        save_snapshot(path.parent / "blocked.json", snapshot)
    assert loaded.products[0].price == Decimal("51.77")
    assert loaded.products[0].scraped_at == fixed_now
    raw = path.read_text(encoding="utf-8")
    assert '"51.77"' in raw
    assert "2026-11-25T22:15:00" in raw
    assert "51.7700000001" not in raw


def test_run_id_collision_suffix(tmp_path: Path, fixed_now: datetime) -> None:
    with pytest.raises(ValueError):
        make_run_id(datetime(2026, 1, 1, 1, 1), tmp_path, "books")
    runs_dir = tmp_path / "runs"
    source_id = "books"
    first_id = make_run_id(fixed_now, runs_dir, source_id)
    snapshot_path(runs_dir, source_id, first_id).parent.mkdir(parents=True, exist_ok=True)
    snapshot_path(runs_dir, source_id, first_id).write_text("{}", encoding="utf-8")
    second_id = make_run_id(fixed_now, runs_dir, source_id)
    assert second_id.endswith("-2")


def test_list_and_latest_pair(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs" / "books"
    runs_dir.mkdir(parents=True)
    (runs_dir / "20261125T221500Z.json").write_text("{}", encoding="utf-8")
    (runs_dir / "20261125T221501Z.json").write_text("{}", encoding="utf-8")
    (runs_dir / "notes.json").write_text("{}", encoding="utf-8")
    listed = list_snapshots(tmp_path / "runs", "books")
    assert len(listed) == 2
    pair = latest_pair(tmp_path / "runs", "books")
    assert pair is not None
    assert pair[0].name == "20261125T221500Z.json"
    assert pair[1].name == "20261125T221501Z.json"


def test_ignores_missing_dir(tmp_path: Path) -> None:
    assert list_snapshots(tmp_path / "missing", "books") == []
    assert latest_pair(tmp_path / "missing", "books") is None


def test_load_bad_json_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ExportError):
        load_snapshot(path)

    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"meta": {}, "products": []}', encoding="utf-8")
    with pytest.raises(ExportError):
        load_snapshot(invalid)


def test_product_count_mismatch_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    product = make_product()
    data = {
        "meta": {
            "run_id": "20261125T221500Z",
            "source_id": "books",
            "started_at": product.scraped_at.isoformat(),
            "finished_at": product.scraped_at.isoformat(),
            "product_count": 5,
            "pages_fetched": 1,
            "detail_pages_fetched": 0,
            "page_errors": 0,
            "config_path": "config.yaml",
        },
        "products": [json.loads(product.model_dump_json())],
    }
    path = tmp_path / "snap.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    load_snapshot(path)
    joined = " ".join(r.message for r in caplog.records).casefold()
    assert "product_count" in joined
