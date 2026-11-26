# The h2open backend: FastAPI on Python 3.14, dependencies installed by uv
# exactly as locked in uv.lock.
#
# Build and run with docker compose from the repo root:
#   docker compose up -d --build backend

FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.14-alpine AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
RUN uv sync --locked --no-dev

FROM python:3.14-alpine
# UID 1000 matches the usual first user on the server, so files mounted
# from secrets/ (chmod 600) stay readable without loosening permissions.
ARG UID=1000
RUN adduser -D -u "${UID}" h2open
WORKDIR /app
COPY --from=build --chown=h2open:h2open /app /app
COPY logging.json /app/logging.json
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
USER h2open
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/health', timeout=2)"
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
