import os
import json
import time
import logging
import asyncio
from typing import Any, Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings, BASE_DIR, APP_VERSION
from app.core.security import (
    verify_session_token,
    get_current_user,
    login_limiter,
    is_authenticated,
    get_client_ip,
)
from app.core.process_manager import process_manager
from app.core.downloader import downloader
from app.core.backup_manager import backup_manager
from app.core.task_scheduler import task_scheduler
from app.core.metrics_manager import metrics_manager
from app.core.player_manager import player_manager
from app.core.activity_manager import activity_manager

logger = logging.getLogger("dockraft.main")


# --- Security Headers Middleware ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security-related HTTP response headers to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # CSP: allow same-origin scripts/styles + Google Fonts + inline styles (needed for Jinja templates)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:;"
        )
        return response


# --- Lifespan (replaces deprecated @app.on_event) ---
_autostart_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    global _autostart_task
    task_scheduler.start_loop()
    metrics_manager.start()

    # Autostart server if enabled in configuration and server is installed
    if settings.runtime_config.get("autostart_server", False) and process_manager.is_installed():
        async def _autostart():
            await asyncio.sleep(2)
            if process_manager.get_status() == "OFFLINE":
                logger.info("[Dockraft] Inicio automático habilitado: arrancando servidor de Minecraft...")
                await process_manager.start_server()
        _autostart_task = asyncio.create_task(_autostart())

    yield
    if _autostart_task and not _autostart_task.done():
        _autostart_task.cancel()
    metrics_manager.stop()
    task_scheduler.stop_loop()
    # Flush debounced writers so no activity/player history is lost on shutdown.
    activity_manager.flush(force=True)
    player_manager.flush()


app = FastAPI(
    title="Dockraft",
    description="Ultra-lightweight Minecraft Server Panel",
    version=APP_VERSION,
    lifespan=lifespan,
)

# --- CORS Middleware ---
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins: List[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.add_middleware(SecurityHeadersMiddleware)


# --- Helper ---
def _is_server_installed() -> bool:
    """Returns True if any known server binary or configured server_file exists in data_dir."""
    return process_manager.is_installed()


# --- Modular Routers ---
from app.routers import (
    auth as auth_router,
    server as server_router,
    players as players_router,
    installer as installer_router,
    activity as activity_router,
    files as files_router,
    backups as backups_router,
    webhooks as webhooks_router,
    tasks as tasks_router,
    plugins as plugins_router,
)
from app.routers.installer import get_update_info, get_version_changelog_info
from app.routers.auth import clear_session_cookies as _clear_session_cookies

app.include_router(auth_router.router)
app.include_router(server_router.router)
app.include_router(players_router.router)
app.include_router(installer_router.router)
app.include_router(activity_router.router)
app.include_router(files_router.router)
app.include_router(backups_router.router)
app.include_router(webhooks_router.router)
app.include_router(tasks_router.router)
app.include_router(plugins_router.router)


# --- WebSocket Console & Stats Hub ---
@app.websocket("/ws/console")
async def websocket_console(websocket: WebSocket, token: Optional[str] = Query(None)):
    if settings.admin_password:
        cookie_token = (
            websocket.cookies.get("dockraft_token")
            or websocket.cookies.get("dockraft_session")
            or websocket.cookies.get("litemc_token")
        )
        effective_token = token or cookie_token
        if not effective_token or not verify_session_token(effective_token):
            await websocket.accept()
            await websocket.close(code=4001)
            return

    await websocket.accept()
    process_manager.connected_websockets.add(websocket)

    try:
        initial_stats = process_manager.get_stats()
        await websocket.send_json({
            "type": "init",
            "status": process_manager.get_status(),
            "history": list(process_manager.log_buffer),
        })
        await websocket.send_json({
            "type": "stats",
            "data": initial_stats,
        })

        async def stats_pusher():
            while True:
                await asyncio.sleep(2)
                try:
                    await websocket.send_json({
                        "type": "stats",
                        "data": process_manager.get_stats(),
                    })
                except Exception:
                    break

        stats_task = asyncio.create_task(stats_pusher())

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "command":
                if settings.admin_password and effective_token:
                    if not verify_session_token(effective_token):
                        await websocket.send_json({"type": "log", "data": "[Dockraft] Sesión caducada por seguridad o inactividad."})
                        await websocket.close(code=4001)
                        break
                cmd = data.get("command", "")
                await process_manager.send_command(cmd)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        process_manager.connected_websockets.discard(websocket)
        if "stats_task" in locals() and not stats_task.done():
            stats_task.cancel()


# --- Serve Static UI & Modular Jinja2 Templates ---
WEB_DIR = BASE_DIR / "web"
if (WEB_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

templates_dir = WEB_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))
START_TIME_TOKEN = str(int(time.time()))
templates.env.globals["asset_v"] = START_TIME_TOKEN
templates.env.globals["app_version"] = APP_VERSION


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Isolated secure login page rendered via Jinja2."""
    session_expired = request.query_params.get("expired") == "1"

    if not settings.admin_password or (is_authenticated(request) and not session_expired):
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    client_ip = get_client_ip(request)
    is_locked, remaining = login_limiter.is_locked(client_ip)

    resp = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "admin_user": getattr(settings, "admin_user", "admin"),
            "is_locked": is_locked,
            "cooldown_seconds": remaining,
            "max_attempts": getattr(settings, "login_max_attempts", 5),
            "app_name": "Dockraft",
            "app_version": APP_VERSION,
            "asset_v": START_TIME_TOKEN,
            "session_expired": session_expired,
        },
    )
    if session_expired:
        _clear_session_cookies(resp)
    return resp


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Main Dockraft Dashboard view."""
    if settings.admin_password and not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    stats = process_manager.get_stats()
    cfg = settings.runtime_config
    is_installed = bool(stats.get("is_installed", False))
    server_status = stats.get("status", "OFFLINE")

    def _safe_json_embed(data: Any) -> str:
        return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "admin_user": getattr(settings, "admin_user", "admin"),
            "app_name": "Dockraft",
            "app_version": APP_VERSION,
            "asset_v": START_TIME_TOKEN,
            "stats": stats,
            "cfg": cfg,
            "is_installed": is_installed,
            "server_status": server_status,
            "server_name": stats.get("server_name") or cfg.get("server_name", "Mi Servidor Dockraft"),
            "server_version": stats.get("server_version") or cfg.get("server_version", ""),
            "server_type": stats.get("server_type") or cfg.get("server_type", ""),
            "motd": stats.get("motd", ""),
            "stats_json": _safe_json_embed(stats),
            "cfg_json": _safe_json_embed(cfg),
        },
    )
