# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from priceparser import __version__, clock
from priceparser.config import ResolvedConfig, ResolvedSource, load_config, select_sources
from priceparser.diff import diff_products
from priceparser.errors import ConfigError, ExportError
from priceparser.export_csv import export_products_csv
from priceparser.export_xlsx import export_changes_xlsx, export_products_xlsx
from priceparser.http_client import PoliteClient
from priceparser.logging_setup import setup_logging
from priceparser.models import CollectResult, DiffReport, Product, RunMeta, RunSnapshot
from priceparser.sources.registry import create_source
from priceparser.storage import (
    latest_pair,
    list_snapshots,
    load_snapshot,
    make_run_id,
    save_snapshot,
    snapshot_path,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Парсер каталогов и цен. Выгрузка в Excel и CSV.",
)

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_VALID_FORMATS = frozenset({"all", "xlsx", "csv"})
_VALID_DIFF_MODES = frozenset({"auto", "on", "off"})

logger = logging.getLogger("priceparser")


def build_client(config: ResolvedConfig) -> PoliteClient:
    """Фабрика. Тесты подменяют priceparser.cli.build_client."""
    return PoliteClient(config.http)


def _display(path: Path) -> str:
    resolved = path.resolve()
    try:
        cwd = Path.cwd().resolve()
        if resolved.is_relative_to(cwd):
            return resolved.relative_to(cwd).as_posix()
    except ValueError:
        pass
    return resolved.as_posix()


def _echo_config_error(exc: ConfigError) -> None:
    typer.echo(str(exc), err=True)
    raise typer.Exit(code=2)


def _parse_log_level(level: str) -> str:
    upper = level.upper()
    if upper not in _VALID_LOG_LEVELS:
        raise ConfigError(f"Некорректный уровень логирования: {level}")
    return upper


def _resolve_log_level(cli_level: str | None, config: ResolvedConfig) -> str:
    if cli_level is not None:
        return _parse_log_level(cli_level)
    return _parse_log_level(config.log_level)


def _check_format(fmt: str) -> str:
    folded = fmt.casefold()
    if folded not in _VALID_FORMATS:
        raise ConfigError("Формат должен быть all, xlsx или csv")
    return folded


def _check_diff_mode(mode: str) -> str:
    folded = mode.casefold()
    if folded not in _VALID_DIFF_MODES:
        raise ConfigError("Сравнение должно быть auto, on или off")
    return folded


def _format_comparison_line(prev_path: Path, report: DiffReport) -> str:
    return (
        f"Сравнение: с {_display(prev_path)}: "
        f"новых {report.new_count}, пропавших {report.removed_count}, "
        f"цена выросла {report.up_count}, цена упала {report.down_count}, "
        f"без изменений {report.unchanged_count}"
    )


@dataclass(frozen=True)
class SourceReportLines:
    source_id: str
    pages_fetched: int
    detail_pages_fetched: int
    product_count: int
    duplicates_dropped: int
    page_errors: int
    snapshot_path: Path | None
    excel_path: Path | None
    csv_path: Path | None
    changes_path: Path | None
    comparison_line: str | None
    export_format: str


def _print_source_report(lines: SourceReportLines) -> None:
    typer.echo(f"Источник: {lines.source_id}")
    typer.echo(f"Страниц каталога: {lines.pages_fetched}")
    typer.echo(f"Страниц карточек: {lines.detail_pages_fetched}")
    typer.echo(
        f"Товаров: {lines.product_count} (дублей отброшено: {lines.duplicates_dropped})"
    )
    typer.echo(f"Ошибки страниц: {lines.page_errors}")
    if lines.snapshot_path is not None:
        typer.echo(f"Снимок: {_display(lines.snapshot_path)}")
    if lines.export_format in {"all", "xlsx"} and lines.excel_path is not None:
        typer.echo(f"Excel: {_display(lines.excel_path)}")
    if lines.export_format in {"all", "csv"} and lines.csv_path is not None:
        typer.echo(f"CSV: {_display(lines.csv_path)}")
    if lines.comparison_line is not None:
        typer.echo(lines.comparison_line)
    if lines.changes_path is not None:
        typer.echo(f"Файл изменений: {_display(lines.changes_path)}")


def _should_write_files(result: CollectResult) -> bool:
    if result.products:
        return True
    return result.page_errors == 0


def _source_ok_after_collect(result: CollectResult, *, strict: bool) -> bool:
    if result.products:
        return not (result.page_errors > 0 and strict)
    return result.page_errors == 0


def _effective_max_pages(source: ResolvedSource, cli_max: int | None) -> int | None:
    if cli_max is not None:
        return cli_max
    return source.max_pages


def _effective_fetch_details(
    source: ResolvedSource,
    *,
    fetch_details: bool,
    no_fetch_details: bool,
) -> bool:
    if fetch_details:
        return True
    if no_fetch_details:
        return False
    return source.fetch_details


def _validate_yaml_fetch(source: ResolvedSource, fetch_details: bool) -> None:
    if source.type == "yaml" and fetch_details:
        raise ConfigError("yaml-источник в этой версии не ходит в карточки")


def _resolve_output_dir(config: ResolvedConfig, cli_output: Path | None) -> Path:
    if cli_output is not None:
        if cli_output.is_absolute():
            return cli_output.resolve()
        return (Path.cwd() / cli_output).resolve()
    return config.output_dir


def _find_previous_snapshot(
    runs_dir: Path,
    source_id: str,
    *,
    current_snapshot: Path,
    explicit_previous: Path | None,
) -> Path | None:
    if explicit_previous is not None:
        return explicit_previous
    snapshots = list_snapshots(runs_dir, source_id)
    candidates = [path for path in snapshots if path.resolve() != current_snapshot.resolve()]
    if not candidates:
        return None
    return candidates[-1]


def _compute_diff_state(
    *,
    diff_mode: str,
    runs_dir: Path,
    source_id: str,
    current_snapshot: Path,
    explicit_previous: Path | None,
    current_products: list[Product],
) -> tuple[DiffReport | None, str, bool]:
    """Вернуть (report, comparison_line, fail_source)."""
    if diff_mode == "off":
        return None, "Сравнение: выключено", False

    prev_path = _find_previous_snapshot(
        runs_dir,
        source_id,
        current_snapshot=current_snapshot,
        explicit_previous=explicit_previous,
    )
    if prev_path is None:
        if diff_mode == "auto":
            return None, "Сравнение: предыдущий снимок не найден", False
        return None, "Сравнение: ошибка, предыдущий снимок не найден", True

    previous = load_snapshot(prev_path)
    report = diff_products(previous.products, current_products)
    return report, _format_comparison_line(prev_path, report), False


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"price-catalog-parser {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Показать версию и выйти",
            is_eager=True,
            callback=version_callback,
        ),
    ] = False,
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("version", help="Показать версию.")
def version_cmd() -> None:
    typer.echo(f"price-catalog-parser {__version__}")
    raise typer.Exit(code=0)


@app.command("validate", help="Проверить конфиг, не ходя в сеть.")
def validate_cmd(
    config_path: Annotated[Path, typer.Option("--config", "-c", help="Путь к YAML-конфигу")] = Path(
        "config.yaml"
    ),
) -> None:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _echo_config_error(exc)
    typer.echo(f"Конфиг корректен: {len(config.sources)} источников")
    raise typer.Exit(code=0)


@app.command("sources", help="Показать источники из конфига.")
def sources_cmd(
    config_path: Annotated[Path, typer.Option("--config", "-c", help="Путь к YAML-конфигу")] = Path(
        "config.yaml"
    ),
) -> None:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _echo_config_error(exc)

    typer.echo("ID  TYPE  STATUS  START")
    for source in config.sources:
        status = "enabled" if source.enabled else "disabled"
        if source.type == "yaml" and source.yaml_spec is not None:
            start = source.yaml_spec.start_urls[0]
        else:
            start = source.start_url or ""
        typer.echo(f"{source.id}  {source.type}  {status}  {start}")
    raise typer.Exit(code=0)


async def _run_sources(
    config: ResolvedConfig,
    selected: tuple[ResolvedSource, ...],
    *,
    max_pages: int | None,
    fetch_details: bool,
    no_fetch_details: bool,
    output_dir: Path,
    fmt: str,
    diff_mode: str,
    previous_path: Path | None,
    strict: bool,
    csv_delimiter: str,
    include_unchanged: bool,
    client: PoliteClient,
) -> int:
    failed = 0
    printed_any = False

    for source in selected:
        eff_fetch = _effective_fetch_details(
            source, fetch_details=fetch_details, no_fetch_details=no_fetch_details
        )
        _validate_yaml_fetch(source, eff_fetch)
        eff_max = _effective_max_pages(source, max_pages)

        try:
            adapter = create_source(
                source,
                max_pages=eff_max,
                fetch_details=eff_fetch,
            )
        except ConfigError as exc:
            _echo_config_error(exc)

        source_failed = False
        try:
            result = await adapter.collect(client)
        except Exception:
            logger.exception("Источник %s: ошибка сбора", source.id)
            failed += 1
            source_failed = True
            if strict:
                break
            continue

        if not _should_write_files(result):
            failed += 1
            source_failed = True
            if strict:
                break
            continue

        if not _source_ok_after_collect(result, strict=strict):
            failed += 1
            source_failed = True

        started_at = result.products[0].scraped_at if result.products else clock.utc_now()
        finished_at = clock.utc_now()
        run_id = make_run_id(started_at, config.runs_dir, source.id)
        snap_path = snapshot_path(config.runs_dir, source.id, run_id)

        meta = RunMeta(
            run_id=run_id,
            source_id=source.id,
            started_at=started_at,
            finished_at=finished_at,
            product_count=len(result.products),
            pages_fetched=result.pages_fetched,
            detail_pages_fetched=result.detail_pages_fetched,
            page_errors=result.page_errors,
            config_path=str(config.config_path),
        )
        snapshot = RunSnapshot(meta=meta, products=result.products)

        try:
            save_snapshot(snap_path, snapshot)
        except ExportError:
            logger.exception("Не удалось записать снимок %s", snap_path)
            failed += 1
            source_failed = True
            if strict:
                break
            continue

        report, comparison_line, diff_fail = _compute_diff_state(
            diff_mode=diff_mode,
            runs_dir=config.runs_dir,
            source_id=source.id,
            current_snapshot=snap_path,
            explicit_previous=previous_path,
            current_products=result.products,
        )
        if diff_fail:
            failed += 1
            source_failed = True

        base_name = f"{source.id}-{run_id}"
        excel_path = output_dir / f"{base_name}.xlsx"
        csv_path = output_dir / f"{base_name}.csv"
        changes_path: Path | None = None

        wrote_excel: Path | None = None
        wrote_csv: Path | None = None

        try:
            if fmt in {"all", "csv"}:
                export_products_csv(result.products, csv_path, delimiter=csv_delimiter)
                wrote_csv = csv_path
                logger.info("Записан %s", csv_path)

            if fmt in {"all", "xlsx"}:
                changes = report.changes if report is not None else None
                export_products_xlsx(
                    result.products,
                    excel_path,
                    changes=changes,
                    include_unchanged=include_unchanged,
                )
                wrote_excel = excel_path
                logger.info("Записан %s", excel_path)
            elif fmt == "csv" and report is not None:
                changes_path = output_dir / f"{base_name}-changes.xlsx"
                export_changes_xlsx(
                    report.changes,
                    changes_path,
                    include_unchanged=include_unchanged,
                )
                logger.info("Записан %s", changes_path)
        except ExportError:
            logger.exception("Ошибка экспорта для источника %s", source.id)
            failed += 1
            source_failed = True

        if printed_any:
            typer.echo("")
        _print_source_report(
            SourceReportLines(
                source_id=source.id,
                pages_fetched=result.pages_fetched,
                detail_pages_fetched=result.detail_pages_fetched,
                product_count=len(result.products),
                duplicates_dropped=result.duplicates_dropped,
                page_errors=result.page_errors,
                snapshot_path=snap_path,
                excel_path=wrote_excel,
                csv_path=wrote_csv,
                changes_path=changes_path,
                comparison_line=comparison_line,
                export_format=fmt,
            )
        )
        printed_any = True

        if source_failed and strict:
            break

    return failed


@app.command("run", help="Скачать источники и записать Excel, CSV и снимок.")
def run_cmd(
    config_path: Annotated[Path, typer.Option("--config", "-c", help="Путь к YAML-конфигу")] = Path(
        "config.yaml"
    ),
    source_ids: Annotated[
        list[str] | None,
        typer.Option("--source", "-s", help="Какой источник запускать, можно повторять."),
    ] = None,
    max_pages: Annotated[
        int | None,
        typer.Option("--max-pages", help="Лимит страниц списка. Перекрывает конфиг"),
    ] = None,
    fetch_details: Annotated[
        bool, typer.Option("--fetch-details", help="Ходить в карточки товара")
    ] = False,
    no_fetch_details: Annotated[
        bool, typer.Option("--no-fetch-details", help="Не ходить в карточки товара")
    ] = False,
    output_dir_flag: Annotated[
        Path | None, typer.Option("--output-dir", help="Куда писать таблицы. Пусто — из конфига")
    ] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="all, xlsx или csv")] = "all",
    diff_mode: Annotated[str, typer.Option("--diff", help="auto, on или off")] = "auto",
    previous: Annotated[
        Path | None,
        typer.Option("--previous", help="JSON предыдущего снимка для сравнения"),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Останавливаться на первом проблемном источнике"),
    ] = False,
    log_level: Annotated[
        str | None, typer.Option("--log-level", help="DEBUG, INFO, WARNING или ERROR")
    ] = None,
    csv_delimiter: Annotated[
        str, typer.Option("--csv-delimiter", help="Разделитель CSV, один символ")
    ] = ",",
    include_unchanged: Annotated[
        bool,
        typer.Option(
            "--include-unchanged",
            help="Писать на лист изменений строки без сдвига цены",
        ),
    ] = False,
) -> None:
    if fetch_details and no_fetch_details:
        typer.echo(
            "Укажите только один из флагов --fetch-details и --no-fetch-details",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        fmt_checked = _check_format(fmt)
        diff_checked = _check_diff_mode(diff_mode)
    except ConfigError as exc:
        _echo_config_error(exc)

    if max_pages is not None and max_pages < 1:
        typer.echo("max-pages должен быть >= 1", err=True)
        raise typer.Exit(code=2)

    if len(csv_delimiter) != 1:
        typer.echo("Разделитель CSV должен быть одним символом", err=True)
        raise typer.Exit(code=2)

    if previous is not None and not previous.is_file():
        typer.echo(f"Файл снимка не найден: {previous}", err=True)
        raise typer.Exit(code=2)

    try:
        config = load_config(config_path)
        level = _resolve_log_level(log_level, config)
        setup_logging(level, config.log_file)
        selected = select_sources(config, source_ids)
    except ConfigError as exc:
        _echo_config_error(exc)

    output_dir = _resolve_output_dir(config, output_dir_flag)

    for src in selected:
        eff_fetch = _effective_fetch_details(
            src, fetch_details=fetch_details, no_fetch_details=no_fetch_details
        )
        try:
            _validate_yaml_fetch(src, eff_fetch)
        except ConfigError as exc:
            _echo_config_error(exc)

    async def _execute() -> int:
        client = build_client(config)
        async with client:
            return await _run_sources(
                config,
                selected,
                max_pages=max_pages,
                fetch_details=fetch_details,
                no_fetch_details=no_fetch_details,
                output_dir=output_dir,
                fmt=fmt_checked,
                diff_mode=diff_checked,
                previous_path=previous,
                strict=strict,
                csv_delimiter=csv_delimiter,
                include_unchanged=include_unchanged,
                client=client,
            )

    try:
        failed = asyncio.run(_execute())
    except ConfigError as exc:
        _echo_config_error(exc)

    n = len(selected)
    typer.echo(f"Готово. Источников: {n}, с ошибками: {failed}.")
    raise typer.Exit(code=1 if failed > 0 else 0)


@app.command("export", help="Записать Excel и CSV из готового снимка, без сети.")
def export_cmd(
    snapshot: Annotated[Path, typer.Option("--snapshot", help="JSON снимка")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="all, xlsx или csv")] = "all",
    output_dir_flag: Annotated[
        Path, typer.Option("--output-dir", help="Куда писать таблицы")
    ] = Path("output"),
    diff_against: Annotated[
        Path | None,
        typer.Option("--diff-against", help="Второй снимок для листа изменений"),
    ] = None,
    include_unchanged: Annotated[
        bool,
        typer.Option("--include-unchanged", help="Писать строки без сдвига цены"),
    ] = False,
    csv_delimiter: Annotated[
        str, typer.Option("--csv-delimiter", help="Разделитель CSV, один символ")
    ] = ",",
) -> None:
    try:
        fmt_checked = _check_format(fmt)
    except ConfigError as exc:
        _echo_config_error(exc)

    if len(csv_delimiter) != 1:
        typer.echo("Разделитель CSV должен быть одним символом", err=True)
        raise typer.Exit(code=2)

    if not snapshot.is_file():
        typer.echo(f"Файл снимка не найден: {snapshot}", err=True)
        raise typer.Exit(code=2)

    if diff_against is not None and not diff_against.is_file():
        typer.echo(f"Файл снимка не найден: {diff_against}", err=True)
        raise typer.Exit(code=2)

    try:
        snap = load_snapshot(snapshot)
    except ExportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if output_dir_flag.is_absolute():
        output_dir = output_dir_flag.resolve()
    else:
        output_dir = (Path.cwd() / output_dir_flag).resolve()

    report: DiffReport | None = None
    comparison_line: str | None = None
    if diff_against is not None:
        try:
            prev = load_snapshot(diff_against)
        except ExportError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        report = diff_products(prev.products, snap.products)
        comparison_line = _format_comparison_line(diff_against, report)

    base_name = f"{snap.meta.source_id}-{snap.meta.run_id}"
    excel_path = output_dir / f"{base_name}.xlsx"
    csv_path = output_dir / f"{base_name}.csv"
    changes_path: Path | None = None
    exit_code = 0

    try:
        if fmt_checked in {"all", "xlsx"}:
            changes = report.changes if report is not None else None
            export_products_xlsx(
                snap.products,
                excel_path,
                changes=changes,
                include_unchanged=include_unchanged,
            )
            typer.echo(f"Excel: {_display(excel_path)}")

        if fmt_checked in {"all", "csv"}:
            export_products_csv(snap.products, csv_path, delimiter=csv_delimiter)
            typer.echo(f"CSV: {_display(csv_path)}")

        if fmt_checked == "csv" and report is not None:
            changes_path = output_dir / f"{base_name}-changes.xlsx"
            export_changes_xlsx(
                report.changes,
                changes_path,
                include_unchanged=include_unchanged,
            )
            typer.echo(f"Файл изменений: {_display(changes_path)}")
    except ExportError as exc:
        typer.echo(str(exc), err=True)
        exit_code = 1

    if comparison_line is not None:
        typer.echo(comparison_line)

    raise typer.Exit(code=exit_code)


def _filter_products_for_source(products: list[Product], source_id: str) -> list[Product]:
    kept = []
    for product in products:
        if product.source_id != source_id:
            logger.warning(
                "Товар с источником %s пропущен, ожидался %s",
                product.source_id,
                source_id,
            )
            continue
        kept.append(product)
    return kept


@app.command("diff", help="Сравнить два снимка и записать Excel с листом изменений.")
def diff_cmd(
    source_id: Annotated[str, typer.Option("--source", "-s", help="Идентификатор источника")],
    config_path: Annotated[Path, typer.Option("--config", "-c", help="Путь к YAML-конфигу")] = Path(
        "config.yaml"
    ),
    previous: Annotated[
        Path | None,
        typer.Option(
            "--previous",
            help="Более ранний снимок. Пусто — предпоследний файл источника",
        ),
    ] = None,
    current: Annotated[
        Path | None,
        typer.Option(
            "--current",
            help="Более поздний снимок. Пусто — последний файл источника",
        ),
    ] = None,
    output_path: Annotated[
        Path | None, typer.Option("--output", "-o", help="Куда писать xlsx")
    ] = None,
    include_unchanged: Annotated[
        bool,
        typer.Option("--include-unchanged", help="Писать строки без сдвига цены"),
    ] = False,
) -> None:
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _echo_config_error(exc)

    snaps = list_snapshots(config.runs_dir, source_id)

    if previous is None and current is None:
        pair = latest_pair(config.runs_dir, source_id)
        if pair is None:
            typer.echo(
                f"Недостаточно снимков для сравнения источника {source_id}: найдено {len(snaps)}",
                err=True,
            )
            raise typer.Exit(code=1)
        prev_path, curr_path = pair
    else:
        if current is None:
            if not snaps:
                typer.echo(
                    f"Недостаточно снимков для сравнения источника {source_id}: найдено 0",
                    err=True,
                )
                raise typer.Exit(code=1)
            curr_path = snaps[-1]
        else:
            if not current.is_file():
                typer.echo(f"Файл снимка не найден: {current}", err=True)
                raise typer.Exit(code=2)
            curr_path = current

        if previous is None:
            if len(snaps) < 2:
                msg = (
                    f"Недостаточно снимков для сравнения источника {source_id}: "
                    f"найдено {len(snaps)}"
                )
                typer.echo(msg, err=True)
                raise typer.Exit(code=1)
            prev_path = snaps[-2]
        else:
            if not previous.is_file():
                typer.echo(f"Файл снимка не найден: {previous}", err=True)
                raise typer.Exit(code=2)
            prev_path = previous

    try:
        prev_snap = load_snapshot(prev_path)
        curr_snap = load_snapshot(curr_path)
    except ExportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    for snap, path in ((prev_snap, prev_path), (curr_snap, curr_path)):
        if snap.meta.source_id != source_id:
            typer.echo(
                f"Снимок {path} относится к источнику {snap.meta.source_id}, ожидался {source_id}",
                err=True,
            )
            raise typer.Exit(code=2)

    prev_products = _filter_products_for_source(prev_snap.products, source_id)
    curr_products = _filter_products_for_source(curr_snap.products, source_id)
    report = diff_products(prev_products, curr_products)

    if output_path is None:
        out_dir = Path.cwd() / "output"
        out_name = (
            f"{source_id}-diff-{prev_snap.meta.run_id}-{curr_snap.meta.run_id}.xlsx"
        )
        output = out_dir / out_name
    elif output_path.is_absolute():
        output = output_path.resolve()
    else:
        output = (Path.cwd() / output_path).resolve()

    try:
        export_changes_xlsx(report.changes, output, include_unchanged=include_unchanged)
    except ExportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Сравнение {source_id}")
    typer.echo(f"Было: {_display(prev_path)} ({len(prev_products)} товаров)")
    typer.echo(f"Стало: {_display(curr_path)} ({len(curr_products)} товаров)")
    typer.echo(f"Новых: {report.new_count}")
    typer.echo(f"Пропавших: {report.removed_count}")
    typer.echo(f"Цена выросла: {report.up_count}")
    typer.echo(f"Цена упала: {report.down_count}")
    typer.echo(f"Без изменений: {report.unchanged_count}")
    typer.echo(f"Файл: {_display(output)}")
    raise typer.Exit(code=0)