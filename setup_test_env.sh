#!/bin/bash
# Secure API key caching for testing session
# This script sets up environment variables for the current testing session only

echo "================================================"
echo "Setting up secure testing environment"
echo "================================================"

# Fetch and export API keys for current session
echo "Fetching OpenAI API key from 1Password..."
export OPENAI_API_KEY=$(op item get tyrupcepa4wluec7sou4e7mkza --fields "api key" --reveal)

if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Failed to retrieve OpenAI API key"
    exit 1
fi

echo "✅ OpenAI API key loaded (${OPENAI_API_KEY:0:10}...)"

# Optional: Also fetch Anthropic key if needed
echo "Fetching Anthropic API key from 1Password..."
export ANTHROPIC_API_KEY=$(op read "op://API/Anthropic/api key")

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  Warning: Failed to retrieve Anthropic API key"
else
    echo "✅ Anthropic API key loaded (${ANTHROPIC_API_KEY:0:10}...)"
fi

echo ""
echo "================================================"
echo "Environment ready for testing!"
echo "================================================"
echo ""
echo "SECURITY REMINDERS:"
echo "  • These keys are only in this shell session"
echo "  • Keys will be cleared when you close the terminal"
echo "  • Don't leave terminal unattended"
echo "  • Run 'unset OPENAI_API_KEY ANTHROPIC_API_KEY' when done"
echo ""
echo "You can now run:"
echo "  poetry run uvicorn nexus.api.storyteller:app --port 8000 --reload"
echo "  python test_structured_output.py"
echo "  python test_gpt5_api.py"
echo ""
echo "To clear keys immediately:"
echo "  source clear_test_env.sh"