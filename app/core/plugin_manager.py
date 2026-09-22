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
    # Unknown/unparseable versions must never be flagged as outdated.
    if not re.search(r'\d', str(current)):
        return False
    if current.strip().lower() == latest.strip().lower():
        return False
    curr_t = parse_version_tuple(current)
    late_t = parse_version_tuple(latest)
    return late_t > curr_t

NEGATIVE_UPDATE_PATTERN = re.compile(
    r'\b(?:no\s+(?:new\s+)?(?:version|update)\b|'
    r'no\s+update\s+(?:found|available|needed)|'
    r'already\s+up[\s\-]to[\s\-]date|'
    r'up[\s\-]to[\s\-]date|'
    r'this\s+is\s+the\s+latest\s+version|'
    r'not\s+(?:outdated|found)|'
    r'ninguna\s+actualizaci[oó]n|'
    r'ya\s+(?:está|esta)\s+actualizado|'
    r'sin\s+actualizaciones?|'
    r'unable\s+to\s+(?:check|fetch|reach)|'
    r'(?:failed|fail(?:ure|ed)?)\s+to\s+check|'
    r'could(?:n.t| not)?\s+check|'
    r'error\s+(?:checking|while\s+checking|obtaining)|'
    r'connection\s+(?:failed|error|unavailable))\b',
    re.IGNORECASE
)

# Extra phrases to check as plain substrings (order matters — check the negative
# context before concluding it's truly a "no update" notice).
_NEGATIVE_EXTRA_PHRASES = [
    "this is the latest version",
    "running the latest version",
    "you're on the latest version",
    "you are on the latest version",
    "you're already on the latest",
    "you are already on the latest",
    "updated to the latest version",
    "is updated to the latest version",
    "plugin is updated to the latest version",
    "está actualizado a la última versión",
    "esta actualizado a la ultima version",
]

UPDATE_KEYWORDS_PATTERN = re.compile(
    r'(?:'
    r'\b(?:new|newer|nueva|nuevas)\s+(?:plugin\s+)?(?:version|versi[oó]n|build|compilaci[oó]n(?:es)?|update|actualizaci[oó]n(?:es)?)\b|'
    r'\b(?:update|actualizaci[oó]n)\s+(?:is\s+)?(?:available|disponible|found|encontrada)\b|'
    r'\b(?:version|versi[oó]n)\s+(?:is\s+)?(?:available|disponible)\b|'
    r'\b(?:outdated|desactualizad[ao]s?|desactualizaci[oó]n(?:es)?)\b|'
    r'\bout\s+of\s+date\b|'
    r'\b\d+\s*(?:builds?|compilaci[oó]n(?:\(es\)|es)?)\s*(?:behind|out\s+of\s+date|de\s+desactualizaci[oó]n)\b|'
    r'\best[aá]s\s+a\s+\d+\s+compilaci|'
    r'\byou(?:\'re|\s+are)\s+\d+\s+builds?\b|'
    r'\b(?:was|were)\s+detected\b|'
    r'\b(?:please|por\s+favor)\s+update\b|'
    r'\b(?:desc[aá]rgala\s+aqu[ií]|download\s+(?:it\s+)?(?:here|at))\b'
    r')',
    re.IGNORECASE
)

class PluginManager:
    def __init__(self):
        self.plugins_dir: Optional[Path] = None
        self.spiget_base_url: str = "https://api.spiget.org/v2"
        self._detected_updates: Dict[str, Dict[str, Any]] = {}
        self._cached_installed_names: Dict[str, str] = {}
        self._cached_installed_names_time: float = 0.0
        self._load_cache()

    @classmethod
    def is_negative_notice(cls, text: str) -> bool:
        """Returns True if the text indicates server is already up-to-date or has no update."""
        if not text:
            return False
        lower = str(text).lower()
        # Check compiled pattern first
        if NEGATIVE_UPDATE_PATTERN.search(text):
            return True
        # Check extra phrases, but guard against "NOT running/on the latest" false-positives
        for phrase in _NEGATIVE_EXTRA_PHRASES:
            idx = lower.find(phrase)
            if idx == -1:
                continue
            # Make sure the 3 chars before the phrase aren't "not"
            before = lower[max(0, idx - 4):idx].strip()
            if before.endswith("not"):
                continue
            return True
        return False

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
                        cleaned = {}
                        for k, v in data.items():
                            if isinstance(v, dict):
                                msg = v.get("message", "")
                                raw = v.get("raw_line", "")
                                if self.is_negative_notice(msg) or self.is_negative_notice(raw):
                                    continue
                                cleaned[k] = v
                        self._detected_updates = cleaned
                        if len(cleaned) != len(data):
                            self._save_cache()
        except Exception:
            pass

    def dismiss_update(self, plugin_name: str) -> bool:
        """Removes a specific plugin update from the detected list and persists cache."""
        p_key = plugin_name.lower().strip()
        if p_key in self._detected_updates:
            del self._detected_updates[p_key]
            self._save_cache()
            return True
        return False

    def clear_detected_updates(self) -> int:
        """Clears all detected plugin updates from memory and cache."""
        count = len(self._detected_updates)
        self._detected_updates.clear()
        self._save_cache()
        return count

    def clear_for_server_start(self) -> None:
        """Clears all detected plugin update notices when the server starts.
        This prevents stale update notices from previous server sessions from
        persisting after the user has already updated their plugins."""
        self._detected_updates.clear()
        self._save_cache()

    def get_plugins_dir(self) -> Path:
        p_dir = getattr(self, "plugins_dir", None) or (settings.data_dir / "plugins")
        p_dir.mkdir(parents=True, exist_ok=True)
        return p_dir

    def get_installed_plugin_names(self) -> Dict[str, str]:
        """Returns a mapping of lowercased plugin name to its canonical display name,
        cached for 30 seconds to avoid repeated disk reads."""
        now = time.time()
        if self._cached_installed_names and (now - self._cached_installed_names_time < 30.0):
            return self._cached_installed_names
        names = {}
        try:
            for p in self.scan_installed_plugins():
                n = (p.get("name") or "").strip()
                if n and len(n) >= 2:
                    names[n.lower()] = n
        except Exception:
            pass
        self._cached_installed_names = names
        self._cached_installed_names_time = now
        return names

    def get_installed_plugin_version(self, plugin_name: str) -> Optional[str]:
        """Returns the version of an installed plugin by matching plugin name against scanned jars."""
        if not plugin_name:
            return None
        low = plugin_name.strip().lower()
        now = time.time()
        if not hasattr(self, "_cached_installed_versions") or (now - getattr(self, "_cached_installed_versions_time", 0) > 15.0):
            mapping = {}
            try:
                for p in self.scan_installed_plugins():
                    p_name = str(p.get("name") or "").strip().lower()
                    p_ver = str(p.get("version") or "").strip()
                    if p_name and p_ver and p_ver != "Desconocida":
                        mapping[p_name] = p_ver
                    stem = re.sub(r'[-_]v?\d.*$', '', str(p.get("filename") or "")).strip().lower()
                    if stem and stem not in mapping and p_ver and p_ver != "Desconocida":
                        mapping[stem] = p_ver
            except Exception:
                pass
            self._cached_installed_versions = mapping
            self._cached_installed_versions_time = now

        return self._cached_installed_versions.get(low)

    def parse_console_update_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parses a console output line to detect whether a plugin is announcing an update."""
        if not line or not isinstance(line, str):
            return None

        # Strip ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', line).strip()
        # Strip standard server log prefix: [12:34:56 INFO]: or [INFO]:
        clean = re.sub(r'^\[\d{2}:\d{2}:\d{2}\s+(?:INFO|WARN|WARNING|ADVERTENCIA|ERROR)\]:\s*', '', clean)
        clean = re.sub(r'^\[(?:INFO|WARN|WARNING|ADVERTENCIA|ERROR)\]\s*', '', clean)

        # Reject negative phrases first (false positives: "already up to date", etc.)
        if self.is_negative_notice(clean):
            return None

        plugin_name = None
        msg = clean

        # 1. Match [PluginName] at start
        m = re.match(r'^\[([a-zA-Z0-9_\-\.]{2,35})\]\s*(.*)$', clean)
        if m:
            plugin_name = m.group(1).strip()
            msg = m.group(2).strip()
        else:
            # 2. Match PluginName: msg
            m_colon = re.match(r'^([a-zA-Z0-9_\-\.]{2,35}):\s+(.*)$', clean)
            if m_colon and m_colon.group(1).lower() not in ("loading", "starting", "done", "warn", "info", "error"):
                plugin_name = m_colon.group(1).strip()
                msg = m_colon.group(2).strip()
            else:
                # 3. Match in-message natural language announcements:
                # e.g. "New version of CMILib was detected..."
                m_in = re.match(
                    r'^(?:a\s+)?(?:new|newer|nueva|nuevas)\s+(?:plugin\s+)?(?:version|versi[oó]n|build|compilaci[oó]n|update|actualizaci[oó]n)\s+(?:of|de|for|para)\s+([a-zA-Z0-9_\-\.]{2,35})\b(.*)$',
                    clean,
                    re.IGNORECASE
                )
                if m_in:
                    plugin_name = m_in.group(1).strip()
                    msg = clean
                else:
                    m_up = re.match(
                        r'^(?:an?\s+)?(?:update|actualizaci[oó]n)\s+(?:is\s+)?(?:available|disponible|found|encontrada)\s+(?:for|para)\s+([a-zA-Z0-9_\-\.]{2,35})\b(.*)$',
                        clean,
                        re.IGNORECASE
                    )
                    if m_up:
                        plugin_name = m_up.group(1).strip()
                        msg = clean
                    else:
                        m_out = re.match(
                            r'^([a-zA-Z0-9_\-\.]{2,35})\s+(?:is\s+(?:outdated|out\s+of\s+date)|est[aá]\s+desactualizad[ao]|has\s+an?\s+(?:new\s+)?update|tiene\s+una\s+nueva\s+actualizaci[oó]n)\b(.*)$',
                            clean,
                            re.IGNORECASE
                        )
                        if m_out:
                            plugin_name = m_out.group(1).strip()
                            msg = clean

        # 4. Fallback: match known installed plugin names if present in line
        if not plugin_name:
            installed = self.get_installed_plugin_names()
            for p_low, p_disp in installed.items():
                if re.search(r'\b' + re.escape(p_low) + r'\b', clean, re.IGNORECASE):
                    plugin_name = p_disp
                    msg = clean
                    break

        if not plugin_name:
            return None

        # Ignore generic server components
        if plugin_name.lower() in ("server thread", "minecraft", "craftscheduler", "user authenticator", "main"):
            return None

        if self.is_negative_notice(msg):
            return None

        # Check for update keywords
        if not UPDATE_KEYWORDS_PATTERN.search(msg):
            return None

        # Extract URL if present
        url = None
        url_m = re.search(r'(https?://[^\s\)\]\'"]+)', msg)
        if url_m:
            candidate_url = url_m.group(1).rstrip('.,;!?:')
            generic_hosts = ("minecraft.net", "mojang.com", "oracle.com", "gnu.org", "w3.org", "aka.ms")
            if not any(h in candidate_url.lower() for h in generic_hosts):
                url = candidate_url

        # Extract version
        version = None
        trans_m = re.search(r'v?[0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?\s*(?:->|➔|to)\s*v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)', msg)
        if trans_m:
            version = trans_m.group(1)
        else:
            new_ver_m = re.search(
                r'(?:new|nueva|latest|to|->|➔)\s*(?:version|versi[oó]n|build|compilaci[oó]n|update)?\s*[:\s\(]?\s*v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)',
                msg,
                re.IGNORECASE
            )
            if new_ver_m:
                version = new_ver_m.group(1)
            else:
                build_m = re.search(r'(\d+)\s*(?:builds?|compilaci[oó]n(?:\(es\)|es)?)\s*(?:behind|out\s+of\s+date|de\s+desactualizaci[oó]n)', msg, re.IGNORECASE)
                if build_m:
                    version = f"+{build_m.group(1)} build"
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

        # Sanity check: if the "available" version is not actually newer than what
        # the plugin itself is reporting as current (e.g. ViaVersion 5.12.0-SNAPSHOT
        # being told 5.12.0 is "new"), skip it.
        if self._is_false_positive_entry(entry):
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
            if entry.get("version") and entry["version"] != "Nueva" and self._detected_updates[p_key].get("version") in (None, "", "Nueva"):
                self._detected_updates[p_key]["version"] = entry["version"]
            self._detected_updates[p_key]["message"] = entry["message"]

        self._save_cache()
        return entry

    def _is_false_positive_entry(self, entry: Dict[str, Any]) -> bool:
        """Returns True if the entry is a false-positive (detected version is not actually newer
        than the current version reported in the same message, e.g. SNAPSHOT vs release, or if
        the installed plugin jar on disk is already equal or newer than the detected version)."""
        detected_ver = entry.get("version") or ""
        p_name = entry.get("plugin") or ""

        # 0. Check against currently installed plugin version on disk
        installed_ver = self.get_installed_plugin_version(p_name)
        if installed_ver and re.search(r'\d', str(installed_ver)):
            # If the detected version is numeric, verify whether target is strictly newer than installed
            if detected_ver and re.search(r'\d', str(detected_ver)) and not str(detected_ver).startswith("+"):
                if not is_newer_version(installed_ver, detected_ver):
                    return True

        if not detected_ver or detected_ver == "Nueva" or str(detected_ver).startswith("+"):
            return False

        # 1. Check "you're on / running / current / instalado" pattern
        current_ver_m = re.search(
            r"(?:you'?re?\s+on[:\s]+|running[:\s]+|current(?:ly)?[:\s]+|instalad[ao]?[:\s]+)v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)",
            entry.get("message", ""),
            re.IGNORECASE
        )
        if current_ver_m:
            current_ver = current_ver_m.group(1)
            if not is_newer_version(current_ver, detected_ver):
                return True

        # 2. Check transition pattern "X -> Y"
        trans_m = re.search(
            r"v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)\s*(?:->|➔|to)\s*v?([0-9]+(?:\.[0-9]+)+(?:-[A-Za-z0-9\.\-]+)?)",
            entry.get("message", ""),
            re.IGNORECASE
        )
        if trans_m:
            curr = trans_m.group(1)
            nxt = trans_m.group(2)
            if not is_newer_version(curr, nxt):
                return True

        return False

    def scan_console_logs(self) -> List[Dict[str, Any]]:
        """Scans in-memory console buffer and data/logs/latest.log to discover updates for the current session."""
        def _process_entry(entry):
            if not entry or self._is_false_positive_entry(entry):
                return
            p_key = entry["plugin"].lower()
            if p_key not in self._detected_updates:
                self._detected_updates[p_key] = entry
            else:
                if entry.get("url") and not self._detected_updates[p_key].get("url"):
                    self._detected_updates[p_key]["url"] = entry["url"]
                if entry.get("version") and entry["version"] != "Nueva" and self._detected_updates[p_key].get("version") in (None, "", "Nueva"):
                    self._detected_updates[p_key]["version"] = entry["version"]

        session_markers = (
            "[Dockraft] Starting command:",
            "Starting org.bukkit.craftbukkit.Main",
            "[bootstrap] Loading Paper",
            "Starting minecraft server version",
        )

        # 1. Scan in-memory process_manager log_buffer for current session only
        try:
            from app.core.process_manager import process_manager
            buf = list(process_manager.log_buffer)
            start_idx = 0
            for idx, line in enumerate(buf):
                if any(m in line for m in session_markers):
                    start_idx = idx
            for line in buf[start_idx:]:
                entry = self.parse_console_update_line(line)
                _process_entry(entry)
        except Exception:
            pass

        # 2. Scan data/logs/latest.log for current session only
        log_file = settings.data_dir / "logs" / "latest.log"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                start_idx = 0
                for idx, line in enumerate(all_lines):
                    if any(m in line for m in session_markers):
                        start_idx = idx
                for line in all_lines[start_idx:]:
                    entry = self.parse_console_update_line(line)
                    _process_entry(entry)
            except Exception:
                pass

        self._save_cache()
        return list(self._detected_updates.values())

    def get_detected_updates(self) -> List[Dict[str, Any]]:
        """Returns detected updates; if empty, scans buffer and latest.log first."""
        if not self._detected_updates:
            self.scan_console_logs()
        # Clean any negative notices that might exist in memory
        cleaned = {
            k: v for k, v in self._detected_updates.items()
            if not self.is_negative_notice(v.get("message", "")) and not self.is_negative_notice(v.get("raw_line", ""))
        }
        # Also purge any entries where the plugin has already been updated on disk
        final_cleaned = {
            k: v for k, v in cleaned.items()
            if not self._is_false_positive_entry(v)
        }
        if len(final_cleaned) != len(self._detected_updates):
            self._detected_updates = final_cleaned
            self._save_cache()
        return list(self._detected_updates.values())

    async def enrich_update_urls(self, updates: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
        """Tries to resolve an official download URL (SpigotMC) for console-detected
        updates that were announced without a link, so the admin always has somewhere
        to download instead of searching the console."""
        from urllib.parse import quote as _url_quote
        missing = [u for u in updates if not (u.get("url") or "").strip()]
        resolved: Dict[str, str] = {}
        if missing:
            async def _resolve(client, name: str) -> None:
                if not name:
                    return
                try:
                    resp = await client.get(
                        f"{self.spiget_base_url}/search/resources/{_url_quote(name, safe='')}?size=3"
                    )
                    if resp.status_code != 200:
                        return
                    items = resp.json()
                    match = None
                    low = name.lower()
                    if isinstance(items, list):
                        for it in items:
                            item_name = str(it.get("name", "")).lower()
                            if item_name == low or low in item_name:
                                match = it
                                break
                    if match and match.get("id"):
                        resolved[low] = f"https://www.spigotmc.org/resources/{match['id']}/"
                except Exception:
                    return

            try:
                async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": "Dockraft-Minecraft-Manager/1.0"}) as client:
                    tasks = [_resolve(client, (u.get("plugin") or "").strip()) for u in missing[:limit]]
                    await asyncio.gather(*tasks)
            except Exception:
                pass

        enriched = []
        changed_cache = False
        for u in updates:
            entry = u
            if not (u.get("url") or "").strip():
                url = resolved.get((u.get("plugin") or "").strip().lower())
                if url:
                    entry = dict(u)
                    entry["url"] = url
                    key = (u.get("plugin") or "").strip().lower()
                    if key in self._detected_updates:
                        self._detected_updates[key]["url"] = url
                        changed_cache = True
            enriched.append(entry)
        if changed_cache:
            self._save_cache()
        return enriched

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
            # 1. Search Spiget for plugin name (URL-encoded)
            from urllib.parse import quote as _url_quote
            search_url = f"{self.spiget_base_url}/search/resources/{_url_quote(name, safe='')}?size=5"
            resp = await client.get(search_url)
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list) and items:
                    # Find exact or best match; never fall back to an arbitrary resource.
                    match = None
                    clean_name_lower = name.lower()
                    for item in items:
                        item_name = str(item.get("name", "")).lower()
                        if item_name == clean_name_lower or clean_name_lower in item_name:
                            match = item
                            break
                    if not match:
                        result["not_on_spigot"] = True
                        return result

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
