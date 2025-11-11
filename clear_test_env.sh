#!/bin/bash
# Clear cached API keys from environment

echo "Clearing cached API keys..."

unset OPENAI_API_KEY
unset ANTHROPIC_API_KEY

echo "✅ API keys cleared from environment"
echo ""
echo "Security check - these should be empty:"
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:-[cleared]}"
echo "  ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-[cleared]}"