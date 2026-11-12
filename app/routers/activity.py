from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response

from app.core.security import get_current_user
from app.core.activity_manager import activity_manager

router = APIRouter(tags=["activity"])


@router.get("/api/activity/logs", dependencies=[Depends(get_current_user)])
async def get_activity_logs(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Returns filtered and paginated activity logs and category counts."""
    return activity_manager.get_logs(category=category, search=search, limit=limit, offset=offset)


@router.post("/api/activity/clear", dependencies=[Depends(get_current_user)])
async def clear_activity_logs():
    """Clears all logged activities."""
    activity_manager.clear_logs()
    activity_manager.log(
        "security",
        "Historial de registros vaciado",
        "El administrador vació el registro de actividad",
        user="admin",
        status="warning",
    )
    return {"status": "success", "message": "Registros de actividad vaciados correctamente"}


@router.get("/api/activity/export", dependencies=[Depends(get_current_user)])
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
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

