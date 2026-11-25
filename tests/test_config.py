from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from priceparser.config import ResolvedSource, load_config, select_sources
from priceparser.errors import ConfigError
from priceparser.sources.registry import create_source

_REPO = Path(__file__).resolve().parents[1]


def _minimal_yaml_source(tmp_path: Path) -> Path:
    src = tmp_path / "sources"
    src.mkdir()
    shutil.copy(_REPO / "sources/webscraper_laptops.yaml", src / "webscraper_laptops.yaml")
    return src


def test_load_example_resolved_paths(tmp_path: Path) -> None:
    _minimal_yaml_source(tmp_path)
    cfg_path = tmp_path / "config.example.yaml"
    shutil.copy(_REPO / "config.example.yaml", cfg_path)
    resolved = load_config(cfg_path)
    assert len(resolved.sources) == 2
    books = next(s for s in resolved.sources if s.id == "books")
    assert books.max_pages == 1
    assert books.fetch_details is True
    laptops = next(s for s in resolved.sources if s.id == "laptops")
    assert laptops.fetch_details is False
    assert resolved.output_dir == (tmp_path / "output").resolve()
    picked = select_sources(resolved, ["laptops"])
    assert len(picked) == 1
    assert picked[0].id == "laptops"
    for source in resolved.sources:
        adapter = create_source(
            source,
            max_pages=source.max_pages,
            fetch_details=source.fetch_details,
        )
        assert adapter.source_id == source.id
    bogus = ResolvedSource(
        id="bogus",
        type="bogus",
        enabled=True,
        start_url=None,
        currency=None,
        categories=(),
        max_pages=1,
        fetch_details=False,
        yaml_path=None,
        yaml_spec=None,
    )
    with pytest.raises(ConfigError):
        create_source(bogus, max_pages=1, fetch_details=False)
    books_bad = ResolvedSource(
        id="books",
        type="books_toscrape",
        enabled=True,
        start_url=None,
        currency="GBP",
        categories=(),
        max_pages=1,
        fetch_details=False,
        yaml_path=None,
        yaml_spec=None,
    )
    with pytest.raises(ConfigError):
        create_source(books_bad, max_pages=1, fetch_details=False)
    yaml_bad = ResolvedSource(
        id="yaml",
        type="yaml",
        enabled=True,
        start_url=None,
        currency=None,
        categories=(),
        max_pages=1,
        fetch_details=False,
        yaml_path=None,
        yaml_spec=None,
    )
    with pytest.raises(ConfigError):
        create_source(yaml_bad, max_pages=1, fetch_details=False)


def test_paths_are_relative_to_config_dir(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    cfg = nested / "config.yaml"
    cfg.write_text(
        """
user_agent: test-agent/1.0
output_dir: out
runs_dir: data/runs
log_file: logs/app.log
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    resolved = load_config(cfg)
    assert resolved.output_dir == (nested / "out").resolve()
    assert resolved.log_file == (nested / "logs/app.log").resolve()

    abs_cfg = nested / "abs.yaml"
    abs_cfg.write_text(
        """
user_agent: test-agent
output_dir: /var/output/abs
runs_dir: /var/runs/abs
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    abs_resolved = load_config(abs_cfg)
    assert str(abs_resolved.output_dir).endswith("/var/output/abs")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("[[", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
    base = """
user_agent: test-agent
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
"""
    bad_cases = [
        "concurrency: 0\n",
        "concurrency: 17\n",
        "delay_seconds: 61\n",
        "max_retries: 0\n",
        "timeout_seconds: 0\n",
        "retry_statuses: []\n",
        "sources: []\n",
        "user_agent: '   '\n",
        "max_pages: 0\n",
        "backoff_max_seconds: -1\n",
        "backoff_base_seconds: 200\n",
        "retry_statuses: [300]\n",
        "log_level: NOPE\n",
    ]
    for fragment in bad_cases:
        p = tmp_path / f"bad_{fragment.split(':')[0]}.yaml"
        p.write_text(base + fragment, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)


def test_duplicate_source_id(tmp_path: Path) -> None:
    path = tmp_path / "dup.yaml"
    path.write_text(
        """
user_agent: test-agent
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)

    ok = tmp_path / "ok.yaml"
    ok.write_text(
        """
user_agent: test-agent
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    resolved = load_config(ok)
    with pytest.raises(ConfigError):
        select_sources(resolved, ["books", "books"])


def test_unknown_type(tmp_path: Path) -> None:
    path = tmp_path / "type.yaml"
    path.write_text(
        """
user_agent: test-agent
sources:
  - id: shop
    type: shop
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_books_requires_currency(tmp_path: Path) -> None:
    path = tmp_path / "curr.yaml"
    path.write_text(
        """
user_agent: test-agent
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)

    bad_id = tmp_path / "bad_id.yaml"
    bad_id.write_text(
        """
user_agent: test-agent
sources:
  - id: 9bad
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(bad_id)


def test_yaml_rejects_fetch_details(tmp_path: Path) -> None:
    src = _minimal_yaml_source(tmp_path)
    path = tmp_path / "yaml_fd.yaml"
    path.write_text(
        f"""
user_agent: test-agent
sources:
  - id: laptops
    type: yaml
    config_file: {src.name}/webscraper_laptops.yaml
    fetch_details: true
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "карточки" in str(exc.value).casefold()


def test_yaml_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    path.write_text(
        """
user_agent: test-agent
sources:
  - id: laptops
    type: yaml
    config_file: sources/nope.yaml
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)

    src = _minimal_yaml_source(tmp_path)
    bad_regex = src / "bad_regex.yaml"
    bad_regex.write_text(
        """
start_urls: ["https://example.com/list"]
currency: USD
item: div.item
fields:
  name:
    selector: a
  url:
    selector: a
    attr: href
  price:
    selector: span
    regex: "["
pagination:
  next_selector: a.next
availability_map:
  in_stock: [available]
  out_of_stock: [gone]
""",
        encoding="utf-8",
    )
    cfg = tmp_path / "bad_regex_cfg.yaml"
    cfg.write_text(
        f"""
user_agent: test-agent
sources:
  - id: bad
    type: yaml
    config_file: {src.name}/bad_regex.yaml
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_extra_field_forbidden(tmp_path: Path) -> None:
    path = tmp_path / "extra.yaml"
    path.write_text(
        """
user_agent: test-agent
proxy: 1
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_source_max_pages_null_means_unlimited(tmp_path: Path) -> None:
    path = tmp_path / "null_mp.yaml"
    path.write_text(
        """
user_agent: test-agent
max_pages: 2
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
    max_pages: null
""",
        encoding="utf-8",
    )
    resolved = load_config(path)
    books = resolved.sources[0]
    assert books.max_pages is None


def test_omitted_max_pages_inherits(tmp_path: Path) -> None:
    path = tmp_path / "inherit.yaml"
    path.write_text(
        """
user_agent: test-agent
max_pages: 2
sources:
  - id: books
    type: books_toscrape
    start_url: https://books.toscrape.com/
    currency: GBP
""",
        encoding="utf-8",
    )
    resolved = load_config(path)
    assert resolved.sources[0].max_pages == 2
