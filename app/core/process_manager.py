import os
import re
import sys
import time
import shutil
import asyncio
import psutil
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Set, List, Deque, Dict, Any, Optional
from fastapi import WebSocket
from app.config import settings
from app.core.fs_utils import atomic_write_text
from app.core.activity_manager import activity_manager

# Optimized Aikar's flags for modern Paper/Purpur/Java servers
AIKAR_FLAGS = [
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC",
    "-XX:+AlwaysPreTouch",
    "-XX:G1NewSizePercent=30",
    "-XX:G1MaxNewSizePercent=40",
    "-XX:G1ReservePercent=20",
    "-XX:G1HeapWastePercent=5",
    "-XX:G1MixedGCCountTarget=4",
    "-XX:InitiatingHeapOccupancyPercent=15",
    "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5",
    "-XX:SurvivorRatio=32",
    "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1"
]

class ProcessManager:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.status: str = "OFFLINE"  # OFFLINE, STARTING, RUNNING, STOPPING
        self.connected_websockets: Set[WebSocket] = set()
        self.log_buffer: Deque[str] = deque(maxlen=1000)
        self._reader_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None
        self._psutil_proc: Optional[psutil.Process] = None
        self._cached_disk_bytes: int = 0
        self._last_disk_check: float = 0.0
        self.started_at: Optional[float] = None
        self.online_players: Set[str] = set()
        self._recent_crashes: List[float] = []
        self._intentional_stop: bool = False
        self._stop_task: Optional[asyncio.Task] = None
        self.last_start_time: Optional[float] = None
        self.current_tps: Dict[str, Any] = {
            "1m": 20.0,
            "5m": 20.0,
            "15m": 20.0,
            "status": "optimal"
        }
        self._tps_poller_task: Optional[asyncio.Task] = None

    def format_uptime(self, seconds: int) -> str:
        """Formats seconds into human-readable Spanish e.g. '2 horas, 27 minutos y 8 segundos'."""
        if seconds <= 0:
            return "0 segundos"
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []
        if days > 0:
            parts.append(f"{days} días" if days != 1 else "1 día")
        if hours > 0:
            parts.append(f"{hours} horas" if hours != 1 else "1 hora")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes} minutos" if minutes != 1 else "1 minuto")
        parts.append(f"{secs} segundos" if secs != 1 else "1 segundo")
        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return f"{parts[0]} y {parts[1]}"
        else:
            return f"{', '.join(parts[:-1])} y {parts[-1]}"

    def format_uptime_clock(self, seconds: int) -> str:
        """Formats seconds into HH:MM:SS format (or Xd HH:MM:SS if >= 24h) for telemetry cards."""
        if seconds <= 0:
            return "00:00:00"
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if days > 0:
            return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def find_running_server_processes(self) -> List[psutil.Process]:
        """Finds any running Java or Bedrock Minecraft server process on the host/container."""
        found = []
        data_dir_str = str(settings.data_dir).lower()
        current_pid = os.getpid()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.pid == current_pid:
                    continue
                name = (p.info.get('name') or "").lower()
                cmdline = p.info.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()

                p_cwd = ""
                try:
                    p_cwd = p.cwd().lower()
                except Exception:
                    pass

                is_mc = False
                # Filter out Minecraft game clients (e.g., CurseForge, Prism, Lunar, client instances)
                is_client = any(cl in cmd_str or cl in p_cwd for cl in ["curseforge", "prism", "lunar", "instances", "tlauncher", "technic", "modcitos"])
                if is_client:
                    continue

                # Must be located in or reference data_dir (or /server_data in Docker)
                in_data_dir = (data_dir_str in p_cwd) or (data_dir_str in cmd_str) or ("/server_data" in p_cwd) or ("/server_data" in cmd_str)

                if "bedrock_server" in name or "bedrock_server" in cmd_str:
                    if in_data_dir or not p_cwd:
                        is_mc = True
                elif "java" in name or "java" in cmd_str:
                    if in_data_dir:
                        if any(k in cmd_str for k in ["server.jar", "paper", "purpur", "fabric", "forge", "paperclip", "nogui", "spigot", "server"]):
                            is_mc = True
                    elif ("/server_data" in p_cwd) or ("/server_data" in cmd_str):
                        is_mc = True

                if is_mc:
                    found.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return found

    def clean_stale_session_locks(self) -> int:
        """Removes session.lock files across data_dir if no server is running to prevent DirectoryLock exceptions."""
        if self.find_running_server_processes():
            return 0
        removed = 0
        try:
            for lock_path in settings.data_dir.rglob("session.lock"):
                try:
                    lock_path.unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    pass
        except Exception:
            pass
        return removed

    def get_status(self) -> str:
        if self.process and self.process.returncode is None:
            return self.status
        # Detect if an unattached/reparented Minecraft process is running
        if self.find_running_server_processes():
            return "RUNNING"
        return "OFFLINE"

    def is_installed(self) -> bool:
        """Returns True if a server jar or binary is present in data_dir."""
        cfg = settings.runtime_config
        server_file = cfg.get("server_file")
        if server_file and (settings.data_dir / server_file).exists():
            return True
        if (settings.data_dir / "server.jar").exists():
            return True
        if (settings.data_dir / "bedrock_server").exists() or (settings.data_dir / "bedrock_server.exe").exists():
            return True
        if (settings.data_dir / "run.sh").exists():
            return True
        try:
            for f in settings.data_dir.iterdir():
                if f.is_file() and f.suffix == ".jar":
                    return True
        except Exception:
            pass
        return False

    def parse_memory_to_mb(self, mem_str: str) -> float:
        """Converts strings like '2G', '4096M', '1024K' into megabytes (float)."""
        if not mem_str:
            return 2048.0
        s = str(mem_str).strip().upper()
        try:
            if s.endswith("G"):
                return float(s[:-1]) * 1024.0
            elif s.endswith("M"):
                return float(s[:-1])
            elif s.endswith("K"):
                return float(s[:-1]) / 1024.0
            return float(s)
        except Exception:
            return 2048.0

    def get_data_dir_size_bytes(self) -> int:
        """Calculates total size of files in settings.data_dir with 5s cache."""
        now = time.time()
        if (now - self._last_disk_check) < 5.0 and self._cached_disk_bytes > 0:
            return self._cached_disk_bytes

        total = 0
        try:
            for root, _, files in os.walk(settings.data_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        pass
        except Exception:
            pass

        self._cached_disk_bytes = total
        self._last_disk_check = now
        return total

    def get_stats(self) -> Dict[str, Any]:
        """Collects memory, CPU, and disk usage of the server process."""
        status = self.get_status()
        cpu_percent = 0.0
        memory_mb = 0.0
        active_pid = None

        if self.process and self.process.pid and self.process.returncode is None:
            active_pid = self.process.pid
        else:
            rogue = self.find_running_server_processes()
            if rogue:
                active_pid = rogue[0].pid

        if active_pid:
            try:
                if self._psutil_proc is None or self._psutil_proc.pid != active_pid:
                    self._psutil_proc = psutil.Process(active_pid)
                    # Prime the CPU calculation
                    self._psutil_proc.cpu_percent(interval=None)

                # Process RSS memory and delta CPU
                memory_mb = self._psutil_proc.memory_info().rss / (1024 * 1024)
                proc_cpu = self._psutil_proc.cpu_percent(interval=None)

                for child in self._psutil_proc.children(recursive=True):
                    try:
                        memory_mb += child.memory_info().rss / (1024 * 1024)
                        proc_cpu += child.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

                num_cores = psutil.cpu_count() or 1
                cpu_percent = min(100.0, proc_cpu / num_cores)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                self._psutil_proc = None
        else:
            self._psutil_proc = None

        sys_mem = psutil.virtual_memory()
        
        # Check if server binary/jar is present
        cfg = settings.runtime_config
        server_file = cfg.get("server_file", "server.jar")
        is_installed = (
            (settings.data_dir / server_file).exists() or
            (settings.data_dir / "server.jar").exists() or
            (settings.data_dir / "bedrock_server").exists() or
            (settings.data_dir / "bedrock_server.exe").exists()
        )

        # Assigned RAM & percent relative to allocated limit
        assigned_memory_mb = self.parse_memory_to_mb(cfg.get("max_ram", "2G"))
        memory_percent = round(min(100.0, (memory_mb / assigned_memory_mb) * 100), 1) if assigned_memory_mb > 0 else 0.0

        # Disk usage & configured disk limit
        disk_limit_gb = float(cfg.get("disk_limit_gb", 10.0) or 0)
        used_disk_bytes = self.get_data_dir_size_bytes()
        used_disk_mb = round(used_disk_bytes / (1024 * 1024), 1)

        try:
            usage = shutil.disk_usage(settings.data_dir)
            total_vol_mb = round(usage.total / (1024 * 1024), 1)
            free_vol_mb = round(usage.free / (1024 * 1024), 1)
        except Exception:
            total_vol_mb = 102400.0
            free_vol_mb = 51200.0

        if disk_limit_gb > 0:
            disk_limit_mb = round(disk_limit_gb * 1024, 1)
            disk_free_mb = max(0.0, round(disk_limit_mb - used_disk_mb, 1))
            disk_percent = round(min(100.0, (used_disk_mb / disk_limit_mb) * 100), 1)
        else:
            disk_limit_mb = total_vol_mb
            disk_free_mb = free_vol_mb
            disk_percent = round(min(100.0, (used_disk_mb / total_vol_mb) * 100), 1)

        # Server start time & uptime
        tz_name = os.getenv("TZ", "America/Guayaquil")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None

        if self.started_at and status != "OFFLINE":
            uptime_seconds = int(time.time() - self.started_at)
            uptime_formatted = self.format_uptime(uptime_seconds)
            uptime_clock = self.format_uptime_clock(uptime_seconds)
            started_dt = datetime.fromtimestamp(self.started_at, tz=tz) if tz else datetime.fromtimestamp(self.started_at)
            started_at_str = started_dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            uptime_seconds = 0
            uptime_formatted = "Fuera de línea"
            uptime_clock = "00:00:00"
            started_at_str = "No iniciado"

        # MOTD and max-players from server.properties
        motd = "A Dockraft Minecraft Server"
        max_players = 20
        prop_file = settings.data_dir / "server.properties"
        if prop_file.exists():
            try:
                with open(prop_file, "r", encoding="utf-8", errors="ignore") as pf:
                    for line in pf:
                        line = line.strip()
                        if line.startswith("motd="):
                            motd = line.split("=", 1)[1]
                        elif line.startswith("max-players="):
                            try:
                                max_players = int(line.split("=", 1)[1])
                            except Exception:
                                pass
            except Exception:
                pass

        if not is_installed:
            server_name = "--"
            server_type = None
            server_version = None
            server_type_display = "--"
            motd = "Ningún servidor instalado"
            max_players = 0
            online_players_count = 0
            started_at_str = "--"
            uptime_formatted = "--"
            uptime_clock = "--"
            assigned_memory_mb = 0.0
            memory_percent = 0.0
        else:
            server_name = cfg.get("server_name", "Mi Servidor Dockraft")
            server_type = cfg.get("server_type", "paper")
            server_version = cfg.get("server_version", "1.21.4")
            server_type_display = "minecraft-bedrock" if server_type == "bedrock" else "minecraft-java"
            online_players_count = len(self.online_players)

        return {
            "status": status,
            "is_installed": is_installed,
            "server_name": server_name,
            "server_type": server_type,
            "server_type_display": server_type_display,
            "server_version": server_version,
            "pid": active_pid,
            "cpu_percent": round(cpu_percent, 1),
            "memory_mb": round(memory_mb, 1),
            "assigned_memory_mb": round(assigned_memory_mb, 1),
            "memory_percent": memory_percent,
            "disk_used_mb": used_disk_mb,
            "disk_limit_mb": disk_limit_mb,
            "disk_free_mb": disk_free_mb,
            "disk_percent": disk_percent,
            "host_memory_total_mb": round(sys_mem.total / (1024 * 1024), 1),
            "host_memory_available_mb": round(sys_mem.available / (1024 * 1024), 1),
            "host_cpu_percent": psutil.cpu_percent(interval=None),
            "started_at": self.started_at,
            "started_at_str": started_at_str,
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": uptime_formatted,
            "uptime_clock": uptime_clock,
            "timezone": tz_name,
            "online_players": online_players_count,
            "max_players": max_players,
            "motd": motd,
            "tps": self.current_tps if status == "RUNNING" else {
                "1m": None, "5m": None, "15m": None, "status": "offline"
            }
        }

    async def broadcast_message(self, message: Dict[str, Any]) -> None:
        """Sends a JSON message to all connected clients."""
        dead_sockets = set()
        for ws in self.connected_websockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)
        self.connected_websockets.difference_update(dead_sockets)

    def _append_log(self, text: str) -> None:
        # deque(maxlen=1000) handles eviction automatically — no manual pop needed
        self.log_buffer.append(text)

    async def _read_stream(self, stream: asyncio.StreamReader) -> None:
        """Reads stdout/stderr from process line by line."""
        while True:
            try:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                self._append_log(line)

                clean_ansi = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', line)

                # Check if server is running
                if self.status == "STARTING":
                    if ("Done (" in line or "Done (" in clean_ansi or
                        "Server started." in clean_ansi or "For help, type" in clean_ansi or
                        "Listening on" in clean_ansi):
                        self.status = "RUNNING"
                        await self.broadcast_message({"type": "status", "status": self.status})
                        try:
                            from app.core.webhook_manager import webhook_manager as wh
                            s_info = wh._get_server_info()
                            wh.dispatch(
                                "server_start",
                                "🟢 Servidor Iniciado",
                                "El servidor de Minecraft ha iniciado correctamente y está accesible para los jugadores.",
                                color=0x2ea043,
                                fields=[
                                    {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                                    {"name": "📦 Tipo / Versión", "value": f"`{s_info['label']}`", "inline": True},
                                    {"name": "📊 Estado", "value": "🟢 En Línea", "inline": True}
                                ]
                            )
                        except Exception:
                            pass

                # Check if server halted due to EULA
                if "agree to the EULA" in line or "agree to the EULA" in clean_ansi or "Go to eula.txt" in line:
                    await self.broadcast_message({"type": "eula_required"})

                # Track player join/leave for live player count and player history
                if "joined the game" in line or "joined the game" in clean_ansi:
                    parts = clean_ansi.split("joined the game")[0].strip().split()
                    if parts:
                        player = parts[-1].lstrip(":")
                        if player:
                            self.online_players.add(player)
                            try:
                                from app.core.player_manager import player_manager
                                player_manager.record_connection(player)
                            except Exception:
                                pass
                            try:
                                from app.core.webhook_manager import webhook_manager as wh
                                s_info = wh._get_server_info()
                                wh.dispatch(
                                    "player_join",
                                    "👤 Jugador Conectado",
                                    f"El jugador **{player}** se ha conectado al servidor.",
                                    color=0x238636,
                                    fields=[
                                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                                        {"name": "👤 Jugador", "value": f"`{player}`", "inline": True},
                                        {"name": "📊 Estado", "value": f"🟢 Conectado ({len(self.online_players)} online)", "inline": True}
                                    ]
                                )
                            except Exception:
                                pass
                elif "left the game" in line or "left the game" in clean_ansi:
                    parts = clean_ansi.split("left the game")[0].strip().split()
                    if parts:
                        player = parts[-1].lstrip(":")
                        if player:
                            self.online_players.discard(player)
                            try:
                                from app.core.player_manager import player_manager
                                player_manager.record_disconnection(player)
                            except Exception:
                                pass
                            try:
                                from app.core.webhook_manager import webhook_manager as wh
                                s_info = wh._get_server_info()
                                wh.dispatch(
                                    "player_leave",
                                    "👤 Jugador Desconectado",
                                    f"El jugador **{player}** ha salido del servidor.",
                                    color=0xd29922,
                                    fields=[
                                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                                        {"name": "👤 Jugador", "value": f"`{player}`", "inline": True},
                                        {"name": "📊 Estado", "value": f"⚪ Desconectado ({len(self.online_players)} online)", "inline": True}
                                    ]
                                )
                            except Exception:
                                pass
                elif "Player connected:" in line or "Player connected:" in clean_ansi:
                    parts = clean_ansi.split("Player connected:")[1].strip().split(",")
                    if parts:
                        player = parts[0].strip()
                        if player:
                            self.online_players.add(player)
                            try:
                                from app.core.player_manager import player_manager
                                player_manager.record_connection(player)
                            except Exception:
                                pass
                            try:
                                from app.core.webhook_manager import webhook_manager as wh
                                s_info = wh._get_server_info()
                                wh.dispatch(
                                    "player_join",
                                    "👤 Jugador Conectado",
                                    f"El jugador **{player}** se ha conectado al servidor.",
                                    color=0x238636,
                                    fields=[
                                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                                        {"name": "👤 Jugador", "value": f"`{player}`", "inline": True},
                                        {"name": "📊 Estado", "value": f"🟢 Conectado ({len(self.online_players)} online)", "inline": True}
                                    ]
                                )
                            except Exception:
                                pass
                elif "Player disconnected:" in line or "Player disconnected:" in clean_ansi:
                    parts = clean_ansi.split("Player disconnected:")[1].strip().split(",")
                    if parts:
                        player = parts[0].strip()
                        if player:
                            self.online_players.discard(player)
                            try:
                                from app.core.player_manager import player_manager
                                player_manager.record_disconnection(player)
                            except Exception:
                                pass
                            try:
                                from app.core.webhook_manager import webhook_manager as wh
                                s_info = wh._get_server_info()
                                wh.dispatch(
                                    "player_leave",
                                    "👤 Jugador Desconectado",
                                    f"El jugador **{player}** ha salido del servidor.",
                                    color=0xd29922,
                                    fields=[
                                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                                        {"name": "👤 Jugador", "value": f"`{player}`", "inline": True},
                                        {"name": "📊 Estado", "value": f"⚪ Desconectado ({len(self.online_players)} online)", "inline": True}
                                    ]
                                )
                            except Exception:
                                pass

                # Intercept TPS line (Paper / Purpur / Spigot / Fabric Carpet)
                tps_m = re.search(r'TPS from last 1m, 5m, 15m:\s*([0-9\.\*]+)[,\s]+([0-9\.\*]+)[,\s]+([0-9\.\*]+)', clean_ansi)
                if tps_m:
                    try:
                        t1 = float(tps_m.group(1).replace('*', ''))
                        t5 = float(tps_m.group(2).replace('*', ''))
                        t15 = float(tps_m.group(3).replace('*', ''))
                        t1 = min(20.0, max(0.0, t1))
                        t5 = min(20.0, max(0.0, t5))
                        t15 = min(20.0, max(0.0, t15))
                        st = "optimal" if t1 >= 19.5 else ("moderate" if t1 >= 16.0 else "lag")
                        self.current_tps = {
                            "1m": round(t1, 2),
                            "5m": round(t5, 2),
                            "15m": round(t15, 2),
                            "status": st
                        }
                        await self.broadcast_message({"type": "tps", "data": self.current_tps})
                    except Exception:
                        pass

                # Broadcast line to connected WebSocket clients
                await self.broadcast_message({"type": "log", "data": line})
            except Exception as loop_err:
                print(f"[Dockraft] Error in _read_stream: {loop_err}")

    async def _process_supervisor(self) -> None:
        """Monitors the sub-process until completion."""
        if not self.process:
            return
        
        await self.process.wait()
        if self._tps_poller_task and not self._tps_poller_task.done():
            self._tps_poller_task.cancel()
            self._tps_poller_task = None

        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
            self._stop_task = None

        prev_status = self.status
        is_intentional = self._intentional_stop or (prev_status == "STOPPING")
        self._intentional_stop = False

        run_start_time = self.started_at
        self.status = "OFFLINE"
        self.started_at = None
        self.online_players.clear()
        exit_code = self.process.returncode
        msg = f"[Dockraft] Server stopped with exit code: {exit_code}"
        self._append_log(msg)
        await self.broadcast_message({"type": "log", "data": msg})
        await self.broadcast_message({"type": "status", "status": "OFFLINE"})
        self.process = None

        # Auto-diagnose crash ONLY if stopped unexpectedly
        if not is_intentional and exit_code != 0:
            try:
                from app.core.diagnostic_manager import diagnostic_manager
                diag = diagnostic_manager.analyze_diagnostics(
                    since_timestamp=run_start_time,
                    exit_code=exit_code
                )
                if diag.get("has_issue"):
                    await self.broadcast_message({"type": "crash_diagnostics", "data": diag})
            except Exception:
                pass

        try:
            from app.core.webhook_manager import webhook_manager as wh
            s_info = wh._get_server_info()
            if is_intentional or exit_code == 0:
                wh.dispatch(
                    "server_stop",
                    "🛑 Servidor Detenido",
                    f"El servidor de Minecraft se ha detenido de forma segura (código de salida {exit_code}).",
                    color=0x8b949e,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Tipo / Versión", "value": f"`{s_info['label']}`", "inline": True},
                        {"name": "📊 Estado", "value": f"🛑 Detenido ({exit_code})", "inline": True}
                    ]
                )
            else:
                wh.dispatch(
                    "server_crash",
                    "⚠️ Caída Inesperada del Servidor (Crash)",
                    f"¡Alerta! El servidor de Minecraft ha finalizado inesperadamente con código de salida {exit_code}.",
                    color=0xda3633,
                    fields=[
                        {"name": "🎮 Servidor", "value": f"`{s_info['name']}`", "inline": True},
                        {"name": "📦 Tipo / Versión", "value": f"`{s_info['label']}`", "inline": True},
                        {"name": "📊 Estado", "value": f"⚠️ Crash ({exit_code})", "inline": True}
                    ]
                )
        except Exception:
            pass

        # Crash Detection and Auto-restart with crash-loop backoff protection (only on non-intentional unexpected crashes)
        if not is_intentional and exit_code != 0:
            crash_detection_enabled = settings.runtime_config.get("crash_detection", True)
            if crash_detection_enabled:
                now = time.time()
                # Prune crashes older than 120 seconds
                self._recent_crashes = [t for t in self._recent_crashes if now - t < 120.0]

                if len(self._recent_crashes) >= 3:
                    loop_msg = "[Dockraft] ¡Alerta! Se detectaron 3 caídas en menos de 2 minutos. Auto-reinicio pausado para evitar saturación del sistema."
                    self._append_log(loop_msg)
                    await self.broadcast_message({"type": "log", "data": loop_msg})
                else:
                    self._recent_crashes.append(now)
                    restart_msg = f"[Dockraft] Caída inesperada detectada (código {exit_code}). Reiniciando servidor automáticamente en 3 segundos (intento {len(self._recent_crashes)}/3)..."
                    self._append_log(restart_msg)
                    await self.broadcast_message({"type": "log", "data": restart_msg})
                    asyncio.create_task(self._delayed_restart(3))

    async def _delayed_restart(self, delay: int = 3) -> None:
        """Safely restarts the server after a short delay and cleans stale locks."""
        await asyncio.sleep(delay)
        if self.get_status() == "OFFLINE" and self.is_installed():
            self.clean_stale_session_locks()
            await self.start_server()

    async def start_server(self) -> Dict[str, Any]:
        """Starts the configured Minecraft server."""
        rogue = self.find_running_server_processes()
        if rogue or self.get_status() != "OFFLINE":
            pid_info = f" (PID {rogue[0].pid})" if rogue else ""
            return {"status": "error", "message": f"Ya existe un proceso del servidor en ejecución{pid_info}. Detén o fuerza la finalización (Kill) antes de iniciar."}

        # Clean any stale session.lock files left by previous crashes
        self.clean_stale_session_locks()

        cfg = settings.runtime_config
        server_type = cfg.get("server_type", "paper")
        server_file = cfg.get("server_file", "server.jar")
        server_path = settings.data_dir / server_file

        # Check file existence
        if not server_path.exists():
            # Check if Bedrock binary exists
            bedrock_candidate = settings.data_dir / "bedrock_server"
            bedrock_candidate_win = settings.data_dir / "bedrock_server.exe"
            if server_type == "bedrock":
                if bedrock_candidate.exists():
                    server_path = bedrock_candidate
                elif bedrock_candidate_win.exists():
                    server_path = bedrock_candidate_win
                else:
                    return {"status": "error", "message": f"Bedrock server binary not found in {settings.data_dir}"}
            else:
                return {"status": "error", "message": f"Server file '{server_file}' not found in {settings.data_dir}. Please download or upload one first."}

        # Build command line
        cmd: List[str] = []
        env = os.environ.copy()
        cpu_cores = int(cfg.get("cpu_cores", 0) or 0)

        if server_type == "bedrock":
            # Bedrock Native Binary
            if sys.platform != "win32":
                try:
                    os.chmod(server_path, 0o755)
                except Exception:
                    pass
                env["LD_LIBRARY_PATH"] = f".:{env.get('LD_LIBRARY_PATH', '')}"
            cmd = [str(server_path)]
        elif server_type == "forge" and (server_file == "run.sh" or (settings.data_dir / "run.sh").exists()):
            # Modern Forge (1.17+) with run.sh launcher
            run_script = settings.data_dir / "run.sh"
            if sys.platform != "win32":
                try:
                    os.chmod(run_script, 0o755)
                except Exception:
                    pass

            # Write memory & processor limits to user_jvm_args.txt for Forge
            min_ram = cfg.get("min_ram", "1G")
            max_ram = cfg.get("max_ram", "2G")
            jvm_args = [f"-Xms{min_ram}", f"-Xmx{max_ram}"]
            if cpu_cores > 0:
                jvm_args.append(f"-XX:ActiveProcessorCount={cpu_cores}")
            custom_flags = cfg.get("custom_jvm_flags", "").strip()
            if custom_flags:
                jvm_args.extend(custom_flags.split())

            user_args_file = settings.data_dir / "user_jvm_args.txt"
            atomic_write_text(user_args_file, "\n".join(jvm_args) + "\n")

            if sys.platform == "win32":
                run_bat = settings.data_dir / "run.bat"
                cmd = ["cmd.exe", "/c", str(run_bat if run_bat.exists() else run_script), "nogui"]
            else:
                cmd = ["bash", str(run_script), "nogui"]
        else:
            # Java Server (Paper, Purpur, Vanilla, Fabric, Legacy Forge)
            java_bin = cfg.get("java_path", "java")
            min_ram = cfg.get("min_ram", "1G")
            max_ram = cfg.get("max_ram", "2G")

            cmd = [java_bin, f"-Xms{min_ram}", f"-Xmx{max_ram}"]

            if cpu_cores > 0:
                cmd.append(f"-XX:ActiveProcessorCount={cpu_cores}")

            if cfg.get("aikar_flags", True):
                cmd.extend(AIKAR_FLAGS)

            custom_flags = cfg.get("custom_jvm_flags", "").strip()
            if custom_flags:
                # Validate flags: only allow safe JVM flag patterns
                # Allow: -X*, -XX:*, -D*, -ea, -da, -server, -client
                _safe_flag_re = re.compile(
                    r'^(-X[a-zA-Z0-9:+\-=%.,@/]+|-XX:[+\-]?[a-zA-Z0-9=:.,]+|-D[a-zA-Z0-9._\-]+=\S*|-ea|-da|-server|-client)$'
                )
                validated_flags = []
                for flag in custom_flags.split():
                    if _safe_flag_re.match(flag):
                        validated_flags.append(flag)
                    else:
                        print(f"[Dockraft] WARNING: Flag JVM descartado por no pasar validación: '{flag}'")
                cmd.extend(validated_flags)

            cmd.extend(["-jar", str(server_path), "nogui"])

        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
            self._stop_task = None
        self._intentional_stop = False

        self.status = "STARTING"
        msg = f"[Dockraft] Starting command: {' '.join(cmd)}"
        self._append_log(msg)
        await self.broadcast_message({"type": "log", "data": msg})
        await self.broadcast_message({"type": "status", "status": self.status})

        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(settings.data_dir),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            self.started_at = time.time()
            self.last_start_time = self.started_at
            self.online_players.clear()

            # Start background stream reading
            asyncio.create_task(self._read_stream(self.process.stdout))
            asyncio.create_task(self._process_supervisor())
            self._tps_poller_task = asyncio.create_task(self._tps_poller_loop())

            try:
                activity_manager.log(
                    category="server",
                    action="Servidor iniciado",
                    details=f"Tipo: {server_type} | Versión: {cfg.get('server_version', 'Desconocida')}",
                    user="admin",
                    status="success"
                )
            except Exception:
                pass

            return {"status": "success", "message": "Server started"}
        except Exception as e:
            self.status = "OFFLINE"
            self.process = None
            err_msg = f"[Dockraft] Error starting server: {str(e)}"
            self._append_log(err_msg)
            await self.broadcast_message({"type": "log", "data": err_msg})
            return {"status": "error", "message": str(e)}

    async def stop_server(self) -> Dict[str, Any]:
        """Sends 'stop' command to server stdin and waits for graceful shutdown."""
        rogue = self.find_running_server_processes()
        if (not self.process or self.process.returncode is not None) and not rogue:
            return {"status": "error", "message": "Server is not running"}

        self._intentional_stop = True
        self.status = "STOPPING"
        await self.broadcast_message({"type": "status", "status": self.status})

        if self.process and self.process.returncode is None and self.process.stdin:
            await self.send_command("stop")
        elif rogue:
            for p in rogue:
                try:
                    p.terminate()
                except Exception:
                    pass

        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()

        target_pid = self.process.pid if self.process else None
        self._stop_task = asyncio.create_task(self._delayed_kill_check(target_pid=target_pid, timeout=25))
        try:
            activity_manager.log(
                category="server",
                action="Servidor detenido",
                details="Solicitud de detención ordenada",
                user="admin",
                status="info"
            )
        except Exception:
            pass
        return {"status": "success", "message": "Stop command sent"}

    async def _delayed_kill_check(self, target_pid: Optional[int] = None, timeout: int = 25) -> None:
        try:
            await asyncio.sleep(timeout)
            if self.status == "STOPPING":
                target_running = False
                if self.process and self.process.returncode is None:
                    if target_pid is None or self.process.pid == target_pid:
                        target_running = True

                rogue = [p for p in self.find_running_server_processes() if target_pid is None or p.pid == target_pid]
                if target_running or rogue:
                    msg = "[Dockraft] Server did not stop in time. Terminating forcibly..."
                    self._append_log(msg)
                    await self.broadcast_message({"type": "log", "data": msg})
                    await self.kill_server()
        except asyncio.CancelledError:
            pass

    async def restart_server(self) -> Dict[str, Any]:
        """Stops and automatically restarts once offline."""
        if self.get_status() != "OFFLINE":
            await self.stop_server()
            # Wait until it is offline
            for _ in range(25):
                await asyncio.sleep(1)
                if self.get_status() == "OFFLINE":
                    break
            if self.get_status() != "OFFLINE":
                await self.kill_server()

        await asyncio.sleep(1)
        return await self.start_server()

    async def kill_server(self) -> Dict[str, Any]:
        """Immediately terminates the process and any orphaned server processes."""
        self._intentional_stop = True
        if self._stop_task and not self._stop_task.done():
            self._stop_task.cancel()
            self._stop_task = None

        killed_any = False
        if self.process and self.process.returncode is None:
            try:
                self.process.kill()
                killed_any = True
            except Exception:
                pass

        for p in self.find_running_server_processes():
            try:
                p.kill()
                killed_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        await asyncio.sleep(0.5)

        self.status = "OFFLINE"
        self.process = None
        self._psutil_proc = None
        self.started_at = None
        self.online_players.clear()

        # Clean stale session.lock so future boots succeed cleanly
        self.clean_stale_session_locks()

        msg = "[Dockraft] Server process forcibly terminated (Kill)."
        self._append_log(msg)
        await self.broadcast_message({"type": "log", "data": msg})
        await self.broadcast_message({"type": "status", "status": "OFFLINE"})

        try:
            activity_manager.log(
                category="server",
                action="Apagado forzado (Kill)",
                details="Proceso de servidor finalizado forzosamente",
                user="admin",
                status="warning"
            )
        except Exception:
            pass

        return {"status": "success", "message": "Server forcibly killed"}

    async def _tps_poller_loop(self) -> None:
        """Periodically requests 'tps' silently from Paper/Purpur/Spigot to keep TPS metric updated."""
        await asyncio.sleep(15)
        while self.get_status() == "RUNNING":
            try:
                cfg = settings.runtime_config
                if cfg.get("server_type") != "bedrock":
                    await self.send_command("tps", echo=False)
                await asyncio.sleep(45)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(45)

    async def send_command(self, cmd_text: str, echo: bool = True, user: str = "admin") -> Dict[str, Any]:
        """Writes command to process stdin and records the activity."""
        clean_cmd = (cmd_text or "").strip()
        if not clean_cmd:
            return {"status": "error", "message": "Empty command"}

        # If server is not running or stdin is not available
        if not self.process or not self.process.stdin or self.process.returncode is not None:
            if echo:
                log_echo = f"> {clean_cmd}"
                fail_echo = f"[Dockraft] Servidor no disponible ({self.status}). No se pudo ejecutar el comando: {clean_cmd}"
                self._append_log(log_echo)
                self._append_log(fail_echo)
                await self.broadcast_message({"type": "log", "data": f"{log_echo}\n{fail_echo}"})
            try:
                activity_manager.log(
                    category="console",
                    action="Comando no ejecutado",
                    details=clean_cmd,
                    user=user or "admin",
                    status="warning"
                )
            except Exception:
                pass
            return {"status": "error", "message": f"Server is not running (status: {self.status})"}

        try:
            self.process.stdin.write(f"{clean_cmd}\n".encode("utf-8"))
            await self.process.stdin.drain()
            if echo:
                # Echo command to log
                log_echo = f"> {clean_cmd}"
                self._append_log(log_echo)
                await self.broadcast_message({"type": "log", "data": log_echo})
                try:
                    activity_manager.log(
                        category="console",
                        action="Comando ejecutado",
                        details=clean_cmd,
                        user=user or "admin",
                        status="success"
                    )
                except Exception:
                    pass
            return {"status": "success"}
        except Exception as e:
            if echo:
                err_echo = f"[Dockraft] Error al enviar comando: {e}"
                self._append_log(err_echo)
                await self.broadcast_message({"type": "log", "data": err_echo})
            try:
                activity_manager.log(
                    category="console",
                    action="Fallo de comando",
                    details=f"{clean_cmd} (Error: {e})",
                    user=user or "admin",
                    status="error"
                )
            except Exception:
                pass
            return {"status": "error", "message": str(e)}

process_manager = ProcessManager()
