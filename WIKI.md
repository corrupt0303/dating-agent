# Dating Agent Project Wiki

Welcome to the Dating Agent Wiki! This document provides in-depth information about the architecture, modules, setup, and usage of the Dating Agent project.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Core Features](#core-features)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Running the Agent](#running-the-agent)
7. [Modules & Utilities](#modules--utilities)
8. [Testing](#testing)
9. [Security](#security)
10. [Troubleshooting](#troubleshooting)
11. [Contributing](#contributing)

---

## Project Overview
The Dating Agent is an advanced AI-powered assistant designed to search, crawl, and analyze dating and classified listings (e.g., Locanto), perform web searches, and interact with users using a suite of tools. It leverages Playwright for browser automation, integrates with LLMs (OpenAI, Azure, etc.), and supports modular tool registration.

## Directory Structure
```
/llm                  # LLM integration scripts (Azure, Ollama, etc.)
/runtime              # Core agent logic, tool definitions, and scrapers
/app                  # (Legacy) Utility scripts
/frontend             # UI components (if applicable)
/test                 # Test scripts and HTML test harnesses
/locanto, /proxy, ... # Specialized modules
requirements.txt      # Python dependencies
README.md             # Project summary and quickstart
WIKI.md               # This file (project documentation)
```

## Core Features
- **Web Scraping**: Playwright-based tools for Locanto and general web crawling
- **LLM Integration**: Azure, OpenAI, Ollama, Cerebras, etc.
- **Tool Registration**: Modular, extensible tool system
- **Secure Configuration**: Uses `.env` for API keys and secrets
- **Parallel/Async Execution**: Tools can run in parallel for fast results

## Installation & Setup
1. **Clone the repository:**
   ```sh
   git clone <repo-url>
   cd dating-agent
   ```
2. **Create a virtual environment:**
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
4. **Configure environment variables:**
   - Copy `.env.example` to `.env` and fill in required keys (see [Configuration](#configuration)).

## Configuration
The agent requires several environment variables. Example keys:
- `OPENWEATHER_API_KEY`
- `AZURE_OPENAI_API_KEY`
- `SERPAPI_API_KEY`
- `WHOOGLE_SERVER`
- ...and others as needed for your deployment

## Running the Agent
**Always run from the project root using module syntax:**
```sh
python -m runtime.dating dev
```
This ensures relative imports work correctly. Do **not** run `python dating.py dev` from inside `runtime/`.

## Modules & Utilities
- **runtime/dating.py**: Main agent logic and tool registration
- **runtime/agent_utils.py**: Shared utility functions
- **runtime/puppeteer_crawler.py**: Playwright-based web crawler
- **runtime/bing_playwright_scraper.py**: Bing search via Playwright
- **runtime/locanto_browser_scraper.py**: Locanto-specific scraper
- **llm/**: LLM integration scripts
- **test/**: Test cases and HTML harnesses

## Testing
- Place tests in the `test/` directory.
- Use standard Python test frameworks or run scripts directly.

## Security
- **Never commit secrets**: Use `.env` for all sensitive keys.
- **Review dependencies**: Keep `requirements.txt` up to date.

## Troubleshooting
- **Relative Import Errors**: Always run as a module from the root (`python -m runtime.dating ...`).
- **Missing Keys**: Double-check your `.env` file.
- **Playwright Issues**: Ensure all Playwright dependencies are installed.

## Contributing
- Fork the repo and submit pull requests.
- Follow the code style and document new tools/utilities in this wiki.

---
For further questions, see the code comments or open an issue.

## ASGI Agent Backend
- **Endpoints:**
  - `POST /chat`: Send a message, get agent reply and chat history (per user)
  - `WS /chat/ws`: Real-time chat with agent, streaming support, chat history
  - `/log`, `/log/download`: Access/download logs
- **Context/History:**
  - Each user gets a separate chat history
  - **Production:** Uses Redis (cloud, SSL, password) for persistent chat history
  - **Local/dev:** Falls back to in-memory if Redis is unavailable
- **Streaming:**
  - WebSocket endpoint streams agent replies as soon as available
- **How to Use:**
  - See README for curl and WebSocket examples
- **Troubleshooting:**
  - If agent doesn't reply, check logs and API keys
  - For multi-turn, ensure you use the same user/session
  - For production, use persistent storage for chat history
  - If Redis is unavailable, history is not persistent
- **Redis Config:**
  - `REDIS_URL`: Redis connection string (default: production cloud endpoint)
  - `USE_REDIS`: Set to `1` to use Redis (default: 1)
  - `REDIS_HISTORY_EXPIRE_SECONDS`: Expiry (in seconds) for chat history (default: 86400 = 24h)
  - Dependency: `aioredis` (install with `pip install aioredis`)

## Log Viewer (Flask)
- Run with `python flask_agent_log_server.py`
- Opens on http://localhost:8080
- Features: live log, search, filter, download, tailing

## Frontend
- Next.js app with voice/chat UI
- Build: `cd frontend && pnpm build`
- Start: `pnpm start`

## Backend Start/Build
- `uvicorn runtime.dating_asgi:app --host 0.0.0.0 --port 8000 --reload`

## Environment
- Set all required API keys for agent tools (Azure/OpenAI, etc.)
- `AGENT_LOG_FILE` for log location

## Example Usage
- See README for API and WebSocket usage

## Logging
- Logs are written to `/tmp/agent.log` by default (set `AGENT_LOG_FILE` to override; must be writable).
- No log rotation is performed; only the current log is kept.
- If file logging is not possible, logs go to the console.

## Healthcheck
- The backend exposes a healthcheck endpoint at `/` that returns a JSON message if the service is running.

## Deployment/Startup
- Always start the backend with:
  ```
  uvicorn runtime.dating_asgi:app --host 0.0.0.0 --port $PORT
  ```
- Use the `$PORT` environment variable provided by your platform.
