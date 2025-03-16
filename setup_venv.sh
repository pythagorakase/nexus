#!/bin/bash

# Comprehensive setup script for Letta project on Apple Silicon
# Sets up Python environment, PostgreSQL with pgvector, and direnv

# Fail on any error
set -e

# Print header
echo "===================================================="
echo "   Letta Development Environment Setup"
echo "===================================================="

# Change to project directory
PROJECT_DIR="/Users/pythagor/nexus"
cd "$PROJECT_DIR"

# Check Python version
PYTHON_VERSION=$(python3 --version)
echo "Using $PYTHON_VERSION"

# Create a virtual environment if it doesn't exist
VENV_DIR="$PROJECT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment with Python 3.11..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created at $VENV_DIR"
else
    echo "✓ Virtual environment already exists at $VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Update pip
echo "Updating pip..."
pip install --upgrade pip

# Install required Python packages
echo "Installing required Python packages..."
# Install packages that don't depend on PostgreSQL first
pip install wheel setuptools pip --upgrade

# Install PostgreSQL-related packages with proper path
echo "Installing psycopg2-binary with pg_config path..."
PG_CONFIG_PATH=$(which pg_config)
LDFLAGS="-L$(pg_config --libdir)" CPPFLAGS="-I$(pg_config --includedir)" pip install psycopg2-binary

# Install rest of the packages
pip install alembic pydantic sqlalchemy requests demjson3 tiktoken \
    numpy pandas scikit-learn torch transformers sentence-transformers \
    openai anthropic chromadb

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Installing PostgreSQL..."
    brew install postgresql@14
    
    # Start PostgreSQL service
    brew services start postgresql@14
    
    # Wait for PostgreSQL to start
    sleep 5
    
    echo "✓ PostgreSQL installed and started"
else
    echo "✓ PostgreSQL is already installed"
    # Ensure PostgreSQL is running
    if ! brew services list | grep postgresql | grep -q "started"; then
        echo "Starting PostgreSQL service..."
        brew services start postgresql
        sleep 5
    fi
fi

# Ensure PostgreSQL binaries are in PATH
POSTGRES_BIN_PATH=$(brew --prefix postgresql@14)/bin
echo "Adding PostgreSQL binaries to PATH: $POSTGRES_BIN_PATH"
export PATH="$POSTGRES_BIN_PATH:$PATH"

# Verify pg_config is accessible
if command -v pg_config &> /dev/null; then
    echo "✓ pg_config is in PATH"
else
    echo "⚠️ Warning: pg_config not found in PATH. Trying alternate PostgreSQL versions..."
    # Try with default PostgreSQL
    POSTGRES_DEFAULT_PATH=$(brew --prefix postgresql)/bin
    if [ -d "$POSTGRES_DEFAULT_PATH" ]; then
        export PATH="$POSTGRES_DEFAULT_PATH:$PATH"
        echo "Added default PostgreSQL binaries to PATH"
    fi
    
    if command -v pg_config &> /dev/null; then
        echo "✓ pg_config found now"
    else
        echo "Error: pg_config still not found. Please install PostgreSQL with Homebrew and try again."
        exit 1
    fi
fi

# Install pgvector extension if not already installed
if ! brew list | grep -q "pgvector"; then
    echo "Installing pgvector extension..."
    brew install pgvector
else
    echo "✓ pgvector extension is already installed"
fi

# Create database and user if they don't exist
echo "Setting up PostgreSQL database and user..."
if ! psql -lqt | cut -d \| -f 1 | grep -qw letta; then
    # Create user if not exists
    if ! psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='letta'" | grep -q 1; then
        createuser -s letta
        psql -c "ALTER USER letta WITH PASSWORD 'letta';"
    fi
    
    # Create database
    createdb -O letta letta
    
    # Enable pgvector extension
    psql -U letta -d letta -c "CREATE EXTENSION IF NOT EXISTS vector;"
    
    echo "✓ Database 'letta' created with user 'letta' and pgvector extension"
else
    echo "✓ Database 'letta' already exists"
    # Ensure pgvector extension is enabled
    psql -U letta -d letta -c "CREATE EXTENSION IF NOT EXISTS vector;"
fi

# Install direnv if not already installed
if ! command -v direnv &> /dev/null; then
    echo "Installing direnv..."
    brew install direnv
else
    echo "✓ direnv is already installed"
fi

# Add direnv hook to shell configuration if not already present
SHELL_TYPE=$(basename "$SHELL")

if [ "$SHELL_TYPE" = "zsh" ]; then
    CONFIG_FILE="$HOME/.zshrc"
    HOOK_CMD='eval "$(direnv hook zsh)"'
    
    if ! grep -q "direnv hook zsh" "$CONFIG_FILE"; then
        echo "Adding direnv hook to ~/.zshrc..."
        echo "" >> "$CONFIG_FILE"
        echo "# direnv hook for environment activation" >> "$CONFIG_FILE"
        echo "$HOOK_CMD" >> "$CONFIG_FILE"
    else
        echo "✓ direnv hook already in ~/.zshrc"
    fi
elif [ "$SHELL_TYPE" = "bash" ]; then
    CONFIG_FILE="$HOME/.bash_profile"
    HOOK_CMD='eval "$(direnv hook bash)"'
    
    if ! grep -q "direnv hook bash" "$CONFIG_FILE"; then
        echo "Adding direnv hook to ~/.bash_profile..."
        echo "" >> "$CONFIG_FILE"
        echo "# direnv hook for environment activation" >> "$CONFIG_FILE"
        echo "$HOOK_CMD" >> "$CONFIG_FILE"
    else
        echo "✓ direnv hook already in ~/.bash_profile"
    fi
else
    echo "Warning: Unknown shell type '$SHELL_TYPE'. Please manually add direnv hook."
    echo "For most shells, add this line to your shell configuration:"
    echo 'eval "$(direnv hook yourshell)"'
fi

# Create a .envrc file for automatic environment activation and Letta configuration
echo "Creating .envrc file with Letta configuration..."
cat > .envrc << EOL
# Activate Python virtual environment
source_env() {
  if [ -f "\$1" ]; then
    source "\$1"
  fi
}

source_env "$VENV_DIR/bin/activate"

# Letta database configuration
export LETTA_PG_URI="postgresql://letta:letta@localhost:5432/letta"
export LETTA_DEBUG=True

# LLM API keys (uncomment and fill in as needed)
# export OPENAI_API_KEY="your-openai-key"
# export ANTHROPIC_API_KEY="your-anthropic-key"
# export GROQ_API_KEY="your-groq-key"

# Anthropic API settings
# export ANTHROPIC_API_URL="https://api.anthropic.com"
# export ANTHROPIC_VERSION="2023-06-01"  # Update to latest version as needed

# Local LLM configuration (uncomment if using local LLMs)
# export VLLM_API_BASE="http://localhost:8000"
# export OLLAMA_BASE_URL="http://localhost:11434"

# llama.cpp server configuration for models from LM Studio
# export LETTA_LLM_ENDPOINT="http://localhost:8080"
# export LETTA_LLM_ENDPOINT_TYPE="llamacpp"
# LM Studio direct API (alternative to llama.cpp)
# export LETTA_LLM_ENDPOINT="http://localhost:1234/v1"
# export LETTA_LLM_ENDPOINT_TYPE="openai"

# Server configuration
export HOST="0.0.0.0"
export PORT="8283"

# Path configuration
export PYTHONPATH="\$PYTHONPATH:$PROJECT_DIR"

echo "🚀 Letta environment activated"
EOL

# Allow the direnv configuration
echo "Allowing direnv to use the .envrc file..."
direnv allow

# Create a helper script for running migrations
cat > run_migrations.sh << EOL
#!/bin/bash
# Run database migrations
cd $PROJECT_DIR
source $VENV_DIR/bin/activate
cd letta
alembic upgrade head
EOL

chmod +x run_migrations.sh

# Instructions for using llama.cpp with Metal support and LM Studio models
cat > setup_llamacpp.sh << EOL
#!/bin/bash
# Script to setup llama.cpp with Metal support for use with LM Studio models
set -e

# Clone llama.cpp repository
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Build with Metal support
make clean
CMAKE_ARGS="-DLLAMA_METAL=ON -DLLAMA_ACCELERATE=ON" make

echo "✅ llama.cpp compiled with Metal support"
echo ""
echo "LM Studio Model Paths:"
echo "Your models are located in: /Users/pythagor/.lmstudio/models/"
echo ""
echo "Starting the server with an LM Studio model:"
echo ""
echo "# For non-sharded models:"
echo "./server -m /Users/pythagor/.lmstudio/models/path-to-your-model.gguf -ngl 1 -c 4096 --port 8080"
echo ""
echo "# For sharded models (like your Llama-3.3-70B):"
echo "./server -m /Users/pythagor/.lmstudio/models/lmstudio-community/Llama-3.3-70B-Instruct-GGUF/Llama-3.3-70B-Instruct-Q6_K-00001-of-00002.gguf -ngl 1 -c 4096 --port 8080"
echo ""
echo "Then configure Letta to use this server by setting:"
echo "export LETTA_LLM_ENDPOINT='http://localhost:8080'"
echo "export LETTA_LLM_ENDPOINT_TYPE='llamacpp'"
EOL

chmod +x setup_llamacpp.sh

echo "===================================================="
echo "   Letta Development Environment Setup Complete!"
echo "===================================================="
echo ""
echo "✅ Python virtual environment created and activated"
echo "✅ PostgreSQL installed with pgvector extension"
echo "✅ Database 'letta' created with user 'letta'"
echo "✅ direnv configured for automatic environment activation"
echo ""
echo "Next steps:"
echo "1. Close and reopen your terminal (or run 'source $CONFIG_FILE')"
echo "2. Navigate to your project directory: cd $PROJECT_DIR"
echo "3. Clone the Letta repository into this directory"
echo "4. Run migrations: ./run_migrations.sh"
echo "5. (Optional) Setup llama.cpp with Metal support: ./setup_llamacpp.sh"
echo ""
echo "To start the Letta server after setup:"
echo "cd $PROJECT_DIR"
echo "letta server --host 0.0.0.0 --port 8283"
