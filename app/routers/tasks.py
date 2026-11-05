from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.task_scheduler import task_scheduler

router = APIRouter(tags=["tasks"])


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


@router.get("/api/tasks", dependencies=[Depends(get_current_user)])
async def list_tasks():
    return task_scheduler.list_tasks()


@router.post("/api/tasks", dependencies=[Depends(get_current_user)])
async def create_task(req: TaskCreateRequest):
    return task_scheduler.create_task(req.model_dump())


@router.get("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def get_task(task_id: str):
    t = task_scheduler.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t


@router.put("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def update_task(task_id: str, req: TaskUpdateRequest):
    t = task_scheduler.update_task(task_id, req.model_dump(exclude_unset=True))
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t


@router.delete("/api/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def delete_task(task_id: str):
    success = task_scheduler.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return {"status": "deleted", "id": task_id}


@router.post("/api/tasks/{task_id}/toggle", dependencies=[Depends(get_current_user)])
async def toggle_task(task_id: str, req: Optional[TaskToggleRequest] = None):
    enabled = req.enabled if req else None
    t = task_scheduler.toggle_task(task_id, enabled)
    if not t:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return t


@router.post("/api/tasks/{task_id}/run", dependencies=[Depends(get_current_user)])
async def run_task(task_id: str):
    try:
        return await task_scheduler.run_task_now(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando tarea: {str(e)}")

