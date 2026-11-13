import os
import json
import stat
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional, Set, Union

PROTECTED_INTERNAL_FILES: Set[str] = {
    "dockraft_config.json",
    "litemc_config.json",
    "webhooks.json",
    "tasks.json",
    "activity_logs.json",
    "plugin_updates.json",
    "dockraft_players.json",
    ".install_lock",
    ".console_plugin_updates.json",
    ".secret_key",
}


def atomic_write_bytes(file_path: Union[str, Path], data: bytes, mode: Optional[int] = None) -> None:
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
        if mode is not None and os.name != "nt":
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(
    file_path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    mode: Optional[int] = None,
) -> None:
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
        if mode is not None and os.name != "nt":
            os.chmod(tmp_path, mode)
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
    max_entries: int = 20000,
    max_total_bytes: int = 2 * 1024 * 1024 * 1024,
    max_ratio: float = 100.0,
) -> int:
    """
    Validates a ZIP archive against ZipSlip, symlinks, and ZipBomb amplification limits
    before streaming members into dest_dir. Returns total extracted bytes.
    Raises ValueError if an unsafe entry or limit violation is detected.
    """
    dest_resolved = Path(dest_dir).resolve()
    total_extracted = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        if len(members) > max_entries:
            raise ValueError(f"Zip exceeds maximum entry limit ({max_entries})")

        for member in members:
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("Zip contains unsafe symbolic links")
            member_path = (dest_resolved / member.filename).resolve()
            if not member_path.is_relative_to(dest_resolved):
                raise ValueError("Zip contains unsafe paths (ZipSlip)")
            if member.compress_size > 0 and (member.file_size / member.compress_size) > max_ratio:
                raise ValueError("Zip compression ratio exceeds safe limit (ZipBomb)")

        for member in members:
            if skip_member_fn and skip_member_fn(member):
                continue
            member_path = (dest_resolved / member.filename).resolve()
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
                if os.name != "nt":
                    try:
                        os.chmod(member_path, stat.S_IMODE(member_path.stat().st_mode) | 0o700)
                    except OSError:
                        pass
                continue

            member_path.parent.mkdir(parents=True, exist_ok=True)
            member_bytes = 0
            with zf.open(member, "r") as src, open(member_path, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    member_bytes += len(chunk)
                    total_extracted += len(chunk)
                    if total_extracted > max_total_bytes:
                        raise ValueError("Zip extracted size exceeds safe limit (ZipBomb)")
                    if (
                        member.compress_size > 0
                        and member_bytes > 10 * 1024 * 1024
                        and (member_bytes / member.compress_size) > max_ratio
                    ):
                        raise ValueError("Zip compression ratio exceeds safe limit (ZipBomb)")
                    dst.write(chunk)

            if os.name != "nt":
                try:
                    os.chmod(member_path, stat.S_IMODE(member_path.stat().st_mode) | 0o600)
                except OSError:
                    pass
    return total_extracted


def format_size(size_bytes: int) -> str:
    """Formats a byte count into a human-readable B/KB/MB/GB string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
