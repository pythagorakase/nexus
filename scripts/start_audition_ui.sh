#!/bin/bash
#
# Start Apex Audition UI development servers
#
# Launches both FastAPI backend and Vite frontend in parallel with live reload.
# Access the UI at http://localhost:5173

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Apex Audition UI...${NC}"

# Function to kill background processes on exit
cleanup() {
    echo -e "\n${GREEN}Shutting down servers...${NC}"
    kill $(jobs -p) 2>/dev/null || true
    exit
}
trap cleanup SIGINT SIGTERM

# Start FastAPI backend
echo -e "${BLUE}[1/2]${NC} Starting FastAPI backend on port 8000..."
cd "$(dirname "$0")/.."
poetry run uvicorn nexus.api.apex_audition:app --reload --port 8000 &
FASTAPI_PID=$!

# Wait a moment for FastAPI to start
sleep 2

# Start Vite frontend
echo -e "${BLUE}[2/2]${NC} Starting Vite dev server on port 5173..."
cd ui
npm run dev -- --host &
VITE_PID=$!

echo ""
echo -e "${GREEN}✓ Servers running:${NC}"
echo "  FastAPI: http://localhost:8000"
echo "  Vite UI: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for background processes
wait
