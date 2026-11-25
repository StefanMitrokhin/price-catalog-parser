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
