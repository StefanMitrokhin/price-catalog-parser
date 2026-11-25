from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from tests.fakes import make_product
from tests.test_diff import _five_product_sets

from priceparser.diff import diff_products
from priceparser.errors import ExportError
from priceparser.export_xlsx import export_changes_xlsx, export_products_xlsx
from priceparser.models import CHANGE_KIND_FONT, ChangeKind, PriceChange


def _rgb_suffix(cell) -> str:
    color = cell.fill.fgColor if cell.fill else None
    if color is None or color.rgb is None:
        return ""
    return str(color.rgb).casefold()[-6:]


def _font_rgb(cell) -> str:
    if cell.font is None or cell.font.color is None or cell.font.color.rgb is None:
        return ""
    return str(cell.font.color.rgb).casefold()[-6:]


def test_products_sheet_style_freeze_filter_widths_and_price_number(
    tmp_path: Path,
) -> None:
    products = [
        make_product(
            name="A-first",
            category="Books",
            price=Decimal("51.77"),
            url="https://example.com/p1",
            image_url="https://example.com/img.jpg",
            old_price=Decimal("60.00"),
        ),
        make_product(
            name="B-second",
            category="Books",
            price=Decimal("10.00"),
            url="https://example.com/p2",
        ),
    ]
    path = tmp_path / "products.xlsx"
    export_products_xlsx(products, path)
    wb = load_workbook(path)
    ws = wb["Товары"]
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:L3"
    assert ws["A1"].value == "Название"
    assert ws["A1"].font.bold
    assert _font_rgb(ws["A1"]).endswith("ffffff")
    assert _rgb_suffix(ws["A1"]).endswith("1f4e79")
    assert ws.row_dimensions[1].height == 22
    assert ws.column_dimensions["A"].width == 42
    assert ws.column_dimensions["B"].width == 12
    price_cell = ws["B2"]
    assert isinstance(price_cell.value, float)
    assert abs(price_cell.value - 51.77) < 1e-9
    assert price_cell.number_format == "#,##0.00"
    url_cell = ws["I2"]
    assert url_cell.hyperlink is not None
    assert _font_rgb(url_cell).endswith("0563c1")
    assert not _rgb_suffix(ws["A2"]).endswith("f7f9fb")
    assert _rgb_suffix(ws["A3"]).endswith("f7f9fb")
    assert ws["A1"].border is not None and ws["A1"].border.left.style == "thin"
    assert wb.properties.creator == "price-catalog-parser"


def test_changes_sheet_omits_unchanged(tmp_path: Path) -> None:
    previous, current = _five_product_sets()
    changes = diff_products(previous, current).changes
    path = tmp_path / "both.xlsx"
    export_products_xlsx(products := current, path, changes=changes, include_unchanged=False)
    wb = load_workbook(path)
    ws = wb["Изменения"]
    labels = {ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)}
    assert len(labels) == 4
    assert "Без изменений" not in labels
    for row in range(2, ws.max_row + 1):
        label = ws.cell(row=row, column=1).value
        if label == "Цена выросла":
            pct = ws.cell(row=row, column=8).value
            assert pct == 10 or pct == 10.0
        color = _font_rgb(ws.cell(row=row, column=1))
        if label in ("Новый", "Цена выросла"):
            kind = ChangeKind.NEW if label == "Новый" else ChangeKind.PRICE_UP
            assert color.endswith(CHANGE_KIND_FONT[kind].casefold())
    del products


def test_changes_sheet_includes_unchanged_when_asked(tmp_path: Path) -> None:
    previous, current = _five_product_sets()
    changes = diff_products(previous, current).changes
    path = tmp_path / "all.xlsx"
    export_products_xlsx(current, path, changes=changes, include_unchanged=True)
    wb = load_workbook(path)
    ws = wb["Изменения"]
    assert ws.max_row == 6
    unchanged_row = next(
        r for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Без изменений"
    )
    assert _font_rgb(ws.cell(row=unchanged_row, column=1)).endswith("666666")


def test_changes_only_workbook(tmp_path: Path) -> None:
    previous, current = _five_product_sets()
    changes = diff_products(previous, current).changes
    path = tmp_path / "changes.xlsx"
    export_changes_xlsx(changes, path, include_unchanged=False)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Изменения"]


def test_empty_products_header_and_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "empty.xlsx"
    export_products_xlsx([], path)
    wb = load_workbook(path)
    ws = wb["Товары"]
    assert ws.auto_filter.ref == "A1:L1"
    assert ws.freeze_panes == "A2"

    def boom_save(_self, _filename):
        raise OSError("disk full")

    monkeypatch.setattr("openpyxl.workbook.workbook.Workbook.save", boom_save)
    with pytest.raises(ExportError):
        export_products_xlsx([], tmp_path / "fail.xlsx")


def test_currency_mismatch_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    change = PriceChange(
        kind=ChangeKind.PRICE_UP,
        identity_key="k",
        name="X",
        url="https://example.com/x",
        sku=None,
        category=None,
        old_price=Decimal("1.00"),
        new_price=Decimal("2.00"),
        delta=Decimal("1.00"),
        delta_pct=Decimal("100.00"),
        currency="GBP",
        currency_mismatch=True,
        source_id="books",
    )
    path = tmp_path / "mismatch.xlsx"
    export_changes_xlsx([change], path)
    wb = load_workbook(path)
    ws = wb["Изменения"]
    assert ws["J2"].value == "Да"

    def boom_save_changes(_self, _filename):
        raise OSError("disk full")

    monkeypatch.setattr("openpyxl.workbook.workbook.Workbook.save", boom_save_changes)
    with pytest.raises(ExportError):
        export_changes_xlsx([change], tmp_path / "fail-changes.xlsx")
