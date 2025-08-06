#!/bin/bash

# Script to set up a Python virtual environment with direnv integration
# For Night City Stories project

# Print header
echo "===================================================="
echo "   Setting up Python environment with direnv"
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
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created at $VENV_DIR"
else
    echo "✓ Virtual environment already exists at $VENV_DIR"
fi

# Ensure direnv is installed
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

# Create a simple .envrc file that activates the venv
echo "Creating .envrc file..."
cat > .envrc << EOL
# Activate Python virtual environment
source_env() {
  if [ -f "\$1" ]; then
    source "\$1"
  fi
}

source_env "$VENV_DIR/bin/activate"
EOL

# Allow the direnv configuration
echo "Allowing direnv to use the .envrc file..."
direnv allow

# Install required packages
echo "Installing required packages..."
source "$VENV_DIR/bin/activate"

# Install key packages (adjust as needed)
pip install -U pip
pip install numpy pandas scikit-learn torch transformers sentence-transformers chromadb openai 

echo "===================================================="
echo "   Python environment setup complete!"
echo "===================================================="
echo "Next steps:"
echo "1. Close and reopen your terminal (or run 'source $CONFIG_FILE')"
echo "2. Navigate to your project directory: cd $PROJECT_DIR"
echo "3. Your Python environment should activate automatically!"
echo ""
echo "To verify it's working, check that your prompt includes '(.venv)' when"
echo "you enter the project directory, or run 'which python' to"
echo "confirm it's using the virtual environment's Python."
echo ""
echo "To install additional packages, navigate to your project directory and use:"
echo "pip install package-name"
