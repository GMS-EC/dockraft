import sys
import re
import shutil
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel

from app.config import settings
from app.core.security import get_current_user
from app.core.process_manager import process_manager as _default_process_manager
from app.core.downloader import downloader as _default_downloader
from app.core.java_manager import JavaManager
from app.core.backup_manager import backup_manager as _default_backup_manager
from app.core.activity_manager import activity_manager as _default_activity_manager
from app.core.modpack_manager import (
    MAX_MRPACK_BYTES,
    SUPPORTED_LOADERS,
    ModConflictError,
    modpack_manager as _default_modpack_manager,
)

logger = logging.getLogger("dockraft.installer")

router = APIRouter(tags=["installer"])

_background_tasks: set = set()

ACTIVE_INSTALLER_STATES = {
    "preparing",
    "stopping",
    "backing_up",
    "downloading",
    "downloading_modpack",
    "installing_loader",
    "downloading_mods",
    "verifying",
    "extracting",
    "extracting_overrides",
    "installing",
    "updating",
    "restarting",
}

DOWNLOADING_INSTALLER_STATES = {
    "downloading",
    "extracting",
    "downloading_modpack",
    "downloading_mods",
    "extracting_overrides",
}


def _set_install_stage(
    downloader_obj,
    status: str,
    percent: Optional[int] = None,
    filename: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Updates downloader.active_download consistently across all pre/post download phases."""
    current = getattr(downloader_obj, "active_download", None)
    base = dict(current) if isinstance(current, dict) else {}
    if filename is not None:
        base["file"] = filename
    if percent is not None:
        base["percent"] = percent
    elif "percent" not in base:
        base["percent"] = 0
    if detail is not None:
        base["detail"] = detail
    elif status == "idle":
        base.pop("detail", None)
    base["status"] = status
    base["is_downloading"] = status in DOWNLOADING_INSTALLER_STATES
    base["is_active"] = status in ACTIVE_INSTALLER_STATES
    downloader_obj.active_download = base


def _is_operation_running(downloader_obj) -> bool:
    """Returns True if an install or update background pipeline is currently running."""
    if any(isinstance(t, asyncio.Task) and not t.done() for t in _background_tasks):
        return True
    current = getattr(downloader_obj, "active_download", None)
    if isinstance(current, dict):
        return str(current.get("status", "")) in ACTIVE_INSTALLER_STATES
    return False


def _track_task(coro) -> asyncio.Task:
    """Spawns an asyncio background task while holding a strong reference to prevent GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    if hasattr(task, "add_done_callback"):
        task.add_done_callback(_background_tasks.discard)
    return task


def _deps():
    """Resolves core dependencies through app.main when loaded, preserving test monkeypatches."""
    main_mod = sys.modules.get("app.main")
    pm = getattr(main_mod, "process_manager", _default_process_manager)
    dl = getattr(main_mod, "downloader", _default_downloader)
    bm = getattr(main_mod, "backup_manager", _default_backup_manager)
    am = getattr(main_mod, "activity_manager", _default_activity_manager)
    is_inst = getattr(main_mod, "_is_server_installed", lambda: pm.is_installed())
    return pm, dl, bm, am, is_inst


def _modpack_dep():
    """Resolves ModpackManager through app.main when loaded, preserving test monkeypatches."""
    main_mod = sys.modules.get("app.main")
    return getattr(main_mod, "modpack_manager", _default_modpack_manager)


class InstallRequest(BaseModel):
    server_type: str  # paper, purpur, vanilla, fabric, bedrock, forge, neoforge
    version: str
    server_name: Optional[str] = "Mi Servidor Dockraft"
    java_path: Optional[str] = None
    min_ram: Optional[str] = "1G"
    max_ram: Optional[str] = "2G"
    aikar_flags: Optional[bool] = True
    cpu_cores: Optional[int] = 2
    disk_limit_gb: Optional[float] = 10.0
    force: Optional[bool] = False


class UpdateRequest(BaseModel):
    version: str
    build: Optional[Union[int, str]] = None
    update_mods: bool = False
    allow_beta_mods: bool = False


class ModpackInstallRequest(BaseModel):
    source: str = "modrinth"
    project_type: str = "modpack"  # modpack | mod
    project_id: str
    version_id: str
    loader: Optional[str] = None
    mc_version: Optional[str] = None
    server_name: Optional[str] = "Mi Servidor Dockraft"
    java_path: Optional[str] = None
    min_ram: Optional[str] = "2G"
    max_ram: Optional[str] = "4G"
    aikar_flags: Optional[bool] = True
    cpu_cores: Optional[int] = 2
    disk_limit_gb: Optional[float] = 10.0
    force: Optional[bool] = False


class ModStackResolveRequest(BaseModel):
    project_ids: List[str]
    loader: str
    mc_version: str
    allow_beta: bool = False


class ModStackInstallRequest(BaseModel):
    project_ids: List[str]
    loader: str
    mc_version: str
    allow_beta: bool = False
    server_name: Optional[str] = "Mi Servidor Dockraft"
    java_path: Optional[str] = None
    min_ram: Optional[str] = "2G"
    max_ram: Optional[str] = "4G"
    aikar_flags: Optional[bool] = True
    cpu_cores: Optional[int] = 2
    disk_limit_gb: Optional[float] = 10.0
    force: Optional[bool] = False


class ModpackUpdateRequest(BaseModel):
    version_id: Optional[str] = None
    allow_beta: bool = False
    update_custom_mods: bool = True


class AddInstalledModRequest(BaseModel):
    project_id: str
    version_id: Optional[str] = None
    allow_beta: bool = False


class UpdateInstalledModsRequest(BaseModel):
    filenames: Optional[List[str]] = None
    allow_beta: bool = False


class ToggleModRequest(BaseModel):
    filename: str


async def resolve_server_download(
    server_type: str,
    version: str,
    build: Optional[Union[int, str]] = None,
    unsupported_detail: str = "Unsupported server type",
) -> Dict[str, Any]:
    """Resolves download_url, target_file, is_zip, and build for a given server_type and version."""
    _, downloader, _, _, _ = _deps()
    target_file = "server.jar"
    is_zip = False
    resolved_build = build
    expected_sha256: Optional[str] = None
    expected_sha1: Optional[str] = None
    allowed_hosts: Optional[set] = None

    if server_type in ["paper", "folia", "velocity"]:
        if build is not None:
            info = await downloader.get_paper_build(server_type, version, build)
        else:
            info = await downloader.get_paper_latest_build(server_type, version)
        download_url = info["download_url"]
        resolved_build = info.get("build")
        expected_sha256 = info.get("sha256")
        allowed_hosts = {"papermc.io"}
    elif server_type == "purpur":
        if build is not None:
            info = await downloader.get_purpur_build(version, build)
        else:
            info = await downloader.get_purpur_latest_build(version)
        download_url = info["download_url"]
        resolved_build = info.get("build")
        allowed_hosts = {"purpurmc.org"}
    elif server_type == "vanilla":
        versions = await downloader.get_vanilla_versions()
        match = next((v for v in versions if v["id"] == version), None)
        if not match:
            raise HTTPException(status_code=404, detail="Version manifest not found")
        v_info = await downloader.get_vanilla_download_info(match["url"])
        download_url = str(v_info["url"])
        expected_sha1 = v_info.get("sha1")
        allowed_hosts = {"mojang.com"}
    elif server_type == "fabric":
        valid_vers = await downloader.get_fabric_versions()
        if valid_vers and version not in valid_vers:
            raise HTTPException(status_code=404, detail="Version manifest not found")
        download_url = await downloader.get_fabric_download_url(version)
        allowed_hosts = {"fabricmc.net"}
    elif server_type == "bedrock":
        platform = "win" if sys.platform == "win32" else "linux"
        download_url = await downloader.get_bedrock_download_url(version, platform=platform)
        target_file = "bedrock-server.zip"
        is_zip = True
        allowed_hosts = {"minecraft.net", "azureedge.net", "minecraft-cdn.net"}
    elif server_type == "forge":
        download_url = await downloader.get_forge_download_url(version)
        target_file = "forge-installer.jar"
        allowed_hosts = {"minecraftforge.net"}
    elif server_type == "neoforge":
        download_url = await downloader.get_neoforge_download_url(version)
        target_file = "neoforge-installer.jar"
        allowed_hosts = {"neoforged.net"}
    elif server_type == "quilt":
        valid_vers = await downloader.get_quilt_versions()
        if valid_vers and version not in valid_vers:
            raise HTTPException(status_code=404, detail="Version manifest not found")
        q_info = await downloader.get_quilt_installer_info()
        download_url = q_info["url"]
        target_file = "quilt-installer.jar"
        expected_sha256 = q_info.get("sha256")
        allowed_hosts = {"quiltmc.org"}
    else:
        raise HTTPException(status_code=400, detail=unsupported_detail)

    return {
        "download_url": download_url,
        "target_file": target_file,
        "is_zip": is_zip,
        "build": resolved_build,
        "expected_sha256": expected_sha256,
        "expected_sha1": expected_sha1,
        "allowed_hosts": allowed_hosts,
    }


def get_version_changelog_info(server_type: str, version_id: str, channel: str = "stable") -> Dict[str, Any]:
    """Generates official changelog URLs, engine notes, and upgrade advice for any Minecraft server version."""
    st = (server_type or "").lower().strip()
    vid = (version_id or "").strip()

    m = re.search(r"([0-9]+(?:\.[0-9]+)+(?:-[a-zA-Z0-9\.\-]+)?)", vid)
    clean_ver = m.group(1) if m else vid

    if st == "bedrock":
        if channel in ("preview", "beta"):
            official_url = "https://feedback.minecraft.net/hc/en-us/sections/360001185332-Beta-and-Preview-Information-and-Changelogs"
            official_label = "Novedades Oficiales de Betas y Previews (Bedrock)"
        else:
            official_url = "https://feedback.minecraft.net/hc/en-us/sections/360001186971-Release-Changelogs"
            official_label = "Página Oficial y Cambios de Bedrock"
        wiki_url = f"https://minecraft.wiki/w/Bedrock_Edition_{clean_ver}"
    elif st == "paper":
        official_url = "https://papermc.io/downloads/paper"
        official_label = "Página Oficial y Descargas de PaperMC"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "folia":
        official_url = "https://papermc.io/downloads/folia"
        official_label = "Página Oficial y Descargas de Folia"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "velocity":
        official_url = "https://papermc.io/downloads/velocity"
        official_label = "Página Oficial y Descargas de Velocity"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "purpur":
        official_url = f"https://purpurmc.org/downloads?version={clean_ver}" if clean_ver else "https://purpurmc.org/downloads"
        official_label = "Página Oficial y Descargas de Purpur"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "fabric":
        official_url = "https://fabricmc.net/"
        official_label = "Portal Oficial de FabricMC"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "forge":
        official_url = "https://files.minecraftforge.net/net/minecraftforge/forge/"
        official_label = "Portal Oficial de Minecraft Forge"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "neoforge":
        official_url = "https://neoforged.net/"
        official_label = "Portal Oficial de NeoForge"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    elif st == "quilt":
        official_url = "https://quiltmc.org/"
        official_label = "Portal Oficial de QuiltMC"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"
    else:
        official_url = "https://www.minecraft.net/articles"
        official_label = "Artículos Oficiales de Lanzamiento en Minecraft.net"
        wiki_url = f"https://minecraft.wiki/w/Java_Edition_{clean_ver}"

    wiki_label = f"Wiki de Minecraft ({clean_ver})"

    is_stable = channel == "stable"
    if is_stable:
        advice_title = "Compilación Estable (Recomendada para Producción)"
        advice_text = (
            f"La versión {clean_ver} es una compilación Estable oficial. Es la opción recomendada "
            "si buscas máxima compatibilidad con plugins/mods, estabilidad para tus jugadores y cero riesgos de fallos experimentales."
        )
    else:
        ch_label = "Beta / Snapshot" if channel in ("beta", "snapshot", "pre") else "Experimental"
        advice_title = f"Compilación {ch_label} (Preliminar de Desarrollo)"
        advice_text = (
            f"La versión {clean_ver} incluye las mecánicas y bloques más recientes antes de su lanzamiento final, "
            "pero puede contener bugs, inestabilidad o incompatibilidad temporal con plugins. Te conviene quedarte en Estable "
            "si tu comunidad está activa, o probar esta versión si tienes un entorno de prueba o deseas explorar las novedades. "
            "Dockraft generará una copia de seguridad preventiva antes de instalar."
        )

    return {
        "clean_version": clean_ver,
        "official_url": official_url,
        "official_label": official_label,
        "wiki_url": wiki_url,
        "wiki_label": wiki_label,
        "changelog_url": official_url,
        "engine_url": wiki_url,
        "engine_label": wiki_label,
        "advice_title": advice_title,
        "advice_text": advice_text,
        "is_stable": is_stable,
    }


@router.get("/api/installer/versions", dependencies=[Depends(get_current_user)])
async def get_installer_versions(type: str = Query("paper")):
    _, downloader, _, _, _ = _deps()
    try:
        if type in ["paper", "folia", "velocity"]:
            versions = await downloader.get_paper_versions(type)
            return {"type": type, "versions": versions}
        elif type == "purpur":
            versions = await downloader.get_purpur_versions()
            return {"type": type, "versions": versions}
        elif type == "vanilla":
            versions = await downloader.get_vanilla_versions()
            return {"type": type, "versions": [v["id"] for v in versions]}
        elif type == "fabric":
            versions = await downloader.get_fabric_versions()
            return {"type": type, "versions": versions}
        elif type == "bedrock":
            versions = await downloader.get_bedrock_versions()
            return {"type": "bedrock", "versions": versions}
        elif type == "forge":
            versions = await downloader.get_forge_versions()
            return {"type": "forge", "versions": versions}
        elif type == "neoforge":
            versions = await downloader.get_neoforge_versions()
            return {"type": "neoforge", "versions": versions}
        elif type == "quilt":
            versions = await downloader.get_quilt_versions()
            return {"type": "quilt", "versions": versions}
        else:
            raise HTTPException(status_code=400, detail="Invalid server type")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching versions: {str(e)}")


@router.get("/api/installer/progress", dependencies=[Depends(get_current_user)])
async def get_install_progress():
    _, downloader, _, _, _ = _deps()
    raw_active = getattr(downloader, "active_download", None)
    if isinstance(raw_active, dict):
        status_val = str(raw_active.get("status", "idle"))
        pct_val = raw_active.get("percent", 0)
        data = {
            **raw_active,
            "status": status_val,
            "percent": pct_val,
            "is_downloading": status_val in DOWNLOADING_INSTALLER_STATES,
            "is_active": status_val in ACTIVE_INSTALLER_STATES,
        }
    else:
        data = {
            "status": "idle",
            "percent": 0,
            "is_downloading": False,
            "is_active": False,
        }

    if data.get("status") == "completed":
        downloader.active_download = {
            "status": "idle",
            "percent": 0,
            "is_downloading": False,
            "is_active": False,
        }
    return data


@router.post("/api/installer/install", dependencies=[Depends(get_current_user)])
async def install_server(req: InstallRequest):
    process_manager, downloader, _, _, is_server_installed = _deps()
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar o cambiar de versión")

    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")

    if is_server_installed() and not req.force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura.",
        )

    try:
        if req.server_type != "bedrock":
            if not req.java_path or req.java_path == "java":
                req.java_path = await asyncio.to_thread(JavaManager.get_best_java_path, req.version)

        dl_info = await resolve_server_download(req.server_type, req.version)
        download_url = dl_info["download_url"]
        target_file = dl_info["target_file"]
        is_zip = dl_info["is_zip"]
        server_build = dl_info["build"]
        expected_sha256 = dl_info.get("expected_sha256")
        expected_sha1 = dl_info.get("expected_sha1")
        allowed_hosts = dl_info.get("allowed_hosts")

        resolved_server_file = (
            ("bedrock_server.exe" if sys.platform == "win32" else "bedrock_server")
            if req.server_type == "bedrock"
            else (("run.bat" if sys.platform == "win32" else "run.sh") if req.server_type in ("forge", "neoforge") else "server.jar")
        )

        cfg_to_save = {
            "server_type": req.server_type,
            "server_version": req.version,
            "server_file": resolved_server_file,
            "server_name": req.server_name or "Mi Servidor Dockraft",
            "java_path": req.java_path or "java",
            "min_ram": req.min_ram or "1G",
            "max_ram": req.max_ram or "2G",
            "aikar_flags": req.aikar_flags if req.aikar_flags is not None else True,
            "cpu_cores": req.cpu_cores if req.cpu_cores is not None else 2,
            "disk_limit_gb": req.disk_limit_gb if req.disk_limit_gb is not None else 10.0,
        }
        if server_build is not None:
            try:
                cfg_to_save["server_build"] = int(server_build)
            except (ValueError, TypeError):
                pass

        settings.save_runtime_config(cfg_to_save)

        if req.server_type in ("forge", "neoforge"):
            java_bin = req.java_path or "java"
            _set_install_stage(downloader, "preparing", percent=0, filename=target_file)

            async def forge_install_pipeline():
                try:
                    installer_path = await downloader.download_file(
                        download_url,
                        target_file,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                        complete_on_finish=False,
                    )
                    _set_install_stage(downloader, "installing", percent=100, filename=target_file)
                    if req.server_type == "neoforge":
                        res = await downloader.install_neoforge_server(installer_path, java_bin=java_bin)
                    else:
                        res = await downloader.install_forge_server(installer_path, java_bin=java_bin)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh")
                    })
                    downloader.ensure_initial_config(sync_initial_defaults=True)
                    _set_install_stage(downloader, "completed", percent=100, filename=target_file)
                except Exception as ex:
                    logger.error("[Dockraft] %s install pipeline error: %s", req.server_type, ex)
                    _set_install_stage(downloader, f"error: {ex}", percent=0, filename=target_file)

            _track_task(forge_install_pipeline())
        else:
            _set_install_stage(downloader, "preparing", percent=0, filename=target_file)
            _track_task(
                downloader.download_file(
                    download_url,
                    target_file,
                    is_zip=is_zip,
                    expected_sha256=expected_sha256,
                    expected_sha1=expected_sha1,
                    allowed_hosts=allowed_hosts,
                )
            )
        return {"status": "started", "target_file": target_file, "download_url": download_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/installer/update-info", dependencies=[Depends(get_current_user)])
async def get_update_info():
    """Returns update status and classified versions for the currently installed server type."""
    _, downloader, _, _, is_server_installed = _deps()
    if not is_server_installed():
        return {
            "is_installed": False,
            "server_type": None,
            "current_version": None,
            "current_channel": "unknown",
            "latest_stable": "",
            "latest_preview": "",
            "update_available": False,
            "preview_available": False,
            "available_versions": [],
            "versions": [],
        }

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    current_version = cfg.get("server_version", "")
    current_build = cfg.get("server_build")
    server_file = cfg.get("server_file")

    if not current_version or current_version.lower() in ["importado", "desconocida", "unknown"]:
        detected_ver = downloader.detect_server_version(server_file=server_file)
        if detected_ver:
            current_version = detected_ver
            settings.save_runtime_config({"server_version": detected_ver})
        else:
            current_version = "importado"

    if current_build is None and server_type in ["paper", "folia", "velocity", "purpur"]:
        detected_build = downloader.detect_server_build(server_file=server_file)
        if detected_build:
            current_build = detected_build
            settings.save_runtime_config({"server_build": detected_build})

    latest_stable = ""
    latest_preview = ""
    version_items = []

    try:
        if server_type == "bedrock":
            b_vers = await downloader.get_bedrock_versions()
            for bv in b_vers:
                m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)+)", bv)
                vid = m.group(1) if m else bv
                is_prev = "preview" in bv.lower() or "beta" in bv.lower()
                ch = "preview" if is_prev else "stable"
                lbl = f"{vid} (Estable)" if not is_prev else f"{vid} (Preview / Beta)"
                version_items.append({"id": bv, "label": lbl, "channel": ch})
                if not is_prev and not latest_stable:
                    latest_stable = vid
                elif is_prev and not latest_preview:
                    latest_preview = vid

        elif server_type == "vanilla":
            latest_info = await downloader.get_vanilla_latest()
            latest_stable = latest_info.get("release", "")
            latest_preview = latest_info.get("snapshot", "")

            raw_versions = await downloader.get_vanilla_versions()
            for v in raw_versions:
                vid = v["id"]
                vtype = v.get("type", "")
                if vtype == "release":
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                elif "-pre" in vid or "pre-release" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                elif "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Release Candidate)"
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type == "fabric":
            fabric_items = await downloader.get_fabric_version_items()
            for f in fabric_items:
                vid = f["id"]
                is_st = f.get("stable", False)
                if is_st:
                    ch = "stable"
                    lbl = f"{vid} (Estable)"
                    if not latest_stable:
                        latest_stable = vid
                elif "-pre" in vid or "-rc" in vid:
                    ch = "pre"
                    lbl = f"{vid} (Pre-Release)"
                    if not latest_preview:
                        latest_preview = vid
                else:
                    ch = "snapshot"
                    lbl = f"{vid} (Snapshot)"
                    if not latest_preview:
                        latest_preview = vid
                version_items.append({"id": vid, "label": lbl, "channel": ch})

        elif server_type in ["paper", "folia", "velocity"]:
            classified = await downloader.get_paper_classified_versions(server_type)
            version_items = classified.get("versions", [])
            latest_stable = classified.get("latest_stable", "")
            latest_preview = classified.get("latest_preview", "")

        elif server_type == "purpur":
            purpur_versions = await downloader.get_purpur_versions()
            for pv in purpur_versions:
                is_pre = "-pre" in pv or "-rc" in pv
                ch = "pre" if is_pre else "stable"
                lbl = f"{pv} (Pre-Release)" if is_pre else f"{pv} (Estable)"
                version_items.append({"id": pv, "label": lbl, "channel": ch})
                if ch == "stable" and not latest_stable:
                    latest_stable = pv
                elif ch != "stable" and not latest_preview:
                    latest_preview = pv

        elif server_type == "forge":
            forge_list = await downloader.get_forge_versions()
            for fv in forge_list:
                vid = fv["mc_version"]
                is_rec = fv.get("is_recommended", False)
                ch = "stable" if is_rec else "preview"
                version_items.append({"id": vid, "label": fv["label"], "channel": ch})
                if is_rec and not latest_stable:
                    latest_stable = vid
                elif not is_rec and not latest_preview:
                    latest_preview = vid

        elif server_type == "neoforge":
            nf_list = await downloader.get_neoforge_versions()
            for nfv in nf_list:
                vid = nfv["mc_version"]
                is_rec = nfv.get("is_recommended", True)
                ch = "stable" if is_rec else "preview"
                version_items.append({"id": vid, "label": nfv["label"], "channel": ch})
                if is_rec and not latest_stable:
                    latest_stable = vid
                elif not is_rec and not latest_preview:
                    latest_preview = vid

        elif server_type == "quilt":
            quilt_versions = await downloader.get_quilt_versions()
            for qv in quilt_versions:
                version_items.append({"id": qv, "label": f"{qv} (Estable)", "channel": "stable"})
                if not latest_stable:
                    latest_stable = qv

    except Exception as e:
        logger.error("[UpdateInfo] Error querying versions for %s: %s", server_type, e)

    curr_l = current_version.lower()
    if server_type == "bedrock":
        current_channel = "preview" if ("preview" in curr_l or "beta" in curr_l) else "stable"
    elif "-pre" in curr_l or "pre-release" in curr_l:
        current_channel = "pre"
    elif "-rc" in curr_l:
        current_channel = "rc"
    elif "snapshot" in curr_l or re.search(r"^[0-9]{2}w[0-9]{2}[a-z]$", curr_l):
        current_channel = "snapshot"
    else:
        matching_ver = next((v for v in version_items if v.get("id") == current_version), None)
        if matching_ver and matching_ver.get("channel") in ("preview", "pre", "snapshot"):
            current_channel = matching_ver.get("channel")
        else:
            current_channel = "stable"

    curr_m = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)+)", current_version)
    curr_clean = curr_m.group(1) if curr_m else current_version

    latest_build = None
    build_update_available = False
    try:
        target_v = current_version if (current_version and current_version != "importado") else latest_stable
        if target_v and server_type in ["paper", "folia", "velocity"]:
            b_info = await downloader.get_paper_latest_build(server_type, target_v)
            if b_info and b_info.get("build"):
                latest_build = int(b_info["build"])
        elif target_v and server_type == "purpur":
            b_info = await downloader.get_purpur_latest_build(target_v)
            if b_info and b_info.get("build"):
                latest_build = int(b_info["build"])
    except Exception as ex:
        logger.warning("[UpdateInfo] Warning querying latest build for %s: %s", server_type, ex)

    if current_build is not None and latest_build is not None:
        try:
            if int(latest_build) > int(current_build):
                build_update_available = True
        except (ValueError, TypeError):
            pass

    update_available = False
    if current_version == "importado":
        update_available = bool(latest_stable)
    elif current_channel == "stable":
        if latest_stable and curr_clean and latest_stable != curr_clean:
            update_available = True
        elif build_update_available:
            update_available = True
    else:
        if latest_preview and current_version != latest_preview:
            update_available = True
        elif build_update_available:
            update_available = True

    preview_available = bool(latest_preview and latest_preview != current_version and latest_preview != latest_stable)

    enriched_versions = []
    for it in version_items:
        cinfo = get_version_changelog_info(server_type, it["id"], it.get("channel", "stable"))
        enriched = dict(it)
        enriched.update(cinfo)
        enriched_versions.append(enriched)

    latest_stable_info = get_version_changelog_info(server_type, latest_stable, "stable") if latest_stable else None
    latest_preview_info = get_version_changelog_info(server_type, latest_preview, "preview") if latest_preview else None
    current_version_info = get_version_changelog_info(server_type, current_version, current_channel) if current_version else None

    return {
        "is_installed": True,
        "server_type": server_type,
        "current_version": current_version,
        "current_build": current_build,
        "current_channel": current_channel,
        "latest_stable": latest_stable,
        "latest_preview": latest_preview,
        "latest_build": latest_build,
        "build_update_available": build_update_available,
        "latest_stable_info": latest_stable_info,
        "latest_preview_info": latest_preview_info,
        "current_version_info": current_version_info,
        "update_available": update_available,
        "preview_available": preview_available,
        "available_versions": [it["label"] for it in enriched_versions],
        "versions": enriched_versions,
        "modpack_name": cfg.get("modpack_name"),
        "modpack_slug": cfg.get("modpack_slug"),
        "modpack_version_name": cfg.get("modpack_version_name"),
        "modpack_type": cfg.get("modpack_type"),
        "loader_version": cfg.get("loader_version"),
    }


@router.get("/api/installer/builds", dependencies=[Depends(get_current_user)])
async def get_installer_builds(version: Optional[str] = None):
    """Retrieves available builds for the current server type and specified version."""
    _, downloader, _, _, is_server_installed = _deps()
    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay servidor instalado")
    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    current_ver = cfg.get("server_version", "")
    current_build = cfg.get("server_build")
    target_ver = version or current_ver

    builds = []
    latest_build = None
    try:
        if server_type in ["paper", "folia", "velocity"]:
            builds = await downloader.get_paper_build_list(server_type, target_ver)
            if builds:
                latest_build = builds[0]["id"]
        elif server_type == "purpur":
            builds = await downloader.get_purpur_build_list(target_ver)
            if builds:
                latest_build = builds[0]["id"]
    except Exception as e:
        logger.error("[BuildsAPI] Error fetching builds for %s %s: %s", server_type, target_ver, e)

    return {
        "server_type": server_type,
        "version": target_ver,
        "current_build": current_build,
        "latest_build": latest_build,
        "builds": builds,
    }


@router.post("/api/installer/update", dependencies=[Depends(get_current_user)])
async def update_server(req: UpdateRequest):
    """Safely updates the existing server to a new version of the same software."""
    process_manager, downloader, backup_manager, activity_manager, is_server_installed = _deps()
    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado para actualizar")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")

    cfg = settings.runtime_config
    server_type = cfg.get("server_type", "paper")
    old_server_file = cfg.get("server_file")

    try:
        dl_info = await resolve_server_download(
            server_type,
            req.version,
            build=req.build,
            unsupported_detail="Tipo de servidor no soportado para actualización",
        )
        download_url = dl_info["download_url"]
        target_file = dl_info["target_file"]
        is_zip = dl_info["is_zip"]
        new_build = dl_info["build"]
        expected_sha256 = dl_info.get("expected_sha256")
        expected_sha1 = dl_info.get("expected_sha1")
        allowed_hosts = dl_info.get("allowed_hosts")

        was_running = process_manager.get_status() != "OFFLINE"
        _set_install_stage(
            downloader,
            "stopping" if was_running else "backing_up",
            percent=0,
            filename=target_file,
        )

        async def safe_update_pipeline():
            try:
                if was_running:
                    _set_install_stage(downloader, "stopping", percent=0, filename=target_file)
                    msg = "[Dockraft] Deteniendo servidor de forma segura para aplicar actualización..."
                    process_manager._append_log(msg)
                    await process_manager.broadcast_message({"type": "log", "data": msg})
                    await process_manager.send_command("save-all", echo=False)
                    await process_manager.stop_server()
                    for _ in range(45):
                        await asyncio.sleep(1)
                        if process_manager.get_status() == "OFFLINE":
                            break
                    if process_manager.get_status() != "OFFLINE":
                        kill_msg = "[Dockraft] El servidor tardó más de 45s en cerrar; forzando detención para proceder con la actualización de forma segura..."
                        process_manager._append_log(kill_msg)
                        await process_manager.broadcast_message({"type": "log", "data": kill_msg})
                        await process_manager.kill_server()

                build_suffix = f"-b{new_build}" if new_build else ""
                tag_name = f"pre-update-{req.version}{build_suffix}"
                _set_install_stage(downloader, "backing_up", percent=0, filename=target_file)
                msg = f"[Dockraft] Generando copia de seguridad preventiva ({tag_name})..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})
                pre_backup = await asyncio.to_thread(
                    backup_manager.create_backup,
                    scope="full",
                    tag=tag_name,
                    compression=True,
                )
                if pre_backup.get("status") == "error":
                    err_detail = pre_backup.get("message") or "Error creando copia preventiva"
                    err_msg = f"[Dockraft] Error al crear copia preventiva: {err_detail}. Abortando actualización para seguridad de datos."
                    process_manager._append_log(err_msg)
                    await process_manager.broadcast_message({"type": "log", "data": err_msg})
                    _set_install_stage(downloader, f"error: {err_detail}", percent=0, filename=target_file)
                    if was_running:
                        await process_manager.start_server()
                    return

                build_label = f" (Build #{new_build})" if new_build else ""
                msg = f"[Dockraft] Descargando actualización {req.version}{build_label} y verificando integridad anti-corrupción..."
                process_manager._append_log(msg)
                await process_manager.broadcast_message({"type": "log", "data": msg})

                if server_type in ("forge", "neoforge", "quilt"):
                    java_path = await asyncio.to_thread(JavaManager.get_best_java_path, req.version) or cfg.get("java_path") or "java"
                    installer_path = await downloader.download_file(
                        download_url,
                        target_file,
                        preserve_existing_configs=True,
                        verify_integrity=True,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                        complete_on_finish=False,
                    )
                    _set_install_stage(downloader, "installing", percent=100, filename=target_file)
                    if server_type == "neoforge":
                        res = await downloader.install_neoforge_server(installer_path, java_bin=java_path)
                    elif server_type == "quilt":
                        res = await downloader.install_quilt_server(installer_path, mc_version=req.version, java_bin=java_path)
                    else:
                        res = await downloader.install_forge_server(installer_path, java_bin=java_path)
                    settings.save_runtime_config({
                        "server_file": res.get("server_file", "run.sh"),
                        "server_version": req.version,
                        "java_path": java_path,
                    })
                else:
                    await downloader.download_file(
                        download_url,
                        target_file,
                        is_zip=is_zip,
                        preserve_existing_configs=True,
                        verify_integrity=True,
                        expected_sha256=expected_sha256,
                        expected_sha1=expected_sha1,
                        allowed_hosts=allowed_hosts,
                        complete_on_finish=False,
                    )
                    if old_server_file and old_server_file != target_file and not is_zip:
                        old_path = settings.data_dir / old_server_file
                        if old_path.exists():
                            try:
                                old_path.unlink()
                            except Exception:
                                pass

                    upd_cfg = {
                        "server_file": target_file if not is_zip else old_server_file or "bedrock_server",
                        "server_version": req.version,
                    }
                    if server_type in SUPPORTED_LOADERS:
                        upd_cfg["java_path"] = await asyncio.to_thread(JavaManager.get_best_java_path, req.version)
                    if new_build is not None:
                        try:
                            upd_cfg["server_build"] = int(new_build)
                        except (ValueError, TypeError):
                            pass
                    settings.save_runtime_config(upd_cfg)

                if server_type in SUPPORTED_LOADERS and getattr(req, "update_mods", False):
                    _set_install_stage(downloader, "updating", percent=92, filename=target_file, detail=f"Migrando mods compatibles para {req.version}...")
                    await _modpack_dep().migrate_mods_for_mc_upgrade(
                        target_mc=req.version,
                        target_loader=server_type,
                        allow_beta=bool(getattr(req, "allow_beta_mods", False)),
                        activity_manager_obj=activity_manager,
                    )

                build_label = f" (Build #{new_build})" if new_build else ""
                activity_manager.log(
                    category="update",
                    action="Servidor actualizado",
                    details=f"Actualizado con éxito a versión {req.version}{build_label} ({server_type.upper()}). Respaldo preventivo: {pre_backup.get('filename')}",
                    user="admin",
                    status="success",
                )

                succ_msg = f"[Dockraft] ¡Servidor actualizado exitosamente a la versión {req.version}{build_label}!"
                process_manager._append_log(succ_msg)
                await process_manager.broadcast_message({"type": "log", "data": succ_msg})

                if was_running:
                    _set_install_stage(downloader, "restarting", percent=100, filename=target_file)
                    restart_msg = "[Dockraft] Reiniciando servidor automáticamente con la nueva versión..."
                    process_manager._append_log(restart_msg)
                    await process_manager.broadcast_message({"type": "log", "data": restart_msg})
                    await asyncio.sleep(1.5)
                    await process_manager.start_server()

                _set_install_stage(downloader, "completed", percent=100, filename=target_file)

            except Exception as ex:
                err_msg = f"[Dockraft] Error en la actualización a {req.version}: {str(ex)}"
                process_manager._append_log(err_msg)
                await process_manager.broadcast_message({"type": "log", "data": err_msg})
                activity_manager.log(
                    category="update",
                    action="Error en actualización",
                    details=f"Fallo al actualizar a {req.version}: {str(ex)}",
                    user="admin",
                    status="error",
                )
                _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename=target_file)
                if was_running and process_manager.get_status() == "OFFLINE":
                    await process_manager.start_server()

        _track_task(safe_update_pipeline())

        return {
            "status": "started",
            "server_type": server_type,
            "target_version": req.version,
            "download_url": download_url,
            "auto_stopping": was_running,
        }

    except HTTPException:
        raise
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail="Version not found")
        if "HTTPStatusError" in type(e).__name__:
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/installer/modpacks/search", dependencies=[Depends(get_current_user)])
async def search_modpacks(
    q: str = Query("", max_length=120),
    project_type: str = Query("modpack"),
    loader: Optional[str] = Query(None),
    game_version: Optional[str] = Query(None),
    limit: int = Query(12, ge=1, le=30),
    offset: int = Query(0, ge=0),
):
    """Searches Modrinth for server-compatible modpacks or mods."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.search_projects(
            query=q,
            project_type=project_type,
            loader=loader,
            game_version=game_version,
            limit=limit,
            offset=offset,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("[Modpacks] Search failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Error consultando catálogo Modrinth: {str(e)}")


@router.get("/api/installer/modpacks/project/{project_id}", dependencies=[Depends(get_current_user)])
async def get_modpack_project(project_id: str):
    """Retrieves project metadata and available server versions from Modrinth."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.get_project_details(project_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail="Proyecto no encontrado en Modrinth")
        logger.error("[Modpacks] Project lookup failed (%s): %s", project_id, e)
        raise HTTPException(status_code=502, detail=f"Error consultando proyecto en Modrinth: {str(e)}")


@router.get(
    "/api/installer/modpacks/project/{project_id}/version/{version_id}/requirements",
    dependencies=[Depends(get_current_user)],
)
async def get_modpack_version_requirements(
    project_id: str,
    version_id: str,
    loader: Optional[str] = Query(None),
    mc_version: Optional[str] = Query(None),
):
    """Inspects loader, Minecraft version, Java recommendation, and required dependencies."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.inspect_version_requirements(
            project_id=project_id,
            version_id=version_id,
            preferred_loader=loader,
            preferred_mc_version=mc_version,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail="Versión no encontrada en Modrinth")
        logger.error("[Modpacks] Requirements inspect failed (%s/%s): %s", project_id, version_id, e)
        raise HTTPException(status_code=502, detail=f"Error analizando requerimientos en Modrinth: {str(e)}")


@router.post("/api/installer/modpacks/install", dependencies=[Depends(get_current_user)])
async def install_modpack_or_mod(req: ModpackInstallRequest):
    """Starts background installation of a Modrinth modpack or mod with all requirements."""
    process_manager, downloader, _, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar un modpack o mod")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")
    if is_server_installed() and not req.force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura.",
        )

    ptype = str(req.project_type or "modpack").strip().lower()
    if ptype not in ("modpack", "mod"):
        raise HTTPException(status_code=400, detail="project_type debe ser 'modpack' o 'mod'")

    initial_stage = "downloading_modpack" if ptype == "modpack" else "preparing"
    initial_detail = (
        "Iniciando descarga del modpack desde Modrinth..."
        if ptype == "modpack"
        else "Resolviendo cargador y dependencias del mod..."
    )
    _set_install_stage(downloader, initial_stage, percent=2, filename=req.project_id, detail=initial_detail)

    def _stage_cb(stage: str, pct: int, detail_msg: Optional[str] = None) -> None:
        _set_install_stage(downloader, stage, percent=pct, filename=req.project_id, detail=detail_msg)

    async def _run_pipeline():
        try:
            if ptype == "modpack":
                await modpack_mgr.install_modrinth_modpack(
                    project_id=req.project_id,
                    version_id=req.version_id,
                    downloader_obj=downloader,
                    activity_manager_obj=activity_manager,
                    server_name=req.server_name or "Mi Servidor Dockraft",
                    min_ram=req.min_ram or "2G",
                    max_ram=req.max_ram or "4G",
                    aikar_flags=req.aikar_flags if req.aikar_flags is not None else True,
                    cpu_cores=req.cpu_cores if req.cpu_cores is not None else 2,
                    disk_limit_gb=req.disk_limit_gb if req.disk_limit_gb is not None else 10.0,
                    java_path=req.java_path,
                    force=bool(req.force),
                    stage_cb=_stage_cb,
                )
            else:
                await modpack_mgr.install_modrinth_mod(
                    project_id=req.project_id,
                    version_id=req.version_id,
                    downloader_obj=downloader,
                    activity_manager_obj=activity_manager,
                    preferred_loader=req.loader,
                    preferred_mc_version=req.mc_version,
                    server_name=req.server_name or "Mi Servidor Dockraft",
                    min_ram=req.min_ram or "2G",
                    max_ram=req.max_ram or "4G",
                    aikar_flags=req.aikar_flags if req.aikar_flags is not None else True,
                    cpu_cores=req.cpu_cores if req.cpu_cores is not None else 2,
                    disk_limit_gb=req.disk_limit_gb if req.disk_limit_gb is not None else 10.0,
                    java_path=req.java_path,
                    force=bool(req.force),
                    stage_cb=_stage_cb,
                )
        except Exception as ex:
            logger.error("[Modpacks] Install pipeline error (%s/%s): %s", req.project_id, req.version_id, ex)
            activity_manager.log(
                category="install",
                action="Error instalando modpack/mod",
                details=f"{req.project_id} ({req.version_id}): {ex}",
                user="admin",
                status="error",
            )
            _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename=req.project_id, detail=str(ex))

    _track_task(_run_pipeline())
    return {
        "status": "started",
        "project_id": req.project_id,
        "version_id": req.version_id,
        "project_type": ptype,
    }


@router.post("/api/installer/modpacks/upload-mrpack", dependencies=[Depends(get_current_user)])
async def upload_and_install_mrpack(
    file: UploadFile = File(...),
    server_name: str = Form("Mi Servidor Dockraft"),
    java_path: Optional[str] = Form(None),
    min_ram: str = Form("2G"),
    max_ram: str = Form("4G"),
    aikar_flags: bool = Form(True),
    cpu_cores: int = Form(2),
    disk_limit_gb: float = Form(10.0),
    force: bool = Form(False),
):
    """Uploads a local .mrpack modpack file and installs loader, mods, and server overrides."""
    process_manager, downloader, _, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar un archivo .mrpack")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")
    if is_server_installed() and not force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura.",
        )

    filename = Path(file.filename or "modpack.mrpack").name
    if not filename.lower().endswith(".mrpack"):
        raise HTTPException(status_code=400, detail="El archivo debe tener extensión .mrpack")

    temp_mrpack = settings.data_dir / f".upload_{uuid.uuid4().hex[:8]}.mrpack"
    total_size = 0
    try:
        with open(temp_mrpack, "wb") as out_fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_MRPACK_BYTES:
                    raise HTTPException(status_code=413, detail="El archivo .mrpack excede el límite máximo de 512 MB")
                out_fh.write(chunk)

        manifest = await asyncio.to_thread(modpack_mgr.parse_mrpack_manifest, temp_mrpack)
    except HTTPException:
        temp_mrpack.unlink(missing_ok=True)
        raise
    except Exception as e:
        temp_mrpack.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Archivo .mrpack inválido: {str(e)}")

    _set_install_stage(
        downloader,
        "preparing",
        percent=15,
        filename=filename,
        detail=f"Archivo {filename} validado ({manifest['loader_type']} {manifest['mc_version']})...",
    )

    def _stage_cb(stage: str, pct: int, detail_msg: Optional[str] = None) -> None:
        _set_install_stage(downloader, stage, percent=pct, filename=filename, detail=detail_msg)

    async def _mrpack_pipeline():
        try:
            await modpack_mgr.install_from_mrpack(
                mrpack_path=temp_mrpack,
                downloader_obj=downloader,
                activity_manager_obj=activity_manager,
                server_name=server_name or manifest["name"],
                min_ram=min_ram or "2G",
                max_ram=max_ram or "4G",
                aikar_flags=aikar_flags,
                cpu_cores=cpu_cores,
                disk_limit_gb=disk_limit_gb,
                java_path=java_path,
                force=force,
                pack_meta={
                    "modpack_name": manifest["name"],
                    "modpack_version_name": manifest["version_id"],
                    "modpack_type": "modpack",
                    "modpack_source": "mrpack_upload",
                },
                stage_cb=_stage_cb,
            )
        except Exception as ex:
            logger.error("[Modpacks] Uploaded .mrpack pipeline error (%s): %s", filename, ex)
            activity_manager.log(
                category="install",
                action="Error instalando .mrpack",
                details=f"{filename}: {ex}",
                user="admin",
                status="error",
            )
            _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename=filename, detail=str(ex))
        finally:
            try:
                temp_mrpack.unlink(missing_ok=True)
            except OSError:
                pass

    _track_task(_mrpack_pipeline())
    return {
        "status": "started",
        "filename": filename,
        "mc_version": manifest["mc_version"],
        "loader_type": manifest["loader_type"],
        "loader_version": manifest["loader_version"],
    }


async def _safe_stop_and_backup(
    process_manager,
    backup_manager,
    downloader,
    tag_name: str,
    filename: str,
    was_running: bool,
) -> Optional[Dict[str, Any]]:
    """Safely stops a running server and creates a preventive backup; aborts and returns None on backup error."""
    if was_running:
        _set_install_stage(downloader, "stopping", percent=62, filename=filename, detail="Deteniendo servidor de forma segura...")
        msg = "[Dockraft] Deteniendo servidor de forma segura para aplicar actualización..."
        process_manager._append_log(msg)
        await process_manager.broadcast_message({"type": "log", "data": msg})
        await process_manager.send_command("save-all", echo=False)
        await process_manager.stop_server()
        for _ in range(45):
            await asyncio.sleep(1)
            if process_manager.get_status() == "OFFLINE":
                break
        if process_manager.get_status() != "OFFLINE":
            kill_msg = "[Dockraft] El servidor tardó más de 45s en cerrar; forzando detención para proceder con seguridad..."
            process_manager._append_log(kill_msg)
            await process_manager.broadcast_message({"type": "log", "data": kill_msg})
            await process_manager.kill_server()

    _set_install_stage(downloader, "backing_up", percent=66, filename=filename, detail=f"Creando respaldo preventivo ({tag_name})...")
    bmsg = f"[Dockraft] Generando copia de seguridad preventiva ({tag_name})..."
    process_manager._append_log(bmsg)
    await process_manager.broadcast_message({"type": "log", "data": bmsg})
    pre_backup = await asyncio.to_thread(
        backup_manager.create_backup,
        scope="full",
        tag=tag_name,
        compression=True,
    )
    if pre_backup.get("status") == "error":
        err_detail = pre_backup.get("message") or "Error creando copia preventiva"
        err_msg = f"[Dockraft] Error al crear copia preventiva: {err_detail}. Abortando actualización."
        process_manager._append_log(err_msg)
        await process_manager.broadcast_message({"type": "log", "data": err_msg})
        _set_install_stage(downloader, f"error: {err_detail}", percent=0, filename=filename, detail=err_detail)
        if was_running:
            await process_manager.start_server()
        return None
    return pre_backup


@router.post("/api/installer/modpacks/resolve-stack", dependencies=[Depends(get_current_user)])
async def resolve_mod_stack_endpoint(req: ModStackResolveRequest):
    """Resolves compatible versions, deduplicated required deps, and conflicts for multiple mods."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.resolve_mod_stack(
            project_ids=req.project_ids,
            loader=req.loader,
            mc_version=req.mc_version,
            allow_beta=req.allow_beta,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("[Modpacks] Resolve stack failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Error resolviendo stack de mods: {str(e)}")


@router.post("/api/installer/modpacks/install-stack", dependencies=[Depends(get_current_user)])
async def install_mod_stack_endpoint(req: ModStackInstallRequest):
    """Installs a custom server with multiple selected mods and deduplicated dependencies."""
    process_manager, downloader, _, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Por favor detén el servidor antes de instalar un servidor con mods")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")
    if is_server_installed() and not req.force:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un servidor instalado en este directorio. Desbloquea la reinstalación para confirmar la sobrescritura.",
        )

    _set_install_stage(downloader, "preparing", percent=2, filename="mod-stack", detail="Resolviendo compatibilidad del stack de mods...")

    def _stage_cb(stage: str, pct: int, detail_msg: Optional[str] = None) -> None:
        _set_install_stage(downloader, stage, percent=pct, filename="mod-stack", detail=detail_msg)

    async def _run_stack():
        try:
            await modpack_mgr.install_mod_stack(
                project_ids=req.project_ids,
                loader=req.loader,
                mc_version=req.mc_version,
                downloader_obj=downloader,
                activity_manager_obj=activity_manager,
                server_name=req.server_name or "Mi Servidor Dockraft",
                min_ram=req.min_ram or "2G",
                max_ram=req.max_ram or "4G",
                aikar_flags=req.aikar_flags if req.aikar_flags is not None else True,
                cpu_cores=req.cpu_cores if req.cpu_cores is not None else 2,
                disk_limit_gb=req.disk_limit_gb if req.disk_limit_gb is not None else 10.0,
                java_path=req.java_path,
                allow_beta=req.allow_beta,
                force=bool(req.force),
                stage_cb=_stage_cb,
            )
        except Exception as ex:
            logger.error("[Modpacks] Install stack error: %s", ex)
            activity_manager.log(
                category="install",
                action="Error instalando servidor con mods",
                details=str(ex),
                user="admin",
                status="error",
            )
            _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename="mod-stack", detail=str(ex))

    _track_task(_run_stack())
    return {"status": "started", "loader": req.loader, "mc_version": req.mc_version, "mods_count": len(req.project_ids)}


@router.get("/api/installer/modpacks/update-status", dependencies=[Depends(get_current_user)])
async def get_modpack_update_status_endpoint(allow_beta: bool = Query(False)):
    """Checks for compatible Modrinth updates for an installed modpack."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.get_modpack_update_status(allow_beta=allow_beta)
    except Exception as e:
        logger.error("[Modpacks] Update status error: %s", e)
        raise HTTPException(status_code=502, detail=f"Error comprobando actualizaciones del modpack: {str(e)}")


@router.post("/api/installer/modpacks/update", dependencies=[Depends(get_current_user)])
async def update_installed_modpack_endpoint(req: ModpackUpdateRequest):
    """Safely updates the installed Modrinth modpack using staged pre-verification and preventive backup."""
    process_manager, downloader, backup_manager, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")

    cfg = settings.runtime_config
    project_id = cfg.get("modpack_id")
    if not project_id or cfg.get("modpack_type") != "modpack":
        raise HTTPException(status_code=400, detail="El servidor actual no proviene de un modpack de Modrinth")

    target_vid = req.version_id
    if not target_vid:
        st = await modpack_mgr.get_modpack_update_status(allow_beta=req.allow_beta)
        latest = st.get("latest_version")
        if not latest:
            raise HTTPException(status_code=400, detail="No hay versiones estables disponibles para actualizar")
        target_vid = latest["id"]

    was_running = process_manager.get_status() != "OFFLINE"
    _set_install_stage(downloader, "downloading_modpack", percent=2, filename=str(project_id), detail="Pre-descargando y verificando actualización del modpack...")

    def _stage_cb(stage: str, pct: int, detail_msg: Optional[str] = None) -> None:
        _set_install_stage(downloader, stage, percent=pct, filename=str(project_id), detail=detail_msg)

    async def _modpack_update_pipeline():
        staged = None
        try:
            # Phase 1: Download & SHA-512 verify BEFORE stopping or touching live server
            staged = await modpack_mgr.stage_modpack_update(
                project_id=str(project_id),
                target_version_id=str(target_vid),
                allow_beta=req.allow_beta,
                stage_cb=_stage_cb,
            )

            # Phase 2: Safe shutdown + preventive backup (aborts safely on backup failure)
            tag = f"pre-modpack-{staged['version_meta'].get('version_number') or target_vid}"
            pre_backup = await _safe_stop_and_backup(
                process_manager, backup_manager, downloader, tag_name=tag, filename=str(project_id), was_running=was_running
            )
            if pre_backup is None:
                return

            # Phase 3: Apply verified update + preserve server.properties & migrate custom mods
            res = await modpack_mgr.apply_staged_modpack_update(
                staged=staged,
                downloader_obj=downloader,
                activity_manager_obj=activity_manager,
                update_custom_mods=req.update_custom_mods,
                allow_beta=req.allow_beta,
                stage_cb=_stage_cb,
            )

            if was_running:
                _set_install_stage(downloader, "restarting", percent=98, filename=str(project_id), detail="Reiniciando servidor con el modpack actualizado...")
                await asyncio.sleep(1.5)
                await process_manager.start_server()

            _set_install_stage(
                downloader,
                "completed",
                percent=100,
                filename=str(project_id),
                detail=f"¡{res['pack_name']} actualizado a {res['version_name']}!",
            )
        except Exception as ex:
            logger.error("[Modpacks] Modpack update error: %s", ex)
            activity_manager.log(
                category="update",
                action="Error actualizando modpack",
                details=f"{project_id}: {ex}",
                user="admin",
                status="error",
            )
            _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename=str(project_id), detail=str(ex))
            if was_running and process_manager.get_status() == "OFFLINE":
                await process_manager.start_server()
        finally:
            if staged:
                try:
                    staged["mrpack_path"].unlink(missing_ok=True)
                except OSError:
                    pass
                shutil.rmtree(staged["stage_dir"], ignore_errors=True)

    _track_task(_modpack_update_pipeline())
    return {"status": "started", "project_id": project_id, "target_version_id": target_vid, "auto_stopping": was_running}


@router.get("/api/installer/mods/installed", dependencies=[Depends(get_current_user)])
async def list_installed_mods_endpoint(check_updates: bool = Query(True), allow_beta: bool = Query(False)):
    """Lists installed JARs in mods/, resolves Modrinth identity via SHA-512, and checks compatible updates."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.list_installed_mods(check_updates=check_updates, allow_beta=allow_beta)
    except Exception as e:
        logger.error("[Mods] Installed list error: %s", e)
        raise HTTPException(status_code=500, detail=f"Error leyendo mods instalados: {str(e)}")


@router.post("/api/installer/mods/add", dependencies=[Depends(get_current_user)])
async def add_installed_mod_endpoint(req: AddInstalledModRequest):
    """Adds a compatible Modrinth mod + required dependencies to the installed modded server."""
    process_manager, downloader, _, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado")
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Detén el servidor antes de instalar mods nuevos")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")

    try:
        return await modpack_mgr.add_mod_to_installed_server(
            project_id=req.project_id,
            version_id=req.version_id,
            allow_beta=req.allow_beta,
            activity_manager_obj=activity_manager,
        )
    except ModConflictError as ce:
        raise HTTPException(status_code=409, detail=str(ce))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("[Mods] Add mod error: %s", e)
        raise HTTPException(status_code=502, detail=f"Error instalando mod: {str(e)}")


@router.post("/api/installer/mods/update", dependencies=[Depends(get_current_user)])
async def update_installed_mods_endpoint(req: UpdateInstalledModsRequest):
    """Updates one or all outdated mods via staged SHA-512 verification and preventive backup."""
    process_manager, downloader, backup_manager, activity_manager, is_server_installed = _deps()
    modpack_mgr = _modpack_dep()

    if not is_server_installed():
        raise HTTPException(status_code=400, detail="No hay ningún servidor instalado")
    if _is_operation_running(downloader):
        raise HTTPException(status_code=409, detail="Ya hay una instalación o actualización en curso")

    was_running = process_manager.get_status() != "OFFLINE"
    _set_install_stage(downloader, "downloading_mods", percent=5, filename="mods", detail="Pre-descargando actualizaciones de mods...")

    def _stage_cb(stage: str, pct: int, detail_msg: Optional[str] = None) -> None:
        _set_install_stage(downloader, stage, percent=pct, filename="mods", detail=detail_msg)

    async def _mods_upd_pipeline():
        staged = None
        try:
            staged = await modpack_mgr.stage_mods_update(
                filenames=req.filenames,
                allow_beta=req.allow_beta,
                stage_cb=_stage_cb,
            )
            pre_backup = await _safe_stop_and_backup(
                process_manager, backup_manager, downloader, tag_name="pre-mods-update", filename="mods", was_running=was_running
            )
            if pre_backup is None:
                return

            res = await asyncio.to_thread(
                modpack_mgr.apply_staged_mods_update, staged, activity_manager
            )
            if was_running:
                _set_install_stage(downloader, "restarting", percent=96, filename="mods", detail="Reiniciando servidor con mods actualizados...")
                await asyncio.sleep(1.5)
                await process_manager.start_server()

            _set_install_stage(
                downloader,
                "completed",
                percent=100,
                filename="mods",
                detail=f"¡{res['count']} mod(s) actualizados correctamente!",
            )
        except Exception as ex:
            logger.error("[Mods] Mods update error: %s", ex)
            activity_manager.log(
                category="update",
                action="Error actualizando mods",
                details=str(ex),
                user="admin",
                status="error",
            )
            _set_install_stage(downloader, f"error: {str(ex)}", percent=0, filename="mods", detail=str(ex))
            if was_running and process_manager.get_status() == "OFFLINE":
                await process_manager.start_server()
        finally:
            if staged and staged.get("stage_dir"):
                shutil.rmtree(staged["stage_dir"], ignore_errors=True)

    _track_task(_mods_upd_pipeline())
    return {"status": "started", "auto_stopping": was_running}


@router.post("/api/installer/mods/toggle", dependencies=[Depends(get_current_user)])
async def toggle_installed_mod_endpoint(req: ToggleModRequest):
    """Enables or disables an installed mod cleanly while the server is offline."""
    process_manager, _, _, _, _ = _deps()
    modpack_mgr = _modpack_dep()
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Detén el servidor antes de activar o desactivar mods")
    try:
        return modpack_mgr.toggle_mod(req.filename)
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/api/installer/mods/{filename}", dependencies=[Depends(get_current_user)])
async def delete_installed_mod_endpoint(filename: str):
    """Deletes an installed mod file from mods/ while the server is offline."""
    process_manager, _, _, _, _ = _deps()
    modpack_mgr = _modpack_dep()
    if process_manager.get_status() != "OFFLINE":
        raise HTTPException(status_code=400, detail="Detén el servidor antes de eliminar mods")
    try:
        return modpack_mgr.delete_mod(filename)
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/api/installer/mods/check-compatibility", dependencies=[Depends(get_current_user)])
async def check_mods_compatibility_endpoint(
    target_mc: str = Query(...),
    target_loader: Optional[str] = Query(None),
    allow_beta: bool = Query(False),
):
    """Checks installed mods compatibility prior to a Minecraft version change."""
    modpack_mgr = _modpack_dep()
    try:
        return await modpack_mgr.check_mods_compatibility_for_target(
            target_mc=target_mc, target_loader=target_loader, allow_beta=allow_beta
        )
    except Exception as e:
        logger.error("[Mods] Compatibility check error: %s", e)
        raise HTTPException(status_code=502, detail=f"Error verificando compatibilidad: {str(e)}")



