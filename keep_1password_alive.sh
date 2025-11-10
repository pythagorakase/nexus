#!/bin/bash
# Keep 1Password session alive by periodic access
# This prevents the session from timing out during development

echo "Keeping 1Password session alive..."
echo "Press Ctrl+C to stop"

while true; do
    # Touch the 1Password session every 8 minutes (before 10-minute timeout)
    op account get > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "$(date): Session refreshed ✓"
    else
        echo "$(date): Session expired, please re-authenticate"
        op signin
    fi
    sleep 480  # 8 minutes
done