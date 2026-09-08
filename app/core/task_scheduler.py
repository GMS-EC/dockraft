import os
import time
import json
import uuid
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import List, Dict, Any, Optional
from croniter import croniter

from app.config import settings
from app.core.process_manager import process_manager
from app.core.backup_manager import backup_manager

from app.core.fs_utils import atomic_write_json

def get_server_timezone() -> ZoneInfo:
    tz_name = os.getenv("TZ", "America/Guayaquil")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        try:
            return ZoneInfo("UTC")
        except Exception:
            return timezone.utc  # type: ignore

class TaskScheduler:
    def __init__(self):
        self.tasks_file: Path = settings.data_dir / "tasks.json"
        self.tasks: List[Dict[str, Any]] = []
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self.load_tasks()

    def get_tz(self) -> ZoneInfo:
        return get_server_timezone()

    def now(self) -> datetime:
        return datetime.now(self.get_tz())

    def load_tasks(self) -> None:
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.tasks = data
            except Exception as e:
                print(f"[Dockraft] Error cargando tasks.json: {e}")
                self.tasks = []
        else:
            self.tasks = []

    def save_tasks(self) -> None:
        try:
            atomic_write_json(self.tasks_file, self.tasks, indent=2)
        except Exception as e:
            print(f"[Dockraft] Error guardando tasks.json: {e}")

    def calculate_next_run(self, task: Dict[str, Any], from_dt: Optional[datetime] = None) -> Optional[str]:
        """Calculates next execution timestamp formatted in server timezone."""
        if not task.get("enabled", True):
            return None

        tz = self.get_tz()
        base_dt = from_dt or self.now()
        schedule_type = task.get("schedule_type", "interval")

        try:
            if schedule_type == "cron":
                expr = task.get("cron_expression", "").strip()
                if not expr or not croniter.is_valid(expr):
                    return None
                cron = croniter(expr, base_dt)
                next_dt = cron.get_next(datetime)
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=tz)
                return next_dt.strftime("%Y-%m-%d %H:%M:%S")

            elif schedule_type == "interval":
                val = float(task.get("interval_value", 1) or 1)
                unit = task.get("interval_unit", "days").lower()
                mult = 60 if unit == "minutes" else (3600 if unit == "hours" else 86400)
                interval_seconds = val * mult

                last_run_str = task.get("last_run")
                if last_run_str:
                    try:
                        last_dt = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
                        next_dt = datetime.fromtimestamp(last_dt.timestamp() + interval_seconds, tz=tz)
                        if next_dt <= base_dt:
                            next_dt = datetime.fromtimestamp(base_dt.timestamp() + interval_seconds, tz=tz)
                    except Exception:
                        next_dt = datetime.fromtimestamp(base_dt.timestamp() + interval_seconds, tz=tz)
                else:
                    next_dt = datetime.fromtimestamp(base_dt.timestamp() + interval_seconds, tz=tz)

                return next_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"[Dockraft] Error calculando próxima ejecución para tarea {task.get('id')}: {e}")
            return None

        return None

    def list_tasks(self) -> List[Dict[str, Any]]:
        """Returns all scheduled tasks with freshly calculated next_run."""
        res = []
        for t in self.tasks:
            copy_t = dict(t)
            if copy_t.get("enabled"):
                copy_t["next_run"] = self.calculate_next_run(copy_t)
            else:
                copy_t["next_run"] = None
            res.append(copy_t)
        return res

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        for t in self.tasks:
            if t.get("id") == task_id:
                copy_t = dict(t)
                copy_t["next_run"] = self.calculate_next_run(copy_t)
                return copy_t
        return None

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())[:8]
        new_task = {
            "id": task_id,
            "name": str(data.get("name", "Nueva Tarea")).strip(),
            "action": str(data.get("action", "restart")).strip(), # start, stop, restart, backup, command, check_updates
            "command": str(data.get("command", "")).strip(),
            "schedule_type": str(data.get("schedule_type", "interval")).strip(), # interval, cron
            "interval_value": max(1, int(data.get("interval_value", 1) or 1)),
            "interval_unit": str(data.get("interval_unit", "days")).strip(), # minutes, hours, days
            "cron_expression": str(data.get("cron_expression", "0 4 * * *")).strip(),
            "enabled": bool(data.get("enabled", True)),
            "last_run": None,
            "created_at": self.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        new_task["next_run"] = self.calculate_next_run(new_task)
        self.tasks.append(new_task)
        self.save_tasks()
        return new_task

    def update_task(self, task_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for i, t in enumerate(self.tasks):
            if t.get("id") == task_id:
                t["name"] = str(data.get("name", t.get("name"))).strip()
                t["action"] = str(data.get("action", t.get("action"))).strip()
                t["command"] = str(data.get("command", t.get("command", ""))).strip()
                t["schedule_type"] = str(data.get("schedule_type", t.get("schedule_type"))).strip()
                t["interval_value"] = max(1, int(data.get("interval_value", t.get("interval_value", 1)) or 1))
                t["interval_unit"] = str(data.get("interval_unit", t.get("interval_unit", "days"))).strip()
                t["cron_expression"] = str(data.get("cron_expression", t.get("cron_expression", "0 4 * * *"))).strip()
                if "enabled" in data:
                    t["enabled"] = bool(data["enabled"])
                t["next_run"] = self.calculate_next_run(t)
                self.save_tasks()
                return dict(t)
        return None

    def delete_task(self, task_id: str) -> bool:
        init_len = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.get("id") != task_id]
        if len(self.tasks) != init_len:
            self.save_tasks()
            return True
        return False

    def toggle_task(self, task_id: str, enabled: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        for t in self.tasks:
            if t.get("id") == task_id:
                if enabled is None:
                    t["enabled"] = not t.get("enabled", True)
                else:
                    t["enabled"] = bool(enabled)
                t["next_run"] = self.calculate_next_run(t)
                self.save_tasks()
                return dict(t)
        return None

    async def execute_task_action(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Executes the specific action defined in a task."""
        action = task.get("action", "restart")
        task_name = task.get("name", task.get("id"))
        result = {"status": "success", "action": action, "task_id": task.get("id")}

        if not process_manager.is_installed():
            print(f"[Dockraft] Omitiendo tarea programada '{task_name}': ningún servidor instalado.")
            return {
                "status": "skipped",
                "action": action,
                "task_id": task.get("id"),
                "message": "Omitido: ningún servidor instalado actualmente"
            }

        print(f"[Dockraft] Ejecutando tarea programada: '{task_name}' (Acción: {action})...")

        try:
            if action == "start":
                if process_manager.get_status() == "OFFLINE":
                    await process_manager.start_server()
                    result["message"] = "Servidor iniciado"
                else:
                    result["message"] = f"Servidor ya estaba {process_manager.get_status()}"

            elif action == "stop":
                if process_manager.get_status() != "OFFLINE":
                    await process_manager.stop_server()
                    result["message"] = "Servidor detenido"
                else:
                    result["message"] = "Servidor ya estaba apagado"

            elif action == "restart":
                await process_manager.restart_server()
                result["message"] = "Servidor reiniciado"

            elif action == "backup":
                cfg = settings.runtime_config
                scope = cfg.get("backup_scope", "full")
                targets = cfg.get("backup_targets", None)
                compression = cfg.get("backup_compression", True)
                stop_server = cfg.get("backup_stop_server", False)
                pre_cmd = (cfg.get("backup_pre_command") or "").strip()

                was_running = process_manager.get_status() != "OFFLINE"

                if was_running and pre_cmd:
                    await process_manager.send_command(pre_cmd)
                    await asyncio.sleep(2)

                if was_running and stop_server:
                    await process_manager.stop_server()
                    for _ in range(25):
                        await asyncio.sleep(1)
                        if process_manager.get_status() == "OFFLINE":
                            break
                    if process_manager.get_status() != "OFFLINE":
                        await process_manager.kill_server()
                        await asyncio.sleep(1)

                try:
                    backup_res = backup_manager.create_backup(
                        tag="auto",
                        scope=scope,
                        targets=targets,
                        compression=compression
                    )
                finally:
                    if was_running and stop_server:
                        await asyncio.sleep(1)
                        await process_manager.start_server()

                max_count = int(cfg.get("backup_max_count", 5) or 5)
                backup_manager.prune_auto_backups(max_count=max_count)
                result["message"] = f"Copia de seguridad generada ({scope}): {backup_res.get('filename')}"

            elif action == "command":
                cmd = task.get("command", "").strip()
                if cmd:
                    if process_manager.get_status() != "OFFLINE":
                        await process_manager.send_command(cmd)
                        result["message"] = f"Comando '{cmd}' enviado a la consola"
                    else:
                        result["message"] = f"Servidor fuera de línea, comando '{cmd}' omitido"
                else:
                    result["message"] = "Sin comando especificado"

            elif action == "check_updates":
                from app.core.downloader import downloader
                server_type = settings.runtime_config.get("server_type", "paper")
                # Trigger a check
                if server_type in ["paper", "folia", "velocity"]:
                    vers = await downloader.get_paper_versions(server_type)
                    latest = vers[-1] if vers else "desconocida"
                elif server_type == "purpur":
                    vers = await downloader.get_purpur_versions()
                    latest = vers[-1] if vers else "desconocida"
                else:
                    vers = await downloader.get_vanilla_versions()
                    latest = vers[0].get("id") if vers else "desconocida"
                result["message"] = f"Verificación de actualizaciones completada. Última versión detectada: {latest}"
                print(f"[Dockraft] {result['message']}")

            else:
                result["status"] = "error"
                result["message"] = f"Acción desconocida: {action}"

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Error ejecutando tarea '{task_name}': {str(e)}"
        # Record execution time and calculate next run
        now_str = self.now().strftime("%Y-%m-%d %H:%M:%S")
        for t in self.tasks:
            if t.get("id") == task.get("id"):
                t["last_run"] = now_str
                t["next_run"] = self.calculate_next_run(t)
                self.save_tasks()
                break

        # Dispatch webhook notification
        try:
            from app.core.webhook_manager import webhook_manager
            webhook_manager.dispatch(
                "task_executed",
                "🕒 Tarea Programada Ejecutada",
                f"La tarea **{task_name}** ({action}) ha concluido:\n{result.get('message', '')}",
                color=0x8957e5 if result.get("status") == "success" else 0xda3633
            )
        except Exception:
            pass

        return result

    async def run_task_now(self, task_id: str) -> Dict[str, Any]:
        for t in self.tasks:
            if t.get("id") == task_id:
                return await self.execute_task_action(t)
        raise ValueError(f"Tarea {task_id} no encontrada")

    async def scheduler_loop(self) -> None:
        """Continuous background loop checking for due scheduled tasks."""
        self._running = True
        print(f"[Dockraft] TaskScheduler iniciado en zona horaria: {os.getenv('TZ', 'America/Guayaquil')}")
        
        while self._running:
            try:
                await asyncio.sleep(10)
                if not process_manager.is_installed():
                    continue

                now_dt = self.now()
                tz = self.get_tz()

                for t in self.tasks:
                    if not t.get("enabled", True):
                        continue

                    # If next_run is missing or past due, check
                    next_run_str = t.get("next_run")
                    if not next_run_str:
                        t["next_run"] = self.calculate_next_run(t, from_dt=now_dt)
                        next_run_str = t.get("next_run")

                    if next_run_str:
                        try:
                            next_dt = datetime.strptime(next_run_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
                            if now_dt >= next_dt:
                                await self.execute_task_action(t)
                        except Exception as ex:
                            print(f"[Dockraft] Error al evaluar tarea {t.get('id')}: {ex}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Dockraft] Error en scheduler_loop: {e}")
                await asyncio.sleep(5)

    def start_loop(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self.scheduler_loop())

    def stop_loop(self) -> None:
        self._running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

task_scheduler = TaskScheduler()
