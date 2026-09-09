import json
import logging
import hashlib
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from app.config import settings
from app.core.process_manager import process_manager
from app.core.fs_utils import atomic_write_json, atomic_write_text

logger = logging.getLogger("dockraft.players")

_MAX_PLAYER_HISTORY = 2000
_SAVE_DEBOUNCE_SECONDS = 2.0

_JAVA_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
_BEDROCK_NAME_RE = re.compile(r"^[A-Za-z0-9_ ]{1,16}$")
_CTRL_CHARS_RE = re.compile(r"[\r\n\x00-\x1f\x7f]")


def _is_bedrock_server() -> bool:
    return settings.runtime_config.get("server_type") == "bedrock"


def _clean_reason(reason: Optional[str], fallback: str = "") -> str:
    """Strips newlines/control characters from a console-embedded reason to prevent
    command injection via stdin, and collapses whitespace."""
    if not reason:
        return fallback
    cleaned = _CTRL_CHARS_RE.sub(" ", reason).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned[:200] or fallback


def _validate_player_name(player_name: str) -> Optional[str]:
    """Returns a normalized valid player name or None if invalid."""
    clean = (player_name or "").strip()
    if not clean:
        return None
    if _is_bedrock_server():
        if not _BEDROCK_NAME_RE.match(clean) or clean.startswith(" ") or clean.endswith(" "):
            return None
    else:
        if not _JAVA_NAME_RE.match(clean):
            return None
    return clean


def _offline_uuid(player_name: str) -> str:
    """Derives the standard offline-mode UUID used by vanilla/Paper servers
    (MD5 of 'OfflinePlayer:<name>' with version/variant bits set)."""
    digest = hashlib.md5(f"OfflinePlayer:{player_name}".encode("utf-8")).digest()
    digest = bytearray(digest)
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def _now_with_offset() -> str:
    """Returns current local time including the UTC offset, matching Mojang's format."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")

class PlayerManager:
    """
    Manages Minecraft players, operators, whitelists, and bans for both Java and Bedrock.
    Supports real-time live server execution via console commands when ONLINE,
    as well as offline JSON file manipulation when OFFLINE.
    """
    def __init__(self):
        self._history_file = settings.data_dir / "dockraft_players.json"
        self._player_history: Dict[str, Dict[str, Any]] = {}
        self._history_lock = threading.Lock()
        self._save_timer: Optional[threading.Timer] = None
        self._save_pending: bool = False
        self._load_history()

    def _load_history(self) -> None:
        """Loads cached player history (last seen, notes) from disk."""
        if self._history_file.exists():
            try:
                with open(self._history_file, "r", encoding="utf-8") as f:
                    self._player_history = json.load(f)
                if not isinstance(self._player_history, dict):
                    self._player_history = {}
                # Bound memory immediately on load.
                self._trim_history()
            except Exception as e:
                logger.debug(f"Error loading player history: {e}")
                self._player_history = {}

    def _trim_history(self) -> None:
        """Keeps only the most recent _MAX_PLAYER_HISTORY entries (by last seen)."""
        if len(self._player_history) <= _MAX_PLAYER_HISTORY:
            return
        ordered = sorted(
            self._player_history.items(),
            key=lambda kv: (kv[1] or {}).get("last_timestamp", 0) or 0,
            reverse=True
        )
        self._player_history = dict(ordered[:_MAX_PLAYER_HISTORY])

    def _schedule_save(self) -> None:
        """Coalesces writes so joins/leaves don't fsync the whole file every event."""
        with self._history_lock:
            self._save_pending = True
            if self._save_timer is None:
                timer = threading.Timer(_SAVE_DEBOUNCE_SECONDS, self.flush)
                timer.daemon = True
                self._save_timer = timer
                timer.start()

    def flush(self) -> None:
        """Writes any pending player history to disk (called by debounce timer and on shutdown)."""
        with self._history_lock:
            self._save_timer = None
            if not self._save_pending:
                return
            self._save_pending = False
            self._trim_history()
            data = json.dumps(self._player_history, indent=2, ensure_ascii=False)
        try:
            atomic_write_text(self._history_file, data)
        except Exception as e:
            logger.warning(f"Error saving player history: {e}")

    def _save_history(self) -> None:
        """Debounced persist (kept as internal alias for existing callers)."""
        self._schedule_save()

    def record_connection(self, player_name: str) -> None:
        """Records a player join event."""
        if not player_name:
            return
        now_dt = datetime.now().strftime("%d/%m/%Y %H:%M")
        with self._history_lock:
            if player_name not in self._player_history:
                self._player_history[player_name] = {}
            self._player_history[player_name]["last_connection"] = now_dt
            self._player_history[player_name]["last_timestamp"] = time.time()
            self._trim_history()
        self._save_history()

    def record_disconnection(self, player_name: str) -> None:
        """Records a player leave event."""
        if not player_name:
            return
        now_dt = datetime.now().strftime("%d/%m/%Y %H:%M")
        with self._history_lock:
            if player_name not in self._player_history:
                self._player_history[player_name] = {}
            self._player_history[player_name]["last_connection"] = now_dt
            self._player_history[player_name]["last_timestamp"] = time.time()
            self._trim_history()
        self._save_history()

    def _read_json_file(self, filename: str) -> Any:
        """Reads a JSON file from settings.data_dir safely."""
        target = settings.data_dir / filename
        if not target.exists():
            return []
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_json_file(self, filename: str, data: Any) -> bool:
        """Writes a JSON file to settings.data_dir safely."""
        target = settings.data_dir / filename
        try:
            atomic_write_json(target, data, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to write {filename}: {e}")
            return False

    def get_ops(self) -> Set[str]:
        """Returns set of operator player names (lowercase)."""
        ops_set = set()
        # Java: ops.json
        raw = self._read_json_file("ops.json")
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "name" in entry:
                    ops_set.add(entry["name"].lower())

        # Bedrock: permissions.json
        bedrock_raw = self._read_json_file("permissions.json")
        if isinstance(bedrock_raw, list):
            for entry in bedrock_raw:
                if isinstance(entry, dict) and entry.get("permission") == "operator":
                    if "name" in entry:
                        ops_set.add(entry["name"].lower())
                    elif "xuid" in entry:
                        ops_set.add(entry["xuid"].lower())

        return ops_set

    def get_banned_players(self) -> List[Dict[str, Any]]:
        """Returns list of banned players with reason, date, and source."""
        banned_list = []
        raw = self._read_json_file("banned-players.json")
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "name" in entry:
                    banned_list.append({
                        "name": entry["name"],
                        "uuid": entry.get("uuid", ""),
                        "created": entry.get("created", "--"),
                        "source": entry.get("source", "Server"),
                        "expires": entry.get("expires", "forever"),
                        "reason": entry.get("reason", "Baneado por un operador.")
                    })
        return banned_list

    def get_whitelist(self) -> Set[str]:
        """Returns set of whitelisted player names (lowercase)."""
        wl_set = set()
        for fn in ["whitelist.json", "allowlist.json"]:
            raw = self._read_json_file(fn)
            if isinstance(raw, list):
                for entry in raw:
                    if isinstance(entry, dict) and "name" in entry:
                        wl_set.add(entry["name"].lower())
        return wl_set

    def get_known_players(self) -> Set[str]:
        """Collects all known players from usercache, history, ops, whitelist, and online players.

        Names are deduplicated case-insensitively, keeping the canonical casing of the
        first source that knows the player (usercache has priority over lowercase lists).
        """
        known: Dict[str, str] = {}

        def _add(name: str) -> None:
            if not name or not name.strip():
                return
            known.setdefault(name.strip().lower(), name.strip())

        # 1. usercache.json (authoritative casing)
        usercache = self._read_json_file("usercache.json")
        if isinstance(usercache, list):
            for u in usercache:
                if isinstance(u, dict) and "name" in u:
                    _add(u["name"])

        # 2. player_history.json
        for name in self._player_history.keys():
            _add(name)

        # 3. ops, whitelist, banned
        for op_name in self.get_ops():
            _add(op_name)
        for wl_name in self.get_whitelist():
            _add(wl_name)
        for b in self.get_banned_players():
            _add(b["name"])

        # 4. currently online players
        for p in process_manager.online_players:
            _add(p)

        return set(known.values())

    def get_all_data(self) -> Dict[str, Any]:
        """Gathers unified player data for the web UI."""
        self._load_history()
        ops = self.get_ops()
        whitelist = self.get_whitelist()
        banned = self.get_banned_players()
        banned_names = {b["name"].lower() for b in banned}
        online_lower = {p.lower() for p in process_manager.online_players}

        players_list = []
        for name in sorted(self.get_known_players(), key=lambda s: s.lower()):
            name_lower = name.lower()
            is_banned = name_lower in banned_names
            is_online = name_lower in online_lower
            is_op = name_lower in ops
            is_whitelisted = name_lower in whitelist

            # Pick the history entry using the canonical lowercase key to avoid duplicates.
            hist = self._player_history.get(name) or self._player_history.get(name_lower, {})
            last_conn = hist.get("last_connection", "never")
            if is_online:
                last_conn = "En línea ahora"
            elif not last_conn or last_conn in ["--", "never", "Nunca", "None"]:
                last_conn = "never"

            players_list.append({
                "name": name,
                "is_online": is_online,
                "is_op": is_op,
                "is_whitelisted": is_whitelisted,
                "is_banned": is_banned,
                "last_connection": last_conn
            })

        # Sort: Online first, then by name
        players_list.sort(key=lambda p: (not p["is_online"], p["name"].lower()))

        return {
            "server_online": process_manager.get_status() in ["RUNNING", "ONLINE"],
            "online_count": len(process_manager.online_players),
            "players": players_list,
            "banned": banned
        }

    async def kick_player(self, player_name: str, reason: str = "") -> Dict[str, Any]:
        """Kicks a connected player."""
        name = _validate_player_name(player_name)
        if not name:
            return {"status": "error", "message": "Nombre de jugador inválido."}

        if process_manager.get_status() not in ["RUNNING", "ONLINE"]:
            return {"status": "warning", "message": "El servidor está fuera de línea. Solo se puede expulsar a jugadores conectados."}

        reason_clean = _clean_reason(reason)
        cmd = f"kick {name}"
        if reason_clean:
            cmd += f" {reason_clean}"

        res = await process_manager.send_command(cmd)
        if res.get("status") != "success":
            return {"status": "error", "message": res.get("message", "No se pudo enviar la orden de expulsión.")}

        # Let the server's own "left the game" event update tracking (no premature bookkeeping).
        return {"status": "success", "message": f"Jugador {name} expulsado."}

    async def kick_all_players(self, reason: str = "") -> Dict[str, Any]:
        """Kicks all currently connected players."""
        if process_manager.get_status() not in ["RUNNING", "ONLINE"]:
            return {"status": "warning", "message": "El servidor está fuera de línea. Solo se puede expulsar a jugadores conectados."}

        reason_clean = _clean_reason(reason, "Mantenimiento del servidor")

        # 1. Native kick @a command
        await process_manager.send_command(f"kick @a {reason_clean}")

        # 2. Iterate through currently tracked online players to ensure disconnection across all server flavors
        online_list = list(process_manager.online_players)
        for p in online_list:
            await process_manager.send_command(f"kick {p} {reason_clean}")

        count = len(online_list)
        process_manager.online_players.clear()

        msg = f"Se ha expulsado a todos los jugadores ({count} conectados)." if count > 0 else "Se ha enviado la orden de expulsión a todos los jugadores (@a)."
        return {
            "status": "success",
            "count": count,
            "message": msg
        }

    async def ban_player(self, player_name: str, reason: str = "") -> Dict[str, Any]:
        """Bans a player either via console command or JSON file."""
        name = _validate_player_name(player_name)
        if not name:
            return {"status": "error", "message": "Nombre de jugador inválido."}

        if _is_bedrock_server():
            return {"status": "warning", "message": "Bedrock no dispone de un archivo de bans tipo Java. Gestiona los accesos desde allowlist.json / la consola Bedrock."}

        reason_clean = _clean_reason(reason, "Baneado por el administrador.")
        online = process_manager.get_status() in ["RUNNING", "ONLINE"]

        if online:
            # 'ban' alone blocks future logins but does NOT disconnect the player;
            # send an explicit kick so the ban applies immediately.
            await process_manager.send_command(f"ban {name} {reason_clean}")
            await process_manager.send_command(f"kick {name} {reason_clean}")
            # The server's "left the game" event will update tracking afterwards.
        else:
            # Offline JSON manipulation with a correct offline-mode UUID + offset date
            banned_list = self._read_json_file("banned-players.json")
            if not isinstance(banned_list, list):
                banned_list = []

            # Remove if duplicate already exists
            banned_list = [b for b in banned_list if b.get("name", "").lower() != name.lower()]
            banned_list.append({
                "uuid": _offline_uuid(name),
                "name": name,
                "created": _now_with_offset(),
                "source": "Dockraft Panel",
                "expires": "forever",
                "reason": reason_clean
            })
            self._write_json_file("banned-players.json", banned_list)

        return {"status": "success", "message": f"Jugador {name} ha sido baneado."}

    async def pardon_player(self, player_name: str) -> Dict[str, Any]:
        """Unbans / pardons a player."""
        name = _validate_player_name(player_name)
        if not name:
            return {"status": "error", "message": "Nombre de jugador inválido."}

        if _is_bedrock_server():
            return {"status": "warning", "message": "Bedrock no dispone de un archivo de bans tipo Java. Gestiona los accesos desde allowlist.json."}

        cmd = f"pardon {name}"
        if process_manager.get_status() in ["RUNNING", "ONLINE"]:
            await process_manager.send_command(cmd)

        # Ensure offline file is updated as well
        banned_list = self._read_json_file("banned-players.json")
        if isinstance(banned_list, list):
            new_list = [b for b in banned_list if b.get("name", "").lower() != name.lower()]
            self._write_json_file("banned-players.json", new_list)

        return {"status": "success", "message": f"Jugador {name} desbaneado con éxito."}

    async def set_op(self, player_name: str, is_op: bool) -> Dict[str, Any]:
        """Grants or revokes OP status."""
        name = _validate_player_name(player_name)
        if not name:
            return {"status": "error", "message": "Nombre de jugador inválido."}

        if _is_bedrock_server():
            return {"status": "warning", "message": "Bedrock gestiona operadores en permissions.json (por XUID). Con el servidor en línea usa su consola o edita permissions.json desde la pestaña Archivos."}

        cmd = f"op {name}" if is_op else f"deop {name}"

        if process_manager.get_status() in ["RUNNING", "ONLINE"]:
            res = await process_manager.send_command(cmd)
            if res.get("status") != "success":
                return {"status": "error", "message": res.get("message", "No se pudo enviar la orden.")}
        else:
            # Offline JSON manipulation
            ops_list = self._read_json_file("ops.json")
            if not isinstance(ops_list, list):
                ops_list = []

            ops_list = [o for o in ops_list if o.get("name", "").lower() != name.lower()]
            if is_op:
                ops_list.append({
                    "uuid": _offline_uuid(name),
                    "name": name,
                    "level": 4,
                    "bypassesPlayerLimit": False
                })
            self._write_json_file("ops.json", ops_list)

        action_word = "promovido a Operador" if is_op else "removido de Operadores"
        return {"status": "success", "message": f"Jugador {name} {action_word}."}

    def add_player(self, player_name: str) -> Dict[str, Any]:
        """Registers a player name into Dockraft's known player catalog without recording a connection."""
        name = _validate_player_name(player_name)
        if not name:
            return {"status": "error", "message": "Nombre de jugador inválido (usa 1-16 letras/números, sin caracteres especiales)."}
        added = False
        with self._history_lock:
            if name not in self._player_history:
                self._player_history[name] = {
                    "last_connection": "never",
                    "last_timestamp": 0.0,
                    "added_manually": True
                }
                added = True
        if added:
            self._save_history()
        return {"status": "success", "message": f"Jugador {name} registrado."}

player_manager = PlayerManager()
