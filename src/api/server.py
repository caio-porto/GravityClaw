import os
import yaml
import asyncio
import logging
import time
import json
import glob
from collections import deque
from datetime import datetime, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv, set_key

from src.interface.telegram_bridge import run_bot_async
from src.agent.loop import AgentLoop

# ---------------------------------------------------------------------------
# Dynamic Host Link for .gemini config & trusted folders inside Docker
# ---------------------------------------------------------------------------
def _ensure_host_gemini_setup():
    """Dynamically links the host machine's .gemini configuration and marks the 
    container workspace as a trusted folder so MCP tools can run.
    """
    import shutil
    
    host_gemini = "/host_machine/mnt/host/c/Users/caiop/.gemini"
    container_gemini = "/root/.gemini"
    
    if os.path.exists(host_gemini):
        # 1. Symlink .gemini folder if not already linked
        if not os.path.islink(container_gemini):
            try:
                if os.path.exists(container_gemini):
                    if os.path.isdir(container_gemini):
                        shutil.rmtree(container_gemini)
                    else:
                        os.remove(container_gemini)
                os.symlink(host_gemini, container_gemini)
                print(f"Dynamically symlinked {container_gemini} to host {host_gemini}")
            except Exception as e:
                print(f"Failed to symlink .gemini: {e}")
        
        # 2. Add /app workspace and host workspace to trustedFolders.json
        trusted_json_path = os.path.join(container_gemini, "trustedFolders.json")
        try:
            d = {}
            if os.path.exists(trusted_json_path):
                with open(trusted_json_path, "r", encoding="utf-8") as f:
                    d = json.load(f) or {}
            
            updated = False
            for p in ["/app", "/host_machine/mnt/host/c/Users/caiop/Repositories/GravityClaw"]:
                if p not in d:
                    d[p] = "TRUST_FOLDER"
                    updated = True
                    
            if updated:
                with open(trusted_json_path, "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=2)
                print(f"Automatically added container directories to trusted folders: {trusted_json_path}")
        except Exception as e:
            print(f"Failed to update trustedFolders.json: {e}")

        # 3. Symlink workspace/project-level .gemini directory if not already linked
        host_project_gemini = "/host_machine/mnt/host/c/Users/caiop/Repositories/GravityClaw/.gemini"
        container_project_gemini = "/app/.gemini"
        
        if not os.path.islink(container_project_gemini):
            try:
                os.makedirs(host_project_gemini, exist_ok=True)
                
                # Prevent data loss: copy any existing container settings to host first
                if os.path.exists(container_project_gemini) and not os.path.islink(container_project_gemini):
                    for item in os.listdir(container_project_gemini):
                        src_item = os.path.join(container_project_gemini, item)
                        dst_item = os.path.join(host_project_gemini, item)
                        if os.path.isfile(src_item):
                            shutil.copy2(src_item, dst_item)
                            
                    if os.path.isdir(container_project_gemini):
                        shutil.rmtree(container_project_gemini)
                    else:
                        os.remove(container_project_gemini)
                        
                os.symlink(host_project_gemini, container_project_gemini)
                print(f"Dynamically symlinked project {container_project_gemini} to host {host_project_gemini}")
            except Exception as e:
                print(f"Failed to symlink project .gemini: {e}")

_ensure_host_gemini_setup()

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------

load_dotenv()

bot_task = None
stop_event = asyncio.Event()
START_TIME = time.time()

# Single shared AgentLoop instance for web chat
agent = AgentLoop()

# In-memory web chat history (newest at the end)
chat_history: deque = deque(maxlen=200)

# Ring buffer for captured log records
log_buffer: deque = deque(maxlen=500)

logger = logging.getLogger(__name__)

CONFIG_PATH = "config.yaml"
MEMORY_DIR = "memory"
CORE_MEMORY_PATH = "MEMORY.md"

# Use host machine's mount path for .env file if available, to bypass Docker single-file mount sync limits
HOST_PROJECT_PATH = "/host_machine/mnt/host/c/Users/caiop/Repositories/GravityClaw"
ENV_PATH = os.path.join(HOST_PROJECT_PATH, ".env") if os.path.exists(HOST_PROJECT_PATH) else ".env"

# ---------------------------------------------------------------------------
# Custom Log Handler — captures logs into the ring buffer
# ---------------------------------------------------------------------------

class BufferLogHandler(logging.Handler):
    """Appends every log record to the global ``log_buffer`` deque."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_buffer.append({
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            })
        except Exception:
            self.handleError(record)


def setup_log_capture() -> None:
    """Attach ``BufferLogHandler`` to the root logger so every log is captured."""
    handler = BufferLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(levelname)s - %(name)s - %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Telegram Bot Runner (existing logic preserved)
# ---------------------------------------------------------------------------

async def telegram_bot_runner() -> None:
    """Run the Telegram bot asynchronously in the main loop with automatic retry."""
    while not stop_event.is_set():
        try:
            await run_bot_async(stop_event)
        except Exception as e:
            logger.error(f"Telegram Bot error: {e}")
            if not stop_event.is_set():
                await asyncio.sleep(5)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_task
    setup_log_capture()
    logger.info("GravityClaw API server starting up")

    # Start the Telegram bot on startup
    stop_event.clear()
    bot_task = asyncio.create_task(telegram_bot_runner())
    yield

    # Clean up on shutdown
    logger.info("GravityClaw API server shutting down")
    stop_event.set()
    if bot_task:
        bot_task.cancel()


app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load and return config.yaml as a dict, or an empty dict on failure."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return {}


def _save_config(data: dict) -> None:
    """Write *data* to config.yaml."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _count_messages_today() -> int:
    """Count '### [' interaction headers in today's daily buffer file."""
    today_file = os.path.join(MEMORY_DIR, f"{date.today().isoformat()}.md")
    if not os.path.exists(today_file):
        return 0
    try:
        with open(today_file, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip().startswith("### ["))
    except Exception:
        return 0


def _count_memory_entries() -> int:
    """Count .md files in the memory/ directory."""
    try:
        return len(glob.glob(os.path.join(MEMORY_DIR, "*.md")))
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# 1. GET / — Serve the UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    try:
        with open("src/api/static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>UI not found</h1><p>Place index.html in src/api/static/</p>", status_code=404)

# ---------------------------------------------------------------------------
# 2. GET /api/status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    config = _load_config()
    primary = config.get("models", {}).get("primary", {})

    return {
        "status": "running",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "bot_running": bot_task is not None and not bot_task.done(),
        "current_model": {
            "provider": primary.get("provider", "unknown"),
            "model_name": primary.get("model_name", "unknown"),
        },
        "model_provider": primary.get("provider", "unknown"),
        "model_name": primary.get("model_name", "unknown"),
        "messages_today": _count_messages_today(),
        "memory_entries": _count_memory_entries(),
    }

# ---------------------------------------------------------------------------
# 3. POST /api/chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def post_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"error": "Message cannot be empty"}, status_code=400)

    now = datetime.now().isoformat()

    # Record user message
    chat_history.append({"role": "user", "content": message, "timestamp": now})

    try:
        response_text = await asyncio.to_thread(agent.process_input, message, "web-ui")
    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        error_msg = f"Error processing message: {e}"
        chat_history.append({"role": "assistant", "content": error_msg, "timestamp": datetime.now().isoformat()})
        return JSONResponse({"error": error_msg}, status_code=500)

    # Record assistant response
    chat_history.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})

    return {"response": response_text}

# ---------------------------------------------------------------------------
# 4. GET /api/chat/history
# ---------------------------------------------------------------------------

@app.get("/api/chat/history")
async def get_chat_history():
    return {"messages": list(chat_history)}

# ---------------------------------------------------------------------------
# 5. GET /api/logs
# ---------------------------------------------------------------------------

@app.get("/api/logs")
async def get_logs(level: str | None = None, limit: int = 100):
    logs = list(log_buffer)

    if level:
        level_upper = level.upper()
        logs = [entry for entry in logs if entry["level"] == level_upper]

    # Return the most recent entries, capped at limit
    return {"logs": logs[-limit:]}

# ---------------------------------------------------------------------------
# 6. GET /api/memory/core
# ---------------------------------------------------------------------------

@app.get("/api/memory/core")
async def get_core_memory():
    try:
        if not os.path.exists(CORE_MEMORY_PATH):
            return {"content": ""}
        with open(CORE_MEMORY_PATH, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        logger.error(f"Failed to read core memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 7. PUT /api/memory/core
# ---------------------------------------------------------------------------

@app.put("/api/memory/core")
async def update_core_memory(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    content = body.get("content")
    if content is None:
        return JSONResponse({"error": "Missing 'content' field"}, status_code=400)

    try:
        with open(CORE_MEMORY_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to write core memory: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 8. GET /api/memory/daily/dates
# ---------------------------------------------------------------------------

@app.get("/api/memory/daily/dates")
async def get_daily_dates():
    try:
        files = glob.glob(os.path.join(MEMORY_DIR, "*.md"))
        dates = sorted(
            [os.path.splitext(os.path.basename(f))[0] for f in files],
            reverse=True,
        )
        return {"dates": dates}
    except Exception as e:
        logger.error(f"Failed to list daily dates: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 9. GET /api/memory/daily
# ---------------------------------------------------------------------------

@app.get("/api/memory/daily")
async def get_daily_memory(date: str | None = None):
    if not date:
        return JSONResponse({"error": "Query parameter 'date' is required (YYYY-MM-DD)"}, status_code=400)

    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return JSONResponse({"error": "Invalid date format. Expected YYYY-MM-DD."}, status_code=400)

    filepath = os.path.join(MEMORY_DIR, f"{date}.md")
    if not os.path.exists(filepath):
        return JSONResponse({"error": f"No daily log found for {date}"}, status_code=404)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return {"date": date, "content": f.read()}
    except Exception as e:
        logger.error(f"Failed to read daily memory for {date}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 10. GET /api/integrations
# ---------------------------------------------------------------------------

STANDARD_ENV_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GITHUB_TOKEN",
    "GEMINI_API_KEY",
    "ACTIVEPIECES_API_KEY",
    "NOTION_API_KEY",
}


def _load_env_keys() -> list:
    """Dynamically parses the `.env` file to extract all keys, merges them with standard keys, 
    and checks if they are set (non-empty).
    """
    keys_in_env = {}
    
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        parts = line.split("=", 1)
                        k = parts[0].strip()
                        v = parts[1].strip()
                        if k:
                            keys_in_env[k] = bool(v)
        except Exception as e:
            logger.error(f"Failed to read .env file for keys: {e}")
            
    all_keys = set(STANDARD_ENV_KEYS).union(keys_in_env.keys())
    
    env_keys_list = []
    for k in sorted(all_keys):
        is_set = keys_in_env.get(k, False) or bool(os.environ.get(k, "").strip())
        env_keys_list.append({
            "name": k,
            "is_set": is_set,
            "is_custom": k not in STANDARD_ENV_KEYS
        })
    return env_keys_list


def _unset_env_key(key: str):
    """Robustly unsets an environment variable key from the `.env` file and pops it from os.environ."""
    if not os.path.exists(ENV_PATH):
        return
    
    try:
        lines = []
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                parts = stripped.split("=", 1)
                if parts[0].strip() == key:
                    continue
            new_lines.append(line)
        
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        logger.error(f"Failed to unset env key {key} in .env file: {e}")
        
    os.environ.pop(key, None)


def _set_env_key(key: str, value: str):
    """Sets/updates an environment variable key in both `.env` file and os.environ."""
    try:
        set_key(ENV_PATH, key, value)
    except Exception as e:
        logger.error(f"Failed to write set_key in .env: {e}")
        
    os.environ[key] = value


@app.get("/api/integrations")
async def get_integrations():
    bot_running = bot_task is not None and not bot_task.done()

    # Load MCP configurations directly from /app/.gemini/settings.json
    settings_path = "/app/.gemini/settings.json"
    mcp_servers = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings_data = json.load(f) or {}
                mcp_servers = settings_data.get("mcpServers", {})
        except Exception as e:
            logger.error(f"Failed to load project settings.json: {e}")

    mcp_tools = []
    for name, config in mcp_servers.items():
        mcp_tools.append({
            "name": name,
            "enabled": True,
            "command": config.get("command", ""),
            "args": config.get("args", []),
            "env": config.get("env", {})
        })

    # Environment keys are dynamically loaded from .env and standard keys
    env_keys_list = _load_env_keys()

    return {
        "telegram": {
            "status": "running" if bot_running else "stopped",
            "bot_running": bot_running,
            "bot_name": os.environ.get("TELEGRAM_BOT_USERNAME", "GravityClawBot"),
            "token_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        },
        "mcp_tools": mcp_tools,
        "tools": mcp_tools,
        "env_keys": env_keys_list,
        "environment": env_keys_list,
    }


# ---------------------------------------------------------------------------
# 10b. POST /api/integrations/telegram/toggle
# ---------------------------------------------------------------------------

@app.post("/api/integrations/telegram/toggle")
async def toggle_telegram_bot(request: Request):
    global bot_task
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    enabled = body.get("enabled", False)
    
    if enabled:
        if not os.environ.get("TELEGRAM_BOT_TOKEN", "").strip():
            return JSONResponse({"error": "Cannot start bot: TELEGRAM_BOT_TOKEN is missing"}, status_code=400)
        
        if bot_task is None or bot_task.done():
            stop_event.clear()
            bot_task = asyncio.create_task(telegram_bot_runner())
            logger.info("Telegram Bot started manually")
            return {"status": "success", "message": "Telegram Bot started"}
        else:
            return {"status": "success", "message": "Telegram Bot is already running"}
    else:
        if bot_task and not bot_task.done():
            stop_event.set()
            try:
                await asyncio.wait_for(bot_task, timeout=2.0)
            except asyncio.TimeoutError:
                bot_task.cancel()
            bot_task = None
            logger.info("Telegram Bot stopped manually")
            return {"status": "success", "message": "Telegram Bot stopped"}
        else:
            return {"status": "success", "message": "Telegram Bot is already stopped"}


# ---------------------------------------------------------------------------
# 10c. POST /api/integrations/telegram/configure
# ---------------------------------------------------------------------------

@app.post("/api/integrations/telegram/configure")
async def configure_telegram_bot(request: Request):
    global bot_task
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    token = body.get("token", "").strip()
    if not token:
        return JSONResponse({"error": "Token cannot be empty"}, status_code=400)
    
    try:
        _set_env_key("TELEGRAM_BOT_TOKEN", token)
        
        was_running = bot_task is not None and not bot_task.done()
        if was_running:
            stop_event.set()
            try:
                await asyncio.wait_for(bot_task, timeout=2.0)
            except asyncio.TimeoutError:
                bot_task.cancel()
            
            stop_event.clear()
            bot_task = asyncio.create_task(telegram_bot_runner())
            logger.info("Telegram Bot hot-restarted after token update")
            
        return {
            "status": "success",
            "message": "Telegram Bot Token updated successfully" + (" and bot restarted" if was_running else "")
        }
    except Exception as e:
        logger.error(f"Failed to configure Telegram Bot: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# 10d. POST /api/integrations/env/save
# ---------------------------------------------------------------------------

@app.post("/api/integrations/env/save")
async def save_env_key(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    name = body.get("name", "").strip().upper()
    value = body.get("value", "").strip()
    
    if not name:
        return JSONResponse({"error": "Key name is required"}, status_code=400)
    
    # Simple validation: keys must contain only alphanumeric characters and underscores
    import re
    if not re.match(r"^[A-Z0-9_]+$", name):
        return JSONResponse({"error": "Key name must only contain alphanumeric characters and underscores"}, status_code=400)
    
    try:
        _set_env_key(name, value)
        return {"status": "success", "message": f"Environment key '{name}' updated successfully"}
    except Exception as e:
        logger.error(f"Failed to save env key '{name}': {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# 10e. DELETE /api/integrations/env/{name}
# ---------------------------------------------------------------------------

@app.delete("/api/integrations/env/{name}")
async def delete_env_key(name: str):
    name = name.strip().upper()
    if not name:
        return JSONResponse({"error": "Key name is required"}, status_code=400)
    
    try:
        _unset_env_key(name)
        return {"status": "success", "message": f"Environment key '{name}' removed successfully"}
    except Exception as e:
        logger.error(f"Failed to delete env key '{name}': {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# 11. POST /api/integrations/mcp/save
# ---------------------------------------------------------------------------

@app.post("/api/integrations/mcp/save")
async def save_mcp_server(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    name = body.get("name")
    command = body.get("command")
    args = body.get("args", [])
    env = body.get("env", {})

    if not name or not command:
        return JSONResponse({"error": "Fields 'name' and 'command' are required"}, status_code=400)

    path = "/app/.gemini/settings.json"
    try:
        data = {"mcpServers": {}}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f) or {}
                except Exception:
                    pass

        mcp = data.setdefault("mcpServers", {})
        mcp[name] = {
            "command": command,
            "args": args
        }
        if env:
            mcp[name]["env"] = env

        # Ensure parent folder exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "message": f"MCP server '{name}' successfully saved"}
    except Exception as e:
        logger.error(f"Failed to save MCP server: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# 11b. DELETE /api/integrations/mcp/{name}
# ---------------------------------------------------------------------------

@app.delete("/api/integrations/mcp/{name}")
async def delete_mcp_server(name: str):
    path = "/app/.gemini/settings.json"
    if not os.path.exists(path):
        return JSONResponse({"error": "No project settings.json found"}, status_code=404)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}

        mcp = data.get("mcpServers", {})
        if name in mcp:
            del mcp[name]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return {"status": "success", "message": f"MCP server '{name}' successfully deleted"}
        else:
            return JSONResponse({"error": f"MCP server '{name}' not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Failed to delete MCP server: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 12. GET /api/config
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def get_config():
    try:
        return _load_config()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------------------------------------------------------
# 13. POST /api/config
# ---------------------------------------------------------------------------

@app.post("/api/config")
async def update_config(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    try:
        config = _load_config()

        # Update models section
        models = config.setdefault("models", {})
        primary = models.setdefault("primary", {})

        if "primary_provider" in data:
            primary["provider"] = data["primary_provider"]
        if "primary_model" in data:
            primary["model_name"] = data["primary_model"]

        if "fallback_models" in data:
            new_fallback = []
            for item in data["fallback_models"]:
                if not item:
                    continue
                parts = item.split("/", 2)
                fb_entry = {}
                if len(parts) >= 1:
                    fb_entry["provider"] = parts[0]
                if len(parts) >= 2:
                    fb_entry["model_name"] = parts[1]
                if len(parts) >= 3:
                    fb_entry["url"] = parts[2]
                new_fallback.append(fb_entry)
            models["fallback"] = new_fallback

        # Update memory section
        memory = config.setdefault("memory", {})
        if "chroma_db_dir" in data:
            memory["chroma_db_dir"] = data["chroma_db_dir"]
        if "collection_name" in data:
            memory["collection_name"] = data["collection_name"]

        # Update voice section
        if "voice_speed" in data or "voice_mode" in data:
            voice = config.setdefault("voice", {})
            if "voice_speed" in data:
                try:
                    voice["speed"] = float(data["voice_speed"])
                except ValueError:
                    voice["speed"] = 1.0
            if "voice_mode" in data:
                voice["mode"] = data["voice_mode"]

        _save_config(config)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 14. GET /api/config/raw
# ---------------------------------------------------------------------------

@app.get("/api/config/raw")
async def get_config_raw():
    try:
        if not os.path.exists(CONFIG_PATH):
            return {"yaml": ""}
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return {"yaml": f.read()}
    except Exception as e:
        logger.error(f"Failed to read raw config: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# 15. POST /api/config/raw
# ---------------------------------------------------------------------------

@app.post("/api/config/raw")
async def update_config_raw(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    raw_yaml = body.get("yaml")
    if raw_yaml is None:
        return JSONResponse({"error": "Missing 'yaml' field"}, status_code=400)

    # Validate that the string is parseable YAML before writing
    try:
        yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return JSONResponse({"error": f"Invalid YAML: {e}"}, status_code=400)

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(raw_yaml)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to write raw config: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ---------------------------------------------------------------------------
# Skills Management & Installation Panel (Phase 7)
# ---------------------------------------------------------------------------

HOST_SKILLS_PATH = "/host_machine/mnt/host/c/Users/caiop/.gemini/config/skills"
SKILLS_DIR = HOST_SKILLS_PATH if os.path.exists(HOST_SKILLS_PATH) else os.path.expanduser("~/.gemini/config/skills")

# Global state for background installation
installer_process = None
installer_logs = ""
installer_running = False

@app.get("/api/skills")
async def list_skills():
    """Lists all installed skills by reading C:\\Users\\caiop\\.gemini\\config\\skills directory."""
    import re
    if not os.path.exists(SKILLS_DIR):
        return {"skills": []}
    
    skills = []
    try:
        for entry in os.scandir(SKILLS_DIR):
            if entry.is_dir() and not entry.name.startswith("."):
                skill_id = entry.name
                skill_md_path = os.path.join(entry.path, "SKILL.md")
                
                name = skill_id
                description = ""
                
                if os.path.exists(skill_md_path):
                    try:
                        with open(skill_md_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            # Parse YAML frontmatter
                            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
                            if match:
                                fm_text = match.group(1)
                                fm = yaml.safe_load(fm_text) or {}
                                name = fm.get("name", name)
                                description = fm.get("description", "")
                    except Exception as e:
                        logger.error(f"Error parsing SKILL.md for {skill_id}: {e}")
                
                skills.append({
                    "id": skill_id,
                    "name": name,
                    "description": description,
                    "path": entry.path
                })
        return {"skills": skills}
    except Exception as e:
        logger.error(f"Failed to list skills: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

_catalog_cache = None

@app.get("/api/skills/catalog")
async def get_skills_catalog():
    """Fetches and returns the available skills catalog from the remote repository."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache
    
    import requests
    url = "https://raw.githubusercontent.com/sickn33/antigravity-awesome-skills/main/skills_index.json"
    try:
        res = await asyncio.to_thread(requests.get, url, timeout=10)
        if res.status_code == 200:
            _catalog_cache = res.json()
            return _catalog_cache
        else:
            return JSONResponse({"error": f"Failed to fetch catalog: HTTP {res.status_code}"}, status_code=500)
    except Exception as e:
        logger.error(f"Error fetching catalog: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/skills/catalog/install")
async def install_catalog_skill(request: Request):
    """Downloads and installs a specific skill from the remote catalog."""
    import requests
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    skill_id = body.get("skill_id")
    if not skill_id:
        return JSONResponse({"error": "Missing 'skill_id' field"}, status_code=400)
    
    url = f"https://raw.githubusercontent.com/sickn33/antigravity-awesome-skills/main/skills/{skill_id}/SKILL.md"
    try:
        res = await asyncio.to_thread(requests.get, url, timeout=10)
        if res.status_code != 200:
            return JSONResponse({"error": f"Failed to fetch SKILL.md for {skill_id}: HTTP {res.status_code}"}, status_code=500)
        
        content = res.text
        
        skill_dir = os.path.join(SKILLS_DIR, skill_id)
        os.makedirs(skill_dir, exist_ok=True)
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return {"status": "success", "message": f"Skill {skill_id} successfully installed"}
    except Exception as e:
        logger.error(f"Error installing skill {skill_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Retrieves the raw SKILL.md content for a given skill."""
    skill_md_path = os.path.join(SKILLS_DIR, skill_id, "SKILL.md")
    if not os.path.exists(skill_md_path):
        return JSONResponse({"error": f"Skill {skill_id} not found"}, status_code=404)
    
    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            return {
                "id": skill_id,
                "content": f.read()
            }
    except Exception as e:
        logger.error(f"Failed to read skill {skill_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.put("/api/skills/{skill_id}")
async def save_skill(skill_id: str, request: Request):
    """Creates or updates a skill's SKILL.md content."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    
    content = body.get("content")
    if content is None:
        return JSONResponse({"error": "Missing 'content' field"}, status_code=400)
    
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    os.makedirs(skill_dir, exist_ok=True)
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    
    try:
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "id": skill_id}
    except Exception as e:
        logger.error(f"Failed to save skill {skill_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """Uninstalls/deletes a skill directory."""
    import shutil
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    if not os.path.exists(skill_dir):
        return JSONResponse({"error": f"Skill {skill_id} not found"}, status_code=404)
    
    try:
        shutil.rmtree(skill_dir)
        return {"status": "success", "message": f"Skill {skill_id} uninstalled"}
    except Exception as e:
        logger.error(f"Failed to delete skill {skill_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)



async def run_installer_async(cmd: list):
    global installer_process, installer_logs, installer_running
    installer_running = True
    installer_logs = f"Running: {' '.join(cmd)}\n\n"
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        installer_process = process
        
        async def read_stream(stream, prefix=""):
            global installer_logs
            while True:
                line = await stream.readline()
                if not line:
                    break
                installer_logs += prefix + line.decode("utf-8", errors="replace")

        await asyncio.gather(
            read_stream(process.stdout),
            read_stream(process.stderr)
        )
        
        rc = await process.wait()
        installer_logs += f"\nProcess finished with exit code {rc}\n"
    except Exception as e:
        installer_logs += f"\nExecution failed: {e}\n"
    finally:
        installer_running = False

@app.post("/api/skills/install")
async def install_skills(request: Request):
    """Triggers npx antigravity-awesome-skills asynchronously."""
    global installer_running
    if installer_running:
        return JSONResponse({"error": "An installation is already in progress"}, status_code=400)
    
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    categories = body.get("categories", [])
    risks = body.get("risks", [])
    
    cmd = ["npx", "antigravity-awesome-skills", "--path", SKILLS_DIR]
    
    if categories:
        cmd.extend(["--category", ",".join(categories)])
    if risks:
        cmd.extend(["--risk", ",".join(risks)])
        
    asyncio.create_task(run_installer_async(cmd))
    return {"status": "started", "message": "Installation started"}

@app.get("/api/skills/install/status")
async def install_status():
    """Returns the current installation status and logs."""
    global installer_running, installer_logs
    return {
        "running": installer_running,
        "logs": installer_logs
    }

# ---------------------------------------------------------------------------
# 16. POST /api/shutdown
# ---------------------------------------------------------------------------

@app.post("/api/shutdown")
async def shutdown_agent():
    """Shuts down the unified server (Docker container will exit)."""
    import threading

    def killer():
        os._exit(0)

    # Give the server a second to return the 200 OK response to the UI
    threading.Timer(1.0, killer).start()

    return {"status": "success", "message": "Agent is shutting down. Check Docker logs."}

# ---------------------------------------------------------------------------
# Static Files Mount
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="src/api/static"), name="static")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
