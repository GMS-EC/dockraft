import re
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx
from app.config import settings

class DiagnosticManager:
    def __init__(self):
        self.mclogs_api_url = "https://api.mclogs.com/1/log"

    def _parse_crash_timestamp(self, path: Path) -> float:
        """Extracts creation timestamp from filename, file header, or mtime."""
        # Try filename first: crash-YYYY-MM-DD_HH.mm.ss-server.txt
        m = re.search(r'crash-(\d{4})-(\d{2})-(\d{2})_(\d{2})\.(\d{2})\.(\d{2})', path.name)
        if m:
            try:
                from datetime import datetime
                year, month, day, hour, minute, second = map(int, m.groups())
                dt = datetime(year, month, day, hour, minute, second)
                return dt.timestamp()
            except Exception:
                pass

        # Try reading first lines of file for "Time: YYYY-MM-DD HH:MM:SS"
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                header = [f.readline() for _ in range(10)]
                for line in header:
                    m_time = re.search(r'Time:\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})', line)
                    if m_time:
                        from datetime import datetime
                        year, month, day, hour, minute, second = map(int, m_time.groups())
                        return datetime(year, month, day, hour, minute, second).timestamp()
        except Exception:
            pass

        # Fallback to file mtime
        return path.stat().st_mtime

    def get_latest_crash_report(
        self,
        since_timestamp: Optional[float] = None,
        max_age_seconds: Optional[int] = 1800
    ) -> Optional[Dict[str, Any]]:
        """Finds and returns the content of the most recent crash report in crash-reports/."""
        crash_dir = settings.data_dir / "crash-reports"
        if not crash_dir.exists():
            return None

        crash_files = [f for f in crash_dir.iterdir() if f.is_file() and f.name.endswith(".txt")]
        if not crash_files:
            return None

        reports = []
        for f in crash_files:
            ts = self._parse_crash_timestamp(f)
            reports.append((ts, f))

        # Sort descending by parsed timestamp
        reports.sort(key=lambda x: x[0], reverse=True)
        latest_ts, latest_file = reports[0]

        now = time.time()
        # If since_timestamp provided, crash must have occurred during or after that start time
        if since_timestamp is not None:
            if latest_ts < (since_timestamp - 10.0):
                return None
        elif max_age_seconds is not None:
            if (now - latest_ts) > max_age_seconds:
                return None

        try:
            content = latest_file.read_text(encoding="utf-8", errors="replace")
            return {
                "filename": latest_file.name,
                "timestamp": latest_ts,
                "content": content
            }
        except Exception:
            return None

    def get_recent_log_tail(self, max_lines: int = 300) -> str:
        """Returns the last N lines of latest.log."""
        log_file = settings.data_dir / "logs" / "latest.log"
        if not log_file.exists():
            return ""

        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        except Exception:
            return ""

    def analyze_diagnostics(
        self,
        since_timestamp: Optional[float] = None,
        exit_code: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Analyzes recent logs and crash reports to identify the root cause
        of crashes or errors with actionable advice.
        """
        max_age = 1800 if since_timestamp is None else None
        crash = self.get_latest_crash_report(since_timestamp=since_timestamp, max_age_seconds=max_age)
        log_tail = self.get_recent_log_tail(300)

        is_crash_report = False
        text_to_analyze = ""
        source_name = "latest.log"

        if crash:
            text_to_analyze = crash["content"]
            source_name = f"crash-reports/{crash['filename']}"
            is_crash_report = True
        else:
            text_to_analyze = log_tail

        if not text_to_analyze.strip():
            # If server terminated with SIGKILL (-9 / 137) and log is empty
            if exit_code in (-9, 137):
                return {
                    "has_issue": True,
                    "severity": "critical",
                    "category": "system",
                    "title": f"Terminación Forzosa por el Sistema (Código {exit_code})",
                    "cause": f"El proceso fue detenido mediante señal SIGKILL ({exit_code}). Esto suele ocurrir cuando el host o Docker agota la memoria RAM física (OOM Killer) o si el proceso no respondió a tiempo a la orden de apagado.",
                    "recommendation": "Verifica los recursos de memoria RAM de la máquina anfitriona y asignados en docker-compose.yml. Si detuviste el servidor manualmente, este aviso es informativo del cierre forzado tras expirar el tiempo de espera.",
                    "source": "Process Supervisor",
                    "excerpt": f"Process terminated with exit code {exit_code} (SIGKILL)."
                }

            return {
                "has_issue": False,
                "title": "Sin registros de errores",
                "message": "No se encontraron reportes de caída recientes ni registros de errores críticos.",
                "source": None,
                "recommendation": "El servidor parece estar funcionando normalmente.",
                "excerpt": ""
            }

        # 1. Out of Memory
        if re.search(r'(OutOfMemoryError|Java heap space|GC overhead limit exceeded)', text_to_analyze, re.IGNORECASE):
            return {
                "has_issue": True,
                "severity": "critical",
                "category": "memory",
                "title": "Falta de Memoria RAM (OutOfMemoryError)",
                "cause": "El proceso del servidor agotó la memoria heap máxima asignada en Java (-Xmx).",
                "recommendation": "Aumenta la memoria RAM en la pestaña Ajustes > Asignación de Recursos (por ejemplo a 3G o 4G), o reduce la distancia de simulación y renderizado en server.properties.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'OutOfMemoryError|Java heap space')
            }

        # 2. Incompatible Java Version
        if re.search(r'(UnsupportedClassVersionError|has been compiled by a more recent version of the Java Runtime)', text_to_analyze):
            m_ver = re.search(r'class file version (\d+)', text_to_analyze)
            req_ver = "más reciente"
            if m_ver:
                ver_code = int(m_ver.group(1))
                if ver_code == 65:
                    req_ver = "Java 21"
                elif ver_code == 69:
                    req_ver = "Java 25"
                elif ver_code == 61:
                    req_ver = "Java 17"

            return {
                "has_issue": True,
                "severity": "critical",
                "category": "java",
                "title": "Incompatibilidad de Versión de Java",
                "cause": f"El servidor o uno de sus plugins requiere {req_ver} para poder ejecutarse.",
                "recommendation": f"Ve a la pestaña Ajustes > Entorno Java y selecciona una versión compatible ({req_ver}). Dockraft incluye Java 17, 21 y 25.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'UnsupportedClassVersionError')
            }

        # 3. Port Already in Use (BindException)
        if re.search(r'(BindException|Address already in use|FAILED TO BIND TO PORT)', text_to_analyze, re.IGNORECASE):
            return {
                "has_issue": True,
                "severity": "critical",
                "category": "network",
                "title": "Puerto de Red Ocupado (Address already in use)",
                "cause": "El puerto 25565 (o el puerto configurado) ya está siendo utilizado por otro proceso o contenedor en la misma máquina.",
                "recommendation": "Asegúrate de que no haya otro servidor de Minecraft o contenedor ejecutándose en el mismo puerto, o cambia el puerto en docker-compose.yml / server.properties.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'BindException|FAILED TO BIND TO PORT')
            }

        # 4. Incompatible Plugin / Missing Class (NoClassDefFoundError / ClassNotFoundException)
        m_noclass = re.search(r'(?:NoClassDefFoundError|ClassNotFoundException):\s*(?:Could not initialize class\s+)?([a-zA-Z0-9_\.\$]+)', text_to_analyze)
        if m_noclass:
            missing_class = m_noclass.group(1).strip()
            class_short = missing_class.split('.')[-1]
            return {
                "has_issue": True,
                "severity": "critical" if is_crash_report else "warning",
                "category": "plugin",
                "title": f"Incompatibilidad de Plugin (Clase no encontrada: {class_short})",
                "cause": f"Un plugin intentó cargar la clase '{missing_class}', la cual no existe o fue removida en esta versión de Paper/Minecraft o le falta una dependencia requerida.",
                "recommendation": f"Revisa los plugins que hacen referencia a '{class_short}'. Si actualizaste Paper recientemente, actualiza esos plugins a su versión compatible o desactívalos temporalmente en la pestaña Archivos.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'NoClassDefFoundError|ClassNotFoundException|Caused by')
            }

        # 5. Plugin / Mod Crash
        m_plugin = re.search(r"(?:Could not load 'plugins/|Plugin `([a-zA-Z0-9_\-]+)` has failed|InvalidPluginException:.*?(?:Plugin|plugins/)([a-zA-Z0-9_\-]+)|Error occurred while enabling ([a-zA-Z0-9_\-]+))", text_to_analyze)
        if m_plugin:
            plugin_name = next((g for g in m_plugin.groups() if g), None)
            return {
                "has_issue": True,
                "severity": "warning",
                "category": "plugin",
                "title": f"Fallo Crítico provocado por Plugin '{plugin_name}'" if plugin_name else "Fallo en Carga de Plugin",
                "cause": f"El plugin {plugin_name or 'instalado'} provocó una excepción no controlada o le falta una dependencia requerida (ej. Vault, ProtocolLib).",
                "recommendation": f"Verifica si {plugin_name or 'el plugin'} tiene una versión más nueva compatible con tu versión de Minecraft, o desactívalo renombrándolo a '.disabled' en la pestaña Archivos.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'Exception|Error|Caused by')
            }

        # 6. Server Tick Loop Exception
        if "Exception in server tick loop" in text_to_analyze:
            return {
                "has_issue": True,
                "severity": "critical",
                "category": "tick_loop",
                "title": "Fallo Crítico en Bucle de Ticks del Servidor",
                "cause": "Una excepción interna detuvo el bucle de procesamiento principal del servidor.",
                "recommendation": "Revisa las trazas del error para comprobar la compatibilidad de plugins o entidades corruptas en el mundo.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'Exception in server tick loop|Caused by')
            }

        # 7. EULA not accepted
        if re.search(r'You need to agree to the EULA', text_to_analyze, re.IGNORECASE):
            return {
                "has_issue": True,
                "severity": "critical",
                "category": "eula",
                "title": "Acuerdo de Licencia (EULA) no Aceptado",
                "cause": "El servidor requiere que el archivo eula.txt contenga eula=true para iniciar.",
                "recommendation": "En la pestaña Archivos edita eula.txt y asegúrate de que diga eula=true, o presiona Guardar en Ajustes.",
                "source": source_name,
                "excerpt": "You need to agree to the EULA in order to run the server."
            }

        # 8. SIGKILL / Forced system exit without specific log exception
        if exit_code in (-9, 137):
            return {
                "has_issue": True,
                "severity": "critical",
                "category": "system",
                "title": f"Terminación Forzosa por el Sistema (Código {exit_code})",
                "cause": f"El proceso fue detenido mediante señal SIGKILL ({exit_code}). Esto ocurre comúnmente si Docker/host agotó la memoria física (Linux OOM Killer) o si el proceso no respondió a tiempo a la orden de apagado.",
                "recommendation": "Verifica los recursos de memoria RAM del host y los límites asignados al contenedor en docker-compose.yml.",
                "source": "Process Supervisor",
                "excerpt": f"Process terminated with exit code {exit_code} (SIGKILL)."
            }

        # 9. Generic Exception / Warning in logs
        m_err = re.search(r'((?:FATAL|ERROR).*?\n(?:.*?\tat .*?\n){1,5})', text_to_analyze)
        if m_err:
            return {
                "has_issue": True,
                "severity": "warning",
                "category": "general",
                "title": "Advertencia o Error Detectado en Registros",
                "cause": "Se detectó una excepción en los registros de ejecución del servidor.",
                "recommendation": "Puedes usar el botón 'Compartir Registro Sanitizado' para obtener un enlace seguro y compartirlo en foros o Discord.",
                "source": source_name,
                "excerpt": m_err.group(1).strip()
            }

        return {
            "has_issue": False,
            "title": "Sin problemas detectados",
            "message": "Los registros no muestran caídas recientes ni errores fatales.",
            "source": source_name,
            "recommendation": "Todo parece operar en orden.",
            "excerpt": ""
        }

    def _extract_relevant_excerpt(self, text: str, pattern: str, max_lines: int = 12) -> str:
        """Extracts lines surrounding the matched pattern."""
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, idx - 2)
                end = min(len(lines), idx + max_lines)
                return "\n".join(lines[start:end])
        return "\n".join(lines[-max_lines:])

    async def share_to_mclogs(self, custom_content: Optional[str] = None) -> Dict[str, Any]:
        """
        Uploads log to mclo.gs (paste service for Minecraft server logs with automatic sanitization).
        Returns {"success": True, "url": "https://mclo.gs/...", "raw": "..."}
        """
        content = custom_content
        if not content:
            # Prefer full latest.log or tail of it (up to 25,000 lines or 8 MB)
            log_file = settings.data_dir / "logs" / "latest.log"
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                        content = "".join(lines[-5000:])
                except Exception as e:
                    return {"success": False, "error": f"No se pudo leer latest.log: {str(e)}"}
            else:
                crash = self.get_latest_crash_report()
                if crash:
                    content = crash["content"]
                else:
                    return {"success": False, "error": "No hay registros disponibles para compartir."}

        if not content or not content.strip():
            return {"success": False, "error": "El registro está vacío."}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    self.mclogs_api_url,
                    data={"content": content}
                )
                if resp.status_code != 200:
                    return {"success": False, "error": f"mclo.gs respondió con código {resp.status_code}"}

                data = resp.json()
                if data.get("success"):
                    return {
                        "success": True,
                        "id": data.get("id"),
                        "url": data.get("url"),
                        "raw": data.get("raw")
                    }
                else:
                    return {"success": False, "error": data.get("error", "Error desconocido de mclo.gs")}
        except Exception as ex:
            return {"success": False, "error": f"Fallo de conexión con mclo.gs: {str(ex)}"}

diagnostic_manager = DiagnosticManager()
