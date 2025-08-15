#!/bin/bash
# Start NEXUS UI - Backend API and React Frontend

echo "🚀 Starting NEXUS UI System..."
echo "================================"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get local IP for network access
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")

echo -e "${BLUE}📡 Starting Backend API Server...${NC}"
echo "   Local:   http://localhost:8000"
echo "   Network: http://${LOCAL_IP}:8000"

# Start backend in background
cd /Users/pythagor/nexus
poetry run uvicorn nexus_api:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
echo -e "${YELLOW}⏳ Waiting for backend to initialize...${NC}"
sleep 5

echo -e "\n${GREEN}🎨 Starting React UI...${NC}"
echo "   Local:   http://localhost:5173"
echo "   Network: http://${LOCAL_IP}:5173"

# Start frontend
cd /Users/pythagor/nexus/iris

# Update .env with current IP if needed
echo "VITE_API_URL=http://${LOCAL_IP}:8000" > .env.development.local

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 Installing frontend dependencies...${NC}"
    npm install
fi

echo -e "\n${GREEN}✨ NEXUS UI Ready!${NC}"
echo "================================"
echo "🖥️  Access from this machine:  http://localhost:5173"
echo "📱  Access from other devices: http://${LOCAL_IP}:5173"
echo ""
echo "Press Ctrl+C to stop both servers"

# Run frontend (this blocks)
npm run dev -- --host 0.0.0.0

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM