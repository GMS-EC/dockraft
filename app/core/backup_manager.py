import os
import time
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from app.config import settings

class BackupManager:
    def __init__(self):
        self.backups_dir: Path = settings.backups_dir
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        # Migrate any legacy backups from settings.data_dir / "backups" if present
        legacy_dir = settings.data_dir / "backups"
        if legacy_dir.resolve() != self.backups_dir.resolve() and legacy_dir.exists():
            for item in legacy_dir.iterdir():
                if item.is_file() and item.name.endswith(".zip"):
                    target_dst = self.backups_dir / item.name
                    if not target_dst.exists():
                        try:
                            shutil.move(str(item), str(target_dst))
                        except Exception:
                            pass

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024 * 1024:
            return f"{round(size_bytes / 1024, 1)} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{round(size_bytes / (1024 * 1024), 1)} MB"
        else:
            return f"{round(size_bytes / (1024 * 1024 * 1024), 2)} GB"

    def get_available_targets(self) -> List[Dict[str, Any]]:
        """Returns top-level directories and important files in settings.data_dir."""
        targets = []
        excluded = {"backups", ".git", ".idea", "__pycache__"}
        if not settings.data_dir.exists():
            return targets

        try:
            for item in sorted(settings.data_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name in excluded or item.name.endswith(".tmp") or item.name.endswith(".pid"):
                    continue

                sz = 0
                if item.is_file():
                    try:
                        sz = item.stat().st_size
                    except Exception:
                        pass
                elif item.is_dir():
                    try:
                        for r, _, fs in os.walk(item):
                            for f in fs:
                                fp = os.path.join(r, f)
                                try:
                                    sz += os.path.getsize(fp)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                is_world = item.name.lower().startswith("world") or item.name.lower() == "worlds"
                is_plugin = item.name.lower() in ["plugins", "mods"]
                is_config = item.name.lower() in ["config", "configs"] or item.name.endswith(".properties") or item.name.endswith(".yml") or item.name.endswith(".json")

                targets.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": sz,
                    "size_formatted": self._format_size(sz),
                    "category": "world" if is_world else ("plugin" if is_plugin else ("config" if is_config else "other"))
                })
        except Exception:
            pass

        return targets

    def _determine_scope(self, filename: str) -> tuple[str, str]:
        fn = filename.lower()
        if "_worlds_plugins_" in fn:
            return "worlds_plugins", "Mundos + Plugins"
        elif "_worlds_" in fn:
            return "worlds", "Solo Mundos"
        elif "_custom_" in fn:
            return "custom", "Personalizado"
        elif "_full_" in fn:
            return "full", "Completo"
        return "full", "Completo"

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists all existing backup zip archives, ordered newest first."""
        self._ensure_dir()
        backups: List[Dict[str, Any]] = []

        try:
            for item in self.backups_dir.iterdir():
                if item.is_file() and item.name.endswith(".zip"):
                    stat = item.stat()
                    dt = datetime.fromtimestamp(stat.st_mtime)
                    scope, scope_label = self._determine_scope(item.name)
                    backups.append({
                        "filename": item.name,
                        "size_bytes": stat.st_size,
                        "size_formatted": self._format_size(stat.st_size),
                        "created_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "timestamp": stat.st_mtime,
                        "is_auto": "auto" in item.name.lower(),
                        "scope": scope,
                        "scope_label": scope_label
                    })
        except Exception:
            pass

        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    def has_server_data(self) -> bool:
        """Checks if data_dir contains actual Minecraft server files/folders rather than just empty/system files."""
        system_files = {"dockraft_config.json", "litemc_config.json", "tasks.json", "webhooks.json", "activity_logs.json", "session.lock", "dockraft.pid", "litemc.pid"}
        system_dirs = {"backups", ".git", ".idea", "__pycache__"}
        if not settings.data_dir.exists():
            return False
        try:
            for item in settings.data_dir.iterdir():
                if item.is_dir() and item.name not in system_dirs:
                    return True
                if item.is_file() and item.name not in system_files and not item.name.endswith(".tmp"):
                    return True
        except Exception:
            pass
        return False

    def create_backup(self, tag: str = "manual", scope: str = "full", targets: Optional[List[str]] = None, compression: bool = True) -> Dict[str, Any]:
        """Creates a zip archive of server files with selective scope."""
        if not self.has_server_data():
            raise HTTPException(
                status_code=400,
                detail="No hay ningún servidor instalado ni datos de Minecraft para respaldar."
            )

        self._ensure_dir()
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        clean_tag = "auto" if tag == "auto" else "manual"
        clean_scope = scope if scope in ["full", "worlds", "worlds_plugins", "custom"] else "full"
        filename = f"backup_{clean_tag}_{clean_scope}_{now_str}.zip"
        target_zip = self.backups_dir / filename

        # Protected / excluded directories and files
        excluded_dirs = {"backups", ".git", ".idea", "__pycache__"}
        excluded_files = {"session.lock", "dockraft.pid", "litemc.pid"}

        # Determine roots to include based on scope
        selected_roots: List[Path] = []
        if clean_scope == "worlds":
            for item in settings.data_dir.iterdir():
                if item.is_dir() and (item.name.lower().startswith("world") or item.name.lower() == "worlds"):
                    selected_roots.append(item)
                elif item.is_file() and item.name in ["server.properties", "eula.txt"]:
                    selected_roots.append(item)
        elif clean_scope == "worlds_plugins":
            for item in settings.data_dir.iterdir():
                if item.is_dir() and (item.name.lower().startswith("world") or item.name.lower() in ["worlds", "plugins", "mods", "config"]):
                    selected_roots.append(item)
                elif item.is_file() and (item.name in ["server.properties", "eula.txt"] or item.name.endswith(".yml") or item.name.endswith(".json")):
                    selected_roots.append(item)
        elif clean_scope == "custom" and targets:
            for t in targets:
                clean_t = Path(t).name
                cand = settings.data_dir / clean_t
                if cand.exists() and clean_t not in excluded_dirs:
                    selected_roots.append(cand)
        else:  # full
            selected_roots = [settings.data_dir]

        compression_mode = zipfile.ZIP_DEFLATED if compression else zipfile.ZIP_STORED
        compress_kwargs = {"compresslevel": 6} if compression else {}
        try:
            with zipfile.ZipFile(target_zip, 'w', compression_mode, **compress_kwargs) as zf:
                for root_item in selected_roots:
                    if root_item.is_file():
                        rel = root_item.relative_to(settings.data_dir)
                        zf.write(root_item, arcname=str(rel))
                    elif root_item.is_dir():
                        for root, dirs, files in os.walk(root_item):
                            rel_root = Path(root).relative_to(settings.data_dir)
                            dirs[:] = [d for d in dirs if d not in excluded_dirs and not str(rel_root / d).startswith("backups")]
                            for file in files:
                                if file in excluded_files or file.endswith(".tmp"):
                                    continue
                                file_path = Path(root) / file
                                arcname = str(rel_root / file)
                                try:
                                    zf.write(file_path, arcname=arcname)
                                except (OSError, FileNotFoundError):
                                    pass

            stat = target_zip.stat()
            formatted_sz = self._format_size(stat.st_size)
            _, scope_label = self._determine_scope(filename)

            try:
                from app.core.webhook_manager import webhook_manager
                s_info = webhook_manager._get_server_info()
                webhook_manager.dispatch(
                    "backup_created",
                    "📦 Copia de Seguridad Completada",
                    f"Se ha generado exitosamente el archivo de respaldo **{filename}**.",
                    color=0x0ea5e9,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "🗺️ Alcance", "value": f"`{scope_label}`", "inline": True},
                        {"name": "📊 Estado", "value": f"📦 Backup OK ({formatted_sz})", "inline": True}
                    ]
                )
            except Exception:
                pass

            return {
                "status": "success",
                "filename": filename,
                "scope": clean_scope,
                "scope_label": scope_label,
                "size_bytes": stat.st_size,
                "size_formatted": formatted_sz,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            if target_zip.exists():
                try:
                    target_zip.unlink()
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")

    def get_backup_path(self, filename: str) -> Path:
        """Safely resolves backup file within backups directory."""
        self._ensure_dir()
        clean_name = Path(filename).name
        target = (self.backups_dir / clean_name).resolve()
        if not target.is_relative_to(self.backups_dir.resolve()) or not target.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        return target

    def restore_backup(self, filename: str) -> Dict[str, Any]:
        """Restores a backup zip into settings.data_dir."""
        backup_file = self.get_backup_path(filename)
        
        try:
            with zipfile.ZipFile(backup_file, 'r') as zf:
                # ZipSlip check
                for member in zf.namelist():
                    member_path = (settings.data_dir / member).resolve()
                    if not member_path.is_relative_to(settings.data_dir.resolve()):
                        raise HTTPException(status_code=400, detail="Corrupted backup archive (unsafe paths)")
                    # Do not overwrite the backups folder itself
                    if member.startswith("backups/") or member.startswith("backups\\"):
                        continue
                
                # Extract
                for member in zf.infolist():
                    if member.filename.startswith("backups/") or member.filename.startswith("backups\\"):
                        continue
                    zf.extract(member, settings.data_dir)

            return {"status": "success", "message": f"Backup '{filename}' restored successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Deletes a backup file."""
        backup_file = self.get_backup_path(filename)
        try:
            backup_file.unlink()
            return {"status": "deleted", "filename": filename}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete backup: {str(e)}")

    def prune_auto_backups(self, max_count: int = 5) -> int:
        """Removes oldest automatic backups exceeding max_count."""
        if max_count <= 0:
            return 0
        backups = [b for b in self.list_backups() if b.get("is_auto")]
        deleted = 0
        if len(backups) > max_count:
            to_delete = backups[max_count:]
            for item in to_delete:
                try:
                    p = self.backups_dir / item["filename"]
                    if p.exists():
                        p.unlink()
                        deleted += 1
                except Exception:
                    pass
        return deleted

backup_manager = BackupManager()
