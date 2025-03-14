#!/bin/bash

# Script to fix the direnv setup for Poetry

# Print header
echo "===================================================="
echo "   Fixing direnv setup for Poetry environment"
echo "===================================================="

# Change to project directory
PROJECT_DIR="/Users/pythagor/nexus"
cd "$PROJECT_DIR"

# Create Poetry environment if it doesn't exist
echo "Ensuring Poetry environment is created..."
poetry install

# Get actual poetry environment path
POETRY_ENV_PATH=$(poetry env info --path)

if [ -z "$POETRY_ENV_PATH" ]; then
    echo "Error: Could not determine Poetry environment path."
    echo "Try running 'poetry install' manually."
    exit 1
fi

echo "Poetry environment found at: $POETRY_ENV_PATH"

# Create a new .envrc file with the correct path
echo "Updating .envrc file..."

cat > .envrc << EOL
# Automatically activate Poetry environment
if [ -d "$POETRY_ENV_PATH" ]; then
  source "$POETRY_ENV_PATH/bin/activate"
else
  echo "Poetry environment not found. Run 'poetry install' first."
fi
EOL

# Allow the new .envrc file
echo "Allowing direnv to use the updated .envrc file..."
direnv allow

echo "===================================================="
echo "   direnv setup fixed!"
echo "===================================================="
echo "Next steps:"
echo "1. Run 'cd ..' and then 'cd $PROJECT_DIR' to test the automatic activation"
echo "2. You should no longer see the 'No such file or directory' error"
echo ""
echo "If it still doesn't work, you may need to manually create the environment:"
echo "poetry install && poetry shell"
echo "Then exit the shell and try 'cd ..' and 'cd $PROJECT_DIR' again."
