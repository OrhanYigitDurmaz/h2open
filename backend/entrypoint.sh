#!/bin/sh
# Commands for the backend container:
#   serve     migrate the database, then run the API (the default)
#   migrate   only migrate the database
#   anything else is run as is, e.g. python -m app.cli create-user ...
set -eu

case "${1:-serve}" in
serve)
    alembic upgrade head
    # One process only: it also runs the outbox dispatcher and the phone
    # call handling, and two of those would ring every phone twice.
    exec uvicorn app.main:app \
        --host "${BACKEND_HOST:-127.0.0.1}" --port "${BACKEND_PORT:-8000}" \
        --workers 1 --proxy-headers --no-server-header \
        --log-config /app/logging.json
    ;;
migrate)
    exec alembic upgrade head
    ;;
*)
    exec "$@"
    ;;
esac
