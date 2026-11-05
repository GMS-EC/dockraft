from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.player_manager import player_manager

router = APIRouter(tags=["players"])


class PlayerActionRequest(BaseModel):
    player: str
    reason: Optional[str] = ""


class KickAllRequest(BaseModel):
    reason: Optional[str] = "Mantenimiento del servidor"


@router.get("/api/players/list", dependencies=[Depends(get_current_user)])
async def get_players_list():
    """Returns unified player directory, active connections, and ban list."""
    return player_manager.get_all_data()


@router.post("/api/players/kick", dependencies=[Depends(get_current_user)])
async def kick_player(req: PlayerActionRequest):
    return await player_manager.kick_player(req.player, req.reason or "")


@router.post("/api/players/kick-all", dependencies=[Depends(get_current_user)])
async def kick_all_players(req: KickAllRequest = KickAllRequest()):
    return await player_manager.kick_all_players(req.reason or "Mantenimiento del servidor")


@router.post("/api/players/ban", dependencies=[Depends(get_current_user)])
async def ban_player(req: PlayerActionRequest):
    return await player_manager.ban_player(req.player, req.reason or "")


@router.post("/api/players/pardon", dependencies=[Depends(get_current_user)])
async def pardon_player(req: PlayerActionRequest):
    return await player_manager.pardon_player(req.player)


@router.post("/api/players/op", dependencies=[Depends(get_current_user)])
async def op_player(req: PlayerActionRequest):
    return await player_manager.set_op(req.player, True)


@router.post("/api/players/deop", dependencies=[Depends(get_current_user)])
async def deop_player(req: PlayerActionRequest):
    return await player_manager.set_op(req.player, False)


@router.post("/api/players/add", dependencies=[Depends(get_current_user)])
async def add_player(req: PlayerActionRequest):
    return player_manager.add_player(req.player)

