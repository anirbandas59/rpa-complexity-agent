# RPA Complexity Assessment Agent — Startup Guide

## Quick Start

The easiest way to start the entire system (API + Frontend) is:

```bash
cd /home/anirban/workspace/projects/rpa-complexity-agent
./run-frontend.sh
```

This single command will:
- ✅ Start the FastAPI backend server on port 8000
- ✅ Wait for the API to be ready
- ✅ Start the Streamlit frontend on port 8502
- ✅ Wait for the frontend to be ready
- ✅ Display helpful information
- ✅ Show real-time logs from both services

## What the Script Does

```
run-frontend.sh
    │
    ├── [1/2] Start FastAPI Backend
    │     │
    │     ├── uvicorn api.main:app --port 8000
    │     ├── Set PYTHONPATH automatically
    │     └── Wait for /api/health to respond
    │
    ├── [2/2] Start Streamlit Frontend
    │     │
    │     ├── streamlit run frontend/app.py
    │     ├── Set PYTHONPATH automatically
    │     └── Wait for http://localhost:8502 to load
    │
    └── Display URLs and instructions
```

## Output Example

```
╔════════════════════════════════════════════════════════╗
║  RPA Complexity Assessment Agent - Full Stack Startup  ║
╚════════════════════════════════════════════════════════╝

[1/2] Starting FastAPI backend server...
✓ API Server started (PID: 169912)
    📡 API URL: http://localhost:8000
    📊 Health: http://localhost:8000/api/health
    📚 Docs: http://localhost:8000/docs
Waiting for API to start...
✓ API is ready

[2/2] Starting Streamlit frontend...
✓ Streamlit started (PID: 169958)
Waiting for frontend to start...
✓ Frontend is ready

════════════════════════════════════════════════════════
✓ FULL STACK RUNNING
════════════════════════════════════════════════════════

📱 FRONTEND:  http://localhost:8502
⚙️  API:       http://localhost:8000

Usage:
  1. Open http://localhost:8502 in your browser
  2. Upload a PDD file (PDF or DOCX)
  3. Wait for assessment (~2-5 minutes)
  4. Download Excel/PDF reports

Logs:
  API logs: tail -f /tmp/api_server.log
  Frontend logs: tail -f /tmp/streamlit.log

Press Ctrl+C to stop all services
```

## Access the System

### 📱 Frontend (User Interface)
- **URL:** http://localhost:8502
- **Use for:** Uploading PDD files and viewing results

### ⚙️ API (Backend Services)
- **URL:** http://localhost:8000
- **Health Check:** http://localhost:8000/api/health
- **API Docs:** http://localhost:8000/docs (Swagger UI)
- **OpenAPI Schema:** http://localhost:8000/openapi.json

## Managing the Services

### Stop All Services
Press `Ctrl+C` in the terminal where `./run-frontend.sh` is running.

This will:
- Stop the Streamlit frontend
- Stop the FastAPI backend
- Clean up log files
- Display confirmation

### View Logs
While the script is running, open another terminal:

**API Server Logs:**
```bash
tail -f /tmp/api_server.log
```

**Streamlit Frontend Logs:**
```bash
tail -f /tmp/streamlit.log
```

### Run Services Separately (Advanced)

If you need to run them separately:

**API Server Only:**
```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

**Frontend Only:**
```bash
PYTHONPATH=$(pwd):$PYTHONPATH uv run streamlit run frontend/app.py
```

## Troubleshooting

### "Address already in use"
Port 8000 or 8502 is occupied by another process.

**Solution:**
```bash
# Kill the process using port 8000
lsof -ti :8000 | xargs kill -9

# Kill the process using port 8502
lsof -ti :8502 | xargs kill -9

# Then run the script again
./run-frontend.sh
```

### "ModuleNotFoundError: No module named 'config'"
The PYTHONPATH is not set correctly.

**Solution:**
The script handles this automatically, but if you run Streamlit manually:
```bash
PYTHONPATH=$(pwd):$PYTHONPATH uv run streamlit run frontend/app.py
```

### Frontend can't connect to API
Make sure both services are running by checking the logs:

```bash
# Check API health
curl http://localhost:8000/api/health

# Check frontend response
curl http://localhost:8502
```

If API is not running, the script will display an error and exit.

### API shows "uvicorn: command not found"
Make sure you're in the project directory and UV is installed:

```bash
cd /home/anirban/workspace/projects/rpa-complexity-agent
uv --version  # Should show version number
uv run python --version  # Should show Python 3.11
```

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   User's Browser                        │
│              http://localhost:8502                      │
└─────────────────────────────────────────────────────────┘
                          ↓
                    Streamlit Frontend
                    (3-page web app)
                          ↓
                  HTTP with CORS enabled
                          ↓
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend Server                     │
│              http://localhost:8000                      │
│                                                         │
│  Endpoints:                                             │
│  - POST   /api/assess                                   │
│  - GET    /api/status/{session_id}                      │
│  - GET    /api/download/{session_id}/{file_type}        │
│  - GET    /api/health                                   │
│  - GET    /api/version                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
                 LangGraph Agent Pipeline
                - Document Intelligence
                - Process Analysis
                - Complexity Assessment
                          ↓
                      Claude API
                  (Anthropic via httpx)
```

## Features Enabled by This Script

✅ **Automatic PYTHONPATH Setup** — No more "ModuleNotFoundError"
✅ **Parallel Startup** — Both services start sequentially
✅ **Health Checks** — Waits for services to be ready before proceeding
✅ **Colored Output** — Easy to read status messages
✅ **Graceful Shutdown** — Ctrl+C stops both services cleanly
✅ **Log Files** — Persistent logs in /tmp/
✅ **Error Handling** — Detects and reports startup failures

## Environment Variables

The script automatically handles these, but you can override:

```bash
# Change frontend port (default 8502)
# Not directly supported by script, would need modification

# Change API port (default 8000)
# Would need to modify script

# Change API host (default 127.0.0.1)
# Would need to modify script
```

To customize ports/hosts, edit `run-frontend.sh` and modify these lines:
- API: `--host 127.0.0.1 --port 8000`
- Frontend: Streamlit uses `~/.streamlit/config.toml` (port 8502)

## Next Steps

1. **Run the script:** `./run-frontend.sh`
2. **Open browser:** http://localhost:8502
3. **Upload a PDD:** Click "Upload PDD" and select a file
4. **Wait for assessment:** System processes for 2-5 minutes
5. **View results:** See complexity score and effort estimate
6. **Download reports:** Export Excel or PDF

---

**Last Updated:** 2026-03-17
**Project:** RPA Complexity Assessment Agent
**Phase:** Phase 8 — API & Frontend
