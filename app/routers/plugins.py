from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.diagnostic_manager import diagnostic_manager
from app.core.plugin_manager import plugin_manager

router = APIRouter(tags=["diagnostics_plugins"])


class ShareLogRequest(BaseModel):
    content: Optional[str] = None


@router.get("/api/diagnostics/analyze", dependencies=[Depends(get_current_user)])
async def analyze_diagnostics():
    """Analyzes logs and crash-reports to identify issues and actionable solutions."""
    return diagnostic_manager.analyze_diagnostics()


@router.post("/api/diagnostics/share", dependencies=[Depends(get_current_user)])
async def share_log(req: Optional[ShareLogRequest] = None):
    """Uploads sanitized logs to mclo.gs and returns a clean shareable URL."""
    custom_content = req.content if req else None
    res = await diagnostic_manager.share_to_mclogs(custom_content)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Error al compartir log en mclo.gs"))
    return res


@router.get("/api/plugins/list", dependencies=[Depends(get_current_user)])
async def list_installed_plugins():
    """Returns all installed plugins detected in data/plugins/*.jar."""
    plugins = plugin_manager.scan_installed_plugins()
    return {"status": "success", "plugins": plugins, "count": len(plugins)}


@router.post("/api/plugins/check-updates", dependencies=[Depends(get_current_user)])
async def check_plugin_updates():
    """Queries Spiget API to check for available updates of installed plugins."""
    results = await plugin_manager.check_plugin_updates()
    outdated = [p for p in results if p.get("has_update")]
    return {"status": "success", "plugins": results, "total": len(results), "outdated_count": len(outdated)}


@router.get("/api/plugins/console-updates", dependencies=[Depends(get_current_user)])
async def get_console_plugin_updates():
    """Returns all plugin update notices detected from console logs,
    resolving official download links for any notice announced without one."""
    updates = await plugin_manager.enrich_update_urls(plugin_manager.get_detected_updates())
    return {"status": "success", "updates": updates, "count": len(updates)}


@router.post("/api/plugins/scan-console", dependencies=[Depends(get_current_user)])
async def scan_console_plugin_updates():
    """Scans data/logs/latest.log and returns detected plugin updates."""
    updates = await plugin_manager.enrich_update_urls(plugin_manager.scan_console_logs())
    return {"status": "success", "updates": updates, "count": len(updates)}


@router.post("/api/plugins/notify-updates", dependencies=[Depends(get_current_user)])
async def notify_plugin_updates():
    """Checks for plugin updates and broadcasts a webhook notification if any are outdated."""
    return await plugin_manager.check_and_notify_updates()


@router.delete("/api/plugins/console-updates/{plugin_name}", dependencies=[Depends(get_current_user)])
async def dismiss_console_plugin_update(plugin_name: str):
    """Dismisses/removes a specific plugin update notice."""
    removed = plugin_manager.dismiss_update(plugin_name)
    return {"status": "success", "removed": removed, "plugin": plugin_name}


@router.delete("/api/plugins/console-updates", dependencies=[Depends(get_current_user)])
async def clear_all_console_plugin_updates():
    """Dismisses/clears all detected plugin update notices."""
    count = plugin_manager.clear_detected_updates()
    return {"status": "success", "cleared_count": count}

