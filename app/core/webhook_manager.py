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

    def _get_server_name(self) -> str:
        return settings.runtime_config.get("server_name", "Mi Servidor Dockraft")

    # --- Channel Dispatchers ---

    async def send_discord(self, title: str, message: str, color: int = 0x388bfd, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Sends an embed alert to Discord webhook."""
        cfg = self.config.get("discord", {})
        url = cfg.get("webhook_url", "").strip()
        if not url:
            raise ValueError("URL de Discord Webhook no configurada")

        server_name = self._get_server_name()
        embed = {
            "title": f"[{server_name}] {title}",
            "description": message,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {
                "text": f"Dockraft • {server_name}"
            }
        }
        if fields:
            embed["fields"] = fields

        payload = {
            "username": f"Dockraft ({server_name})",
            "embeds": [embed]
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Discord API returned status {resp.status_code}: {resp.text}")

    async def send_telegram(self, title: str, message: str, fields: Optional[List[Dict[str, Any]]] = None) -> None:
        """Sends an HTML alert to Telegram Bot."""
        cfg = self.config.get("telegram", {})
        token = cfg.get("bot_token", "").strip()
        chat_id = cfg.get("chat_id", "").strip()

        if not token or not chat_id:
            raise ValueError("Bot Token o Chat ID de Telegram no configurados")

        server_name = self._get_server_name()
        html_text = f"<b>[{server_name}] {title}</b>\n\n{message}"
        if fields:
            for f in fields:
                html_text += f"\n• <b>{f.get('name')}:</b> {f.get('value')}"

        payload = {
            "chat_id": chat_id,
            "text": html_text,
            "parse_mode": "HTML"
        }

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Telegram API returned status {resp.status_code}: {resp.text}")

    def _send_email_sync(self, subject: str, body: str) -> None:
        """Synchronous SMTP email sender meant to run in a thread pool."""
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

        server_name = self._get_server_name()
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{server_name}] {subject}"
        msg["From"] = from_email
        msg["To"] = ", ".join(recipients)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
</head>
<body style="margin:0; padding:20px; background-color:#0d1117; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color:#c9d1d9;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:560px; margin:0 auto; background-color:#161b22; border:1px solid #30363d; border-radius:8px; overflow:hidden;">
    <tr>
      <td style="padding:20px 24px; background:linear-gradient(135deg, #1f2937, #111827); border-bottom:1px solid #30363d;">
        <h2 style="margin:0; color:#58a6ff; font-size:18px;">🔔 Notificación de {server_name}</h2>
      </td>
    </tr>
    <tr>
      <td style="padding:24px;">
        <h3 style="margin-top:0; color:#f0f6fc; font-size:16px;">{subject}</h3>
        <p style="color:#8b949e; font-size:14px; line-height:1.6; margin:16px 0;">{body}</p>
        <div style="margin-top:20px; padding:12px; background:#0d1117; border-radius:6px; font-size:12px; color:#8b949e;">
          Fecha del Servidor: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
      </td>
    </tr>
    <tr>
      <td style="padding:14px 24px; background-color:#090d13; font-size:11px; color:#6e7681; text-align:center;">
        Generado automáticamente por tu panel Dockraft.
      </td>
    </tr>
  </table>
</body>
</html>"""

        msg.attach(MIMEText(body, "plain", "utf-8"))
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

    async def send_email(self, title: str, message: str) -> None:
        """Asynchronously sends email notification via thread pool."""
        await asyncio.to_thread(self._send_email_sync, title, message)

    async def test_channel(self, channel: str) -> Dict[str, Any]:
        """Tests sending a test notification to a specific channel."""
        test_title = "🔔 Prueba de Notificación"
        test_message = f"¡Hola! Esta es una prueba exitosa del canal {channel.upper()} enviada desde tu panel Dockraft."
        
        try:
            if channel == "discord":
                await self.send_discord(test_title, test_message, color=0x5865f2)
            elif channel == "telegram":
                await self.send_telegram(test_title, test_message)
            elif channel == "email":
                await self.send_email(test_title, test_message)
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

        # Run non-blocking in active event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_dispatch_all(title, message, color, fields))
        except RuntimeError:
            # If no running loop (e.g., synchronous thread), schedule using new loop or ignore
            try:
                asyncio.run(self._async_dispatch_all(title, message, color, fields))
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
            tasks.append(self._safe_call(self.send_email(title, message), "Email"))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, coro, name: str) -> None:
        try:
            await coro
        except Exception as e:
            print(f"[Dockraft Webhooks] Failed to send to {name}: {e}")

webhook_manager = WebhookManager()
