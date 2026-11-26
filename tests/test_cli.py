# ruff: noqa: RUF001
from __future__ import annotations

import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from tests.conftest import (
    BOOKS_HIMALAYAS,
    BOOKS_HOME,
    LAPTOPS_PAGE1,
    read_fixture,
)
from tests.fakes import FakeClient, make_product
from tests.test_crawl import _books_client
from typer.testing import CliRunner

from priceparser import cli
from priceparser.errors import FetchError, RobotsDenied
from priceparser.models import RunMeta, RunSnapshot
from priceparser.storage import save_snapshot

_REPO = Path(__file__).resolve().parents[1]
_RUNNER = CliRunner()
_FIXED = datetime(2026, 11, 25, 22, 15, tzinfo=UTC)


def _offline_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    shutil.copy(_REPO / "sources/webscraper_laptops.yaml", src / "webscraper_laptops.yaml")
    cfg.write_text(
        f"""
user_agent: test-agent/1.0
output_dir: output
runs_dir: data/runs
log_file: run.log
sources:
  - id: books
    type: books_toscrape
    enabled: true
    start_url: {BOOKS_HOME}
    currency: GBP
    categories: [Travel]
    max_pages: 1
    fetch_details: true
  - id: laptops
    type: yaml
    config_file: sources/webscraper_laptops.yaml
    max_pages: 1
""",
        encoding="utf-8",
    )
    return cfg


def _patch_offline_client(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = _books_client()
    monkeypatch.setattr(cli, "build_client", lambda _cfg: client)
    return client


def test_version() -> None:
    import subprocess
    import sys

    result = _RUNNER.invoke(cli.app, ["version"])
    assert result.exit_code == 0
    assert "price-catalog-parser 0.1.0" in result.stdout
    result2 = _RUNNER.invoke(cli.app, ["--version"])
    assert result2.exit_code == 0
    assert "price-catalog-parser 0.1.0" in result2.stdout
    proc = subprocess.run(
        [sys.executable, "-m", "priceparser", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "0.1.0" in proc.stdout


def test_help() -> None:
    result = _RUNNER.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "Парсер каталогов и цен" in result.stdout
    assert _RUNNER.invoke(cli.app, ["run", "--help"]).exit_code == 0
    assert _RUNNER.invoke(cli.app, ["export", "--help"]).exit_code == 0
    assert _RUNNER.invoke(cli.app, ["diff", "--help"]).exit_code == 0


def test_validate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "sources"
    src.mkdir()
    shutil.copy(_REPO / "sources/webscraper_laptops.yaml", src / "webscraper_laptops.yaml")
    shutil.copy(_REPO / "config.example.yaml", tmp_path / "config.example.yaml")
    result = _RUNNER.invoke(cli.app, ["validate", "--config", "config.example.yaml"])
    assert result.exit_code == 0
    assert "Конфиг корректен: 2 источников" in result.stdout
    from priceparser.config import load_config

    assert cli.build_client(load_config(tmp_path / "config.example.yaml")) is not None


def test_validate_bad_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.yaml"
    bad.write_text("", encoding="utf-8")
    result = _RUNNER.invoke(cli.app, ["validate", "--config", str(bad)])
    assert result.exit_code == 2
    ua = tmp_path / "ua.yaml"
    ua.write_text(
        """
user_agent: "bot/1 (кириллица)"
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    bad_ua = _RUNNER.invoke(cli.app, ["validate", "--config", str(ua)])
    assert bad_ua.exit_code == 2
    assert "ASCII" in bad_ua.stderr + bad_ua.stdout
    cfg = _offline_config(tmp_path)
    dup = _RUNNER.invoke(
        cli.app, ["run", "--config", str(cfg), "--source", "books", "--source", "books"]
    )
    assert dup.exit_code == 2
    fmt = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--format", "badfmt"])
    assert fmt.exit_code == 2
    diff = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--diff", "maybe"])
    assert diff.exit_code == 2
    log = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--log-level", "nope"])
    assert log.exit_code == 2
    yaml_fd = _RUNNER.invoke(
        cli.app,
        ["run", "--config", str(cfg), "--source", "laptops", "--fetch-details"],
    )
    assert yaml_fd.exit_code == 2
    delim = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--csv-delimiter", ";;"])
    assert delim.exit_code == 2


def test_sources_lists_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    shutil.copy(_REPO / "config.example.yaml", tmp_path / "config.example.yaml")
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    shutil.copy(_REPO / "sources/webscraper_laptops.yaml", src / "webscraper_laptops.yaml")
    result = _RUNNER.invoke(cli.app, ["sources", "--config", "config.example.yaml"])
    assert result.exit_code == 0
    assert "books" in result.stdout
    assert "laptops" in result.stdout
    assert "books_toscrape" in result.stdout


def test_run_books_offline_writes_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    client = _patch_offline_client(monkeypatch)
    client.pages[LAPTOPS_PAGE1] = read_fixture("webscraper_laptops_page1.html")
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        [
            "run",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--output-dir",
            str(tmp_path / "custom_out"),
        ],
    )
    assert result.exit_code == 0
    json_files = list((tmp_path / "data/runs/books").glob("*.json"))
    assert len(json_files) == 1
    xlsx_files = list((tmp_path / "custom_out").glob("books-*.xlsx"))
    csv_files = list((tmp_path / "custom_out").glob("books-*.csv"))
    assert len(xlsx_files) == 1
    assert len(csv_files) == 1
    wb = load_workbook(xlsx_files[0])
    assert "Товары" in wb.sheetnames
    assert wb["Товары"].max_row >= 3
    assert "Источник: books" in result.stdout
    assert "Ошибки страниц: 0" in result.stdout
    assert "Сравнение: предыдущий снимок не найден" in result.stdout
    assert "Готово. Источников: 1, с ошибками: 0." in result.stdout
    assert csv_files[0].read_bytes()[:3] == b"\xef\xbb\xbf"
    assert (tmp_path / "run.log").is_file()
    extra = _RUNNER.invoke(
        cli.app,
        [
            "run",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--max-pages",
            "2",
            "--fetch-details",
        ],
    )
    assert extra.exit_code == 0
    lap = _RUNNER.invoke(
        cli.app, ["run", "--config", str(cfg), "--source", "laptops", "--format", "xlsx"]
    )
    assert lap.exit_code == 0
    assert list((tmp_path / "output").glob("laptops-*.xlsx"))
    off = _RUNNER.invoke(
        cli.app,
        [
            "run",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--diff",
            "off",
            "--no-fetch-details",
        ],
    )
    assert off.exit_code == 0

    class BoomClient(FakeClient):
        async def get_text(self, url: str, *, check_robots: bool = True) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "build_client", lambda _cfg: BoomClient())
    boom = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--source", "books"])
    assert boom.exit_code == 1

    from priceparser.errors import ExportError

    monkeypatch.setattr(
        cli,
        "export_products_xlsx",
        lambda *a, **k: (_ for _ in ()).throw(ExportError("fail")),
    )
    monkeypatch.setattr(cli, "build_client", lambda _cfg: _books_client())
    export_fail = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--source", "books"])
    assert export_fail.exit_code == 1

    from priceparser.errors import ExportError as ExportErr

    monkeypatch.setattr(cli, "build_client", lambda _cfg: _books_client())
    monkeypatch.setattr(
        cli,
        "save_snapshot",
        lambda *a, **k: (_ for _ in ()).throw(ExportErr("snap")),
    )
    snap_fail = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--source", "books"])
    assert snap_fail.exit_code == 1


def test_run_diff_auto_adds_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    _patch_offline_client(monkeypatch)
    cfg = _offline_config(tmp_path)
    runs = tmp_path / "data/runs/books"
    runs.mkdir(parents=True)
    prev_products = [
        make_product(
            name="It's Only the Himalayas",
            url=BOOKS_HIMALAYAS,
            sku="c0ffee0000000001",
            price=Decimal("40.00"),
            currency="GBP",
        ),
        make_product(
            name="Removed Book",
            url="https://books.toscrape.com/gone",
            price=Decimal("1.00"),
            currency="GBP",
        ),
    ]
    meta = RunMeta(
        run_id="20261125T220000Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=len(prev_products),
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path=str(cfg),
    )
    prev_path = runs / "20261125T220000Z.json"
    save_snapshot(prev_path, RunSnapshot(meta=meta, products=prev_products))
    result = _RUNNER.invoke(
        cli.app,
        [
            "run",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--include-unchanged",
            "--previous",
            str(prev_path),
        ],
    )
    assert result.exit_code == 0
    xlsx = next((tmp_path / "output").glob("books-*.xlsx"))
    wb = load_workbook(xlsx)
    assert "Изменения" in wb.sheetnames
    labels = {wb["Изменения"].cell(row=r, column=1).value for r in range(2, 20)}
    assert "Пропавший" in labels
    assert "цена выросла" in result.stdout.casefold() or "Цена выросла" in str(labels)
    assert "пропавших" in result.stdout.casefold()


def test_run_diff_on_without_previous_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    _patch_offline_client(monkeypatch)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        [
            "run",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--diff",
            "on",
        ],
    )
    assert result.exit_code == 1
    assert "Сравнение: ошибка, предыдущий снимок не найден" in result.stdout
    assert list((tmp_path / "data/runs/books").glob("*.json"))


def test_run_unknown_source_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--source", "nope"])
    assert result.exit_code == 2
    assert not list((tmp_path / "output").glob("*"))
    bad_pages = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--max-pages", "0"])
    assert bad_pages.exit_code == 2
    bad_snap = _RUNNER.invoke(cli.app, ["export", "--snapshot", str(tmp_path / "nope.json")])
    assert bad_snap.exit_code == 2
    thin = _RUNNER.invoke(cli.app, ["diff", "--config", str(cfg), "--source", "books"])
    assert thin.exit_code == 1


def test_export_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    monkeypatch.chdir(tmp_path)

    def boom(_cfg):
        raise AssertionError("build_client must not run for export")

    monkeypatch.setattr(cli, "build_client", boom)
    product = make_product()
    older = make_product(
        url="https://example.com/old",
        price=Decimal("8.00"),
    )
    meta = RunMeta(
        run_id="20261125T221500Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=1,
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path="cfg.yaml",
    )
    older_meta = RunMeta(
        run_id="20261125T220000Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=1,
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path="cfg.yaml",
    )
    snap_path = tmp_path / "snap.json"
    prev_path = tmp_path / "prev.json"
    save_snapshot(snap_path, RunSnapshot(meta=meta, products=[product]))
    save_snapshot(prev_path, RunSnapshot(meta=older_meta, products=[older]))
    result = _RUNNER.invoke(
        cli.app,
        ["export", "--snapshot", str(snap_path), "--format", "csv", "--output-dir", "out"],
    )
    assert result.exit_code == 0
    assert list((tmp_path / "out").glob("*.csv"))
    result_all = _RUNNER.invoke(
        cli.app,
        [
            "export",
            "--snapshot",
            str(snap_path),
            "--diff-against",
            str(prev_path),
            "--format",
            "all",
            "--output-dir",
            "out2",
            "--include-unchanged",
        ],
    )
    assert result_all.exit_code == 0
    assert list((tmp_path / "out2").glob("*.xlsx"))
    assert "Сравнение:" in result_all.stdout
    bad_delim = _RUNNER.invoke(
        cli.app,
        ["export", "--snapshot", str(snap_path), "--csv-delimiter", "ab"],
    )
    assert bad_delim.exit_code == 2
    missing_prev = _RUNNER.invoke(
        cli.app,
        [
            "export",
            "--snapshot",
            str(snap_path),
            "--diff-against",
            str(tmp_path / "missing.json"),
        ],
    )
    assert missing_prev.exit_code == 2
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    bad_export = _RUNNER.invoke(
        cli.app,
        ["export", "--snapshot", str(corrupt)],
    )
    assert bad_export.exit_code == 1


def test_diff_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    runs = tmp_path / "data/runs/books"
    runs.mkdir(parents=True)
    for rid in ("20261125T221500Z", "20261125T221501Z"):
        meta = RunMeta(
            run_id=rid,
            source_id="books",
            started_at=fixed_now,
            finished_at=fixed_now,
            product_count=1,
            pages_fetched=1,
            detail_pages_fetched=0,
            page_errors=0,
            config_path=str(cfg),
        )
        p = make_product(url=f"https://example.com/{rid}", price=Decimal("10.00"))
        save_snapshot(runs / f"{rid}.json", RunSnapshot(meta=meta, products=[p]))
    result = _RUNNER.invoke(cli.app, ["diff", "--config", str(cfg), "--source", "books"])
    assert result.exit_code == 0
    explicit = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--previous",
            str(runs / "20261125T221500Z.json"),
            "--current",
            str(runs / "20261125T221501Z.json"),
        ],
    )
    assert explicit.exit_code == 0
    result = explicit
    assert result.exit_code == 0
    wrong = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "laptops",
            "--previous",
            str(runs / "20261125T221500Z.json"),
            "--current",
            str(runs / "20261125T221501Z.json"),
        ],
    )
    assert wrong.exit_code == 2
    custom = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--output",
            "custom-diff.xlsx",
        ],
    )
    assert custom.exit_code == 0
    assert (tmp_path / "custom-diff.xlsx").is_file()
    bad_snap = runs / "broken.json"
    bad_snap.write_text("{", encoding="utf-8")
    bad_diff = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--current",
            str(bad_snap),
        ],
    )
    assert bad_diff.exit_code == 1
    missing_prev = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--previous",
            str(tmp_path / "nope.json"),
        ],
    )
    assert missing_prev.exit_code == 2
    assert "Новых:" in result.stdout
    assert "Файл:" in result.stdout
    xlsx = next((tmp_path / "output").glob("books-diff-*.xlsx"))
    wb = load_workbook(xlsx)
    assert "Изменения" in wb.sheetnames
    (runs / "20261125T221501Z.json").unlink()
    thin_prev = _RUNNER.invoke(
        cli.app,
        [
            "diff",
            "--config",
            str(cfg),
            "--source",
            "books",
            "--current",
            str(runs / "20261125T221500Z.json"),
        ],
    )
    assert thin_prev.exit_code == 1


def test_strict_stops_second_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    src = tmp_path / "sources"
    src.mkdir()
    shutil.copy(_REPO / "sources/webscraper_laptops.yaml", src / "webscraper_laptops.yaml")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
user_agent: test-agent/1.0
output_dir: output
runs_dir: data/runs
sources:
  - id: books
    type: books_toscrape
    start_url: {BOOKS_HOME}
    currency: GBP
    categories: [Cookbook]
    max_pages: 1
  - id: laptops
    type: yaml
    config_file: sources/webscraper_laptops.yaml
    max_pages: 1
""",
        encoding="utf-8",
    )
    client = FakeClient(pages={BOOKS_HOME: read_fixture("books_home.html")})
    monkeypatch.setattr(cli, "build_client", lambda _cfg: client)
    result = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--strict"])
    assert result.exit_code == 1
    assert not any("webscraper.io" in u for u in client.calls)
    assert "с ошибками: 1" in result.stdout
    assert "Готово. Источников: 2, с ошибками: 1." in result.stdout


def test_format_csv_writes_changes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    _patch_offline_client(monkeypatch)
    cfg = _offline_config(tmp_path)
    runs = tmp_path / "data/runs/books"
    runs.mkdir(parents=True)
    prev = make_product(
        name="It's Only the Himalayas",
        url=BOOKS_HIMALAYAS,
        sku="c0ffee0000000001",
        price=Decimal("40.00"),
        currency="GBP",
    )
    meta = RunMeta(
        run_id="20261125T220000Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=1,
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path=str(cfg),
    )
    save_snapshot(runs / "20261125T220000Z.json", RunSnapshot(meta=meta, products=[prev]))
    result = _RUNNER.invoke(
        cli.app, ["run", "--config", str(cfg), "--source", "books", "--format", "csv"]
    )
    assert result.exit_code == 0
    product_xlsx = [
        p for p in (tmp_path / "output").glob("books-*.xlsx") if "-changes" not in p.name
    ]
    assert not product_xlsx
    assert list((tmp_path / "output").glob("books-*.csv"))
    assert list((tmp_path / "output").glob("*-changes.xlsx"))
    assert "Файл изменений:" in result.stdout


def test_both_fetch_flags_exit_2() -> None:
    result = _RUNNER.invoke(cli.app, ["run", "--fetch-details", "--no-fetch-details"])
    assert result.exit_code == 2
    assert "один" in (result.stderr + result.stdout).casefold()


def test_run_logs_source_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_offline_client(monkeypatch)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(cli.app, ["run", "--config", str(cfg), "--source", "books"])
    assert result.exit_code == 0
    log_text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "Источник books: старт" in log_text


def test_run_counts_one_failed_source_with_page_errors_and_diff_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)

    class FailCollectClient(FakeClient):
        async def get_text(self, url: str, *, check_robots: bool = True) -> str:
            raise FetchError(url, "down", status=503)

    monkeypatch.setattr(cli, "build_client", lambda _cfg: FailCollectClient())
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        ["run", "--config", str(cfg), "--source", "books", "--diff", "on"],
    )
    assert result.exit_code == 1
    assert "Готово. Источников: 1, с ошибками: 1." in result.stdout


def test_export_xlsx_only_and_diff_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    monkeypatch.chdir(tmp_path)

    def boom(_cfg):
        raise AssertionError("build_client must not run for export")

    monkeypatch.setattr(cli, "build_client", boom)
    product = make_product()
    meta = RunMeta(
        run_id="20261125T221500Z",
        source_id="books",
        started_at=fixed_now,
        finished_at=fixed_now,
        product_count=1,
        pages_fetched=1,
        detail_pages_fetched=0,
        page_errors=0,
        config_path="cfg.yaml",
    )
    snap_path = tmp_path / "snap.json"
    save_snapshot(snap_path, RunSnapshot(meta=meta, products=[product]))
    result = _RUNNER.invoke(
        cli.app,
        ["export", "--snapshot", str(snap_path), "--format", "xlsx", "--output-dir", "onlyxlsx"],
    )
    assert result.exit_code == 0
    assert "Excel:" in result.stdout
    assert not list((tmp_path / "onlyxlsx").glob("*.csv"))
    bad_fmt = _RUNNER.invoke(
        cli.app,
        ["export", "--snapshot", str(snap_path), "--format", "nope"],
    )
    assert bad_fmt.exit_code == 2


def test_run_invalid_log_level_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        ["run", "--config", str(cfg), "--source", "books", "--log-level", "VERBOSE"],
    )
    assert result.exit_code == 2


def test_run_yaml_fetch_details_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        ["run", "--config", str(cfg), "--source", "laptops", "--fetch-details"],
    )
    assert result.exit_code == 2
    assert "yaml" in (result.stderr + result.stdout).casefold()


def test_run_strict_fails_source_with_page_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    import priceparser.clock as clock_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clock_mod, "utc_now", lambda: fixed_now)
    client = _books_client()
    client.errors[BOOKS_HIMALAYAS] = RobotsDenied(BOOKS_HIMALAYAS)
    monkeypatch.setattr(cli, "build_client", lambda _cfg: client)
    cfg = _offline_config(tmp_path)
    result = _RUNNER.invoke(
        cli.app,
        ["run", "--config", str(cfg), "--source", "books", "--strict"],
    )
    assert result.exit_code == 1
    assert "Ошибки страниц: 1" in result.stdout
    assert "Готово. Источников: 1, с ошибками: 1." in result.stdout


def test_diff_export_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    from priceparser.errors import ExportError

    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    runs = tmp_path / "data/runs/books"
    runs.mkdir(parents=True)
    for rid in ("20261125T221500Z", "20261125T221501Z"):
        meta = RunMeta(
            run_id=rid,
            source_id="books",
            started_at=fixed_now,
            finished_at=fixed_now,
            product_count=1,
            pages_fetched=1,
            detail_pages_fetched=0,
            page_errors=0,
            config_path=str(cfg),
        )
        p = make_product(url=f"https://example.com/{rid}", price=Decimal("10.00"))
        save_snapshot(runs / f"{rid}.json", RunSnapshot(meta=meta, products=[p]))
    monkeypatch.setattr(
        cli,
        "export_changes_xlsx",
        lambda *a, **k: (_ for _ in ()).throw(ExportError("disk full")),
    )
    result = _RUNNER.invoke(cli.app, ["diff", "--config", str(cfg), "--source", "books"])
    assert result.exit_code == 1
    assert "disk full" in result.stderr + result.stdout


def test_diff_filters_products_from_other_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_now: datetime
) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = _offline_config(tmp_path)
    runs = tmp_path / "data/runs/books"
    runs.mkdir(parents=True)
    books = make_product(source_id="books")
    laptops = make_product(
        source_id="laptops",
        url="https://example.com/laptop",
        name="Laptop",
    )
    for rid, products in (
        ("20261125T221500Z", [books]),
        ("20261125T221501Z", [books, laptops]),
    ):
        meta = RunMeta(
            run_id=rid,
            source_id="books",
            started_at=fixed_now,
            finished_at=fixed_now,
            product_count=len(products),
            pages_fetched=1,
            detail_pages_fetched=0,
            page_errors=0,
            config_path=str(cfg),
        )
        save_snapshot(runs / f"{rid}.json", RunSnapshot(meta=meta, products=products))
    result = _RUNNER.invoke(cli.app, ["diff", "--config", str(cfg), "--source", "books"])
    assert result.exit_code == 0


def test_sources_bad_config_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.yaml"
    bad.write_text("sources: []", encoding="utf-8")
    result = _RUNNER.invoke(cli.app, ["sources", "--config", str(bad)])
    assert result.exit_code == 2
