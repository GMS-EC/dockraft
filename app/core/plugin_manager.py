import re
import json
import time
import asyncio
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
import yaml

from app.config import settings

def parse_version_tuple(ver_str: str) -> tuple:
    """Extracts numeric segments from version string for safe comparison (e.g. 'v5.4.130-SNAPSHOT' -> (5, 4, 130))."""
    clean = re.sub(r'^[vV]', '', str(ver_str).strip())
    # Grab all digit sequences
    parts = re.findall(r'\d+', clean)
    if parts:
        return tuple(int(p) for p in parts[:4])
    return (0,)

def is_newer_version(current: str, latest: str) -> bool:
    """Returns True if latest version is higher than current version."""
    if not current or not latest:
        return False
    if current.strip().lower() == latest.strip().lower():
        return False
    curr_t = parse_version_tuple(current)
    late_t = parse_version_tuple(latest)
    return late_t > curr_t

class PluginManager:
    def __init__(self):
        self.plugins_dir: Optional[Path] = None
        self.spiget_base_url: str = "https://api.spiget.org/v2"
        self._detected_updates: Dict[str, Dict[str, Any]] = {}
        self._load_cache()

    @property
    def cache_file(self) -> Path:
        return settings.data_dir / "plugin_updates.json"

    @property
    def logs_dir(self) -> Path:
        return settings.data_dir / "logs"

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._detected_updates, f, indent=2)
        except Exception:
            pass

    def _load_cache(self):
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._detected_updates = data
        except Exception:
            pass

    def get_plugins_dir(self) -> Path:
        p_dir = getattr(self, "plugins_dir", None) or (settings.data_dir / "plugins")
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def parse_console_update_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parses a console output line to detect whether a plugin is announcing an update with a link."""
        if not line or not isinstance(line, str):
            return None

        # Strip ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', line).strip()
        # Strip standard server log prefix: [12:34:56 INFO]: or [INFO]:
        clean = re.sub(r'^\[\d{2}:\d{2}:\d{2}\s+(?:INFO|WARN|WARNING|ADVERTENCIA)\]:\s*', '', clean)
        clean = re.sub(r'^\[(?:INFO|WARN|WARNING|ADVERTENCIA)\]\s*', '', clean)

        # Match [PluginName] at start
        m = re.match(r'^\[([a-zA-Z0-9_\-\.]{2,35})\]\s*(.*)$', clean)
        if not m:
            return None

        plugin_name = m.group(1).strip()
        msg = m.group(2).strip()

        # Ignore generic server components
        if plugin_name.lower() in ("server thread", "minecraft", "craftscheduler", "user authenticator", "main"):
            return None

        # Check for update keywords
        update_kw = re.search(
            r'\b(?:update\s+is\s+available|new\s+update|new\s+version|version\s+is\s+available|'
            r'nueva\s+versi[oó]n|actualizaci[oó]n\s+disponible|outdated|update\s+available|'
            r'new\s+build\s+available|update\s+found)\b',
            msg,
            re.IGNORECASE
        )
        if not update_kw:
            return None

        # Extract URL if present
        url = None
        url_m = re.search(r'(https?://[^\s\)\]\'"]+)', msg)
        if url_m:
            candidate_url = url_m.group(1).rstrip('.,;!?:')
            generic_hosts = ("minecraft.net", "mojang.com", "oracle.com", "gnu.org", "w3.org", "aka.ms")
            if not any(h in candidate_url.lower() for h in generic_hosts):
                url = candidate_url

        # Extract version if present (prioritize new version indicators)
        version = None
        new_ver_m = re.search(
            r'(?:new|nueva|latest|to|->|➔)\s*(?:version|versi[oó]n|build|update)?\s*[:\s\(]\s*v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)',
            msg,
            re.IGNORECASE
        )
        if new_ver_m:
            version = new_ver_m.group(1)
        else:
            ver_m = re.search(r'(?:version|v|\:|\#)\s*([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)', msg, re.IGNORECASE)
            if ver_m:
                version = ver_m.group(1)
            else:
                ver_num = re.search(r'\b([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b', msg)
                if ver_num:
                    version = ver_num.group(1)

        import time
        return {
            "plugin": plugin_name,
            "version": version or "Nueva",
            "url": url,
            "message": msg,
            "raw_line": clean,
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S")
        }

    def handle_console_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Called for each line output by the server process."""
        entry = self.parse_console_update_line(line)
        if not entry:
            return None

        p_key = entry["plugin"].lower()
        is_new = p_key not in self._detected_updates

        if is_new:
            self._detected_updates[p_key] = entry
            # Trigger webhook dispatch for the newly detected update
            try:
                from app.core.webhook_manager import webhook_manager as wh
                s_info = wh._get_server_info()
                plugin_title = entry["plugin"]
                url_str = entry.get("url") or ""
                body_desc = f"El plugin **{plugin_title}** ha reportado una nueva versión en consola:\n\n`{entry['message']}`"
                if url_str:
                    body_desc += f"\n\n[Descargar Actualización]({url_str})"

                wh.dispatch(
                    "plugin_update",
                    f"📦 Actualización: {plugin_title}",
                    body_desc,
                    color=0x388bfd,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Plugin", "value": f"`{plugin_title}`", "inline": True},
                        {"name": "🔗 Enlace de Descarga", "value": f"<{url_str}>" if url_str else "`Ver en consola`", "inline": True}
                    ]
                )
            except Exception:
                pass
        else:
            if entry.get("url") and not self._detected_updates[p_key].get("url"):
                self._detected_updates[p_key]["url"] = entry["url"]
            self._detected_updates[p_key]["message"] = entry["message"]

        self._save_cache()
        return entry

    def scan_console_logs(self) -> List[Dict[str, Any]]:
        """Scans in-memory console buffer and data/logs/latest.log to discover updates."""
        # 1. Scan in-memory process_manager log_buffer
        try:
            from app.core.process_manager import process_manager
            for line in list(process_manager.log_buffer):
                entry = self.parse_console_update_line(line)
                if entry:
                    p_key = entry["plugin"].lower()
                    if p_key not in self._detected_updates:
                        self._detected_updates[p_key] = entry
                    elif entry.get("url") and not self._detected_updates[p_key].get("url"):
                        self._detected_updates[p_key]["url"] = entry["url"]
        except Exception:
            pass

        # 2. Scan data/logs/latest.log
        log_file = settings.data_dir / "logs" / "latest.log"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        entry = self.parse_console_update_line(line)
                        if entry:
                            p_key = entry["plugin"].lower()
                            if p_key not in self._detected_updates:
                                self._detected_updates[p_key] = entry
                            elif entry.get("url") and not self._detected_updates[p_key].get("url"):
                                self._detected_updates[p_key]["url"] = entry["url"]
            except Exception:
                pass

        self._save_cache()
        return list(self._detected_updates.values())

    def get_detected_updates(self) -> List[Dict[str, Any]]:
        """Returns detected updates; if empty, scans buffer and latest.log first."""
        if not self._detected_updates:
            self.scan_console_logs()
        return list(self._detected_updates.values())

    def scan_installed_plugins(self) -> List[Dict[str, Any]]:
        """Scans data/plugins/*.jar, parses plugin.yml, and returns metadata for each installed plugin."""
        plugins_dir = self.get_plugins_dir()
        plugins = []

        for jar_path in sorted(plugins_dir.glob("*.jar")):
            plugin_info = {
                "filename": jar_path.name,
                "file_size": jar_path.stat().st_size,
                "file_size_formatted": self._format_size(jar_path.stat().st_size),
                "name": jar_path.stem,
                "version": "Desconocida",
                "author": "",
                "description": "",
                "website": "",
                "valid": False
            }

            try:
                with zipfile.ZipFile(jar_path, "r") as z:
                    yml_candidates = [n for n in z.namelist() if n.lower() == "plugin.yml" or n.lower().endswith("/plugin.yml")]
                    if yml_candidates:
                        raw_yml = z.read(yml_candidates[0]).decode("utf-8", errors="replace")
                        parsed = None
                        try:
                            parsed = yaml.safe_load(raw_yml)
                        except Exception:
                            pass

                        if isinstance(parsed, dict):
                            plugin_info["name"] = str(parsed.get("name") or plugin_info["name"])
                            plugin_info["version"] = str(parsed.get("version") or plugin_info["version"])
                            author_val = parsed.get("author") or parsed.get("authors")
                            if isinstance(author_val, list):
                                plugin_info["author"] = ", ".join(str(a) for a in author_val)
                            elif author_val:
                                plugin_info["author"] = str(author_val)
                            plugin_info["description"] = str(parsed.get("description") or "")
                            plugin_info["website"] = str(parsed.get("website") or "")
                            plugin_info["valid"] = True
                        else:
                            # Fallback regex parsing
                            name_m = re.search(r'^\s*name:\s*[\'"]?([^\'"\r\n]+)', raw_yml, re.M)
                            ver_m = re.search(r'^\s*version:\s*[\'"]?([^\'"\r\n]+)', raw_yml, re.M)
                            if name_m:
                                plugin_info["name"] = name_m.group(1).strip()
                                plugin_info["valid"] = True
                            if ver_m:
                                plugin_info["version"] = ver_m.group(1).strip()
            except Exception:
                # If corrupt or non-readable jar, retain filename
                pass

            plugins.append(plugin_info)

        return plugins

    async def check_plugin_updates(self) -> List[Dict[str, Any]]:
        """Queries Spiget API for each installed plugin to detect updates."""
        installed = self.scan_installed_plugins()
        if not installed:
            return []

        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Dockraft-Minecraft-Manager/1.0"}) as client:
            tasks = [self._check_single_plugin(client, p) for p in installed]
            return await asyncio.gather(*tasks)

    async def _check_single_plugin(self, client: httpx.AsyncClient, plugin: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(plugin)
        result["has_update"] = False
        result["latest_version"] = None
        result["spigot_url"] = None
        result["spigot_id"] = None
        result["checked"] = True

        name = plugin.get("name")
        if not name or name == "Desconocida":
            return result

        try:
            # 1. Search Spiget for plugin name
            search_url = f"{self.spiget_base_url}/search/resources/{name}?size=5"
            resp = await client.get(search_url)
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list) and items:
                    # Find exact or best match
                    match = None
                    clean_name_lower = name.lower()
                    for item in items:
                        item_name = str(item.get("name", "")).lower()
                        if item_name == clean_name_lower or clean_name_lower in item_name:
                            match = item
                            break
                    if not match:
                        match = items[0]

                    res_id = match.get("id")
                    result["spigot_id"] = res_id
                    result["spigot_url"] = f"https://www.spigotmc.org/resources/{res_id}/"

                    # 2. Get latest version of this resource
                    ver_url = f"{self.spiget_base_url}/resources/{res_id}/versions/latest"
                    ver_resp = await client.get(ver_url)
                    if ver_resp.status_code == 200:
                        ver_data = ver_resp.json()
                        latest_name = str(ver_data.get("name", "")).strip()
                        if latest_name:
                            result["latest_version"] = latest_name
                            result["has_update"] = is_newer_version(result["version"], latest_name)
        except Exception as e:
            result["check_error"] = str(e)

        return result

    async def check_and_notify_updates(self) -> Dict[str, Any]:
        """Runs check and, if outdated plugins are found, dispatches webhook alert."""
        results = await self.check_plugin_updates()
        outdated = [p for p in results if p.get("has_update")]
        if outdated:
            for p in outdated:
                p_key = p["name"].lower()
                if p_key not in self._detected_updates:
                    self._detected_updates[p_key] = {
                        "plugin": p["name"],
                        "version": p.get("latest_version") or "Nueva",
                        "url": p.get("spigot_url") or "",
                        "message": f"Nueva versión {p.get('latest_version')} disponible (instalada: {p.get('version')})",
                        "raw_line": "",
                        "timestamp": time.time(),
                        "time_str": time.strftime("%H:%M:%S")
                    }
            self._save_cache()

            try:
                from app.core.webhook_manager import webhook_manager as wh
                s_info = wh._get_server_info()
                
                details_preview = "\n".join([
                    f"• **{p['name']}**: `v{p['version']}` ➔ `v{p['latest_version']}`"
                    for p in outdated[:5]
                ])
                if len(outdated) > 5:
                    details_preview += f"\n_y {len(outdated) - 5} plugin(s) más..._"

                wh.dispatch(
                    "plugin_update",
                    "📦 Actualizaciones de Plugins Disponibles",
                    f"Se han detectado **{len(outdated)} plugin(s)** con nuevas versiones:\n\n{details_preview}",
                    color=0x388bfd,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Total Desactualizados", "value": f"`{len(outdated)} plugins`", "inline": True},
                        {"name": "📊 Fuente", "value": "`SpigotMC / Spiget`", "inline": True}
                    ]
                )
            except Exception:
                pass

        console_updates = self.get_detected_updates()
        if console_updates and not outdated:
            try:
                from app.core.webhook_manager import webhook_manager as wh
                s_info = wh._get_server_info()
                
                details_preview = "\n".join([
                    f"• **{u['plugin']}** ({u.get('version') or 'Nueva'}): " + (f"<{u['url']}>" if u.get('url') else f"`{u['message'][:55]}`")
                    for u in console_updates[:5]
                ])
                if len(console_updates) > 5:
                    details_preview += f"\n_y {len(console_updates) - 5} plugin(s) más..._"

                wh.dispatch(
                    "plugin_update",
                    "📦 Actualizaciones de Plugins (Consola)",
                    f"Se han detectado **{len(console_updates)} plugin(s)** con avisos de actualización en la consola:\n\n{details_preview}",
                    color=0x388bfd,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Total Reportados", "value": f"`{len(console_updates)} plugins`", "inline": True},
                        {"name": "📊 Fuente", "value": "`Consola del Servidor`", "inline": True}
                    ]
                )
            except Exception:
                pass

        return {
            "total_installed": len(results),
            "total_outdated": len(outdated),
            "plugins": results,
            "console_updates": console_updates
        }

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

plugin_manager = PluginManager()
