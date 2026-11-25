# План реализации: price-catalog-parser

Документ — единственная спецификация. Реализатор (другая модель) переносит её в код **дословно**. Если в этом файле что-то зафиксировано, это не обсуждается и не «улучшается» по ходу. Если какой-то крайний случай ниже не описан, выбирается вариант из раздела 20 «Решения по умолчанию», а не новый дизайн.

Объём специально средний: один пакет, два учебных источника, CLI, Excel/CSV, снимки прогонов, сравнение цен. Веб-интерфейса, базы данных и обхода защит нет.

Проверено 2026-11-25 по живой разметке:

- `https://books.toscrape.com/` — карточка `article.product_pod`, цена `p.price_color` вида `£51.77`, рейтинг классом `star-rating Three`, наличие `p.instock.availability`, следующая страница `li.next a`. Карточка товара: таблица `table.table-striped`, строка `UPC`, крошки `ul.breadcrumb` (`Home / Books / Poetry / название`). `robots.txt` отвечает **404**.
- `https://webscraper.io/test-sites/e-commerce/static/computers/laptops` — карточка `div.card.thumbnail`, цена `span[itemprop=price]` вида `$416.99`, ссылка `a.title` с атрибутом `title`, рейтинг `p[data-rating]`, картинка `img[itemprop=image]`, следующая страница `a[rel=next]`.
- `https://webscraper.io/robots.txt` запрещает только `/test-sites/product/`, `/test-sites/pagination/`, `/test-sites/pagination*?page=`, `/test-sites/scroll/`, `/test-sites/load-more/`. Путь `/test-sites/e-commerce/` **не запрещён**. Его и парсим. Запрещённые пути не добавлять в конфиг.

Автор портфолио: **Стефан Митрохин**. Живой логин GitHub на 2026-11-25 — **StefanMitrokhin** (`https://github.com/StefanMitrokhin`). Имя `Stephanchik` из постановки задачи отдаёт 404, поэтому все ссылки на профиль и репозиторий ведут на `https://github.com/StefanMitrokhin/price-catalog-parser`. Строку copyright в `LICENSE` не переписывать: там остаётся `2026 Stephanchik`.

---

## 1. Цели и не-цели

### 1.1. Цели

Сделать проект, который выглядит как типичный фриланс-заказ «спарсить цены конкурентов в Excel»:

1. Собирать с учебных публичных каталогов товары с полями: название, цена, старая цена, наличие, категория, рейтинг, URL, URL картинки, артикул (SKU), если он есть на сайте.
2. Выгружать их в `.xlsx` (оформленная шапка, автофильтр, ширины колонок, замороженная шапка, цена числом) и в CSV (UTF-8 с BOM, чтобы Excel открыл кириллицу в шапке).
3. Уметь сравнить два прогона одного источника и выгрузить лист «Изменения»: новые, пропавшие, цена выросла, цена упала.
4. Ходить по страницам пагинации вежливо: лимит параллелизма, пауза, таймаут, повторы с экспоненциальной паузой, свой User-Agent, уважение `robots.txt`.
5. Подключать новый сайт одним из двух способов, без правки ядра:
   - маленький класс-адаптер, зарегистрированный в реестре;
   - YAML-файл с CSS-селекторами.
6. Дать CLI и YAML-конфиг. В комплекте два готовых источника: класс `books_toscrape` и YAML для ноутбуков webscraper.io.
7. Покрыть парсинг и выгрузку тестами на сохранённом HTML. Сети в тестах нет.
8. Python 3.11+, аннотации, ruff, mypy, pytest, GitHub Actions на 3.11 и 3.12, Dockerfile.

Готовый результат для заказчика описан текстом `README.md` в разделе 17. Этот текст копируется в корень репозитория без правок.

### 1.2. Вне объёма (не делать)

- Сайты, которые не являются учебными демо для парсинга. В репозиторий не добавлять магазины, маркетплейсы, страницы с логином.
- Обход капчи, прокси, ротация IP, подмена отпечатков браузера, авторизация, cookies с сессией.
- Рендер JavaScript (Playwright, Selenium). Вариант webscraper.io `ajax` не поддерживается: он требует JS.
- База данных, ORM, очереди, веб-API, Telegram-бот, GUI.
- Планировщик внутри процесса (APScheduler, cron-демон, цикл `while True: sleep`). Расписание — только инструкция в README: системный cron или `docker run` по cron.
- Поиск «похожих» товаров между разными источниками. Сравнение только внутри одного `source_id` и только по ключу из раздела 6.4.
- Нормализация валют и конвертация по курсу. Числа сравниваются как есть, разные валюты помечаются флагом.
- Старая цена не выдумывается. Если на странице её нет, поле пустое. На books.toscrape.com старой цены нет. В фикстуре YAML она есть специально, чтобы селектор был покрыт тестом; на живом webscraper.io её сейчас нет, и в боевом прогоне колонка будет пустой.
- Лог не пишет HTML страниц и тела ответов.
- Не коммитить `output/`, снимки прогонов, `.xlsx`, виртуальные окружения.
- Не менять файл `LICENSE`. Текст MIT остаётся как есть, copyright `2026 Stephanchik`.
- Не добавлять lock-файл (`uv.lock`, `poetry.lock`, `requirements.txt`). Версии зафиксированы в `pyproject.toml` через `==`.
- Не подключать Rich, pandas, Scrapy, BeautifulSoup-замены, tenacity. Повторы и пауза написаны в `http_client.py`, чтобы тест управлял сном.
- Не поднимать покрытие ради пустых тестов «импортнулся модуль». Список тестов в разделе 14 полный: других тестовых функций не добавлять. Вспомогательные функции внутри тестовых файлов можно.

### 1.3. Как выглядит демонстрационный прогон

`config.example.yaml` ограничивает books категорией Travel и одной страницей каталога с заходом в карточки (там SKU), а laptops — одной страницей списка. При паузе 1 секунда это короткий вежливый прогон, а не выкачивание всех 1000 книг.

---

## 2. Принятые решения

Эти решения закрывают развилки. Реализатор их не переоткрывает.

| Тема | Решение |
| --- | --- |
| CLI | Typer 0.29.2. Вывод человеку — обычный текст через `typer.echo`, не Rich-таблицы. |
| Параллелизм | asyncio + `httpx.AsyncClient`. Потоки не использовать. Источники идут строго по очереди. Страницы одного списка тоже по очереди, потому что ссылка «дальше» известна только после разбора. Карточки товара одного источника качаются параллельно, но через тот же семафор и ту же паузу на хост. |
| Модели | Pydantic 2.14. `Product` и снимки сериализуются в JSON. Деньги — `Decimal`, в JSON строка с двумя знаками. |
| HTML | BeautifulSoup + парсер `lxml`. |
| Конфиг | Один YAML. Относительные пути считаются от каталога файла конфига, не от текущей рабочей директории. |
| Новый сайт | Либо класс в `sources/` и строка в реестре, либо YAML и запись `type: yaml`. Ядро (`crawl`, экспорт, CLI) не ветвится по сайтам. |
| Ключ товара | Если SKU непустой — `sku:{source_id}:{sku в нижнем регистре}`. Иначе `url:{source_id}:{нормализованный URL}`. Смешивать ключи между прогонами нельзя: если в одном снимке SKU есть, а в другом нет, diff покажет «пропал» и «новый». README это прямо говорит. |
| Дедуп | Первое вхождение ключа побеждает, остальные отбрасываются. |
| robots.txt | По умолчанию включено. 404 и 410 — всё разрешено. Другой HTTP-ошибке и сетевой ошибке на `robots.txt` — весь origin запрещён (fail closed). `respect_robots: false` разрешает всё и файл не качает. |
| Повторы | `max_retries: 3` означает **три попытки всего**, не «три повтора сверху». |
| Коды выхода | `0` успех, `1` ошибка источника или обязательного сравнения, `2` ошибка конфига или аргументов. |
| Шапка таблиц | Русский язык. Данные как на сайте (названия книг на английском). |
| CSV | Разделитель запятая. Флаг `--csv-delimiter` для русской локали Excel (`;`). |
| Кодировка CSV | `utf-8-sig` (BOM), перевод строки `\r\n`. |
| Excel | openpyxl. Цена — `float` с форматом `#,##0.00`. Это осознанное ограничение: суммы до копеек в диапазоне float64 для этого проекта достаточны. |
| Время | Один `scraped_at` на весь прогон источника, UTC, берётся в начале `collect`. `run_id` строится из этого же момента. |
| Часы в коде | Только `priceparser.clock.utc_now()`, вызов через модуль `clock`, чтобы тест мог сделать `monkeypatch`. |
| Лимит страниц | Считает успешно скачанные страницы **списков**. Страница обнаружения категорий books и карточки товара в лимит не входят. |
| Наследование лимита | Если у источника ключ `max_pages` / `fetch_details` присутствует в YAML, берётся он (в том числе `max_pages: null` = без лимита). Если ключ опущен, берётся значение верхнего уровня конфига. CLI `--max-pages` перекрывает оба. |
| mypy | `strict = true` по пакету `priceparser`. |
| Покрытие | Ветка включена, порог 90% по пакету `priceparser`. |
| CI | Ubuntu, Python 3.11 и 3.12. Docker в CI не собирать. |
| Версия | `0.1.0` в `priceparser.__version__`. |
| Ссылки на GitHub | Профиль и репозиторий: `StefanMitrokhin`. Логин `Stephanchik` на 2026-11-25 отвечает 404. Copyright в LICENSE не трогать. |

---

## 3. Дерево файлов

После реализации в репозитории есть ровно эти пути плюс уже существующие `LICENSE` и `.gitignore`. Лишних модулей, `src/priceparser/py.typed` (добавить: пакет типизирован, файл пустой) и скрытых утилит нет.

`src/priceparser/py.typed` — пустой файл, чтобы пакет был типизирован по PEP 561.

```
.
├── .github/
│   └── workflows/
│       └── ci.yml
├── .dockerignore
├── .gitignore                         # существующий файл, только дописать блок из раздела 16
├── Dockerfile
├── LICENSE                            # не изменять
├── README.md                          # заменить целиком текстом из раздела 17
├── config.example.yaml
├── pyproject.toml
├── data/
│   └── runs/
│       └── .gitkeep                   # пустой файл
├── docs/
│   └── PLAN.md                        # этот документ, при реализации не править
├── sources/
│   └── webscraper_laptops.yaml
├── src/
│   └── priceparser/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── clock.py
│       ├── config.py
│       ├── crawl.py
│       ├── dedup.py
│       ├── diff.py
│       ├── errors.py
│       ├── export_csv.py
│       ├── export_xlsx.py
│       ├── html_utils.py
│       ├── http_client.py
│       ├── logging_setup.py
│       ├── models.py
│       ├── prices.py
│       ├── robots.py
│       ├── storage.py
│       ├── urls.py
│       ├── py.typed
│       └── sources/
│           ├── __init__.py
│           ├── base.py
│           ├── books_toscrape.py
│           ├── registry.py
│           └── yaml_source.py
└── tests/
    ├── conftest.py
    ├── fakes.py
    ├── fixtures/
    │   ├── books_home.html
    │   ├── books_travel.html
    │   ├── books_travel_page2.html
    │   ├── books_detail_attic.html
    │   ├── books_detail_himalayas.html
    │   ├── webscraper_laptops_page1.html
    │   ├── webscraper_laptops_page2.html
    │   └── robots_disallow_private.txt
    ├── test_books_parser.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_crawl.py
    ├── test_dedup.py
    ├── test_diff.py
    ├── test_export_csv.py
    ├── test_export_xlsx.py
    ├── test_http_client.py
    ├── test_prices.py
    ├── test_robots.py
    ├── test_storage.py
    ├── test_urls.py
    └── test_yaml_source.py
```

Каталог `output/` создаётся в рантайме, в git его нет.

В каждом модуле пакета первая строка кода:

```python
from __future__ import annotations
```

Импорты только абсолютные: `from priceparser.models import Product`. Логгер: `logger = logging.getLogger(__name__)`. Публичные функции и классы — с однострочным docstring на русском. Комментарии только там, где этот план помечает неочевидный инвариант.

`tests/__init__.py` не создавать.

---

## 4. Зависимости и `pyproject.toml`

Версии ниже — актуальные релизы PyPI на 2026-11-25. Пиновать через `==`. Не обновлять «до совместимых».

Прямые зависимости выполнения:

| Пакет | Версия | Зачем |
| --- | --- | --- |
| typer | 0.29.2 | CLI |
| httpx | 0.28.1 | HTTP, в тестах `MockTransport` |
| beautifulsoup4 | 4.15.0 | Разбор HTML |
| lxml | 6.1.3 | Парсер для BeautifulSoup |
| openpyxl | 3.1.5 | xlsx |
| pyyaml | 6.0.4 | Конфиг, `yaml.safe_load` |
| pydantic | 2.14.4 | Модели |

Зависимости разработки (`[dev]`):

| Пакет | Версия |
| --- | --- |
| ruff | 0.17.6 |
| pytest | 9.2.0 |
| pytest-cov | 7.1.0 |
| pytest-asyncio | 1.5.0 |
| mypy | 2.4.1 |

Сборка: hatchling 1.33.0. Transitive-зависимости (click, idna, и т.д.) не пиновать.

Файл `pyproject.toml` целиком:

```toml
[build-system]
requires = ["hatchling==1.33.0"]
build-backend = "hatchling.build"

[project]
name = "price-catalog-parser"
version = "0.1.0"
description = "Парсер цен и каталогов с выгрузкой в Excel и CSV"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Стефан Митрохин" }]
keywords = ["scraping", "prices", "excel", "csv", "portfolio"]
classifiers = [
  "Development Status :: 4 - Beta",
  "Environment :: Console",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Typing :: Typed",
]
dependencies = [
  "typer==0.29.2",
  "httpx==0.28.1",
  "beautifulsoup4==4.15.0",
  "lxml==6.1.3",
  "openpyxl==3.1.5",
  "pyyaml==6.0.4",
  "pydantic==2.14.4",
]

[project.optional-dependencies]
dev = [
  "ruff==0.17.6",
  "pytest==9.2.0",
  "pytest-cov==7.1.0",
  "pytest-asyncio==1.5.0",
  "mypy==2.4.1",
]

[project.urls]
Homepage = "https://github.com/StefanMitrokhin/price-catalog-parser"
Repository = "https://github.com/StefanMitrokhin/price-catalog-parser"

[project.scripts]
priceparser = "priceparser.cli:app"

[tool.hatch.build.targets.wheel]
only-include = ["priceparser"]

[tool.hatch.build.targets.wheel.sources]
"src" = ""

[tool.hatch.build.targets.sdist]
include = ["src/priceparser", "README.md", "LICENSE", "pyproject.toml"]

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"src/priceparser/cli.py" = ["B008"]

[tool.ruff.lint.isort]
known-first-party = ["priceparser"]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
addopts = "-q --strict-markers"

[tool.coverage.run]
branch = true
source = ["priceparser"]

[tool.coverage.report]
fail_under = 90
show_missing = true
exclude_lines = [
  "pragma: no cover",
  "if __name__ == .__main__.:",
  "if TYPE_CHECKING:",
]

[tool.mypy]
python_version = "3.11"
strict = true
packages = ["priceparser"]
mypy_path = "src"
warn_unused_ignores = true
disallow_any_generics = true

[[tool.mypy.overrides]]
module = ["bs4.*", "lxml.*", "yaml.*", "openpyxl.*"]
ignore_missing_imports = true
```

Проверка после установки: `python -c "import priceparser; print(priceparser.__version__)"` печатает `0.1.0`, а `priceparser.__file__` лежит внутри `src/priceparser`. Если hatchling не подхватывает src-layout с конфигом выше, правится **только** секция `[tool.hatch.build.targets.wheel*]`, пока импорт не станет таким. Код пакета из-за этого не переносится.

`__init__.py`:

```python
from __future__ import annotations

__version__ = "0.1.0"
```

Других реэкспортов нет.

`__main__.py`:

```python
from __future__ import annotations

from priceparser.cli import app

if __name__ == "__main__":
    app()
```

Команды `priceparser` и `python -m priceparser` ведут себя одинаково.

---

## 5. Модель данных

Модуль `priceparser/models.py`. Все модели: `model_config = ConfigDict(frozen=True, extra="forbid")`.

### 5.1. Перечисления

```python
class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class ChangeKind(StrEnum):
    NEW = "new"
    REMOVED = "removed"
    PRICE_UP = "price_up"
    PRICE_DOWN = "price_down"
    UNCHANGED = "unchanged"
```

`StrEnum` из `enum` (Python 3.11). Значения в JSON — эти строки.

Русские подписи (константы модуля `models.py`, их импортируют экспорт и CLI):

```python
AVAILABILITY_RU: dict[Availability, str] = {
    Availability.IN_STOCK: "В наличии",
    Availability.OUT_OF_STOCK: "Нет в наличии",
    Availability.UNKNOWN: "Неизвестно",
}

CHANGE_KIND_RU: dict[ChangeKind, str] = {
    ChangeKind.NEW: "Новый",
    ChangeKind.REMOVED: "Пропавший",
    ChangeKind.PRICE_UP: "Цена выросла",
    ChangeKind.PRICE_DOWN: "Цена упала",
    ChangeKind.UNCHANGED: "Без изменений",
}

CHANGE_KIND_FONT: dict[ChangeKind, str] = {
    ChangeKind.NEW: "196F3D",
    ChangeKind.REMOVED: "922B21",
    ChangeKind.PRICE_UP: "C0392B",
    ChangeKind.PRICE_DOWN: "1A7F37",
    ChangeKind.UNCHANGED: "666666",
}
```

Цвета — RGB без `#`, для шрифта openpyxl.

### 5.2. `Product`

Поля в этом порядке:

| Поле | Тип | Правило |
| --- | --- | --- |
| source_id | str | как в конфиге, непустой |
| name | str | `min_length=1`, обрезать пробелы по краям до валидации |
| url | str | абсолютный `http` или `https` |
| price | Decimal | `>= 0`, всегда квантован до `0.01` HALF_UP |
| currency | str | ровно 3 заглавные латинские буквы |
| old_price | Decimal \| None | то же квантование, `>= 0`, может быть меньше текущей цены — не менять местами |
| availability | Availability | по умолчанию `UNKNOWN` |
| category | str \| None | пустая строка превращается в None |
| rating | float \| None | если задан, `0 <= rating <= 5`. Сравнение с допуском не нужно: наружу пишется `float` |
| image_url | str \| None | если задан, абсолютный http(s), иначе None |
| sku | str \| None | пустая строка превращается в None, иначе `strip` |
| scraped_at | datetime | только timezone-aware. Naive datetime — ошибка валидации |

Сериализация денег — строка. Валидатор `mode="before"` принимает `Decimal`, `int`, `float`, `str` и делает `Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. `float` в файлах снимков не писать; валидатор терпит его только на чтение.

```python
def _money_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.01')):.2f}"
```

Повесить `@field_serializer("price", "old_price")` с этой функцией. `scraped_at` уходит в JSON как ISO 8601 с секундами и смещением, например `2026-11-25T22:15:00+00:00`. Для этого достаточно стандартного JSON-режима Pydantic 2, если в объект кладётся aware datetime. В тесте круглый путь проверяет именно такую строку. Если Pydantic добавит микросекунды, перед сохранением заменить `scraped_at` на `scraped_at.replace(microsecond=0)`.

Метод не добавлять `identity_key` на модель: ключ считает `urls.product_key`, чтобы правило жило в одном месте.

### 5.3. `ProductDraft`

Обычный `@dataclass` (не pydantic), в `models.py`. Те же поля, кроме `scraped_at`. Значения по умолчанию: `old_price=None`, `availability=Availability.UNKNOWN`, `category=None`, `rating=None`, `image_url=None`, `sku=None`.

```python
def to_product(self, scraped_at: datetime) -> Product:
    """Собрать Product. Валидация pydantic здесь и есть проверка черновика."""
```

### 5.4. `ListingParseResult`

`@dataclass(frozen=True)` в `models.py`:

```python
@dataclass(frozen=True)
class ListingParseResult:
    products: list[ProductDraft]
    next_url: str | None
```

### 5.5. `CollectResult`

`@dataclass(frozen=True)` в `models.py`:

```python
@dataclass(frozen=True)
class CollectResult:
    products: list[Product]       # уже без дублей, в порядке первого появления
    pages_fetched: int            # успешные страницы списков
    detail_pages_fetched: int     # успешные карточки
    page_errors: int
    duplicates_dropped: int
```

`products` отсортированы **не** здесь. Сортировка только при экспорте. Снимок хранит порядок обхода.

### 5.6. `RunMeta` и `RunSnapshot`

```python
class RunMeta(BaseModel):
    run_id: str
    source_id: str
    started_at: datetime
    finished_at: datetime
    product_count: int            # равно len(products) на момент записи
    pages_fetched: int
    detail_pages_fetched: int
    page_errors: int
    config_path: str              # абсолютный путь строкой


class RunSnapshot(BaseModel):
    meta: RunMeta
    products: list[Product]
```

Оба frozen, extra forbid. `product_count` при загрузке может разойтись с длиной списка: читатель доверяет списку и пишет warning `product_count не совпадает с числом товаров`. Это делает `storage.load_snapshot`.

### 5.7. `PriceChange` и `DiffReport`

```python
class PriceChange(BaseModel):
    kind: ChangeKind
    identity_key: str
    name: str
    url: str
    sku: str | None
    category: str | None
    old_price: Decimal | None
    new_price: Decimal | None
    delta: Decimal | None
    delta_pct: Decimal | None
    currency: str | None
    currency_mismatch: bool
    source_id: str
```

Деньги сериализуются так же, как у `Product` (на случай отладки). В xlsx они всё равно пишутся числом.

```python
@dataclass(frozen=True)
class DiffReport:
    changes: list[PriceChange]   # включая UNCHANGED, уже отсортированные
    new_count: int
    removed_count: int
    up_count: int
    down_count: int
    unchanged_count: int
```

Смысл полей изменения:

| kind | name, url, sku, category | old_price | new_price | delta | currency |
| --- | --- | --- | --- | --- | --- |
| NEW | из текущего | None | текущая цена | None | валюта текущего |
| REMOVED | из предыдущего | прошлая цена | None | None | валюта предыдущего |
| PRICE_UP, PRICE_DOWN, UNCHANGED | из текущего | прошлая | текущая | `money(new-old)` | валюта текущего |

`currency_mismatch` истинен только у трёх видов с двумя ценами, когда `previous.currency != current.currency`. У NEW и REMOVED всегда `False`. `delta_pct` — процентные пункты, не доля: рост с 50 до 55 даёт `Decimal("10.00")`. Если старая цена равна 0, `delta_pct` равен None, даже когда обе цены 0. При обеих нулевых ценах kind = `UNCHANGED`, delta = `0.00`.

Сортировка `changes`: ранг вида NEW=0, REMOVED=1, PRICE_UP=2, PRICE_DOWN=3, UNCHANGED=4, затем `name.casefold()`, затем `url`.

---

## 6. Алгоритмы, которые копируются без изменения поведения

### 6.1. Деньги и наличие — `prices.py`

Константа `MONEY = Decimal("0.01")`.

Нормативная функция разбора цены. Перенести как есть.

```python
def parse_price(raw: str) -> Decimal:
    """Вытащить цену из текста узла.

    Правила разделителей:
    - есть и запятая, и точка: последний из них — десятичный, второй — группы разрядов;
    - только запятая: если после неё 1 или 2 цифры, это десятичная запятая, иначе группы разрядов;
    - одна точка и ровно 3 цифры после неё: это группа разрядов (1.149 -> 1149), не десятичная дробь;
    - одна точка и 1, 2 или больше 3 цифр после неё: десятичная точка, длинная дробь квантуется HALF_UP;
    - несколько точек: последняя десятичная, если после неё 1 или 2 цифры, иначе все точки — группы разрядов.
    Пробелы и неразрывные пробелы между разрядами удаляются. Отрицательные значения — ParseError.
    """
    cleaned = re.sub(r"[^\d,.\s\u00A0]", "", raw)
    cleaned = cleaned.replace("\u00a0", "").replace(" ", "")
    if not cleaned or not re.search(r"\d", cleaned):
        raise ParseError(f"нет цены в {raw!r}")

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        whole, frac = cleaned.rsplit(",", 1)
        if whole.count(",") == 0 and 1 <= len(frac) <= 2 and frac.isdigit():
            cleaned = whole.replace(",", "") + "." + frac
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        head, frac = cleaned.rsplit(".", 1)
        if 1 <= len(frac) <= 2 and frac.isdigit():
            cleaned = head.replace(".", "") + "." + frac
        else:
            cleaned = cleaned.replace(".", "")
    elif cleaned.count(".") == 1:
        whole, frac = cleaned.split(".")
        if len(frac) == 3 and frac.isdigit():
            cleaned = whole + frac

    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParseError(f"нет цены в {raw!r}") from exc
    if value < 0:
        raise ParseError(f"отрицательная цена {raw!r}")
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)
```

Обязательные примеры (они же тесты):

| Вход | Результат |
| --- | --- |
| `£51.77` | `51.77` |
| `$416.99` | `416.99` |
| `$1,149.99` | `1149.99` |
| `1 149,99` | `1149.99` |
| `51,77` | `51.77` |
| `1.149` | `1149.00` |
| `1.149,50` | `1149.50` |
| `51.775` | `51.78` |
| `0` | `0.00` |
| `""`, `"free"`, `"-1.00"` | `ParseError` |

Наличие:

```python
DEFAULT_OUT_PHRASES: tuple[str, ...] = (
    "out of stock",
    "not in stock",
    "sold out",
    "unavailable",
    "нет в наличии",
)
DEFAULT_IN_PHRASES: tuple[str, ...] = (
    "in stock",
    "available",
    "в наличии",
)


def parse_availability(
    text: str | None,
    *,
    out_phrases: tuple[str, ...] = DEFAULT_OUT_PHRASES,
    in_phrases: tuple[str, ...] = DEFAULT_IN_PHRASES,
) -> Availability:
    """Сначала фразы отсутствия, потом наличия: подстрока, casefold, пробелы схлопнуты."""
    if text is None:
        return Availability.UNKNOWN
    norm = " ".join(text.casefold().split())
    if not norm:
        return Availability.UNKNOWN
    if any(phrase in norm for phrase in out_phrases):
        return Availability.OUT_OF_STOCK
    if any(phrase in norm for phrase in in_phrases):
        return Availability.IN_STOCK
    return Availability.UNKNOWN
```

Порядок проверки обязателен: `"not in stock"` содержит `"in stock"`, но это отсутствие.

Рейтинг:

```python
def parse_rating(raw: str | None) -> float | None:
    """Число 0..5 включительно. Пусто -> None. Вне диапазона -> None и warning, не исключение."""
    if raw is None:
        return None
    text = raw.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        logger.warning("Непонятный рейтинг: %s", raw)
        return None
    if value < 0 or value > 5:
        logger.warning("Рейтинг вне шкалы 0..5: %s", raw)
        return None
    return value
```

Книжная словесная шкала живёт в адаптере books, не здесь.

### 6.2. URL — `urls.py`

```python
def normalize_url(url: str) -> str:
    """Ключ для дедупа и diff. Фрагмент убирается, хост в нижнем регистре,
    порты 80 и 443 убираются, хвостовой слэш у пути убирается кроме корня `/`,
    query-параметры сортируются, userinfo отбрасывается.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query_pairs.sort()
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))


def product_key(source_id: str, url: str, sku: str | None) -> str:
    if sku is not None and sku.strip():
        return f"sku:{source_id}:{sku.strip().casefold()}"
    return f"url:{source_id}:{normalize_url(url)}"


def is_http_url(url: str) -> bool:
    parts = urlsplit(url.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc)
```

`product_key` для `Product` — тонкая обёртка `product_key(p.source_id, p.url, p.sku)` с тем же именем нельзя (перегрузка). Сделать две функции:

- `product_key_parts(source_id: str, url: str, sku: str | None) -> str` — реализация;
- `product_key(product: Product) -> str` и `draft_key(draft: ProductDraft) -> str` вызывают её.

Так mypy спокоен, а правило одно.

### 6.3. Дедуп — `dedup.py`

```python
def dedupe_drafts(drafts: list[ProductDraft]) -> tuple[list[ProductDraft], int]:
    """Оставить первое вхождение draft_key. Вернуть (уникальные, сколько отброшено)."""
```

Порядок сохранившихся элементов — порядок первого появления. Лог на INFO, только если отброшено больше нуля: `Отброшено дублей: N`. Сам `dedupe_drafts` логирует. Повторно по готовым `Product` не дедуплицировать.

### 6.4. Сравнение — `diff.py`

```python
def diff_products(previous: list[Product], current: list[Product]) -> DiffReport:
    """Сравнить уже дедуплицированные списки одного источника."""
```

Алгоритм:

1. `prev_map`: идти по `previous`, ключ `product_key`. При повторе ключа оставить первый и залогировать warning `Повтор ключа в предыдущем снимке: {key}`. То же для `curr_map`.
2. Для каждого ключа текущего снимка в порядке `current`:
   - нет в предыдущем → `NEW`;
   - есть: если `cur.price > prev.price` → `PRICE_UP`; если `<` → `PRICE_DOWN`; иначе `UNCHANGED`. Сравнение только `Decimal`, не float.
   - `delta = money(cur.price - prev.price)` для этих трёх видов, включая `0.00` у UNCHANGED.
   - `delta_pct`: если `prev.price == 0`, None; иначе `(delta / prev.price * Decimal(100)).quantize(MONEY, ROUND_HALF_UP)`.
   - при разной валюте warning один раз на товар: `Разные валюты у {key}: {prev} и {cur}` и `currency_mismatch=True`.
3. Для ключей предыдущего снимка, которых нет в текущем, в порядке `previous` добавить `REMOVED`.
4. Отсортировать как в разделе 5.7 и посчитать пять счётчиков по полному списку, включая UNCHANGED.

Фильтр «не писать без изменений» делает экспорт, не `diff_products`.

### 6.5. Обход списков — `crawl.py`

```python
async def walk_listings(
    client: PageFetcher,
    start_urls: list[str],
    parse: Callable[[str, str], ListingParseResult],
    max_pages: int | None,
) -> tuple[list[ProductDraft], int, int]:
    """Вернуть (черновики, pages_fetched, page_errors).

    Цепочки start_urls идут по очереди. Внутри цепочки следующая ссылка
    берётся из parse(). Уже виденный URL (нормализованный) не качается второй раз:
    цепочка на нём останавливается. max_pages — общий потолок успешных страниц
    на весь вызов. Неуспешный URL увеличивает page_errors и обрывает только
    текущую цепочку. Следующий start_url всё ещё обрабатывается, если потолок не взят.
    """
```

Поведение по шагам для каждого URL, который собираемся качать:

1. Если `max_pages` не None и `pages_fetched >= max_pages`: залогировать warning `Достигнут max_pages={max_pages}, остальные страницы пропущены` один раз (флаг `warned`), выйти из всей функции, вернуть накопленное.
2. `norm = normalize_url(url)`. Если `norm` уже в `seen`, остановить текущую цепочку (не ошибка).
3. Добавить `norm` в `seen` до запроса, чтобы цикл по `next` на ту же страницу не зациклился.
4. `html = await client.get_text(url)`.
5. `RobotsDenied`: warning `Пропуск {url}: запрещено robots.txt`, `page_errors += 1`, оборвать цепочку.
6. `FetchError`: error `Не удалось загрузить {url}: {message}`, `page_errors += 1`, оборвать цепочку.
7. Успех: `pages_fetched += 1`. Вызвать `parse`. Если `parse` бросил `ParseError` или любое другое исключение: error с URL и текстом, `page_errors += 1`, черновики этой страницы не добавлять, оборвать цепочку.
8. Иначе добавить `result.products` и, если `result.next_url`, поставить его следующим в этой цепочке (не в общую очередь других start_urls).

Пустой список товаров при успешном разборе — не ошибка страницы. Warning: `На {url} не найдено товаров`.

---

## 7. Конфиги

### 7.1. `config.example.yaml`

Файл в корне, копируется пользователем в `config.yaml` (этот второй файл в git не кладётся; в `.gitignore` его можно не добавлять, в README сказано не коммитить свой рабочий конфиг, если там появятся правки). Сам пример коммитится.

```yaml
user_agent: "price-catalog-parser/0.1 (+https://github.com/StefanMitrokhin/price-catalog-parser; учебный парсер, только demo-сайты)"
timeout_seconds: 20
max_retries: 3
backoff_base_seconds: 0.5
backoff_max_seconds: 8
retry_statuses: [429, 500, 502, 503, 504]
concurrency: 4
delay_seconds: 1.0
respect_robots: true
max_pages: 2
fetch_details: false
output_dir: output
runs_dir: data/runs
log_level: INFO
log_file: null

sources:
  - id: books
    type: books_toscrape
    enabled: true
    start_url: "https://books.toscrape.com/"
    currency: GBP
    categories: ["Travel"]
    max_pages: 1
    fetch_details: true

  - id: laptops
    type: yaml
    enabled: true
    config_file: sources/webscraper_laptops.yaml
    max_pages: 1
```

`currency: GBP` без кавычек YAML прочитает как строку. Это нормально.

### 7.2. `sources/webscraper_laptops.yaml`

```yaml
start_urls:
  - "https://webscraper.io/test-sites/e-commerce/static/computers/laptops"
currency: USD
category: Laptops
item: "div.card.thumbnail"
fields:
  name:
    selector: "a.title"
    attr: title
  url:
    selector: "a.title"
    attr: href
    absolute: true
  price:
    selector: "span[itemprop=price]"
  old_price:
    selector: "span.old-price"
    optional: true
  availability:
    selector: "span.availability"
    optional: true
  image_url:
    selector: "img"
    attr: src
    absolute: true
    optional: true
  sku:
    selector: "[itemprop=sku]"
    optional: true
  rating:
    selector: "p[data-rating]"
    attr: data-rating
    count_selector: "span.ws-icon-star"
    optional: true
  category:
    selector: "span.category"
    optional: true
pagination:
  next_selector: "a[rel=next]"
  attr: href
  absolute: true
availability_map:
  in_stock:
    - "in stock"
    - "available"
    - "в наличии"
  out_of_stock:
    - "out of stock"
    - "not in stock"
    - "sold out"
    - "unavailable"
    - "нет в наличии"
```

На живом сайте нет `span.old-price`, `span.availability`, `[itemprop=sku]`, `span.category`. Селекторы optional, прогон не падает, категория берётся из строкового поля `category: Laptops`. Рейтинг берётся из `data-rating`.

### 7.3. Загрузка — `config.py`

Модели конфига тоже pydantic, `extra="forbid"`. Они **не** frozen на время чтения `model_fields_set`, затем из них собирается неизменяемый результат.

```python
class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    attr: str | None = None
    regex: str | None = None
    absolute: bool = False
    optional: bool = False
    count_selector: str | None = None


class PaginationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next_selector: str
    attr: str = "href"
    absolute: bool = True


class AvailabilityMapSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_stock: list[str]
    out_of_stock: list[str]


class YamlFields(BaseModel):
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


class YamlSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_urls: list[str]
    currency: str
    category: str | None = None
    item: str
    fields: YamlFields
    pagination: PaginationSpec
    availability_map: AvailabilityMapSpec | None = None


class SourceEntry(BaseModel):
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


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_agent: str = (
        "price-catalog-parser/0.1 "
        "(+https://github.com/StefanMitrokhin/price-catalog-parser; "
        "учебный парсер, только demo-сайты)"
    )
    timeout_seconds: float = 20.0
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 8.0
    retry_statuses: list[int] = Field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )
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
```

Проверки `AppConfig` (через `field_validator` / `model_validator`, текст ошибки на русском, оборачивается в `ConfigError`):

- `user_agent` непустой после `strip`, длина `<= 300`;
- `timeout_seconds` в диапазоне `(0, 120]`;
- `max_retries` в `1..8`;
- `backoff_base_seconds >= 0`, `backoff_max_seconds >= backoff_base_seconds`, оба `<= 120`;
- `concurrency` в `1..16`;
- `delay_seconds` в `0..60`;
- каждый статус в `retry_statuses` — целое `400..599`, список не пустой;
- `max_pages` либо None, либо `>= 1`;
- `sources` длиной минимум 1;
- `id` уникальны и каждый матчит `^[a-z][a-z0-9_-]{0,31}$`.

Проверки `SourceEntry` после того, как известен тип:

- `books_toscrape`: `start_url` обязателен и проходит `is_http_url`; `currency` обязателен и матчит `^[A-Z]{3}$`; `config_file` пуст. Иначе `ConfigError`.
- `yaml`: `config_file` обязателен; `start_url`, `currency` и непустой `categories` запрещены (они задаются внутри YAML-файла); `fetch_details: true` запрещён с текстом `yaml-источник в этой версии не ходит в карточки`. `fetch_details: false` можно указать явно.

Проверки `YamlSourceConfig` при чтении файла:

- `start_urls` минимум один, каждый `is_http_url`;
- `currency` матчит `^[A-Z]{3}$`;
- `item`, селекторы полей и `pagination.next_selector` непустые;
- у полей `name`, `url`, `price` флаг `optional` не может быть true;
- `regex`, если задан, компилируется `re.compile`. Ошибка компиляции — `ConfigError` с именем поля.

Итоговые dataclass (frozen):

```python
@dataclass(frozen=True)
class HttpSettings:
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
    http: HttpSettings
    output_dir: Path
    runs_dir: Path
    log_level: str
    log_file: Path | None
    sources: tuple[ResolvedSource, ...]
    config_path: Path
```

```python
def load_config(path: Path) -> ResolvedConfig:
    """Прочитать YAML, проверить схему, подгрузить YAML источников, разрешить пути."""
```

Шаги `load_config`:

1. Если `path` не файл: `ConfigError(f"Файл конфига не найден: {path}")`.
2. Прочитать UTF-8. `yaml.YAMLError` → `ConfigError(f"Ошибка YAML: {exc}")`.
3. Корень не `dict` → `ConfigError("Корень конфига должен быть словарём")`.
4. `AppConfig.model_validate`. `ValidationError` → `ConfigError(f"Некорректный конфиг: {exc}")`.
5. `base = path.parent.resolve()`.
6. `output_dir`, `runs_dir`, `log_file`: если строка абсолютная, `Path(s)`; если относительная, `(base / s).resolve()`.
7. Для каждого source сохранить сырой dict из YAML (до модели), чтобы видеть, был ли ключ. Надёжный способ: взять `entry.model_fields_set` у `SourceEntry`. Если `"max_pages"` в `model_fields_set`, использовать значение записи, включая None. Если нет — `app.max_pages`. То же для `fetch_details`: нет в `model_fields_set` → `app.fetch_details`.
8. Для `type: yaml` путь `config_file` резолвить от `base`, прочитать отдельным `yaml.safe_load`, провалидировать `YamlSourceConfig`. Нет файла → `ConfigError(f"Файл источника не найден: {path}")`.
9. Вернуть `ResolvedConfig`. Сетевых вызовов нет.

Вспомогательная функция, которой пользуется CLI:

```python
def select_sources(
    config: ResolvedConfig,
    only_ids: list[str] | None,
) -> tuple[ResolvedSource, ...]:
    """only_ids None или пуст: все enabled, в порядке файла.
    Иначе: ровно эти id, в порядке аргументов, даже если enabled false.
    Неизвестный id -> ConfigError (это код выхода 2).
    Повтор одного id в аргументах -> ConfigError.
    """
```

---

## 8. Модули: контракты

### 8.1. `errors.py`

```python
class PriceParserError(Exception):
    """База контролируемых ошибок пакета."""


class ConfigError(PriceParserError):
    """Конфиг или аргументы. Код выхода 2."""


class FetchError(PriceParserError):
    def __init__(self, url: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {message}")
        self.url = url
        self.message = message
        self.status = status


class RobotsDenied(PriceParserError):
    def __init__(self, url: str) -> None:
        super().__init__(f"Запрещено robots.txt: {url}")
        self.url = url


class ParseError(PriceParserError):
    """Страница или поле не разобраны."""


class ExportError(PriceParserError):
    """Файл выгрузки не записан."""
```

`ItemSkip` как исключение не вводить. Пропуск карточки — `return` из локальной функции разбора одной карточки и warning.

### 8.2. `clock.py`

```python
def utc_now() -> datetime:
    """Текущий момент в UTC, микросекунды обнулены."""
    return datetime.now(timezone.utc).replace(microsecond=0)
```

### 8.3. `html_utils.py`

BeautifulSoup типизирован плохо. Все входы `Any`, все выходы — нормальные типы, чтобы остальной код проходил mypy strict.

```python
def make_soup(html: str) -> Any:
    """BeautifulSoup(html, "lxml"). Ошибка парсера -> ParseError."""


def text_of(node: Any) -> str:
    """get_text(' ', strip=True) либо пустая строка, если node is None."""


def attr_of(node: Any, name: str) -> str | None:
    """Атрибут строкой. Список (так бывает у class) -> первый элемент. Нет атрибута -> None."""


def abs_url(page_url: str, href: str | None) -> str | None:
    """urljoin. Пустой href -> None. Уже абсолютная ссылка остаётся абсолютной."""
```

### 8.4. `logging_setup.py`

```python
def setup_logging(level: str, log_file: Path | None) -> None:
    """Настроить логгер `priceparser`.

    Формат: `%(asctime)s %(levelname)s %(name)s: %(message)s`
    Дата: `%Y-%m-%dT%H:%M:%S`
    Поток: stderr. Файл, если log_file задан: UTF-8, каталог создать.
    Перед добавлением обработчиков очистить `logger.handlers` у `priceparser`,
    чтобы повторный вызов не двоил строки.
    `logger.propagate = False`, чтобы строки не дублировались корневым логгером.
    Логгерам `httpx` и `httpcore` выставить уровень WARNING.
    """
```

Тесты парсеров `setup_logging` не вызывают. Они смотрят `caplog.at_level(..., logger="priceparser....")`: pytest вешает handler на указанный логгер, поэтому `propagate = False` им не мешает. Тест CLI, которому нужен файл лога, читает сам файл, а не caplog. В `conftest.py` propagate не переключать.

### 8.5. `robots.py`

```python
class RobotsCache:
    def __init__(self, *, respect: bool, user_agent: str) -> None: ...

    async def allowed(
        self,
        fetch: Callable[[str], Awaitable[tuple[int, str]]],
        url: str,
    ) -> bool:
        """Можно ли качать url.

        respect False: сразу True, fetch не вызывать.
        Иначе взять origin `scheme://netloc` (netloc в нижнем регистре, как в URL).
        robots URL: `{origin}/robots.txt`.
        Кэш на процесс: один fetch на origin.
        Статус 404 или 410: разрешить всё.
        Статус >= 400: запретить весь origin и залогировать error.
        FetchError от fetch: запретить весь origin и залогировать error.
        Статус 200: urllib.robotparser.RobotFileParser, parse(text.splitlines()).
        Пустой 200 без правил: can_fetch вернёт True, так и оставить.
        Решение: parser.can_fetch(self.user_agent, url). В can_fetch передавать
        полный User-Agent. Правила `User-agent: *` на webscraper.io тогда применяются.
        """
```

`RobotFileParser` создавать пустым (`RobotFileParser()`), не через `set_url`+`read`: текст уже скачан нами. Вызов синхронный, это нормально.

### 8.6. `http_client.py`

Протокол, чтобы тесты подсовывали `FakeClient`:

```python
class PageFetcher(Protocol):
    async def get_text(self, url: str, *, check_robots: bool = ...) -> str: ...
```

Значение по умолчанию `check_robots` в протоколе можно не дублировать. Реализация:

```python
class PoliteClient:
    def __init__(
        self,
        settings: HttpSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None: ...

    async def __aenter__(self) -> PoliteClient: ...
    async def __aexit__(self, *exc: object) -> None: ...

    async def get_text(self, url: str, *, check_robots: bool = True) -> str:
        """Текст ответа. После исчерпания попыток или на 4xx вне списка повторов — FetchError.
        Запрет robots — RobotsDenied, без HTTP на сам url.
        """
```

Конструктор сохраняет:

- `sleeper` по умолчанию `asyncio.sleep`;
- `monotonic` по умолчанию `time.monotonic`;
- `jitter` по умолчанию `lambda: random.uniform(0.0, 0.05)`;
- `asyncio.Semaphore(settings.concurrency)`;
- словарь блокировок и `next_at` по хосту;
- `RobotsCache(respect=settings.respect_robots, user_agent=settings.user_agent)`;
- `httpx.AsyncClient` создавать в `__aenter__`, закрывать в `__aexit__`.

Параметры клиента httpx:

- `timeout=httpx.Timeout(settings.timeout_seconds)`;
- `follow_redirects=True`;
- `max_redirects=20` (это и есть дефолт httpx; задать явно);
- `headers`: `User-Agent` из настроек, `Accept: text/html,application/xhtml+xml;q=0.9,*/*;q=0.8`;
- `limits=httpx.Limits(max_connections=settings.concurrency, max_keepalive_connections=settings.concurrency)`;
- `transport=transport`, если передан (в тестах `httpx.MockTransport`).

Инвариант без взаимоблокировки, его записать в docstring класса: `get_text` проверяет robots **до** захвата семафора. Запрос `robots.txt` идёт через внутренний `_fetch_with_retries` и сам берёт семафор. `RobotsCache.allowed` нельзя вызывать, держа семафор: `Semaphore` не реентерабельный.

`get_text`:

1. `urlsplit`. Схема не `http`/`https` или нет netloc → `FetchError` сразу, без повторов и без robots.
2. Если `check_robots` и не `await self._robots.allowed(self._fetch_status, url)` → `RobotsDenied`. `_fetch_status` описан ниже и **не** проверяет robots.
3. `async with self._sem`.
4. `await self._wait_host(url)`.
5. `return await self._fetch_with_retries(url)`.

`_wait_host`:

- хост = `urlsplit(url).netloc.lower()` (с портом, если он нестандартный: `example.com:8080`);
- отдельный `asyncio.Lock` на хост;
- под локом: `wait = next_at.get(host, now) - now`. Если `wait > 0`, `await sleeper(wait)`. Время после сна перечитать через `monotonic` (тестовые часы двигает сам sleeper);
- затем `next_at[host] = now + delay_seconds`;
- лок отпустить **до** самого HTTP, чтобы пауза была между стартами, а не между концами. Семафор при этом всё ещё держится вокруг всей попытки включая повторы: параллелизм ограничен на время запроса. Это принятое поведение.

`_fetch_status(url) -> tuple[int, str]` нужен robots-кэшу. Он делает `_fetch_with_retries` и возвращает статус и текст, **не** превращая 404 в исключение. Повторы по `retry_statuses` внутри те же. После исчерпания попыток на 429/5xx вернуть последний статус и текст (возможно пустой), не исключение. Транспортная ошибка после исчерпания попыток — `FetchError`.

`get_text` после `_fetch_with_retries`, если статус `>= 400`, бросает `FetchError(url, f"HTTP {status}", status=status)`. Если статус `< 400`, возвращает `response.text`. Content-Type не проверять: и HTML, и странный тип отдаются текстом. На DEBUG залогировать content-type.

`_fetch_with_retries`:

```text
for attempt in range(1, max_retries + 1):
    try:
        response = await client.get(url)
    except (httpx.TimeoutException, httpx.TransportError, httpx.TooManyRedirects) as exc:
        if attempt == max_retries:
            raise FetchError(url, str(exc)) from exc
        delay = self._backoff(attempt)
        warning "Повтор {url} через {delay:.2f} с: {exc}"
        await sleeper(delay)
        continue
    if response.status_code in retry_statuses:
        if attempt == max_retries:
            return response          # вызывающий решит, ошибка это или нет
        delay = self._retry_after(response) or self._backoff(attempt)
        warning "Повтор {url} через {delay:.2f} с: HTTP {status}"
        await sleeper(delay)
        continue
    return response
```

Успешный ответ (статус не из списка повторов, включая 404) логируется на INFO: `GET {url} -> {status} за {elapsed_ms} мс (попытка {attempt})`. Время замера — `monotonic` до и после `client.get` одной попытки, в миллисекундах, целое.

```python
def _backoff(self, attempt: int) -> float:
    """attempt — номер неудачной попытки, начиная с 1.
    min(backoff_max, backoff_base * 2 ** (attempt - 1)) + jitter().
    """


def _retry_after(self, response: httpx.Response) -> float | None:
    """Заголовок Retry-After. Если значение — целое число секунд `^\\d+$`,
    вернуть min(это число, backoff_max). Иначе None (тогда обычный backoff).
    HTTP-даты не разбирать.
    """
```

`get_text` и статусы:

- `_fetch_with_retries` возвращает `httpx.Response`;
- если статус в `retry_statuses` и попытки кончились, `get_text` бросает `FetchError` с этим статусом (для обычных страниц);
- `_fetch_status` в этом же случае возвращает `(status, text)`, потому что robots хочет видеть 5xx, а не исключение. Реализовать это флагом `raise_for_retry_exhausted: bool` у одного метода, чтобы не копировать цикл.

Не ретраить 401, 403, 404, 410. Один запрос и `FetchError`.

### 8.7. `sources/base.py`

```python
class Source(ABC):
    source_id: str

    @abstractmethod
    async def collect(self, client: PageFetcher) -> CollectResult:
        """Собрать товары источника. Внутри вызвать walk_listings и dedupe_drafts."""
```

### 8.8. `sources/books_toscrape.py`

```python
class BooksToScrapeSource(Source):
    def __init__(
        self,
        *,
        source_id: str,
        start_url: str,
        currency: str,
        categories: tuple[str, ...],
        max_pages: int | None,
        fetch_details: bool,
    ) -> None: ...

    async def collect(self, client: PageFetcher) -> CollectResult: ...
```

Чистые функции того же модуля (их тестируют напрямую, без HTTP):

```python
def parse_books_categories(page_url: str, html: str) -> list[tuple[str, str]]:
    """Список (имя, абсолютный URL) из `div.side_categories ul li ul li a`,
    в порядке сайдбара. Имя = text_of. Пустые имена пропустить.
    """


def parse_books_listing(
    page_url: str,
    html: str,
    *,
    source_id: str,
    currency: str,
) -> ListingParseResult:
    """Разобрать страницу списка books.toscrape.com."""


def parse_books_detail(page_url: str, html: str, draft: ProductDraft) -> ProductDraft:
    """Дополнить черновик карточкой товара. Недостающие узлы не затирают уже собранное."""
```

`parse_books_listing`:

- Для каждого `article.product_pod`:
  - ссылка и имя: `h3 a`. Имя = атрибут `title`, если он непустой, иначе `text_of`. URL = `abs_url(page_url, href)`.
  - цена: `p.price_color` через `parse_price`. `ParseError` или отсутствие узла → warning `Пропущен товар на {page_url}: нет цены` и `continue`.
  - нет имени или нет URL → такой же warning с причиной `нет названия` / `нет ссылки`, `continue`.
  - наличие: `parse_availability(text_of(article.select_one("p.availability")))`.
  - рейтинг: у `p.star-rating` взять класс, который не равен `star-rating`. Слова `one two three four five` (casefold) → `1.0 .. 5.0`. Другое слово → warning `Неизвестная оценка {word} на {page_url}` и `rating=None`. Нет узла → None.
  - картинка: `abs_url` от `div.image_container img` атрибут `src`.
  - `old_price=None`, `sku=None`, `category=None`, `currency` из аргумента, `source_id` из аргумента.
- `next_url`: `li.next a` атрибут `href` через `abs_url`. Нет узла → None.

`parse_books_detail`:

- `h1` непустой → заменить `name`.
- `p.price_color` разбирается → заменить `price`. Ошибка разбора → оставить цену черновика и warning.
- Рейтинг из `p.star-rating` тем же словарём, если узел есть.
- Таблица `table.table-striped tr`: для каждой строки `th`/`td`. Ключ `text_of(th).casefold()`.
  - `upc` → `sku` (пустое не затирает уже бывший sku; на списке sku всё равно None).
  - `availability` → `parse_availability`.
- Категория из крошек: все `ul.breadcrumb li`, непустые тексты. Если их хотя бы 3, категория = предпоследний (`Home, Books, Poetry, Title` → `Poetry`). Иначе категорию не трогать.
- Картинка: `#product_gallery img` `src` через `abs_url`, если есть.
- Вернуть **новый** `ProductDraft` (`dataclasses.replace`), входной не мутировать.

`collect`:

1. `started = clock.utc_now()`.
2. Если `categories` не пуст:
   - скачать `start_url` через `client.get_text`. Эта загрузка **не** увеличивает `pages_fetched`. Ошибка этой загрузки: вернуть пустой `CollectResult` с `page_errors=1` (и нулями в остальном), залогировать error. Не бросать исключение наружу: CLI смотрит на `page_errors` и пустой список.
   - `found = parse_books_categories(start_url, html)`.
   - Для каждого запрошенного имени (порядок как в конфиге) найти элемент `found`, сравнивая `casefold` и схлопнутые пробелы.
   - Хотя бы одно имя не найдено: это не `page_errors`, а исключение `ParseError` с текстом `Категория не найдена: {name}. Доступны: {имена через запятую}`. CLI поймает его как провал источника. До обхода списков дело не доходит. Текст доступных имён — в порядке сайдбара.
   - Иначе `start_urls` = найденные URL в порядке конфига.
3. Если `categories` пуст: `start_urls = [start_url]`. Предварительный запрос не делать: первая страница и есть список.
4. `drafts, pages_fetched, page_errors = await walk_listings(client, start_urls, parse, max_pages)`, где `parse` — лямбда в `parse_books_listing` с `source_id` и `currency`.
5. `unique, dropped = dedupe_drafts(drafts)`.
6. Если `fetch_details`:
   - для каждого черновика запланировать загрузку `draft.url`;
   - параллелизм даёт сам клиент (семафор). Запускать `asyncio.gather` по всем карточкам, `return_exceptions=False`. Каждая корутина ловит `FetchError` и `RobotsDenied` сама, пишет error/warning, увеличивает локальный счётчик ошибок (собрать через список или `asyncio`-безопасный int в замыкании: в одном потоке событий гонки нет, обычный `errors[0] += 1` допустим), и возвращает исходный черновик.
   - успех: `parse_books_detail`, `detail_pages_fetched += 1`.
   - `ParseError` из detail: warning, оставить черновик списка, в `detail_pages_fetched` не плюсовать, в `page_errors` плюсовать.
7. Если `fetch_details` ложь: список черновиков остаётся как после шага 5, `detail_pages_fetched = 0`.
8. Второй проход `dedupe_drafts` по черновикам после карточек. Он нужен, потому что ключ мог смениться с URL на SKU и два разных URL с одним UPC должны схлопнуться. `duplicates_dropped` — сумма счётчиков обоих проходов. Если `fetch_details` ложь, второй проход всё равно вызвать: он даст ноль, код один.
9. `products = [d.to_product(started) for d in черновики после второго дедупа]`. Ошибка валидации одного товара: warning и пропуск этого товара, не провал всего источника.
10. Вернуть `CollectResult`. Отдельный тест на второй дедуп в `test_crawl.py` не добавлять: правило ключа покрыто `test_dedup.py`, а `collect` просто вызывает `dedupe_drafts` дважды.

Категория со списка не проставляется. Она появляется из крошек карточки. При `fetch_details: false` и обходе категории Travel поле `category` останется None. В примере конфига `fetch_details: true`, поэтому в демо категория будет `Travel` (или другая крошка). Это написано в README.

### 8.9. `sources/yaml_source.py`

```python
class YamlSource(Source):
    def __init__(
        self,
        *,
        source_id: str,
        spec: YamlSourceConfig,
        max_pages: int | None,
    ) -> None: ...

    async def collect(self, client: PageFetcher) -> CollectResult: ...

    def parse_listing(self, page_url: str, html: str) -> ListingParseResult:
        """Разобрать одну страницу по spec. Без сети."""
```

`collect` вызывает `walk_listings` со `start_urls` из spec и `self.parse_listing`, затем `dedupe_drafts`, затем `to_product(clock.utc_now())`. `detail_pages_fetched=0`. Карточки не качать.

Разбор карточки:

1. `soup = make_soup(html)`.
2. `next_url`: `soup.select_one(pagination.next_selector)`. Взять атрибут `pagination.attr`. Если `pagination.absolute`, прогнать через `abs_url`. Нет узла или пустой атрибут → None.
3. Для каждого `item.select` по селектору `spec.item` (это список, не `select_one`):
   - вытащить поля через общую функцию `_extract(item, field, page_url) -> str | None`;
   - обязательные `name`, `url`, `price`: None → warning `Пропущен товар на {page_url}: нет {имени поля}` и следующая карточка;
   - `price` и `old_price` через `parse_price`. Ошибка на обязательной цене → пропуск карточки. Ошибка на optional старой цене → warning и `old_price=None`, карточку не бросать;
   - `url` и `image_url`: если у поля `absolute: true`, `abs_url`. После этого URL обязан проходить `is_http_url`, иначе пропуск;
   - `availability`: если поля нет в spec или текст None → `UNKNOWN`, иначе `parse_availability` с фразами из `availability_map`, если карта задана, иначе с дефолтами из `prices.py`;
   - `rating`: особый порядок. Сначала `_extract` (атрибут или текст). Если результат None и у поля задан `count_selector`, посчитать `len(item.select(count_selector))`. Если счётчик 0, считать что оценки нет (None), не ноль. Явный атрибут `0` остаётся нулём и уходит в `parse_rating`. Ноль звёзд без атрибута — это «разметки нет»;
   - `category`: текст селектора, если непустой; иначе строка `spec.category`; иначе None;
   - `sku`: текст или None;
   - `currency` и `source_id` из spec / конструктора.

`_extract(node, spec, page_url) -> str | None`:

1. `found = node.select_one(spec.selector)`.
2. Нет узла → None.
3. Если `spec.attr` задан: `attr_of`. Иначе `text_of`.
4. Если задан `regex`: `re.search`. Нет совпадения → None. Если есть группа 1, взять её, иначе всё совпадение `group(0)`.
5. `strip`. Пустая строка → None.
6. Абсолютный URL здесь не делать: это решает вызывающий по флагу поля, чтобы `_extract` оставался про строку. Для `pagination` абсолютность применяется снаружи, как в шаге 2.

`regex` компилируется один раз в `__init__` и кладётся в dict по имени поля. В `_extract` передавать уже `re.Pattern[str] | None`.

### 8.10. `sources/registry.py` и `sources/__init__.py`

```python
def create_source(
    source: ResolvedSource,
    *,
    max_pages: int | None,
    fetch_details: bool,
) -> Source:
    """Собрать адаптер. Неизвестный type -> ConfigError.

    books_toscrape: BooksToScrapeSource из полей ResolvedSource.
    yaml: YamlSource(source_id=source.id, spec=source.yaml_spec, max_pages=max_pages).
    yaml_spec None у yaml-источника -> ConfigError (защита, load_config так не отдаёт).
    """
```

`sources/__init__.py` пустой кроме docstring модуля «Адаптеры сайтов». Реестр не импортировать из `__init__`, чтобы не было циклов. CLI импортирует `create_source` из `priceparser.sources.registry`.

Новый класс-адаптер добавляется так (это же текст README): файл рядом, ветка в `create_source`, тип в `Literal` модели `SourceEntry`. Три точки, ядро не трогается.

### 8.11. `storage.py`

```python
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z(?:-\d+)?$")


def make_run_id(when: datetime, runs_dir: Path, source_id: str) -> str:
    """База: when.strftime('%Y%m%dT%H%M%SZ'), when обязан быть aware UTC.
    Файл `{runs_dir}/{source_id}/{base}.json` если занят, пробовать `{base}-2`, `{base}-3`, ...
    Каталог не создавать: только проверить exists().
    """


def snapshot_path(runs_dir: Path, source_id: str, run_id: str) -> Path:
    return runs_dir / source_id / f"{run_id}.json"


def save_snapshot(path: Path, snapshot: RunSnapshot) -> None:
    """Создать родительские каталоги. Записать model_dump_json(indent=2) в UTF-8 без BOM.
    Добавить перевод строки в конце файла. OSError -> ExportError.
    """


def load_snapshot(path: Path) -> RunSnapshot:
    """UTF-8. Битый JSON или ValidationError -> ExportError с путём.
    Если meta.product_count != len(products): warning и всё равно вернуть снимок.
    """


def list_snapshots(runs_dir: Path, source_id: str) -> list[Path]:
    """Файлы `*.json` в каталоге источника, у которых stem матчит _RUN_ID_RE.
    Сортировка по имени по возрастанию. Каталога нет -> пустой список, не ошибка.
    """


def latest_pair(runs_dir: Path, source_id: str) -> tuple[Path, Path] | None:
    """Два последних пути (предыдущий, текущий) или None, если файлов меньше двух."""
```

Имя `20261125T221500Z` лексикографически совпадает с хронологией, суффикс `-2` тоже сортируется после базы, потому что `-` идёт после конца более короткого имени? Проверка: строка `20261125T221500Z` короче, чем `20261125T221500Z-2`. Сортировка по полному имени: общая приставка, затем конец против `-`. Символ конца меньше `-`. Значит база идёт **раньше** `-2`. Это правильный порядок «сначала первый файл этой секунды, потом суффиксы». `latest_pair` берёт два последних элемента отсортированного списка. Тест `test_run_id_collision_suffix` это фиксирует: после записи двух снимков с одним `when` идентификаторы `...Z` и `...Z-2`, и пара именно такая.

Запись снимка в CLI использует `make_run_id` **до** `save_snapshot`.

Пример JSON, который обязан получаться из модели (тест круглого пути сравнивает поля, не весь текст байт-в-байт, но деньги — строки с двумя знаками, дата — с `+00:00` и без микросекунд):

```json
{
  "meta": {
    "run_id": "20261125T221500Z",
    "source_id": "books",
    "started_at": "2026-11-25T22:15:00+00:00",
    "finished_at": "2026-11-25T22:15:04+00:00",
    "product_count": 1,
    "pages_fetched": 1,
    "detail_pages_fetched": 1,
    "page_errors": 0,
    "config_path": "/tmp/config.yaml"
  },
  "products": [
    {
      "source_id": "books",
      "name": "A Light in the Attic",
      "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
      "price": "51.77",
      "currency": "GBP",
      "old_price": null,
      "availability": "in_stock",
      "category": "Poetry",
      "rating": 3.0,
      "image_url": "https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg",
      "sku": "a897fe39b1053632",
      "scraped_at": "2026-11-25T22:15:00+00:00"
    }
  ]
}
```

### 8.12. `export_csv.py`

```python
PRODUCT_HEADERS: tuple[str, ...] = (
    "Название",
    "Цена",
    "Старая цена",
    "Валюта",
    "Наличие",
    "Категория",
    "Рейтинг",
    "Артикул",
    "URL",
    "Картинка",
    "Источник",
    "Снято",
)


def sort_products(products: list[Product]) -> list[Product]:
    """Категория None в конце. Дальше category.casefold(), name.casefold(), url."""


def export_products_csv(
    products: list[Product],
    path: Path,
    *,
    delimiter: str = ",",
) -> None:
    """Записать CSV. delimiter — ровно один символ, иначе ExportError.
    Кодировка utf-8-sig, newline='' в open(), lineterminator '\\r\\n',
    csv.QUOTE_MINIMAL, quoting по правилам csv (запятые и кавычки в названии экранируются).
    Каталог создать. Пустой список товаров: файл только с шапкой.
    """
```

Порядок строк: `sort_products`. Ячейки:

| Колонка | Значение |
| --- | --- |
| Название | `name` |
| Цена | `f"{price:.2f}"` уже квантованного Decimal, точка |
| Старая цена | так же или пустая строка |
| Валюта | `GBP` |
| Наличие | значение из `AVAILABILITY_RU` |
| Категория | строка или пусто |
| Рейтинг | `f"{rating:.1f}"` (пример `3.0`) или пусто |
| Артикул | sku или пусто |
| URL | как есть |
| Картинка | как есть или пусто |
| Источник | source_id |
| Снято | `scraped_at.isoformat(timespec="seconds")` |

None не писать словом `None`.

### 8.13. `export_xlsx.py`

Константы ширин в том же порядке, что шапка:

```python
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
```

```python
def export_products_xlsx(
    products: list[Product],
    path: Path,
    *,
    changes: list[PriceChange] | None = None,
    include_unchanged: bool = False,
) -> None:
    """Книга с листом «Товары». Если changes не None, второй лист «Изменения».
    changes=[] означает лист только с шапкой. changes=None означает, что листа нет.
    """


def export_changes_xlsx(
    changes: list[PriceChange],
    path: Path,
    *,
    include_unchanged: bool = False,
) -> None:
    """Книга, единственный лист которой — «Изменения». Активный лист — он."""
```

Общее оформление обоих листов, функция `_style_sheet(ws, headers, widths)` в этом модуле:

- Шрифт данных: Calibri, размер 11, цвет не задавать (чёрный по умолчанию), кроме колонки вида изменения и гиперссылок.
- Шапка, строка 1: шрифт Calibri 11, bold, цвет `FFFFFF`. Заливка `PatternFill(fill_type="solid", fgColor="1F4E79")`. Выравнивание по центру по горизонтали и вертикали, `wrap_text=False`. Высота строки 22.
- Заморозка: `ws.freeze_panes = "A2"`.
- Автофильтр: на диапазон от `A1` до последней колонки и последней строки. Если данных нет, диапазон шапки, для товаров это `A1:L1`. Считать букву колонки через `openpyxl.utils.get_column_letter`.
- Ширины: `column_dimensions[letter].width` из кортежа.
- Граница каждой ячейки шапки и данных: тонкая, цвет `D9D9D9`, все четыре стороны.
- Зебра только на строках данных: excel-строка 3, 5, 7… (нечётные номера) заливка `F7F9FB`. Строка 2 (первый товар) без дополнительной заливки. Шапка своей заливкой не перекрашивается.
- Выравнивание данных: вертикально по центру, горизонтально по умолчанию.
- `wb.properties.creator = "price-catalog-parser"`.
- Ориентация листа landscape, вписать по ширине на 1 страницу, по высоте не ограничивать: `page_setup.orientation = "landscape"`, `page_setup.fitToWidth = 1`, `page_setup.fitToHeight = 0`, `sheet_properties.pageSetUpPr.fitToPage = True`.
- `print_title_rows = "1:1"`.
- `auto_filter.ref` и `freeze_panes` обязательны даже при нуле строк данных.
- Каталог файла создать. `OSError` → `ExportError`.
- Имена листов строго `Товары` и `Изменения`. В книге прогона активный лист — `Товары`.

Лист товаров, порядок колонок = `PRODUCT_HEADERS`, порядок строк = `sort_products`:

- Цена и старая цена: в ячейку `float(price)`, `number_format = "#,##0.00"`. Пустая старая цена: значение `None`, формат тот же можно поставить.
- Рейтинг: `float`, формат `0.0`, либо пусто.
- Наличие: русская подпись.
- Остальные поля: строки. Пустые Optional — `None` в ячейке, не строка `"None"`.
- Колонки URL и Картинка: если значение непустое, `cell.hyperlink = value` и шрифт Calibri 11, цвет `0563C1`, `underline="single"`. Этот шрифт ставится после зебры и заменяет обычный шрифт только в этих ячейках.
- «Снято»: строка `isoformat(timespec="seconds")`, не объект datetime (так тест сравнивает строки и нет сюрприза с таймзоной Excel).

Лист изменений:

- Брать из `changes` только те, у которых `kind != UNCHANGED`, если `include_unchanged` ложь. Порядок после фильтра сохранять (список уже отсортирован `diff_products`).
- Колонка «Изменение»: текст `CHANGE_KIND_RU[kind]`. Шрифт Calibri 11, цвет `CHANGE_KIND_FONT[kind]`, не bold.
- Цены, разница: `float` или пусто, формат `#,##0.00`. «Разница %»: `float(delta_pct)` формат `0.00`, это уже проценты, не делить на 100. Пустой `delta_pct` — пустая ячейка.
- «Валюты различаются»: `Да` или `Нет`.
- URL: гиперссылка тем же стилем, что на листе товаров.
- Остальные строки как есть.

Не добавлять третий лист, графики, формулы, автосумму.

### 8.14. `cli.py`

```python
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Парсер каталогов и цен. Выгрузка в Excel и CSV.",
)
```

Колбэк корня с `--version` / `-V` (`is_eager=True`): печать `price-catalog-parser 0.1.0` и выход 0. Текст помощи флага: `Показать версию и выйти`.

Команда `version` без аргументов печатает то же и выходит 0. Help: `Показать версию`.

Общие правила CLI:

- Конфиг по умолчанию: путь `config.yaml` относительно текущей директории. Опция `--config` / `-c`, help `Путь к YAML-конфигу`.
- `ConfigError` в любой команде: `typer.echo(str(exc), err=True)`, код 2. Строку `Готово` не печатать.
- Неизвестный источник в `--source`: код 2, текст из `select_sources`.
- `setup_logging` вызывается после успешной загрузки конфига. Уровень: флаг `--log-level`, если передан, иначе `config.log_level`. Допустимые значения те же четыре. Мусор → код 2.
- Файлы пишутся только командами `run`, `export`, `diff`.

#### Команда `run`

Help: `Скачать источники и записать Excel, CSV и снимок`.

Опции:

| Опция | Тип | По умолчанию | Help |
| --- | --- | --- | --- |
| `--config` `-c` | Path | `config.yaml` | Путь к YAML-конфигу |
| `--source` `-s` | список строк, repeatable | пусто | Какой источник запускать, можно повторять. Пусто — все включённые |
| `--max-pages` | int \| None | None | Лимит страниц списка. Перекрывает конфиг |
| `--fetch-details` | flag | False | Ходить в карточки товара |
| `--no-fetch-details` | flag | False | Не ходить в карточки товара |
| `--output-dir` | Path \| None | None | Куда писать таблицы. Пусто — из конфига |
| `--format` `-f` | str | `all` | `all`, `xlsx` или `csv` |
| `--diff` | str | `auto` | `auto`, `on` или `off` |
| `--previous` | Path \| None | None | JSON предыдущего снимка для сравнения |
| `--strict` | flag | False | Останавливаться на первом проблемном источнике |
| `--log-level` | str \| None | None | DEBUG, INFO, WARNING или ERROR |
| `--csv-delimiter` | str | `,` | Разделитель CSV, один символ |
| `--include-unchanged` | flag | False | Писать на лист изменений строки без сдвига цены |

Проверки до сети, код 2:

- оба флага `--fetch-details` и `--no-fetch-details` сразу: `Укажите только один из флагов --fetch-details и --no-fetch-details`;
- `--format` не из `all|xlsx|csv` (сравнение casefold): `Формат должен быть all, xlsx или csv`;
- `--diff` не из `auto|on|off`: `Сравнение должно быть auto, on или off`;
- `--max-pages` передан и `< 1`: `max-pages должен быть >= 1`;
- `--csv-delimiter` не ровно один символ: `Разделитель CSV должен быть одним символом`;
- `--previous` передан и это не файл: `Файл снимка не найден: {path}`.

Сеть: один клиент на всю команду.

```python
def build_client(config: ResolvedConfig) -> PoliteClient:
    """Фабрика. Тесты подменяют priceparser.cli.build_client."""
    return PoliteClient(config.http)
```

`run` вызывает `build_client` как глобальное имя модуля `cli`, затем `async with client`. Внутри цикла по выбранным источникам — `create_source` и `await source.collect(client)`. Не импортировать `build_client` внутрь функции повторно.

Эффективные параметры источника:

- `max_pages`: если флаг передан (не None), он; иначе `ResolvedSource.max_pages`;
- `fetch_details`: флаг `--fetch-details` → True; `--no-fetch-details` → False; иначе значение источника. Для yaml-источника True после этой логики → `ConfigError` ещё до сети (код 2): `yaml-источник в этой версии не ходит в карточки`.

Дальше для каждого источника по порядку, ошибки одного не роняют процесс, пока не включён `--strict`:

1. `result = await source.collect(client)`. Исключение (`PriceParserError` и любое другое): залогировать exception, пометить источник проваленным, файлов этого источника не писать. При `--strict` прекратить цикл. Без `--strict` перейти к следующему.
2. Решить, писать ли файлы, по таблице раздела 12. Если не писать — источник провален, дальше как в шаге 1.
3. `started_at` взять из `result.products[0].scraped_at`, если товары есть, иначе `clock.utc_now()`. `finished_at = clock.utc_now()`.
4. `run_id = make_run_id(started_at, runs_dir, source.id)`. Если секунда занята, суффикс из `make_run_id`, но тогда `started_at` в мете остаётся истинным временем, а `run_id` может иметь `-2`.
5. Собрать `RunSnapshot` и `save_snapshot`.
6. Экспорт по `--format`:
   - `all`: CSV и xlsx;
   - `xlsx`: только xlsx;
   - `csv`: только CSV.
   - Имена: `{output_dir}/{source_id}-{run_id}.csv` и `.xlsx`. `output_dir` из флага, если он был, иначе из конфига. Флаг относительный — от текущей директории, не от конфига: это путь командной строки, не путь из файла. Записать это в help не нужно, но реализовать так.
7. Сравнение:
   - `off`: не читать старые снимки, листа нет, в stdout `Сравнение: выключено`.
   - `auto` или `on`: предыдущий снимок — это `--previous`, если передан. Иначе самый новый файл в `list_snapshots`, чьё имя **не** равно только что записанному. Если таких нет: при `auto` строка `Сравнение: предыдущий снимок не найден` и код источника успешный (если нет других причин для провала); при `on` строка `Сравнение: ошибка, предыдущий снимок не найден`, источник провален, но снимок и таблица товаров уже записаны.
   - Снимок загрузился: `diff_products(previous.products, result.products)`.
   - Формат `all` или `xlsx`: передать `changes=report.changes` в `export_products_xlsx` (вызвать экспорт xlsx **после** расчёта diff, не дважды; порядок шагов такой: сначала решить diff, потом писать файлы).
   - Формат `csv`: таблицу товаров писать в CSV, а изменения — отдельным файлом `{output_dir}/{source_id}-{run_id}-changes.xlsx` через `export_changes_xlsx`.
   - `--include-unchanged` пробрасывается в экспорт.
8. Напечатать блок источника (раздел 9). Между источниками пустая строка.

После цикла всегда, если не было кода 2:

```text
Готово. Источников: {N}, с ошибками: {M}.
```

`N` — сколько источников было выбрано, включая не начатые из-за `--strict`. `M` — сколько помечено проваленными. Если `M > 0`, код выхода 1, иначе 0.

Перестановка шага 6 и 7: практически вычислить diff до записи xlsx, а CSV можно писать в любой момент после снимка. Снимок писать даже если экспорт упал. Если `export_*` бросил `ExportError`, источник провален, уже записанные файлы не удалять, залогировать ошибку.

#### Команда `export`

Help: `Записать Excel и CSV из готового снимка, без сети`.

| Опция | По умолчанию | Help |
| --- | --- | --- |
| `--snapshot` | обязательный Path | JSON снимка |
| `--format` `-f` | `all` | `all`, `xlsx` или `csv` |
| `--output-dir` | каталог `output` в cwd | Куда писать таблицы |
| `--diff-against` | None | Второй снимок: лист изменений, где этот файл считается предыдущим, а `--snapshot` текущим |
| `--include-unchanged` | False | Писать строки без сдвига цены |
| `--csv-delimiter` | `,` | Разделитель CSV, один символ |

Имена файлов из `meta.run_id` и `meta.source_id` снимка `--snapshot`. Сеть не открывать (`build_client` не вызывать). Нет файла → код 2. Битый снимок (`ExportError`) → код 1. Успех печатает те же строки `Excel:` / `CSV:` / при наличии `Сравнение:` и `Файл изменений:`, без строки `Готово` (эта строка только у `run`). Код 0.

#### Команда `diff`

Help: `Сравнить два снимка и записать Excel с листом изменений`.

| Опция | По умолчанию | Help |
| --- | --- | --- |
| `--config` `-c` | `config.yaml` | Путь к YAML-конфигу |
| `--source` `-s` | обязательный | Идентификатор источника |
| `--previous` | None | Более ранний снимок. Пусто — предпоследний файл источника |
| `--current` | None | Более поздний снимок. Пусто — последний файл источника |
| `--output` `-o` | None | Куда писать xlsx. Пусто — `output/{id}-diff-{prev_run}-{curr_run}.xlsx` рядом с cwd, каталог `output` |
| `--include-unchanged` | False | Писать строки без сдвига цены |

Если для подстановки по умолчанию не хватает двух снимков: код 1, stderr `Недостаточно снимков для сравнения источника {id}: найдено {n}`. Если у загруженного снимка `meta.source_id` не равен `--source`: код 2, `Снимок {path} относится к источнику {actual}, ожидался {id}`. Товары с чужим `source_id` внутри файла пропустить с warning.

Stdout ровно:

```text
Сравнение {id}
Было: {prev_path} ({n} товаров)
Стало: {curr_path} ({m} товаров)
Новых: {new}
Пропавших: {removed}
Цена выросла: {up}
Цена упала: {down}
Без изменений: {unchanged}
Файл: {output}
```

Числа — из `DiffReport`, включая unchanged, даже если строки unchanged не записаны в файл.

#### Команда `sources`

Help: `Показать источники из конфига`.

Опция `--config`. Сети нет. Stdout, одна шапка и дальше строки через два пробела между колонками (не выравнивать таблицу пробелами до колонки, тесты ищут подстроки):

```text
ID  TYPE  STATUS  START
books  books_toscrape  enabled  https://books.toscrape.com/
laptops  yaml  enabled  https://webscraper.io/test-sites/e-commerce/static/computers/laptops
```

`STATUS` = `enabled` или `disabled`. `START` для books = `start_url`. Для yaml = первый `start_urls` из spec. Выключенные тоже показывать.

#### Команда `validate`

Help: `Проверить конфиг, не ходя в сеть`.

Успех, stdout: `Конфиг корректен: {n} источников`. `n` — длина `config.sources`, включая disabled. Код 0. Ошибка — код 2 и текст `ConfigError` в stderr.

### 8.15. Сборка прогона в CLI и коды — сводка функций

Чтобы `cli.py` не расползался, вынести чистую функцию в `cli.py` (её проще тестировать через Typer, отдельно не дробить):

Печать блока `run` — функция `_print_source_report(...)` со строками из раздела 9. Тест смотрит весь stdout, поэтому формулировки фиксированы.

---

## 9. Команды CLI, примеры и ожидаемый вывод

Ниже фигурные поля — подстановка. Остальной текст, включая двоеточия и запятые, фиксирован. Числа без выравнивания пробелами.

### 9.1. `priceparser version` и `priceparser --version`

Stdout:

```text
price-catalog-parser 0.1.0
```

Код 0. `--help` содержит фразу `Парсер каталогов и цен`.

### 9.2. `priceparser validate --config config.example.yaml`

```text
Конфиг корректен: 2 источников
```

### 9.3. `priceparser sources --config config.example.yaml`

```text
ID  TYPE  STATUS  START
books  books_toscrape  enabled  https://books.toscrape.com/
laptops  yaml  enabled  https://webscraper.io/test-sites/e-commerce/static/computers/laptops
```

### 9.4. `priceparser run`

Пример для README (числа живого сайта могут отличаться; формат строк — нет):

```bash
priceparser run --config config.yaml --source books --max-pages 1 --fetch-details
```

Stdout при первом прогоне, когда предыдущего снимка нет, формат `all`, diff `auto`:

```text
Источник: books
Страниц каталога: 1
Страниц карточек: 11
Товаров: 11 (дублей отброшено: 0)
Ошибки страниц: 0
Снимок: data/runs/books/20261125T221500Z.json
Excel: output/books-20261125T221500Z.xlsx
CSV: output/books-20261125T221500Z.csv
Сравнение: предыдущий снимок не найден

Готово. Источников: 1, с ошибками: 0.
```

Пути в stdout — как их видит пользователь: если путь внутри cwd, печатать относительный через `Path.relative_to` когда это возможно, иначе абсолютный. В тестах рабочий каталог — `tmp_path`, и строки `Снимок:`, `Excel:`, `CSV:` проверяются на суффикс имени файла и на то, что файл существует, а не на полный префикс машины. Реализация: функция `_display(path: Path) -> str`, которая возвращает `path.as_posix()` относительный к cwd, если `path.resolve().is_relative_to(Path.cwd())`, иначе `path.as_posix()`.

Когда сравнение посчитано и формат включает xlsx:

```text
Сравнение: с data/runs/books/20261125T180000Z.json: новых 1, пропавших 0, цена выросла 2, цена упала 1, без изменений 8
```

Когда формат `csv` и сравнение посчитано, следом отдельная строка:

```text
Файл изменений: output/books-20261125T221500Z-changes.xlsx
```

Когда `--diff off`:

```text
Сравнение: выключено
```

Когда `--diff on` и старого снимка нет:

```text
Сравнение: ошибка, предыдущий снимок не найден
```

и код выхода 1, при этом строки `Снимок`, `Excel`, `CSV` уже напечатаны, файлы есть.

Два источника подряд разделяются одной пустой строкой, затем общая `Готово`.

Если формат `xlsx`, строку `CSV:` не печатать. Если формат `csv`, строку `Excel:` не печатать (файл изменений печатается своей строкой).

Строка `Страниц карточек` печатается всегда, даже если 0.

### 9.5. `priceparser diff`

```bash
priceparser diff --config config.yaml --source books
```

Stdout — шаблон из раздела 8.14. Код 0, когда файлов хватает.

### 9.6. `priceparser export`

```bash
priceparser export --snapshot data/runs/books/20261125T221500Z.json --format xlsx
```

Печатает строки `Excel:` и, если передан `--diff-against`, строку `Сравнение:` в той же формулировке, что `run`, плюс при формате csv строку `Файл изменений:`.

### 9.7. Плохие вызовы

| Вызов | Код | Куда текст |
| --- | --- | --- |
| `validate` с битым YAML | 2 | stderr, префикс из `ConfigError` |
| `run --source missing` | 2 | stderr |
| `run --fetch-details --no-fetch-details` | 2 | stderr, точная фраза из 8.14 |
| `run --format pdf` | 2 | stderr |
| `diff` при одном снимке | 1 | stderr, фраза `Недостаточно снимков` |

---

## 10. Форматы Excel и CSV в деталях

### 10.1. Имена файлов

| Что | Имя |
| --- | --- |
| Таблица прогона | `{output}/{source_id}-{run_id}.xlsx` |
| CSV прогона | `{output}/{source_id}-{run_id}.csv` |
| Только изменения, когда основной файл не xlsx | `{output}/{source_id}-{run_id}-changes.xlsx` |
| Команда `diff` | `{output}/{source_id}-diff-{prev_run_id}-{curr_run_id}.xlsx` |

`run_id` уже безопасен для файловой системы регулярным выражением.

### 10.2. CSV

- Кодировка UTF-8 с BOM (`utf-8-sig`). Первые байты файла `EF BB BF`.
- Разделитель по умолчанию `,`.
- Перевод строки `\r\n`.
- Шапка ровно `PRODUCT_HEADERS`, русские буквы как в константе.
- Цена `51.77`, не `£51.77` и не `51,77`. Валюта отдельной колонкой.
- Рейтинг `3.0`.
- Кавычки csv, если в названии есть разделитель или кавычка. Название `Say "Hello", world` должно корректно читаться `csv.reader` обратно.

### 10.3. XLSX лист «Товары»

12 колонок A–L. Строка 1 — шапка. Данные со строки 2.

Проверки, которые делает тест через openpyxl (сравнивать цвет в нижнем регистре, допуская префикс `00`, потому что openpyxl иногда хранит `001F4E79`):

- имя листа `Товары`;
- `freeze_panes == "A2"`;
- `auto_filter.ref` покрывает шапку и все строки данных;
- ячейка A1: значение `Название`, шрифт жирный, цвет заканчивается на `ffffff`, заливка заканчивается на `1f4e79`;
- высота строки 1 равна 22;
- ширина колонки A равна 42, колонки B равна 12;
- ячейка цены (B2 для первого товара после сортировки) имеет тип числа, значение `51.77` с точностью `abs(value-51.77) < 1e-9`, формат `#,##0.00`;
- ячейка URL — гиперссылка на URL товара, цвет шрифта заканчивается на `0563c1`;
- у строки 3 (если товаров хотя бы 2) заливка заканчивается на `f7f9fb`; у строки 2 заливки зебры нет;
- граница A1 задана (style `thin`);
- `creator == "price-catalog-parser"`.

Сортировка перед записью: категория `None` после любых названий категорий, дальше по имени. Тест кладёт товары `Books/B`, `None/A`, `Books/A` и ожидает порядок `Books/A`, `Books/B`, `None/A`.

### 10.4. XLSX лист «Изменения»

Колонки A–L как `CHANGE_HEADERS`.

Виды в колонке A пишутся по-русски. Цвет шрифта A2 равен цвету первого вида в отсортированном списке. По умолчанию строк `Без изменений` нет. С флагом они есть и их шрифт заканчивается на `666666`.

Пример содержимого для теста (после сортировки видов): сначала «Новый», потом «Пропавший», потом «Цена выросла», потом «Цена упала». Колонка «Разница %» у роста со 100 до 110 равна числу `10` (или `10.0`) с форматом `0.00`. Колонка «Валюты различаются» содержит `Да` только в заранее собранной строке с GBP против USD.

Книга команды `diff` не содержит лист `Товары`.

---

## 11. Ошибки и коды возврата

### 11.1. Что чем кончается

| Ситуация | Исключение | Код | Файлы прогона |
| --- | --- | --- | --- |
| Нет файла конфига, битый YAML, лишнее поле, дубль id, плохой тип, yaml-источник с `fetch_details: true` | `ConfigError` | 2 | нет |
| Плохой флаг CLI | `ConfigError` или `typer.Exit(2)` | 2 | нет |
| Страница списка не скачалась, но товары с других страниц есть, `--strict` выключен | поймано внутри `walk_listings` | 0 | пишутся |
| То же, `--strict` включен | источник помечен проваленным | 1 | пишутся, следующие источники не стартуют |
| Все страницы упали, товаров 0 | провал источника | 1 | не пишутся |
| Товаров 0 и ошибок страниц 0 (пустой каталог) | не провал | 0 | пишутся шапки и снимок с пустым списком |
| Категория books не найдена | `ParseError` из `collect` | 1 | не пишутся |
| Карточка товара не скачалась | warning, черновик списка сохранён | как у страниц: ошибка копится в `page_errors` | товар в выгрузке есть, без SKU |
| Одна карточка списка без цены | warning, карточка пропущена | не влияет | остальные есть |
| `--diff on` и нет предыдущего снимка | провал после записи товаров | 1 | снимок и таблица есть, листа изменений нет |
| `--diff auto` и нет предыдущего | не провал | 0 | без листа изменений |
| Не удалось записать xlsx/csv | `ExportError` | 1 | снимок остаётся, что успело записаться — тоже |
| `robots.txt` отдал 500 | origin запрещён, страницы дают `RobotsDenied` | по таблице пустых товаров | как обычные ошибки страниц |
| `KeyboardInterrupt` | не перехватывать | 130, как решит Python | как получится |

`page_errors` включает и списки, и карточки, и `RobotsDenied`.

Таблица «писать ли файлы» для `run`, повторение без двусмысленности:

| Товаров | Ошибок страниц | strict | Писать снимок и таблицы | Идти к следующему источнику | Вклад в код |
| --- | --- | --- | --- | --- | --- |
| > 0 | 0 | любой | да | да | успех |
| > 0 | > 0 | нет | да | да | успех |
| > 0 | > 0 | да | да | нет | провал |
| 0 | 0 | любой | да | да | успех |
| 0 | > 0 | нет | нет | да | провал |
| 0 | > 0 | да | нет | нет | провал |
| исключение из collect | | нет | нет | да | провал |
| исключение из collect | | да | нет | нет | провал |

Итог процесса: код 1, если хотя бы один провал, иначе 0. Код 2 только до начала источников (конфиг, флаги, неизвестный id, yaml+fetch details).

### 11.2. Логи

Уровни:

- INFO: старт источника `Источник {id}: старт`, каждая удачная HTTP-попытка, отброшенные дубли, путь записанного файла `Записан {path}`.
- WARNING: пропуск карточки, пустая страница, неизвестный рейтинг, лимит страниц, robots deny, повтор запроса, разные валюты, несовпадение `product_count`.
- ERROR: страница не скачалась после повторов, категория не найдена, провал экспорта, robots.txt недоступен.

Сообщение категории не найдена логируется на ERROR в CLI, когда исключение поймано (`logger.exception`).

В текст лога не попадают HTML, заголовки ответа целиком и query с паролями (паролей в проекте нет).

---

## 12. HTTP-вежливость: числа по умолчанию

Из `config.example.yaml`, чтобы демо не выглядело агрессивным:

- не больше 4 одновременных запросов на весь процесс (источники и так по очереди, семафор общий на один клиент команды `run`);
- не меньше 1.0 с между **стартами** запросов на один и тот же netloc, включая запрос `robots.txt` и карточки;
- таймаут 20 с на запрос;
- до 3 попыток на транспорт, таймаут и статусы 429, 500, 502, 503, 504;
- пауза перед следующей попыткой: 0.5 с, потом 1 с, потом 2 с, потолок 8 с, плюс случайные 0–0.05 с. В тестах jitter = 0;
- если `Retry-After` — целое число секунд, спать столько, но не дольше `backoff_max_seconds`;
- User-Agent как в примере конфига;
- редиректы следовать, не больше 20;
- `robots.txt` уважать.

Полный обход books.toscrape.com (50 страниц плюс 1000 карточек) при паузе 1 с займёт заметное время. Пример конфига этого не делает. Снимать лимит можно, убрав `max_pages` (значение `null` на источнике) и не передавая флаг. Отдельного флага «без лимита» нет.

---

## 13. Фикстуры HTML

Файлы в `tests/fixtures/` кодировка UTF-8 **без** BOM. Это сокращённая разметка, повторяющая реальные селекторы сайтов на 2026-11-25, с короткими синтетическими хвостами (вторая страница, старая цена, товар без цены). Тесты читают эти файлы и не ходят в сеть. Комментарии HTML сохраняются: парсер их игнорирует.

Правило тестов: строка `http://` или `https://` в тестах допустима только как данные (URL в словаре `FakeClient`, ожидаемые ссылки, `MockTransport`). Вызовов `httpx` к живому хосту и `urllib.request.urlopen` в тестах нет.

### 13.1. `books_home.html`

```html
<!DOCTYPE html>
<html>
<head><title>Books</title></head>
<body>
<div class="side_categories">
  <ul class="nav nav-list">
    <li>
      <a href="catalogue/category/books_1/index.html">Books</a>
      <ul>
        <li><a href="catalogue/category/books/travel_2/index.html">Travel</a></li>
        <li><a href="catalogue/category/books/mystery_3/index.html">Mystery</a></li>
      </ul>
    </li>
  </ul>
</div>
<article class="product_pod">
  <div class="image_container">
    <a href="catalogue/a-light-in-the-attic_1000/index.html">
      <img alt="A Light in the Attic" class="thumbnail" src="media/cache/attic.jpg"/>
    </a>
  </div>
  <p class="star-rating Three"><i class="icon-star"></i></p>
  <h3><a href="catalogue/a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light in the ...</a></h3>
  <div class="product_price">
    <p class="price_color">£51.77</p>
    <p class="instock availability"><i class="icon-ok"></i>In stock</p>
  </div>
</article>
<article class="product_pod">
  <div class="image_container">
    <a href="catalogue/tipping-the-velvet_999/index.html">
      <img alt="Tipping the Velvet" class="thumbnail" src="media/cache/velvet.jpg"/>
    </a>
  </div>
  <p class="star-rating One"><i class="icon-star"></i></p>
  <h3><a href="catalogue/tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping the Velvet</a></h3>
  <div class="product_price">
    <p class="price_color">£53.74</p>
    <p class="instock availability"><i class="icon-ok"></i>In stock</p>
  </div>
</article>
<ul class="pager">
  <li class="current">Page 1 of 2</li>
  <li class="next"><a href="catalogue/page-2.html">next</a></li>
</ul>
</body>
</html>
```

Ожидания при `page_url = https://books.toscrape.com/`:

- два товара;
- имя первого берётся из `title`, не из обрезанного текста `A Light in the ...`;
- цена `51.77`, валюта аргумента парсера `GBP`, рейтинг `3.0` и `1.0`, наличие `in_stock`, sku None, category None, old_price None;
- URL `https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html`;
- картинка `https://books.toscrape.com/media/cache/attic.jpg`;
- next `https://books.toscrape.com/catalogue/page-2.html`;
- категории `[("Travel", "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"), ("Mystery", "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html")]`.

### 13.2. `books_travel.html`

```html
<!DOCTYPE html>
<html>
<body>
<article class="product_pod">
  <div class="image_container">
    <a href="../../../its-only-the-himalayas_981/index.html">
      <img class="thumbnail" src="../../../media/cache/himalayas.jpg" alt="It's Only the Himalayas"/>
    </a>
  </div>
  <p class="star-rating Two"><i class="icon-star"></i></p>
  <h3><a href="../../../its-only-the-himalayas_981/index.html" title="It's Only the Himalayas">It's Only the Himalayas</a></h3>
  <div class="product_price">
    <p class="price_color">£45.17</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<article class="product_pod">
  <div class="image_container">
    <a href="../../../second-travel-book_100/index.html">
      <img class="thumbnail" src="../../../media/cache/second.jpg" alt="Second Travel Book"/>
    </a>
  </div>
  <p class="star-rating Five"><i class="icon-star"></i></p>
  <h3><a href="../../../second-travel-book_100/index.html" title="Second Travel Book">Second Travel Book</a></h3>
  <div class="product_price">
    <p class="price_color">£10.00</p>
    <p class="instock availability">Out of stock</p>
  </div>
</article>
<article class="product_pod">
  <div class="image_container">
    <a href="../../../broken-book_1/index.html"><img src="../../../media/cache/broken.jpg"/></a>
  </div>
  <p class="star-rating One"></p>
  <h3><a href="../../../broken-book_1/index.html" title="Broken Book">Broken Book</a></h3>
  <div class="product_price">
    <p class="price_color">нет</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
  <li class="current">Page 1 of 2</li>
  <li class="next"><a href="page-2.html">next</a></li>
</ul>
</body>
</html>
```

`page_url = https://books.toscrape.com/catalogue/category/books/travel_2/index.html`.

Ожидания:

- разобраны 2 товара, третий пропущен (цена `нет`);
- первый URL `https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html`;
- картинка `https://books.toscrape.com/media/cache/himalayas.jpg`;
- второй товар наличие `out_of_stock`, цена `10.00`, рейтинг `5.0`;
- next `https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html`.

### 13.3. `books_travel_page2.html`

```html
<!DOCTYPE html>
<html>
<body>
<article class="product_pod">
  <div class="image_container">
    <a href="../../../page-two-book_50/index.html">
      <img class="thumbnail" src="../../../media/cache/page-two.jpg"/>
    </a>
  </div>
  <p class="star-rating One"></p>
  <h3><a href="../../../page-two-book_50/index.html" title="Page Two Book">Page Two Book</a></h3>
  <div class="product_price">
    <p class="price_color">£20.00</p>
    <p class="instock availability">In stock</p>
  </div>
</article>
<ul class="pager">
  <li class="current">Page 2 of 2</li>
</ul>
</body>
</html>
```

Тот же базовый URL, что у page-2: `https://books.toscrape.com/catalogue/category/books/travel_2/page-2.html`. Next отсутствует (`next_url is None`). Один товар, цена `20.00`.

### 13.4. `books_detail_attic.html`

```html
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="/">Books</a></li>
  <li><a href="category/books/poetry_1/index.html">Poetry</a></li>
  <li class="active">A Light in the Attic</li>
</ul>
<div class="col-sm-6 product_main">
  <h1>A Light in the Attic</h1>
  <p class="price_color">£51.77</p>
  <p class="instock availability">In stock (22 available)</p>
  <p class="star-rating Three"><i class="icon-star"></i></p>
</div>
<div id="product_gallery">
  <img alt="A Light in the Attic" src="../../media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg"/>
</div>
<table class="table table-striped">
  <tr><th>UPC</th><td>a897fe39b1053632</td></tr>
  <tr><th>Product Type</th><td>Books</td></tr>
  <tr><th>Price (excl. tax)</th><td>£51.77</td></tr>
  <tr><th>Price (incl. tax)</th><td>£51.77</td></tr>
  <tr><th>Tax</th><td>£0.00</td></tr>
  <tr><th>Availability</th><td>In stock (22 available)</td></tr>
  <tr><th>Number of reviews</th><td>0</td></tr>
</table>
</body>
</html>
```

`page_url = https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html`.

Ожидания от черновика, у которого имя было усечённым, sku None, category None:

- name `A Light in the Attic`;
- sku `a897fe39b1053632`;
- category `Poetry`;
- availability `in_stock` (фраза содержит `in stock`, число отзывов 0 рейтингом не становится);
- rating `3.0`;
- image `https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg`;
- price `51.77`.

### 13.5. `books_detail_himalayas.html`

```html
<!DOCTYPE html>
<html>
<body>
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="/">Books</a></li>
  <li><a href="#">Travel</a></li>
  <li class="active">It's Only the Himalayas</li>
</ul>
<div class="product_main">
  <h1>It's Only the Himalayas</h1>
  <p class="price_color">£45.17</p>
  <p class="star-rating Two"></p>
</div>
<div id="product_gallery">
  <img src="../../media/cache/himalayas.jpg"/>
</div>
<table class="table table-striped">
  <tr><th>UPC</th><td>c0ffee0000000001</td></tr>
  <tr><th>Availability</th><td>In stock (5 available)</td></tr>
</table>
</body>
</html>
```

SKU `c0ffee0000000001`, категория `Travel`, цена `45.17`, рейтинг `2.0`.

Для ветки «нет в наличии» отдельный файл не нужен: тест передаёт в `parse_books_detail` короткую строку HTML прямо из теста, таблица с `Availability` = `Out of stock`, и ждёт `out_of_stock`. Такой inline-HTML в юнит-тестах разрешён для краевых веток. Основные поля книг и ноутбуков проверяются файлами фикстур.

Для неизвестного класса рейтинга тест передаёт `<article class="product_pod">...</article>` со `p class="star-rating Ten"` и валидной ценой, и ждёт `rating is None` плюс warning в caplog.

### 13.6. `webscraper_laptops_page1.html`

Первая карточка специально содержит `span.old-price`, которого на живом сайте нет. Третья карточка без цены должна быть пропущена.

```html
<!DOCTYPE html>
<html>
<body>
<div class="card thumbnail" itemscope itemtype="https://schema.org/Product">
  <div class="product-wrapper card-body">
    <img alt="item" class="image" itemprop="image" src="/images/test-sites/e-commerce/items/cart2.png"/>
    <div class="caption">
      <h4 class="price float-end pull-right">
        <span itemprop="price">$416.99</span>
        <span class="old-price">$499.99</span>
      </h4>
      <h4>
        <a class="title" href="/test-sites/e-commerce/static/product/31" title="Packard 255 G2">Packard 255 G2</a>
      </h4>
    </div>
    <div class="ratings">
      <p data-rating="2"><span class="ws-icon ws-icon-star"></span><span class="ws-icon ws-icon-star"></span></p>
    </div>
  </div>
</div>
<div class="card thumbnail">
  <div class="product-wrapper card-body">
    <img alt="item" class="image" src="/images/test-sites/e-commerce/items/cart2.png"/>
    <div class="caption">
      <h4 class="price"><span itemprop="price">$306.99</span></h4>
      <h4><a class="title" href="/test-sites/e-commerce/static/product/32" title="Aspire E1-510">Aspire E1-510</a></h4>
    </div>
    <div class="ratings">
      <p data-rating="3"><span class="ws-icon ws-icon-star"></span></p>
    </div>
  </div>
</div>
<div class="card thumbnail">
  <div class="product-wrapper card-body">
    <h4><a class="title" href="/test-sites/e-commerce/static/product/99" title="No Price Laptop">No Price Laptop</a></h4>
  </div>
</div>
<ul class="pagination">
  <li class="page-item">
    <a class="page-link next" rel="next" href="/test-sites/e-commerce/static/computers/laptops?page=2">›</a>
  </li>
</ul>
</body>
</html>
```

`page_url = https://webscraper.io/test-sites/e-commerce/static/computers/laptops`.

Ожидания `YamlSource.parse_listing` на spec из `sources/webscraper_laptops.yaml`:

- 2 товара, третий пропущен;
- первый: имя `Packard 255 G2` (атрибут `title`), цена `416.99`, старая `499.99`, валюта `USD`, рейтинг `2.0`, категория `Laptops` (со страницы селектор `span.category` пуст, берётся статическая строка spec), sku None, наличие `unknown`;
- URL `https://webscraper.io/test-sites/e-commerce/static/product/31`;
- картинка `https://webscraper.io/images/test-sites/e-commerce/items/cart2.png`;
- второй: цена `306.99`, old_price None, рейтинг `3.0`;
- next `https://webscraper.io/test-sites/e-commerce/static/computers/laptops?page=2`.

### 13.7. `webscraper_laptops_page2.html`

```html
<!DOCTYPE html>
<html>
<body>
<div class="card thumbnail">
  <div class="product-wrapper card-body">
    <img class="image" src="/images/test-sites/e-commerce/items/cart2.png"/>
    <div class="caption">
      <h4 class="price"><span itemprop="price">$100.00</span></h4>
      <h4><a class="title" href="/test-sites/e-commerce/static/product/200" title="Page Two Laptop">Page Two Laptop</a></h4>
    </div>
    <div class="ratings">
      <p><span class="ws-icon ws-icon-star"></span><span class="ws-icon ws-icon-star"></span><span class="ws-icon ws-icon-star"></span><span class="ws-icon ws-icon-star"></span></p>
    </div>
  </div>
</div>
</body>
</html>
```

На этой карточке нет `data-rating`. Срабатывает `count_selector`: 4 звезды → рейтинг `4.0`. Next отсутствует.

Отдельный маленький тест со звёздами 0 и без атрибута (inline HTML из одной пустой `div.ratings`) ждёт `rating is None`.

### 13.8. `robots_disallow_private.txt`

```text
User-agent: *
Disallow: /private
```

---

## 14. План тестов

Каждая функция ниже существует с таким именем. Новых тестовых функций не добавлять: порог покрытия достигается этими сценариями, потому что они заходят в перечисленные ветки. Общие константы URL вынести в `tests/conftest.py`.

`tests/conftest.py`:

```python
FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixtures() -> Path:
    return FIXTURES

@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 11, 25, 22, 15, tzinfo=timezone.utc)
```

Плюс функция `read_fixture(name: str) -> str` (не тест).

`tests/fakes.py` — класс `FakeClient` как в разделе 8.6 по смыслу: словарь URL → HTML, словарь URL → исключение, список `calls`, метод `get_text`, поддержка `async with`. Неизвестный URL → `FetchError` со статусом 404.

Запуск, которым обязан проходить CI:

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov=priceparser --cov-report=term-missing --cov-fail-under=90
```

### 14.1. `test_prices.py`

- `test_parse_price_examples`: параметризация таблицы из раздела 6.1, включая три ошибки (`pytest.raises(ParseError)`).
- `test_parse_availability_in_stock`: `In stock (22 available)` → `IN_STOCK`.
- `test_parse_availability_out_before_in`: `not in stock` → `OUT_OF_STOCK`.
- `test_parse_availability_unknown`: `предзаказ` → `UNKNOWN`.
- `test_parse_availability_blank`: `None` и `"   "` → `UNKNOWN`.
- `test_parse_rating_numeric`: `"3"` → `3.0`, `"3,5"` → `3.5`, `"0"` → `0.0`.
- `test_parse_rating_out_of_range`: `"6"` и `"nope"` → None, в caplog есть `Рейтинг` или `рейтинг` (сравнение casefold).

### 14.2. `test_urls.py`

- `test_normalize_drops_fragment_and_trailing_slash`: `https://Example.com/a/b/#x` → `https://example.com/a/b`.
- `test_normalize_sorts_query`: `https://example.com/a?b=2&a=1` → `https://example.com/a?a=1&b=2`.
- `test_normalize_drops_default_port`: `https://example.com:443/a` → `https://example.com/a`, а `http://example.com:8080/a` сохраняет `:8080`.
- `test_product_key_prefers_sku`: черновик или Product с sku `AbC` даёт ключ `sku:books:abc`, URL при этом другой не влияет.
- `test_product_key_uses_url_when_sku_missing`: одинаковые URL с хвостовым слэшем и без него дают один ключ `url:books:...`.

Для сборки `Product` в тестах завести в `tests/fakes.py` фабрику `make_product(**overrides) -> Product` с заполненными обязательными полями (имя `Item`, цена `Decimal("10.00")`, валюта `USD`, url `https://example.com/p`, source_id `books`, `scraped_at=fixed`). Фабрика не считается тестовой функцией.

### 14.3. `test_books_parser.py`

- `test_listing_homepage_two_products_and_next` — ожидания раздела 13.1.
- `test_listing_category_relative_links` — ожидания 13.2, включая пропуск третьей карточки и `caplog` с `нет цены`.
- `test_listing_last_page_has_no_next` — фикстура page2, один товар, `next_url is None`.
- `test_categories_from_sidebar` — два имени и абсолютные URL.
- `test_detail_fills_sku_category_and_image` — фикстура attic поверх черновика с усечённым именем.
- `test_detail_out_of_stock_inline` — короткая таблица `Out of stock`.
- `test_unknown_star_class_sets_rating_none` — класс `Ten`, warning.

### 14.4. `test_yaml_source.py`

Загружать spec через `load_config` от временной копии или напрямую: тест может вызвать `YamlSourceConfig.model_validate(yaml.safe_load(path.read_text()))` на настоящем `sources/webscraper_laptops.yaml`, затем `YamlSource(source_id="laptops", spec=spec, max_pages=2)`.

- `test_parse_laptops_page_with_old_price_and_rating` — ожидания 13.6.
- `test_page_without_next_counts_stars` — фикстура page2, рейтинг `4.0`, `next_url is None`, категория `Laptops`.
- `test_zero_stars_without_attribute_is_none` — inline-карточка с пустым `div.ratings` и валидной ценой, рейтинг None.
- `test_static_category_used` — уже покрыто первым тестом (категория `Laptops`). Этот отдельный тест не про категорию, а про то, что явный `span.category` побеждает статическую строку: inline-карточка с `<span class="category">Gaming</span>`, ожидание `Gaming`. Имя теста оставить `test_selector_category_overrides_static`.

Итого в файле четыре теста: `test_parse_laptops_page_with_old_price_and_rating`, `test_page_without_next_counts_stars`, `test_zero_stars_without_attribute_is_none`, `test_selector_category_overrides_static`.

### 14.5. `test_dedup.py`

- `test_keeps_first_by_url`: два черновика с одним URL и разными именами, остаётся первый, счётчик 1.
- `test_sku_key_collapses_different_urls`: одинаковый sku, разные URL, остаётся первый.
- `test_no_duplicates_returns_same_length`: счётчик 0, тот же порядок.

### 14.6. `test_diff.py`

Собрать previous и current фабрикой:

- общий товар цена 100 → 110, имя `Up`, валюта USD (PRICE_UP, delta 10.00, pct 10.00);
- общий товар 50 → 40, имя `Down` (PRICE_DOWN, delta -10.00, pct -20.00);
- общий товар 5 → 5, имя `Same` (UNCHANGED, delta 0.00, pct 0.00);
- только в current, имя `Fresh` (NEW, delta None);
- только в previous, имя `Gone` (REMOVED).

Тесты:

- `test_kinds_and_counts`: пять счётчиков равны 1, в `changes` пять элементов.
- `test_sort_order`: имена в порядке Fresh, Gone, Up, Down, Same (ранг вида, внутри вида имя и так уникально).
- `test_percent_half_up`: предыдущая цена `Decimal("3.00")`, текущая `Decimal("4.00")` даёт pct `33.33` (4/3*100 = 133.333... минус 100 = 33.333 → `33.33`).
- `test_zero_old_price_percent_is_none`: предыдущая 0, текущая 0 → UNCHANGED, delta 0, pct None. Отдельная пара предыдущая 0, текущая 1 → PRICE_UP, pct None.
- `test_currency_mismatch_flag`: USD → GBP при той же логике роста, флаг True, валюта в строке равна текущей `GBP`.
- `test_sku_and_url_do_not_match`: предыдущий товар с sku `abc` и URL `/1`, текущий без sku и URL `/1`. Это NEW и REMOVED, не изменение цены. Тест фиксирует известное ограничение.

### 14.7. `test_export_csv.py`

- `test_bom_delimiter_headers_and_numbers`: три товара фабрикой, файл начинается с BOM, `csv.reader` (encoding utf-8-sig) даёт шапку `PRODUCT_HEADERS`, цена `10.00` строкой, наличие `В наличии` после того как фабрика по умолчанию `IN_STOCK`. Задать одному товару рейтинг `3` и увидеть `3.0`.
- `test_custom_delimiter`: delimiter `;`, в строке заголовка есть `;` и нет `,` между полями. Читать через `csv.reader(..., delimiter=";")`.
- `test_empty_products_header_only`: одна строка-шапка.
- `test_quotes_comma_in_name`: имя `Say "Hello", world`, чтение csv возвращает это имя без кавычек.
- `test_sorted_by_category_then_name`: категории как в разделе 10.3, порядок имён `A`, `B`, `A-without-category`.

Пять тестов. Наличие «Неизвестно» проверяется в xlsx-тесте, чтобы не раздувать список: в CSV-тесте сортировки один товар с `UNKNOWN`, и в его строке есть `Неизвестно`. Добавить эту проверку внутрь `test_sorted_by_category_then_name`, отдельную функцию не создавать.

### 14.8. `test_export_xlsx.py`

- `test_products_sheet_style_freeze_filter_widths_and_price_number`: два товара, проверки раздела 10.3. Первый по сортировке имеет цену `51.77` и URL, чтобы гиперссылка и число были в строке 2. Второй нужен ради зебры строки 3.
- `test_changes_sheet_omits_unchanged`: передать полный `DiffReport.changes` из набора раздела 14.6, `include_unchanged=False`. На листе `Изменения` 4 строки данных, текста `Без изменений` нет. Проверить pct `10` у строки роста и подпись `Новый`.
- `test_changes_sheet_includes_unchanged_when_asked`: 5 строк данных, цвет шрифта у `Без изменений` заканчивается на `666666`.
- `test_changes_only_workbook`: `export_changes_xlsx`, имена листов ровно `["Изменения"]`.
- `test_empty_products_header_and_filter`: `auto_filter.ref == "A1:L1"`, `freeze_panes == "A2"`.
- `test_currency_mismatch_yes`: одна `PriceChange` с `currency_mismatch=True`, ячейка `Да`.

Шесть тестов. Цвета видов NEW и PRICE_UP проверить внутри `test_changes_sheet_omits_unchanged`: найти строку по тексту подписи и сравнить цвет.

### 14.9. `test_config.py`

Писать временные YAML в `tmp_path`. Рядом класть крошечный валидный yaml источника, когда тип `yaml`.

- `test_load_example_resolved_paths`: скопировать `config.example.yaml` и `sources/webscraper_laptops.yaml` в tmp, поправить `config_file` если нужно (при копии обоих с сохранением относительного пути `sources/...` просто создать ту же структуру). `load_config` возвращает два источника, `books.max_pages == 1`, `books.fetch_details is True`, `laptops.fetch_details is False`, `output_dir` равен `(tmp / "output").resolve()`.
- `test_paths_are_relative_to_config_dir`: конфиг лежит в `tmp/nested/config.yaml` с `output_dir: out`. Резолв `tmp/nested/out`, а не `cwd/out`. Запускать тест так, чтобы cwd был `tmp`, не `nested`.
- `test_missing_file`: `ConfigError`.
- `test_invalid_yaml`: текст `[[` → `ConfigError`.
- `test_duplicate_source_id`: два `books` → `ConfigError`.
- `test_unknown_type`: `type: shop` → `ConfigError`.
- `test_books_requires_currency`: нет currency → `ConfigError`.
- `test_yaml_rejects_fetch_details`: `fetch_details: true` у yaml → `ConfigError` с подстрокой `карточки`.
- `test_yaml_file_missing`: `config_file` указывает в пустоту → `ConfigError`.
- `test_extra_field_forbidden`: ключ `proxy: 1` → `ConfigError`.
- `test_source_max_pages_null_means_unlimited`: у источника `max_pages: null`, у корня `max_pages: 2`, в результате у источника None.
- `test_omitted_max_pages_inherits`: ключа нет, у источника оказывается 2.

Двенадцать тестов.

### 14.10. `test_robots.py`

`fetch` — обычная async-функция, которую тест подсовывает в `RobotsCache.allowed`. Она считает вызовы.

- `test_disallow_rule`: тело из фикстуры `robots_disallow_private.txt`, статус 200. URL `https://example.com/private/x` → False, `https://example.com/ok` → True.
- `test_404_allows_all`: статус 404, любой путь True.
- `test_500_denies_all`: статус 500, путь `/ok` False.
- `test_respect_false_allows_without_fetch`: счётчик fetch остаётся 0.
- `test_cache_fetches_robots_once`: два `allowed` на один origin, fetch вызван один раз.

Пять тестов. Для 500 проверить, что повторный `allowed` не вызывает fetch ещё раз (кэш запрета). Эту проверку включить в `test_500_denies_all`, не отдельным тестом.

### 14.11. `test_http_client.py`

`MockTransport` и внедрённые `sleeper`, `monotonic`, `jitter=lambda: 0.0`. Клиент открывать через `async with`.

Часы теста:

```python
state = {"t": 0.0}

async def sleeper(seconds: float) -> None:
    state["t"] += seconds
    sleeps.append(seconds)

def monotonic() -> float:
    return state["t"]
```

Настройки собирать маленьким `HttpSettings` в тесте: `max_retries=3`, `backoff_base_seconds=0.5`, `backoff_max_seconds=8`, `delay_seconds=1`, `concurrency=1`, `respect_robots=False`, пока тест не про robots, `timeout_seconds=5`, `retry_statuses=(429, 500, 502, 503, 504)`, любой непустой user agent.

- `test_retry_then_success_backoff`: два ответа 500, затем 200 с телом `ok`. `get_text` возвращает `ok`. `sleeps == [0.5, 1.0]`.
- `test_retry_exhausted`: три ответа 500, `FetchError`, `exc.status == 500`, в `sleeps` ровно два элемента (после последней попытки не спят).
- `test_404_no_retry`: один вызов транспорта, `FetchError.status == 404`, `sleeps == []`.
- `test_retry_after_capped`: первый ответ 429 с заголовком `Retry-After: 100`, второй 200. При потолке 8 сон равен `8.0`.
- `test_delay_between_requests`: `respect_robots=False`, два URL одного хоста, оба 200, `delay_seconds=1`. `sleeps == [1.0]`.
- `test_robots_denied_does_not_get_page`: `respect_robots=True`. Транспорт: `/robots.txt` отдаёт фикстуру disallow `/private`; запрос на `/private/item` не должен случиться (счётчик путей). `get_text` бросает `RobotsDenied`. Запрос на `/ok` возвращает тело.
- `test_timeout_retried`: первый вызов транспорта бросает `httpx.TimeoutException("slow")`, второй отвечает 200. Текст получен, один сон `0.5`.

Семь тестов.

Замечание по MockTransport: он не ходит в сеть. `httpx.TimeoutException` конструируется как `httpx.TimeoutException("slow")`. Если эта сигнатура в 0.28.1 потребует request-объект, бросать `httpx.ReadTimeout("slow")` — это подкласс `TimeoutException`. Тест ловит поведение клиента, не тип конструктора: исключение, которое бросает transport, должно быть экземпляром `httpx.TimeoutException`.

### 14.12. `test_crawl.py`

Собрать `BooksToScrapeSource` руками, без конфига: `source_id="books"`, `start_url="https://books.toscrape.com/"`, `currency="GBP"`, `categories=("Travel",)`, `max_pages=1`, `fetch_details=True`.

Страницы `FakeClient`:

- `https://books.toscrape.com/` → `books_home.html`;
- `https://books.toscrape.com/catalogue/category/books/travel_2/index.html` → `books_travel.html`;
- URL карточки Гималаев → `books_detail_himalayas.html`;
- URL второй книги → `books_detail_himalayas.html` тоже можно, но лучше отдать короткий валидный detail с другим UPC `dddddddddddd0002`, inline-строкой в словаре страниц (это всё ещё фикстура-данные, не файл; разрешено). Либо одну общую detail-страницу: тест тогда проверяет, что sku второй книги тоже заполнился, и не требует уникальности. Чтобы второй дедуп не склеил книги, UPC должны различаться. Вторая страница — inline HTML с UPC `dddddddddddd0002` и крошками Travel.

Тесты:

- `test_books_collect_travel_only_with_details`: в `calls` есть главная и Travel, нет URL Mystery, нет `page-2.html` (лимит 1). Два товара. У Гималаев sku `c0ffee0000000001`, категория `Travel`, цена `45.17`. `pages_fetched == 1`, `detail_pages_fetched == 2`, `page_errors == 0`. `scraped_at` обоих равен `fixed_now`, для этого monkeypatch `priceparser.clock.utc_now`.
- `test_max_pages_two_follows_second_page`: `max_pages=2`, `fetch_details=False`, в calls есть page-2, товаров 3 (2+1), `pages_fetched == 2`.
- `test_failed_category_does_not_drop_previous`: две категории `("Travel", "Mystery")`. Mystery URL есть в сайдбаре главной. В FakeClient страница Mystery отсутствует (404 FetchError). Travel при этом собран, `page_errors == 1`, товары Travel на месте. Порядок категорий в конструкторе: Travel, затем Mystery.
- `test_missing_category_raises`: категория `("Cookbook",)` → `ParseError`, в тексте `Cookbook` и `Travel`.
- `test_yaml_stops_at_max_pages`: YamlSource с живым spec, `max_pages=1`, FakeClient с page1 и page2. Вызов `collect` возвращает 2 товара, page2 не в `calls`.
- `test_cycle_guard`: подменить не нужно отдельно, если page1 next указывает на саму себя. Сделать крошечный spec и HTML, где `a[rel=next]` ведёт на тот же URL. `pages_fetched == 1`, функция завершается (не зависает). Таймаут теста стандартный. Это тест `test_cycle_guard`.

Шесть тестов. Лимит страниц yaml и цикл — оба в `test_crawl.py`, не в `test_yaml_source.py`.

Для цикла spec можно собрать `YamlSourceConfig.model_validate` словарём в тесте, без файла. Селекторы те же, что у ноутбуков, `start_urls` один.

### 14.13. `test_storage.py`

- `test_roundtrip_snapshot_decimal_and_datetime`: сохранить снимок с ценой `Decimal("51.77")` и `fixed_now`, прочитать, цена равна `Decimal("51.77")`, `scraped_at` равен `fixed_now`, в сыром тексте файла есть `"51.77"` и `2026-11-25T22:15:00+00:00`, нет `51.7700000001`.
- `test_run_id_collision_suffix`: дважды `make_run_id` с одним временем после записи первого пустого файла через `save_snapshot` (или просто `path.write_text("{}")` — но `make_run_id` смотрит на `exists()`, так что достаточно создать пустой файл по предсказанному пути). Второй id заканчивается на `-2`.
- `test_list_and_latest_pair`: файлы `20261125T221500Z.json`, `20261125T221501Z.json` и мусор `notes.json`. `list_snapshots` длиной 2, мусора нет. `latest_pair` возвращает эти два в хронологическом порядке.
- `test_ignores_missing_dir`: нет каталога, `list_snapshots` возвращает `[]`, `latest_pair` возвращает None.
- `test_load_bad_json_raises`: файл `{` → `ExportError`.

Пять тестов. Warning про `product_count` проверить внутри roundtrip-теста не надо. Добавить расхождение в `test_load_bad_json` нельзя. Вместо этого в `test_roundtrip_snapshot_decimal_and_datetime` после чтения вручную не проверять warning. Отдельный шестой тест **разрешён**, потому что ветка warning иначе останется без покрытия и может уронить 90%: `test_product_count_mismatch_warns`. Он читает валидный JSON, в котором `product_count` равен 5 при одном товаре, и проверяет warning. Итого шесть тестов в файле. Это единственное разрешённое добавление к спискам раздела 14: данный тест и никакие другие.

### 14.14. `test_cli.py`

`CliRunner` из `typer.testing`. В каждом тесте `monkeypatch.chdir(tmp_path)`, кроме тех, где путь и так абсолютный.

Конфиг для офлайн-run: минимальный YAML books с `categories: ["Travel"]`, `max_pages: 1`, `fetch_details: true`, `runs_dir` и `output_dir` внутри tmp. `build_client` подменён на функцию, которая возвращает `FakeClient` с теми же страницами, что в `test_books_collect_travel_only_with_details`. Часы подменены.

- `test_version`: `version` и `--version`, stdout содержит `price-catalog-parser 0.1.0`, код 0.
- `test_help`: `--help`, код 0, stdout содержит `Парсер каталогов и цен`.
- `test_validate_ok`: пример конфига, скопированный в tmp вместе с sources, stdout `Конфиг корректен: 2 источников`.
- `test_validate_bad_exit_2`: пустой файл, код 2.
- `test_sources_lists_ids`: stdout содержит `books` и `laptops` и `books_toscrape`.
- `test_run_books_offline_writes_files`: код 0, существует один json в `data/runs/books`, один xlsx, один csv. xlsx открывается, лист `Товары`, товаров 2. stdout содержит `Источник: books`, `Ошибки страниц: 0`, `Сравнение: предыдущий снимок не найден`, `Готово. Источников: 1, с ошибками: 0.` CSV начинается с BOM.
- `test_run_diff_auto_adds_sheet`: сначала записать предыдущий снимок руками `save_snapshot` с одним товаром Гималаев по цене `40.00` и тем же sku `c0ffee0000000001`, и второй товар которого нет в новом прогоне (REMOVED). Затем `run`. Код 0. В xlsx есть лист `Изменения`. Есть строка, где цена выросла (45.17 против 40), и строка `Пропавший`. stdout содержит `цена выросла` и `пропавших`.
- `test_run_diff_on_without_previous_exit_1`: `--diff on`, предыдущего файла нет, код 1, stdout содержит `Сравнение: ошибка, предыдущий снимок не найден`, json снимка при этом создан.
- `test_run_unknown_source_exit_2`: `--source nope`, код 2, файлов в output нет.
- `test_export_snapshot`: взять json из офлайн-run (или собрать `save_snapshot`), вызвать `export --format csv`, код 0, появился csv, сеть не нужна (клиент не патчить: если команда его вызовет, теста упадёт на отсутствии сети только если FakeClient не подставлен; команда `export` не должна звать `build_client`. Дополнительно патч `build_client` на функцию, которая бросает `AssertionError`, чтобы регрессия всплыла).
- `test_diff_command`: два снимка в `runs_dir`, вызов без путей, код 0, stdout содержит `Новых:` и `Файл:`, xlsx существует, лист `Изменения`.
- `test_strict_stops_second_source`: конфиг из двух источников. Первый `books` с категорией `Cookbook` (упадёт). Второй `laptops` yaml. `--strict`. Патч клиента: у ноутбуков страницы нет, и если бы источник стартовал, `calls` получил бы URL ноутбуков. Ожидание: код 1, URL ноутбуков в `calls` нет, stdout `с ошибками: 1` (второй не стартовал, провален только первый; `N` равен 2, `M` равен 1). Уточнение числа: выбранных источников 2, проваленных 1, второй не запускался и в проваленные не пишется. `Готово. Источников: 2, с ошибками: 1.`
- `test_format_csv_writes_changes_file`: есть предыдущий снимок, `--format csv`, код 0, xlsx товаров нет, csv есть, файл `*-changes.xlsx` есть, в stdout есть `Файл изменений:`.
- `test_both_fetch_flags_exit_2`: код 2, stderr содержит `только один`.

Четырнадцать тестов. `test_version` считает один тест и внутри вызывает runner дважды.

### 14.15. Что не тестировать

- Живой books.toscrape.com и webscraper.io.
- Dockerfile в pytest.
- Внешний вид шрифта Calibri в самом Excel (достаточно атрибутов openpyxl).
- Гонку семафора на настоящей нагрузке. Тест паузы последовательный, `concurrency=1`.

---

## 15. CI

Файл `.github/workflows/ci.yml` целиком:

```yaml
name: CI

on:
  push:
    branches: ["main"]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: test (${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"

      - name: Ruff
        run: |
          ruff check .
          ruff format --check .

      - name: Mypy
        run: mypy src

      - name: Pytest
        run: pytest --cov=priceparser --cov-report=term-missing --cov-fail-under=90
```

Других workflow нет. Секретов нет. Python 3.13 в матрицу не добавлять.

Локальная проверка перед коммитом — те же четыре команды, что в разделе 14.

---

## 16. Docker, gitignore, расписание

### 16.1. `Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY sources ./sources
COPY config.example.yaml ./config.example.yaml

RUN pip install --no-cache-dir . \
    && mkdir -p /app/output /app/data/runs \
    && chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/output", "/app/data"]

ENTRYPOINT ["priceparser"]
CMD ["--help"]
```

### 16.2. `.dockerignore`

```text
.git
.venv
venv
output
data/runs
tests
.pytest_cache
.mypy_cache
.ruff_cache
**/__pycache__
**/*.pyc
```

Образ не копирует тесты. Конфиг заказчика монтируется снаружи, в образ не запекается ничего, кроме примера и `sources/webscraper_laptops.yaml`.

Команды для README:

```bash
docker build -t priceparser .
docker run --rm \
  -v "$PWD/output:/app/output" \
  -v "$PWD/data:/app/data" \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/sources:/app/sources:ro" \
  priceparser run --config /app/config.yaml
```

Каталоги `output` и `data` на хосте должны существовать и быть доступны на запись пользователю, под которым запускается Docker. Если том смонтирован как root-only, процесс `appuser` (uid 10001) не запишет файл: в README одна фраза, что каталоги нужно создать и отдать в запись uid 10001, либо запускать из среды, где это уже так. Не переключать образ на root ради удобства.

### 16.3. Дополнение `.gitignore`

Существующий файл не переписывать. В конец добавить:

```gitignore

# priceparser runtime
output/
data/runs/*
!data/runs/.gitkeep
```

### 16.4. Расписание

Кода планировщика нет. В README есть два готовых примера: cron на хосте и cron, который вызывает `docker run`. Оба запускаются раз в неделю, в понедельник в 09:00, потому что для витрины цен этого достаточно и это вежливее ежечасного опроса. Пользователь может поменять расписание сам.

---

## 17. Текст `README.md` дословно

Заменить корневой `README.md` на текст внутри забора из четырёх тильд ниже. Строки забора в файл не входят. Внутри нет ссылок на картинки: бинарные скриншоты в репозиторий не класть, чтобы README не показывал битые изображения. Раздел «Как выглядит результат» описывает листы так, чтобы заказчик понял выгрузку без PNG.

Если у сопровождающего позже появятся три снимка экрана, их можно положить в `docs/screenshots/` и дописать картинки отдельным коммитом. Имена, если этот коммит когда-нибудь случится:

1. `docs/screenshots/cli-run.png` — терминал с блоком `Источник:` и строкой `Готово`.
2. `docs/screenshots/excel-products.png` — лист «Товары»: синяя шапка, строка фильтра, закреплена первая строка, цена выровнена как число.
3. `docs/screenshots/excel-changes.png` — лист «Изменения»: подписи «Новый», «Пропавший», «Цена выросла», «Цена упала» разными цветами.

В этой реализации каталог `docs/screenshots/` не создавать.

Ниже текст README открыт забором из четырёх тильд, потому что внутри есть свои блоки кода. В `README.md` переносятся только строки между забором. Сам забор и фраза «Конец дословного README» в файл не входят.

~~~~markdown
# Парсер цен и каталогов в Excel

Учебный проект Стефана Митрохина ([StefanMitrokhin](https://github.com/StefanMitrokhin)).

Задача, которую он закрывает: «спарсите цены конкурентов в Excel». Программа открывает каталог, собирает товары и сохраняет таблицу, которую можно сразу открыть в Excel или отдать в Google Sheets. Повторный запуск сравнивает цены с прошлым разом.

Это портфолио, не универсальный паук. В комплекте два сайта, которые специально опубликованы для практики парсинга:

- [books.toscrape.com](https://books.toscrape.com/) — книжный каталог;
- [учебный магазин webscraper.io](https://webscraper.io/test-sites/e-commerce/static/computers/laptops) — ноутбуки.

Цены на этих сайтах вымышленные. Обхода защит, логинов и прокси здесь нет. Чужой магазин подключается только если его владелец не против автоматического сбора, а `robots.txt` это разрешает. Как добавить сайт, написано ниже.

## Что попадает в таблицу

По каждому товару:

- название;
- цена числом и отдельная колонка валюты;
- старая цена, если на сайте она есть (на учебных сайтах её обычно нет);
- наличие: «В наличии», «Нет в наличии» или «Неизвестно»;
- категория;
- рейтинг по шкале от 0 до 5;
- артикул, если он указан на карточке;
- ссылка на товар и ссылка на картинку;
- источник и время снимка в UTC.

Повтор одного и того же товара на нескольких страницах схлопывается. В файле остаётся первое вхождение.

## Как выглядит результат

Команда пишет три вещи:

- `output/<источник>-<время>.xlsx` — книга Excel;
- `output/<источник>-<время>.csv` — тот же список, UTF-8 с BOM, чтобы русская шапка открылась в Excel;
- `data/runs/<источник>/<время>.json` — снимок для следующего сравнения.

Лист **Товары**:

- синяя шапка белым жирным шрифтом, фильтр включён, первая строка закреплена;
- ширина колонок задана, длинные ссылки не сжимают цену;
- цена и старая цена — числа с двумя знаками, не текст. В Excel по ним можно сортировать и считать сумму;
- ссылка на товар кликабельна.

Лист **Изменения** появляется со второго прогона:

- «Новый» — товара не было в прошлый раз;
- «Пропавший» — был и исчез;
- «Цена выросла» и «Цена упала» — с разницей в деньгах и в процентах;
- строки без изменения цены в лист не попадают. Их можно добавить флагом `--include-unchanged`.

CSV нужен, когда таблицу забирает другая программа. Разделитель по умолчанию — запятая. Если Excel в русской локали сваливает всё в один столбец, запустите с `--csv-delimiter ';'`.

Сравнение идёт внутри одного источника. Товар узнаётся по артикулу, а если артикула нет — по ссылке. Для книг артикул (UPC) появляется только когда включён заход в карточку (`fetch_details`). Оба прогона нужно делать в одном режиме, иначе книга без артикула и та же книга с артикулом будут выглядеть как разные товары.

## Быстрый старт

Нужен Python 3.11 или новее.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml
priceparser validate --config config.yaml
priceparser run --config config.yaml
```

На Windows виртуальное окружение включается так: `.venv\Scripts\activate`.

Пример конфига специально короткий: категория Travel на books.toscrape.com, одна страница списка, заход в карточки за артикулом, и одна страница ноутбуков. Между запросами пауза 1 секунда. Прогон вежливый и занимает немного времени.

Проверка без установки пакета в систему:

```bash
python -m priceparser version
```

Полезные команды:

```bash
priceparser sources --config config.yaml
priceparser run --config config.yaml --source books --max-pages 1 --fetch-details
priceparser diff --config config.yaml --source books
priceparser export --snapshot data/runs/books/<файл>.json --format xlsx
```

`validate` и `sources` в сеть не ходят. `export` пересобирает таблицу из уже скачанного снимка.

Полный вывод `run` выглядит так (числа зависят от сайта):

```text
Источник: books
Страниц каталога: 1
Страниц карточек: 11
Товаров: 11 (дублей отброшено: 0)
Ошибки страниц: 0
Снимок: data/runs/books/20261125T221500Z.json
Excel: output/books-20261125T221500Z.xlsx
CSV: output/books-20261125T221500Z.csv
Сравнение: предыдущий снимок не найден

Готово. Источников: 1, с ошибками: 0.
```

Со второго раза строка «Сравнение» покажет, сколько товаров появилось, пропало и у скольких изменилась цена.

## Конфиг

Файл `config.yaml`. Пути внутри него (`output_dir`, `runs_dir`, `config_file`, `log_file`) считаются от папки, где лежит сам конфиг, а не от места, откуда вы вызвали команду.

Верхний уровень задаёт вежливость: User-Agent, таймаут, число попыток, паузу, параллелизм, уважение к `robots.txt`, каталоги вывода. У каждого источника свой `id`, его тип и лимит страниц.

`max_pages` ограничивает страницы списков, а не карточки товаров. `null` снимает лимит. В примере лимит стоит намеренно.

Лог пишется в stderr. Уровень меняется ключом `log_level` или флагом `--log-level`. Файл лога включается ключом `log_file`.

## Как добавить сайт

Два пути. Ядро, Excel и CLI трогать не нужно.

### Вариант 1. YAML с селекторами

Подходит, если товары видны в обычном HTML и список страниц идёт ссылкой «дальше». Образец — `sources/webscraper_laptops.yaml`.

В конфиге:

```yaml
sources:
  - id: shop
    type: yaml
    enabled: true
    config_file: sources/shop.yaml
    max_pages: 2
```

В `sources/shop.yaml` задаются стартовые URL, валюта из трёх букв, CSS-селектор карточки, селекторы полей и селектор ссылки на следующую страницу. Необязательное поле (`optional: true`) не роняет прогон, если на сайте его нет. Обязательны название, ссылка и цена.

Валюта берётся из файла источника, а не угадывается по значку. Так `£` и `$` не перепутаются.

Такой источник читает только страницы списков. В карточку товара он не заходит.

Перед боевым прогоном посмотрите `robots.txt`. Если путь запрещён, программа пропустит его и напишет об этом в лог. Отключать проверку (`respect_robots: false`) имеет смысл только на сайте, который вы сами контролируете.

### Вариант 2. Класс-адаптер

Нужен, когда у сайта своя пагинация или артикул лежит на отдельной странице. Образец — `src/priceparser/sources/books_toscrape.py`.

1. Новый файл в `src/priceparser/sources/`.
2. Класс с методом `collect`, который возвращает `CollectResult`.
3. Ветка в `create_source` (`src/priceparser/sources/registry.py`).
4. Новое имя типа в модели `SourceEntry`.
5. Фикстура HTML и тесты без сети.

Разбор страницы держите чистой функцией от строки HTML. Сеть остаётся в `collect`.

## Расписание

Отдельной службы в программе нет. Её запускает планировщик операционной системы, когда вам нужно свежее сравнение.

Раз в неделю, в понедельник в 09:00, из виртуального окружения:

```cron
0 9 * * 1 cd /path/to/price-catalog-parser && /path/to/price-catalog-parser/.venv/bin/priceparser run --config config.yaml >> output/cron.log 2>&1
```

Тот же ритм через Docker:

```cron
0 9 * * 1 docker run --rm -v /path/to/price-catalog-parser/output:/app/output -v /path/to/price-catalog-parser/data:/app/data -v /path/to/price-catalog-parser/config.yaml:/app/config.yaml:ro -v /path/to/price-catalog-parser/sources:/app/sources:ro priceparser run --config /app/config.yaml >> /path/to/price-catalog-parser/output/cron.log 2>&1
```

Каждый запуск сам найдёт предыдущий снимок и допишет лист «Изменения».

## Docker

Образ собирается на Python 3.12 и запускается от пользователя `appuser` (uid 10001).

```bash
docker build -t priceparser .
mkdir -p output data
docker run --rm \
  -v "$PWD/output:/app/output" \
  -v "$PWD/data:/app/data" \
  -v "$PWD/config.yaml:/app/config.yaml:ro" \
  -v "$PWD/sources:/app/sources:ro" \
  priceparser run --config /app/config.yaml
```

Каталоги `output` и `data` должны быть доступны на запись uid 10001. Иначе процесс внутри контейнера не сохранит файл.

Справка по командам: `docker run --rm priceparser --help`.

## Разработка

```bash
pip install -e ".[dev]"
ruff check .
ruff format --check .
mypy src
pytest --cov=priceparser --cov-report=term-missing --cov-fail-under=90
```

Тесты читают сохранённый HTML из `tests/fixtures` и не открывают сайты. GitHub Actions гоняет те же проверки на Python 3.11 и 3.12.

## Ограничения

- Учебные сайты иногда лежат. Повтор запроса помогает при сетевой ошибке, но не при выключенном хосте.
- Вёрстка демо-сайта может измениться. Тогда обновляются адаптер и фикстуры вместе. Тесты ловят расхождение с фикстурой, а не с живой страницей.
- Страницы, которые собираются только в браузере через JavaScript, не поддерживаются.
- Сравнение не сопоставляет товары с разных сайтов и не конвертирует валюты. Если валюта в двух снимках разная, строка всё равно строится, а в колонке «Валюты различаются» стоит «Да».
- Цена в Excel записывается числом с плавающей точкой с двумя знаками. Для цен каталога этого достаточно.

## Лицензия

MIT. См. файл `LICENSE`.
~~~~

Конец дословного README. В файле репозитория перевод строки в конце есть, маркера «Конец» нет.

---

## 18. Описание репозитория и topics

Сделать после того, как код уже в `main` (в этом плановом PR описание не менять, если нет прав; шаг стоит в чеклисте реализации).

Описание (GitHub About), одна строка:

```text
Парсер цен и каталогов с выгрузкой в Excel и CSV. Демо на учебных сайтах.
```

Topics, все сразу:

- `python`
- `web-scraping`
- `price-parser`
- `excel`
- `openpyxl`
- `portfolio`
- `beautifulsoup`
- `asyncio`
- `cli`

Команда, если установлен `gh` от имени владельца:

```bash
gh repo edit StefanMitrokhin/price-catalog-parser \
  --description "Парсер цен и каталогов с выгрузкой в Excel и CSV. Демо на учебных сайтах." \
  --add-topic python \
  --add-topic web-scraping \
  --add-topic price-parser \
  --add-topic excel \
  --add-topic openpyxl \
  --add-topic portfolio \
  --add-topic beautifulsoup \
  --add-topic asyncio \
  --add-topic cli
```

Если `gh` нет, то же самое вбивается в About репозитория руками. На реализацию кода это не влияет.

---

## 19. Чеклист реализации

Делать сверху вниз. Не перескакивать: каждый шаг оставляет тесты зелёными для уже написанного кода. Коммит на шаг — нормально. В сообщениях коммитов писать, что сделано, без приписок про инструменты.

Общий критерий готовности в конце раздела. Пока он не выполнен, работа не закончена.

### Шаг 1. Каркас пакета

Сделать `pyproject.toml` из раздела 4, пустые модули с `__version__`, `errors.py`, `clock.py`, `py.typed`, `data/runs/.gitkeep`. Дописать `.gitignore`. Установить `pip install -e ".[dev]"`.

Приёмка: `import priceparser` печатает `0.1.0`; `ruff check .` и `mypy src` проходят; `priceparser version` ещё можно не проверять.

### Шаг 2. Деньги, URL, модели

`models.py`, `prices.py`, `urls.py` и тесты `test_prices.py`, `test_urls.py`, фабрика в `tests/fakes.py`.

Приёмка: тесты этих двух файлов зелёные. `Product` отвергает naive datetime и отрицательную цену (это можно не выделять в отдельный тест: валидатор вызывается фабрикой, а отрицательная цена покрыта `parse_price`). Добавить в `test_prices.py` ничего сверх списка. Если mypy ругается на фабрику, чинить аннотации, не ослабляя strict.

### Шаг 3. Конфиг

`config.py`, оба YAML-файла примера, `test_config.py`.

Приёмка: 12 тестов конфига зелёные. `priceparser validate` можно подключить на шаге 11; сейчас достаточно прямого `load_config`.

### Шаг 4. Разбор books и YAML без сети

`html_utils.py`, `books_toscrape.py` (чистые функции; `collect` можно оставить незакрытым заглушкой, которая бросает `NotImplementedError`, только если mypy и покрытие это переживут — нет, не оставлять заглушку: `collect` пишется на шаге 8). На этом шаге реализуются `parse_books_listing`, `parse_books_detail`, `parse_books_categories` и `YamlSource.parse_listing` вместе с `_extract`. Метод `collect` у обоих классов реализовать тонкой обёрткой уже на шаге 8. Чтобы пакет импортировался, методы `collect` на шаге 4 могут звать `walk_listings`, даже если тест `collect` ещё не написан.

Проще для приёмки: на шаге 4 написать парсеры и их тесты, а `collect` реализовать полностью, но без отдельного теста до шага 8. Покрытие просядет до шага 8 и это нормально: порог 90% обязателен в CI в конце, не после каждого шага. Локально после шага 4 зелёные `test_books_parser.py` и `test_yaml_source.py`.

Приёмка: ожидания разделов 13.1–13.7 выполняются этими тестами. Фикстуры скопированы байт-в-байт из раздела 13 (пробелы внутри элементов, которые `get_text` схлопывает, на цену и имя не влияют; всё же копировать тексты файлов как в плане, чтобы diff фикстур не гулял).

### Шаг 5. Дедуп и diff

`dedup.py`, `diff.py`, тесты.

Приёмка: тесты раздела 14.5 и 14.6 зелёные, проценты совпадают с указанными Decimal.

### Шаг 6. Экспорт

`export_csv.py`, `export_xlsx.py`, тесты.

Приёмка: BOM у CSV проверяется байтами `path.read_bytes()[:3] == b"\xef\xbb\xbf"`. Цвета openpyxl сравниваются так, как написано в разделе 10.3. Если openpyxl 3.1.5 отдаёт цвет объектом без `.rgb`, читать `str(color.rgb)` только когда атрибут есть; тест должен падать понятным assert, а не AttributeError. Реализацию подстроить под реальный объект openpyxl этой версии, ожидаемые RGB не менять.

### Шаг 7. Снимки

`storage.py` и `test_storage.py`, включая `test_product_count_mismatch_warns`.

Приёмка: круглый путь денег и дат из раздела 8.11.

### Шаг 8. HTTP, robots, обход

`robots.py`, `http_client.py`, `crawl.py`, метод `collect` у обоих источников, `registry.py`, тесты `test_robots.py`, `test_http_client.py`, `test_crawl.py`.

Приёмка: семь тестов HTTP, пять robots, шесть crawl. Цикл пагинации завершается. Mystery не скачивается, когда просят Travel. `FakeClient` используется вместо сети.

### Шаг 9. CLI

`cli.py`, `logging_setup.py`, `__main__.py`, `test_cli.py`.

Приёмка: 14 тестов CLI. `build_client` подменяется. Команда `export` не создаёт HTTP-клиент. Тексты stdout совпадают с разделом 9, включая `Готово. Источников: 2, с ошибками: 1.` в тесте `--strict`.

### Шаг 10. Docker, README, CI, гигиена

`Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, замена `README.md` текстом раздела 17, дописанный `.gitignore`.

Приёмка:

- `ruff check .`, `ruff format --check .`, `mypy src` без ошибок;
- `pytest --cov=priceparser --cov-report=term-missing --cov-fail-under=90` проходит локально на той версии Python, которая стоит в среде (3.11 или 3.12);
- в README нет картинок и нет маркеров из плана;
- `LICENSE` не изменён (`git diff -- LICENSE` пустой);
- `docs/PLAN.md` не изменён реализацией;
- `docker build` в чеклист приёмки CI не входит. Если в среде есть Docker, собрать образ и выполнить `docker run --rm priceparser version`, ожидание `price-catalog-parser 0.1.0`. Если Docker нет, написать это в итоге PR и не имитировать успех.

### Шаг 11. Описание GitHub

Команда из раздела 18. Если нет прав на `gh repo edit`, шаг считается выполненным, когда команда и список topics приведены в тексте PR. На код это не блокер.

### Критерий готовности целиком

1. Дерево файлов совпадает с разделом 3. Лишних модулей нет.
2. `config.example.yaml` и `sources/webscraper_laptops.yaml` совпадают с разделом 7.
3. Все тесты раздела 14 существуют под своими именами и проходят.
4. Покрытие пакета `priceparser` не ниже 90% при `branch = true`.
5. ruff и mypy чистые на 3.11 и, в CI, на 3.12.
6. `priceparser run` на фиктивном клиенте пишет xlsx с листами «Товары» и, со второго снимка, «Изменения», и CSV с BOM.
7. README — клиентский текст из раздела 17.
8. В коде нет ключей, паролей, обращений к боевым магазинам и отключения robots по умолчанию.

---

## 20. Риски и вопросы

### 20.1. Риски, которые остаются даже при точной реализации

1. **Живая вёрстка уедет от фикстур.** Тесты останутся зелёными, а `run` по настоящему сайту начнёт писать «не найдено товаров». Это сигнал обновить селекторы и фикстуры одним коммитом, а не прикручивать «угадайку». books.toscrape.com годами стабилен, но гарантии нет. webscraper.io уже отличается от старых статей в интернете: цена лежит в `span[itemprop=price]`, рейтинг в `p[data-rating]`, не в устаревших классах Bootstrap 3 из блогов 2018 года. Селекторы в этом плане сняты 2026-11-25.

2. **webscraper.io ужесточит `robots.txt`.** Сейчас `/test-sites/e-commerce/` разрешён, а часть других тестовых путей запрещена. Если запрет расширят на e-commerce, программа обязана пропустить страницы и завершить источник с ошибкой страниц. Обходить запрет нельзя. Демо тогда держится на books и на любом другом YAML, который пользователь имеет право качать.

3. **books.toscrape.com иногда не отвечает.** Три попытки с паузой это не лечат, если хост лежит час. Для портфолио достаточно, что ошибка видна в логе и код выхода равен 1, когда товаров нет.

4. **Полный каталог книг долгий.** 1000 карточек при паузе 1 секунда — это больше 15 минут только на паузах, плюс страницы списков. Пример конфига поэтому режет категорию и `max_pages`. Это не баг скорости.

5. **Ключ SKU против URL.** Включённый в одном прогоне и выключенный в другом `fetch_details` ломает сравнение книг: одна и та же книга станет «пропавшей» и «новой». Поведение выбрано сознательно и описано в README. Чинить нечёткой склейкой по имени нельзя: имена повторяются, а проект обещает предсказуемый ключ.

6. **Деньги во float внутри xlsx.** `Decimal` живёт в снимке и в CSV. В ячейке Excel лежит float. Для цен с двумя знаками в пределах каталога расхождение на двоичное представление отсекается форматом ячейки. Не переходить на хранение цены строкой: тогда сломается сортировка числом, а это обещание заказчику.

7. **Русская локаль Excel и CSV.** BOM решает кириллицу. Разделитель запятая может не подойти Excel, у которого десятичный разделитель — запятая, и он ждёт `;`. Флаг `--csv-delimiter` это закрывает. Менять умолчание на `;` нельзя: так файл хуже открывается в локали с точкой и в скриптах.

8. **mypy strict и библиотеки.** У bs4, lxml, yaml, openpyxl в конфиге `ignore_missing_imports`. Если у установленного openpyxl объявятся несовместимые типы, чинится наш вызов, а не отключение strict на весь пакет. Дополнительные `ignore` не добавлять пачкой.

9. **Порог покрытия 90% с учётом веток.** Если в конце не хватает 1–2 пунктов, закрывать ветку тестом из уже описанного файла, расширяя существующую функцию, а не заводя восьмой вид источника. Если ветка в принципе не нужна, удалить её из кода, а не помечать `pragma: no cover` без причины. `pragma: no cover` допустим только на защитных ветках, которые в разделе 11 названы «не перехватывать» (`KeyboardInterrupt`) — таких строк в коде нет, так что pragma скорее всего не понадобится.

10. **Docker и права на том.** uid 10001 не запишет в каталог, принадлежащий root. README это говорит. Не чинить переходом на `USER root`.

11. **CI не собирает Docker.** Сломанный Dockerfile может приехать зелёным CI. Шаг 10 просит локальную сборку, если демон есть.

12. **hatchling и src-layout.** Если конфиг колеса из раздела 4 на hatchling 1.33.0 положит пакет не туда, правится только секция сборки, пока `import priceparser` не укажет на `src/priceparser`. Зависимости из-за этого не менять.

13. **Конструктор `httpx.TimeoutException` в тесте.** В 0.28.1 удобнее бросать из транспорта `httpx.ReadTimeout`. Смысл теста — что клиент повторяет подкласс `TimeoutException`. Если и `ReadTimeout` нельзя создать без request, допустимо определить в тесте `_Boom(httpx.TimeoutException)` и бросить его. Поведение клиента не менять.

14. **Параллельные карточки и порядок.** `asyncio.gather` сохраняет порядок задач. Второй дедуп идёт по этому порядку. Тест с двумя карточками не должен зависеть от того, какая закончила HTTP первой: порядок gather равен порядку черновиков.

15. **Случайный jitter.** В бою он есть (0–0.05 с), в тестах он выключен. Не «стабилизировать» бой удалением jitter: короткие синхронные залпы хуже для чужого хоста. Не увеличивать его до долей секунды молча.

### 20.2. Вопросы, которые не блокируют работу

Ответы уже даны. Реализатор не останавливается, чтобы их переспросить.

| Вопрос | Ответ, которого придерживаться |
| --- | --- |
| Нужен ли настоящий магазин заказчика в этом репозитории? | Нет. Только два учебных сайта. Новый магазин — отдельное согласие владельца сайта и отдельная задача. |
| Делать ли скриншоты в первый PR с кодом? | Нет. README описывает листы словами. |
| Какой разделитель CSV по умолчанию? | Запятая, флаг для точки с запятой. |
| Ставить ли Python 3.13 в CI? | Нет, только 3.11 и 3.12. |
| Нужен ли lock-файл? | Нет. |
| Писать ли цены в Excel текстом, чтобы не было float? | Нет, число с форматом `#,##0.00`. |
| Обходить ли запрет robots на время демо? | Нет. |
| Сравнивать ли товары разных источников в одной книге? | Нет. Один прогон — один источник в своих файлах. Команда `run` без `--source` последовательно пишет отдельные файлы. |
| Нужна ли колонка описания товара? | Нет. Поля перечислены в целях, описание webscraper.io не сохраняется. |
| Качать ли все 50 категорий книг в примере? | Нет, в примере одна категория Travel и одна страница. |

### 20.3. Что считать багом реализации, а не вопросом

- Тест ходит в сеть.
- Селекторы books или YAML расходятся с разделом 13, и тест фикстуры падает.
- В xlsx цена лежит строкой.
- В CSV нет BOM или шапка на английском.
- `--diff auto` падает, если старого снимка нет.
- YAML-источник молча ходит в карточки.
- Относительный `output_dir` считается от cwd, хотя он задан в конфиге.
- В репозиторий попал файл из `output/` или `data/runs/*.json`.
- `LICENSE` изменён.
- Появился третий сайт, Scrapy, Playwright или база данных.

Исправление такого расхождения — привести код к этому документу. Документ во время реализации не переписывать «под то, что вышло».
