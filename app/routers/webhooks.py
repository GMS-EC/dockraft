from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.webhook_manager import webhook_manager

router = APIRouter(tags=["webhooks"])


class WebhookConfigRequest(BaseModel):
    discord: Optional[Dict[str, Any]] = None
    telegram: Optional[Dict[str, Any]] = None
    email: Optional[Dict[str, Any]] = None
    events: Optional[Dict[str, Any]] = None


@router.get("/api/webhooks/config", dependencies=[Depends(get_current_user)])
async def get_webhooks_config():
    return webhook_manager.get_sanitized_config()


@router.post("/api/webhooks/config", dependencies=[Depends(get_current_user)])
async def save_webhooks_config(req: WebhookConfigRequest):
    saved = webhook_manager.save_config(req.model_dump(exclude_unset=True))
    return {"status": "saved", "config": saved}


@router.post("/api/webhooks/test/{channel}", dependencies=[Depends(get_current_user)])
async def test_webhook_channel(channel: str):
    res = await webhook_manager.test_channel(channel.lower())
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Error enviando notificación de prueba"))
    return res

