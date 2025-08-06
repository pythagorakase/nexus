#!/bin/bash
# Install pgvector extension for PostgreSQL

# Ensure script fails on error
set -e

echo "===== Installing pgvector extension for PostgreSQL ====="

# Check for Postgres.app
POSTGRES_APP_BIN="/Applications/Postgres.app/Contents/Versions"
if [ -d "$POSTGRES_APP_BIN" ]; then
    echo "Postgres.app detected"
    
    # Find the latest version
    LATEST_VERSION=$(ls -1 "$POSTGRES_APP_BIN" | sort -V | tail -1)
    if [ -n "$LATEST_VERSION" ]; then
        echo "Using Postgres.app version: $LATEST_VERSION"
        export PATH="$POSTGRES_APP_BIN/$LATEST_VERSION/bin:$PATH"
    fi
fi

# Check if PostgreSQL is running
pg_running=$(pg_isready 2>/dev/null && echo "yes" || echo "no")
if [ "$pg_running" != "yes" ]; then
    echo "Warning: PostgreSQL might not be running or the connection is not working."
    echo "continuing anyway - if you're using Postgres.app, please make sure it's running."
fi

# Get PostgreSQL version
echo "Detecting PostgreSQL version..."
PG_VERSION=$(psql -c "SHOW server_version;" -t 2>/dev/null || echo "")

if [ -z "$PG_VERSION" ]; then
    echo "Could not detect PostgreSQL version automatically."
    read -p "Please enter your PostgreSQL version (e.g., 14.0): " PG_VERSION
fi

PG_VERSION=$(echo $PG_VERSION | tr -d ' ' | cut -d '.' -f1,2)
echo "PostgreSQL version: $PG_VERSION"

# Install dependencies
echo "Installing dependencies..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    brew install postgresql@$PG_VERSION
    brew install cmake
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux (Ubuntu/Debian)
    sudo apt update
    sudo apt install -y postgresql-server-dev-$PG_VERSION make cmake gcc
fi

# Clone pgvector repository
echo "Cloning pgvector repository..."
TMP_DIR=$(mktemp -d)
cd $TMP_DIR
git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git
cd pgvector

# Build and install pgvector
echo "Building pgvector..."
make
echo "Installing pgvector..."
sudo make install

# Create SQL script for installing the extension
cat > create_extension.sql << EOF
-- Add pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add cosine similarity function (if needed)
CREATE OR REPLACE FUNCTION cosine_similarity(bytea, bytea) RETURNS float8
LANGUAGE SQL IMMUTABLE STRICT PARALLEL SAFE AS
$$
    SELECT 1 - (a <=> b) FROM (SELECT a::vector, b::vector FROM (VALUES (\\$1, \\$2)) AS t(a, b)) AS v
$$;

-- Create indexes on chunk_embeddings table
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model 
    ON chunk_embeddings (model);

-- Check if extension is installed correctly
SELECT TRUE as extension_installed FROM pg_extension WHERE extname = 'vector';
EOF

# Try to install in the default database
echo "Installing extension into PostgreSQL..."
# First try 'postgres' database
if psql -d postgres -f create_extension.sql 2>/dev/null; then
    echo "Successfully installed extension in 'postgres' database."
else
    # If that fails, ask the user for the database name
    echo "Could not install extension in 'postgres' database."
    read -p "Please enter your database name: " DB_NAME
    
    if [ -n "$DB_NAME" ]; then
        psql -d "$DB_NAME" -f create_extension.sql
    else
        echo "No database name provided. Skipping extension installation."
    fi
fi

echo "===== pgvector installation complete ====="
echo "You can now use vector operations in your PostgreSQL databases."
echo "If you want to install pgvector on a specific database, run:"
echo "psql -d YOUR_DATABASE -c 'CREATE EXTENSION vector;'"
echo "Don't forget to update your database.yml or settings to include the pgvector extension."

# Clean up
cd
rm -rf $TMP_DIR

exit 0