#!/bin/bash

# PostgreSQL Debugging Script
# This will help diagnose and fix common PostgreSQL configuration issues

echo "======================================================"
echo "   PostgreSQL Configuration Diagnostic Tool"
echo "======================================================"

# Check if PostgreSQL is installed via Homebrew
echo "Checking PostgreSQL installation..."
if brew list | grep -q "postgresql"; then
    echo "✅ PostgreSQL is installed via Homebrew"
    
    # Check which version
    PG_VERSION=$(brew list | grep postgresql | grep -o '@.*' || echo "")
    if [ -z "$PG_VERSION" ]; then
        echo "   Using default PostgreSQL version"
        PG_PATH=$(brew --prefix postgresql)
    else
        echo "   Using PostgreSQL$PG_VERSION"
        PG_PATH=$(brew --prefix postgresql$PG_VERSION)
    fi
    
    echo "   Installation path: $PG_PATH"
else
    echo "❌ PostgreSQL is not installed via Homebrew"
    echo "   Installing PostgreSQL..."
    brew install postgresql@14
    PG_PATH=$(brew --prefix postgresql@14)
    echo "✅ PostgreSQL installed at: $PG_PATH"
fi

# Check if pg_config is in PATH
echo -e "\nChecking for pg_config..."
if command -v pg_config &> /dev/null; then
    echo "✅ pg_config found in PATH"
    echo "   Path: $(which pg_config)"
    echo "   Version: $(pg_config --version)"
else
    echo "❌ pg_config not found in PATH"
    echo "   Adding PostgreSQL binaries to PATH..."
    export PATH="$PG_PATH/bin:$PATH"
    
    if command -v pg_config &> /dev/null; then
        echo "✅ pg_config is now available"
        echo "   Path: $(which pg_config)"
    else
        echo "❌ Still can't find pg_config. This is a critical issue."
        echo "   Please try manually installing PostgreSQL: brew install postgresql"
        exit 1
    fi
fi

# Check if PostgreSQL service is running
echo -e "\nChecking if PostgreSQL service is running..."
if brew services list | grep postgresql | grep -q "started"; then
    echo "✅ PostgreSQL service is running"
else
    echo "❌ PostgreSQL service is not running"
    echo "   Starting PostgreSQL service..."
    brew services start postgresql || brew services start postgresql@14
    sleep 5
    
    if brew services list | grep postgresql | grep -q "started"; then
        echo "✅ PostgreSQL service started successfully"
    else
        echo "❌ Failed to start PostgreSQL service"
        echo "   Try manually starting with: brew services start postgresql"
    fi
fi

# Test PostgreSQL connection
echo -e "\nTesting PostgreSQL connection..."
if psql -d postgres -c "SELECT version();" &> /dev/null; then
    echo "✅ Successfully connected to PostgreSQL"
    POSTGRES_VERSION=$(psql -d postgres -c "SELECT version();" -t | xargs)
    echo "   Version: $POSTGRES_VERSION"
else
    echo "❌ Failed to connect to PostgreSQL"
    echo "   Check PostgreSQL logs: tail -f $(find $(brew --prefix)/var/log -name 'postgres*' | sort | tail -n 1)"
fi

# Check if pgvector extension is installed
echo -e "\nChecking for pgvector extension..."
if brew list | grep -q "pgvector"; then
    echo "✅ pgvector extension is installed"
else
    echo "❌ pgvector extension is not installed"
    echo "   Installing pgvector..."
    brew install pgvector
fi

# Display environment for installing psycopg2-binary
echo -e "\nEnvironment for installing psycopg2-binary:"
echo "Run the following command to install psycopg2-binary:"
echo "LDFLAGS=\"-L$(pg_config --libdir)\" CPPFLAGS=\"-I$(pg_config --includedir)\" pip install psycopg2-binary"

# Add PostgreSQL to PATH permanently
echo -e "\nTo add PostgreSQL to your PATH permanently, add this to your shell profile:"
if [ -f "$HOME/.zshrc" ]; then
    SHELL_PROFILE="$HOME/.zshrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_PROFILE="$HOME/.bash_profile"
else
    SHELL_PROFILE="your shell profile"
fi

echo "echo 'export PATH=\"$PG_PATH/bin:\$PATH\"' >> $SHELL_PROFILE"
echo -e "\nOr run this command to do it automatically:"
echo "echo 'export PATH=\"$PG_PATH/bin:\$PATH\"' >> $SHELL_PROFILE"

echo -e "\n======================================================"
echo "   PostgreSQL Diagnostic Complete"
echo "======================================================"
