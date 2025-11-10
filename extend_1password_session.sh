#!/bin/bash
# Extend 1Password CLI session timeout for testing
# This approach keeps 1Password authenticated longer

echo "================================================"
echo "Extending 1Password Session for Testing"
echo "================================================"

# Sign in with extended session (30 minutes instead of default 10)
eval $(op signin --session-timeout 30m)

if [ $? -eq 0 ]; then
    echo "✅ 1Password session extended to 30 minutes"
    echo ""
    echo "You can now run commands without repeated biometric prompts for 30 minutes"
    echo "The API scripts will fetch keys from 1Password as needed"
    echo ""
    echo "No keys are cached in environment - more secure but slightly slower"
else
    echo "❌ Failed to extend 1Password session"
    echo "You may need to run: op signin"
fi