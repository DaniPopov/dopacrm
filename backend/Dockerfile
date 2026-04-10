FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

COPY pyproject.toml uv.lock alembic.ini ./
COPY backend/ ./backend/

RUN uv pip install --system -e .

# Run as non-root — any code vulnerability is contained to this user,
# not the entire container filesystem. Celery's "superuser privileges"
# warning also goes away.
RUN useradd --create-home --shell /bin/false app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/workspace/backend/app"]
