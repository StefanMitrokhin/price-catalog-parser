from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from priceparser.models import Product, ProductDraft


def normalize_url(url: str) -> str:
    """Ключ для дедупа и diff. Фрагмент убирается, хост в нижнем регистре."""
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


def product_key_parts(source_id: str, url: str, sku: str | None) -> str:
    """Построить ключ идентичности товара по источнику, URL и SKU."""
    if sku is not None and sku.strip():
        return f"sku:{source_id}:{sku.strip().casefold()}"
    return f"url:{source_id}:{normalize_url(url)}"


def product_key(product: Product) -> str:
    """Ключ идентичности для готового товара."""
    return product_key_parts(product.source_id, product.url, product.sku)


def draft_key(draft: ProductDraft) -> str:
    """Ключ идентичности для черновика товара."""
    return product_key_parts(draft.source_id, draft.url, draft.sku)


def is_http_url(url: str) -> bool:
    """Проверить, что строка — абсолютный HTTP(S) URL."""
    parts = urlsplit(url.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc)