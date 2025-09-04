#!/usr/bin/env bash
# Start the Letta server configured for the NEXUS PostgreSQL database.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/letta_config.env"

echo "Using PostgreSQL database '$LETTA_PG_DB' on $LETTA_PG_HOST:$LETTA_PG_PORT as user '$LETTA_PG_USER'"

letta server --port "${LETTA_SERVER_PORT:-8283}" --host "${LETTA_SERVER_HOST:-0.0.0.0}"

