import os
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx

from app.config import settings
from app.core.fs_utils import atomic_write_json

DEFAULT_CONFIG: Dict[str, Any] = {
    "discord": {
        "enabled": False,
        "webhook_url": ""
    },
    "telegram": {
        "enabled": False,
        "bot_token": "",
        "chat_id": ""
    },
    "email": {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_use_tls": True,
        "from_email": "",
        "to_emails": ""
    },
    "events": {
        "server_start": True,
        "server_stop": True,
        "server_crash": True,
        "backup_created": True,
        "task_executed": True,
        "player_join": False,
        "player_leave": False
    }
}

class WebhookManager:
    def __init__(self):
        self.config_file: Path = settings.data_dir / "webhooks.json"
        self.config: Dict[str, Any] = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Loads webhook configuration from disk or returns defaults."""
        config = json.loads(json.dumps(DEFAULT_CONFIG))
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        for k, v in saved.items():
                            if k in config and isinstance(v, dict):
                                config[k].update(v)
                            else:
                                config[k] = v
            except Exception as e:
                print(f"[Dockraft] Error loading webhooks.json: {e}")
        return config

    def save_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Updates and persists webhook configuration to webhooks.json."""
        for section in ["discord", "telegram", "email", "events"]:
            if section in new_config and isinstance(new_config[section], dict):
                self.config[section].update(new_config[section])
        
        try:
            atomic_write_json(self.config_file, self.config, indent=2)
        except Exception as e:
            print(f"[Dockraft] Error saving webhooks.json: {e}")
            raise RuntimeError(f"Error saving webhook configuration: {e}")
            
        return self.config

    def _get_server_info(self) -> Dict[str, Any]:
        """Retrieves server name, type, version, and formatted label."""
        name = settings.runtime_config.get("server_name", "Mi Servidor Dockraft")
        stype = settings.runtime_config.get("server_type", "minecraft")
        sver = settings.runtime_config.get("server_version", "")
        
        type_clean = stype.capitalize() if stype else "Minecraft"
        label = f"{type_clean} {sver}".strip()
        
        return {
            "name": name,
            "type": stype,
            "version": sver,
            "label": label or "Minecraft"
        }

    def _get_server_name(self) -> str:
        return self._get_server_info()["name"]

    def _build_default_fields(self, event_type: str, color: int = 0x388bfd) -> List[Dict[str, Any]]:
        """Generates clean, 3-column inline metadata fields matching professional Discord/Telegram standards."""
        info = self._get_server_info()
        name = info["name"]
        label = info["label"]

        status_badge = "🟢 En Línea"
        if event_type == "server_stop":
            status_badge = "🛑 Detenido"
        elif event_type == "server_crash":
            status_badge = "⚠️ Crash"
        elif event_type == "backup_created":
            status_badge = "📦 Backup OK"
        elif event_type == "task_executed":
            status_badge = "✅ Éxito" if color != 0xda3633 else "❌ Error"
        elif event_type == "player_join":
            status_badge = "🟢 Conectado"
        elif event_type == "player_leave":
            status_badge = "⚪ Desconectado"
        elif event_type == "test":
            status_badge = "✅ Canal Activo"

        return [
            {"name": "🎮 Servidor", "value": f"`{name}`", "inline": True},
            {"name": "🗺️ Tipo / Versión", "value": f"`{label}`", "inline": True},
            {"name": "📊 Estado", "value": status_badge, "inline": True}
        ]

    # --- Channel Dispatchers ---

    async def send_discord(self, title: str, message: str, color: int = 0x388bfd, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Sends a rich, styled embed alert to Discord webhook matching gaming server standards."""
        cfg = self.config.get("discord", {})
        url = cfg.get("webhook_url", "").strip()
        if not url:
            raise ValueError("URL de Discord Webhook no configurada")

        info = self._get_server_info()
        server_name = info["name"]
        
        effective_fields = fields if fields is not None else self._build_default_fields("info", color)
        
        now_local = datetime.now()
        footer_time = now_local.strftime("%d/%m/%Y %H:%M")

        embed = {
            "title": title,
            "description": message,
            "color": color,
            "fields": effective_fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": f"Dockraft — Minecraft Server Manager • {footer_time}",
                "icon_url": "https://cdn-icons-png.flaticon.com/512/606/606545.png"
            }
        }

        # Use server name as bot username (Discord limit is 80 chars)
        bot_username = server_name[:80] if server_name else "Dockraft"
        payload = {
            "username": bot_username,
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/606/606545.png",
            "embeds": [embed]
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Discord API returned status {resp.status_code}: {resp.text}")

    async def send_telegram(self, title: str, message: str, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Sends a cleanly formatted HTML alert with badges and monospaced code blocks to Telegram Bot."""
        cfg = self.config.get("telegram", {})
        token = cfg.get("bot_token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()

        if not token or not chat_id:
            raise ValueError("Bot Token o Chat ID de Telegram no configurados")

        effective_fields = fields if fields is not None else self._build_default_fields("info")

        # Convert markdown **bold** to HTML <b>
        clean_msg = message
        while "**" in clean_msg:
            clean_msg = clean_msg.replace("**", "<b>", 1).replace("**", "</b>", 1)

        html_lines = [
            f"<b>{title}</b>",
            "",
            clean_msg,
            ""
        ]

        if effective_fields:
            for f in effective_fields:
                fname = f.get("name", "")
                fval = str(f.get("value", "")).replace("`", "")
                html_lines.append(f"{fname}: <code>{fval}</code>")
            html_lines.append("")

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        html_lines.append(f"<i>⏰ {now_str} • Dockraft Manager</i>")

        payload = {
            "chat_id": chat_id,
            "text": "\n".join(html_lines),
            "parse_mode": "HTML"
        }

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Telegram API returned status {resp.status_code}: {resp.text}")

    def _send_email_sync(self, subject: str, body: str, color: int = 0x388bfd, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Synchronous SMTP email sender rendering an ultra-sleek dark glassmorphism HTML email."""
        cfg = self.config.get("email", {})
        host = cfg.get("smtp_host", "").strip()
        port = int(cfg.get("smtp_port", 587) or 587)
        user = cfg.get("smtp_user", "").strip()
        pwd = cfg.get("smtp_password", "")
        use_tls = cfg.get("smtp_use_tls", True)
        from_email = cfg.get("from_email", "").strip() or user
        to_raw = cfg.get("to_emails", "").strip()

        if not host or not to_raw:
            raise ValueError("Host SMTP o destinatarios de correo no configurados")

        recipients = [e.strip() for e in to_raw.replace(";", ",").split(",") if e.strip()]
        if not recipients:
            raise ValueError("No hay destinatarios de correo válidos especificados")

        info = self._get_server_info()
        server_name = info["name"]
        effective_fields = fields if fields is not None else self._build_default_fields("info", color)

        color_hex = f"#{color:06x}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{server_name}] {subject}"
        msg["From"] = from_email
        msg["To"] = ", ".join(recipients)

        # Plain text fallback
        plain_lines = [
            f"=== {subject} ===",
            f"Servidor: {server_name}",
            f"Fecha: {now_str}",
            "",
            body.replace("**", ""),
            ""
        ]
        if effective_fields:
            plain_lines.append("Detalles:")
            for f in effective_fields:
                val = str(f.get("value", "")).replace("`", "")
                plain_lines.append(f"  • {f.get('name', '')}: {val}")
        plain_lines.append("\nDockraft — Minecraft Server Manager")
        body_plain = "\n".join(plain_lines)

        # HTML table rows for fields
        fields_rows = ""
        if effective_fields:
            for f in effective_fields:
                fname = f.get("name", "")
                fval = str(f.get("value", "")).replace("`", "")
                fields_rows += f"""
                <tr>
                  <td style="padding: 10px 16px; border-bottom: 1px solid #21262d; font-size: 13px; font-weight: 600; color: #8b949e; width: 38%;">
                    {fname}
                  </td>
                  <td style="padding: 10px 16px; border-bottom: 1px solid #21262d; font-size: 13px; color: #f0f6fc;">
                    <code style="background: rgba(110, 118, 129, 0.2); padding: 2px 7px; border-radius: 4px; font-family: monospace; font-size: 12px;">{fval}</code>
                  </td>
                </tr>
                """

        # Format body HTML
        body_html = body.replace("\n", "<br>")
        while "**" in body_html:
            body_html = body_html.replace("**", "<strong>", 1).replace("**", "</strong>", 1)

        fields_table_html = f"""
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0d1117; border: 1px solid #21262d; border-radius: 8px; margin-bottom: 10px; overflow: hidden;">
          {fields_rows}
        </table>
        """ if fields_rows else ""

        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 24px 12px; background-color: #0b0f17; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e6edf3; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 580px; margin: 0 auto; background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.5);">
    <!-- Brand Header -->
    <tr>
      <td style="padding: 18px 24px; background: linear-gradient(135deg, #1c2433 0%, #111622 100%); border-bottom: 1px solid #30363d;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td style="vertical-align: middle;">
              <span style="font-size: 13px; font-weight: 800; letter-spacing: 1.5px; color: #58a6ff; text-transform: uppercase;">DOCKRAFT</span>
              <span style="font-size: 11px; color: #8b949e; margin-left: 6px;">| Panel Minecraft</span>
            </td>
            <td style="text-align: right; vertical-align: middle;">
              <span style="display: inline-block; padding: 4px 10px; background: rgba(56, 139, 253, 0.15); border: 1px solid rgba(56, 139, 253, 0.3); border-radius: 12px; font-size: 11px; font-weight: 600; color: #58a6ff;">
                🎮 {server_name}
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Accent Color Top Bar -->
    <tr>
      <td style="height: 3px; background-color: {color_hex};"></td>
    </tr>

    <!-- Main Content Area -->
    <tr>
      <td style="padding: 24px 24px 20px 24px;">
        <h2 style="margin: 0 0 16px 0; color: #f0f6fc; font-size: 18px; font-weight: 700;">
          {subject}
        </h2>

        <!-- Message Body Callout -->
        <div style="background-color: #0d1117; border-left: 3px solid {color_hex}; border-radius: 4px; padding: 14px 16px; margin-bottom: 20px;">
          <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6; word-break: break-word;">
            {body_html}
          </p>
        </div>

        <!-- Metadata Table -->
        {fields_table_html}
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 14px 24px; background-color: #0d1117; border-top: 1px solid #21262d; text-align: center;">
        <p style="margin: 0; font-size: 11px; color: #8b949e; line-height: 1.5;">
          Notificación generada automáticamente por <strong>Dockraft</strong> para el servidor <em>{server_name}</em>.<br>
          <span style="color: #6e7681;">⏰ {now_str}</span>
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""

        msg.attach(MIMEText(body_plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if use_tls:
                server.starttls()

        try:
            if user and pwd:
                server.login(user, pwd)
            server.sendmail(from_email, recipients, msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass

    async def send_email(self, title: str, message: str, color: int = 0x388bfd, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Asynchronously sends email notification via thread pool."""
        await asyncio.to_thread(self._send_email_sync, title, message, color, fields)

    async def test_channel(self, channel: str) -> Dict[str, Any]:
        """Tests sending a test notification to a specific channel."""
        info = self._get_server_info()
        server_name = info["name"]
        server_label = info["label"]

        test_title = "🔔 Prueba de Notificación"
        test_message = f"¡Conexión verificada exitosamente! Las notificaciones automáticas de tu servidor **{server_name}** están activas y funcionando correctamente."
        test_fields = [
            {"name": "🎮 Servidor", "value": f"`{server_name}`", "inline": True},
            {"name": "📦 Tipo / Versión", "value": f"`{server_label}`", "inline": True},
            {"name": "📊 Estado", "value": "✅ Conectado OK", "inline": True}
        ]
        
        try:
            if channel == "discord":
                await self.send_discord(test_title, test_message, color=0x5865f2, fields=test_fields)
            elif channel == "telegram":
                await self.send_telegram(test_title, test_message, fields=test_fields)
            elif channel == "email":
                await self.send_email(test_title, test_message, color=0x5865f2, fields=test_fields)
            else:
                return {"status": "error", "message": f"Canal desconocido: '{channel}'"}
                
            return {"status": "success", "message": f"Notificación de prueba enviada a {channel.capitalize()} correctamente."}
        except Exception as e:
            return {"status": "error", "message": f"Error al enviar notificación a {channel}: {str(e)}"}

    def dispatch(self, event_type: str, title: str, message: str, color: int = 0x388bfd, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Dispatches event notifications asynchronously to all configured and enabled channels."""
        events_cfg = self.config.get("events", {})
        if not events_cfg.get(event_type, True):
            return  # Event is disabled by user

        # Ensure fields are populated if not provided
        effective_fields = fields if fields is not None else self._build_default_fields(event_type, color)

        # Run non-blocking in active event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_dispatch_all(title, message, color, effective_fields))
        except RuntimeError:
            try:
                asyncio.run(self._async_dispatch_all(title, message, color, effective_fields))
            except Exception as e:
                print(f"[Dockraft Webhooks] Could not dispatch event '{event_type}': {e}")

    async def _async_dispatch_all(self, title: str, message: str, color: int, fields: Optional[List[Dict[str, Any]]]) -> None:
        """Internal worker sending alerts to all enabled channels."""
        tasks = []

        if self.config.get("discord", {}).get("enabled"):
            tasks.append(self._safe_call(self.send_discord(title, message, color, fields), "Discord"))

        if self.config.get("telegram", {}).get("enabled"):
            tasks.append(self._safe_call(self.send_telegram(title, message, fields), "Telegram"))

        if self.config.get("email", {}).get("enabled"):
            tasks.append(self._safe_call(self.send_email(title, message, color, fields), "Email"))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, coro, name: str) -> None:
        try:
            await coro
        except Exception as e:
            print(f"[Dockraft Webhooks] Failed to send to {name}: {e}")

webhook_manager = WebhookManager()
