from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import PlainTextResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
from typing import Dict, List
from runtime.dating import AIVoiceAssistant, handle_multi_tool_query

# --- Redis config for production ---
# Set REDIS_URL in your environment to enable Redis chat history.
# Example: rediss://:password@host:port/0
REDIS_URL = os.environ.get("REDIS_URL")
USE_REDIS = bool(REDIS_URL) and os.environ.get("USE_REDIS", "1") == "1"

try:
    import aioredis
    redis_available = True
except ImportError:
    redis_available = False

app = FastAPI()

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_FILE = os.environ.get("AGENT_LOG_FILE", "/tmp/agent.log")

# In-memory chat history fallback
user_histories: Dict[str, List[Dict]] = {}

REDIS_HISTORY_EXPIRE_SECONDS = int(os.environ.get("REDIS_HISTORY_EXPIRE_SECONDS", 60*60*24))  # default: 24h

async def get_redis():
    if not redis_available or not REDIS_URL:
        return None
    return await aioredis.from_url(REDIS_URL, decode_responses=True, ssl=True)

async def get_history(user_id: str) -> List[Dict]:
    if USE_REDIS and redis_available:
        try:
            redis = await get_redis()
            data = await redis.get(f"history:{user_id}")
            if data:
                import json
                return json.loads(data)
            return []
        except Exception:
            pass
    return user_histories.setdefault(user_id, [])

async def set_history(user_id: str, history: List[Dict]):
    if USE_REDIS and redis_available:
        try:
            redis = await get_redis()
            import json
            await redis.set(f"history:{user_id}", json.dumps(history), ex=REDIS_HISTORY_EXPIRE_SECONDS)
            return
        except Exception:
            pass
    user_histories[user_id] = history

def get_user_id(request: Request) -> str:
    # Use session/cookie/auth header for real apps
    return request.headers.get("X-User-ID", "demo_user")

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Dating Agent ASGI is running."}

@app.get("/log")
async def get_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            content = f.read()
        return PlainTextResponse(content)
    return PlainTextResponse("Log file not found.", status_code=404)

@app.get("/log/download")
async def download_log():
    if os.path.exists(LOG_FILE):
        return FileResponse(LOG_FILE, filename=os.path.basename(LOG_FILE), media_type="text/plain")
    return PlainTextResponse("Log file not found.", status_code=404)

@app.websocket("/ws")
async def websocket_log_stream(websocket: WebSocket):
    await websocket.accept()
    last_size = 0
    try:
        while True:
            if not os.path.exists(LOG_FILE):
                await websocket.send_text("Waiting for log file...")
                await asyncio.sleep(1)
                continue
            with open(LOG_FILE, "r") as f:
                f.seek(last_size)
                new = f.read()
                if new:
                    f.seek(0, 2)
                    last_size = f.tell()
                    await websocket.send_text(new)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass

# --- Real Agent Chat Logic ---

@app.post("/chat")
async def chat_endpoint(request: Request):
    """
    POST /chat
    Body: {"message": "..."}
    Returns: {"reply": "...", "history": [...]}
    """
    data = await request.json()
    user_message = data.get("message", "")
    user_id = get_user_id(request)
    history = await get_history(user_id)
    history.append({"role": "user", "content": user_message})

    # Create agent/session (stateless for now)
    assistant = AIVoiceAssistant()
    agent = assistant.create_agent()
    session = assistant.setup_session(vad=None)  # Pass VAD if needed

    # Call agent logic and capture reply
    session.last_reply = None
    async def capture_reply(results):
        if isinstance(results, list):
            session.last_reply = "\n\n".join(str(r) for r in results if r)
        else:
            session.last_reply = str(results)
    import types
    from runtime import dating
    session.handle_tool_results = types.MethodType(lambda self, results: capture_reply(results), session)
    await handle_multi_tool_query(session, user_message)
    agent_reply = session.last_reply or "(No reply)"
    history.append({"role": "assistant", "content": agent_reply})
    await set_history(user_id, history)
    return JSONResponse({"reply": agent_reply, "history": history})

@app.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    """
    WebSocket /chat/ws
    Send: {"message": "..."}
    Receive: {"reply": "...", "history": [...]}
    """
    await websocket.accept()
    user_id = "demo_user_ws"
    history = await get_history(user_id)
    assistant = AIVoiceAssistant()
    agent = assistant.create_agent()
    session = assistant.setup_session(vad=None)
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            history.append({"role": "user", "content": user_message})
            session.last_reply = None
            async def capture_reply(results):
                if isinstance(results, list):
                    session.last_reply = "\n\n".join(str(r) for r in results if r)
                else:
                    session.last_reply = str(results)
            import types
            from runtime import dating
            session.handle_tool_results = types.MethodType(lambda self, results: capture_reply(results), session)
            await handle_multi_tool_query(session, user_message)
            agent_reply = session.last_reply or "(No reply)"
            history.append({"role": "assistant", "content": agent_reply})
            await set_history(user_id, history)
            await websocket.send_json({"reply": agent_reply, "history": history})
    except WebSocketDisconnect:
        pass

# For local dev: run with
# uvicorn runtime.dating_asgi:app --host 0.0.0.0 --port 8000 --reload 