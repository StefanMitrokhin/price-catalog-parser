# ruff: noqa: RUF001
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes import make_product

from priceparser.errors import ExportError
from priceparser.export_csv import PRODUCT_HEADERS, export_products_csv
from priceparser.models import Availability


def test_bom_delimiter_headers_and_numbers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    products = [
        make_product(name="A", url="https://example.com/a"),
        make_product(
            name="B",
            url="https://example.com/b",
            price=Decimal("10.00"),
            rating=3,
        ),
        make_product(name="C", url="https://example.com/c"),
    ]
    path = tmp_path / "out.csv"
    export_products_csv(products, path)
    assert path.read_bytes()[:3] == b"\xef\xbb\xbf"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(PRODUCT_HEADERS)
    original_open = Path.open

    def broken_open(self, *args, **kwargs):
        if str(self).endswith("fail.csv"):
            raise OSError("no write")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(ExportError):
        export_products_csv([make_product()], tmp_path / "fail.csv")

    price_row = next(r for r in rows[1:] if r[0] == "B")
    assert price_row[1] == "10.00"
    assert price_row[6] == "3.0"
    assert price_row[4] == "В наличии"


def test_custom_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "semi.csv"
    export_products_csv([make_product()], path, delimiter=";")
    header = path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert ";" in header
    assert "," not in header.replace("Снято", "")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][0] == "Название"
    with pytest.raises(ExportError):
        export_products_csv([], tmp_path / "bad.csv", delimiter=";;")


def test_empty_products_header_only(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    export_products_csv([], path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 1


def test_quotes_comma_in_name(tmp_path: Path) -> None:
    name = 'Say "Hello", world'
    path = tmp_path / "quoted.csv"
    export_products_csv([make_product(name=name)], path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[1][0] == name


def test_sorted_by_category_then_name(tmp_path: Path) -> None:
    products = [
        make_product(name="B", category="Books", url="https://example.com/b"),
        make_product(name="A-without-category", category=None, url="https://example.com/c"),
        make_product(name="A", category="Books", url="https://example.com/a"),
        make_product(
            name="Unknown",
            category="Books",
            availability=Availability.UNKNOWN,
            url="https://example.com/u",
        ),
    ]
    path = tmp_path / "sorted.csv"
    export_products_csv(products, path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    names = [r[0] for r in rows[1:]]
    assert names == ["A", "B", "Unknown", "A-without-category"]
    unknown_row = next(r for r in rows[1:] if r[0] == "Unknown")
    assert unknown_row[4] == "Неизвестно"
