import asyncio
import logging
import time
from collections import deque
from datetime import datetime
from typing import Dict, Any, List

from app.core.process_manager import process_manager

logger = logging.getLogger("dockraft.metrics")

class MetricsManager:
    """
    Ultra-lightweight in-memory metrics recorder using a circular ring buffer (deque).
    Provides real-time and historical telemetry (CPU, RAM, Players) without database
    or disk I/O overhead.
    """
    def __init__(self, maxlen: int = 360):
        # 360 samples at 10-second intervals = 1 hour of high-resolution telemetry (~45 KB RAM)
        self.history: deque = deque(maxlen=maxlen)
        self.peak_cpu: float = 0.0
        self.peak_ram_mb: float = 0.0
        self.peak_players: int = 0
        self._sampling_task: asyncio.Task | None = None
        self._is_running: bool = False

    def record_sample(self) -> Dict[str, Any]:
        """Captures a single performance telemetry point."""
        now = time.time()
        time_str = datetime.fromtimestamp(now).strftime("%H:%M:%S")

        status = process_manager.get_status()
        stats = process_manager.get_stats()

        cpu = round(stats.get("cpu_percent", 0.0), 1)
        ram_mb = round(stats.get("memory_mb", 0.0), 1)
        ram_percent = round(stats.get("memory_percent", 0.0), 1)
        assigned_ram_mb = round(stats.get("assigned_memory_mb", 2048.0), 1)
        players = int(stats.get("online_players", 0))

        # Track peaks
        if cpu > self.peak_cpu:
            self.peak_cpu = cpu
        if ram_mb > self.peak_ram_mb:
            self.peak_ram_mb = ram_mb
        if players > self.peak_players:
            self.peak_players = players

        sample = {
            "timestamp": int(now),
            "time_str": time_str,
            "status": status,
            "cpu_percent": cpu,
            "memory_mb": ram_mb,
            "memory_percent": ram_percent,
            "assigned_ram_mb": assigned_ram_mb,
            "players_online": players
        }

        self.history.append(sample)
        return sample

    async def _sampler_loop(self) -> None:
        """Background coroutine that samples server telemetry periodically."""
        self._is_running = True
        logger.info("[Dockraft Metrics] Loop de telemetria en memoria iniciado (intervalo: 10s).")
        while self._is_running:
            try:
                self.record_sample()
            except Exception as e:
                logger.debug(f"[Dockraft Metrics] Error muestreando telemetria: {e}")
            await asyncio.sleep(10)

    def start(self) -> None:
        """Starts the background telemetry sampler."""
        if self._sampling_task is None or self._sampling_task.done():
            self._sampling_task = asyncio.create_task(self._sampler_loop())

    def stop(self) -> None:
        """Stops the telemetry sampler."""
        self._is_running = False
        if self._sampling_task and not self._sampling_task.done():
            self._sampling_task.cancel()

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns the chronological list of recorded metrics."""
        return list(self.history)

    def get_summary(self) -> Dict[str, Any]:
        """Returns aggregate metrics, peaks, and latest status."""
        stats = process_manager.get_stats()
        history_list = list(self.history)

        avg_cpu = 0.0
        if history_list:
            online_samples = [s["cpu_percent"] for s in history_list if s.get("status") in ["RUNNING", "ONLINE", "STARTING"]]
            if online_samples:
                avg_cpu = round(sum(online_samples) / len(online_samples), 1)

        return {
            "current_status": process_manager.get_status(),
            "uptime_seconds": stats.get("uptime_seconds", 0),
            "uptime_str": stats.get("uptime_formatted", "--"),
            "current_cpu": round(stats.get("cpu_percent", 0.0), 1),
            "peak_cpu": self.peak_cpu,
            "avg_cpu": avg_cpu,
            "current_ram_mb": round(stats.get("memory_mb", 0.0), 1),
            "assigned_ram_mb": round(stats.get("assigned_memory_mb", 2048.0), 1),
            "current_ram_percent": round(stats.get("memory_percent", 0.0), 1),
            "peak_ram_mb": self.peak_ram_mb,
            "current_players": int(stats.get("online_players", 0)),
            "peak_players": self.peak_players,
            "total_samples": len(self.history)
        }

    def reset(self) -> None:
        """Clears recorded history and resets peak counters."""
        self.history.clear()
        self.peak_cpu = 0.0
        self.peak_ram_mb = 0.0
        self.peak_players = 0

metrics_manager = MetricsManager()
