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

    def get_latest_crash_report(self) -> Optional[Dict[str, Any]]:
        """Finds and returns the content of the most recent crash report in crash-reports/."""
        crash_dir = settings.data_dir / "crash-reports"
        if not crash_dir.exists():
            return None

        crash_files = [f for f in crash_dir.iterdir() if f.is_file() and f.name.endswith(".txt")]
        if not crash_files:
            return None

        # Sort by mtime descending
        crash_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest = crash_files[0]

        try:
            content = latest.read_text(encoding="utf-8", errors="replace")
            return {
                "filename": latest.name,
                "timestamp": latest.stat().st_mtime,
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

    def analyze_diagnostics(self) -> Dict[str, Any]:
        """
        Analyzes recent logs and crash reports to identify the root cause
        of crashes or errors with actionable advice.
        """
        crash = self.get_latest_crash_report()
        log_tail = self.get_recent_log_tail(300)

        # Prefer crash report if recent (within 24 hours)
        is_crash_report = False
        text_to_analyze = ""
        source_name = "latest.log"

        if crash and (time.time() - crash["timestamp"] < 86400):
            text_to_analyze = crash["content"]
            source_name = f"crash-reports/{crash['filename']}"
            is_crash_report = True
        else:
            text_to_analyze = log_tail

        if not text_to_analyze.strip():
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

        # 4. Plugin / Mod Crash
        m_plugin = re.search(r"(?:Could not load 'plugins/|Plugin `([a-zA-Z0-9_\-]+)` has failed|InvalidPluginException:.*?(?:Plugin|plugins/)([a-zA-Z0-9_\-]+)|Error occurred while enabling ([a-zA-Z0-9_\-]+))", text_to_analyze)
        if m_plugin or "Exception in server tick loop" in text_to_analyze:
            plugin_name = next((g for g in m_plugin.groups() if g), None) if m_plugin else None
            title = f"Fallo Crítico provocado por Plugin '{plugin_name}'" if plugin_name else "Fallo Crítico en Bucle de Ticks del Servidor"
            return {
                "has_issue": True,
                "severity": "warning" if plugin_name else "critical",
                "category": "plugin",
                "title": title,
                "cause": f"El plugin {plugin_name or 'un plugin instalado'} provocó una excepción no controlada o le falta una dependencia requerida (ej. Vault, ProtocolLib)." if plugin_name else "Una excepción interna detuvo el bucle de procesamiento del servidor.",
                "recommendation": f"Verifica si {plugin_name or 'el plugin'} tiene una versión más nueva compatible con tu versión de Minecraft, o desactívalo renombrándolo a '.disabled' en la pestaña Archivos." if plugin_name else "Revisa las trazas del error y comprueba la compatibilidad de plugins.",
                "source": source_name,
                "excerpt": self._extract_relevant_excerpt(text_to_analyze, r'Exception|Error|Caused by')
            }

        # 5. EULA not accepted
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

        # 6. Generic Exception / Warning
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
