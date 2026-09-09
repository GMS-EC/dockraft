import hmac
import hashlib
import time
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, Security, Request, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

security_bearer = HTTPBearer(auto_error=False)

class LoginRateLimiter:
    """
    In-memory rate limiter for login attempts per client IP.
    Enforces maximum consecutive failed attempts and cooldown period.
    """
    def __init__(self, max_attempts: int = 5, cooldown_seconds: int = 600):
        self.max_attempts = max_attempts
        self.cooldown_seconds = cooldown_seconds
        self.records: Dict[str, Dict[str, Any]] = {}
        self._cleanup_counter: int = 0

    def is_locked(self, ip: str) -> Tuple[bool, int]:
        now = time.time()
        # Periodic cleanup every 50 calls to avoid memory leak
        self._cleanup_counter += 1
        if self._cleanup_counter >= 50:
            self.cleanup_expired()
            self._cleanup_counter = 0

        record = self.records.get(ip)
        if not record:
            return False, 0
        
        lockout_until = record.get("lockout_until", 0)
        if now < lockout_until:
            remaining = int(lockout_until - now)
            return True, max(1, remaining)
        
        # If lockout period has expired, reset failures
        if lockout_until > 0 and now >= lockout_until:
            del self.records[ip]
            return False, 0

        # If attempts never triggered lockout but have gone stale (> cooldown_seconds), prune
        stale_threshold = max(self.cooldown_seconds, 900)
        if lockout_until == 0 and (now - record.get("last_attempt", 0)) > stale_threshold:
            del self.records[ip]
            return False, 0
        
        return False, 0

    def cleanup_expired(self) -> None:
        """Removes all records whose lockout has expired or whose attempts have gone stale, preventing memory leak."""
        now = time.time()
        stale_threshold = max(self.cooldown_seconds, 900)
        expired = [
            ip for ip, rec in self.records.items()
            if (rec.get("lockout_until", 0) > 0 and now >= rec["lockout_until"])
            or (rec.get("lockout_until", 0) == 0 and (now - rec.get("last_attempt", 0)) > stale_threshold)
        ]
        for ip in expired:
            del self.records[ip]

        # Safety cap: If records still exceed 2000 (e.g. massive distributed bot flood), drop oldest entries
        if len(self.records) > 2000:
            sorted_ips = sorted(self.records.items(), key=lambda item: item[1].get("last_attempt", 0))
            to_remove = len(self.records) - 1500
            for ip, _ in sorted_ips[:to_remove]:
                del self.records[ip]

    def record_failure(self, ip: str) -> Tuple[int, int]:
        now = time.time()
        # Periodic cleanup check
        self._cleanup_counter += 1
        if self._cleanup_counter >= 50:
            self.cleanup_expired()
            self._cleanup_counter = 0

        stale_threshold = max(self.cooldown_seconds, 900)
        record = self.records.setdefault(ip, {
            "attempts": 0,
            "lockout_until": 0,
            "last_attempt": now
        })

        # If previous lockout expired, reset
        if record["lockout_until"] > 0 and now >= record["lockout_until"]:
            record["attempts"] = 0
            record["lockout_until"] = 0
        elif record["lockout_until"] == 0 and (now - record.get("last_attempt", 0)) > stale_threshold:
            record["attempts"] = 0

        record["attempts"] += 1
        record["last_attempt"] = now

        if record["attempts"] >= self.max_attempts:
            record["lockout_until"] = now + self.cooldown_seconds
            return 0, self.cooldown_seconds

        remaining_attempts = max(0, self.max_attempts - record["attempts"])
        return remaining_attempts, 0

    def record_success(self, ip: str) -> None:
        if ip in self.records:
            del self.records[ip]

login_limiter = LoginRateLimiter(
    max_attempts=getattr(settings, "login_max_attempts", 5),
    cooldown_seconds=getattr(settings, "login_cooldown_seconds", 600)
)

def get_session_max_age() -> int:
    """
    Returns the session timeout in seconds based on runtime_config or settings.
    Default is 60 minutes (3600 seconds), minimum 60 seconds.
    """
    try:
        minutes = int(settings.runtime_config.get("session_timeout_minutes", getattr(settings, "session_timeout_minutes", 60)))
        if minutes < 1:
            minutes = 60
    except (ValueError, TypeError):
        minutes = 60
    return minutes * 60

def get_token_age(token: str) -> Optional[int]:
    """Returns the age in seconds of a given token, or None if invalid."""
    if not token or ":" not in token:
        return None
    try:
        timestamp_str, _ = token.split(":", 1)
        return int(time.time()) - int(timestamp_str)
    except Exception:
        return None

def create_session_token() -> str:
    """Generates an HMAC session token based on secret key and timestamp."""
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.secret_key.encode(),
        timestamp.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{timestamp}:{signature}"

def verify_session_token(token: str, max_age_seconds: Optional[int] = None) -> bool:
    """Verifies the authenticity and expiration of the session token."""
    if not token or ":" not in token:
        return False
    if max_age_seconds is None:
        max_age_seconds = get_session_max_age()
    try:
        timestamp_str, signature = token.split(":", 1)
        token_time = int(timestamp_str)
        if time.time() - token_time > max_age_seconds:
            return False
        expected_sig = hmac.new(
            settings.secret_key.encode(),
            timestamp_str.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_sig)
    except Exception:
        return False

def verify_admin_credentials(username: Optional[str], password: str) -> bool:
    """Validates provided username and password using constant-time comparison."""
    if not settings.admin_password:
        return True
    
    # Check username if configured
    expected_user = getattr(settings, "admin_user", "admin")
    if expected_user:
        input_user = (username or "").strip()
        if not hmac.compare_digest(input_user.encode(), expected_user.encode()):
            return False

    return hmac.compare_digest((password or "").encode(), settings.admin_password.encode())

def verify_admin_password(password: str) -> bool:
    """Validates provided password against settings.admin_password (compatibility alias)."""
    return verify_admin_credentials(getattr(settings, "admin_user", "admin"), password)

async def get_current_user(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    token_param: Optional[str] = Query(None, alias="token")
) -> bool:
    """
    Dependency that authenticates requests.
    If no admin_password is configured in settings, access is open.
    Otherwise checks Authorization header, cookie 'dockraft_token' (or legacy 'litemc_token'), or '?token=' query param.
    """
    if not settings.admin_password:
        return True

    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif token_param:
        token = token_param
    elif "dockraft_token" in request.cookies:
        token = request.cookies.get("dockraft_token")
    elif "dockraft_session" in request.cookies:
        token = request.cookies.get("dockraft_session")
    elif "litemc_token" in request.cookies:
        token = request.cookies.get("litemc_token")

    if not token or not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

def is_authenticated(request: Request) -> bool:
    """
    Checks if a request has a valid session token without raising an exception.
    Useful for page route redirects (e.g. GET / and GET /login).
    """
    if not settings.admin_password:
        return True

    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "dockraft_token" in request.cookies:
        token = request.cookies.get("dockraft_token")
    elif "dockraft_session" in request.cookies:
        token = request.cookies.get("dockraft_session")
    elif "litemc_token" in request.cookies:
        token = request.cookies.get("litemc_token")
    elif "token" in request.query_params:
        token = request.query_params.get("token")

    return bool(token and verify_session_token(token))
