#!/usr/bin/env bash
# Start Letta server using PostgreSQL backend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/letta_config.env"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "Configuration file $CONFIG_FILE not found" >&2
  exit 1
fi

# Load environment variables
set -a
source "$CONFIG_FILE"
set +a

echo "Starting Letta server on ${LETTA_SERVER_HOST}:${LETTA_SERVER_PORT}"
echo "Connecting to PostgreSQL ${LETTA_PG_DB} at ${LETTA_PG_HOST}:${LETTA_PG_PORT} as ${LETTA_PG_USER}"
if [ -n "${LETTA_PG_URI:-}" ]; then
  echo "Using custom PG URI: ${LETTA_PG_URI}"
fi

exec letta server --port "${LETTA_SERVER_PORT}" --host "${LETTA_SERVER_HOST}"

