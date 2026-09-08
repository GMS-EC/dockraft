import os
import json
import secrets
from pathlib import Path
from typing import Optional, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_BACKUPS_DIR = BASE_DIR / "backups"

class Settings:
    def __init__(self):
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.data_dir: Path = Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()
        self.backups_dir: Path = Path(os.getenv("BACKUPS_DIR", str(DEFAULT_BACKUPS_DIR))).resolve()
        self.admin_user: str = os.getenv("ADMIN_USER", os.getenv("ADMIN_USERNAME", "admin"))
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "")
        _provided_key = os.getenv("SECRET_KEY", "")
        if _provided_key:
            self.secret_key: str = _provided_key
        else:
            self.secret_key = secrets.token_hex(32)
            print(
                "[Dockraft] WARNING: SECRET_KEY no configurado. Se usó una clave aleatoria temporal.\n"
                "           Los tokens de sesión se invalidarán en cada reinicio.\n"
                "           Establece SECRET_KEY en tu .env para sesión persistente."
            )
        self.login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
        self.login_cooldown_seconds: int = int(os.getenv("LOGIN_COOLDOWN_SECONDS", "600"))
        self.session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.config_file: Path = self.data_dir / "dockraft_config.json"
        self._legacy_config_file: Path = self.data_dir / "litemc_config.json"
        
        # Default runtime config
        self.runtime_config: Dict[str, Any] = {
            "server_name": "Mi Servidor Dockraft",
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

    def load_runtime_config(self) -> None:
        target = self.config_file if self.config_file.exists() else (self._legacy_config_file if self._legacy_config_file.exists() else None)
        if target and target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.runtime_config.update(saved)
            except Exception as e:
                print(f"[Dockraft] Error loading config: {e}")

    def save_runtime_config(self, new_config: Dict[str, Any]) -> None:
        self.runtime_config.update(new_config)
        from app.core.fs_utils import atomic_write_json
        atomic_write_json(self.config_file, self.runtime_config, indent=2)

settings = Settings()
