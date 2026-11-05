import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.core.security import get_current_user
from app.core.process_manager import process_manager
from app.core.backup_manager import backup_manager
from app.core.file_manager import file_manager
from app.core.task_scheduler import task_scheduler
from app.core.activity_manager import activity_manager

router = APIRouter(tags=["backups"])


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


@router.get("/api/backups/list", dependencies=[Depends(get_current_user)])
async def get_backups():
    return backup_manager.list_backups()


@router.get("/api/backups/targets", dependencies=[Depends(get_current_user)])
async def get_backup_targets():
    return backup_manager.get_available_targets()


@router.post("/api/backups/create", dependencies=[Depends(get_current_user)])
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
        res = await asyncio.to_thread(
            backup_manager.create_backup,
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


@router.post("/api/backups/restore", dependencies=[Depends(get_current_user)])
async def restore_backup(req: BackupRestoreRequest):
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de restaurar una copia de seguridad")
    res = await asyncio.to_thread(backup_manager.restore_backup, req.filename)
    file_manager.invalidate_quota_cache()
    if res.get("status") == "success":
        try:
            activity_manager.log("backup", "Copia restaurada", f"Restaurada copia '{req.filename}'", user="admin", status="warning")
        except Exception:
            pass
    return res


@router.delete("/api/backups/{filename}", dependencies=[Depends(get_current_user)])
async def delete_backup(filename: str):
    res = backup_manager.delete_backup(filename)
    if res.get("status") == "success":
        try:
            activity_manager.log("backup", "Copia eliminada", f"Eliminada copia '{filename}'", user="admin", status="info")
        except Exception:
            pass
    return res


@router.get("/api/backups/download/{filename}", dependencies=[Depends(get_current_user)])
async def download_backup(filename: str):
    target_path = backup_manager.get_backup_path(filename)
    return FileResponse(
        str(target_path),
        filename=target_path.name,
        media_type="application/zip"
    )


@router.get("/api/backups/config", dependencies=[Depends(get_current_user)])
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


@router.post("/api/backups/config", dependencies=[Depends(get_current_user)])
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
    if req.auto_backup is not None or req.backup_interval_hours is not None:
        task_scheduler.sync_auto_backup_task(
            enabled=bool(settings.runtime_config.get("auto_backup", False)),
            interval_hours=int(settings.runtime_config.get("backup_interval_hours", 24) or 24)
        )
    return {"status": "saved", "config": settings.runtime_config}

