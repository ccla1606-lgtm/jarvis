FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system jarvis \
    && useradd --system --gid jarvis --create-home jarvis

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && chown -R jarvis:jarvis /app

USER jarvis

EXPOSE 8000

CMD ["sh", "-c", "python -m jarvis.infrastructure.migrations && exec uvicorn jarvis.api:app --host 0.0.0.0 --port 8000"]
