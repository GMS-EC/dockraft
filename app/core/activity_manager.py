import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings
from app.core.fs_utils import atomic_write_text

class ActivityManager:
    """Manages persistent audit and activity logs including console commands,
    server lifecycle, backups, updates, players, and security events.
    """

    MAX_ENTRIES = 1500
    RETENTION_DAYS = 7

    def __init__(self, log_file: Optional[Any] = None, max_entries: int = 1500, retention_days: int = 7):
        self._entries: List[Dict[str, Any]] = []
        self._next_id: int = 1
        self._loaded: bool = False
        self._custom_log_file = Path(log_file) if log_file else None
        self.max_entries = max_entries
        self.retention_days = retention_days

    @property
    def log_file(self) -> Path:
        if self._custom_log_file:
            return self._custom_log_file
        return settings.data_dir / "activity_logs.json"

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._entries = data
                        if self._entries:
                            max_id = max(e.get("id", 0) for e in self._entries)
                            self._next_id = max_id + 1
                        # Prune expired records upon load
                        if self.prune_expired(self.retention_days) > 0:
                            self._save()
            except Exception as e:
                print(f"[Dockraft] Warning loading activity_logs.json: {e}")
                self._entries = []

    def prune_expired(self, max_age_days: Optional[int] = None) -> int:
        """Prunes log entries older than max_age_days (default: 7 days).
        Returns the number of pruned entries.
        """
        days = max_age_days if max_age_days is not None else self.retention_days
        if days is None or days <= 0:
            return 0

        now_sec = time.time()
        cutoff_sec = now_sec - (days * 86400)
        initial_count = len(self._entries)
        survivors = []

        for e in self._entries:
            # Check created_at float
            c_at = e.get("created_at")
            if c_at is not None:
                try:
                    if float(c_at) >= cutoff_sec:
                        survivors.append(e)
                    continue
                except (ValueError, TypeError):
                    pass

            # Fallback to iso timestamp
            iso_val = e.get("iso")
            if iso_val:
                try:
                    dt = datetime.fromisoformat(iso_val)
                    if dt.timestamp() >= cutoff_sec:
                        survivors.append(e)
                    continue
                except Exception:
                    pass

            # Fallback to timestamp string %Y-%m-%d %H:%M:%S
            ts_val = e.get("timestamp")
            if ts_val:
                try:
                    dt = datetime.strptime(ts_val, "%Y-%m-%d %H:%M:%S")
                    if dt.timestamp() >= cutoff_sec:
                        survivors.append(e)
                    continue
                except Exception:
                    pass

            # Retain if timestamp cannot be parsed
            survivors.append(e)

        pruned = initial_count - len(survivors)
        if pruned > 0:
            self._entries = survivors
        return pruned

    def _save(self):
        try:
            self.prune_expired(self.retention_days)
            # Keep at most max_entries
            limit = self.max_entries or self.MAX_ENTRIES
            if len(self._entries) > limit:
                self._entries = self._entries[-limit:]
            json_str = json.dumps(self._entries, indent=2, ensure_ascii=False)
            atomic_write_text(self.log_file, json_str)
        except Exception as e:
            print(f"[Dockraft] Error saving activity_logs.json: {e}")

    def log(
        self,
        category: str,
        action: str,
        details: str = "",
        user: str = "admin",
        status: str = "success"
    ) -> Dict[str, Any]:
        """Records a new activity event.
        Categories: console, server, backup, update, player, security, task, file
        Statuses: success, warning, error, info
        """
        self._ensure_loaded()
        now = datetime.now()
        entry = {
            "id": self._next_id,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "iso": now.isoformat(),
            "created_at": time.time(),
            "category": category,
            "action": action,
            "details": details,
            "user": user or "admin",
            "status": status
        }
        self._next_id += 1
        self._entries.append(entry)
        self._save()
        return entry

    def get_logs(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Returns filtered and paginated activity logs along with category counts."""
        self._ensure_loaded()
        self.prune_expired(self.retention_days)

        # Category counts
        counts = {
            "all": len(self._entries),
            "console": 0,
            "server": 0,
            "backup": 0,
            "update": 0,
            "player": 0,
            "security": 0,
            "task": 0,
            "file": 0
        }
        for e in self._entries:
            cat = e.get("category", "")
            if cat in counts:
                counts[cat] += 1

        # Filtering
        filtered = list(self._entries)
        if category and category != "all":
            filtered = [e for e in filtered if e.get("category") == category]

        if search and search.strip():
            q = search.strip().lower()
            filtered = [
                e for e in filtered
                if q in e.get("action", "").lower()
                or q in e.get("details", "").lower()
                or q in e.get("user", "").lower()
                or q in e.get("timestamp", "").lower()
            ]

        # Order by newest first
        filtered.reverse()

        total = len(filtered)
        paginated = filtered[offset : offset + limit]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "counts": counts,
            "logs": paginated
        }

    def clear_logs(self) -> bool:
        """Clears all logged activities."""
        self._ensure_loaded()
        self._entries = []
        self._save()
        return True

    def export_logs(self, format_type: str = "csv") -> str:
        """Exports all logs as CSV, formatted plain text, or JSON."""
        self._ensure_loaded()
        if format_type == "json":
            return json.dumps(self._entries, indent=2, ensure_ascii=False)

        if format_type == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["id", "timestamp", "category", "action", "details", "user", "status"])
            for e in self._entries:
                writer.writerow([
                    e.get("id", ""),
                    e.get("timestamp", ""),
                    e.get("category", ""),
                    e.get("action", ""),
                    e.get("details", ""),
                    e.get("user", "admin"),
                    e.get("status", "info")
                ])
            return output.getvalue()

        # Plain text format
        lines = [
            "==================================================",
            f" DOCKRAFT - REGISTRO DE AUDITORÍA Y ACTIVIDAD",
            f" Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f" Total de eventos: {len(self._entries)}",
            "==================================================\n"
        ]
        for e in self._entries:
            ts = e.get("timestamp", "")
            cat = (e.get("category") or "").upper().ljust(8)
            status = e.get("status", "info").upper()
            action = e.get("action", "")
            details = e.get("details", "")
            user = e.get("user", "admin")
            lines.append(f"[{ts}] [{cat}] [{status}] ({user}) {action}: {details}")

        return "\n".join(lines)

activity_manager = ActivityManager()
