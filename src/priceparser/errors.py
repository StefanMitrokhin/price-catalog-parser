from __future__ import annotations


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
