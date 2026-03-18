#!/bin/bash
# Start RPA Complexity Assessment Agent (API + Frontend)
# This script starts both the FastAPI backend and Streamlit frontend

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  RPA Complexity Assessment Agent - Full Stack Startup  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Project Root:${NC} $PROJECT_ROOT"
echo -e "${YELLOW}PYTHONPATH:${NC} $PYTHONPATH"
echo ""

cd "$PROJECT_ROOT"

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"

    # Kill API server
    if [ ! -z "$API_PID" ]; then
        echo "Stopping API server (PID: $API_PID)..."
        kill $API_PID 2>/dev/null
    fi

    # Kill Streamlit
    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Stopping Streamlit frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID 2>/dev/null
    fi

    echo -e "${GREEN}✓ All services stopped${NC}"
    exit 0
}

# Set trap to catch Ctrl+C
trap cleanup INT TERM

# ═══════════════════════════════════════════════════════════
# START API SERVER
# ═══════════════════════════════════════════════════════════

echo -e "${BLUE}[1/2]${NC} Starting FastAPI backend server..."
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 > /tmp/api_server.log 2>&1 &
API_PID=$!
echo -e "${GREEN}✓${NC} API Server started (PID: $API_PID)"
echo -e "    📡 API URL: ${BLUE}http://localhost:8000${NC}"
echo -e "    📊 Health: ${BLUE}http://localhost:8000/api/health${NC}"
echo -e "    📚 Docs: ${BLUE}http://localhost:8000/docs${NC}"

# Wait for API to be ready
echo -e "${YELLOW}Waiting for API to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ API failed to start${NC}"
        echo "Check logs: cat /tmp/api_server.log"
        cleanup
    fi
    sleep 1
done

echo ""

# ═══════════════════════════════════════════════════════════
# START STREAMLIT FRONTEND
# ═══════════════════════════════════════════════════════════

echo -e "${BLUE}[2/2]${NC} Starting Streamlit frontend..."
uv run streamlit run frontend/app.py > /tmp/streamlit.log 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓${NC} Streamlit started (PID: $FRONTEND_PID)"

# Wait for Streamlit to be ready
echo -e "${YELLOW}Waiting for frontend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8502 > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Frontend is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Frontend failed to start${NC}"
        echo "Check logs: cat /tmp/streamlit.log"
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ FULL STACK RUNNING${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📱 FRONTEND:${NC}  ${BLUE}http://localhost:8502${NC}"
echo -e "${BLUE}⚙️  API:${NC}       ${BLUE}http://localhost:8000${NC}"
echo ""
echo -e "${YELLOW}Usage:${NC}"
echo "  1. Open http://localhost:8502 in your browser"
echo "  2. Upload a PDD file (PDF or DOCX)"
echo "  3. Wait for assessment (~2-5 minutes)"
echo "  4. Download Excel/PDF reports"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo "  API logs: tail -f /tmp/api_server.log"
echo "  Frontend logs: tail -f /tmp/streamlit.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Keep script running
wait
