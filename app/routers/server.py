import os
import sys
import re
import time
import shutil
import zipfile
import asyncio
from pathlib import Path
from typing import Dict, Optional, List, Union
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.config import settings
from app.core.security import get_current_user
from app.core.process_manager import process_manager
from app.core.downloader import downloader
from app.core.file_manager import file_manager
from app.core.java_manager import JavaManager
from app.core.metrics_manager import metrics_manager
from app.core.fs_utils import atomic_write_text, PROTECTED_INTERNAL_FILES, safe_extract_zip

router = APIRouter(tags=["server"])


class CommandRequest(BaseModel):
    command: str


class EulaRequest(BaseModel):
    accepted: bool


class RawPropertiesRequest(BaseModel):
    content: str


class RuntimeConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    server_name: Optional[str] = None
    server_type: Optional[str] = None
    server_version: Optional[str] = None
    server_build: Optional[Union[str, int]] = None
    server_file: Optional[str] = None
    java_path: Optional[str] = None
    java_version: Optional[int] = None
    min_ram: Optional[str] = None
    max_ram: Optional[str] = None
    aikar_flags: Optional[bool] = None
    custom_jvm_flags: Optional[str] = None
    eula_accepted: Optional[bool] = None
    auto_restart: Optional[bool] = None
    disk_limit_gb: Optional[float] = Field(default=None, ge=0.0, le=10240.0)
    cpu_cores: Optional[int] = Field(default=None, ge=0, le=128)
    auto_backup: Optional[bool] = None
    backup_interval_hours: Optional[int] = Field(default=None, ge=1, le=720)
    backup_max_count: Optional[int] = Field(default=None, ge=1, le=500)
    backup_scope: Optional[str] = None
    backup_targets: Optional[List[str]] = None
    backup_compression: Optional[bool] = None
    backup_stop_server: Optional[bool] = None
    backup_pre_command: Optional[str] = None
    autostart_server: Optional[bool] = None
    crash_detection: Optional[bool] = None
    session_timeout_minutes: Optional[int] = Field(default=None, ge=1, le=10080)

    @field_validator("min_ram", "max_ram")
    @classmethod
    def validate_ram_format(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.match(r"^\d+[MGmg]$", v):
                raise ValueError("El formato de RAM debe ser numérico seguido de M o G (ej: 1G, 2048M)")
        return v

    @field_validator("server_file")
    @classmethod
    def validate_server_file(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v or ".." in v or "/" in v or "\\" in v or v in PROTECTED_INTERNAL_FILES:
                raise ValueError("Nombre de archivo ejecutable del servidor no válido")
        return v


def _sync_property_aliases(props: Dict[str, str]) -> None:
    """Synchronizes Java/Bedrock equivalent property keys in-place."""
    if "server-name" in props and "motd" not in props:
        props["motd"] = props["server-name"]
    elif "motd" in props and "server-name" not in props:
        props["server-name"] = props["motd"]

    if "allow-list" in props and "white-list" not in props:
        props["white-list"] = props["allow-list"]
    elif "white-list" in props and "allow-list" not in props:
        props["allow-list"] = props["white-list"]


@router.get("/api/health")
async def health_check():
    """Lightweight unauthenticated healthcheck endpoint for Docker."""
    return {"status": "ok"}


@router.get("/api/server/status", dependencies=[Depends(get_current_user)])
async def server_status():
    return process_manager.get_stats()


@router.post("/api/server/start", dependencies=[Depends(get_current_user)])
async def server_start():
    return await process_manager.start_server()


@router.post("/api/server/stop", dependencies=[Depends(get_current_user)])
async def server_stop():
    return await process_manager.stop_server()


@router.post("/api/server/restart", dependencies=[Depends(get_current_user)])
async def server_restart():
    return await process_manager.restart_server()


@router.post("/api/server/kill", dependencies=[Depends(get_current_user)])
async def server_kill():
    return await process_manager.kill_server()


@router.post("/api/server/delete", dependencies=[Depends(get_current_user)])
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

        settings.save_runtime_config({
            "server_type": "paper",
            "server_version": "",
            "server_file": "server.jar",
        })

        return {
            "status": "success",
            "message": "Servidor eliminado correctamente. Las copias de seguridad se han conservado.",
            "deleted_items": deleted_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar servidor: {str(e)}")


@router.post("/api/server/command", dependencies=[Depends(get_current_user)])
async def server_command(req: CommandRequest):
    return await process_manager.send_command(req.command)


@router.get("/api/server/eula", dependencies=[Depends(get_current_user)])
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


@router.post("/api/server/eula", dependencies=[Depends(get_current_user)])
async def set_eula(req: EulaRequest):
    eula_file = settings.data_dir / "eula.txt"
    val = "true" if req.accepted else "false"
    atomic_write_text(
        eula_file,
        f"# By changing the setting below to TRUE you are indicating your agreement to our EULA (https://account.mojang.com/documents/minecraft_eula).\neula={val}\n",
    )
    return {"status": "success", "accepted": req.accepted}


@router.get("/api/config", dependencies=[Depends(get_current_user)])
async def get_config():
    return settings.runtime_config


@router.post("/api/config", dependencies=[Depends(get_current_user)])
async def update_config(config: RuntimeConfigUpdate):
    settings.save_runtime_config(config.model_dump(exclude_unset=True))
    return {"status": "saved", "config": settings.runtime_config}


@router.get("/api/metrics/history", dependencies=[Depends(get_current_user)])
async def get_metrics_history():
    """Returns chronological telemetry samples and summary statistics."""
    return {
        "history": metrics_manager.get_history(),
        "summary": metrics_manager.get_summary(),
    }


@router.post("/api/metrics/reset", dependencies=[Depends(get_current_user)])
async def reset_metrics():
    """Clears recorded telemetry buffer and peaks."""
    metrics_manager.reset()
    return {"status": "reset", "summary": metrics_manager.get_summary()}


@router.get("/api/server/properties", dependencies=[Depends(get_current_user)])
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

    _sync_property_aliases(props)
    return {"exists": True, "server_type": server_type, "properties": props}


@router.post("/api/server/properties", dependencies=[Depends(get_current_user)])
async def save_properties(new_props: Dict[str, str]):
    """Updates key-values in server.properties, keeping formatting/comments where possible."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    lines = []
    keys_written = set()

    to_save = dict(new_props)
    _sync_property_aliases(to_save)

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


@router.get("/api/server/properties/raw", dependencies=[Depends(get_current_user)])
async def get_raw_properties():
    """Reads full raw text of server.properties."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    if not prop_file.exists():
        return {"exists": False, "server_type": server_type, "content": ""}
    content = prop_file.read_text(encoding="utf-8", errors="replace")
    return {"exists": True, "server_type": server_type, "content": content}


@router.post("/api/server/properties/raw", dependencies=[Depends(get_current_user)])
async def save_raw_properties(req: RawPropertiesRequest):
    """Saves full raw text of server.properties with atomic write."""
    prop_file = settings.data_dir / "server.properties"
    server_type = settings.runtime_config.get("server_type", "paper")
    atomic_write_text(prop_file, req.content)
    return {"status": "success", "server_type": server_type}


@router.get("/api/java/runtimes", dependencies=[Depends(get_current_user)])
async def get_runtimes():
    return await asyncio.to_thread(JavaManager.detect_runtimes)


@router.post("/api/server/import", dependencies=[Depends(get_current_user)])
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

        with zipfile.ZipFile(temp_zip, "r") as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            file_manager._check_disk_quota(extra_bytes=total_uncompressed)

        try:
            await asyncio.to_thread(
                safe_extract_zip,
                temp_zip,
                settings.data_dir,
                lambda member: Path(member.filename).parts[0] in PROTECTED_INTERNAL_FILES if Path(member.filename).parts else False,
            )
            file_manager.invalidate_quota_cache()
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

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
            "server_version": detected_version,
        })

        return {
            "status": "success",
            "message": f"Servidor importado correctamente como '{detected_type}' ({detected_file})",
            "server_type": detected_type,
            "server_file": detected_file,
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

