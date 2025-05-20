# Dating Agent Voice Assistant

This project is a voice-enabled AI assistant for matchmaking, classifieds, and general information, with robust Locanto browser integration and support for web search, Wikipedia, news, weather, math, and more.

## Features
- Voice-driven conversational agent
- Locanto browser and matchmaking tools
- Web search, Wikipedia, news, weather, math, fun content
- Azure/OpenAI LLM and TTS integration
- **LLM-based parallel tool orchestration**: The agent uses an LLM to select and run multiple tools in parallel for any query
- Chunked, spoken results for long outputs
- Frontend (Next.js) with voice and chat UI
- Flask log viewer with live terminal log, search, filtering, download, and tailing
- Log rotation (keeps last 3 logs)
- **ASGI/FastAPI backend** with:
  - `/chat` POST endpoint: chat with agent, context/history per user
  - `/chat/ws` WebSocket endpoint: real-time chat with agent, streaming support
  - `/log` and `/log/download` endpoints for logs

## LLM-Based Tool Orchestration
The agent now uses an LLM (OpenAI GPT-4o or Azure OpenAI) to analyze each user query and select the most relevant tools to run, based on their descriptions. All selected tools are executed in parallel for maximum efficiency. Results are combined and spoken to the user.

### How it works
- The agent describes all available tools and their docstrings to the LLM, asking for a JSON list of tool names to invoke for the query.
- The LLM returns the list; all tools are run in parallel using `asyncio.gather`.
- If the LLM is unavailable, the agent falls back to keyword-based selection.

### Adding new tools
To add a new tool to the orchestration:
1. Implement the tool as a function with a clear, action-oriented docstring.
2. Add the tool to the `available_tools` mapping in `dating.py`'s `handle_multi_tool_query`.
3. The LLM will automatically consider it for relevant queries.

## Quickstart

### 1. Install Python dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the agent (with log rotation)
```bash
python runtime/dating.py
```

### 3. Run the Flask log viewer
```bash
python flask_agent_log_server.py
```
- Open http://localhost:8080 to view logs
- Features: live log, search, filter by level, download, tailing (pause/resume)
- Set `AGENT_LOG_FILE` env var to change log file (default: agent.log)

### 4. Run the frontend
```bash
cd frontend
pnpm dev
```

### 5. (Optional) Run the agent with Uvicorn (ASGI/FastAPI)
If you have an ASGI entrypoint (e.g., `runtime/dating_asgi.py`):
```bash
uvicorn runtime.dating_asgi:app --host 0.0.0.0 --port 8000 --reload
```

## Directory Structure
- `dating.py` — Main entrypoint and agent logic
- `agent_utils.py` — Utilities for chunking, speaking, Locanto query construction
- `locanto_constants.py` — Valid slugs and IDs for Locanto
- `locanto_browser_scraper.py` — Playwright-powered Locanto browser scraper
- `requirements.txt` — Python dependencies
- `http/`, `llm/`, `locations/`, `proxy/`, `stat/`, `tags/`, `locanto/` — Supporting data and modules

## Notes
- Playwright requires a Chromium browser install (`playwright install`).
- For Locanto scraping, ensure your IP is not blocked or use a proxy if needed.
- All code is Python 3.8+ compatible.

## License
See LICENSE for details.

## Log and Healthcheck
- Logs are written to `/tmp/agent.log` by default (set `AGENT_LOG_FILE` to override; must be writable).
- No log rotation is performed; only the current log is kept.
- If file logging is not possible, logs go to the console.
- The backend exposes a healthcheck endpoint at `/` that returns a JSON message if the service is running.

## Deployment/Startup
To run the backend in production or on serverless platforms (Azure, Leapcell, etc.), use:

```
uvicorn runtime.dating_asgi:app --host 0.0.0.0 --port $PORT
```

- Always use the `$PORT` environment variable provided by the platform.
- The backend will listen on `/` for healthchecks and on `/chat`, `/chat/ws`, etc. for API calls.

## Environment Variables
- `AGENT_LOG_FILE`: Path to log file (default: agent.log)
- `REDIS_URL`: Redis connection string for chat history (default: production cloud endpoint)
- `USE_REDIS`: Set to `1` to use Redis for chat history (default: 1)
- `REDIS_HISTORY_EXPIRE_SECONDS`: Expiry (in seconds) for chat history in Redis (default: 86400 = 24h)
- See `.env` for other agent/LLM/LiveKit config

## Production Chat History (Redis)
- In production, chat history is stored in Redis (cloud endpoint, SSL, password protected).
- For local/dev or if Redis is unavailable, falls back to in-memory (not persistent).
- Dependency: `aioredis` (install with `pip install aioredis`)

## Packaging
- To package the agent, run:
```