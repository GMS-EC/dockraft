from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.core.security import (
    create_session_token,
    verify_admin_credentials,
    get_current_user,
    login_limiter,
    get_session_max_age,
    revoke_token,
    get_token_from_request,
    get_all_tokens_from_request,
    get_client_ip,
)
from app.core.activity_manager import activity_manager

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: Optional[str] = "admin"
    password: str


def set_session_cookies(response: Response, token: str, max_age: int) -> None:
    """Sets both current and legacy session cookies with consistent security flags."""
    _secure = settings.https_enabled
    for cookie_name in ("dockraft_token", "litemc_token"):
        response.set_cookie(
            key=cookie_name,
            value=token,
            httponly=True,
            secure=_secure,
            max_age=max_age,
            samesite="lax",
        )


def clear_session_cookies(response: Response) -> None:
    """Deletes all session cookies with consistent security flags."""
    _secure = settings.https_enabled
    for cookie_name in ("dockraft_token", "dockraft_session", "litemc_token"):
        response.delete_cookie(
            key=cookie_name,
            httponly=True,
            secure=_secure,
            samesite="lax",
        )


@router.get("/api/auth/status")
async def auth_status(user: bool = Depends(get_current_user)):
    max_age = get_session_max_age()
    return {
        "auth_required": bool(settings.admin_password),
        "authenticated": True,
        "admin_user": getattr(settings, "admin_user", "admin"),
        "session_timeout_minutes": max_age // 60,
    }


@router.post("/api/auth/refresh")
async def auth_refresh(request: Request, response: Response, user: bool = Depends(get_current_user)):
    """Refreshes the active session token, revoking the previous token(s)."""
    for tok in get_all_tokens_from_request(request):
        revoke_token(tok)
    new_token = create_session_token()
    max_age = get_session_max_age()
    set_session_cookies(response, new_token, max_age)
    return {
        "status": "success",
        "token": new_token,
        "session_timeout_minutes": max_age // 60,
    }


@router.post("/api/auth/login")
async def auth_login(req: LoginRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    max_age = get_session_max_age()

    # 1. Rate limiting check: check if this IP is currently locked out
    is_locked, remaining = login_limiter.is_locked(client_ip)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Acceso bloqueado temporalmente. Reintente en {remaining} segundos.",
            headers={"Retry-After": str(remaining)},
        )

    # 2. Verify admin credentials (username + password; fail-closed if admin_password is empty)
    if verify_admin_credentials(req.username, req.password):
        login_limiter.record_success(client_ip)
        token = create_session_token()
        set_session_cookies(response, token, max_age)
        try:
            activity_manager.log(
                "security",
                "Inicio de sesión exitoso",
                f"Usuario '{req.username or 'admin'}' conectado (IP: {client_ip})",
                user=req.username or "admin",
                status="success",
            )
        except Exception:
            pass
        return {"status": "success", "session_timeout_minutes": max_age // 60}

    # 4. Record failed attempt and check if threshold reached
    remaining_attempts, cooldown = login_limiter.record_failure(client_ip)
    if cooldown > 0:
        try:
            activity_manager.log(
                "security",
                "Bloqueo por fuerza bruta",
                f"5 intentos fallidos superados (IP: {client_ip})",
                user="desconocido",
                status="error",
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Ha alcanzado el límite de 5 intentos fallidos. Acceso bloqueado durante 10 minutos ({cooldown}s).",
            headers={"Retry-After": str(cooldown)},
        )

    try:
        activity_manager.log(
            "security",
            "Intento de inicio fallido",
            f"Credenciales inválidas para '{req.username or 'admin'}' (IP: {client_ip})",
            user=req.username or "desconocido",
            status="warning",
        )
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Credenciales inválidas. Intentos restantes antes del bloqueo: {remaining_attempts}",
    )


@router.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    for tok in get_all_tokens_from_request(request):
        revoke_token(tok)
    clear_session_cookies(response)
    try:
        activity_manager.log("security", "Cierre de sesión", "Sesión cerrada por el usuario", user="admin", status="info")
    except Exception:
        pass
    return {"status": "success", "message": "Sesión cerrada"}


@router.get("/logout")
async def logout_page(request: Request):
    for tok in get_all_tokens_from_request(request):
        revoke_token(tok)
    redirect_resp = RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    clear_session_cookies(redirect_resp)
    return redirect_resp

