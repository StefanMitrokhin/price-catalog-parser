# ruff: noqa: RUF001, RUF002
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from priceparser import __version__
from priceparser.errors import ConfigError
from priceparser.urls import is_http_url

_SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class FieldSpec(BaseModel):
    """Селектор одного поля карточки в YAML-источнике."""

    model_config = ConfigDict(extra="forbid")
    selector: str
    attr: str | None = None
    regex: str | None = None
    absolute: bool = False
    optional: bool = False
    count_selector: str | None = None

    @model_validator(mode="after")
    def _check_regex(self) -> FieldSpec:
        if self.regex is not None:
            try:
                re.compile(self.regex)
            except re.error as exc:
                raise ValueError(f"Некорректное regex: {exc}") from exc
        if not self.selector.strip():
            raise ValueError("Селектор не может быть пустым")
        return self


class PaginationSpec(BaseModel):
    """Пагинация списка в YAML-источнике."""

    model_config = ConfigDict(extra="forbid")
    next_selector: str
    attr: str = "href"
    absolute: bool = True

    @model_validator(mode="after")
    def _check_selector(self) -> PaginationSpec:
        if not self.next_selector.strip():
            raise ValueError("Селектор следующей страницы не может быть пустым")
        return self


class AvailabilityMapSpec(BaseModel):
    """Сопоставление текстов наличия."""

    model_config = ConfigDict(extra="forbid")
    in_stock: list[str]
    out_of_stock: list[str]


class YamlFields(BaseModel):
    """Набор полей карточки."""

    model_config = ConfigDict(extra="forbid")
    name: FieldSpec
    url: FieldSpec
    price: FieldSpec
    old_price: FieldSpec | None = None
    availability: FieldSpec | None = None
    category: FieldSpec | None = None
    rating: FieldSpec | None = None
    image_url: FieldSpec | None = None
    sku: FieldSpec | None = None

    @model_validator(mode="after")
    def _required_not_optional(self) -> YamlFields:
        for name in ("name", "url", "price"):
            spec: FieldSpec = getattr(self, name)
            if spec.optional:
                raise ValueError(f"Поле {name} не может быть optional")
        return self


class YamlSourceConfig(BaseModel):
    """Схема файла YAML-источника."""

    model_config = ConfigDict(extra="forbid")
    start_urls: list[str]
    currency: str
    category: str | None = None
    item: str
    fields: YamlFields
    pagination: PaginationSpec
    availability_map: AvailabilityMapSpec | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if not _CURRENCY_RE.match(v):
            raise ValueError("Валюта должна быть кодом из трёх заглавных букв")
        return v

    @model_validator(mode="after")
    def _check_urls_and_item(self) -> YamlSourceConfig:
        if not self.start_urls:
            raise ValueError("Нужен хотя бы один start_url")
        for url in self.start_urls:
            if not is_http_url(url):
                raise ValueError(f"Некорректный URL: {url}")
        if not self.item.strip():
            raise ValueError("Селектор карточки item не может быть пустым")
        return self


class SourceEntry(BaseModel):
    """Одна запись источника в главном конфиге."""

    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["books_toscrape", "yaml"]
    enabled: bool = True
    start_url: str | None = None
    currency: str | None = None
    categories: list[str] = Field(default_factory=list)
    max_pages: int | None = None
    fetch_details: bool = False
    config_file: str | None = None

    @field_validator("id")
    @classmethod
    def _id_pattern(cls, v: str) -> str:
        if not _SOURCE_ID_RE.match(v):
            raise ValueError(
                "id источника должен начинаться с латинской буквы и "
                "содержать до 32 символов [a-z0-9_-]"
            )
        return v

    @field_validator("max_pages")
    @classmethod
    def _max_pages(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("max_pages должен быть >= 1")
        return v

    @model_validator(mode="after")
    def _check_type_fields(self) -> SourceEntry:
        if self.type == "books_toscrape":
            if not self.start_url or not is_http_url(self.start_url):
                raise ValueError("Для books_toscrape нужен корректный start_url")
            if not self.currency or not _CURRENCY_RE.match(self.currency):
                raise ValueError("Для books_toscrape нужна валюта из трёх заглавных букв")
            if self.config_file:
                raise ValueError("У books_toscrape не должно быть config_file")
        elif self.type == "yaml":
            if not self.config_file or not self.config_file.strip():
                raise ValueError("Для yaml нужен config_file")
            if self.start_url:
                raise ValueError("У yaml-источника start_url задаётся в файле источника")
            if self.currency:
                raise ValueError("У yaml-источника currency задаётся в файле источника")
            if self.categories:
                raise ValueError("У yaml-источника categories задаются в файле источника")
            if self.fetch_details:
                raise ValueError("yaml-источник в этой версии не ходит в карточки")
        return self


class AppConfig(BaseModel):
    """Схема главного YAML-конфига."""

    model_config = ConfigDict(extra="forbid")
    user_agent: str = (
        f"price-catalog-parser/{__version__} "
        "(educational parser; +https://github.com/StefanMitrokhin/price-catalog-parser)"
    )
    timeout_seconds: float = 20.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    retry_statuses: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])
    concurrency: int = 4
    delay_seconds: float = 1.0
    respect_robots: bool = True
    max_pages: int | None = None
    fetch_details: bool = False
    output_dir: str = "output"
    runs_dir: str = "data/runs"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_file: str | None = None
    sources: list[SourceEntry]

    @field_validator("user_agent")
    @classmethod
    def _user_agent(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("user_agent не может быть пустым")
        if len(s) > 300:
            raise ValueError("user_agent длиннее 300 символов")
        if not s.isascii():
            raise ValueError("user_agent должен содержать только ASCII-символы (заголовок HTTP)")
        return s

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout(cls, v: float) -> float:
        if not (0 < v <= 120):
            raise ValueError("timeout_seconds должен быть в диапазоне (0, 120]")
        return v

    @field_validator("max_retries")
    @classmethod
    def _max_retries(cls, v: int) -> int:
        if not (1 <= v <= 8):
            raise ValueError("max_retries должен быть от 1 до 8")
        return v

    @field_validator("backoff_base_seconds")
    @classmethod
    def _backoff_base(cls, v: float) -> float:
        if v < 0 or v > 120:
            raise ValueError("backoff_base_seconds должен быть от 0 до 120")
        return v

    @field_validator("backoff_max_seconds")
    @classmethod
    def _backoff_max(cls, v: float) -> float:
        if v < 0 or v > 120:
            raise ValueError("backoff_max_seconds должен быть от 0 до 120")
        return v

    @field_validator("concurrency")
    @classmethod
    def _concurrency(cls, v: int) -> int:
        if not (1 <= v <= 16):
            raise ValueError("concurrency должен быть от 1 до 16")
        return v

    @field_validator("delay_seconds")
    @classmethod
    def _delay(cls, v: float) -> float:
        if not (0 <= v <= 60):
            raise ValueError("delay_seconds должен быть от 0 до 60")
        return v

    @field_validator("retry_statuses")
    @classmethod
    def _retry_statuses(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("retry_statuses не может быть пустым")
        for status in v:
            if not (400 <= status <= 599):
                raise ValueError(f"Статус повтора должен быть 400-599, получено {status}")
        return v

    @field_validator("max_pages")
    @classmethod
    def _max_pages(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("max_pages должен быть >= 1")
        return v

    @model_validator(mode="after")
    def _backoff_order(self) -> AppConfig:
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ValueError("backoff_max_seconds не может быть меньше backoff_base_seconds")
        return self

    @model_validator(mode="after")
    def _sources_nonempty_and_unique(self) -> AppConfig:
        if not self.sources:
            raise ValueError("Нужен хотя бы один источник")
        seen: set[str] = set()
        for entry in self.sources:
            if entry.id in seen:
                raise ValueError(f"Повтор id источника: {entry.id}")
            seen.add(entry.id)
        return self


@dataclass(frozen=True)
class HttpSettings:
    """Параметры HTTP-клиента."""

    user_agent: str
    timeout_seconds: float
    max_retries: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    retry_statuses: tuple[int, ...]
    concurrency: int
    delay_seconds: float
    respect_robots: bool


@dataclass(frozen=True)
class ResolvedSource:
    """Источник после разрешения путей и наследования полей."""

    id: str
    type: str
    enabled: bool
    start_url: str | None
    currency: str | None
    categories: tuple[str, ...]
    max_pages: int | None
    fetch_details: bool
    yaml_path: Path | None
    yaml_spec: YamlSourceConfig | None


@dataclass(frozen=True)
class ResolvedConfig:
    """Готовый конфиг для CLI и парсеров."""

    http: HttpSettings
    output_dir: Path
    runs_dir: Path
    log_level: str
    log_file: Path | None
    sources: tuple[ResolvedSource, ...]
    config_path: Path


def _resolve_path(base: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p.resolve()
    return (base / value).resolve()


def _load_yaml_source(yaml_path: Path) -> YamlSourceConfig:
    if not yaml_path.is_file():
        raise ConfigError(f"Файл источника не найден: {yaml_path}")
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Ошибка YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Корень файла источника должен быть словарём")
    try:
        return YamlSourceConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Некорректный файл источника: {exc}") from exc


def load_config(path: Path) -> ResolvedConfig:
    """Прочитать YAML, проверить схему, подгрузить YAML источников, разрешить пути."""
    if not path.is_file():
        raise ConfigError(f"Файл конфига не найден: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Ошибка YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Корень конфига должен быть словарём")

    try:
        app = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Некорректный конфиг: {exc}") from exc

    base = path.parent.resolve()
    output_dir = _resolve_path(base, app.output_dir)
    runs_dir = _resolve_path(base, app.runs_dir)
    log_file = None if app.log_file is None else _resolve_path(base, app.log_file)

    http = HttpSettings(
        user_agent=app.user_agent,
        timeout_seconds=app.timeout_seconds,
        max_retries=app.max_retries,
        backoff_base_seconds=app.backoff_base_seconds,
        backoff_max_seconds=app.backoff_max_seconds,
        retry_statuses=tuple(app.retry_statuses),
        concurrency=app.concurrency,
        delay_seconds=app.delay_seconds,
        respect_robots=app.respect_robots,
    )

    resolved_sources: list[ResolvedSource] = []
    for entry in app.sources:
        max_pages = entry.max_pages if "max_pages" in entry.model_fields_set else app.max_pages
        fetch_details = (
            entry.fetch_details if "fetch_details" in entry.model_fields_set else app.fetch_details
        )

        yaml_path: Path | None = None
        yaml_spec: YamlSourceConfig | None = None
        if entry.type == "yaml":
            yaml_path = (base / cast(str, entry.config_file)).resolve()
            yaml_spec = _load_yaml_source(yaml_path)

        resolved_sources.append(
            ResolvedSource(
                id=entry.id,
                type=entry.type,
                enabled=entry.enabled,
                start_url=entry.start_url,
                currency=entry.currency,
                categories=tuple(entry.categories),
                max_pages=max_pages,
                fetch_details=fetch_details,
                yaml_path=yaml_path,
                yaml_spec=yaml_spec,
            )
        )

    return ResolvedConfig(
        http=http,
        output_dir=output_dir,
        runs_dir=runs_dir,
        log_level=app.log_level,
        log_file=log_file,
        sources=tuple(resolved_sources),
        config_path=path.resolve(),
    )


def select_sources(
    config: ResolvedConfig,
    only_ids: list[str] | None,
) -> tuple[ResolvedSource, ...]:
    """only_ids None или пуст: все enabled, в порядке файла.

    Иначе: ровно эти id, в порядке аргументов, даже если enabled false.
    Неизвестный id -> ConfigError (это код выхода 2).
    Повтор одного id в аргументах -> ConfigError.
    """
    if not only_ids:
        return tuple(s for s in config.sources if s.enabled)

    by_id = {s.id: s for s in config.sources}
    seen: set[str] = set()
    chosen: list[ResolvedSource] = []
    for sid in only_ids:
        if sid in seen:
            raise ConfigError(f"Повтор источника в аргументах: {sid}")
        seen.add(sid)
        if sid not in by_id:
            raise ConfigError(f"Неизвестный источник: {sid}")
        chosen.append(by_id[sid])
    return tuple(chosen)
