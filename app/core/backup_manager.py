import os
import re
import uuid
import json
import stat
import logging
import unicodedata
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from app.config import settings
from app.core.fs_utils import PROTECTED_INTERNAL_FILES, atomic_write_json, format_size, safe_extract_zip

logger = logging.getLogger("dockraft.backups")

class BackupManager:
    META_FILENAME = ".backups_meta.json"

    def __init__(self):
        self.backups_dir: Path = settings.backups_dir
        self._ensure_dir()

    @property
    def _meta_file(self) -> Path:
        return self.backups_dir / self.META_FILENAME

    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        if not self._meta_file.exists():
            return {}
        try:
            with open(self._meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_metadata(self, meta: Dict[str, Dict[str, Any]]) -> None:
        try:
            atomic_write_json(self._meta_file, meta, indent=2)
        except Exception as e:
            logger.warning("Failed to save backups metadata: %s", e)

    def _record_backup_meta(self, filename: str, origin: str, scope: str, tag: str, created_at: str) -> None:
        meta = self._load_metadata()
        meta[filename] = {
            "origin": origin,
            "scope": scope,
            "tag": tag,
            "created_at": created_at,
        }
        self._save_metadata(meta)

    def _remove_backup_meta(self, filename: str) -> None:
        meta = self._load_metadata()
        if filename in meta:
            del meta[filename]
            self._save_metadata(meta)

    @staticmethod
    def _slugify_server_name(name: Optional[str]) -> str:
        raw = str(name or "").strip()
        if not raw:
            return "dockraft"
        normalized = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
        return (slug[:40].strip("-")) or "dockraft"

    @staticmethod
    def _scope_label(scope: str) -> str:
        labels = {
            "worlds_plugins": "Mundos + Plugins",
            "worlds": "Solo Mundos",
            "custom": "Personalizado",
            "full": "Completo",
        }
        return labels.get(scope, "Completo")

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
                        except Exception as e:
                            logger.warning("Failed to migrate legacy backup '%s': %s", item.name, e)

    def get_available_targets(self) -> List[Dict[str, Any]]:
        """Returns top-level directories and important files in settings.data_dir."""
        targets = []
        excluded = {"backups", ".git", ".idea", "__pycache__"}
        if not settings.data_dir.exists():
            return targets

        try:
            for item in sorted(settings.data_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if (
                    item.name in excluded
                    or item.name.lower() in PROTECTED_INTERNAL_FILES
                    or item.name.endswith(".tmp")
                    or item.name.endswith(".pid")
                ):
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
                    "size_formatted": format_size(sz),
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
        meta_map = self._load_metadata()

        try:
            for item in self.backups_dir.iterdir():
                if item.is_file() and item.name.endswith(".zip"):
                    stat = item.stat()
                    dt = datetime.fromtimestamp(stat.st_mtime)
                    meta = meta_map.get(item.name, {})
                    if meta.get("scope") in ("full", "worlds", "worlds_plugins", "custom"):
                        scope = meta["scope"]
                        scope_label = self._scope_label(scope)
                    else:
                        scope, scope_label = self._determine_scope(item.name)

                    origin = meta.get("origin")
                    if origin not in ("auto", "manual"):
                        origin = "auto" if "auto" in item.name.lower() else "manual"

                    backups.append({
                        "filename": item.name,
                        "size_bytes": stat.st_size,
                        "size_formatted": format_size(stat.st_size),
                        "created_at": meta.get("created_at") or dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "timestamp": stat.st_mtime,
                        "origin": origin,
                        "is_auto": origin == "auto",
                        "tag": meta.get("tag", ""),
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

    def create_backup(self, tag: str = "manual", scope: str = "full", targets: Optional[List[str]] = None, compression: bool = True, compress: Optional[bool] = None) -> Dict[str, Any]:
        """Creates a zip archive of server files with selective scope."""
        if compress is not None:
            compression = compress

        try:
            from app.core.downloader import downloader
            if downloader.progress.get("is_downloading"):
                raise HTTPException(
                    status_code=409,
                    detail="No se puede crear un respaldo mientras se está instalando o descargando el servidor."
                )
        except HTTPException:
            raise
        except Exception:
            pass

        if not self.has_server_data():
            raise HTTPException(
                status_code=400,
                detail="No hay ningún servidor instalado ni datos de Minecraft para respaldar."
            )

        self._ensure_dir()
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d_%H-%M-%S")
        created_at_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        origin = "auto" if str(tag or "").strip().lower() == "auto" else "manual"
        clean_scope = scope if scope in ["full", "worlds", "worlds_plugins", "custom"] else "full"
        server_slug = self._slugify_server_name(settings.runtime_config.get("server_name"))

        filename = f"{server_slug}_{now_str}.zip"
        target_zip = self.backups_dir / filename
        suffix = 1
        while target_zip.exists():
            filename = f"{server_slug}_{now_str}_{suffix}.zip"
            target_zip = self.backups_dir / filename
            suffix += 1

        # Protected / excluded directories and files
        excluded_dirs = {"backups", ".git", ".idea", "__pycache__"}
        excluded_files = {"session.lock", "dockraft.pid", "litemc.pid"} | PROTECTED_INTERNAL_FILES

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
                elif (
                    item.is_file()
                    and item.name.lower() not in excluded_files
                    and (item.name in ["server.properties", "eula.txt"] or item.name.endswith(".yml") or item.name.endswith(".json"))
                ):
                    selected_roots.append(item)
        elif clean_scope == "custom" and targets:
            for t in targets:
                clean_t = Path(t).name
                cand = settings.data_dir / clean_t
                if cand.exists() and clean_t not in excluded_dirs and clean_t.lower() not in excluded_files:
                    selected_roots.append(cand)
        else:  # full
            selected_roots = [settings.data_dir]

        compression_mode = zipfile.ZIP_DEFLATED if compression else zipfile.ZIP_STORED
        compress_kwargs = {"compresslevel": 6} if compression else {}
        try:
            with zipfile.ZipFile(target_zip, 'w', compression_mode, **compress_kwargs) as zf:
                for root_item in selected_roots:
                    if root_item.is_symlink():
                        continue
                    if root_item.is_file():
                        if root_item.name.lower() in excluded_files or root_item.name.endswith(".tmp"):
                            continue
                        rel = root_item.relative_to(settings.data_dir)
                        zf.write(root_item, arcname=str(rel))
                    elif root_item.is_dir():
                        for root, dirs, files in os.walk(root_item, followlinks=False):
                            rel_root = Path(root).relative_to(settings.data_dir)
                            dirs[:] = [
                                d for d in dirs
                                if d not in excluded_dirs
                                and not str(rel_root / d).startswith("backups")
                                and not (Path(root) / d).is_symlink()
                            ]
                            for file in files:
                                if file.lower() in excluded_files or file.endswith(".tmp"):
                                    continue
                                file_path = Path(root) / file
                                if file_path.is_symlink():
                                    continue
                                arcname = str(rel_root / file)
                                try:
                                    zf.write(file_path, arcname=arcname)
                                except (OSError, FileNotFoundError):
                                    pass

            stat = target_zip.stat()
            formatted_sz = format_size(stat.st_size)
            scope_label = self._scope_label(clean_scope)
            self._record_backup_meta(
                filename=filename,
                origin=origin,
                scope=clean_scope,
                tag=str(tag or origin),
                created_at=created_at_str,
            )

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
                "origin": origin,
                "is_auto": origin == "auto",
                "scope": clean_scope,
                "scope_label": scope_label,
                "size_bytes": stat.st_size,
                "size_formatted": formatted_sz,
                "created_at": created_at_str
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
        if (
            not target.is_relative_to(self.backups_dir.resolve())
            or not target.is_file()
            or target.is_symlink()
        ):
            raise HTTPException(status_code=404, detail="Backup file not found")
        return target

    def restore_backup(self, filename: str) -> Dict[str, Any]:
        """Restores a backup zip into settings.data_dir."""
        backup_file = self.get_backup_path(filename)
        
        try:
            def _skip_backup_member(member: zipfile.ZipInfo) -> bool:
                if member.filename.startswith("backups/") or member.filename.startswith("backups\\"):
                    return True
                parts = Path(member.filename).parts
                if len(parts) == 1 and parts[0].lower() in PROTECTED_INTERNAL_FILES:
                    return True
                return False

            try:
                safe_extract_zip(backup_file, settings.data_dir, skip_member_fn=_skip_backup_member)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=f"Corrupted backup archive ({ve})")

            return {"status": "success", "message": f"Backup '{filename}' restored successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Deletes a backup file and its metadata entry."""
        backup_file = self.get_backup_path(filename)
        try:
            backup_file.unlink()
            self._remove_backup_meta(backup_file.name)
            return {"status": "deleted", "filename": filename}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete backup: {str(e)}")

    def prune_backups(self, max_count: int = 5) -> int:
        """Removes oldest backups (regardless of origin) exceeding max_count."""
        if max_count <= 0:
            return 0
        backups = self.list_backups()
        deleted = 0
        if len(backups) > max_count:
            to_delete = backups[max_count:]
            for item in to_delete:
                try:
                    p = self.backups_dir / item["filename"]
                    if p.exists():
                        p.unlink()
                        self._remove_backup_meta(item["filename"])
                        deleted += 1
                except Exception:
                    pass
        return deleted

    def prune_auto_backups(self, max_count: int = 5) -> int:
        """Backward-compatible alias that enforces global backup retention."""
        return self.prune_backups(max_count=max_count)

    # --- Backup Policies ---
    def _default_policy_from_config(self) -> Dict[str, Any]:
        cfg = settings.runtime_config
        pre = (cfg.get("backup_pre_command") or "").strip()
        if pre.lower() == "save-all":
            pre = ""
        scope = cfg.get("backup_scope", "full")
        if scope not in ("full", "custom", "worlds", "worlds_plugins"):
            scope = "full"
        return {
            "id": "default",
            "name": "Respaldo por Defecto",
            "scope": scope,
            "targets": list(cfg.get("backup_targets") or []),
            "compression": bool(cfg.get("backup_compression", True)),
            "stop_server": bool(cfg.get("backup_stop_server", False)),
            "pre_command": pre,
            "post_command": str(cfg.get("backup_post_command") or "").strip(),
        }

    def get_policies(self) -> List[Dict[str, Any]]:
        """Returns configured backup policies, seeding a default policy if none exist."""
        cfg = settings.runtime_config
        raw = cfg.get("backup_policies")
        if isinstance(raw, list) and len(raw) > 0:
            cleaned: List[Dict[str, Any]] = []
            for p in raw:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or "").strip() or uuid.uuid4().hex[:8]
                scope = p.get("scope", "full")
                if scope not in ("full", "custom", "worlds", "worlds_plugins"):
                    scope = "full"
                pre = str(p.get("pre_command") or "").strip()
                if pre.lower() == "save-all":
                    pre = ""
                cleaned.append({
                    "id": pid,
                    "name": str(p.get("name") or "Política de Respaldo").strip() or "Política de Respaldo",
                    "scope": scope,
                    "targets": list(p.get("targets") or []),
                    "compression": bool(p.get("compression", True)),
                    "stop_server": bool(p.get("stop_server", False)),
                    "pre_command": pre,
                    "post_command": str(p.get("post_command") or "").strip(),
                })
            if cleaned:
                return cleaned
        return [self._default_policy_from_config()]

    def get_policy(self, policy_id: Optional[str] = None) -> Dict[str, Any]:
        """Resolves a policy by ID, falling back to the first/default policy."""
        policies = self.get_policies()
        if policy_id:
            for p in policies:
                if p["id"] == policy_id:
                    return p
        return policies[0]

    def save_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates or updates a backup policy in runtime_config."""
        policies = self.get_policies()
        pid = str(policy_data.get("id") or "").strip()
        scope = policy_data.get("scope", "full")
        if scope not in ("full", "custom", "worlds", "worlds_plugins"):
            scope = "full"
        pre = str(policy_data.get("pre_command") or "").strip()
        if pre.lower() == "save-all":
            pre = ""
        name = str(policy_data.get("name") or "").strip() or "Política de Respaldo"
        entry = {
            "id": pid or uuid.uuid4().hex[:8],
            "name": name,
            "scope": scope,
            "targets": list(policy_data.get("targets") or []),
            "compression": bool(policy_data.get("compression", True)),
            "stop_server": bool(policy_data.get("stop_server", False)),
            "pre_command": pre,
            "post_command": str(policy_data.get("post_command") or "").strip(),
        }

        idx = next((i for i, p in enumerate(policies) if p["id"] == entry["id"]), None)
        if idx is not None:
            policies[idx] = entry
        else:
            if len(policies) >= 4:
                raise HTTPException(status_code=400, detail="Solo puedes tener hasta 4 políticas de respaldo.")
            policies.append(entry)

        update_cfg: Dict[str, Any] = {"backup_policies": policies}
        # Keep legacy top-level backup_* fields synced with the first/default policy
        primary = policies[0]
        update_cfg.update({
            "backup_scope": primary["scope"],
            "backup_targets": primary["targets"],
            "backup_compression": primary["compression"],
            "backup_stop_server": primary["stop_server"],
            "backup_pre_command": primary["pre_command"],
            "backup_post_command": primary.get("post_command", ""),
        })
        settings.save_runtime_config(update_cfg)
        return entry

    def delete_policy(self, policy_id: str) -> List[Dict[str, Any]]:
        """Deletes a backup policy by ID (requires at least one policy to remain)."""
        policies = self.get_policies()
        if len(policies) <= 1:
            raise HTTPException(status_code=400, detail="Debe existir al menos una política de respaldo.")
        remaining = [p for p in policies if p["id"] != policy_id]
        if len(remaining) == len(policies):
            raise HTTPException(status_code=404, detail="Política de respaldo no encontrada.")
        primary = remaining[0]
        settings.save_runtime_config({
            "backup_policies": remaining,
            "backup_scope": primary["scope"],
            "backup_targets": primary["targets"],
            "backup_compression": primary["compression"],
            "backup_stop_server": primary["stop_server"],
            "backup_pre_command": primary["pre_command"],
        })
        return remaining

backup_manager = BackupManager()
