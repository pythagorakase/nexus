#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/letta_config.env" ]; then
  echo "Loading Letta configuration from $SCRIPT_DIR/letta_config.env"
  set -o allexport
  source "$SCRIPT_DIR/letta_config.env"
  set +o allexport
else
  echo "Configuration file letta_config.env not found" >&2
  exit 1
fi

echo "Starting Letta server using PostgreSQL at ${LETTA_PG_HOST}:${LETTA_PG_PORT}/${LETTA_PG_DB} as ${LETTA_PG_USER}"

echo "Letta will listen on ${LETTA_SERVER_HOST:-0.0.0.0}:${LETTA_SERVER_PORT:-8283}"

exec letta server --port "${LETTA_SERVER_PORT:-8283}" --host "${LETTA_SERVER_HOST:-0.0.0.0}"
