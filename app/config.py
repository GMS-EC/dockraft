import os
import sys
import re
import json
import secrets
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("dockraft")

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS).resolve()
else:
    BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_instance_dir() -> Path:
    """Resolves the active server instance directory (data, backups, state, .env)."""
    env_inst = os.getenv("DOCKRAFT_INSTANCE_DIR", "").strip()
    if env_inst:
        return Path(env_inst).expanduser().resolve()
    appimage_path = os.getenv("APPIMAGE", "").strip()
    if appimage_path:
        app_dir = Path(appimage_path).expanduser().resolve().parent
        if (app_dir / ".portable").exists() or (app_dir / ".env").exists():
            return app_dir
        return (Path.home() / "Dockraft" / "instancias" / "default").resolve()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / ".portable").exists() or (exe_dir / ".env").exists():
            return exe_dir
        return (Path.home() / "Dockraft" / "instancias" / "default").resolve()
    return BASE_DIR


def _load_env_file(env_path: Path) -> None:
    """Loads KEY=VALUE pairs from an instance .env file without overriding process env vars."""
    if not env_path.is_file():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                val = val[1:-1]
            if key:
                os.environ.setdefault(key, val)
    except Exception as e:
        logger.warning("[Dockraft] Could not read .env file %s: %s", env_path, e)


INSTANCE_DIR = _resolve_instance_dir()
_load_env_file(INSTANCE_DIR / ".env")
DEFAULT_DATA_DIR = INSTANCE_DIR / "data"
if INSTANCE_DIR.parent.name.lower() == "instancias":
    DEFAULT_BACKUPS_DIR = INSTANCE_DIR.parent.parent / "backups" / f"backup-{INSTANCE_DIR.name}"
else:
    DEFAULT_BACKUPS_DIR = INSTANCE_DIR / "backups"

def _read_version_from_changelog() -> str:
    """Reads the latest version from CHANGELOG.md by finding the first ## [X.Y.Z] header."""
    env_ver = os.getenv("DOCKRAFT_VERSION") or os.getenv("APP_VERSION")
    if env_ver:
        return env_ver.strip().lstrip("v")

    candidate_paths = [
        BASE_DIR / "CHANGELOG.md",
        Path("/app/CHANGELOG.md"),
        Path.cwd() / "CHANGELOG.md",
        Path(__file__).resolve().parent.parent / "CHANGELOG.md",
    ]

    for changelog in candidate_paths:
        try:
            if changelog.is_file():
                with open(changelog, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r'^##\s+\[(\d+\.\d+\.\d+(?:-[A-Za-z0-9\.\-]+)?)\]', line.strip())
                        if m:
                            return m.group(1)
        except Exception:
            pass

    return "1.6.0"

APP_VERSION = _read_version_from_changelog()

class Settings:
    def __init__(self):
        inst_dir = _resolve_instance_dir()
        def_data_dir = inst_dir / "data"
        if inst_dir.parent.name.lower() == "instancias":
            def_backups_dir = inst_dir.parent.parent / "backups" / f"backup-{inst_dir.name}"
        else:
            def_backups_dir = inst_dir / "backups"
        self.instance_dir: Path = inst_dir
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.data_dir: Path = Path(os.getenv("DATA_DIR", str(def_data_dir))).resolve()
        self.backups_dir: Path = Path(os.getenv("BACKUPS_DIR", str(def_backups_dir))).resolve()
        self.admin_user: str = os.getenv("ADMIN_USER", os.getenv("ADMIN_USERNAME", "admin"))
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "").strip()
        if not self.admin_password and "pytest" not in sys.modules:
            self.admin_password = secrets.token_urlsafe(18)
            logger.warning(
                "[Dockraft] ADMIN_PASSWORD is not set! Generated an ephemeral password for user '%s': %s "
                "(set ADMIN_PASSWORD in your environment to configure a fixed password)",
                self.admin_user,
                self.admin_password,
            )

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        default_state_dir = inst_dir / ".dockraft_state"
        self.panel_state_dir: Path = Path(os.getenv("DOCKRAFT_STATE_DIR", str(default_state_dir))).resolve()
        self.panel_state_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(self.panel_state_dir, 0o700)
            except OSError:
                pass

        self.config_file: Path = self.data_dir / "dockraft_config.json"
        self._legacy_config_file: Path = self.data_dir / "litemc_config.json"
        self._secret_key_file: Path = self.panel_state_dir / ".secret_key"
        self._legacy_secret_key_file: Path = self.data_dir / ".secret_key"

        _provided_key = os.getenv("SECRET_KEY", "").strip()
        if _provided_key:
            self.secret_key: str = _provided_key
        else:
            self.secret_key = self._load_or_create_secret_key()

        self.login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.login_cooldown_seconds: int = int(os.getenv("LOGIN_COOLDOWN_SECONDS", "600"))
        self.session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
        # Fix #1: Set to true when the panel is behind an HTTPS reverse proxy
        # so session cookies are marked Secure and never sent over plain HTTP.
        self.https_enabled: bool = os.getenv("HTTPS_ENABLED", "false").lower() in ("true", "1", "yes")
        self.trust_proxy_headers: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")
        _raw_proxies = os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1")
        self.trusted_proxies: list[str] = [p.strip() for p in _raw_proxies.split(",") if p.strip()]
        self._revoked_tokens_file: Path = self.panel_state_dir / ".revoked_tokens.json"
        
        # Default runtime config
        self.runtime_config: Dict[str, Any] = {
            "server_name": os.getenv("SERVER_NAME", "Mi Servidor Dockraft"),
            "server_type": "paper", # paper, purpur, vanilla, fabric, bedrock, custom
            "server_version": "1.21.4",
            "server_file": "server.jar",
            "java_path": "java",
            "min_ram": "1G",
            "max_ram": "2G",
            "aikar_flags": True,
            "custom_jvm_flags": "",
            "eula_accepted": True,
            "auto_restart": False,
            "disk_limit_gb": 10.0,
            "cpu_cores": 2,
            "auto_backup": False,
            "backup_interval_hours": 24,
            "backup_max_count": 5,
            "backup_scope": "full",
            "backup_targets": [],
            "backup_compression": True,
            "backup_stop_server": False,
            "backup_pre_command": "save-all",
            "autostart_server": False,
            "crash_detection": True,
            "session_timeout_minutes": self.session_timeout_minutes
        }
        self.load_runtime_config()

    def _load_or_create_secret_key(self) -> str:
        """Loads a persisted auto-generated SECRET_KEY from panel_state_dir/.secret_key, or creates one."""
        try:
            if self._secret_key_file.is_file():
                if os.name != "nt":
                    try:
                        os.chmod(self._secret_key_file, 0o600)
                    except OSError:
                        pass
                persisted = self._secret_key_file.read_text(encoding="utf-8").strip()
                if len(persisted) >= 32:
                    return persisted
        except Exception:
            pass

        # Migrate legacy secret key out of data_dir if present
        legacy_file = getattr(self, "_legacy_secret_key_file", None)
        if legacy_file and legacy_file.is_file():
            try:
                persisted = legacy_file.read_text(encoding="utf-8").strip()
                if len(persisted) >= 32:
                    if "pytest" not in sys.modules:
                        from app.core.fs_utils import atomic_write_text
                        atomic_write_text(self._secret_key_file, persisted, mode=0o600)
                        try:
                            legacy_file.unlink()
                        except OSError:
                            pass
                    return persisted
            except Exception:
                pass

        generated = secrets.token_hex(32)
        if "pytest" not in sys.modules:
            try:
                from app.core.fs_utils import atomic_write_text
                atomic_write_text(self._secret_key_file, generated, mode=0o600)
            except Exception:
                pass
        return generated

    def load_runtime_config(self) -> None:
        target = self.config_file if self.config_file.exists() else (self._legacy_config_file if self._legacy_config_file.exists() else None)
        if target and target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.runtime_config.update(saved)
            except Exception as e:
                logger.error("[Dockraft] Error loading config: %s", e)

    def save_runtime_config(self, new_config: Dict[str, Any]) -> None:
        self.runtime_config.update(new_config)
        from app.core.fs_utils import atomic_write_json
        atomic_write_json(self.config_file, self.runtime_config, indent=2)

settings = Settings()
