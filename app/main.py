import os
import sys
import re
import json
import time
import shutil
import zipfile
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Depends,
    HTTPException, UploadFile, File, Form, Query, Response, Request, status
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from app.config import settings, BASE_DIR
from app.core.security import (
    create_session_token, verify_admin_password, verify_admin_credentials,
    verify_session_token, get_current_user, login_limiter, is_authenticated,
    get_session_max_age
)
from app.core.process_manager import process_manager
from app.core.downloader import downloader
from app.core.file_manager import file_manager
from app.core.java_manager import JavaManager
from app.core.backup_manager import backup_manager
from app.core.task_scheduler import task_scheduler
from app.core.webhook_manager import webhook_manager
from app.core.metrics_manager import metrics_manager
from app.core.player_manager import player_manager
from app.core.fs_utils import atomic_write_text
from app.core.diagnostic_manager import diagnostic_manager
from app.core.activity_manager import activity_manager


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
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    task_scheduler.start_loop()
    metrics_manager.start()

    # Autostart server if enabled in configuration and server is installed
    if settings.runtime_config.get("autostart_server", False) and process_manager.is_installed():
        async def _autostart():
            await asyncio.sleep(2)
            if process_manager.get_status() == "OFFLINE":
                print("[Dockraft] Inicio automático habilitado: arrancando servidor de Minecraft...")
                await process_manager.start_server()
        asyncio.create_task(_autostart())

    yield
    metrics_manager.stop()
    task_scheduler.stop_loop()


app = FastAPI(
    title="Dockraft",
    description="Ultra-lightweight Minecraft Server Panel",
    version="1.0.0",
    lifespan=lifespan
)

# --- CORS Middleware ---
# IMPORTANT: allow_origins=["*"] combined with allow_credentials=True is invalid per the CORS spec.
# Restrict to specific origins via the ALLOWED_ORIGINS env var (comma-separated).
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
    # No explicit origins: allow all but WITHOUT credentials (safe default for local/LAN use)
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

# --- Pydantic Schemas ---
class LoginRequest(BaseModel):
    username: Optional[str] = "admin"
    password: str

class CommandRequest(BaseModel):
    command: str

class FileSaveRequest(BaseModel):
    path: str
    content: str

class FolderCreateRequest(BaseModel):
    path: str

class UnzipRequest(BaseModel):
    path: str
    target_dir: str = ""

class FileRenameRequest(BaseModel):
    path: str
    new_name: str

class FileDuplicateRequest(BaseModel):
    path: str

class FileCompressRequest(BaseModel):
    path: str

class FileCreateRequest(BaseModel):
    path: str

class InstallRequest(BaseModel):
    server_type: str # paper, purpur, vanilla, fabric, bedrock, forge
    version: str
    server_name: Optional[str] = "Mi Servidor Dockraft"
    java_path: Optional[str] = None
    min_ram: Optional[str] = "1G"
    max_ram: Optional[str] = "2G"
    aikar_flags: Optional[bool] = True
    cpu_cores: Optional[int] = 2
    disk_limit_gb: Optional[float] = 10.0
    force: Optional[bool] = False

class EulaRequest(BaseModel):
    accepted: bool

class UpdateRequest(BaseModel):
    version: str

class PlayerActionRequest(BaseModel):
    player: str
    reason: Optional[str] = ""

class KickAllRequest(BaseModel):
    reason: Optional[str] = "Mantenimiento del servidor"

class BackupCreateRequest(BaseModel):
    tag: Optional[str] = "manual"
    scope: Optional[str] = "full"
    targets: Optional[List[str]] = None
    compression: Optional[bool] = None
    stop_server: Optional[bool] = None
    pre_command: Optional[str] = None

class BackupRestoreRequest(BaseModel):
    filename: str

class BackupConfigRequest(BaseModel):
    auto_backup: Optional[bool] = None
    backup_interval_hours: Optional[int] = None
    backup_max_count: int = 5
    backup_scope: Optional[str] = "full"
    backup_targets: Optional[List[str]] = None
    backup_compression: Optional[bool] = True
    backup_stop_server: Optional[bool] = False
    backup_pre_command: Optional[str] = "save-all"

class WebhookConfigRequest(BaseModel):
    discord: Optional[Dict[str, Any]] = None
    telegram: Optional[Dict[str, Any]] = None
    email: Optional[Dict[str, Any]] = None
    events: Optional[Dict[str, Any]] = None

class TaskCreateRequest(BaseModel):
    name: str
    action: str
    command: Optional[str] = ""
    schedule_type: str = "interval"
    interval_value: Optional[int] = 1
    interval_unit: Optional[str] = "days"
    cron_expression: Optional[str] = "0 4 * * *"
    enabled: Optional[bool] = True

class TaskUpdateRequest(BaseModel):
    name: Optional[str] = None
    action: Optional[str] = None
    command: Optional[str] = None
    schedule_type: Optional[str] = None
    interval_value: Optional[int] = None
    interval_unit: Optional[str] = None
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None

class TaskToggleRequest(BaseModel):
    enabled: Optional[bool] = None

class RawPropertiesRequest(BaseModel):
    content: str

# --- Authentication Endpoints ---
@app.get("/api/auth/status")
async def auth_status(user: bool = Depends(get_current_user)):
    max_age = get_session_max_age()
    return {
        "auth_required": bool(settings.admin_password),
        "authenticated": True,
        "admin_user": getattr(settings, "admin_user", "admin"),
        "session_timeout_minutes": max_age // 60
    }

@app.post("/api/auth/refresh")
async def auth_refresh(response: Response, user: bool = Depends(get_current_user)):
    """Refreshes the active session token and sliding cookie timestamp."""
    new_token = create_session_token()
    max_age = get_session_max_age()
    response.set_cookie(key="dockraft_token", value=new_token, httponly=True, max_age=max_age, samesite="lax")
    response.set_cookie(key="litemc_token", value=new_token, httponly=True, max_age=max_age, samesite="lax")
    return {
        "status": "success",
        "token": new_token,
        "session_timeout_minutes": max_age // 60
    }

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    max_age = get_session_max_age()

    # 1. Rate limiting check: check if this IP is currently locked out
    is_locked, remaining = login_limiter.is_locked(client_ip)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Acceso bloqueado temporalmente. Reintente en {remaining} segundos.",
            headers={"Retry-After": str(remaining)}
        )

    # 2. If no admin password is configured, grant access directly
    if not settings.admin_password:
        login_limiter.record_success(client_ip)
        token = create_session_token()
        response.set_cookie(key="dockraft_token", value=token, httponly=True, max_age=max_age, samesite="lax")
        response.set_cookie(key="litemc_token", value=token, httponly=True, max_age=max_age, samesite="lax")
        return {"status": "success", "token": token, "session_timeout_minutes": max_age // 60}

    # 3. Verify admin credentials (username + password)
    if verify_admin_credentials(req.username, req.password):
        login_limiter.record_success(client_ip)
        token = create_session_token()
        response.set_cookie(key="dockraft_token", value=token, httponly=True, max_age=max_age, samesite="lax")
        response.set_cookie(key="litemc_token", value=token, httponly=True, max_age=max_age, samesite="lax")
        try:
            activity_manager.log("security", "Inicio de sesión exitoso", f"Usuario '{req.username or 'admin'}' conectado (IP: {client_ip})", user=req.username or "admin", status="success")
        except Exception:
            pass
        return {"status": "success", "token": token, "session_timeout_minutes": max_age // 60}

    # 4. Record failed attempt and check if threshold reached
    remaining_attempts, cooldown = login_limiter.record_failure(client_ip)
    if cooldown > 0:
        try:
            activity_manager.log("security", "Bloqueo por fuerza bruta", f"5 intentos fallidos superados (IP: {client_ip})", user="desconocido", status="error")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Ha alcanzado el límite de 5 intentos fallidos. Acceso bloqueado durante 10 minutos ({cooldown}s).",
            headers={"Retry-After": str(cooldown)}
        )

    try:
        activity_manager.log("security", "Intento de inicio fallido", f"Credenciales inválidas para '{req.username or 'admin'}' (IP: {client_ip})", user=req.username or "desconocido", status="warning")
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Credenciales inválidas. Intentos restantes antes del bloqueo: {remaining_attempts}"
    )

@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(key="dockraft_token")
    response.delete_cookie(key="litemc_token")
    try:
        activity_manager.log("security", "Cierre de sesión", "Sesión cerrada por el usuario", user="admin", status="info")
    except Exception:
        pass
    return {"status": "success", "message": "Sesión cerrada"}

@app.get("/logout")
async def logout_page():
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect_resp.delete_cookie(key="dockraft_token")
    redirect_resp.delete_cookie(key="litemc_token")
    return redirect_resp

# --- Health & Status Endpoints ---
@app.get("/api/health")
async def health_check():
    """Lightweight unauthenticated healthcheck endpoint for Docker."""
    return {"status": "ok"}

# --- Server Control Endpoints ---
@app.get("/api/server/status", dependencies=[Depends(get_current_user)])
async def server_status():
    return process_manager.get_stats()

@app.post("/api/server/start", dependencies=[Depends(get_current_user)])
async def server_start():
    return await process_manager.start_server()

@app.post("/api/server/stop", dependencies=[Depends(get_current_user)])
async def server_stop():
    return await process_manager.stop_server()

@app.post("/api/server/restart", dependencies=[Depends(get_current_user)])
async def server_restart():
    return await process_manager.restart_server()

@app.post("/api/server/kill", dependencies=[Depends(get_current_user)])
async def server_kill():
    return await process_manager.kill_server()

@app.post("/api/server/delete", dependencies=[Depends(get_current_user)])
async def delete_server():
    """Safely uninstalls/wipes the server files, keeping the backups directory intact."""
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de eliminarlo")

    protected_items = {"backups", "dockraft_config.json", "litemc_config.json"}
    deleted_count = 0
    try:
        for item in settings.data_dir.iterdir():
            if item.name in protected_items or item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
                deleted_count += 1
            elif item.is_file():
                try:
                    item.unlink()
                    deleted_count += 1
                except Exception:
                    pass

        # Reset runtime config
        settings.save_runtime_config({
            "server_type": "paper",
            "server_version": "",
            "server_file": "server.jar"
        })

        return {
            "status": "success",
            "message": "Servidor eliminado correctamente. Las copias de seguridad se han conservado.",
            "deleted_items": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar servidor: {str(e)}")

@app.post("/api/server/command", dependencies=[Depends(get_current_user)])
async def server_command(req: CommandRequest):
    return await process_manager.send_command(req.command)

@app.get("/api/server/eula", dependencies=[Depends(get_current_user)])
async def get_eula():
    eula_file = settings.data_dir / "eula.txt"
    accepted = False
    if eula_file.exists():
        with open(eula_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip().lower() == "eula=true":
                    accepted = True
                    break
    return {"accepted": accepted}

@app.post("/api/server/eula", dependencies=[Depends(get_current_user)])
async def set_eula(req: EulaRequest):
    eula_file = settings.data_dir / "eula.txt"
    val = "true" if req.accepted else "false"
    atomic_write_text(eula_file, f"# By changing the setting below to TRUE you are indicating your agreement to our EULA (https://account.mojang.com/documents/minecraft_eula).\neula={val}\n")
    return {"status": "success", "accepted": req.accepted}

# --- Configuration & Properties ---
@app.get("/api/config", dependencies=[Depends(get_current_user)])
async def get_config():
    return settings.runtime_config

@app.post("/api/config", dependencies=[Depends(get_current_user)])
async def update_config(config: Dict[str, Any]):
    settings.save_runtime_config(config)
    return {"status": "saved", "config": settings.runtime_config}

# --- Performance Telemetry & Metrics ---
@app.get("/api/metrics/history", dependencies=[Depends(get_current_user)])
async def get_metrics_history():
    """Returns chronological telemetry samples and summary statistics."""
    return {
        "history": metrics_manager.get_history(),
        "summary": metrics_manager.get_summary()
    }

@app.post("/api/metrics/reset", dependencies=[Depends(get_current_user)])
async def reset_metrics():
    """Clears recorded telemetry buffer and peaks."""
    metrics_manager.reset()
    return {"status": "reset", "summary": metrics_manager.get_summary()}

# --- Player Management Endpoints ---
@app.get("/api/players/list", dependencies=[Depends(get_current_user)])
async def get_players_list():
    """Returns unified player directory, active connections, and ban list."""
    return player_manager.get_all_data()

@app.post("/api/players/kick", dependencies=[Depends(get_current_user)])
async def kick_player(req: PlayerActionRequest):
    return await player_manager.kick_player(req.player, req.reason or "")

@app.post("/api/players/kick-all", dependencies=[Depends(get_current_user)])
async def kick_all_players(req: KickAllRequest = KickAllRequest()):
    return await player_manager.kick_all_players(req.reason or "Mantenimiento del servidor")

@app.post("/api/players/ban", dependencies=[Depends(get_current_user)])
async def ban_player(req: PlayerActionRequest):
    return await player_manager.ban_player(req.player, req.reason or "")

@app.post("/api/players/pardon", dependencies=[Depends(get_current_user)])
async def pardon_player(req: PlayerActionRequest):
    return await player_manager.pardon_player(req.player)

@app.post("/api/players/op", dependencies=[Depends(get_current_user)])
async def op_player(req: PlayerActionRequest):
    return await player_manager.set_op(req.player, True)

@app.post("/api/players/deop", dependencies=[Depends(get_current_user)])
async def deop_player(req: PlayerActionRequest):
    return await player_manager.set_op(req.player, False)

@app.post("/api/players/add", dependencies=[Depends(get_current_user)])
async def add_player(req: PlayerActionRequest):
    return player_manager.add_player(req.player)

@app.get("/api/server/properties", dependencies=[Depends(get_current_user)])
async def get_properties():
    """Reads server.properties if present and returns key-values."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    if not prop_file.exists():
        return {"exists": False, "server_type": server_type, "properties": {}}

    props: Dict[str, str] = {}
    with open(prop_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                props[key.strip()] = val.strip()

    # Alias sync for convenience across Java and Bedrock
    if "server-name" in props and "motd" not in props:
        props["motd"] = props["server-name"]
    elif "motd" in props and "server-name" not in props:
        props["server-name"] = props["motd"]

    if "allow-list" in props and "white-list" not in props:
        props["white-list"] = props["allow-list"]
    elif "white-list" in props and "allow-list" not in props:
        props["allow-list"] = props["white-list"]

    return {"exists": True, "server_type": server_type, "properties": props}

@app.post("/api/server/properties", dependencies=[Depends(get_current_user)])
async def save_properties(new_props: Dict[str, str]):
    """Updates key-values in server.properties, keeping formatting/comments where possible."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    lines = []
    keys_written = set()

    # Keep aliases synchronized
    to_save = dict(new_props)
    if "server-name" in to_save and "motd" not in to_save:
        to_save["motd"] = to_save["server-name"]
    elif "motd" in to_save and "server-name" not in to_save:
        to_save["server-name"] = to_save["motd"]

    if "allow-list" in to_save and "white-list" not in to_save:
        to_save["white-list"] = to_save["allow-list"]
    elif "white-list" in to_save and "allow-list" not in to_save:
        to_save["allow-list"] = to_save["white-list"]

    if prop_file.exists():
        with open(prop_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    key = key.strip()
                    if key in to_save:
                        lines.append(f"{key}={to_save[key]}\n")
                        keys_written.add(key)
                        continue
                lines.append(line)

    for k, v in to_save.items():
        if k not in keys_written:
            lines.append(f"{k}={v}\n")

    atomic_write_text(prop_file, "".join(lines))

    return {"status": "success", "server_type": server_type}

@app.get("/api/server/properties/raw", dependencies=[Depends(get_current_user)])
async def get_raw_properties():
    """Reads full raw text of server.properties."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    if not prop_file.exists():
        return {"exists": False, "server_type": server_type, "content": ""}
    content = prop_file.read_text(encoding="utf-8", errors="replace")
    return {"exists": True, "server_type": server_type, "content": content}

@app.post("/api/server/properties/raw", dependencies=[Depends(get_current_user)])
async def save_raw_properties(req: RawPropertiesRequest):
    """Saves full raw text of server.properties with atomic write."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    atomic_write_text(prop_file, req.content)
    return {"status": "success", "server_type": server_type}

# --- Java & Runtimes ---
@app.get("/api/java/runtimes", dependencies=[Depends(get_current_user)])
async def get_runtimes():
    return JavaManager.detect_runtimes()

# --- Downloader & Installer ---
@app.get("/api/installer/versions", dependencies=[Depends(get_current_user)])
async def get_installer_versions(type: str = Query("paper")):
    try:
        if type in ["paper", "folia", "velocity"]:
            versions = await downloader.get_paper_versions(type)
            return {"type": type, "versions": versions}
        elif type == "purpur":
            versions = await downloader.get_purpur_versions()
            return {"type": type, "versions": versions}
        elif type == "vanilla":
            versions = await downloader.get_vanilla_versions()
            return {"type": type, "versions": [v["id"] for v in versions]}
        elif type == "fabric":
            versions = await downloader.get_fabric_versions()
            return {"type": type, "versions": versions}
        elif type == "bedrock":
            versions = await downloader.get_bedrock_versions()
            return {"type": "bedrock", "versions": versions}
        elif type == "forge":
            versions = await downloader.get_forge_versions()
            return {"type": "forge", "versions": versions}
        else:
            raise HTTPException(status_code=400, detail="Invalid server type")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching versions: {str(e)}")

@app.get("/api/installer/progress", dependencies=[Depends(get_current_user)])
async def get_install_progress():
    data = downloader.active_download or {"status": "idle", "percent": 0}
    if data.get("status") == "completed":
        downloader.active_download = {"status": "idle", "percent": 100}
    return data

@app.post("/api/installer/install", dependencies=[Depends(get_current_user)])
async def install_server(req: InstallRequest):
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar o cambiar de versión")

    # Guard against accidental overwrite if server is already installed
    if _is_server_installed() and not req.force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura."
        )

    target_file = "server.jar"
    download_url = ""
    is_zip = False

    try:
        # Auto-resolve best Java runtime if not specifically provided
        if req.server_type != "bedrock":
            if not req.java_path or req.java_path == "java":
                req.java_path = JavaManager.get_best_java_path(req.version)

        if req.server_type in ["paper", "folia", "velocity"]:
            info = await downloader.get_paper_latest_build(req.server_type, req.version)
            download_url = info["download_url"]
            target_file = "server.jar"
        elif req.server_type == "purpur":
            info = await downloader.get_purpur_latest_build(req.version)
            download_url = info["download_url"]
            target_file = "server.jar"
        elif req.server_type == "vanilla":
            versions = await downloader.get_vanilla_versions()
            match = next((v for v in versions if v["id"] == req.version), None)
            if not match:
                raise HTTPException(status_code=404, detail="Version manifest not found")
            download_url = await downloader.get_vanilla_download_url(match["url"])
            target_file = "server.jar"
        elif req.server_type == "fabric":
            download_url = await downloader.get_fabric_download_url(req.version)
            target_file = "server.jar"
        elif req.server_type == "bedrock":
            platform = "win" if sys.platform == "win32" else "linux"
            download_url = await downloader.get_bedrock_download_url(req.version, platform=platform)
            target_file = "bedrock-server.zip"
            is_zip = True
        elif req.server_type == "forge":
            download_url = await downloader.get_forge_download_url(req.version)
            target_file = "forge-installer.jar"
        else:
            raise HTTPException(status_code=400, detail="Unsupported server type")

        if req.server_type == "forge":
            java_bin = req.java_path or "java"
            async def forge_install_pipeline():
                try:
                    installer_path = await downloader.download_file(download_url, target_file)
                    res = await downloader.install_forge_server(installer_path, java_bin=java_bin)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh")
                    })
                except Exception as ex:
                    print(f"[Dockraft] Forge install pipeline error: {ex}")

            asyncio.create_task(forge_install_pipeline())
        else:
            # Start download in background task
            asyncio.create_task(downloader.download_file(download_url, target_file, is_zip=is_zip))

        # Update runtime config
        resolved_server_file = (
            ("bedrock_server.exe" if sys.platform == "win32" else "bedrock_server")
            if req.server_type == "bedrock"
            else ("run.sh" if req.server_type == "forge" else "server.jar")
        )

        settings.save_runtime_config({
            "server_type": req.server_type,
            "server_version": req.version,
            "server_file": resolved_server_file,
            "server_name": req.server_name or "Mi Servidor Dockraft",
            "java_path": req.java_path or "java",
            "min_ram": req.min_ram or "1G",
            "max_ram": req.max_ram or "2G",
            "aikar_flags": req.aikar_flags if req.aikar_flags is not None else True,
            "cpu_cores": req.cpu_cores if req.cpu_cores is not None else 2,
            "disk_limit_gb": req.disk_limit_gb if req.disk_limit_gb is not None else 10.0
        })

        return {"status": "started", "target_file": target_file, "download_url": download_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/installer/update-info", dependencies=[Depends(get_current_user)])
async def get_update_info():
    """Returns update status and classified versions for the currently installed server type."""
    if not _is_server_installed():
        return {
            "is_installed": False,
            "server_type": None,
            "current_version": None,
            "current_channel": "unknown",
            "latest_stable": "",
            "latest_preview": "",
            "update_available": False,
            "preview_available": False,
            "available_versions": [],
            "versions": []
        }

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    current_version = cfg.get("server_version", "")
    server_file = cfg.get("server_file")

    # If version is generic, missing, or imported, attempt auto-detection from local files
    if not current_version or current_version.lower() in ["importado", "desconocida", "unknown"]:
        detected_ver = downloader.detect_server_version(server_file=server_file)
        if detected_ver:
            current_version = detected_ver
            settings.save_runtime_config({"server_version": detected_ver})
        else:
            current_version = "importado"
    
    latest_stable = ""
    latest_preview = ""
    version_items = []

    try:
        if server_type == "bedrock":
            b_vers = await downloader.get_bedrock_versions()
            for bv in b_vers:
                m = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)+)', bv)
                vid = m.group(1) if m else bv
                is_prev = "preview" in bv.lower() or "beta" in bv.lower()
                ch = "preview" if is_prev else "stable"
                lbl = f"{vid} (Estable)" if not is_prev else f"{vid} (Preview / Beta)"
                version_items.append({"id": bv, "label": lbl, "channel": ch})
                if not is_prev and not latest_stable:
                    latest_stable = vid
                elif is_prev and not latest_preview:
                    latest_preview = vid

        elif server_type == "vanilla":
            latest_info = await downloader.get_vanilla_latest()
            latest_stable = latest_info.get("release", "")
            latest_preview = latest_info.get("snapshot", "")
            
            raw_versions = await downloader.get_vanilla_versions()
            for v in raw_versions:
                vid = v["id"]
                vtype = v.get("type", "")
                if vtype == "release":
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                elif "-pre" in vid or "pre-release" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                elif "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Release Candidate)"
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type == "fabric":
            fabric_items = await downloader.get_fabric_version_items()
            for f in fabric_items:
                vid = f["id"]
                is_st = f.get("stable", False)
                if is_st:
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                    if not latest_stable:
                        latest_stable = vid
                elif "-pre" in vid or "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                    if not latest_preview:
                        latest_preview = vid
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                    if not latest_preview:
                        latest_preview = vid
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type in ["paper", "folia", "velocity"]:
            paper_versions = await downloader.get_paper_versions(server_type)
            for pv in paper_versions:
                ch = "pre" if "-pre" in pv or "-rc" in pv else "stable"
                lbl = f"{pv} (Estable)" if ch == "stable" else f"{pv} (Pre-Release)"
                version_items.append({"id": pv, "label": lbl, "channel": ch})
                if ch == "stable" and not latest_stable:
                    latest_stable = pv
                elif ch != "stable" and not latest_preview:
                    latest_preview = pv

        elif server_type == "purpur":
            purpur_versions = await downloader.get_purpur_versions()
            for pv in purpur_versions:
                version_items.append({"id": pv, "label": f"{pv} (Estable)", "channel": "stable"})
            if purpur_versions:
                latest_stable = purpur_versions[0]

        elif server_type == "forge":
            forge_list = await downloader.get_forge_versions()
            for fv in forge_list:
                vid = fv["mc_version"]
                is_rec = fv.get("is_recommended", False)
                ch = "stable" if is_rec else "preview"
                version_items.append({"id": vid, "label": fv["label"], "channel": ch})
                if is_rec and not latest_stable:
                    latest_stable = vid
                elif not is_rec and not latest_preview:
                    latest_preview = vid

    except Exception as e:
        print(f"[UpdateInfo] Error querying versions for {server_type}: {e}")

    # Determine current version channel
    curr_l = current_version.lower()
    if server_type == "bedrock":
        current_channel = "preview" if ("preview" in curr_l or "beta" in curr_l) else "stable"
    elif "-pre" in curr_l or "pre-release" in curr_l:
        current_channel = "pre"
    elif "-rc" in curr_l:
        current_channel = "rc"
    elif "snapshot" in curr_l or re.search(r'^[0-9]{2}w[0-9]{2}[a-z]$', curr_l):
        current_channel = "snapshot"
    else:
        current_channel = "stable"

    curr_m = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)+)', current_version)
    curr_clean = curr_m.group(1) if curr_m else current_version

    # Update available:
    update_available = False
    if current_version == "importado":
        update_available = bool(latest_stable)
    elif current_channel == "stable":
        if latest_stable and curr_clean and latest_stable != curr_clean:
            update_available = True
    else:
        # If on pre or snapshot, notify if latest preview is different
        if latest_preview and current_version != latest_preview:
            update_available = True

    preview_available = bool(latest_preview and latest_preview != current_version and latest_preview != latest_stable)

    return {
        "is_installed": True,
        "server_type": server_type,
        "current_version": current_version,
        "current_channel": current_channel,
        "latest_stable": latest_stable,
        "latest_preview": latest_preview,
        "update_available": update_available,
        "preview_available": preview_available,
        "available_versions": [it["label"] for it in version_items],
        "versions": version_items
    }

@app.post("/api/installer/update", dependencies=[Depends(get_current_user)])
async def update_server(req: UpdateRequest):
    """Safely updates the existing server to a new version of the same software,
    preserving configs and worlds, auto-stopping gracefully if running,
    creating a pre-update backup, and verifying file integrity against corruption."""
    if not _is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado para actualizar")

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    old_server_file = cfg.get("server_file")
    target_file = "server.jar"
    download_url = ""
    is_zip = False

    try:
        if server_type in ["paper", "folia", "velocity"]:
            info = await downloader.get_paper_latest_build(server_type, req.version)
            download_url = info["download_url"]
            target_file = "server.jar"
        elif server_type == "purpur":
            info = await downloader.get_purpur_latest_build(req.version)
            download_url = info["download_url"]
            target_file = "server.jar"
        elif server_type == "vanilla":
            versions = await downloader.get_vanilla_versions()
            match = next((v for v in versions if v["id"] == req.version), None)
            if not match:
                raise HTTPException(status_code=404, detail="Version manifest not found")
            download_url = await downloader.get_vanilla_download_url(match["url"])
            target_file = "server.jar"
        elif server_type == "fabric":
            download_url = await downloader.get_fabric_download_url(req.version)
            target_file = "server.jar"
        elif server_type == "bedrock":
            platform = "win" if sys.platform == "win32" else "linux"
            download_url = await downloader.get_bedrock_download_url(req.version, platform=platform)
            target_file = "bedrock-server.zip"
            is_zip = True
        elif server_type == "forge":
            download_url = await downloader.get_forge_download_url(req.version)
            target_file = "forge-installer.jar"
        else:
            raise HTTPException(status_code=400, detail="Tipo de servidor no soportado para actualización")

        was_running = process_manager.get_status() != "OFFLINE"

        async def safe_update_pipeline():
            try:
                # 1. Stop gracefully if running
                if was_running:
                    msg = "[Dockraft] Deteniendo servidor de forma segura para aplicar actualización..."
                    process_manager._append_log(msg)
                    await process_manager.broadcast_message({"type": "log", "data": msg})
                    await process_manager.send_command("save-all", echo=False)
                    await process_manager.stop_server()
                    # Wait for offline status
                    for _ in range(30):
                        await asyncio.sleep(1)
                        if process_manager.get_status() == "OFFLINE":
                            break
                    if process_manager.get_status() != "OFFLINE":
                        await process_manager.kill_server()

                # 2. Create pre-update backup
                msg = f"[Dockraft] Generando copia de seguridad preventiva (pre-update-{req.version})..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})
                pre_backup = await backup_manager.create_backup(
                    scope="full",
                    tag=f"pre-update-{req.version}",
                    compress=True
                )
                if pre_backup.get("status") == "error":
                    err_msg = f"[Dockraft] Error al crear copia preventiva: {pre_backup.get('message')}. Abortando actualización para seguridad de datos."
                    process_manager._append_log(err_msg)
                    await process_manager.broadcast_message({"type": "log", "data": err_msg})
                    if was_running:
                        await process_manager.start_server()
                    return

                # 3. Download and verify integrity
                msg = f"[Dockraft] Descargando actualización {req.version} y verificando integridad anti-corrupción..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})

                if server_type == "forge":
                    java_path = cfg.get("java_path") or JavaManager.get_best_java_path(req.version)
                    installer_path = await downloader.download_file(
                        download_url,
                        target_file,
                        preserve_existing_configs=True,
                        verify_integrity=True
                    )
                    res = await downloader.install_forge_server(installer_path, java_bin=java_path)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh"),
                        "server_version": req.version
                    })
                else:
                    await downloader.download_file(
                        download_url,
                        target_file,
                        is_zip=is_zip,
                        preserve_existing_configs=True,
                        verify_integrity=True
                    )
                    if old_server_file and old_server_file != target_file and not is_zip:
                        old_path = settings.data_dir / old_server_file
                        if old_path.exists():
                            try:
                                old_path.unlink()
                            except Exception:
                                pass

                    settings.save_runtime_config({
                        "server_file": target_file if not is_zip else old_server_file or "bedrock_server",
                        "server_version": req.version
                    })

                # Log activity
                activity_manager.log(
                    category="update",
                    action="Servidor actualizado",
                    details=f"Actualizado con éxito a versión {req.version} ({server_type.upper()}). Respaldo preventivo: {pre_backup.get('filename')}",
                    user="admin",
                    status="success"
                )

                succ_msg = f"[Dockraft] ¡Servidor actualizado exitosamente a la versión {req.version}!"
                process_manager._append_log(succ_msg)
                await process_manager.broadcast_message({"type": "log", "data": succ_msg})

                # 4. Restart if was running
                if was_running:
                    restart_msg = "[Dockraft] Reiniciando servidor automáticamente con la nueva versión..."
                    process_manager._append_log(restart_msg)
                    await process_manager.broadcast_message({"type": "log", "data": restart_msg})
                    await asyncio.sleep(1.5)
                    await process_manager.start_server()

            except Exception as ex:
                err_msg = f"[Dockraft] Error en la actualización a {req.version}: {str(ex)}"
                process_manager._append_log(err_msg)
                await process_manager.broadcast_message({"type": "log", "data": err_msg})
                activity_manager.log(
                    category="update",
                    action="Error en actualización",
                    details=f"Fallo al actualizar a {req.version}: {str(ex)}",
                    user="admin",
                    status="error"
                )
                if was_running and process_manager.get_status() == "OFFLINE":
                    await process_manager.start_server()

        asyncio.create_task(safe_update_pipeline())

        # Update saved version in runtime config optimistically
        settings.save_runtime_config({"server_version": req.version})

        return {
            "status": "started",
            "server_type": server_type,
            "target_version": req.version,
            "download_url": download_url,
            "auto_stopping": was_running
        }

    except HTTPException:
        raise
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail="Version not found")
        if "HTTPStatusError" in type(e).__name__:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# --- Activity / Audit Log Endpoints ---
@app.get("/api/activity/logs", dependencies=[Depends(get_current_user)])
async def get_activity_logs(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Returns filtered and paginated activity logs and category counts."""
    return activity_manager.get_logs(category=category, search=search, limit=limit, offset=offset)

@app.post("/api/activity/clear", dependencies=[Depends(get_current_user)])
async def clear_activity_logs():
    """Clears all logged activities."""
    activity_manager.clear_logs()
    activity_manager.log("security", "Historial de registros vaciado", "El administrador vació el registro de actividad", user="admin", status="warning")
    return {"status": "success", "message": "Registros de actividad vaciados correctamente"}

@app.get("/api/activity/export", dependencies=[Depends(get_current_user)])
async def export_activity_logs(format: str = Query("csv", pattern="^(txt|json|csv)$")):
    """Exports activity logs as CSV, plain text or JSON file."""
    content = activity_manager.export_logs(format_type=format)
    if format == "json":
        media_type = "application/json"
    elif format == "csv":
        media_type = "text/csv; charset=utf-8"
    else:
        media_type = "text/plain; charset=utf-8"
    filename = f"dockraft_activity_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# --- File Manager Endpoints ---
@app.get("/api/files/list", dependencies=[Depends(get_current_user)])
async def file_list(path: str = Query("")):
    return file_manager.list_directory(path)

@app.get("/api/files/content", dependencies=[Depends(get_current_user)])
async def file_content(path: str = Query(...)):
    return file_manager.read_file(path)

@app.post("/api/files/save", dependencies=[Depends(get_current_user)])
async def file_save(req: FileSaveRequest):
    return file_manager.write_file(req.path, req.content)

@app.post("/api/files/folder", dependencies=[Depends(get_current_user)])
async def file_folder(req: FolderCreateRequest):
    return file_manager.create_folder(req.path)

@app.delete("/api/files/delete", dependencies=[Depends(get_current_user)])
async def file_delete(path: str = Query(...)):
    return file_manager.delete_item(path)

@app.post("/api/files/upload", dependencies=[Depends(get_current_user)])
async def file_upload(path: str = Form(""), file: UploadFile = File(...)):
    return await file_manager.save_upload(path, file)

@app.post("/api/files/unzip", dependencies=[Depends(get_current_user)])
async def file_unzip(req: UnzipRequest):
    return file_manager.extract_zip(req.path, req.target_dir)

@app.get("/api/files/download", dependencies=[Depends(get_current_user)])
async def file_download(path: str = Query(...)):
    safe_path = file_manager._resolve_safe_path(path)
    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(safe_path),
        filename=safe_path.name,
        media_type="application/octet-stream"
    )

@app.post("/api/files/rename", dependencies=[Depends(get_current_user)])
async def file_rename(req: FileRenameRequest):
    return file_manager.rename_item(req.path, req.new_name)

@app.post("/api/files/duplicate", dependencies=[Depends(get_current_user)])
async def file_duplicate(req: FileDuplicateRequest):
    return file_manager.duplicate_item(req.path)

@app.post("/api/files/compress", dependencies=[Depends(get_current_user)])
async def file_compress(req: FileCompressRequest):
    return file_manager.compress_item(req.path)

@app.post("/api/files/create", dependencies=[Depends(get_current_user)])
async def file_create(req: FileCreateRequest):
    return file_manager.create_file(req.path)

# --- Server Import Endpoint ---
@app.post("/api/server/import", dependencies=[Depends(get_current_user)])
async def import_server(file: UploadFile = File(...), accept_eula: bool = Form(True)):
    """Imports an existing Minecraft server from an uploaded zip archive."""
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de importar")
    
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="El archivo debe tener formato .zip")

    temp_zip = settings.data_dir / f"import_temp_{int(time.time())}.zip"
    try:
        with open(temp_zip, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ZipSlip check
        with zipfile.ZipFile(temp_zip, 'r') as zf:
            for member in zf.namelist():
                dest = (settings.data_dir / member).resolve()
                if not dest.is_relative_to(settings.data_dir.resolve()):
                    raise HTTPException(status_code=400, detail="Archivo zip no seguro (ZipSlip detectado)")
            zf.extractall(settings.data_dir)

        # Detect server type from extracted contents
        detected_type = "paper"
        detected_file = "server.jar"

        if (settings.data_dir / "bedrock_server").exists() or (settings.data_dir / "bedrock_server.exe").exists():
            detected_type = "bedrock"
            detected_file = "bedrock_server.exe" if sys.platform == "win32" else "bedrock_server"
            if sys.platform != "win32":
                try:
                    os.chmod(settings.data_dir / "bedrock_server", 0o755)
                except Exception:
                    pass
        elif (settings.data_dir / "run.sh").exists():
            detected_type = "forge"
            detected_file = "run.sh"
            if sys.platform != "win32":
                try:
                    os.chmod(settings.data_dir / "run.sh", 0o755)
                except Exception:
                    pass
        else:
            for f in settings.data_dir.iterdir():
                if f.is_file() and f.name.endswith(".jar"):
                    fn = f.name.lower()
                    if "forge" in fn:
                        detected_type = "forge"
                        detected_file = f.name
                        break
                    elif "fabric" in fn:
                        detected_type = "fabric"
                        detected_file = f.name
                        break
                    elif "purpur" in fn:
                        detected_type = "purpur"
                        detected_file = f.name
                        break
                    elif "paper" in fn:
                        detected_type = "paper"
                        detected_file = f.name
                        break
                    elif "server" in fn:
                        detected_file = f.name

        if accept_eula:
            downloader.accept_eula()

        detected_version = downloader.detect_server_version(server_file=detected_file) or "importado"

        settings.save_runtime_config({
            "server_type": detected_type,
            "server_file": detected_file,
            "server_version": detected_version
        })

        return {
            "status": "success",
            "message": f"Servidor importado correctamente como '{detected_type}' ({detected_file})",
            "server_type": detected_type,
            "server_file": detected_file
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al importar el servidor: {str(e)}")
    finally:
        if temp_zip.exists():
            try:
                temp_zip.unlink()
            except Exception:
                pass

# --- Backup Management Endpoints ---
@app.get("/api/backups/list", dependencies=[Depends(get_current_user)])
async def get_backups():
    return backup_manager.list_backups()

@app.get("/api/backups/targets", dependencies=[Depends(get_current_user)])
async def get_backup_targets():
    return backup_manager.get_available_targets()

@app.post("/api/backups/create", dependencies=[Depends(get_current_user)])
async def create_backup(req: BackupCreateRequest):
    cfg = settings.runtime_config
    compression = req.compression if req.compression is not None else cfg.get("backup_compression", True)
    stop_server = req.stop_server if req.stop_server is not None else cfg.get("backup_stop_server", False)
    pre_cmd = req.pre_command if req.pre_command is not None else cfg.get("backup_pre_command", "")

    was_running = process_manager.get_status() != "OFFLINE"

    if was_running and pre_cmd and pre_cmd.strip():
        await process_manager.send_command(pre_cmd.strip())
        await asyncio.sleep(2)

    if was_running and stop_server:
        await process_manager.stop_server()
        for _ in range(25):
            await asyncio.sleep(1)
            if process_manager.get_status() == "OFFLINE":
                break
        if process_manager.get_status() != "OFFLINE":
            await process_manager.kill_server()
            await asyncio.sleep(1)

    try:
        res = backup_manager.create_backup(
            tag=req.tag or "manual",
            scope=req.scope or "full",
            targets=req.targets,
            compression=compression
        )
        if res.get("status") == "success":
            try:
                activity_manager.log("backup", "Copia creada", f"Archivo: {res.get('filename')} | Tamaño: {res.get('size_human', 'N/A')}", user="admin", status="success")
            except Exception:
                pass
        return res
    finally:
        if was_running and stop_server:
            await asyncio.sleep(1)
            await process_manager.start_server()

@app.post("/api/backups/restore", dependencies=[Depends(get_current_user)])
async def restore_backup(req: BackupRestoreRequest):
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de restaurar una copia de seguridad")
    res = backup_manager.restore_backup(req.filename)
    if res.get("status") == "success":
        try:
            activity_manager.log("backup", "Copia restaurada", f"Restaurada copia '{req.filename}'", user="admin", status="warning")
        except Exception:
            pass
    return res

@app.delete("/api/backups/{filename}", dependencies=[Depends(get_current_user)])
async def delete_backup(filename: str):
    res = backup_manager.delete_backup(filename)
    if res.get("status") == "success":
        try:
            activity_manager.log("backup", "Copia eliminada", f"Eliminada copia '{filename}'", user="admin", status="info")
        except Exception:
            pass
    return res

@app.get("/api/backups/download/{filename}", dependencies=[Depends(get_current_user)])
async def download_backup(filename: str):
    target_path = backup_manager.get_backup_path(filename)
    return FileResponse(
        str(target_path),
        filename=target_path.name,
        media_type="application/zip"
    )

@app.get("/api/backups/config", dependencies=[Depends(get_current_user)])
async def get_backup_config():
    cfg = settings.runtime_config
    return {
        "auto_backup": cfg.get("auto_backup", False),
        "backup_interval_hours": cfg.get("backup_interval_hours", 24),
        "backup_max_count": cfg.get("backup_max_count", 5),
        "backup_scope": cfg.get("backup_scope", "full"),
        "backup_targets": cfg.get("backup_targets", []),
        "backup_compression": cfg.get("backup_compression", True),
        "backup_stop_server": cfg.get("backup_stop_server", False),
        "backup_pre_command": cfg.get("backup_pre_command", "save-all")
    }

@app.post("/api/backups/config", dependencies=[Depends(get_current_user)])
async def save_backup_config(req: BackupConfigRequest):
    update_data = {
        "backup_max_count": req.backup_max_count,
        "backup_scope": req.backup_scope or "full",
        "backup_targets": req.backup_targets if req.backup_targets is not None else [],
        "backup_compression": req.backup_compression if req.backup_compression is not None else True,
        "backup_stop_server": req.backup_stop_server if req.backup_stop_server is not None else False,
        "backup_pre_command": req.backup_pre_command if req.backup_pre_command is not None else "save-all"
    }
    if req.auto_backup is not None:
        update_data["auto_backup"] = req.auto_backup
    if req.backup_interval_hours is not None:
        update_data["backup_interval_hours"] = req.backup_interval_hours
    settings.save_runtime_config(update_data)
    return {"status": "saved", "config": settings.runtime_config}

# --- Webhook Management Endpoints ---
@app.get("/api/webhooks/config", dependencies=[Depends(get_current_user)])
async def get_webhooks_config():
    return webhook_manager.load_config()

@app.post("/api/webhooks/config", dependencies=[Depends(get_current_user)])
async def save_webhooks_config(req: WebhookConfigRequest):
    saved = webhook_manager.save_config(req.model_dump(exclude_unset=True))
    return {"status": "saved", "config": saved}

@app.post("/api/webhooks/test/{channel}", dependencies=[Depends(get_current_user)])
async def test_webhook_channel(channel: str):
    res = await webhook_manager.test_channel(channel.lower())
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Error enviando notificación de prueba"))
    return res

# --- Scheduled Tasks Endpoints ---
@app.get("/api/tasks", dependencies=[Depends(get_current_user)])
async def list_tasks():
    return task_scheduler.list_tasks()

@app.post("/api/tasks", dependencies=[Depends(get_current_user)])
async def create_task(req: TaskCreateRequest):
    return task_scheduler.create_task(req.model_dump())

@app.get("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def get_task(task_id: str):
    t = task_scheduler.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t

@app.put("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def update_task(task_id: str, req: TaskUpdateRequest):
    t = task_scheduler.update_task(task_id, req.model_dump(exclude_unset=True))
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t

@app.delete("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def delete_task(task_id: str):
    success = task_scheduler.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {"status": "deleted", "id": task_id}

@app.post("/api/tasks/{task_id}/toggle", dependencies=[Depends(get_current_user)])
async def toggle_task(task_id: str, req: Optional[TaskToggleRequest] = None):
    enabled = req.enabled if req else None
    t = task_scheduler.toggle_task(task_id, enabled)
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t

@app.post("/api/tasks/{task_id}/run", dependencies=[Depends(get_current_user)])
async def run_task(task_id: str):
    try:
        return await task_scheduler.run_task_now(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando tarea: {str(e)}")

# --- Scheduled Background Tasks Loop (now handled by lifespan above) ---

# --- Diagnostics & Log Sharing Endpoints ---
class ShareLogRequest(BaseModel):
    content: Optional[str] = None

@app.get("/api/diagnostics/analyze", dependencies=[Depends(get_current_user)])
async def analyze_diagnostics():
    """Analyzes logs and crash-reports to identify issues and actionable solutions."""
    return diagnostic_manager.analyze_diagnostics()

@app.post("/api/diagnostics/share", dependencies=[Depends(get_current_user)])
async def share_log(req: Optional[ShareLogRequest] = None):
    """Uploads sanitized logs to mclo.gs and returns a clean shareable URL."""
    custom_content = req.content if req else None
    res = await diagnostic_manager.share_to_mclogs(custom_content)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Error al compartir log en mclo.gs"))
    return res

# --- Plugins & SpigotMC Update Checker Endpoints ---
from app.core.plugin_manager import plugin_manager

@app.get("/api/plugins/list", dependencies=[Depends(get_current_user)])
async def list_installed_plugins():
    """Returns all installed plugins detected in data/plugins/*.jar."""
    plugins = plugin_manager.scan_installed_plugins()
    return {"status": "success", "plugins": plugins, "count": len(plugins)}

@app.post("/api/plugins/check-updates", dependencies=[Depends(get_current_user)])
async def check_plugin_updates():
    """Queries Spiget API to check for available updates of installed plugins."""
    results = await plugin_manager.check_plugin_updates()
    outdated = [p for p in results if p.get("has_update")]
    return {"status": "success", "plugins": results, "total": len(results), "outdated_count": len(outdated)}

@app.get("/api/plugins/console-updates", dependencies=[Depends(get_current_user)])
async def get_console_plugin_updates():
    """Returns all plugin update notices detected from console logs."""
    updates = plugin_manager.get_detected_updates()
    return {"status": "success", "updates": updates, "count": len(updates)}

@app.post("/api/plugins/scan-console", dependencies=[Depends(get_current_user)])
async def scan_console_plugin_updates():
    """Scans data/logs/latest.log and returns detected plugin updates."""
    updates = plugin_manager.scan_console_logs()
    return {"status": "success", "updates": updates, "count": len(updates)}

@app.post("/api/plugins/notify-updates", dependencies=[Depends(get_current_user)])
async def notify_plugin_updates():
    """Checks for plugin updates and broadcasts a webhook notification if any are outdated."""
    return await plugin_manager.check_and_notify_updates()

@app.delete("/api/plugins/console-updates/{plugin_name}", dependencies=[Depends(get_current_user)])
async def dismiss_console_plugin_update(plugin_name: str):
    """Dismisses/removes a specific plugin update notice."""
    removed = plugin_manager.dismiss_update(plugin_name)
    return {"status": "success", "removed": removed, "plugin": plugin_name}

@app.delete("/api/plugins/console-updates", dependencies=[Depends(get_current_user)])
async def clear_all_console_plugin_updates():
    """Dismisses/clears all detected plugin update notices."""
    count = plugin_manager.clear_detected_updates()
    return {"status": "success", "cleared_count": count}

# --- WebSocket Console & Stats Hub ---
@app.websocket("/ws/console")
async def websocket_console(websocket: WebSocket, token: Optional[str] = Query(None)):
    # Authenticate websocket connection
    if settings.admin_password:
        cookie_token = (
            websocket.cookies.get("dockraft_token")
            or websocket.cookies.get("dockraft_session")
            or websocket.cookies.get("litemc_token")
        )
        effective_token = token or cookie_token
        if not effective_token or not verify_session_token(effective_token):
            # Must accept() before being able to close() with a code in WebSocket protocol
            await websocket.accept()
            await websocket.close(code=4001)
            return

    await websocket.accept()
    process_manager.connected_websockets.add(websocket)

    # Send initial backlog and status
    try:
        initial_stats = process_manager.get_stats()
        await websocket.send_json({
            "type": "init",
            "status": process_manager.get_status(),
            "history": list(process_manager.log_buffer)  # deque is not JSON-serializable — must cast to list
        })
        # Send initial stats immediately so client doesn't wait 2s
        await websocket.send_json({
            "type": "stats",
            "data": initial_stats
        })
        
        # Periodic stats loop
        async def stats_pusher():
            while True:
                await asyncio.sleep(2)
                try:
                    await websocket.send_json({
                        "type": "stats",
                        "data": process_manager.get_stats()
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
        if 'stats_task' in locals() and not stats_task.done():
            stats_task.cancel()

# --- Serve Static UI & Modular Jinja2 Templates ---
WEB_DIR = BASE_DIR / "web"
if (WEB_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

templates_dir = WEB_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Isolated secure login page rendered via Jinja2."""
    session_expired = request.query_params.get("expired") == "1"

    # If no password is required or user is already authenticated (and not arriving as expired), redirect straight to dashboard
    if not settings.admin_password or (is_authenticated(request) and not session_expired):
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    client_ip = request.client.host if request.client else "unknown"
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
            "session_expired": session_expired
        }
    )
    if session_expired:
        resp.delete_cookie("dockraft_token")
        resp.delete_cookie("litemc_token")
    return resp

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Main Dockraft Dashboard view.
    Requires active session if admin_password is configured.
    Unauthenticated users are redirected to /login.
    """
    if settings.admin_password and not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    stats = process_manager.get_stats()
    cfg = settings.runtime_config
    is_installed = bool(stats.get("is_installed", False))
    server_status = stats.get("status", "OFFLINE")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "admin_user": getattr(settings, "admin_user", "admin"),
            "app_name": "Dockraft",
            "stats": stats,
            "cfg": cfg,
            "is_installed": is_installed,
            "server_status": server_status,
            "server_name": stats.get("server_name") or cfg.get("server_name", "Mi Servidor Dockraft"),
            "server_version": stats.get("server_version") or cfg.get("server_version", ""),
            "server_type": stats.get("server_type") or cfg.get("server_type", ""),
            "motd": stats.get("motd", ""),
            "stats_json": json.dumps(stats),
            "cfg_json": json.dumps(cfg)
        }
    )
