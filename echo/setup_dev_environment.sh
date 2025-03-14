#!/bin/bash

# Night City Stories Development Environment Setup Script

# Fail on any error
set -e

# Ensure script is run with sufficient privileges
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run with sudo or as root" 
   exit 1
fi

# Print header
echo "===================================================="
echo "   Night City Stories Dev Environment Setup"
echo "===================================================="

# Check for Homebrew (macOS package manager)
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for M-series Macs
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/${SUDO_USER}/.zprofile
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Update Homebrew
brew update

# Install pyenv for Python version management
if ! command -v pyenv &> /dev/null; then
    echo "Installing pyenv..."
    brew install pyenv
    
    # Add pyenv initialization to shell profile
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> /Users/${SUDO_USER}/.zprofile
    echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> /Users/${SUDO_USER}/.zprofile
    echo 'eval "$(pyenv init --path)"' >> /Users/${SUDO_USER}/.zprofile
    echo 'eval "$(pyenv init -)"' >> /Users/${SUDO_USER}/.zshrc
fi

# Reload shell environment
source /Users/${SUDO_USER}/.zprofile
source /Users/${SUDO_USER}/.zshrc

# Install Python 3.11.x
echo "Installing Python 3.11..."
pyenv install 3.11.11
pyenv global 3.11.11

# Verify Python version
python3 --version

# Install poetry for dependency management
if ! command -v poetry &> /dev/null; then
    echo "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    
    # Add Poetry to PATH
    echo 'export PATH="/Users/${SUDO_USER}/.local/bin:$PATH"' >> /Users/${SUDO_USER}/.zprofile
fi

# Reload shell to ensure all paths are updated
source /Users/${SUDO_USER}/.zprofile
source /Users/${SUDO_USER}/.zshrc

# Create project directory
PROJECT_DIR="/Users/${SUDO_USER}/Projects/NightCityStories"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create pyproject.toml based on the requirements.txt
cat > pyproject.toml << EOL
[tool.poetry]
name = "night-city-stories"
version = "0.1.0"
description = "Narrative Intelligence System"
authors = ["Neil Gordon Clark <neilgordonclark@gmail.com>"]

[tool.poetry.dependencies]
python = "^3.11"
annotated-types = "0.7.0"
anyio = "4.8.0"
asgiref = "3.8.1"
backoff = "2.2.1"
bcrypt = "4.2.1"
chroma-hnswlib = "0.7.6"
chromadb = "0.6.3"
fastapi = "^0.115.8"
httpx = "^0.28.1"
huggingface-hub = "^0.29.1"
numpy = "^2.2.3"
openai = "^1.64.0"
opentelemetry-api = "^1.30.0"
pandas = "^2.2.3"
pydantic = "^2.10.6"
python-dotenv = "^1.0.1"
requests = "^2.32.3"
scikit-learn = "^1.6.1"
sentence-transformers = "^3.4.1"
torch = "^2.2.2"
transformers = "^4.49.0"
uvicorn = "^0.34.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
black = "^24.3.0"
mypy = "^1.9.0"
flake8 = "^7.0.0"
isort = "^5.13.2"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
EOL

# Create a basic README.txt
cat > README.txt << EOL
Night City Stories - Development Environment

Quick Start:
1. Ensure Python 3.11 is installed
2. Install Poetry: curl -sSL https://install.python-poetry.org | python3 -
3. Run poetry install to set up dependencies
4. Activate environment with poetry shell

Key Components:
- Context Management
- Memory Retrieval
- Narrative Generation
EOL

# Copy requirements.txt to project
cp /path/to/original/requirements.txt "$PROJECT_DIR/requirements.txt"

# Create .gitignore
cat > .gitignore << EOL
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Poetry
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Misc
.DS_Store
.env
*.log

# Machine Learning
*.pt
*.pth
*.onnx
EOL

# Install project dependencies
poetry install

# Set appropriate permissions
chown -R ${SUDO_USER}:staff "$PROJECT_DIR"

echo "===================================================="
echo "   Night City Stories Dev Environment Setup Complete"
echo "===================================================="
echo "Next steps:"
echo "1. cd ~/Projects/NightCityStories"
echo "2. poetry shell"
echo "3. Start developing!"