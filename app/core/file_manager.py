import os
import stat
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, UploadFile
from app.config import settings
from app.core.fs_utils import PROTECTED_INTERNAL_FILES, atomic_write_text, safe_extract_zip

class FileManager:
    PROTECTED_FILES = PROTECTED_INTERNAL_FILES
    _QUOTA_CACHE_TTL = 5.0

    def __init__(self):
        self.base_dir = settings.data_dir
        self._cached_used_bytes: Optional[int] = None
        self._cache_ts: float = 0.0

    def invalidate_quota_cache(self, delta_bytes: Optional[int] = None) -> None:
        """Updates or invalidates the cached disk usage."""
        if delta_bytes is not None and self._cached_used_bytes is not None:
            self._cached_used_bytes = max(0, self._cached_used_bytes + delta_bytes)
            self._cache_ts = time.time()
        else:
            self._cached_used_bytes = None
            self._cache_ts = 0.0

    def _get_used_bytes(self, force_recalc: bool = False) -> int:
        now = time.time()
        if not force_recalc and self._cached_used_bytes is not None and (now - self._cache_ts) < self._QUOTA_CACHE_TTL:
            return self._cached_used_bytes

        total_used = 0
        try:
            for root, _, files in os.walk(self.base_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total_used += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        pass
        except Exception:
            pass

        self._cached_used_bytes = total_used
        self._cache_ts = now
        return total_used

    def _is_protected_root_file(self, path: Path) -> bool:
        resolved_base = self.base_dir.resolve()
        resolved_path = path.resolve()
        return resolved_path.parent == resolved_base and resolved_path.name.lower() in self.PROTECTED_FILES

    def _resolve_safe_path(self, relative_path: str = "") -> Path:
        """
        Resolves relative path and verifies it strictly stays within settings.data_dir.
        Throws 403 Forbidden if path traversal is detected.
        """
        # Clean relative path of leading slashes and normalize separators
        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        target = (self.base_dir / clean_rel).resolve()
        
        try:
            # Python 3.9+ is_relative_to
            if not target.is_relative_to(self.base_dir.resolve()):
                raise HTTPException(status_code=403, detail="Access denied: Path traversal detected")
        except AttributeError:
            # Fallback for older python
            base_str = str(self.base_dir.resolve())
            target_str = str(target)
            if not target_str.startswith(base_str):
                raise HTTPException(status_code=403, detail="Access denied: Path traversal detected")

        if self._is_protected_root_file(target):
            raise HTTPException(status_code=403, detail="Access denied: Protected system configuration file")

        return target

    def list_directory(self, relative_path: str = "") -> Dict[str, Any]:
        """Lists files and folders in the target directory."""
        target_dir = self._resolve_safe_path(relative_path)
        if not target_dir.exists() or not target_dir.is_dir():
            raise HTTPException(status_code=404, detail="Directory not found")

        is_root = target_dir == self.base_dir.resolve()
        items: List[Dict[str, Any]] = []
        try:
            for entry in os.scandir(target_dir):
                if is_root and entry.name.lower() in self.PROTECTED_FILES:
                    continue
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if entry.is_file() else 0,
                    "modified": int(stat.st_mtime),
                    "extension": entry.name.split(".")[-1].lower() if "." in entry.name and not entry.is_dir() else ""
                })
        except PermissionError:
            raise HTTPException(status_code=403, detail="Permission denied")

        # Sort: directories first, then alphabetical
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        rel_str = str(target_dir.relative_to(self.base_dir.resolve())).replace("\\", "/")
        if rel_str == ".":
            rel_str = ""

        return {
            "current_path": rel_str,
            "items": items
        }

    def read_file(self, relative_path: str) -> Dict[str, Any]:
        """Reads file text content with a maximum safety limit (2 MB)."""
        target = self._resolve_safe_path(relative_path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        if target.stat().st_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large for inline editor (>10MB)")


        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {
                "path": relative_path,
                "content": content,
                "size": target.stat().st_size
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    def _check_disk_quota(self, extra_bytes: int = 0) -> None:
        """Verifies that adding extra_bytes does not exceed the configured disk quota."""
        disk_limit_gb = float(settings.runtime_config.get("disk_limit_gb", 10.0) or 0)
        if disk_limit_gb <= 0:
            return

        limit_bytes = int(disk_limit_gb * 1024 * 1024 * 1024)
        total_used = self._get_used_bytes()

        if (total_used + extra_bytes) > limit_bytes:
            used_gb = round(total_used / (1024 * 1024 * 1024), 2)
            raise HTTPException(
                status_code=400,
                detail=f"Límite de espacio en disco superado ({used_gb} GB usados de {disk_limit_gb} GB permitidos). Libera espacio o amplía el límite en Configuración."
            )

    def write_file(self, relative_path: str, content: str) -> Dict[str, Any]:
        """Saves content to the target file."""
        target = self._resolve_safe_path(relative_path)
        content_bytes = len(content.encode("utf-8"))
        old_size = target.stat().st_size if target.exists() else 0
        extra_bytes = max(0, content_bytes - old_size)
        self._check_disk_quota(extra_bytes=extra_bytes)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, content)
            self.invalidate_quota_cache(delta_bytes=content_bytes - old_size)
            return {"status": "saved", "path": relative_path, "size": len(content)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")

    def create_folder(self, relative_path: str) -> Dict[str, Any]:
        """Creates a new folder."""
        target = self._resolve_safe_path(relative_path)
        if target.exists():
            raise HTTPException(status_code=400, detail="Folder already exists")
        target.mkdir(parents=True, exist_ok=True)
        return {"status": "created", "path": relative_path}

    def delete_item(self, relative_path: str) -> Dict[str, Any]:
        """Deletes a file or directory."""
        target = self._resolve_safe_path(relative_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Item not found")

        if target == self.base_dir:
            raise HTTPException(status_code=400, detail="Cannot delete root data directory")

        if target.is_dir():
            shutil.rmtree(target)
            self.invalidate_quota_cache()
        else:
            sz = target.stat().st_size
            target.unlink()
            self.invalidate_quota_cache(delta_bytes=-sz)

        return {"status": "deleted", "path": relative_path}

    async def save_upload(self, relative_dir: str, file: UploadFile) -> Dict[str, Any]:
        """Saves an uploaded file while enforcing disk quota in a single pass."""
        target_dir = self._resolve_safe_path(relative_dir)
        if not target_dir.is_dir():
            raise HTTPException(status_code=400, detail="Target path is not a directory")

        self._check_disk_quota(extra_bytes=0)

        # Sanitize filename: extract basename only, remove dangerous characters
        raw_name = file.filename or "upload"
        safe_name = Path(raw_name).name  # strip any path components
        safe_name = re.sub(r'[^\w.\-]', '_', safe_name)  # allow word chars, dots, hyphens
        safe_name = safe_name.lstrip('.')  # prevent hidden/dotfiles like .bashrc
        if not safe_name:
            safe_name = "upload"
        dest_file = target_dir / safe_name
        if self._is_protected_root_file(dest_file):
            raise HTTPException(status_code=403, detail="Access denied: Cannot overwrite protected system file")

        old_size = dest_file.stat().st_size if dest_file.exists() else 0
        disk_limit_gb = float(settings.runtime_config.get("disk_limit_gb", 10.0) or 0)
        limit_bytes = int(disk_limit_gb * 1024 * 1024 * 1024) if disk_limit_gb > 0 else 0
        base_used = max(0, self._get_used_bytes() - old_size)

        written = 0
        try:
            with open(dest_file, "wb") as f:
                while True:
                    chunk = file.file.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if limit_bytes > 0 and (base_used + written) > limit_bytes:
                        used_gb = round(base_used / (1024 * 1024 * 1024), 2)
                        raise HTTPException(
                            status_code=400,
                            detail=f"Límite de espacio en disco superado ({used_gb} GB usados de {disk_limit_gb} GB permitidos). Libera espacio o amplía el límite en Configuración."
                        )
                    f.write(chunk)

            self.invalidate_quota_cache(delta_bytes=written - old_size)
            return {
                "status": "uploaded",
                "filename": file.filename,
                "size": written
            }
        except HTTPException:
            if dest_file.exists():
                dest_file.unlink(missing_ok=True)
            self.invalidate_quota_cache()
            raise
        finally:
            await file.close()

    def extract_zip(self, relative_zip_path: str, target_relative_dir: str = "") -> Dict[str, Any]:
        """Extracts a zip file securely into the given directory."""
        zip_path = self._resolve_safe_path(relative_zip_path)
        dest_dir = self._resolve_safe_path(target_relative_dir)

        if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
            raise HTTPException(status_code=400, detail="Invalid zip file")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                total_uncompressed = sum(max(0, int(m.file_size or 0)) for m in zf.infolist())
            self._check_disk_quota(extra_bytes=total_uncompressed)

            is_root_dest = dest_dir == self.base_dir.resolve()
            safe_extract_zip(
                zip_path,
                dest_dir,
                skip_member_fn=(lambda m: Path(m.filename).name.lower() in self.PROTECTED_FILES and len(Path(m.filename).parts) == 1) if is_root_dest else None,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {"status": "extracted", "path": relative_zip_path}

    def rename_item(self, relative_path: str, new_name: str) -> Dict[str, Any]:
        """Renames a file or folder safely."""
        raw_name = (new_name or "").strip()
        if not raw_name or "/" in raw_name or "\\" in raw_name or ".." in raw_name:
            raise HTTPException(status_code=400, detail="Nombre inválido o caracteres no permitidos")
        clean_new = Path(raw_name).name

        target = self._resolve_safe_path(relative_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Elemento no encontrado")

        if target == self.base_dir:
            raise HTTPException(status_code=400, detail="No se puede renombrar el directorio raíz")

        dest = target.parent / clean_new
        # Ensure destination stays within base_dir
        if not dest.resolve().is_relative_to(self.base_dir.resolve()) or self._is_protected_root_file(dest):
            raise HTTPException(status_code=403, detail="Ruta de destino inválida")

        if dest.exists():
            raise HTTPException(status_code=400, detail=f"Ya existe un elemento llamado '{clean_new}'")

        target.rename(dest)
        rel_dest = str(dest.relative_to(self.base_dir.resolve())).replace("\\", "/")
        return {"status": "renamed", "old_path": relative_path, "new_path": rel_dest, "name": clean_new}

    def duplicate_item(self, relative_path: str) -> Dict[str, Any]:
        """Duplicates a file or folder with a .copy suffix."""
        target = self._resolve_safe_path(relative_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Elemento no encontrado")

        if target.is_symlink():
            raise HTTPException(status_code=400, detail="No se permiten enlaces simbólicos")

        if target.resolve() == self.base_dir.resolve():
            raise HTTPException(status_code=400, detail="No se puede duplicar el directorio raíz")

        parent = target.parent
        if target.is_file():
            stem = target.stem
            suffix = target.suffix
            candidate = f"{stem}.copy{suffix}"
            idx = 1
            while (parent / candidate).exists():
                candidate = f"{stem}.copy_{idx}{suffix}"
                idx += 1
            dest = parent / candidate

            self._check_disk_quota(extra_bytes=target.stat().st_size)
            shutil.copy2(target, dest)
        else:
            candidate = f"{target.name}.copy"
            idx = 1
            while (parent / candidate).exists():
                candidate = f"{target.name}.copy_{idx}"
                idx += 1
            dest = parent / candidate

            total_size = sum(
                f.stat().st_size
                for f in target.rglob('*')
                if not f.is_symlink() and f.is_file()
            )
            self._check_disk_quota(extra_bytes=total_size)

            def _ignore_symlinks(dir_path: str, names: List[str]) -> List[str]:
                return [n for n in names if (Path(dir_path) / n).is_symlink()]

            shutil.copytree(target, dest, ignore=_ignore_symlinks)

        return {"status": "duplicated", "new_name": dest.name}

    def compress_item(self, relative_path: str) -> Dict[str, Any]:
        """Compresses a file or directory into a .zip archive."""
        target = self._resolve_safe_path(relative_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="Elemento no encontrado")

        if target.is_symlink():
            raise HTTPException(status_code=400, detail="No se permiten enlaces simbólicos")

        base_resolved = self.base_dir.resolve()
        if target.resolve() == base_resolved:
            raise HTTPException(status_code=400, detail="No se puede comprimir el directorio raíz")

        parent = target.parent
        zip_name = f"{target.name}.zip"
        if (parent / zip_name).exists():
            zip_name = f"{target.name}_{int(time.time())}.zip"
        dest_zip = parent / zip_name

        self._check_disk_quota(extra_bytes=1024 * 1024)

        try:
            with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                if target.is_file():
                    zf.write(target, arcname=target.name)
                else:
                    for root, dirs, files in os.walk(target, followlinks=False):
                        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
                        for file in files:
                            file_path = Path(root) / file
                            if file_path.is_symlink() or file.lower() in PROTECTED_INTERNAL_FILES:
                                continue
                            if not file_path.resolve().is_relative_to(base_resolved):
                                continue
                            arcname = file_path.relative_to(parent)
                            zf.write(file_path, arcname=str(arcname))
            return {"status": "compressed", "archive_name": dest_zip.name}
        except Exception as e:
            if dest_zip.exists():
                dest_zip.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Error al comprimir: {str(e)}")

    def create_file(self, relative_path: str) -> Dict[str, Any]:
        """Creates an empty file at the specified relative path."""
        target = self._resolve_safe_path(relative_path)
        if target.exists():
            raise HTTPException(status_code=400, detail="El archivo ya existe")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        return {"status": "created", "path": relative_path}

    def bulk_delete(self, paths: List[str]) -> Dict[str, Any]:
        """Deletes multiple files or directories safely."""
        deleted = []
        errors = []
        for p in paths:
            try:
                target = self._resolve_safe_path(p)
                if not target.exists() or target == self.base_dir:
                    continue
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                deleted.append(p)
            except Exception as e:
                errors.append({"path": p, "error": str(e)})

        return {"status": "ok", "deleted": deleted, "errors": errors, "count": len(deleted), "deleted_count": len(deleted)}

    def bulk_compress(self, paths: List[str], target_dir: str = "", archive_name: str = "") -> Dict[str, Any]:
        """Compresses multiple selected files or folders into a single .zip archive."""
        dest_dir = self._resolve_safe_path(target_dir)
        if not dest_dir.exists() or not dest_dir.is_dir():
            dest_dir = self.base_dir

        raw_name = (archive_name or "").strip()
        if not raw_name or "/" in raw_name or "\\" in raw_name:
            raw_name = f"archive_{int(time.time())}.zip"
        if not raw_name.lower().endswith(".zip"):
            raw_name += ".zip"

        dest_zip = dest_dir / raw_name
        if dest_zip.exists():
            dest_zip = dest_dir / f"{dest_zip.stem}_{int(time.time())}.zip"

        self._check_disk_quota(extra_bytes=1024 * 1024)

        base_resolved = self.base_dir.resolve()
        try:
            with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                for p in paths:
                    target = self._resolve_safe_path(p)
                    if not target.exists() or target.is_symlink() or target.resolve() == base_resolved:
                        continue
                    if target.is_file():
                        if target.name.lower() in PROTECTED_INTERNAL_FILES:
                            continue
                        zf.write(target, arcname=target.name)
                    else:
                        for root, dirs, files in os.walk(target, followlinks=False):
                            dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
                            for file in files:
                                file_path = Path(root) / file
                                if file_path.is_symlink() or file.lower() in PROTECTED_INTERNAL_FILES:
                                    continue
                                if not file_path.resolve().is_relative_to(base_resolved):
                                    continue
                                arcname = Path(target.name) / file_path.relative_to(target)
                                zf.write(file_path, arcname=str(arcname).replace("\\", "/"))

            rel_zip = str(dest_zip.relative_to(self.base_dir.resolve())).replace("\\", "/")
            return {"status": "compressed", "archive_name": dest_zip.name, "path": rel_zip}
        except Exception as e:
            if dest_zip.exists():
                dest_zip.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Error al comprimir: {str(e)}")

file_manager = FileManager()
