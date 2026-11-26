# ruff: noqa: RUF001, RUF002
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from priceparser.errors import ExportError
from priceparser.models import RunSnapshot

logger = logging.getLogger(__name__)

_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z(?:-\d+)?$")


def make_run_id(when: datetime, runs_dir: Path, source_id: str) -> str:
    """База: when.strftime('%Y%m%dT%H%M%SZ'), when обязан быть aware UTC."""
    if when.tzinfo is None:
        raise ValueError("when должен быть timezone-aware")
    base = when.strftime("%Y%m%dT%H%M%SZ")
    candidate = base
    suffix = 2
    while (runs_dir / source_id / f"{candidate}.json").exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def snapshot_path(runs_dir: Path, source_id: str, run_id: str) -> Path:
    """Путь к JSON-файлу снимка прогона."""
    return runs_dir / source_id / f"{run_id}.json"


def save_snapshot(path: Path, snapshot: RunSnapshot) -> None:
    """Создать родительские каталоги и записать снимок в UTF-8."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = snapshot.model_dump_json(indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"Не удалось записать снимок: {path}: {exc}") from exc


def load_snapshot(path: Path) -> RunSnapshot:
    """Прочитать снимок; битый JSON или схема → ExportError."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"Не удалось прочитать снимок: {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExportError(f"Битый JSON снимка: {path}: {exc}") from exc
    try:
        snapshot = RunSnapshot.model_validate(data)
    except ValidationError as exc:
        raise ExportError(f"Некорректный снимок: {path}: {exc}") from exc
    if snapshot.meta.product_count != len(snapshot.products):
        logger.warning(
            "product_count (%s) не совпадает с числом товаров (%s) в %s",
            snapshot.meta.product_count,
            len(snapshot.products),
            path,
        )
    return snapshot


def list_snapshots(runs_dir: Path, source_id: str) -> list[Path]:
    """Файлы *.json с валидным run_id, сортировка по имени."""
    directory = runs_dir / source_id
    if not directory.is_dir():
        return []
    paths = [p for p in directory.glob("*.json") if _RUN_ID_RE.match(p.stem)]
    return sorted(paths, key=lambda p: p.name)


def latest_pair(runs_dir: Path, source_id: str) -> tuple[Path, Path] | None:
    """Два последних снимка (предыдущий, текущий) или None."""
    paths = list_snapshots(runs_dir, source_id)
    if len(paths) < 2:
        return None
    return paths[-2], paths[-1]
