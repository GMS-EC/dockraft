"""
Dockraft Desktop Launcher (Windows & Linux AppImage).

Provides:
- Unified background tray app with 5 actions:
  1. Instancias (Tkinter Instance Manager with 1-click Web auto-fill, Files & Port Editor)
  2. Nueva instancia (Tkinter wizard with first-time-only root folder picker & live port validation)
  3. Editar configuraciones (Tkinter global & .env configuration editor)
  4. Acerca de (Credits, GPLv3 license & GitHub update checker)
  5. Salir (closes the app and all running Dockraft instances)
"""
import argparse
import asyncio
import base64
import ctypes
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any


_UI_LANG_OVERRIDE: str | None = None
_ACTIVE_MAIN_ROOT: Path | None = None


def _default_main_root() -> Path:
    return (Path.home() / "Dockraft").resolve()


def _root_pointer_candidates() -> list[Path]:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        try:
            candidates.append((Path(sys.executable).resolve().parent / ".dockraft_root").resolve())
        except Exception:
            pass
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        candidates.append((Path(base) / "Dockraft" / ".dockraft_root").resolve())
    else:
        xdg = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        candidates.append((Path(xdg) / "dockraft" / ".dockraft_root").resolve())
    return candidates


def _resolve_main_root() -> Path:
    global _ACTIVE_MAIN_ROOT
    if _ACTIVE_MAIN_ROOT is not None and _ACTIVE_MAIN_ROOT.is_dir():
        return _ACTIVE_MAIN_ROOT
    for ptr in _root_pointer_candidates():
        if ptr.is_file():
            try:
                raw = ptr.read_text(encoding="utf-8").strip()
                if raw:
                    custom = Path(raw).expanduser().resolve()
                    if (custom / "launcher_config.json").is_file() or (custom / "instancias").is_dir():
                        _ACTIVE_MAIN_ROOT = custom
                        return custom
                    try:
                        ptr.unlink(missing_ok=True)
                    except Exception:
                        pass
            except Exception:
                pass
    return _default_main_root()


def _set_main_root(main_root: Path) -> Path:
    global _ACTIVE_MAIN_ROOT
    resolved = main_root.expanduser().resolve()
    if resolved.name.lower() == "instancias":
        resolved = resolved.parent.resolve()
    old_cfg_path = _launcher_config_path()
    _ACTIVE_MAIN_ROOT = resolved
    default_root = _default_main_root()
    is_default = (
        str(resolved).lower() == str(default_root).lower()
        if sys.platform == "win32"
        else resolved == default_root
    )
    for ptr in _root_pointer_candidates():
        if is_default:
            try:
                ptr.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            try:
                ptr.parent.mkdir(parents=True, exist_ok=True)
                ptr.write_text(str(resolved), encoding="utf-8")
                break
            except Exception:
                continue
    new_cfg_path = (resolved / "launcher_config.json").resolve()
    if old_cfg_path != new_cfg_path and old_cfg_path.is_file():
        try:
            resolved.mkdir(parents=True, exist_ok=True)
            if not new_cfg_path.is_file():
                shutil.move(str(old_cfg_path), str(new_cfg_path))
            else:
                old_cfg_path.unlink(missing_ok=True)
        except Exception:
            pass
    return resolved


def _launcher_config_path() -> Path:
    return (_resolve_main_root() / "launcher_config.json").resolve()


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Reads all KEY=VALUE pairs from an instance .env file."""
    res: dict[str, str] = {}
    if not env_path.is_file():
        return res
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                res[k] = v
    except Exception:
        pass
    return res


def _read_env_credentials(env_path: Path) -> tuple[str, str]:
    """Reads ADMIN_USER and ADMIN_PASSWORD from an existing .env file if present."""
    env_map = _parse_env_file(env_path)
    return env_map.get("ADMIN_USER", ""), env_map.get("ADMIN_PASSWORD", "")


def _update_env_file(env_path: Path, updates: dict[str, str]) -> None:
    """Updates or appends KEY=VALUE pairs in env_path while preserving comments and other keys."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    seen: set[str] = set()
    if env_path.is_file():
        try:
            lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            lines = []
    new_lines: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        new_lines.append(raw)
    if not new_lines:
        new_lines.append("# Dockraft Instance Configuration")
    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _update_mc_server_port(instance_dir: Path, mc_port: int) -> None:
    """Updates server-port in data/server.properties if the file exists."""
    prop_path = instance_dir / "data" / "server.properties"
    if not prop_path.is_file():
        return
    try:
        text = prop_path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?m)^server-port\s*=", text):
            text = re.sub(r"(?m)^server-port\s*=.*$", f"server-port={mc_port}", text)
        else:
            text = text.rstrip("\r\n") + f"\nserver-port={mc_port}\n"
        prop_path.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _load_launcher_config() -> dict:
    cfg_path = _launcher_config_path()
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw_list = data.get("instances", [])
                if isinstance(raw_list, list):
                    valid = [
                        i for i in raw_list
                        if isinstance(i, dict) and i.get("dir") and Path(str(i["dir"])).is_dir()
                    ]
                    if len(valid) != len(raw_list):
                        data["instances"] = valid
                        if data.get("last_instance") and not Path(str(data["last_instance"])).is_dir():
                            data["last_instance"] = valid[0]["dir"] if valid else ""
                        try:
                            cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                        except Exception:
                            pass
                return data
        except Exception:
            pass
    return {"last_instance": "", "instances": []}


def _default_instances_root() -> Path:
    cfg = _load_launcher_config()
    saved_root = str(cfg.get("instances_root", "")).strip()
    if saved_root:
        p = Path(saved_root).resolve()
        return p if p.name.lower() == "instancias" else (p / "instancias").resolve()
    return (_resolve_main_root() / "instancias").resolve()


def _main_root_dir() -> Path:
    """Returns the top-level main folder (<Carpeta-principal>) containing 'instancias' and 'backups'."""
    inst_root = _default_instances_root()
    return inst_root.parent if inst_root.name.lower() == "instancias" else inst_root


def _instance_backups_dir(instance_dir: Path) -> Path:
    """
    Returns <Carpeta-principal>/backups/backup-<nombre-instancia> outside 'instancias'
    so deleting an instance preserves its backups.
    """
    inst = instance_dir.resolve()
    main_root = inst.parent.parent if inst.parent.name.lower() == "instancias" else inst.parent
    return (main_root / "backups" / f"backup-{inst.name}").resolve()


def _migrate_legacy_backups(instance_dir: Path, backups_dir: Path) -> None:
    """Moves any legacy backups from <instancia>/backups into <Carpeta-principal>/backups/backup-<instancia>."""
    try:
        backups_dir.mkdir(parents=True, exist_ok=True)
        legacy_dir = instance_dir.resolve() / "backups"
        if legacy_dir.is_dir() and legacy_dir.resolve() != backups_dir.resolve():
            for item in legacy_dir.iterdir():
                dest = backups_dir / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            if not any(legacy_dir.iterdir()):
                legacy_dir.rmdir()
    except Exception:
        pass


def _discover_all_instances() -> list[dict]:
    """Discovers instances from launcher_config.json and scans instances_root subdirectories."""
    cfg = _load_launcher_config()
    by_dir: dict[str, dict] = {}
    ordered_dirs: list[str] = []

    def _inspect_dir(inst_dir: Path, fallback_entry: dict | None = None) -> dict | None:
        if not inst_dir.is_dir():
            return None
        env_map = _parse_env_file(inst_dir / ".env")
        fb = fallback_entry or {}
        if not env_map and not (inst_dir / "data").is_dir() and not fb:
            return None
        name = env_map.get("SERVER_NAME") or str(fb.get("name") or "").strip() or inst_dir.name
        port_str = env_map.get("PORT") or str(fb.get("port") or "8000")
        mc_str = env_map.get("MC_PORT") or str(fb.get("mc_port") or "25565")
        port = int(port_str) if str(port_str).isdigit() else 8000
        mc_port = int(mc_str) if str(mc_str).isdigit() else 25565
        host = env_map.get("HOST") or str(fb.get("host") or "127.0.0.1")
        return {
            "name": name,
            "dir": str(inst_dir.resolve()),
            "port": port,
            "mc_port": mc_port,
            "host": host,
        }

    for entry in cfg.get("instances", []):
        if isinstance(entry, dict) and entry.get("dir"):
            p = Path(str(entry["dir"]))
            info = _inspect_dir(p, entry)
            if info:
                d_key = info["dir"].lower() if sys.platform == "win32" else info["dir"]
                if d_key not in by_dir:
                    by_dir[d_key] = info
                    ordered_dirs.append(d_key)

    root_dir = _default_instances_root()
    if root_dir.is_dir():
        try:
            for sub in sorted(root_dir.iterdir(), key=lambda x: x.name.lower()):
                if sub.is_dir() and not sub.name.startswith("."):
                    info = _inspect_dir(sub)
                    if info:
                        d_key = info["dir"].lower() if sys.platform == "win32" else info["dir"]
                        if d_key not in by_dir:
                            by_dir[d_key] = info
                            ordered_dirs.append(d_key)
        except Exception:
            pass

    result = [by_dir[k] for k in ordered_dirs]
    if result != cfg.get("instances", []):
        try:
            cfg["instances"] = result[:25]
            if not cfg.get("last_instance") and result:
                cfg["last_instance"] = result[0]["dir"]
            cfg_path = _launcher_config_path()
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return result


def _ensure_stdio(instance_dir: Path) -> None:
    """Redirects None stdout/stderr when packaged with console=False or run without a terminal."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        state_dir = instance_dir / ".dockraft_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        log_f = open(state_dir / "panel.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        log_f = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log_f
    if sys.stderr is None:
        sys.stderr = log_f


def _slugify_name(name: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in str(name or "").strip().lower())
    clean = "-".join(part for part in clean.split("-") if part)
    return clean or "default"


def _save_launcher_config(
    instance_dir: Path,
    port: int,
    mc_port: int = 25565,
    name: str = "",
    instances_root: Path | None = None,
    default_user: str = "",
    default_password: str = "",
    default_host: str = "",
    session_timeout: int | None = None,
) -> None:
    if instances_root is not None:
        _set_main_root(instances_root)
    cfg = _load_launcher_config()
    cfg_path = _launcher_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    inst_str = str(instance_dir.resolve())
    inst_name = name.strip() or instance_dir.name
    cfg["last_instance"] = inst_str
    if instances_root is not None:
        cfg["instances_root"] = str(instances_root.resolve())
    elif not cfg.get("instances_root"):
        cfg["instances_root"] = str(instance_dir.resolve().parent)
    if default_user.strip():
        cfg["default_admin_user"] = default_user.strip()
    if default_password.strip():
        cfg["default_admin_password"] = default_password.strip()
    if default_host.strip():
        cfg["default_host"] = default_host.strip()
    if session_timeout is not None:
        cfg["session_timeout_minutes"] = int(session_timeout)

    def _norm(p_str: str) -> str:
        return p_str.lower() if sys.platform == "win32" else p_str

    instances = [
        i for i in cfg.get("instances", [])
        if isinstance(i, dict) and _norm(str(i.get("dir", ""))) != _norm(inst_str)
    ]
    instances.insert(0, {"name": inst_name, "dir": inst_str, "port": port, "mc_port": mc_port})
    cfg["instances"] = instances[:25]
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _get_ui_lang() -> str:
    """Returns current UI language code ('es' or 'en') from memory override or launcher_config.json."""
    if _UI_LANG_OVERRIDE in ("es", "en"):
        return _UI_LANG_OVERRIDE
    cfg = _load_launcher_config()
    lang = str(cfg.get("language") or "").strip().lower()
    if lang in ("es", "en"):
        return lang
    env_lang = (os.getenv("DOCKRAFT_LANG") or "").strip().lower()
    if env_lang.startswith("en"):
        return "en"
    return "es"


def _set_ui_lang(lang: str) -> str:
    """Persists UI language ('es' or 'en') in memory and in launcher_config.json if already initialized."""
    global _UI_LANG_OVERRIDE
    norm = "en" if str(lang or "").strip().lower().startswith("en") else "es"
    _UI_LANG_OVERRIDE = norm
    cfg_path = _launcher_config_path()
    if cfg_path.is_file():
        cfg = _load_launcher_config()
        cfg["language"] = norm
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return norm


def _tr(es: str, en: str) -> str:
    """Returns the localized string according to the active desktop UI language ('es' or 'en')."""
    return en if _get_ui_lang() == "en" else es


def _get_app_version() -> str:
    env_ver = (os.getenv("DOCKRAFT_VERSION") or os.getenv("APP_VERSION") or "").strip()
    if env_ver:
        return env_ver.lstrip("vV")
    chg = _find_asset("CHANGELOG.md")
    if chg and chg.is_file():
        try:
            for line in chg.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^##\s+\[(\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?)\]", line.strip())
                if m:
                    return m.group(1)
        except Exception:
            pass
    ver_file = _find_asset("VERSION")
    if ver_file and ver_file.is_file():
        try:
            v = ver_file.read_text(encoding="utf-8").strip()
            if v:
                return v.lstrip("vV")
        except Exception:
            pass
    return "1.6.0"


def _stop_instance(instance_dir: Path, port: int = 0) -> tuple[bool, str]:
    """
    Stops a single Dockraft instance (both its Minecraft server if running in instance_dir
    and its web panel process), without closing the Dockraft system tray or other instances.
    """
    target = instance_dir.resolve()
    target_norm = str(target).lower() if sys.platform == "win32" else str(target)

    # Signal the instance's panel watcher to gracefully save the MC world and stop uvicorn
    try:
        state_dir = target / ".dockraft_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "stop_panel.flag").write_text("stop", encoding="utf-8")
    except Exception:
        pass

    if port > 0 and _is_port_open(port):
        grace_deadline = time.monotonic() + 2.5
        while time.monotonic() < grace_deadline and _is_port_open(port):
            time.sleep(0.15)

    try:
        import psutil

        my_pid = os.getpid()
        to_wait = []
        for proc in psutil.process_iter(["pid", "name", "cwd", "cmdline"]):
            try:
                if proc.info["pid"] == my_pid:
                    continue
                cwd_str = str(proc.info.get("cwd") or "")
                cmd_list = proc.info.get("cmdline") or []
                cmd_str = " ".join(str(x) for x in cmd_list)
                cwd_norm = cwd_str.lower() if sys.platform == "win32" else cwd_str
                cmd_norm = cmd_str.lower() if sys.platform == "win32" else cmd_str

                is_mc_in_inst = cwd_norm.startswith(target_norm) or (target_norm in cmd_norm and any(k in cmd_norm for k in ("java", "bedrock_server")))
                is_bg_panel = (target_norm in cmd_norm) and ("--headless" in cmd_norm or "--instance-dir" in cmd_norm)
                if is_mc_in_inst or is_bg_panel:
                    proc.terminate()
                    to_wait.append(proc)
            except Exception:
                pass
        if to_wait:
            _, alive = psutil.wait_procs(to_wait, timeout=2.0)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass

    if port > 0:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and _is_port_open(port):
            time.sleep(0.15)

    return True, _tr(
        f"Instancia '{target.name}' detenida correctamente.",
        f"Instance '{target.name}' stopped successfully.",
    )


def _create_desktop_shortcut() -> tuple[bool, str]:
    """Creates a Desktop and Start Menu / Application Launcher shortcut for Dockraft."""
    if sys.platform == "win32":
        try:
            ico_path = _find_asset("packaging/windows/dockraft.ico")
            if getattr(sys, "frozen", False):
                target_exe = str(Path(sys.executable).resolve())
                args_str = ""
                work_dir = str(Path(sys.executable).resolve().parent)
            else:
                py_exe = Path(sys.executable).resolve()
                pyw = py_exe.with_name("pythonw.exe")
                target_exe = str(pyw if pyw.is_file() else py_exe)
                script_p = str(Path(__file__).resolve())
                args_str = f'"{script_p}"'
                work_dir = str(Path(__file__).resolve().parent)

            ps_script = (
                "$ws = New-Object -ComObject WScript.Shell; "
                "$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs')); "
                "foreach ($d in $dirs) { "
                "  if ($d -and (Test-Path $d)) { "
                "    $s = $ws.CreateShortcut((Join-Path $d 'Dockraft.lnk')); "
                f"    $s.TargetPath = '{target_exe.replace(chr(39), chr(39)*2)}'; "
                f"    $s.Arguments = '{args_str.replace(chr(39), chr(39)*2)}'; "
                f"    $s.WorkingDirectory = '{work_dir.replace(chr(39), chr(39)*2)}'; "
                "    $s.Description = 'Dockraft'; "
                + (f"    $s.IconLocation = '{str(ico_path).replace(chr(39), chr(39)*2)},0'; " if ico_path else "")
                + "    $s.Save(); "
                "  } "
                "}"
            )
            extra_kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=10, **extra_kw)
            if res.returncode == 0:
                return True, _tr(
                    "Se crearon los accesos directos de Dockraft en tu Escritorio y en el Menú Inicio.",
                    "Dockraft shortcuts were created on your Desktop and Start Menu.",
                )
            return False, _tr(
                f"No se pudo crear el acceso directo:\n{res.stderr.strip() or res.stdout.strip()}",
                f"Could not create shortcut:\n{res.stderr.strip() or res.stdout.strip()}",
            )
        except Exception as e:
            return False, _tr(
                f"Error al crear el acceso directo en Windows:\n{e}",
                f"Error creating shortcut on Windows:\n{e}",
            )
    else:
        try:
            app_exec = os.getenv("APPIMAGE") or (sys.executable if getattr(sys, "frozen", False) else f"{sys.executable} {Path(__file__).resolve()}")
            icon_src = _find_icon_png()
            icon_dest = Path.home() / ".local" / "share" / "icons" / "dockraft.png"
            if icon_src and icon_src.is_file():
                icon_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(icon_src, icon_dest)
            desktop_content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Dockraft\n"
                "Comment=Minecraft Server Manager\n"
                f"Exec={app_exec}\n"
                f"Icon={icon_dest if icon_dest.is_file() else 'dockraft'}\n"
                "Terminal=false\n"
                "Categories=Game;Utility;\n"
            )
            apps_dir = Path.home() / ".local" / "share" / "applications"
            apps_dir.mkdir(parents=True, exist_ok=True)
            app_file = apps_dir / "dockraft.desktop"
            app_file.write_text(desktop_content, encoding="utf-8")
            app_file.chmod(0o755)

            for d_name in ("Desktop", "Escritorio"):
                d_dir = Path.home() / d_name
                if d_dir.is_dir():
                    desk_file = d_dir / "Dockraft.desktop"
                    desk_file.write_text(desktop_content, encoding="utf-8")
                    desk_file.chmod(0o755)
            return True, _tr(
                "Acceso directo creado en tu menú de aplicaciones y Escritorio (~/.local/share/applications/dockraft.desktop).",
                "Shortcut created in your applications menu and Desktop (~/.local/share/applications/dockraft.desktop).",
            )
        except Exception as e:
            return False, _tr(
                f"No se pudo crear el acceso directo en Linux:\n{e}",
                f"Could not create shortcut on Linux:\n{e}",
            )


def _configure_firewall_ports() -> tuple[bool, str]:
    """Opens all configured Dockraft Web & Minecraft ports in the OS Firewall."""
    instances = _discover_all_instances()
    web_ports = sorted({int(i.get("port") or 8000) for i in instances} | {8000})
    mc_ports = sorted({int(i.get("mc_port") or 25565) for i in instances} | {25565})
    all_ports_csv = ",".join(str(p) for p in sorted(set(web_ports + mc_ports)))

    if sys.platform == "win32":
        try:
            cmd_args = (
                f'/c netsh advfirewall firewall delete rule name="Dockraft Server Ports" >nul 2>&1 & '
                f'netsh advfirewall firewall add rule name="Dockraft Server Ports" dir=in action=allow protocol=TCP localport={all_ports_csv} & '
                f'netsh advfirewall firewall add rule name="Dockraft Server Ports" dir=in action=allow protocol=UDP localport={all_ports_csv}'
            )
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmd_args, None, 0)
            if int(ret) > 32:
                return (
                    True,
                    _tr(
                        f"Reglas aplicadas en Windows Defender Firewall para los puertos:\n"
                        f"• Web (TCP): {', '.join(map(str, web_ports))}\n"
                        f"• Minecraft (TCP/UDP): {', '.join(map(str, mc_ports))}",
                        f"Rules applied in Windows Defender Firewall for ports:\n"
                        f"• Web (TCP): {', '.join(map(str, web_ports))}\n"
                        f"• Minecraft (TCP/UDP): {', '.join(map(str, mc_ports))}",
                    ),
                )
            return False, _tr(
                "Se canceló el permiso de administrador (UAC) para abrir los puertos en el Firewall.",
                "Administrator permission (UAC) to open Firewall ports was cancelled.",
            )
        except Exception as e:
            return False, _tr(
                f"No se pudo configurar Windows Firewall:\n{e}",
                f"Could not configure Windows Firewall:\n{e}",
            )
    else:
        ufw_cmds = [f"sudo ufw allow {p}/tcp" for p in web_ports] + [f"sudo ufw allow {p}/tcp && sudo ufw allow {p}/udp" for p in mc_ports]
        return (
            True,
            _tr(
                "Para abrir los puertos de tus instancias en Linux (UFW), ejecuta:\n\n",
                "To open your instance ports on Linux (UFW), run:\n\n",
            )
            + "\n".join(ufw_cmds),
        )


def _notify_tray(tray_icon: Any, message: str, title: str = "Dockraft") -> None:
    """Shows a non-intrusive system tray notification if supported by the OS backend."""
    if tray_icon is None:
        return
    try:
        if getattr(tray_icon, "HAS_NOTIFICATION", True):
            tray_icon.notify(message, title)
    except Exception:
        pass


def _delete_instance(instance_dir: Path) -> tuple[bool, str]:
    """
    Safely deletes an instance folder while preserving its backups inside
    <Carpeta-principal>/backups/backup-<nombre-instancia>.
    Also terminates any running server/panel process bound to this instance and removes it from launcher_config.json.
    """
    import time

    target = instance_dir.resolve()
    backups_dir = _instance_backups_dir(target)
    _migrate_legacy_backups(target, backups_dir)

    target_norm = str(target).lower() if sys.platform == "win32" else str(target)
    try:
        import psutil

        my_pid = os.getpid()
        to_wait = []
        for proc in psutil.process_iter(["pid", "cwd", "cmdline"]):
            try:
                if proc.info["pid"] == my_pid:
                    continue
                cwd_str = str(proc.info.get("cwd") or "")
                cmd_list = proc.info.get("cmdline") or []
                cmd_str = " ".join(str(x) for x in cmd_list)
                cwd_norm = cwd_str.lower() if sys.platform == "win32" else cwd_str
                cmd_norm = cmd_str.lower() if sys.platform == "win32" else cmd_str
                if (cwd_norm and cwd_norm.startswith(target_norm)) or (target_norm in cmd_norm):
                    proc.terminate()
                    to_wait.append(proc)
            except Exception:
                pass
        if to_wait:
            _, alive = psutil.wait_procs(to_wait, timeout=1.5)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass

    try:
        if target.exists():
            shutil.rmtree(target, ignore_errors=False)
    except Exception:
        time.sleep(0.4)
        shutil.rmtree(target, ignore_errors=True)

    cfg_path = _launcher_config_path()
    cfg = _load_launcher_config()

    def _norm(p_str: str) -> str:
        return p_str.lower() if sys.platform == "win32" else p_str

    remaining = [
        i for i in cfg.get("instances", [])
        if isinstance(i, dict) and _norm(str(i.get("dir", ""))) != target_norm
    ]
    cfg["instances"] = remaining
    if _norm(str(cfg.get("last_instance") or "")) == target_norm:
        cfg["last_instance"] = remaining[0]["dir"] if remaining else ""
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    if target.exists():
        return False, _tr(
            f"No se pudieron eliminar todos los archivos de {target} (verifica que no estén abiertos en otro programa).",
            f"Could not delete all files in {target} (check that they are not open in another program).",
        )
    return True, _tr(
        f"Instancia eliminada. Tus backups siguen seguros en:\n{backups_dir}",
        f"Instance deleted. Your backups remain safe at:\n{backups_dir}",
    )


def _is_port_open(port_num: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port_num)), timeout=0.2):
            return True
    except OSError:
        return False


def _suggest_next_ports(cfg: dict | None = None, exclude_dir: Path | None = None) -> tuple[int, int]:
    all_inst = _discover_all_instances()
    excl_norm = (str(exclude_dir.resolve()).lower() if sys.platform == "win32" else str(exclude_dir.resolve())) if exclude_dir else ""
    used_web: set[int] = set()
    used_mc: set[int] = set()
    for i in all_inst:
        d_str = str(i.get("dir", ""))
        d_norm = d_str.lower() if sys.platform == "win32" else d_str
        if excl_norm and d_norm == excl_norm:
            continue
        if str(i.get("port", "")).isdigit():
            used_web.add(int(i["port"]))
        if str(i.get("mc_port", "")).isdigit():
            used_mc.add(int(i["mc_port"]))

    web_port = 8000
    while web_port in used_web or _is_port_open(web_port):
        web_port += 1
    mc_port = 25565
    while mc_port in used_mc or mc_port == web_port or _is_port_open(mc_port):
        mc_port += 1
    return web_port, mc_port


def _validate_ports(web_port_str: str, mc_port_str: str, exclude_dir: Path | None = None) -> tuple[bool, str]:
    """Validates Web & MC ports against syntax, equality, other Dockraft instances, and active OS sockets."""
    w_raw = str(web_port_str or "").strip()
    m_raw = str(mc_port_str or "").strip()
    if not w_raw.isdigit() or not m_raw.isdigit():
        return False, _tr(
            "⚠ Los puertos Web y Minecraft deben ser números enteros.",
            "⚠ Web and Minecraft ports must be integers.",
        )
    w_port = int(w_raw)
    m_port = int(m_raw)
    if not (1024 <= w_port <= 65535) or not (1024 <= m_port <= 65535):
        return False, _tr(
            "⚠ Usa puertos entre 1024 y 65535 para evitar conflictos del sistema.",
            "⚠ Use ports between 1024 and 65535 to avoid system conflicts.",
        )
    if w_port == m_port:
        return False, _tr(
            "⚠ El puerto Web y el puerto de Minecraft no pueden ser el mismo.",
            "⚠ Web port and Minecraft port cannot be the same.",
        )

    excl_norm = ""
    current_inst_port = None
    if exclude_dir is not None:
        try:
            resolved_excl = str(exclude_dir.resolve())
            excl_norm = resolved_excl.lower() if sys.platform == "win32" else resolved_excl
            env_m = _parse_env_file(exclude_dir / ".env")
            if env_m.get("PORT", "").isdigit():
                current_inst_port = int(env_m["PORT"])
        except Exception:
            pass

    for inst in _discover_all_instances():
        d_str = str(inst.get("dir", ""))
        d_norm = d_str.lower() if sys.platform == "win32" else d_str
        if excl_norm and d_norm == excl_norm:
            continue
        i_name = inst.get("name") or Path(d_str).name
        i_web = int(inst.get("port") or 0)
        i_mc = int(inst.get("mc_port") or 0)
        if w_port in (i_web, i_mc):
            return False, _tr(
                f"⚠ El puerto Web {w_port} ya está asignado a la instancia '{i_name}'.",
                f"⚠ Web port {w_port} is already assigned to instance '{i_name}'.",
            )
        if m_port in (i_web, i_mc):
            return False, _tr(
                f"⚠ El puerto MC {m_port} ya está asignado a la instancia '{i_name}'.",
                f"⚠ MC port {m_port} is already assigned to instance '{i_name}'.",
            )

    if w_port != current_inst_port and _is_port_open(w_port):
        return False, _tr(
            f"⚠ El puerto Web {w_port} está ocupado actualmente por otro programa.",
            f"⚠ Web port {w_port} is currently in use by another program.",
        )

    return True, _tr(
        f"✓ Puertos disponibles (Web :{w_port} | Minecraft :{m_port})",
        f"✓ Ports available (Web :{w_port} | Minecraft :{m_port})",
    )


def _executable_argv() -> list[str]:
    """Returns argv prefix to spawn another Dockraft launcher process (reuses mounted binary in AppImage)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    appimage = os.getenv("APPIMAGE", "").strip()
    if appimage and Path(appimage).is_file():
        return [appimage]
    return [sys.executable, str(Path(__file__).resolve())]


def _child_dockraft_env() -> dict[str, str]:
    """Returns environment for spawning a child Dockraft process (keeps AppImage/bundle libs and resets PyInstaller bootloader)."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _clean_host_env() -> dict[str, str]:
    """Restores host library paths when spawning external Linux tools from a frozen bundle."""
    env = dict(os.environ)
    if os.name != "nt":
        for k in ("APPDIR", "ARGV0", "OWD"):
            env.pop(k, None)
        orig_ld = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig_ld is not None:
            if orig_ld:
                env["LD_LIBRARY_PATH"] = orig_ld
            else:
                env.pop("LD_LIBRARY_PATH", None)
        elif "LD_LIBRARY_PATH" in env:
            bundle_roots = [p for p in (getattr(sys, "_MEIPASS", ""), env.get("APPDIR", "")) if p]
            kept = [
                part for part in env["LD_LIBRARY_PATH"].split(":")
                if part and not any(part.startswith(root) for root in bundle_roots)
            ]
            if kept:
                env["LD_LIBRARY_PATH"] = ":".join(kept)
            else:
                env.pop("LD_LIBRARY_PATH", None)
    return env


def _open_url(url: str) -> None:
    if sys.platform != "win32" and sys.platform != "darwin":
        try:
            subprocess.Popen(
                ["xdg-open", url],
                env=_clean_host_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    webbrowser.open(url)


def _open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(
            ["xdg-open", target],
            env=_clean_host_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _get_global_credentials() -> tuple[str, str]:
    cfg = _load_launcher_config()
    user = str(cfg.get("default_admin_user") or "admin").strip()
    pw = str(cfg.get("default_admin_password") or "").strip()
    if not pw:
        for inst in _discover_all_instances():
            u, p = _read_env_credentials(Path(inst["dir"]) / ".env")
            if p:
                user = u or user
                pw = p
                break
    return user, pw


def _build_autofill_url(instance_dir: Path, port: int, host: str = "127.0.0.1") -> str:
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    user, pw = _read_env_credentials(instance_dir / ".env")
    if not pw:
        g_user, g_pw = _get_global_credentials()
        user = user or g_user
        pw = pw or g_pw
    if user and pw:
        raw = json.dumps({"u": user, "p": pw, "l": _get_ui_lang()}, ensure_ascii=False).encode("utf-8")
        token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"http://{browser_host}:{port}/login#autofill={token}"
    return f"http://{browser_host}:{port}"


def _spawn_instance_background(instance_dir: Path, port: int) -> None:
    extra_kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if sys.platform == "win32" else {}
    subprocess.Popen(
        _executable_argv() + ["--instance-dir", str(instance_dir), "--port", str(port), "--headless", "--no-browser"],
        env=_child_dockraft_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **extra_kw,
    )


def _open_or_launch_instance(inst_dir: str | Path, inst_port: int) -> None:
    p_dir = Path(inst_dir).resolve()
    if not _is_port_open(inst_port):
        _spawn_instance_background(p_dir, inst_port)
        _wait_for_port("127.0.0.1", inst_port, timeout=10.0)
    _open_url(_build_autofill_url(p_dir, inst_port))


def _default_instance_dir() -> Path:
    appimage = os.getenv("APPIMAGE", "").strip()
    if appimage:
        app_dir = Path(appimage).expanduser().resolve().parent
        if (app_dir / ".portable").exists() or (app_dir / ".env").exists():
            return app_dir
    elif getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / ".portable").exists() or (exe_dir / ".env").exists():
            return exe_dir
    cfg = _load_launcher_config()
    saved = str(cfg.get("last_instance", "")).strip()
    if saved and Path(saved).is_dir():
        return Path(saved).resolve()
    discovered = _discover_all_instances()
    if discovered:
        return Path(discovered[0]["dir"]).resolve()
    return (_default_instances_root() / "survival").resolve()


def _ensure_instance_env(
    instance_dir: Path,
    host: str | None,
    port: int | None,
    mc_port: int | None = None,
    admin_user: str = "admin",
    admin_password: str = "",
    server_name: str = "",
    update_existing: bool = False,
) -> tuple[bool, str]:
    """Ensures instance_dir/.env exists with persistent credentials and external BACKUPS_DIR. Returns (is_first_run, password)."""
    instance_dir.mkdir(parents=True, exist_ok=True)
    backups_dir = _instance_backups_dir(instance_dir)
    _migrate_legacy_backups(instance_dir, backups_dir)
    env_file = instance_dir / ".env"
    if env_file.is_file():
        updates: dict[str, str] = {"BACKUPS_DIR": str(backups_dir)}
        if update_existing:
            if server_name.strip():
                updates["SERVER_NAME"] = server_name.strip()
            if host:
                updates["HOST"] = host
            if port:
                updates["PORT"] = str(port)
            if mc_port:
                updates["MC_PORT"] = str(mc_port)
                _update_mc_server_port(instance_dir, mc_port)
            if admin_user.strip():
                updates["ADMIN_USER"] = admin_user.strip()
            if admin_password.strip():
                updates["ADMIN_PASSWORD"] = admin_password.strip()
        _update_env_file(env_file, updates)
        _, existing_pw = _read_env_credentials(env_file)
        return False, existing_pw

    cfg = _load_launcher_config()
    generated_pw = admin_password.strip() or str(cfg.get("default_admin_password") or "").strip() or secrets.token_urlsafe(12)
    generated_secret = secrets.token_urlsafe(32)
    bind_host = host or str(cfg.get("default_host") or "127.0.0.1")
    bind_port = port or 8000
    game_port = mc_port or 25565
    timeout_min = int(cfg.get("session_timeout_minutes") or 60)
    srv_name = server_name.strip() or instance_dir.name or "Mi Servidor Dockraft"
    content = (
        "# Dockraft Instance Configuration\n"
        f"SERVER_NAME={srv_name}\n"
        f"HOST={bind_host}\n"
        f"PORT={bind_port}\n"
        f"MC_PORT={game_port}\n"
        f"BACKUPS_DIR={backups_dir}\n"
        "ADMIN_USER=" + (admin_user.strip() or "admin") + "\n"
        f"ADMIN_PASSWORD={generated_pw}\n"
        f"SESSION_TIMEOUT_MINUTES={timeout_min}\n"
        f"SECRET_KEY={generated_secret}\n"
    )
    env_file.write_text(content, encoding="utf-8")
    return True, generated_pw


def _enable_win_dpi_and_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GMS-EC.Dockraft.Launcher")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _apply_dark_titlebar(tk_root, allow_maximize: bool = True) -> None:
    def _style_win32_hwnd() -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(tk_root.winfo_id()) or tk_root.winfo_id()
            # Ensure WS_EX_LAYERED is never left set so Windows 11 DWM animations (maximize/minimize) work natively
            gwl_exstyle = -20
            ws_ex_layered = 0x00080000
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            if ex_style & ws_ex_layered:
                ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, ex_style & ~ws_ex_layered)

            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            corner = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
            if not allow_maximize:
                gwl_style = -16
                ws_maximizebox = 0x00010000
                style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_style)
                if style & ws_maximizebox:
                    ctypes.windll.user32.SetWindowLongW(hwnd, gwl_style, style & ~ws_maximizebox)
                    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
            ico_path = _find_asset("packaging/windows/dockraft.ico")
            if ico_path:
                try:
                    tk_root.iconbitmap(str(ico_path))
                except Exception:
                    pass
                try:
                    image_icon = 1
                    lr_loadfromfile = 0x0010
                    wm_seticon = 0x0080
                    h_small = ctypes.windll.user32.LoadImageW(0, str(ico_path), image_icon, 16, 16, lr_loadfromfile)
                    h_big = ctypes.windll.user32.LoadImageW(0, str(ico_path), image_icon, 32, 32, lr_loadfromfile)
                    if h_small:
                        ctypes.windll.user32.SendMessageW(hwnd, wm_seticon, 0, h_small)
                    if h_big:
                        ctypes.windll.user32.SendMessageW(hwnd, wm_seticon, 1, h_big)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        tk_root.update_idletasks()
        _style_win32_hwnd()
        tk_root.deiconify()
        tk_root.update_idletasks()
        _style_win32_hwnd()
        tk_root.lift()
    except Exception:
        pass


def _make_rounded_rect_img(
    width: int,
    height: int,
    radius: int,
    fill: str,
    border: str | None = None,
    outer_bg: str | None = None,
    border_width: int = 1,
    master=None,
):
    """Generates a smooth supersampled rounded-rectangle PhotoImage via Pillow."""
    from PIL import Image, ImageDraw, ImageTk

    w = max(4, int(width))
    h = max(4, int(height))
    scale = 2 if (w > 520 or h > 260) else 4
    base_rgba = outer_bg if outer_bg else (0, 0, 0, 0)
    img = Image.new("RGBA", (w * scale, h * scale), base_rgba)
    draw = ImageDraw.Draw(img)
    r = min(radius * scale, (min(w, h) * scale) // 2)
    bw = max(1, border_width * scale) if border else 0
    draw.rounded_rectangle(
        [0, 0, w * scale - 1, h * scale - 1],
        radius=r,
        fill=fill,
        outline=border if border else None,
        width=bw,
    )
    resample_mode = Image.Resampling.BILINEAR if scale == 2 else Image.Resampling.LANCZOS
    img = img.resize((w, h), resample_mode)
    return ImageTk.PhotoImage(img, master=master)


def _pick_fonts(tk_root) -> tuple[str, str]:
    from tkinter import font as tkfont

    try:
        available = set(tkfont.families(tk_root))
    except Exception:
        available = set()

    ui_candidates = ("Segoe UI", "Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans")
    mono_candidates = ("Consolas", "JetBrains Mono", "Ubuntu Mono", "DejaVu Sans Mono", "Liberation Mono")
    ui = next((f for f in ui_candidates if f in available), "Sans" if sys.platform != "win32" else "Segoe UI")
    mono = next((f for f in mono_candidates if f in available), "monospace" if sys.platform != "win32" else "Consolas")
    return ui, mono


def _find_asset(rel_path: str) -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / rel_path)
    candidates.append(Path(__file__).resolve().parent / rel_path)
    for c in candidates:
        if c.is_file():
            return c
    return None


def _find_icon_png() -> Path | None:
    return _find_asset("packaging/linux/dockraft.png") or _find_asset("packaging/windows/dockraft_icon.png")


def _build_tk_primitives(root, allow_resize: bool = True):
    """Creates reusable rounded panel, entry, button, and checkbox builders bound to root."""
    import tkinter as tk
    from tkinter import font as tkfont

    bg = "#0f1115"
    card = "#181b21"
    panel = "#13161b"
    fg = "#e5e7eb"
    muted = "#9ca3af"
    accent = "#3ca374"
    accent_hover = "#2f8e64"
    accent_border = "#4bbd88"
    border = "#282e38"
    entry_bg = "#0e1014"
    btn_bg = "#252a33"
    btn_hover = "#303744"
    btn_border = "#343b48"

    ui_font, mono_font = _pick_fonts(root)
    try:
        root.withdraw()
    except Exception:
        pass
    root.configure(bg=bg)
    root.resizable(allow_resize, allow_resize)

    ico_applied = False
    if sys.platform == "win32":
        ico_path = _find_asset("packaging/windows/dockraft.ico")
        if ico_path:
            try:
                root.iconbitmap(str(ico_path))
                ico_applied = True
            except Exception:
                pass

    header_logo = None
    png_path = _find_icon_png()
    if png_path:
        try:
            from PIL import Image, ImageTk

            pil_img = Image.open(png_path).convert("RGBA")
            logo_photo = ImageTk.PhotoImage(pil_img.resize((64, 64), Image.Resampling.LANCZOS), master=root)
            if not ico_applied:
                root.iconphoto(True, logo_photo)
            root._logo_photo = logo_photo
            header_logo = ImageTk.PhotoImage(pil_img.resize((44, 44), Image.Resampling.LANCZOS), master=root)
            root._header_logo = header_logo
        except Exception:
            pass

    def rounded_panel(parent, outer_bg: str = card, fill: str = panel, border_col: str = border, radius: int = 12, padx: int = 14, pady: int = 10, expand: bool = False):
        if expand:
            wrap = tk.Frame(parent, bg=fill, highlightbackground=border_col, highlightthickness=1, bd=0)
            inner_f = tk.Frame(wrap, bg=fill)
            inner_f.pack(fill="both", expand=True, padx=padx, pady=pady)
            wrap._sync_height = lambda: None
            return wrap, inner_f

        c = tk.Canvas(parent, bg=outer_bg, width=200, height=48, highlightthickness=0, bd=0)
        inner = tk.Frame(c, bg=fill)
        win_id = c.create_window(padx, pady, window=inner, anchor="nw")
        state = {"w": 0, "h": 0, "img": None, "border": border_col, "fill": fill, "job": None}

        def _draw(w: int, h: int, force: bool = False):
            if w < 12 or h < 12 or (not force and w == state["w"] and h == state["h"]):
                return
            state["w"], state["h"] = w, h
            img = _make_rounded_rect_img(w, h, radius, state["fill"], border=state["border"], outer_bg=outer_bg, border_width=1, master=root)
            state["img"] = img
            c.delete("bg")
            c.create_image(0, 0, anchor="nw", image=img, tag="bg")
            c.tag_lower("bg")

        def _sync_height():
            req_h = inner.winfo_reqheight() + pady * 2
            if req_h != c.winfo_reqheight():
                c.configure(height=req_h)
            if state["w"] > 0:
                _draw(state["w"], req_h)

        def _on_canvas_cfg(event):
            c.itemconfigure(win_id, width=max(20, event.width - padx * 2))
            if state["w"] == 0:
                _draw(event.width, event.height)
                c.after_idle(_sync_height)
            else:
                if state["job"] is not None:
                    try:
                        c.after_cancel(state["job"])
                    except Exception:
                        pass
                w_ev, h_ev = event.width, event.height
                state["job"] = c.after(12, lambda: (_draw(w_ev, h_ev), _sync_height()))

        c.bind("<Configure>", _on_canvas_cfg)
        inner.bind("<Configure>", lambda _e: _sync_height(), add="+")
        c._sync_height = _sync_height
        return c, inner

    def rounded_entry(parent, var, parent_bg: str = card, font=None, radius: int = 10, height: int = 38, init_w: int = 120, **kw):
        entry_font = font or (mono_font, 10)
        c = tk.Canvas(parent, bg=parent_bg, width=init_w, height=height, highlightthickness=0, bd=0)
        entry = tk.Entry(
            c,
            textvariable=var,
            bg=entry_bg,
            fg=fg,
            disabledbackground=panel,
            disabledforeground="#6b7280",
            insertbackground=fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=entry_font,
            **kw,
        )
        win_id = c.create_window(12, height // 2, window=entry, anchor="w")
        state = {"w": 0, "focused": False, "disabled": False, "img": None}

        def _redraw(force: bool = False):
            w = state["w"]
            if w < 16:
                return
            disabled = str(entry["state"]) == "disabled"
            if not force and state["img"] is not None and disabled == state["disabled"]:
                return
            state["disabled"] = disabled
            fill_col = panel if disabled else entry_bg
            border_col = "#22272f" if disabled else (accent if state["focused"] else border)
            entry.configure(bg=fill_col)
            img = _make_rounded_rect_img(w, height, radius, fill_col, border=border_col, outer_bg=parent_bg, border_width=1, master=root)
            state["img"] = img
            c.delete("bg")
            c.create_image(0, 0, anchor="nw", image=img, tag="bg")
            c.tag_lower("bg")

        def _on_cfg(event):
            state["w"] = event.width
            c.itemconfigure(win_id, width=max(20, event.width - 24))
            _redraw(force=True)

        c.bind("<Configure>", _on_cfg)
        c.bind("<Button-1>", lambda _e: entry.focus_set())
        entry.bind("<FocusIn>", lambda _e: (state.update({"focused": True}), _redraw(force=True)))
        entry.bind("<FocusOut>", lambda _e: (state.update({"focused": False}), _redraw(force=True)))
        entry._refresh_rounded = lambda: _redraw(force=True)
        return c, entry

    def rounded_button(
        parent,
        text: str,
        command,
        parent_bg: str = card,
        bg_col: str = btn_bg,
        hover_col: str = btn_hover,
        border_col: str = btn_border,
        fg_col: str = fg,
        font=None,
        radius: int = 10,
        padx: int = 14,
        height: int = 36,
        min_w: int = 76,
    ):
        btn_font = font or (ui_font, 9)
        meas = tkfont.Font(family=btn_font[0], size=btn_font[1], weight=btn_font[2] if len(btn_font) > 2 else "normal")
        btn_w = max(min_w, meas.measure(text) + padx * 2)
        c = tk.Canvas(parent, bg=parent_bg, width=btn_w, height=height, highlightthickness=0, bd=0, cursor="hand2")
        normal_img = _make_rounded_rect_img(btn_w, height, radius, bg_col, border=border_col, outer_bg=parent_bg, border_width=1, master=root)
        hover_img = _make_rounded_rect_img(btn_w, height, radius, hover_col, border=border_col, outer_bg=parent_bg, border_width=1, master=root)
        c._imgs = (normal_img, hover_img)
        bg_id = c.create_image(0, 0, anchor="nw", image=normal_img)
        txt_id = c.create_text(btn_w // 2, height // 2, text=text, fill=fg_col, font=btn_font)

        c.bind("<Enter>", lambda _e: c.itemconfigure(bg_id, image=hover_img))
        c.bind("<Leave>", lambda _e: c.itemconfigure(bg_id, image=normal_img))

        def _release(event):
            if 0 <= event.x <= btn_w and 0 <= event.y <= height:
                command()

        c.bind("<ButtonRelease-1>", _release)
        c._set_text = lambda new_t: c.itemconfigure(txt_id, text=new_t)
        return c

    def rounded_checkbox(parent, text: str, var, parent_bg: str = card):
        row = tk.Frame(parent, bg=parent_bg, cursor="hand2")
        chk_size = 18
        chk_canvas = tk.Canvas(row, bg=parent_bg, width=chk_size, height=chk_size, highlightthickness=0, bd=0, cursor="hand2")
        chk_canvas.pack(side="left", padx=(0, 8))
        off_img = _make_rounded_rect_img(chk_size, chk_size, 5, entry_bg, border=border, outer_bg=parent_bg, border_width=1, master=root)
        on_img = _make_rounded_rect_img(chk_size, chk_size, 5, accent, border=accent_border, outer_bg=parent_bg, border_width=1, master=root)
        chk_canvas._imgs = (off_img, on_img)
        init_val = bool(var.get())
        bg_id = chk_canvas.create_image(0, 0, anchor="nw", image=on_img if init_val else off_img)
        mark_id = chk_canvas.create_text(chk_size // 2, chk_size // 2, text="✓" if init_val else "", fill="#ffffff", font=(ui_font, 9, "bold"))
        lbl = tk.Label(row, text=text, bg=parent_bg, fg=fg if init_val else muted, font=(ui_font, 8), cursor="hand2")
        lbl.pack(side="left")

        def _toggle(_e=None):
            val = not bool(var.get())
            var.set(val)
            chk_canvas.itemconfigure(bg_id, image=on_img if val else off_img)
            chk_canvas.itemconfigure(mark_id, text="✓" if val else "")
            lbl.configure(fg=fg if val else muted)

        chk_canvas.bind("<Button-1>", _toggle)
        lbl.bind("<Button-1>", _toggle)
        return row

    def lang_button(parent, on_change, parent_bg: str = card, height: int = 32):
        cur_code = "EN" if _get_ui_lang() == "en" else "ES"

        def _switch():
            next_lang = "en" if _get_ui_lang() == "es" else "es"
            _set_ui_lang(next_lang)
            on_change()

        return rounded_button(
            parent,
            f"🌐 {cur_code}",
            _switch,
            parent_bg=parent_bg,
            font=(ui_font, 8, "bold"),
            radius=9,
            padx=10,
            height=height,
            min_w=54,
        )

    return {
        "bg": bg,
        "card": card,
        "panel": panel,
        "fg": fg,
        "muted": muted,
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_border": accent_border,
        "border": border,
        "entry_bg": entry_bg,
        "btn_bg": btn_bg,
        "btn_hover": btn_hover,
        "btn_border": btn_border,
        "ui_font": ui_font,
        "mono_font": mono_font,
        "header_logo": header_logo,
        "rounded_panel": rounded_panel,
        "rounded_entry": rounded_entry,
        "rounded_button": rounded_button,
        "rounded_checkbox": rounded_checkbox,
        "lang_button": lang_button,
    }


def _run_dark_message_dialog(
    title: str,
    message: str,
    buttons: list[tuple[str, int, bool]],
    default_idx: int = -1,
    parent: Any = None,
    danger_primary: bool = False,
) -> int:
    """Shows a dark rounded Tkinter dialog with the Dockraft logo, window icon, and configurable buttons."""
    import tkinter as tk

    _enable_win_dpi_and_app_id()
    chosen = {"code": buttons[default_idx][1] if buttons else 0}
    if parent is not None:
        root = tk.Toplevel(parent, class_="Dockraft")
        root.transient(parent)
        root.grab_set()
    else:
        root = tk.Tk(className="Dockraft")
    root.title(title)
    ui = _build_tk_primitives(root, allow_resize=False)

    outer, inner = ui["rounded_panel"](root, ui["bg"], ui["card"], ui["border"], radius=16, padx=22, pady=18, expand=True)
    outer.pack(fill="both", expand=True, padx=14, pady=14)

    hdr = tk.Frame(inner, bg=ui["card"])
    hdr.pack(fill="x", pady=(0, 10))
    if ui["header_logo"] is not None:
        lbl_logo = tk.Label(hdr, image=ui["header_logo"], bg=ui["card"])
        lbl_logo.image = ui["header_logo"]
        lbl_logo.pack(side="left", padx=(0, 12))
    tk.Label(
        hdr,
        text=title,
        bg=ui["card"],
        fg=ui["fg"],
        font=(ui["ui_font"], 12, "bold"),
        anchor="w",
        justify="left",
        wraplength=380,
    ).pack(side="left", fill="x", expand=True)

    tk.Label(
        inner,
        text=message,
        bg=ui["card"],
        fg="#cbd5e1",
        font=(ui["ui_font"], 9),
        justify="left",
        anchor="w",
        wraplength=440,
    ).pack(fill="x", pady=(0, 16))

    btn_row = tk.Frame(inner, bg=ui["card"])
    btn_row.pack(fill="x", side="bottom")

    prim_bg = "#dc2626" if danger_primary else ui["accent"]
    prim_hover = "#ef4444" if danger_primary else ui["accent_hover"]
    prim_border = "#f87171" if danger_primary else ui["accent_border"]

    for label, code, primary in reversed(buttons):
        ui["rounded_button"](
            btn_row,
            label,
            lambda val=code: (chosen.update({"code": val}), root.destroy()),
            bg_col=prim_bg if primary else ui["btn_bg"],
            hover_col=prim_hover if primary else ui["btn_hover"],
            border_col=prim_border if primary else ui["btn_border"],
            fg_col="#ffffff" if primary else ui["fg"],
            font=(ui["ui_font"], 9, "bold" if primary else "normal"),
            padx=16,
            height=36,
        ).pack(side="right", padx=(8, 0))

    root.bind("<Escape>", lambda _e: root.destroy())
    root.update_idletasks()
    w = max(490, inner.winfo_reqwidth() + 72)
    h = max(210, inner.winfo_reqheight() + 72)
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    _apply_dark_titlebar(root, allow_maximize=False)
    if parent is not None:
        parent.wait_window(root)
    else:
        root.mainloop()
    return chosen["code"]


def _prompt_dark_dialog(title: str, message: str, mode: str) -> int:
    try:
        payload = json.dumps({"title": title, "message": message, "mode": mode})
        if threading.current_thread() is threading.main_thread():
            return _handle_dialog_mode(payload)
        extra_kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if sys.platform == "win32" else {}
        proc = subprocess.run(_executable_argv() + ["--dialog-mode", payload], env=_child_dockraft_env(), **extra_kw)
        return proc.returncode
    except Exception:
        return 0 if mode == "info" else 1


def _run_setup_dialog(
    initial_root: Path,
    initial_name: str = "Survival",
    initial_port: int = 8000,
    initial_mc_port: int = 25565,
    initial_user: str = "admin",
    initial_password: str = "",
) -> dict | None:
    """
    Shows the 'Nueva Instancia' / 'New Instance' wizard.
    - First run only: asks for the main root folder and global admin credentials.
    - Subsequent runs: uses the saved instances_root automatically and validates ports in real time.
    """
    import tkinter as tk
    from tkinter import filedialog

    _enable_win_dpi_and_app_id()
    result: dict | None = None

    cfg = _load_launcher_config()
    existing_instances = _discover_all_instances()
    has_configured_root = bool(str(cfg.get("instances_root", "")).strip()) or len(existing_instances) > 0

    root = tk.Tk(className="Dockraft")
    ui = _build_tk_primitives(root)
    card = ui["card"]
    panel = ui["panel"]
    fg = ui["fg"]
    muted = ui["muted"]
    ui_font = ui["ui_font"]
    mono_font = ui["mono_font"]

    base_default = initial_root.parent if initial_root.name.lower() == "instancias" else initial_root
    name_var = tk.StringVar(value=initial_name)
    root_var = tk.StringVar(value=str(base_default))
    port_var = tk.StringVar(value=str(initial_port))
    mc_port_var = tk.StringVar(value=str(initial_mc_port))
    user_var = tk.StringVar(value=initial_user or "admin")
    pw_var = tk.StringVar(value=initial_password or secrets.token_urlsafe(10))
    default_lan = str(cfg.get("default_host") or "127.0.0.1") == "0.0.0.0"
    lan_var = tk.BooleanVar(value=default_lan)

    def _compute_instance_paths() -> tuple[Path, Path]:
        base = Path(root_var.get().strip() or str(base_default)).expanduser()
        inst_root = base if base.name.lower() == "instancias" else (base / "instancias")
        inst_dir = inst_root / _slugify_name(name_var.get())
        return inst_root, inst_dir

    def _submit(event=None):
        nonlocal result
        if not root_var.get().strip():
            _run_dark_message_dialog(
                "Dockraft",
                _tr("Debes elegir una carpeta principal válida.", "You must choose a valid main folder."),
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )
            return
        inst_root, inst_dir = _compute_instance_paths()
        ok_ports, port_msg = _validate_ports(port_var.get(), mc_port_var.get(), exclude_dir=inst_dir)
        if not ok_ports:
            _run_dark_message_dialog(
                _tr("Dockraft — Conflicto de Puertos", "Dockraft — Port Conflict"),
                port_msg,
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )
            return
        result = {
            "server_name": name_var.get().strip() or inst_dir.name,
            "instances_root": inst_root.resolve(),
            "instance_dir": inst_dir.resolve(),
            "host": "0.0.0.0" if lan_var.get() else "127.0.0.1",
            "port": int(port_var.get().strip()),
            "mc_port": int(mc_port_var.get().strip()),
            "admin_user": user_var.get().strip() or "admin",
            "admin_password": pw_var.get().strip(),
        }
        root.destroy()

    def _cancel(event=None):
        root.destroy()

    state_holder: dict[str, Any] = {"outer": None, "traces": []}

    def _build_content():
        for var_obj, tid in state_holder["traces"]:
            try:
                var_obj.trace_remove("write", tid)
            except Exception:
                pass
        state_holder["traces"].clear()
        if state_holder["outer"] is not None:
            state_holder["outer"].destroy()

        root.title(
            _tr("Dockraft — Nueva Instancia", "Dockraft — New Instance")
            if has_configured_root
            else _tr("Dockraft — Configuración Inicial", "Dockraft — Initial Setup")
        )

        outer_wrap, frame = ui["rounded_panel"](root, ui["bg"], card, ui["border"], radius=16, padx=22, pady=20, expand=True)
        outer_wrap.pack(fill="both", expand=True, padx=14, pady=14)
        state_holder["outer"] = outer_wrap

        header = tk.Frame(frame, bg=card)
        header.pack(fill="x", pady=(0, 14))
        if ui["header_logo"] is not None:
            lbl_logo = tk.Label(header, image=ui["header_logo"], bg=card)
            lbl_logo.image = ui["header_logo"]
            lbl_logo.pack(side="left", padx=(0, 12))
        title_box = tk.Frame(header, bg=card)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text=(
                _tr("Nueva Instancia de Dockraft", "New Dockraft Instance")
                if has_configured_root
                else _tr("Configuración Inicial de Dockraft", "Dockraft Initial Setup")
            ),
            bg=card,
            fg=fg,
            font=(ui_font, 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text=(
                _tr(
                    "Se creará dentro de tu carpeta principal de instancias con puertos validados.",
                    "It will be created inside your main instances folder with validated ports.",
                )
                if has_configured_root
                else _tr(
                    "Elige la carpeta principal donde vivirán tus instancias y backups.",
                    "Choose the main folder where your instances and backups will live.",
                )
            ),
            bg=card,
            fg=muted,
            font=(ui_font, 9),
        ).pack(anchor="w", pady=(2, 0))

        # Server Name row
        tk.Label(frame, text=_tr("Nombre del servidor", "Server name"), bg=card, fg=fg, font=(ui_font, 9, "bold")).pack(anchor="w")
        name_box, _ = ui["rounded_entry"](frame, name_var, font=(ui_font, 10), init_w=360)
        name_box.pack(fill="x", pady=(5, 11))

        # Main folder row
        tk.Label(
            frame,
            text=_tr(
                "Carpeta principal (contendrá 'instancias' y 'backups')",
                "Main folder (will contain 'instancias' and 'backups')",
            ),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        dir_row = tk.Frame(frame, bg=card)
        dir_row.pack(fill="x", pady=(5, 8))
        dir_box, _ = ui["rounded_entry"](dir_row, root_var, font=(mono_font, 9), init_w=300)
        dir_box.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _browse():
            chosen = filedialog.askdirectory(
                initialdir=root_var.get() or str(base_default),
                title=_tr("Selecciona la carpeta principal para Dockraft", "Select the main folder for Dockraft"),
            )
            if chosen:
                root_var.set(str(Path(chosen).resolve()))

        ui["rounded_button"](dir_row, _tr("Examinar...", "Browse..."), _browse, padx=16, height=38).pack(side="right")

        # Preview box
        preview_wrap, preview_inner = ui["rounded_panel"](frame, card, panel, ui["border"], radius=12, padx=14, pady=10)
        preview_wrap.pack(fill="x", pady=(0, 12))
        preview_var = tk.StringVar()
        preview_lbl = tk.Label(
            preview_inner,
            textvariable=preview_var,
            bg=panel,
            fg=muted,
            font=(ui_font, 8),
            justify="left",
            anchor="w",
            wraplength=540,
        )
        preview_lbl.pack(fill="x", anchor="w")
        preview_inner.bind("<Configure>", lambda e: preview_lbl.configure(wraplength=max(260, e.width - 4)), add="+")

        # Ports row + Suggest Free button
        ports_hdr = tk.Frame(frame, bg=card)
        ports_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(ports_hdr, text=_tr("Configuración de Puertos", "Port Configuration"), bg=card, fg=fg, font=(ui_font, 9, "bold")).pack(side="left")

        def _fill_free_ports():
            _, cur_dir = _compute_instance_paths()
            w_free, m_free = _suggest_next_ports(exclude_dir=cur_dir)
            port_var.set(str(w_free))
            mc_port_var.set(str(m_free))

        ui["rounded_button"](
            ports_hdr,
            _tr("Sugerir puertos libres", "Suggest free ports"),
            _fill_free_ports,
            font=(ui_font, 8),
            padx=10,
            height=26,
            radius=8,
            min_w=90,
        ).pack(side="right")

        row2 = tk.Frame(frame, bg=card)
        row2.pack(fill="x", pady=(2, 8))
        col1 = tk.Frame(row2, bg=card)
        col1.pack(side="left", fill="x", expand=True, padx=(0, 8))
        col2 = tk.Frame(row2, bg=card)
        col2.pack(side="left", fill="x", expand=True, padx=(0, 8 if not initial_password else 0))

        tk.Label(col1, text=_tr("Puerto Web (HTTP)", "Web Port (HTTP)"), bg=card, fg=muted, font=(ui_font, 8)).pack(anchor="w")
        port_box, _ = ui["rounded_entry"](col1, port_var, font=(mono_font, 10), init_w=110)
        port_box.pack(fill="x", pady=(4, 0))

        tk.Label(col2, text=_tr("Puerto Minecraft", "Minecraft Port"), bg=card, fg=muted, font=(ui_font, 8)).pack(anchor="w")
        mc_box, _ = ui["rounded_entry"](col2, mc_port_var, font=(mono_font, 10), init_w=110)
        mc_box.pack(fill="x", pady=(4, 0))

        if initial_password:
            cred_wrap, cred_inner = ui["rounded_panel"](frame, card, panel, ui["border"], radius=12, padx=14, pady=9)
            cred_wrap.pack(fill="x", pady=(2, 8))
            tk.Label(
                cred_inner,
                text=_tr(
                    f"✓ Se usará tu usuario ({user_var.get()}) y contraseña global (auto-relleno al abrir la web).",
                    f"✓ Your global user ({user_var.get()}) and password will be used (auto-filled when opening the web panel).",
                ),
                bg=panel,
                fg="#3fb950",
                font=(ui_font, 8),
                anchor="w",
            ).pack(fill="x", anchor="w")
        else:
            col3 = tk.Frame(row2, bg=card)
            col3.pack(side="left", fill="x", expand=True)
            tk.Label(col3, text=_tr("Usuario Admin", "Admin User"), bg=card, fg=muted, font=(ui_font, 8)).pack(anchor="w")
            user_box, _ = ui["rounded_entry"](col3, user_var, font=(mono_font, 10), init_w=110)
            user_box.pack(fill="x", pady=(4, 0))

            tk.Label(
                frame,
                text=_tr(
                    "Contraseña del panel (se usará en todas tus instancias)",
                    "Panel password (will be used across all your instances)",
                ),
                bg=card,
                fg=fg,
                font=(ui_font, 9, "bold"),
            ).pack(anchor="w")
            pw_row = tk.Frame(frame, bg=card)
            pw_row.pack(fill="x", pady=(5, 8))
            pw_box, _ = ui["rounded_entry"](pw_row, pw_var, font=(mono_font, 10), init_w=300)
            pw_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ui["rounded_button"](pw_row, _tr("Generar", "Generate"), lambda: pw_var.set(secrets.token_urlsafe(10)), padx=14, height=38).pack(side="right")

        # Live validation status labels
        port_status_var = tk.StringVar()
        port_status_lbl = tk.Label(frame, textvariable=port_status_var, bg=card, fg="#3fb950", font=(ui_font, 8, "bold"))
        port_status_lbl.pack(anchor="w", pady=(2, 2))

        status_var = tk.StringVar()
        status_lbl = tk.Label(frame, textvariable=status_var, bg=card, fg=muted, font=(ui_font, 8))
        status_lbl.pack(anchor="w", pady=(0, 8))

        ui["rounded_checkbox"](
            frame,
            _tr("Permitir acceso al panel desde mi red local (0.0.0.0)", "Allow panel access from my local network (0.0.0.0)"),
            lan_var,
        ).pack(anchor="w", pady=(0, 14))

        def _refresh_state(*_):
            inst_root, p = _compute_instance_paths()
            main_root = inst_root.parent if inst_root.name.lower() == "instancias" else inst_root
            backups_p = main_root / "backups" / f"backup-{p.name}"
            preview_var.set(
                _tr(
                    f"Carpeta principal: {main_root}\nInstancia: {p}\nBackups (fuera de instancias): {backups_p}",
                    f"Main folder: {main_root}\nInstance: {p}\nBackups (outside instances): {backups_p}",
                )
            )
            preview_wrap.after_idle(preview_wrap._sync_height)

            ok_ports, port_msg = _validate_ports(port_var.get(), mc_port_var.get(), exclude_dir=p)
            port_status_var.set(port_msg)
            port_status_lbl.configure(fg="#3fb950" if ok_ports else "#f59e0b")

            if (p / ".env").is_file():
                status_var.set(
                    _tr(
                        "• Esta carpeta de instancia ya existe: se actualizarán sus puertos y abrirá el panel.",
                        "• This instance folder already exists: its ports will be updated and the panel will open.",
                    )
                )
                status_lbl.configure(fg="#58a6ff")
            else:
                status_var.set(_tr("• Nueva instancia lista para crearse.", "• New instance ready to be created."))
                status_lbl.configure(fg=muted)

        for v_obj in (root_var, name_var, port_var, mc_port_var):
            tid = v_obj.trace_add("write", _refresh_state)
            state_holder["traces"].append((v_obj, tid))
        _refresh_state()

        btn_row = tk.Frame(frame, bg=card)
        btn_row.pack(fill="x", side="bottom", pady=(2, 0))

        ui["rounded_button"](
            btn_row,
            _tr("Crear e Iniciar", "Create & Start"),
            _submit,
            bg_col=ui["accent"],
            hover_col=ui["accent_hover"],
            border_col=ui["accent_border"],
            fg_col="#ffffff",
            font=(ui_font, 10, "bold"),
            radius=11,
            padx=20,
            height=40,
        ).pack(side="right")
        ui["rounded_button"](btn_row, _tr("Cancelar", "Cancel"), _cancel, radius=11, padx=16, height=40).pack(side="right", padx=(0, 8))

        root.update_idletasks()
        preview_wrap._sync_height()
        if initial_password:
            cred_wrap._sync_height()
        root.update_idletasks()

    _build_content()
    root.bind("<Return>", _submit)
    root.bind("<Escape>", _cancel)
    w = max(650, state_holder["outer"].winfo_reqwidth() + 72)
    h = max(555, state_holder["outer"].winfo_reqheight() + 72)
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(w, h)
    _apply_dark_titlebar(root, allow_maximize=True)
    _close_splash()
    root.mainloop()
    return result


def _run_instances_dialog() -> None:
    """
    Shows the Tkinter Instance Manager window:
    - Lists all detected instances with live status (En línea / Detenida), Web & MC ports.
    - Clicking 'Abrir Web' / 'Iniciar y Abrir' starts it if stopped and opens the browser with auto-filled login.
    - 'Detener' stops a running instance without closing the tray or other instances.
    - 'Archivos' button opens the instance folder in Explorer.
    - 'Puertos' allows live-validated port & name editing without touching text files.
    - 'Borrar' deletes the instance while keeping backups safe.
    """
    import tkinter as tk

    _enable_win_dpi_and_app_id()
    root = tk.Tk(className="Dockraft")
    ui = _build_tk_primitives(root, allow_resize=True)
    card = ui["card"]
    panel = ui["panel"]
    fg = ui["fg"]
    muted = ui["muted"]
    ui_font = ui["ui_font"]
    mono_font = ui["mono_font"]

    status_widgets: list[tuple[int, Any, Any, Any]] = []
    state_holder: dict[str, Any] = {"outer": None, "traces": []}

    def _build_content():
        for var_obj, tid in state_holder["traces"]:
            try:
                var_obj.trace_remove("write", tid)
            except Exception:
                pass
        state_holder["traces"].clear()
        status_widgets.clear()
        if state_holder["outer"] is not None:
            state_holder["outer"].destroy()

        root.title(_tr("Dockraft — Gestor de Instancias", "Dockraft — Instance Manager"))

        outer_wrap, frame = ui["rounded_panel"](root, ui["bg"], card, ui["border"], radius=16, padx=22, pady=18, expand=True)
        outer_wrap.pack(fill="both", expand=True, padx=14, pady=14)
        state_holder["outer"] = outer_wrap

        # Header
        header = tk.Frame(frame, bg=card)
        header.pack(fill="x", pady=(0, 12))
        if ui["header_logo"] is not None:
            lbl_logo = tk.Label(header, image=ui["header_logo"], bg=card)
            lbl_logo.image = ui["header_logo"]
            lbl_logo.pack(side="left", padx=(0, 12))
        title_box = tk.Frame(header, bg=card)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text=_tr("Instancias de Dockraft", "Dockraft Instances"),
            bg=card,
            fg=fg,
            font=(ui_font, 13, "bold"),
        ).pack(anchor="w")
        root_path_lbl = tk.Label(
            title_box,
            text=_tr(
                f"Carpeta principal: {_main_root_dir()}  (instancias/ y backups/)",
                f"Main folder: {_main_root_dir()}  (instancias/ & backups/)",
            ),
            bg=card,
            fg=muted,
            font=(ui_font, 8),
        )
        root_path_lbl.pack(anchor="w", pady=(2, 0))

        def _open_new_instance_wizard():
            root.destroy()
            _handle_new_instance_flow()

        ui["rounded_button"](
            header,
            _tr("+ Nueva instancia", "+ New instance"),
            _open_new_instance_wizard,
            bg_col=ui["accent"],
            hover_col=ui["accent_hover"],
            border_col=ui["accent_border"],
            fg_col="#ffffff",
            font=(ui_font, 9, "bold"),
            padx=14,
            height=36,
        ).pack(side="right", padx=(8, 0))

        ui["rounded_button"](
            header,
            _tr("Carpeta principal", "Main folder"),
            lambda: _open_path(_main_root_dir()),
            font=(ui_font, 8),
            padx=12,
            height=36,
        ).pack(side="right")

        # Inline Port Editor Frame (hidden until user clicks 'Puertos' / 'Ports' on an instance)
        editor_wrap, editor_inner = ui["rounded_panel"](frame, card, "#11141a", ui["accent_border"], radius=12, padx=14, pady=10)
        editing_state: dict[str, Any] = {"dir": None}
        ed_title_var = tk.StringVar(value=_tr("Editar instancia", "Edit instance"))
        ed_name_var = tk.StringVar()
        ed_web_var = tk.StringVar()
        ed_mc_var = tk.StringVar()
        ed_valid_var = tk.StringVar()

        ed_top = tk.Frame(editor_inner, bg="#11141a")
        ed_top.pack(fill="x", pady=(0, 6))
        tk.Label(ed_top, textvariable=ed_title_var, bg="#11141a", fg=fg, font=(ui_font, 9, "bold")).pack(side="left")
        ed_valid_lbl = tk.Label(ed_top, textvariable=ed_valid_var, bg="#11141a", fg="#3fb950", font=(ui_font, 8, "bold"))
        ed_valid_lbl.pack(side="right")

        ed_fields = tk.Frame(editor_inner, bg="#11141a")
        ed_fields.pack(fill="x")

        f_name = tk.Frame(ed_fields, bg="#11141a")
        f_name.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(f_name, text=_tr("Nombre", "Name"), bg="#11141a", fg=muted, font=(ui_font, 8)).pack(anchor="w")
        n_b, _ = ui["rounded_entry"](f_name, ed_name_var, parent_bg="#11141a", font=(ui_font, 9), height=34, init_w=150)
        n_b.pack(fill="x", pady=(2, 0))

        f_web = tk.Frame(ed_fields, bg="#11141a")
        f_web.pack(side="left", padx=(0, 8))
        tk.Label(f_web, text=_tr("Puerto Web", "Web Port"), bg="#11141a", fg=muted, font=(ui_font, 8)).pack(anchor="w")
        w_b, _ = ui["rounded_entry"](f_web, ed_web_var, parent_bg="#11141a", font=(mono_font, 9), height=34, init_w=95)
        w_b.pack(pady=(2, 0))

        f_mc = tk.Frame(ed_fields, bg="#11141a")
        f_mc.pack(side="left", padx=(0, 10))
        tk.Label(f_mc, text=_tr("Puerto MC", "MC Port"), bg="#11141a", fg=muted, font=(ui_font, 8)).pack(anchor="w")
        m_b, _ = ui["rounded_entry"](f_mc, ed_mc_var, parent_bg="#11141a", font=(mono_font, 9), height=34, init_w=95)
        m_b.pack(pady=(2, 0))

        def _validate_editor(*_):
            if not editing_state["dir"]:
                return
            ok, msg = _validate_ports(ed_web_var.get(), ed_mc_var.get(), exclude_dir=Path(editing_state["dir"]))
            ed_valid_var.set(msg)
            ed_valid_lbl.configure(fg="#3fb950" if ok else "#f59e0b")

        for v_obj in (ed_web_var, ed_mc_var):
            tid = v_obj.trace_add("write", _validate_editor)
            state_holder["traces"].append((v_obj, tid))

        def _close_editor():
            editing_state["dir"] = None
            editor_wrap.pack_forget()

        def _save_editor():
            target_dir_str = editing_state["dir"]
            if not target_dir_str:
                return
            target_dir = Path(target_dir_str)
            ok, msg = _validate_ports(ed_web_var.get(), ed_mc_var.get(), exclude_dir=target_dir)
            if not ok:
                _run_dark_message_dialog(
                    _tr("Dockraft — Puertos inválidos", "Dockraft — Invalid Ports"),
                    msg,
                    [(_tr("Aceptar", "OK"), 0, True)],
                    parent=root,
                )
                return
            new_name = ed_name_var.get().strip() or target_dir.name
            new_web = int(ed_web_var.get().strip())
            new_mc = int(ed_mc_var.get().strip())
            _ensure_instance_env(target_dir, None, new_web, new_mc, server_name=new_name, update_existing=True)
            _save_launcher_config(target_dir, new_web, mc_port=new_mc, name=new_name)
            _close_editor()
            _rebuild_list()

        ed_btns = tk.Frame(ed_fields, bg="#11141a")
        ed_btns.pack(side="right", anchor="s", pady=(14, 0))
        ui["rounded_button"](
            ed_btns,
            _tr("Guardar", "Save"),
            _save_editor,
            parent_bg="#11141a",
            bg_col=ui["accent"],
            hover_col=ui["accent_hover"],
            border_col=ui["accent_border"],
            fg_col="#ffffff",
            font=(ui_font, 8, "bold"),
            padx=12,
            height=34,
            min_w=70,
        ).pack(side="left", padx=(0, 6))
        ui["rounded_button"](
            ed_btns,
            _tr("Cerrar", "Close"),
            _close_editor,
            parent_bg="#11141a",
            font=(ui_font, 8),
            padx=10,
            height=34,
            min_w=64,
        ).pack(side="left")

        # Scrollable list area for instances
        list_outer = tk.Frame(frame, bg=card)
        list_outer.pack(fill="both", expand=True)

        list_canvas = tk.Canvas(list_outer, bg=card, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=list_canvas.yview)
        list_inner = tk.Frame(list_canvas, bg=card)
        list_win = list_canvas.create_window((0, 0), window=list_inner, anchor="nw")
        list_canvas.configure(yscrollcommand=scrollbar.set)
        list_canvas.pack(side="left", fill="both", expand=True)

        def _on_list_inner_cfg(_e=None):
            list_canvas.configure(scrollregion=list_canvas.bbox("all"))

        def _on_list_canvas_cfg(event):
            list_canvas.itemconfigure(list_win, width=event.width)

        def _on_mousewheel(event):
            try:
                bbox = list_canvas.bbox("all")
                if not bbox or (bbox[3] - bbox[1]) <= list_canvas.winfo_height():
                    return
                if getattr(event, "num", None) == 4:
                    list_canvas.yview_scroll(-1, "units")
                elif getattr(event, "num", None) == 5:
                    list_canvas.yview_scroll(1, "units")
                elif getattr(event, "delta", 0):
                    step = -1 if event.delta > 0 else 1
                    list_canvas.yview_scroll(step, "units")
            except Exception:
                pass

        list_inner.bind("<Configure>", _on_list_inner_cfg)
        list_canvas.bind("<Configure>", _on_list_canvas_cfg)
        root.bind_all("<MouseWheel>", _on_mousewheel)
        root.bind_all("<Button-4>", _on_mousewheel)
        root.bind_all("<Button-5>", _on_mousewheel)

        def _open_editor_for(inst: dict):
            editing_state["dir"] = inst["dir"]
            ed_title_var.set(_tr(f"Editar puertos — {inst['name']}", f"Edit ports — {inst['name']}"))
            ed_name_var.set(inst["name"])
            ed_web_var.set(str(inst["port"]))
            ed_mc_var.set(str(inst["mc_port"]))
            _validate_editor()
            editor_wrap.pack(fill="x", pady=(0, 10), before=list_outer)
            editor_wrap.after_idle(editor_wrap._sync_height)

        def _launch_and_close(inst_dir: str, inst_port: int):
            threading.Thread(target=_open_or_launch_instance, args=(inst_dir, inst_port), daemon=True).start()
            root.after(250, root.destroy)

        def _handle_stop_instance(inst: dict):
            i_dir = Path(inst["dir"]).resolve()
            i_name = inst["name"]
            i_port = int(inst["port"])
            choice = _run_dark_message_dialog(
                _tr("Detener instancia de Dockraft", "Stop Dockraft Instance"),
                _tr(
                    f"¿Seguro que deseas detener la instancia '{i_name}'?\n\n"
                    f"Se apagará su panel web (puerto :{i_port}) y, si el servidor de Minecraft "
                    "está en ejecución dentro de esta instancia, se guardará el mundo y se cerrará.",
                    f"Are you sure you want to stop instance '{i_name}'?\n\n"
                    f"Its web panel (port :{i_port}) will shut down and, if the Minecraft server "
                    "is running inside this instance, the world will be saved and closed.",
                ),
                [(_tr("Cancelar", "Cancel"), 1, False), (_tr("Detener instancia", "Stop instance"), 0, True)],
                default_idx=0,
                parent=root,
                danger_primary=True,
            )
            if choice != 0:
                return

            def _worker():
                _stop_instance(i_dir, i_port)
                if root.winfo_exists():
                    root.after(0, _rebuild_list)

            threading.Thread(target=_worker, daemon=True).start()

        def _confirm_delete(inst: dict):
            i_dir = Path(inst["dir"]).resolve()
            i_name = inst["name"]
            b_dir = _instance_backups_dir(i_dir)
            choice = _run_dark_message_dialog(
                _tr("Eliminar instancia de Dockraft", "Delete Dockraft Instance"),
                _tr(
                    f"¿Seguro que deseas eliminar la instancia '{i_name}'?\n\n"
                    f"Se borrará la carpeta de la instancia:\n• {i_dir}\n\n"
                    f"Tus backups NO se borrarán y se conservarán en:\n• {b_dir}",
                    f"Are you sure you want to delete instance '{i_name}'?\n\n"
                    f"The instance folder will be deleted:\n• {i_dir}\n\n"
                    f"Your backups will NOT be deleted and will remain safe at:\n• {b_dir}",
                ),
                [(_tr("Cancelar", "Cancel"), 1, False), (_tr("Eliminar instancia", "Delete instance"), 0, True)],
                default_idx=0,
                parent=root,
                danger_primary=True,
            )
            if choice == 0:
                if editing_state.get("dir") == str(i_dir):
                    _close_editor()
                ok, msg = _delete_instance(i_dir)
                _rebuild_list()
                if not ok:
                    _run_dark_message_dialog(
                        _tr("Dockraft — Aviso al eliminar", "Dockraft — Delete Warning"),
                        msg,
                        [(_tr("Aceptar", "OK"), 0, True)],
                        parent=root,
                    )

        def _rebuild_list():
            for child in list_inner.winfo_children():
                child.destroy()
            status_widgets.clear()
            instances = _discover_all_instances()
            if not instances:
                empty_wrap, empty_in = ui["rounded_panel"](list_inner, card, panel, ui["border"], radius=12, padx=18, pady=24)
                empty_wrap.pack(fill="x", pady=8)
                tk.Label(
                    empty_in,
                    text=_tr(
                        "Aún no hay instancias creadas.\nHaz clic en '+ Nueva instancia' arriba a la derecha para crear la primera.",
                        "No instances have been created yet.\nClick '+ New instance' in the top right to create your first one.",
                    ),
                    bg=panel,
                    fg=muted,
                    font=(ui_font, 9),
                    justify="center",
                ).pack(fill="x")
                return

            if len(instances) > 4:
                scrollbar.pack(side="right", fill="y", padx=(4, 0))
            else:
                scrollbar.pack_forget()

            for inst in instances:
                i_dir = inst["dir"]
                i_name = inst["name"]
                i_port = int(inst["port"])
                i_mc = int(inst["mc_port"])
                online = _is_port_open(i_port)
                b_dir = _instance_backups_dir(Path(i_dir))

                row_wrap, row_in = ui["rounded_panel"](list_inner, card, panel, ui["border"], radius=12, padx=14, pady=11)
                row_wrap.pack(fill="x", pady=(0, 8))

                right = tk.Frame(row_in, bg=panel)
                right.pack(side="right", padx=(12, 0))

                open_btn = ui["rounded_button"](
                    right,
                    _tr("Abrir Web", "Open Web") if online else _tr("Iniciar y Abrir", "Start & Open"),
                    lambda d=i_dir, p=i_port: _launch_and_close(d, p),
                    parent_bg=panel,
                    bg_col=ui["accent"],
                    hover_col=ui["accent_hover"],
                    border_col=ui["accent_border"],
                    fg_col="#ffffff",
                    font=(ui_font, 8, "bold"),
                    padx=12,
                    height=32,
                    min_w=96,
                )
                open_btn.pack(side="right", padx=(6, 0))

                stop_btn = ui["rounded_button"](
                    right,
                    _tr("Detener", "Stop"),
                    lambda item=inst: _handle_stop_instance(item),
                    parent_bg=panel,
                    bg_col="#332411",
                    hover_col="#4d3518",
                    border_col="#b45309",
                    fg_col="#fcd34d",
                    font=(ui_font, 8, "bold"),
                    padx=10,
                    height=32,
                    min_w=68,
                )
                if online:
                    stop_btn.pack(side="right", padx=(6, 0))

                ui["rounded_button"](
                    right,
                    _tr("Puertos", "Ports"),
                    lambda item=inst: _open_editor_for(item),
                    parent_bg=panel,
                    font=(ui_font, 8),
                    padx=10,
                    height=32,
                    min_w=64,
                ).pack(side="right", padx=(6, 0))

                ui["rounded_button"](
                    right,
                    _tr("Archivos", "Files"),
                    lambda d=i_dir: _open_path(Path(d)),
                    parent_bg=panel,
                    font=(ui_font, 8),
                    padx=10,
                    height=32,
                    min_w=64,
                ).pack(side="right", padx=(6, 0))

                ui["rounded_button"](
                    right,
                    _tr("Borrar", "Delete"),
                    lambda item=inst: _confirm_delete(item),
                    parent_bg=panel,
                    bg_col="#2d1619",
                    hover_col="#4c1d24",
                    border_col="#7f1d1d",
                    fg_col="#fca5a5",
                    font=(ui_font, 8, "bold"),
                    padx=10,
                    height=32,
                    min_w=60,
                ).pack(side="right")

                left = tk.Frame(row_in, bg=panel)
                left.pack(side="left", fill="x", expand=True)

                top_line = tk.Frame(left, bg=panel)
                top_line.pack(fill="x", anchor="w")
                dot_lbl = tk.Label(
                    top_line,
                    text=_tr("● En línea", "● Online") if online else _tr("○ Detenida", "○ Stopped"),
                    bg=panel,
                    fg="#3fb950" if online else muted,
                    font=(ui_font, 8, "bold"),
                )
                dot_lbl.pack(side="left", padx=(0, 8))
                name_lbl = tk.Label(
                    top_line,
                    text=i_name,
                    bg=panel,
                    fg=fg,
                    font=(ui_font, 11, "bold"),
                )
                name_lbl.pack(side="left", padx=(0, 10))
                ports_lbl = tk.Label(
                    top_line,
                    text=f"Web :{i_port}   •   Minecraft :{i_mc}",
                    bg=panel,
                    fg="#94a3b8",
                    font=(mono_font, 8, "bold"),
                )
                ports_lbl.pack(side="left")

                sub_lbl = tk.Label(
                    left,
                    text=_tr(f"Instancia: {i_dir}\nBackups:  {b_dir}", f"Instance: {i_dir}\nBackups:  {b_dir}"),
                    bg=panel,
                    fg=muted,
                    font=(mono_font, 8),
                    justify="left",
                    anchor="w",
                    wraplength=420,
                )
                sub_lbl.pack(fill="x", anchor="w", pady=(3, 0))

                def _on_left_cfg(event, lbl=sub_lbl, rw=row_wrap):
                    lbl.configure(wraplength=max(200, event.width - 6))
                    rw.after_idle(rw._sync_height)

                left.bind("<Configure>", _on_left_cfg, add="+")

                status_widgets.append((i_port, dot_lbl, open_btn, stop_btn))
                row_wrap.after_idle(row_wrap._sync_height)

        _rebuild_list()

    _build_content()

    def _poll_live_status():
        if not root.winfo_exists():
            return
        for p_num, d_lbl, o_btn, s_btn in status_widgets:
            is_up = _is_port_open(p_num)
            d_lbl.configure(
                text=_tr("● En línea", "● Online") if is_up else _tr("○ Detenida", "○ Stopped"),
                fg="#3fb950" if is_up else muted,
            )
            o_btn._set_text(_tr("Abrir Web", "Open Web") if is_up else _tr("Iniciar y Abrir", "Start & Open"))
            if is_up and not s_btn.winfo_ismapped():
                s_btn.pack(side="right", padx=(6, 0), after=o_btn)
            elif not is_up and s_btn.winfo_ismapped():
                s_btn.pack_forget()
        root.after(2500, _poll_live_status)

    root.after(2500, _poll_live_status)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.update_idletasks()
    w, h = 920, 550
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(880, 500)
    _apply_dark_titlebar(root, allow_maximize=True)
    _close_splash()
    root.mainloop()


def _run_settings_dialog(first_run: bool = False) -> bool:
    """
    Shows the Tkinter Global & .env Configuration window ('Editar configuraciones' / 'Edit settings')
    so the user never needs to edit .env in a text editor.
    Synchronizes credentials, default host, session timeout, and instances_root across all instances.
    Returns True if settings were saved, False if cancelled.
    """
    import tkinter as tk
    from tkinter import filedialog

    _enable_win_dpi_and_app_id()
    cfg = _load_launcher_config()
    cur_user, cur_pw = _get_global_credentials()
    cur_root = str(_default_instances_root())
    cur_timeout = str(cfg.get("session_timeout_minutes") or 60)
    cur_lan = str(cfg.get("default_host") or "127.0.0.1") == "0.0.0.0"

    saved_ok = {"val": False}
    root = tk.Tk(className="Dockraft")
    ui = _build_tk_primitives(root)
    card = ui["card"]
    panel = ui["panel"]
    fg = ui["fg"]
    muted = ui["muted"]
    ui_font = ui["ui_font"]
    mono_font = ui["mono_font"]

    root_var = tk.StringVar(value=cur_root)
    user_var = tk.StringVar(value=cur_user or "admin")
    timeout_var = tk.StringVar(value=cur_timeout)
    pw_var = tk.StringVar(value=cur_pw or secrets.token_urlsafe(10))
    lan_var = tk.BooleanVar(value=cur_lan)
    pw_visible = {"val": bool(first_run)}
    state_holder: dict[str, Any] = {"outer": None}

    def _save_settings(event=None):
        new_root_str = root_var.get().strip()
        new_user = user_var.get().strip() or "admin"
        new_pw = pw_var.get().strip()
        t_raw = timeout_var.get().strip()
        if not new_root_str:
            _run_dark_message_dialog(
                "Dockraft",
                _tr("La carpeta principal no puede estar vacía.", "Main folder cannot be empty."),
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )
            return
        if not new_pw or len(new_pw) < 4:
            _run_dark_message_dialog(
                "Dockraft",
                _tr("La contraseña debe tener al menos 4 caracteres.", "Password must be at least 4 characters long."),
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )
            return
        if not t_raw.isdigit() or not (5 <= int(t_raw) <= 10080):
            _run_dark_message_dialog(
                "Dockraft",
                _tr("El tiempo de sesión debe estar entre 5 y 10080 minutos.", "Session timeout must be between 5 and 10080 minutes."),
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )
            return

        new_host = "0.0.0.0" if lan_var.get() else "127.0.0.1"
        new_timeout = int(t_raw)
        new_root = Path(new_root_str).expanduser().resolve()
        if new_root.name.lower() != "instancias":
            new_root = (new_root / "instancias").resolve()
        cfg_data = _load_launcher_config()
        _set_main_root(new_root.parent)
        new_root.mkdir(parents=True, exist_ok=True)
        (new_root.parent / "backups").mkdir(parents=True, exist_ok=True)

        cfg_data["instances_root"] = str(new_root)
        cfg_data["default_admin_user"] = new_user
        cfg_data["default_admin_password"] = new_pw
        cfg_data["default_host"] = new_host
        cfg_data["session_timeout_minutes"] = new_timeout
        cfg_data["language"] = _get_ui_lang()
        cfg_path = _launcher_config_path()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg_data, indent=2, ensure_ascii=False), encoding="utf-8")

        for inst in _discover_all_instances():
            i_dir = Path(inst["dir"])
            if i_dir.is_dir():
                b_dir = _instance_backups_dir(i_dir)
                _migrate_legacy_backups(i_dir, b_dir)
                _update_env_file(
                    i_dir / ".env",
                    {
                        "ADMIN_USER": new_user,
                        "ADMIN_PASSWORD": new_pw,
                        "HOST": new_host,
                        "SESSION_TIMEOUT_MINUTES": str(new_timeout),
                        "BACKUPS_DIR": str(b_dir),
                    },
                )
        saved_ok["val"] = True
        root.destroy()

    def _build_content():
        if state_holder["outer"] is not None:
            state_holder["outer"].destroy()

        root.title(
            _tr("Dockraft — Configuración Inicial", "Dockraft — Initial Configuration")
            if first_run
            else _tr("Dockraft — Editar Configuraciones", "Dockraft — Edit Settings")
        )

        outer_wrap, frame = ui["rounded_panel"](root, ui["bg"], card, ui["border"], radius=16, padx=22, pady=20, expand=True)
        outer_wrap.pack(fill="both", expand=True, padx=14, pady=14)
        state_holder["outer"] = outer_wrap

        header = tk.Frame(frame, bg=card)
        header.pack(fill="x", pady=(0, 14))
        if ui["header_logo"] is not None:
            lbl_logo = tk.Label(header, image=ui["header_logo"], bg=card)
            lbl_logo.image = ui["header_logo"]
            lbl_logo.pack(side="left", padx=(0, 12))
        ui["lang_button"](header, _build_content).pack(side="right", padx=(8, 0))
        title_box = tk.Frame(header, bg=card)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text=(
                _tr("Bienvenido a Dockraft — Configuración Global", "Welcome to Dockraft — Global Configuration")
                if first_run
                else _tr("Configuración Global de Dockraft", "Dockraft Global Settings")
            ),
            bg=card,
            fg=fg,
            font=(ui_font, 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text=(
                _tr(
                    "Elige tu idioma (🌐 arriba a la derecha), carpeta principal y credenciales antes de crear tu primera instancia.",
                    "Choose your language (🌐 top right), main folder, and credentials before creating your first instance.",
                )
                if first_run
                else _tr(
                    "Los cambios de idioma, usuario, contraseña y sesión se aplicarán a todas tus instancias.",
                    "Language, user, password, and session changes will apply to all your instances.",
                )
            ),
            bg=card,
            fg=muted,
            font=(ui_font, 9),
        ).pack(anchor="w", pady=(2, 0))

        # Main instances folder
        tk.Label(
            frame,
            text=_tr("Carpeta principal de instancias", "Main instances folder"),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        dir_row = tk.Frame(frame, bg=card)
        dir_row.pack(fill="x", pady=(5, 11))
        dir_box, _ = ui["rounded_entry"](dir_row, root_var, font=(mono_font, 9), init_w=340)
        dir_box.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _browse_root():
            chosen = filedialog.askdirectory(
                initialdir=root_var.get() or cur_root,
                title=_tr("Selecciona la carpeta de instancias", "Select the instances folder"),
            )
            if chosen:
                p = Path(chosen).resolve()
                if p.name.lower() != "instancias":
                    p = p / "instancias"
                root_var.set(str(p))

        ui["rounded_button"](dir_row, _tr("Cambiar...", "Change..."), _browse_root, padx=14, height=38).pack(side="right")

        # Admin user + Session timeout row
        row_u = tk.Frame(frame, bg=card)
        row_u.pack(fill="x", pady=(0, 11))
        c_u = tk.Frame(row_u, bg=card)
        c_u.pack(side="left", fill="x", expand=True, padx=(0, 8))
        c_t = tk.Frame(row_u, bg=card)
        c_t.pack(side="left", fill="x", expand=True)

        tk.Label(
            c_u,
            text=_tr("Usuario Administrador (Global)", "Administrator User (Global)"),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        u_box, _ = ui["rounded_entry"](c_u, user_var, font=(mono_font, 10), init_w=160)
        u_box.pack(fill="x", pady=(5, 0))

        tk.Label(
            c_t,
            text=_tr("Expiración de sesión (minutos)", "Session timeout (minutes)"),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        t_box, _ = ui["rounded_entry"](c_t, timeout_var, font=(mono_font, 10), init_w=120)
        t_box.pack(fill="x", pady=(5, 0))

        # Global Password row with Show/Hide & Generate
        tk.Label(
            frame,
            text=_tr(
                "Contraseña global del panel (se auto-rellena al abrir instancias)",
                "Global panel password (auto-filled when opening instances)",
            ),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        pw_row = tk.Frame(frame, bg=card)
        pw_row.pack(fill="x", pady=(5, 11))
        pw_box, pw_entry = ui["rounded_entry"](
            pw_row,
            pw_var,
            font=(mono_font, 10),
            init_w=240,
            show="" if pw_visible["val"] else "•",
        )
        pw_box.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _toggle_pw():
            pw_visible["val"] = not pw_visible["val"]
            pw_entry.configure(show="" if pw_visible["val"] else "•")
            toggle_pw_btn._set_text(_tr("Ocultar", "Hide") if pw_visible["val"] else _tr("Mostrar", "Show"))

        ui["rounded_button"](pw_row, _tr("Generar", "Generate"), lambda: pw_var.set(secrets.token_urlsafe(10)), padx=12, height=38).pack(side="right")
        toggle_pw_btn = ui["rounded_button"](
            pw_row,
            _tr("Ocultar", "Hide") if pw_visible["val"] else _tr("Mostrar", "Show"),
            _toggle_pw,
            padx=12,
            height=38,
        )
        toggle_pw_btn.pack(side="right", padx=(0, 6))

        ui["rounded_checkbox"](
            frame,
            _tr(
                "Permitir acceso al panel desde red local (0.0.0.0) en todas las instancias",
                "Allow panel access from local network (0.0.0.0) across all instances",
            ),
            lan_var,
        ).pack(anchor="w", pady=(2, 10))

        # Desktop & Network Integration row
        tk.Label(
            frame,
            text=_tr("Integración con el Escritorio y Red", "Desktop & Network Integration"),
            bg=card,
            fg=fg,
            font=(ui_font, 9, "bold"),
        ).pack(anchor="w")
        desk_row = tk.Frame(frame, bg=card)
        desk_row.pack(fill="x", pady=(5, 11))

        def _on_shortcut():
            ok, msg = _create_desktop_shortcut()
            _run_dark_message_dialog(
                _tr("Dockraft — Acceso Directo", "Dockraft — Shortcut") if ok else _tr("Dockraft — Error", "Dockraft — Error"),
                msg,
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )

        def _on_firewall():
            ok, msg = _configure_firewall_ports()
            _run_dark_message_dialog(
                _tr("Dockraft — Firewall Configurado", "Dockraft — Firewall Configured") if ok else "Dockraft — Firewall",
                msg,
                [(_tr("Aceptar", "OK"), 0, True)],
                parent=root,
            )

        ui["rounded_button"](
            desk_row,
            _tr("Crear acceso directo (Escritorio / Menú Inicio)", "Create shortcut (Desktop / Start Menu)"),
            _on_shortcut,
            font=(ui_font, 8, "bold"),
            padx=14,
            height=36,
        ).pack(side="left", padx=(0, 8))

        ui["rounded_button"](
            desk_row,
            _tr("Abrir puertos en Firewall", "Open ports in Firewall"),
            _on_firewall,
            font=(ui_font, 8, "bold"),
            padx=14,
            height=36,
        ).pack(side="left")

        info_wrap, info_in = ui["rounded_panel"](frame, card, panel, ui["border"], radius=12, padx=14, pady=9)
        info_wrap.pack(fill="x", pady=(0, 12))
        inst_count = len(_discover_all_instances())
        tk.Label(
            info_in,
            text=_tr(
                f"ℹ Se sincronizarán los archivos .env de tus {inst_count} instancia(s) automáticamente al guardar.",
                f"ℹ The .env files of your {inst_count} instance(s) will be synchronized automatically upon saving.",
            ),
            bg=panel,
            fg="#58a6ff",
            font=(ui_font, 8),
            anchor="w",
        ).pack(fill="x", anchor="w")

        btn_row = tk.Frame(frame, bg=card)
        btn_row.pack(fill="x", side="bottom")

        ui["rounded_button"](
            btn_row,
            _tr("Guardar y Continuar", "Save & Continue") if first_run else _tr("Guardar Configuración", "Save Settings"),
            _save_settings,
            bg_col=ui["accent"],
            hover_col=ui["accent_hover"],
            border_col=ui["accent_border"],
            fg_col="#ffffff",
            font=(ui_font, 10, "bold"),
            radius=11,
            padx=18,
            height=40,
        ).pack(side="right")
        ui["rounded_button"](btn_row, _tr("Cancelar", "Cancel"), root.destroy, radius=11, padx=16, height=40).pack(side="right", padx=(0, 8))

        root.update_idletasks()
        info_wrap._sync_height()
        root.update_idletasks()

    _build_content()
    root.bind("<Return>", _save_settings)
    root.bind("<Escape>", lambda _e: root.destroy())
    w = max(650, state_holder["outer"].winfo_reqwidth() + 72)
    h = max(515, state_holder["outer"].winfo_reqheight() + 72)
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(w, h)
    _apply_dark_titlebar(root, allow_maximize=True)
    _close_splash()
    root.mainloop()
    return saved_ok["val"]


def _handle_new_instance_flow() -> None:
    """Runs the Nueva Instancia wizard, writes .env & config, starts the instance in background, and opens its web."""
    cfg = _load_launcher_config()
    sug_web, sug_mc = _suggest_next_ports(cfg)
    admin_user, admin_pw = _get_global_credentials()
    instances = _discover_all_instances()
    default_name = _tr(f"Servidor {len(instances) + 1}", f"Server {len(instances) + 1}") if instances else "Survival"
    res = _run_setup_dialog(
        _default_instances_root(),
        initial_name=default_name,
        initial_port=sug_web,
        initial_mc_port=sug_mc,
        initial_user=admin_user,
        initial_password=admin_pw,
    )
    if not res:
        return
    inst_dir = res["instance_dir"]
    _, pw = _ensure_instance_env(
        inst_dir,
        res["host"],
        res["port"],
        res["mc_port"],
        res["admin_user"],
        res["admin_password"],
        server_name=res["server_name"],
        update_existing=True,
    )
    _save_launcher_config(
        inst_dir,
        res["port"],
        mc_port=res["mc_port"],
        name=res["server_name"],
        instances_root=res["instances_root"],
        default_user=res["admin_user"],
        default_password=pw or res["admin_password"],
        default_host=res["host"],
    )
    _open_or_launch_instance(inst_dir, res["port"])


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    check_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((check_host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _parse_semver(ver: str) -> tuple[int, ...]:
    nums = []
    for part in str(ver).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    return tuple(nums)


def _fetch_latest_version_info() -> tuple[str, str]:
    import urllib.request

    latest_ver = ""
    release_url = "https://github.com/GMS-EC/dockraft/releases/latest"

    # 1. Check latest GitHub Release tag
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/GMS-EC/dockraft/releases/latest",
            headers={"User-Agent": "Dockraft-Desktop-Launcher"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name", "")).strip().lstrip("vV")
        if tag:
            latest_ver = tag
        if data.get("html_url"):
            release_url = str(data["html_url"])
    except Exception:
        pass

    # 2. Also check remote CHANGELOG.md on GitHub so version detection is always synchronized with CHANGELOG.md
    for branch in ("main", "master"):
        try:
            chg_req = urllib.request.Request(
                f"https://raw.githubusercontent.com/GMS-EC/dockraft/{branch}/CHANGELOG.md",
                headers={"User-Agent": "Dockraft-Desktop-Launcher"},
            )
            with urllib.request.urlopen(chg_req, timeout=6) as resp:
                chg_text = resp.read().decode("utf-8", errors="replace")
            for line in chg_text.splitlines():
                m = re.match(r"^##\s+\[(\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?)\]", line.strip())
                if m:
                    remote_chg_ver = m.group(1)
                    if not latest_ver or _parse_semver(remote_chg_ver) > _parse_semver(latest_ver):
                        latest_ver = remote_chg_ver
                    break
            break
        except Exception:
            continue

    return latest_ver, release_url


def _run_about_dialog() -> None:
    """Native dark window displaying Dockraft credits, GPLv3 license, version, and update checker."""
    try:
        import tkinter as tk
    except Exception:
        return

    _enable_win_dpi_and_app_id()
    cur_ver = _get_app_version().strip().lstrip("vV")

    root = tk.Tk(className="Dockraft")
    ui = _build_tk_primitives(root)
    card = ui["card"]
    panel = ui["panel"]
    fg = ui["fg"]
    muted = ui["muted"]
    ui_font = ui["ui_font"]

    state_holder: dict[str, Any] = {"outer": None}

    def _build_content():
        if state_holder["outer"] is not None:
            state_holder["outer"].destroy()

        root.title(_tr("Dockraft — Acerca de", "Dockraft — About"))

        outer_wrap, frame = ui["rounded_panel"](root, ui["bg"], card, ui["border"], radius=16, padx=22, pady=20, expand=True)
        outer_wrap.pack(fill="both", expand=True, padx=14, pady=14)
        state_holder["outer"] = outer_wrap

        # Header with logo & title
        hdr = tk.Frame(frame, bg=card)
        hdr.pack(fill="x", pady=(0, 14))
        if ui["header_logo"] is not None:
            lbl_logo = tk.Label(hdr, image=ui["header_logo"], bg=card)
            lbl_logo.image = ui["header_logo"]
            lbl_logo.pack(side="left", padx=(0, 12))

        title_box = tk.Frame(hdr, bg=card)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="Dockraft",
            bg=card,
            fg=fg,
            font=(ui_font, 15, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_box,
            text=_tr(
                f"Versión instalada: v{cur_ver}  •  Gestor de Servidores Minecraft",
                f"Installed version: v{cur_ver}  •  Minecraft Server Manager",
            ),
            bg=card,
            fg=ui["accent"],
            font=(ui_font, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Credits & License rounded panel
        info_wrap, info_box = ui["rounded_panel"](frame, card, panel, ui["border"], radius=12, padx=16, pady=12)
        info_wrap.pack(fill="x", pady=(0, 12))

        tk.Label(
            info_box,
            text=_tr("CRÉDITOS Y AUTORÍA", "CREDITS & AUTHORSHIP"),
            bg=panel,
            fg=ui["accent"],
            font=(ui_font, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            info_box,
            text=_tr(
                "Desarrollado por Marcus Mayorga (@GMS-EC)\nSitio web: gmsec.cc  •  GitHub: github.com/GMS-EC/dockraft",
                "Developed by Marcus Mayorga (@GMS-EC)\nWebsite: gmsec.cc  •  GitHub: github.com/GMS-EC/dockraft",
            ),
            bg=panel,
            fg=fg,
            font=(ui_font, 9),
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(2, 10))

        tk.Frame(info_box, bg=ui["border"], height=1).pack(fill="x", pady=(0, 8))

        tk.Label(
            info_box,
            text=_tr("LICENCIA DE SOFTWARE LIBRE", "FREE SOFTWARE LICENSE"),
            bg=panel,
            fg="#58a6ff",
            font=(ui_font, 8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            info_box,
            text=_tr(
                "Distribuido bajo la licencia GNU General Public License v3.0 (GPLv3).\n"
                "Software libre y de código abierto: puedes usar, estudiar, compartir\n"
                "y modificar este programa bajo los términos de la licencia GPLv3.",
                "Distributed under the GNU General Public License v3.0 (GPLv3).\n"
                "Free and open-source software: you are free to use, study, share,\n"
                "and modify this program under the terms of the GPLv3 license.",
            ),
            bg=panel,
            fg=muted,
            font=(ui_font, 8),
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Update check rounded panel
        upd_wrap, upd_box = ui["rounded_panel"](frame, card, panel, ui["border"], radius=12, padx=16, pady=12)
        upd_wrap.pack(fill="x", pady=(0, 16))

        tk.Label(
            upd_box,
            text=_tr("ACTUALIZACIONES", "UPDATES"),
            bg=panel,
            fg=ui["accent"],
            font=(ui_font, 8, "bold"),
            anchor="w",
        ).pack(fill="x")

        status_var = tk.StringVar(value=_tr("Pulsa para buscar actualizaciones.", "Click to check for updates."))
        lbl_status = tk.Label(
            upd_box,
            textvariable=status_var,
            bg=panel,
            fg=muted,
            font=(ui_font, 9),
            justify="left",
            anchor="w",
            wraplength=420,
        )
        lbl_status.pack(fill="x", pady=(4, 0))

        checking_state = {"busy": False}

        def _do_check_updates():
            if checking_state["busy"]:
                return
            checking_state["busy"] = True
            status_var.set(_tr("Buscando actualizaciones...", "Checking for updates..."))
            lbl_status.configure(fg="#fbbf24")
            upd_wrap._sync_height()

            def _worker():
                latest_ver, release_url = _fetch_latest_version_info()

                def _update_ui():
                    checking_state["busy"] = False
                    if not latest_ver:
                        status_var.set(_tr("No se pudo conectar con GitHub.", "Could not connect to GitHub."))
                        lbl_status.configure(fg="#f87171")
                        upd_wrap._sync_height()
                        return
                    if _parse_semver(latest_ver) > _parse_semver(cur_ver):
                        status_var.set(_tr(f"¡Nueva versión disponible: v{latest_ver}!", f"New version available: v{latest_ver}!"))
                        lbl_status.configure(fg=ui["accent"])
                        upd_wrap._sync_height()
                        msg = _tr(
                            f"Hay una nueva versión disponible: v{latest_ver}\nVersión instalada: v{cur_ver}\n\n¿Deseas abrir la página de descarga en GitHub?",
                            f"A new version is available: v{latest_ver}\nInstalled version: v{cur_ver}\n\nWould you like to open the download page on GitHub?",
                        )
                        if _prompt_dark_dialog(_tr("Dockraft — Actualización Disponible", "Dockraft — Update Available"), msg, "yesno") == 6:
                            _open_url(release_url)
                    else:
                        status_var.set(_tr(f"Estás al día (v{cur_ver}).", f"You are up to date (v{cur_ver})."))
                        lbl_status.configure(fg=ui["accent"])
                        upd_wrap._sync_height()

                try:
                    root.after(0, _update_ui)
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()

        # Action buttons row
        btn_row = tk.Frame(frame, bg=card)
        btn_row.pack(fill="x", side="bottom")

        ui["rounded_button"](
            btn_row,
            _tr("Buscar actualizaciones", "Check for updates"),
            _do_check_updates,
            bg_col=ui["accent"],
            hover_col=ui["accent_hover"],
            border_col=ui["accent_border"],
            fg_col="#ffffff",
            font=(ui_font, 9, "bold"),
            radius=10,
            padx=14,
            height=38,
        ).pack(side="left", padx=(0, 8))

        ui["rounded_button"](
            btn_row,
            "GitHub",
            lambda: _open_url("https://github.com/GMS-EC/dockraft"),
            radius=10,
            padx=14,
            height=38,
        ).pack(side="left")

        ui["rounded_button"](
            btn_row,
            _tr("Cerrar", "Close"),
            root.destroy,
            radius=10,
            padx=16,
            height=38,
        ).pack(side="right")

        root.update_idletasks()
        info_wrap._sync_height()
        upd_wrap._sync_height()
        root.update_idletasks()

    _build_content()
    root.bind("<Escape>", lambda _e: root.destroy())
    w = max(560, state_holder["outer"].winfo_reqwidth() + 72)
    h = max(440, state_holder["outer"].winfo_reqheight() + 72)
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(w, h)
    _apply_dark_titlebar(root, allow_maximize=False)
    _close_splash()
    root.mainloop()


def _create_tray_image():
    from PIL import Image, ImageDraw

    icon_png = _find_icon_png()
    if icon_png:
        try:
            return Image.open(icon_png).convert("RGBA")
        except Exception:
            pass

    img = Image.new("RGBA", (64, 64), (20, 22, 25, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(27, 30, 35, 255), outline=(60, 163, 116, 255), width=4)
    draw.rectangle((18, 18, 46, 46), fill=(60, 163, 116, 255))
    draw.rectangle((26, 26, 38, 38), fill=(20, 22, 25, 255))
    return img


def _find_all_instance_mc_processes() -> list:
    """Finds any running Minecraft (Java/Bedrock) server process belonging to any Dockraft instance."""
    import psutil

    all_dirs = [str(Path(i["dir"]).resolve()).lower() for i in _discover_all_instances()]
    root_str = str(_default_instances_root()).lower()
    found = []
    cur_pid = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == cur_pid:
                continue
            name = (p.info.get("name") or "").lower()
            cmd_str = " ".join(p.info.get("cmdline") or []).lower()
            try:
                p_cwd = p.cwd().lower()
            except Exception:
                p_cwd = ""
            if not any(k in name or k in cmd_str for k in ("java", "bedrock_server")):
                continue
            if (root_str and (root_str in p_cwd or root_str in cmd_str)) or any(d in p_cwd or d in cmd_str for d in all_dirs):
                found.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return found


def _terminate_all_other_dockraft_processes(stop_mc_servers: bool) -> None:
    """Terminates other background Dockraft panel processes and optionally stops running MC servers."""
    import psutil

    cur_pid = os.getpid()
    if stop_mc_servers:
        for mc_p in _find_all_instance_mc_processes():
            try:
                mc_p.terminate()
            except Exception:
                pass

    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == cur_pid:
                continue
            cmd = p.info.get("cmdline") or []
            cmd_str = " ".join(cmd).lower()
            name = (p.info.get("name") or "").lower()
            if ("launcher.py" in cmd_str or "dockraft" in name) and "--instance-dir" in cmd_str:
                p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def _handle_dialog_mode(payload_raw: str) -> int:
    try:
        data = json.loads(payload_raw)
    except Exception:
        return 1
    title = str(data.get("title", "Dockraft"))
    message = str(data.get("message", ""))
    mode = str(data.get("mode", "info"))
    if mode == "quit":
        return _run_dark_message_dialog(
            title,
            message,
            [
                (_tr("Sí, detener todo y salir", "Yes, stop all & quit"), 6, True),
                (_tr("No, dejar servidores activos", "No, leave servers running"), 7, False),
                (_tr("Cancelar", "Cancel"), 2, False),
            ],
            default_idx=2,
        )
    if mode == "yesno":
        return _run_dark_message_dialog(
            title,
            message,
            [(_tr("Sí", "Yes"), 6, True), (_tr("No", "No"), 7, False)],
            default_idx=1,
        )
    return _run_dark_message_dialog(title, message, [(_tr("Aceptar", "OK"), 0, True)], default_idx=0)


_SINGLE_INSTANCE_MUTEX = None


def _update_splash(text: str) -> None:
    try:
        import pyi_splash  # type: ignore

        if pyi_splash.is_alive():
            pyi_splash.update_text(text)
    except Exception:
        pass


def _close_splash() -> None:
    try:
        import pyi_splash  # type: ignore

        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass


def _acquire_single_instance_mutex() -> bool:
    """Acquires an OS mutex for the main launcher so double-clicking Dockraft.exe twice doesn't start duplicate processes."""
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            mutex = kernel32.CreateMutexW(None, False, "Local\\DockraftMainLauncherMutex_v1")
            last_err = kernel32.GetLastError()
            if mutex:
                _SINGLE_INSTANCE_MUTEX = mutex
            if last_err == 183:  # ERROR_ALREADY_EXISTS
                return False
        except Exception:
            pass
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Dockraft Desktop Launcher")
    parser.add_argument("--instance-dir", default=os.getenv("DOCKRAFT_INSTANCE_DIR", ""), help="Carpeta de datos de la instancia")
    parser.add_argument("--host", default=None, help="Host de escucha (por defecto 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Puerto HTTP (por defecto 8000)")
    parser.add_argument("--setup", action="store_true", help="Abrir asistente de Nueva Instancia")
    parser.add_argument("--instances-ui", action="store_true", help="Abrir ventana del Gestor de Instancias")
    parser.add_argument("--settings-ui", action="store_true", help="Abrir ventana de Configuración Global")
    parser.add_argument("--about-ui", action="store_true", help="Abrir ventana de Acerca de")
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador al iniciar")
    parser.add_argument("--headless", action="store_true", help="Ejecutar sin icono en la bandeja del sistema")
    parser.add_argument("--dialog-mode", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.dialog_mode:
        _close_splash()
        sys.exit(_handle_dialog_mode(args.dialog_mode))
    if args.instances_ui:
        _close_splash()
        _run_instances_dialog()
        return
    if args.settings_ui:
        _close_splash()
        _run_settings_dialog()
        return
    if args.about_ui:
        _close_splash()
        _run_about_dialog()
        return

    has_gui = sys.platform == "win32" or bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
    is_headless = args.headless or not has_gui
    if is_headless or args.setup:
        _close_splash()

    # Single-instance guard for the main desktop launcher
    if not is_headless and not args.instance_dir and not args.setup:
        if not _acquire_single_instance_mutex():
            _close_splash()
            if _discover_all_instances():
                _run_instances_dialog()
            return

    _update_splash(_tr("Cargando configuración de Dockraft...", "Loading Dockraft configuration..."))
    cfg = _load_launcher_config()
    existing_instances = _discover_all_instances()
    has_saved_instance = len(existing_instances) > 0
    is_first_launch = (
        not is_headless
        and not args.instance_dir
        and not args.setup
        and not has_saved_instance
        and not str(cfg.get("default_admin_password") or "").strip()
    )
    if is_first_launch:
        if not _run_settings_dialog(first_run=True):
            return
        cfg = _load_launcher_config()
        existing_instances = _discover_all_instances()
        has_saved_instance = len(existing_instances) > 0

    should_show_setup = args.setup or (not is_headless and not args.instance_dir and not has_saved_instance)

    admin_user, admin_password = _get_global_credentials()
    server_name = ""
    chosen_instances_root = None
    chosen_host = args.host
    chosen_port = args.port
    chosen_mc_port = None

    if should_show_setup:
        # If invoked via '--setup' while another instance is already running, use the standalone new-instance flow
        if args.setup and has_saved_instance:
            _handle_new_instance_flow()
            return
        sug_web, sug_mc = _suggest_next_ports(cfg)
        instances_root = _default_instances_root()
        default_name = f"Servidor {len(existing_instances) + 1}" if has_saved_instance else "Survival"
        setup_res = _run_setup_dialog(
            instances_root,
            initial_name=default_name,
            initial_port=args.port or sug_web,
            initial_mc_port=sug_mc,
            initial_user=admin_user,
            initial_password=admin_password,
        )
        if not setup_res:
            return
        server_name = setup_res["server_name"]
        chosen_instances_root = setup_res["instances_root"]
        instance_dir = setup_res["instance_dir"]
        if not chosen_host:
            chosen_host = setup_res["host"]
        chosen_port = setup_res["port"]
        chosen_mc_port = setup_res["mc_port"]
        admin_user = setup_res["admin_user"]
        admin_password = setup_res["admin_password"]
    else:
        instance_dir = Path(args.instance_dir).expanduser().resolve() if args.instance_dir else _default_instance_dir()

    os.environ["DOCKRAFT_INSTANCE_DIR"] = str(instance_dir)
    if chosen_host and (args.host or not (instance_dir / ".env").is_file()):
        os.environ["HOST"] = chosen_host
    if chosen_port and not (instance_dir / ".env").is_file():
        os.environ["PORT"] = str(chosen_port)
    if chosen_mc_port and not (instance_dir / ".env").is_file():
        os.environ["MC_PORT"] = str(chosen_mc_port)
    if server_name and not (instance_dir / ".env").is_file():
        os.environ["SERVER_NAME"] = server_name

    _, initial_pw = _ensure_instance_env(
        instance_dir,
        chosen_host,
        chosen_port,
        chosen_mc_port,
        admin_user,
        admin_password,
        server_name=server_name,
        update_existing=should_show_setup,
    )
    _ensure_stdio(instance_dir)
    _update_splash(_tr("Iniciando panel web de Dockraft...", "Starting Dockraft web panel..."))

    import uvicorn
    from app.config import settings
    from app.main import app

    bind_host = args.host or settings.host
    bind_port = args.port or settings.port
    env_mc = os.getenv("MC_PORT", "").strip()
    saved_mc_port = int(env_mc) if env_mc.isdigit() else (chosen_mc_port or 25565)
    saved_name = server_name or os.getenv("SERVER_NAME", "").strip() or instance_dir.name
    _save_launcher_config(
        instance_dir,
        bind_port,
        mc_port=saved_mc_port,
        name=saved_name,
        instances_root=chosen_instances_root,
        default_user=admin_user,
        default_password=initial_pw or admin_password,
    )

    stop_flag_path = instance_dir / ".dockraft_state" / "stop_panel.flag"
    try:
        if stop_flag_path.exists():
            stop_flag_path.unlink()
    except Exception:
        pass

    use_colors = bool(getattr(sys.stdout, "isatty", lambda: False)())
    config = uvicorn.Config(app, host=bind_host, port=bind_port, log_level="info", use_colors=use_colors)
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    def _watch_local_stop_signal():
        from app.core.process_manager import process_manager

        while server_thread.is_alive():
            if stop_flag_path.exists():
                try:
                    stop_flag_path.unlink()
                except Exception:
                    pass
                if process_manager.get_status() in ("RUNNING", "STARTING"):
                    ev_loop = getattr(app.state, "event_loop", None)
                    if ev_loop and ev_loop.is_running():
                        try:
                            fut = asyncio.run_coroutine_threadsafe(process_manager.stop_server(), ev_loop)
                            fut.result(timeout=25)
                        except Exception:
                            pass
                server.should_exit = True
                break
            time.sleep(0.3)

    threading.Thread(target=_watch_local_stop_signal, daemon=True).start()

    ready = _wait_for_port(bind_host, bind_port, timeout=15.0)
    if ready and not args.no_browser and not is_headless and should_show_setup:
        _close_splash()
        _open_url(_build_autofill_url(instance_dir, bind_port, bind_host))

    if not is_headless:
        try:
            import queue
            import pystray

            ui_queue: queue.Queue[str] = queue.Queue()

            def _menu_instances(icon, item):
                ui_queue.put("instances")

            def _menu_new_instance(icon, item):
                ui_queue.put("new_instance")

            def _menu_settings(icon, item):
                ui_queue.put("settings")

            def _menu_about(icon, item):
                ui_queue.put("about")

            def _menu_quit_all(icon, item):
                ui_queue.put("quit")

            def _do_quit_all(icon_obj) -> bool:
                from app.core.process_manager import process_manager

                active_mc = _find_all_instance_mc_processes()
                local_running = process_manager.get_status() in ("RUNNING", "STARTING")
                stop_servers = False

                if local_running or active_mc:
                    quit_msg = _tr(
                        "Hay uno o más servidores de Minecraft en ejecución.\n\n"
                        "¿Deseas detener limpiamente todos los servidores antes de cerrar Dockraft?\n\n"
                        "• Sí: Guarda los mundos, apaga los servidores y cierra todas las instancias.\n"
                        "• No: Cierra los paneles de Dockraft y deja los servidores activos.\n"
                        "• Cancelar: Mantener Dockraft abierto.",
                        "One or more Minecraft servers are currently running.\n\n"
                        "Would you like to cleanly stop all servers before closing Dockraft?\n\n"
                        "• Yes: Save worlds, shut down servers, and close all instances.\n"
                        "• No: Close Dockraft panels and leave servers running.\n"
                        "• Cancel: Keep Dockraft open.",
                    )
                    ans = _prompt_dark_dialog(
                        _tr("Dockraft — Cerrar Todas las Instancias", "Dockraft — Close All Instances"),
                        quit_msg,
                        "quit",
                    )
                    if ans == 2:
                        return False
                    stop_servers = (ans == 6)

                if stop_servers and local_running:
                    ev_loop = getattr(app.state, "event_loop", None)
                    if ev_loop and ev_loop.is_running():
                        try:
                            fut = asyncio.run_coroutine_threadsafe(process_manager.stop_server(), ev_loop)
                            fut.result(timeout=35)
                        except Exception:
                            pass

                _terminate_all_other_dockraft_processes(stop_mc_servers=stop_servers)
                server.should_exit = True
                try:
                    icon_obj.stop()
                except Exception:
                    pass
                return True

            menu = pystray.Menu(
                pystray.MenuItem(lambda _item: _tr("Instancias", "Instances"), _menu_instances, default=True),
                pystray.MenuItem(lambda _item: _tr("Nueva instancia", "New instance"), _menu_new_instance),
                pystray.MenuItem(lambda _item: _tr("Editar configuraciones", "Edit settings"), _menu_settings),
                pystray.MenuItem(lambda _item: _tr("Acerca de", "About"), _menu_about),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda _item: _tr("Salir", "Quit"), _menu_quit_all),
            )
            tray = pystray.Icon("Dockraft", _create_tray_image(), "Dockraft", menu)

            def _watch_tray_lang():
                last_lang = _get_ui_lang()
                while server_thread.is_alive():
                    cur_l = _get_ui_lang()
                    if cur_l != last_lang:
                        last_lang = cur_l
                        try:
                            tray.update_menu()
                        except Exception:
                            pass
                    time.sleep(1.0)

            threading.Thread(target=_watch_tray_lang, daemon=True).start()

            def _on_tray_ready(icon_obj):
                icon_obj.visible = True
                if ready:
                    _notify_tray(
                        icon_obj,
                        _tr(
                            f"Instancia '{saved_name}' activa en puerto :{bind_port}",
                            f"Instance '{saved_name}' active on port :{bind_port}",
                        ),
                        "Dockraft",
                    )

            threading.Thread(target=lambda: tray.run(setup=_on_tray_ready), daemon=True).start()

            # When launching Dockraft normally with existing instances, open the Instance Manager immediately
            if not should_show_setup and not args.no_browser:
                ui_queue.put("instances")
            else:
                _close_splash()

            while server_thread.is_alive():
                try:
                    cmd_action = ui_queue.get(timeout=0.3)
                except queue.Empty:
                    continue
                # Drain any duplicate clicks queued while a window was open
                while not ui_queue.empty():
                    try:
                        nxt = ui_queue.get_nowait()
                        if nxt == "quit":
                            cmd_action = "quit"
                    except queue.Empty:
                        break
                if cmd_action == "instances":
                    _run_instances_dialog()
                elif cmd_action == "new_instance":
                    _handle_new_instance_flow()
                elif cmd_action == "settings":
                    _run_settings_dialog()
                elif cmd_action == "about":
                    _run_about_dialog()
                elif cmd_action == "quit":
                    if _do_quit_all(tray):
                        break

            server.should_exit = True
            server_thread.join(timeout=5.0)
            return
        except Exception as e:
            _close_splash()
            print(f"[Dockraft] Bandeja del sistema no disponible ({e}); continuando en primer plano.", file=sys.stderr)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        server_thread.join(timeout=5.0)


if __name__ == "__main__":
    main()
