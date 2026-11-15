import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

from app.core.fs_utils import atomic_write_text

DEFAULT_MC_JAVA_PORT = 25565
DEFAULT_MC_BEDROCK_PORT = 19132
DEFAULT_MC_BEDROCK_V6_PORT = 19133


def parse_properties_text(text: str) -> Dict[str, str]:
    """Parses Java/Bedrock server.properties text into an ordered key-value dict."""
    props: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            props[key.strip()] = val.strip()
    return props


def update_properties_text(text: str, updates: Dict[str, str]) -> str:
    """Updates or appends key=value pairs in server.properties text while preserving comments and order."""
    if not updates:
        return text
    lines = text.splitlines()
    new_lines: list[str] = []
    written: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(raw)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    return "\n".join(new_lines) + "\n"


def sync_property_aliases(props: Dict[str, str]) -> None:
    """Synchronizes Java/Bedrock equivalent property keys in-place."""
    if "server-name" in props and "motd" not in props:
        props["motd"] = props["server-name"]
    elif "motd" in props and "server-name" not in props:
        props["server-name"] = props["motd"]

    if "allow-list" in props and "white-list" not in props:
        props["white-list"] = props["allow-list"]
    elif "white-list" in props and "allow-list" not in props:
        props["allow-list"] = props["white-list"]


def _bedrock_v6_port_for(mc_port: int) -> int:
    """Computes a non-conflicting Bedrock IPv6 port matching an IPv4 MC port."""
    if mc_port == DEFAULT_MC_BEDROCK_PORT:
        return DEFAULT_MC_BEDROCK_V6_PORT
    return mc_port + 1000 if mc_port <= 64535 else mc_port - 1000


def compute_port_updates(existing_text: str, mc_port: int, server_type: str = "") -> Dict[str, str]:
    """Returns server.properties key updates required so the server binds on mc_port."""
    existing = parse_properties_text(existing_text)
    s_type = (server_type or "").strip().lower()
    is_bedrock = (
        s_type == "bedrock"
        or "server-udp-ports" in existing
        or "server-portv6" in existing
        or "transport" in existing
    )
    updates: Dict[str, str] = {"server-port": str(mc_port)}
    if is_bedrock:
        if "server-udp-ports" in existing or s_type == "bedrock":
            updates["server-udp-ports"] = str(mc_port)
        if "server-portv6" in existing or s_type == "bedrock":
            updates["server-portv6"] = str(_bedrock_v6_port_for(mc_port))
    return updates


def update_server_properties_port(prop_path: Path, mc_port: int, server_type: str = "") -> Optional[int]:
    """
    Updates port keys in server.properties if the file exists.
    Returns the previous server-port integer if found, else None.
    """
    if not prop_path.is_file():
        return None
    try:
        text = prop_path.read_text(encoding="utf-8", errors="replace")
        existing = parse_properties_text(text)
        prev_raw = existing.get("server-port", "").strip()
        prev_port = int(prev_raw) if prev_raw.isdigit() else None
        updates = compute_port_updates(text, mc_port, server_type=server_type)
        new_text = update_properties_text(text, updates)
        if new_text != text:
            atomic_write_text(prop_path, new_text)
        return prev_port
    except Exception:
        return None


def _parse_env_mc_port(env_path: Path) -> Optional[int]:
    if not env_path.is_file():
        return None
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == "MC_PORT":
                val = val.strip().strip('"').strip("'")
                if val.isdigit() and 1 <= int(val) <= 65535:
                    return int(val)
    except Exception:
        pass
    return None


def read_instance_mc_port(instance_dir: Optional[Path] = None) -> Optional[int]:
    """
    Resolves the instance's configured MC_PORT from instance_dir/.env first
    (always re-reading disk so launcher updates apply cleanly) then os.environ.
    Returns None if MC_PORT is not configured (e.g. Docker Compose defaults).
    """
    if instance_dir is not None:
        env_file_port = _parse_env_mc_port(Path(instance_dir) / ".env")
        if env_file_port is not None:
            os.environ["MC_PORT"] = str(env_file_port)
            return env_file_port

    env_mc = os.getenv("MC_PORT", "").strip()
    if env_mc.isdigit() and 1 <= int(env_mc) <= 65535:
        return int(env_mc)
    return None


def update_env_mc_port(instance_dir: Optional[Path], mc_port: int) -> bool:
    """
    Synchronizes MC_PORT into instance_dir/.env and launcher_config.json if
    instance_dir is a managed Dockraft desktop instance with an existing .env.
    """
    if instance_dir is None or not (1 <= int(mc_port) <= 65535):
        return False
    inst = Path(instance_dir).resolve()
    env_path = inst / ".env"
    if not env_path.is_file():
        return False
    try:
        lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines: list[str] = []
        found = False
        for raw in lines:
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k == "MC_PORT":
                    new_lines.append(f"MC_PORT={mc_port}")
                    found = True
                    continue
            new_lines.append(raw)
        if not found:
            new_lines.append(f"MC_PORT={mc_port}")
        atomic_write_text(env_path, "\n".join(new_lines) + "\n")
        os.environ["MC_PORT"] = str(mc_port)
    except Exception:
        return False

    # Best-effort sync to launcher_config.json if located at the main folder
    for candidate_root in (inst.parent.parent, inst.parent):
        cfg_path = candidate_root / "launcher_config.json"
        if cfg_path.is_file():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                changed = False
                for entry in data.get("instances", []):
                    if isinstance(entry, dict) and entry.get("dir"):
                        try:
                            if Path(str(entry["dir"])).resolve() == inst:
                                entry["mc_port"] = int(mc_port)
                                changed = True
                        except Exception:
                            pass
                if changed:
                    atomic_write_text(cfg_path, json.dumps(data, indent=2, ensure_ascii=False))
                break
            except Exception:
                pass
    return True


def ensure_initial_server_properties(
    data_dir: Path,
    server_type: str = "paper",
    server_name: str = "Mi Servidor Dockraft",
    instance_dir: Optional[Path] = None,
    sync_initial_defaults: bool = False,
) -> None:
    """
    Guarantees server.properties exists and matches the instance's configured MC port
    and safe open-join defaults (whitelist / allow-list disabled on initial creation).
    """
    prop_file = Path(data_dir) / "server.properties"
    s_type = (server_type or "paper").strip().lower()
    s_name = (server_name or "Mi Servidor Dockraft").strip() or "Mi Servidor Dockraft"
    configured_port = read_instance_mc_port(instance_dir)
    target_port = configured_port if configured_port is not None else (
        DEFAULT_MC_BEDROCK_PORT if s_type == "bedrock" else DEFAULT_MC_JAVA_PORT
    )

    if not prop_file.exists():
        try:
            if s_type == "bedrock":
                v6_port = _bedrock_v6_port_for(target_port)
                content = (
                    f"# Minecraft Bedrock server properties - Dockraft\n"
                    f"server-name={s_name}\n"
                    f"motd={s_name}\n"
                    f"gamemode=survival\n"
                    f"difficulty=easy\n"
                    f"allow-cheats=false\n"
                    f"max-players=10\n"
                    f"online-mode=true\n"
                    f"allow-list=false\n"
                    f"white-list=false\n"
                    f"server-port={target_port}\n"
                    f"server-portv6={v6_port}\n"
                    f"server-udp-ports={target_port}\n"
                    f"view-distance=32\n"
                    f"tick-distance=4\n"
                )
            else:
                content = (
                    f"# Minecraft server properties - Dockraft\n"
                    f"server-port={target_port}\n"
                    f"motd={s_name}\n"
                    f"server-name={s_name}\n"
                    f"online-mode=true\n"
                    f"white-list=false\n"
                    f"enforce-whitelist=false\n"
                    f"max-players=20\n"
                    f"difficulty=easy\n"
                    f"gamemode=survival\n"
                    f"view-distance=10\n"
                    f"simulation-distance=8\n"
                )
            atomic_write_text(prop_file, content)
        except Exception:
            pass
        return

    try:
        existing_text = prop_file.read_text(encoding="utf-8", errors="replace")
        existing = parse_properties_text(existing_text)
        updates: Dict[str, str] = {}

        if sync_initial_defaults:
            # Fresh installation (e.g. Bedrock zip just extracted default server.properties):
            # align ports with instance MC_PORT, disable whitelist/allow-list so players can join
            # right away, and apply configured server name if Mojang's generic default is set.
            updates.update(compute_port_updates(existing_text, target_port, server_type=s_type))
            if s_type == "bedrock" or "allow-list" in existing:
                updates["allow-list"] = "false"
            if s_type != "bedrock" or "white-list" in existing:
                updates["white-list"] = "false"
            if s_type != "bedrock" or "enforce-whitelist" in existing:
                updates["enforce-whitelist"] = "false"
            cur_name = existing.get("server-name", "").strip()
            if s_name and cur_name in ("", "Dedicated Server", "Mi Servidor Dockraft"):
                updates["server-name"] = s_name
            cur_motd = existing.get("motd", "").strip()
            if s_name and cur_motd in ("", "A Minecraft Server", "Dedicated Server"):
                updates["motd"] = s_name
        elif configured_port is not None:
            # Existing server (update, import, or pre-start check): keep port aligned with instance MC_PORT
            port_updates = compute_port_updates(existing_text, configured_port, server_type=s_type)
            for pk, pv in port_updates.items():
                if existing.get(pk, "").strip() != pv:
                    updates[pk] = pv

        if updates:
            new_text = update_properties_text(existing_text, updates)
            if new_text != existing_text:
                atomic_write_text(prop_file, new_text)
    except Exception:
        pass
