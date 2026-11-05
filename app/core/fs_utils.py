import os
import json
import stat
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional, Set, Union

PROTECTED_INTERNAL_FILES: Set[str] = {
    "dockraft_config.json",
    "webhooks.json",
    "tasks.json",
    "activity_logs.json",
    ".install_lock",
    ".console_plugin_updates.json",
}


def atomic_write_bytes(file_path: Union[str, Path], data: bytes) -> None:
    """
    Safely and atomically writes bytes to a file by first writing to a temporary file
    in the same directory, syncing to physical disk, and atomically replacing the target.
    Prevents file corruption or zero-byte truncation during unexpected power-off/crashes.
    """
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(file_path: Union[str, Path], content: str, encoding: str = "utf-8") -> None:
    """
    Safely and atomically writes text to a file by writing to a temporary file in the
    same directory, syncing to physical disk, and replacing the target atomically.
    """
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_json(file_path: Union[str, Path], data: Any, indent: int = 2, encoding: str = "utf-8") -> None:
    """
    Safely and atomically serializes and writes JSON data to a file.
    If serialization or disk write fails, the original file is left completely untouched.
    """
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def safe_extract_zip(
    zip_path: Union[str, Path],
    dest_dir: Union[str, Path],
    skip_member_fn: Optional[Callable[[zipfile.ZipInfo], bool]] = None,
) -> int:
    """
    Validates a ZIP archive against ZipSlip path traversal and symlink attacks
    before extracting members into dest_dir. Returns total extracted bytes.
    Raises ValueError if an unsafe entry is detected.
    """
    dest_resolved = Path(dest_dir).resolve()
    total_extracted = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        for member in members:
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Zip contains unsafe symbolic links")
            member_path = (dest_resolved / member.filename).resolve()
            if not member_path.is_relative_to(dest_resolved):
                raise ValueError("Zip contains unsafe paths (ZipSlip)")

        for member in members:
            if skip_member_fn and skip_member_fn(member):
                continue
            zf.extract(member, dest_resolved)
            total_extracted += max(0, int(member.file_size or 0))
    return total_extracted
