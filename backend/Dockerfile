FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini main.py ./
RUN useradd --uid 10001 --create-home hireagent \
    && mkdir -p storage/uploads storage/page_texts storage/exports storage/backups logs \
    && chown -R hireagent:hireagent storage logs
USER hireagent
EXPOSE 8000
CMD ["python", "main.py"]
