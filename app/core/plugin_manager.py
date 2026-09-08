import re
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
        self.plugins_dir: Path = settings.data_dir / "plugins"
        self.spiget_base_url: str = "https://api.spiget.org/v2"

    def get_plugins_dir(self) -> Path:
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        return self.plugins_dir

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
                    f"Se han detectado **{len(outdated)} plugin(s)** con nuevas versiones en SpigotMC:\n\n{details_preview}",
                    color=0x388bfd,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Total Desactualizados", "value": f"`{len(outdated)} plugins`", "inline": True},
                        {"name": "📊 Fuente", "value": "`SpigotMC / Spiget`", "inline": True}
                    ]
                )
            except Exception:
                pass

        return {
            "total_installed": len(results),
            "total_outdated": len(outdated),
            "plugins": results
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
