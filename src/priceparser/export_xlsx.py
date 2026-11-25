# ruff: noqa: RUF001, RUF002
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from priceparser.errors import ExportError
from priceparser.export_csv import PRODUCT_HEADERS, sort_products
from priceparser.models import (
    AVAILABILITY_RU,
    CHANGE_KIND_FONT,
    CHANGE_KIND_RU,
    ChangeKind,
    PriceChange,
    Product,
)

PRODUCT_WIDTHS: tuple[float, ...] = (42, 12, 14, 10, 16, 22, 12, 20, 46, 46, 16, 22)

CHANGE_HEADERS: tuple[str, ...] = (
    "Изменение",
    "Название",
    "Артикул",
    "Категория",
    "Цена была",
    "Цена стала",
    "Разница",
    "Разница %",
    "Валюта",
    "Валюты различаются",
    "URL",
    "Источник",
)
CHANGE_WIDTHS: tuple[float, ...] = (18, 42, 20, 22, 14, 14, 12, 12, 10, 20, 46, 16)

_THIN = Side(style="thin", color="D9D9D9")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E79")
_ZEBRA_FILL = PatternFill(fill_type="solid", fgColor="F7F9FB")
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_DATA_FONT = Font(name="Calibri", size=11)
_LINK_FONT = Font(name="Calibri", size=11, color="0563C1", underline="single")
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=False)
_DATA_ALIGNMENT = Alignment(vertical="center")
_PRICE_FORMAT = "#,##0.00"
_RATING_FORMAT = "0.0"
_PCT_FORMAT = "0.00"


def _style_sheet(
    ws: Worksheet,
    headers: tuple[str, ...],
    widths: tuple[float, ...],
    *,
    last_row: int,
) -> None:
    """Общее оформление листа: шапка, ширины, фильтр, страница."""
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGNMENT
        cell.border = _BORDER
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = widths[col_idx - 1]

    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last_col}{last_row}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"


def _apply_zebra_and_border(ws: Worksheet, row: int, col_count: int) -> None:
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.border = _BORDER
        cell.alignment = _DATA_ALIGNMENT
        if cell.font is None or cell.font == _DATA_FONT:
            cell.font = _DATA_FONT
        if row >= 3 and row % 2 == 1:
            cell.fill = _ZEBRA_FILL


def _set_hyperlink(cell: Cell, url: str) -> None:
    cell.hyperlink = url
    cell.font = _LINK_FONT


def _money_cell(cell: Cell, value: Decimal | None) -> None:
    if value is None:
        cell.value = None
    else:
        cell.value = float(value)
    cell.number_format = _PRICE_FORMAT


def _write_products_sheet(ws: Worksheet, products: list[Product]) -> None:
    ordered = sort_products(products)
    last_row = max(1, len(ordered) + 1)
    _style_sheet(ws, PRODUCT_HEADERS, PRODUCT_WIDTHS, last_row=last_row)

    for row_idx, product in enumerate(ordered, start=2):
        row_values: list[object] = [
            product.name,
            None,
            None,
            product.currency,
            AVAILABILITY_RU[product.availability],
            product.category,
            None,
            product.sku,
            product.url,
            product.image_url,
            product.source_id,
            product.scraped_at.isoformat(timespec="seconds"),
        ]
        for col_idx, value in enumerate(row_values, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)
        _apply_zebra_and_border(ws, row_idx, len(PRODUCT_HEADERS))
        _money_cell(ws.cell(row=row_idx, column=2), product.price)
        _money_cell(ws.cell(row=row_idx, column=3), product.old_price)
        if product.rating is not None:
            rating_cell = ws.cell(row=row_idx, column=7, value=float(product.rating))
            rating_cell.number_format = _RATING_FORMAT
        if product.url:
            _set_hyperlink(ws.cell(row=row_idx, column=9), product.url)
        if product.image_url:
            _set_hyperlink(ws.cell(row=row_idx, column=10), product.image_url)


def _filtered_changes(changes: list[PriceChange], *, include_unchanged: bool) -> list[PriceChange]:
    if include_unchanged:
        return list(changes)
    return [c for c in changes if c.kind != ChangeKind.UNCHANGED]


def _write_changes_sheet(
    ws: Worksheet, changes: list[PriceChange], *, include_unchanged: bool
) -> None:
    filtered = _filtered_changes(changes, include_unchanged=include_unchanged)
    last_row = max(1, len(filtered) + 1)
    _style_sheet(ws, CHANGE_HEADERS, CHANGE_WIDTHS, last_row=last_row)

    for row_idx, change in enumerate(filtered, start=2):
        mismatch = "Да" if change.currency_mismatch else "Нет"
        ws.cell(row=row_idx, column=1, value=CHANGE_KIND_RU[change.kind])
        ws.cell(row=row_idx, column=2, value=change.name)
        ws.cell(row=row_idx, column=3, value=change.sku)
        ws.cell(row=row_idx, column=4, value=change.category)
        ws.cell(row=row_idx, column=9, value=change.currency)
        ws.cell(row=row_idx, column=10, value=mismatch)
        ws.cell(row=row_idx, column=11, value=change.url)
        ws.cell(row=row_idx, column=12, value=change.source_id)
        _apply_zebra_and_border(ws, row_idx, len(CHANGE_HEADERS))
        _money_cell(ws.cell(row=row_idx, column=5), change.old_price)
        _money_cell(ws.cell(row=row_idx, column=6), change.new_price)
        _money_cell(ws.cell(row=row_idx, column=7), change.delta)
        if change.delta_pct is not None:
            pct_cell = ws.cell(row=row_idx, column=8, value=float(change.delta_pct))
            pct_cell.number_format = _PCT_FORMAT
        kind_cell = ws.cell(row=row_idx, column=1)
        kind_cell.font = Font(
            name="Calibri",
            size=11,
            color=CHANGE_KIND_FONT[change.kind],
        )
        if change.url:
            _set_hyperlink(ws.cell(row=row_idx, column=11), change.url)


def export_products_xlsx(
    products: list[Product],
    path: Path,
    *,
    changes: list[PriceChange] | None = None,
    include_unchanged: bool = False,
) -> None:
    """Книга с листом «Товары» и опционально «Изменения»."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.properties.creator = "price-catalog-parser"
    ws = wb.active
    ws.title = "Товары"
    _write_products_sheet(ws, products)

    if changes is not None:
        ws_changes = wb.create_sheet("Изменения")
        _write_changes_sheet(ws_changes, changes, include_unchanged=include_unchanged)

    wb.active = wb["Товары"]
    try:
        wb.save(path)
    except OSError as exc:
        raise ExportError(f"Не удалось записать XLSX: {path}: {exc}") from exc


def export_changes_xlsx(
    changes: list[PriceChange],
    path: Path,
    *,
    include_unchanged: bool = False,
) -> None:
    """Книга только с листом «Изменения»."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.properties.creator = "price-catalog-parser"
    ws = wb.active
    ws.title = "Изменения"
    _write_changes_sheet(ws, changes, include_unchanged=include_unchanged)
    wb.active = wb["Изменения"]
    try:
        wb.save(path)
    except OSError as exc:
        raise ExportError(f"Не удалось записать XLSX: {path}: {exc}") from exc
