#!/bin/bash
# API Key Caching Daemon
# This script caches API keys in a temporary file with automatic expiration

CACHE_DIR="/tmp/nexus_api_cache"
CACHE_DURATION=3600  # 60 minutes in seconds
OPENAI_CACHE="$CACHE_DIR/openai_key"
ANTHROPIC_CACHE="$CACHE_DIR/anthropic_key"

# Create secure cache directory
setup_cache() {
    mkdir -p "$CACHE_DIR"
    chmod 700 "$CACHE_DIR"  # Only current user can access
}

# Check if cache is still valid
is_cache_valid() {
    local cache_file=$1
    if [ ! -f "$cache_file" ]; then
        return 1  # No cache
    fi

    local cache_age=$(($(date +%s) - $(stat -f %m "$cache_file" 2>/dev/null || echo 0)))
    if [ $cache_age -gt $CACHE_DURATION ]; then
        return 1  # Cache expired
    fi
    return 0  # Cache valid
}

# Get OpenAI key (from cache or 1Password)
get_openai_key() {
    if is_cache_valid "$OPENAI_CACHE"; then
        cat "$OPENAI_CACHE"
    else
        echo "Fetching OpenAI key from 1Password (will cache for 60 minutes)..." >&2
        local key=$(op item get tyrupcepa4wluec7sou4e7mkza --fields "api key" --reveal)
        if [ $? -eq 0 ]; then
            echo "$key" > "$OPENAI_CACHE"
            chmod 600 "$OPENAI_CACHE"  # Secure the cached key
            echo "$key"
        else
            echo "Failed to retrieve OpenAI key" >&2
            return 1
        fi
    fi
}

# Get Anthropic key (from cache or 1Password)
get_anthropic_key() {
    if is_cache_valid "$ANTHROPIC_CACHE"; then
        cat "$ANTHROPIC_CACHE"
    else
        echo "Fetching Anthropic key from 1Password (will cache for 60 minutes)..." >&2
        local key=$(op read "op://API/Anthropic/api key")
        if [ $? -eq 0 ]; then
            echo "$key" > "$ANTHROPIC_CACHE"
            chmod 600 "$ANTHROPIC_CACHE"
            echo "$key"
        else
            echo "Failed to retrieve Anthropic key" >&2
            return 1
        fi
    fi
}

# Clear cache
clear_cache() {
    echo "Clearing API key cache..."
    rm -rf "$CACHE_DIR"
    echo "✅ Cache cleared"
}

# Main script
case "$1" in
    setup)
        setup_cache
        export OPENAI_API_KEY=$(get_openai_key)
        export ANTHROPIC_API_KEY=$(get_anthropic_key)
        echo "✅ API keys cached and exported for 60 minutes"
        echo "   OpenAI: ${OPENAI_API_KEY:0:10}..."
        echo "   Anthropic: ${ANTHROPIC_API_KEY:0:10}..."
        ;;
    clear)
        clear_cache
        unset OPENAI_API_KEY
        unset ANTHROPIC_API_KEY
        ;;
    openai)
        get_openai_key
        ;;
    anthropic)
        get_anthropic_key
        ;;
    *)
        echo "Usage: $0 {setup|clear|openai|anthropic}"
        echo ""
        echo "  setup     - Cache and export both API keys for 60 minutes"
        echo "  clear     - Clear the cache and unset environment variables"
        echo "  openai    - Get OpenAI key (from cache or 1Password)"
        echo "  anthropic - Get Anthropic key (from cache or 1Password)"
        echo ""
        echo "To use in your shell:"
        echo "  eval \$(./api_key_daemon.sh setup)"
        echo ""
        echo "Cache location: $CACHE_DIR"
        echo "Cache duration: $CACHE_DURATION seconds ($(($CACHE_DURATION / 60)) minutes)"
        ;;
esac