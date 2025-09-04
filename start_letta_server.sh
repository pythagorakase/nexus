#!/usr/bin/env bash
set -e

# Load environment variables from letta_config.env
CONFIG_FILE="$(dirname "$0")/letta_config.env"
if [ -f "$CONFIG_FILE" ]; then
  echo "Loading configuration from $CONFIG_FILE"
  set -a
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  set +a
else
  echo "Configuration file not found: $CONFIG_FILE" >&2
  exit 1
fi

echo "Starting Letta server..."
echo "Using PostgreSQL at ${LETTA_PG_HOST}:${LETTA_PG_PORT}/${LETTA_PG_DB}"  

exec letta server --port "${LETTA_SERVER_PORT:-8283}" --host "${LETTA_SERVER_HOST:-0.0.0.0}"
