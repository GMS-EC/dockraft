import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional
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
logger = logging.getLogger("dockraft.backups.router")


class BackupCreateRequest(BaseModel):
    tag: Optional[str] = "manual"
    scope: Optional[str] = "full"
    targets: Optional[List[str]] = None
    compression: Optional[bool] = None
    stop_server: Optional[bool] = None
    pre_command: Optional[str] = None
    post_command: Optional[str] = None
    background: bool = False


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
    backup_pre_command: Optional[str] = ""


class BackupPolicyRequest(BaseModel):
    id: Optional[str] = None
    name: str
    scope: Optional[str] = "full"
    targets: Optional[List[str]] = None
    compression: Optional[bool] = True
    stop_server: Optional[bool] = False
    pre_command: Optional[str] = ""
    post_command: Optional[str] = ""
    backup_max_count: Optional[int] = None


@router.get("/api/backups/list", dependencies=[Depends(get_current_user)])
async def get_backups():
    return await asyncio.to_thread(backup_manager.list_backups)


@router.get("/api/backups/targets", dependencies=[Depends(get_current_user)])
async def get_backup_targets():
    return await asyncio.to_thread(backup_manager.get_available_targets)


def _validate_backup_preconditions() -> None:
    try:
        from app.core.downloader import downloader
        if downloader.progress.get("is_downloading"):
            raise HTTPException(
                status_code=409,
                detail="No se puede crear un respaldo mientras se está instalando o descargando el servidor."
            )
    except HTTPException:
        raise
    except Exception:
        pass

    if not backup_manager.has_server_data():
        raise HTTPException(
            status_code=400,
            detail="No hay ningún servidor instalado ni datos de Minecraft para respaldar."
        )


async def _execute_backup_pipeline(req: BackupCreateRequest, job_id: str) -> Dict[str, Any]:
    cfg = settings.runtime_config
    compression = req.compression if req.compression is not None else cfg.get("backup_compression", True)
    stop_server = req.stop_server if req.stop_server is not None else cfg.get("backup_stop_server", False)
    pre_cmd = req.pre_command if req.pre_command is not None else cfg.get("backup_pre_command", "")
    post_cmd = req.post_command if req.post_command is not None else cfg.get("backup_post_command", "")

    was_running = process_manager.get_status() != "OFFLINE"
    result: Optional[Dict[str, Any]] = None
    failed = False

    try:
        if was_running:
            backup_manager.update_job(job_id, stage="saving")
            await process_manager.send_command("save-all")
            extra_cmd = (pre_cmd or "").strip()
            if extra_cmd and extra_cmd.lower() != "save-all":
                await process_manager.send_command(extra_cmd)
            await asyncio.sleep(2)

        if was_running and stop_server:
            backup_manager.update_job(job_id, stage="stopping")
            await process_manager.stop_server()
            for _ in range(25):
                await asyncio.sleep(1)
                if process_manager.get_status() == "OFFLINE":
                    break
            if process_manager.get_status() != "OFFLINE":
                await process_manager.kill_server()
                await asyncio.sleep(1)

        try:
            backup_manager.update_job(job_id, stage="compressing")
            res = await asyncio.to_thread(
                backup_manager.create_backup,
                tag=req.tag or "manual",
                scope=req.scope or "full",
                targets=req.targets,
                compression=compression
            )
            if res.get("status") == "success":
                backup_manager.update_job(job_id, stage="pruning")
                max_count = int(cfg.get("backup_max_count", 5) or 5)
                await asyncio.to_thread(backup_manager.prune_backups, max_count=max_count)
                try:
                    activity_manager.log(
                        "backup",
                        "Copia creada",
                        f"Archivo: {res.get('filename')} | Tamaño: {res.get('size_formatted', 'N/A')}",
                        user="admin",
                        status="success"
                    )
                except Exception:
                    pass
            result = res
        finally:
            if was_running and stop_server:
                backup_manager.update_job(job_id, stage="restarting")
                await asyncio.sleep(1)
                await process_manager.start_server()
            post_text = (post_cmd or "").strip()
            if post_text and process_manager.get_status() != "OFFLINE":
                try:
                    await process_manager.send_command(post_text)
                except Exception:
                    pass
    except HTTPException as exc:
        failed = True
        backup_manager.update_job(
            job_id,
            is_running=False,
            status="error",
            stage="error",
            error=str(exc.detail or "Error al crear la copia de seguridad"),
        )
        raise
    except Exception as exc:
        failed = True
        backup_manager.update_job(
            job_id,
            is_running=False,
            status="error",
            stage="error",
            error=str(exc),
        )
        raise
    finally:
        if result is not None and not failed:
            backup_manager.update_job(
                job_id,
                is_running=False,
                status="completed",
                stage="completed",
                filename=result.get("filename"),
                size_formatted=result.get("size_formatted"),
                size_bytes=result.get("size_bytes", 0),
                origin=result.get("origin"),
                is_auto=result.get("is_auto"),
                scope=result.get("scope"),
                scope_label=result.get("scope_label"),
                created_at=result.get("created_at"),
                error=None,
            )

    assert result is not None
    return result


async def _run_background_backup(req: BackupCreateRequest, job_id: str) -> None:
    try:
        await _execute_backup_pipeline(req, job_id)
    except Exception as exc:
        logger.warning("Background backup job '%s' failed: %s", job_id, exc)


@router.get("/api/backups/status", dependencies=[Depends(get_current_user)])
async def get_backup_status():
    return backup_manager.progress


@router.post("/api/backups/create", dependencies=[Depends(get_current_user)])
async def create_backup(req: BackupCreateRequest):
    _validate_backup_preconditions()
    job_id = uuid.uuid4().hex[:12]
    if not backup_manager.try_start_job(job_id, stage="preparing"):
        raise HTTPException(
            status_code=409,
            detail="Ya hay una copia de seguridad en progreso. Espera a que finalice."
        )

    if req.background:
        asyncio.create_task(_run_background_backup(req, job_id))
        return {
            "status": "started",
            "job_id": job_id,
            "progress": backup_manager.progress,
        }

    return await _execute_backup_pipeline(req, job_id)


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
    res = await asyncio.to_thread(backup_manager.delete_backup, filename)
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
        "backup_pre_command": "" if (cfg.get("backup_pre_command") or "").strip().lower() == "save-all" else (cfg.get("backup_pre_command") or "")
    }


@router.post("/api/backups/config", dependencies=[Depends(get_current_user)])
async def save_backup_config(req: BackupConfigRequest):
    update_data = {
        "backup_max_count": req.backup_max_count,
        "backup_scope": req.backup_scope or "full",
        "backup_targets": req.backup_targets if req.backup_targets is not None else [],
        "backup_compression": req.backup_compression if req.backup_compression is not None else True,
        "backup_stop_server": req.backup_stop_server if req.backup_stop_server is not None else False,
        "backup_pre_command": req.backup_pre_command.strip() if req.backup_pre_command is not None else ""
    }
    if req.auto_backup is not None:
        update_data["auto_backup"] = req.auto_backup
    if req.backup_interval_hours is not None:
        update_data["backup_interval_hours"] = req.backup_interval_hours
    settings.save_runtime_config(update_data)
    if req.backup_max_count and req.backup_max_count > 0:
        backup_manager.prune_backups(max_count=int(req.backup_max_count))
    if req.auto_backup is not None or req.backup_interval_hours is not None:
        task_scheduler.sync_auto_backup_task(
            enabled=bool(settings.runtime_config.get("auto_backup", False)),
            interval_hours=int(settings.runtime_config.get("backup_interval_hours", 24) or 24)
        )
    return {"status": "saved", "config": settings.runtime_config}


@router.get("/api/backups/policies", dependencies=[Depends(get_current_user)])
async def list_backup_policies():
    cfg = settings.runtime_config
    return {
        "max_count": int(cfg.get("backup_max_count", 5) or 5),
        "policies": backup_manager.get_policies(),
    }


@router.post("/api/backups/policies", dependencies=[Depends(get_current_user)])
async def save_backup_policy(req: BackupPolicyRequest):
    if req.backup_max_count is not None and req.backup_max_count > 0:
        settings.save_runtime_config({"backup_max_count": int(req.backup_max_count)})
        backup_manager.prune_backups(max_count=int(req.backup_max_count))

    saved = backup_manager.save_policy({
        "id": req.id,
        "name": req.name,
        "scope": req.scope or "full",
        "targets": req.targets if req.targets is not None else [],
        "compression": req.compression if req.compression is not None else True,
        "stop_server": req.stop_server if req.stop_server is not None else False,
        "pre_command": req.pre_command or "",
        "post_command": req.post_command or "",
    })
    return {
        "status": "saved",
        "policy": saved,
        "policies": backup_manager.get_policies(),
        "max_count": int(settings.runtime_config.get("backup_max_count", 5) or 5),
    }


@router.delete("/api/backups/policies/{policy_id}", dependencies=[Depends(get_current_user)])
async def delete_backup_policy(policy_id: str):
    remaining = backup_manager.delete_policy(policy_id)
    return {
        "status": "deleted",
        "policies": remaining,
    }

