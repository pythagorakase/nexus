#!/bin/bash

# Script to set up direnv for automatic Poetry environment activation
# For Night City Stories project

# Print header
echo "===================================================="
echo "   Setting up direnv for automatic environment activation"
echo "===================================================="

# Install direnv if not already installed
if ! command -v direnv &> /dev/null; then
    echo "Installing direnv..."
    brew install direnv
else
    echo "✓ direnv is already installed"
fi

# Check which shell is being used
SHELL_TYPE=$(basename "$SHELL")

# Add direnv hook to shell configuration if not already present
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

# Create .envrc file in the project directory
PROJECT_DIR="/Users/pythagor/nexus"
cd "$PROJECT_DIR"

if [ ! -f ".envrc" ]; then
    echo "Creating .envrc file in $PROJECT_DIR..."
    cat > .envrc << EOL
# Automatically activate Poetry environment when entering this directory
use_poetry() {
  source $(poetry env info --path)/bin/activate
}

use_poetry
EOL
    echo "✓ Created .envrc file"
else
    echo "✓ .envrc file already exists"
fi

# Allow the direnv configuration
echo "Allowing direnv to use the .envrc file..."
direnv allow

echo "===================================================="
echo "   direnv setup complete!"
echo "===================================================="
echo "Next steps:"
echo "1. Close and reopen your terminal (or run 'source $CONFIG_FILE')"
echo "2. Navigate to your project directory: cd $PROJECT_DIR"
echo "3. Your Poetry environment should activate automatically!"
echo ""
echo "To verify it's working, check that your prompt changes when"
echo "you enter the project directory, or run 'which python' to"
echo "confirm it's using the Poetry environment's Python."
echo ""
echo "Note: If it doesn't work immediately, you may need to restart"
echo "your terminal for shell changes to take effect."
