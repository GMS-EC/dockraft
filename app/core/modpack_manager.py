import asyncio
import hashlib
import io
import ipaddress
import json
import logging
import os
import re
import shutil
import stat
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.config import APP_VERSION, settings
from app.core.fs_utils import PROTECTED_INTERNAL_FILES, atomic_write_json
from app.core.java_manager import JavaManager

logger = logging.getLogger("dockraft.modpacks")

MODRINTH_API_BASE = "https://api.modrinth.com/v2"
SUPPORTED_LOADERS = ("fabric", "neoforge", "forge", "quilt")
MODRINTH_HEADERS = {
    "User-Agent": f"Dockraft-Manager/{APP_VERSION} (https://github.com/GMS-EC/dockraft)",
}
MAX_MRPACK_BYTES = 512 * 1024 * 1024  # 512 MB hard limit
MANIFEST_FILENAME = ".dockraft_modpack_manifest.json"
PRESERVED_CONFIG_ON_UPDATE = {
    "server.properties",
    "ops.json",
    "whitelist.json",
    "allowlist.json",
    "banned-players.json",
    "banned-ips.json",
    "eula.txt",
}


class ModConflictError(ValueError):
    """Raised when attempting to add or update mods with mutual incompatibilities."""
    pass


class ModpackManager:
    """Manages Modrinth catalog discovery, dependency resolution, and .mrpack installation."""

    def __init__(self) -> None:
        self._search_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._project_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    @staticmethod
    def _validate_download_url(url: str) -> str:
        """Validates an external download URL to block SSRF / non-HTTPS targets."""
        raw = str(url or "").strip()
        parsed = urlparse(raw)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError(f"URL de descarga no permitida o insegura: {raw}")

        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
            raise ValueError(f"Host de descarga bloqueado por seguridad: {host}")

        try:
            ip_obj = ipaddress.ip_address(host)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                raise ValueError(f"Dirección IP de descarga bloqueada por seguridad: {host}")
        except ValueError as ip_err:
            # Raised either by ip_address() for a domain name OR by our security check above
            if "bloqueada por seguridad" in str(ip_err):
                raise
        return raw

    @staticmethod
    def _safe_target_path(data_dir: Path, rel_path: str) -> Path:
        """Resolves a relative mod/override path safely inside data_dir without ZipSlip."""
        cleaned = str(rel_path or "").replace("\\", "/").strip()
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]

        if not cleaned or "\x00" in cleaned or cleaned.startswith("/") or ":" in cleaned.split("/", 1)[0]:
            raise ValueError(f"Ruta inválida dentro del paquete: {rel_path}")

        posix_parts = PurePosixPath(cleaned).parts
        if not posix_parts or any(part in ("..", ".", "") for part in posix_parts):
            raise ValueError(f"Ruta no segura fuera del directorio de datos: {rel_path}")

        if posix_parts[0].lower() in PROTECTED_INTERNAL_FILES:
            raise ValueError(f"Archivo interno protegido por Dockraft: {rel_path}")

        data_resolved = data_dir.resolve()
        candidate = (data_resolved / Path(*posix_parts)).resolve()
        if not candidate.is_relative_to(data_resolved):
            raise ValueError(f"Intento de escritura fuera de data_dir bloqueado: {rel_path}")
        return candidate

    @staticmethod
    def _clean_previous_modded_install(data_dir: Path) -> None:
        """Removes previous server jars/mods/loaders safely when force-overwriting."""
        if not data_dir.exists():
            return
        for dirname in ("mods", "libraries"):
            dpath = data_dir / dirname
            if dpath.exists() and dpath.is_dir():
                shutil.rmtree(dpath, ignore_errors=True)

        for fname in ("run.sh", "run.bat", "user_jvm_args.txt", "quilt-server-launch.jar"):
            fpath = data_dir / fname
            if fpath.is_file():
                try:
                    fpath.unlink()
                except OSError:
                    pass

        for item in data_dir.iterdir():
            if item.is_file() and item.suffix.lower() == ".jar" and item.name.lower() not in PROTECTED_INTERNAL_FILES:
                try:
                    item.unlink()
                except OSError:
                    pass

    @staticmethod
    def _pick_preferred_mc_version(game_versions: List[str], preferred: Optional[str] = None) -> str:
        """Selects the requested MC version or the newest stable release in game_versions."""
        versions = [str(v).strip() for v in (game_versions or []) if str(v).strip()]
        if preferred and preferred in versions:
            return preferred
        if not versions:
            return ""
        stable_candidates = [v for v in versions if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)]
        if stable_candidates:
            stable_candidates.sort(key=lambda s: [int(p) for p in s.split(".")], reverse=True)
            return stable_candidates[0]
        return versions[-1]

    @staticmethod
    def _default_ram_for_modded() -> Dict[str, Any]:
        return {
            "min_ram": "2G",
            "max_ram": "4G",
            "min_recommended_gb": 4,
            "recommended_gb": 4,
        }

    @classmethod
    def _estimate_recommended_ram(
        cls,
        loader: str,
        project_type: str = "modpack",
        pack_size_bytes: int = 0,
        mod_count: int = 0,
        total_mod_bytes: int = 0,
        description_text: str = "",
    ) -> Dict[str, Any]:
        """Estimates discreet minimum/recommended RAM (-Xms / -Xmx) for a modpack or mod stack."""
        ldr = str(loader or "").lower().strip()
        ptype = str(project_type or "modpack").lower().strip()
        is_heavy_loader = ldr in ("forge", "neoforge")

        # Check if Modrinth description/body explicitly mentions a server RAM figure (3-10 GB)
        explicit_gb: Optional[int] = None
        if description_text:
            m = re.search(
                r"(?:recommended|minimum|server|allocate|assign|dedicate|requires?|mínim[oa]|recomendad[oa])[^\n.]{0,40}?(\d+)\s*(?:-\s*(\d+)\s*)?gb\s*(?:of\s+|de\s+)?ram"
                r"|(\d+)\s*(?:-\s*(\d+)\s*)?gb\s*(?:of\s+|de\s+)?ram\s*(?:recommended|minimum|required|recomendad[oa]|mínim[oa])",
                description_text,
                re.IGNORECASE,
            )
            if m:
                nums = [int(g) for g in m.groups() if g and g.isdigit()]
                valid = [n for n in nums if 3 <= n <= 10]
                if valid:
                    explicit_gb = max(valid)

        if ptype == "modpack":
            if explicit_gb and explicit_gb >= 6:
                min_gb, rec_gb = max(4, explicit_gb - 2), explicit_gb
            elif pack_size_bytes >= 35 * 1024 * 1024:
                min_gb, rec_gb = 6, 8
            elif is_heavy_loader or pack_size_bytes >= 12 * 1024 * 1024:
                min_gb, rec_gb = 4, 6
            else:
                min_gb, rec_gb = 4, (explicit_gb or 4)
        else:
            # Custom mod stack or single mod with dependencies
            if total_mod_bytes >= 50 * 1024 * 1024 or mod_count >= 15 or is_heavy_loader:
                min_gb, rec_gb = 4, 4
            elif mod_count >= 6 or total_mod_bytes >= 15 * 1024 * 1024:
                min_gb, rec_gb = 3, 4
            else:
                min_gb, rec_gb = 2, 3

        xms_gb = max(2, min_gb // 2) if rec_gb >= 4 else 1
        return {
            "min_ram": f"{xms_gb}G",
            "max_ram": f"{rec_gb}G",
            "min_recommended_gb": min_gb,
            "recommended_gb": rec_gb,
        }

    async def search_projects(
        self,
        query: str = "",
        project_type: str = "modpack",
        loader: Optional[str] = None,
        game_version: Optional[str] = None,
        limit: int = 12,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Searches Modrinth for server-compatible modpacks or mods."""
        ptype = str(project_type or "modpack").strip().lower()
        if ptype not in ("modpack", "mod"):
            raise ValueError("project_type debe ser 'modpack' o 'mod'")

        q = str(query or "").strip()
        ldr = str(loader or "").strip().lower() or None
        gv = str(game_version or "").strip() or None
        lim = max(1, min(int(limit), 30))
        off = max(0, int(offset))

        cache_key = f"{ptype}|{q.lower()}|{ldr or ''}|{gv or ''}|{lim}|{off}"
        now = time.time()
        cached = self._search_cache.get(cache_key)
        if cached and (now - cached[0] < 60.0):
            return cached[1]

        facets: List[List[str]] = [
            [f"project_type:{ptype}"],
            ["server_side:required", "server_side:optional"],
        ]
        if ldr in SUPPORTED_LOADERS:
            facets.append([f"categories:{ldr}"])
        if gv:
            facets.append([f"versions:{gv}"])

        params: Dict[str, Any] = {
            "facets": json.dumps(facets),
            "limit": lim,
            "offset": off,
            "index": "relevance" if q else "downloads",
        }
        if q:
            params["query"] = q

        async with httpx.AsyncClient(timeout=15.0, headers=MODRINTH_HEADERS) as client:
            resp = await client.get(f"{MODRINTH_API_BASE}/search", params=params)
            resp.raise_for_status()
            raw = resp.json()

        hits: List[Dict[str, Any]] = []
        for item in raw.get("hits", []):
            cats = item.get("categories") or []
            seen_loaders: List[str] = []
            for c in cats:
                cl = str(c).lower()
                if cl in SUPPORTED_LOADERS and cl not in seen_loaders:
                    seen_loaders.append(cl)
            if not seen_loaders:
                continue

            slug = item.get("slug") or item.get("project_id")
            hits.append({
                "project_id": item.get("project_id"),
                "slug": slug,
                "title": item.get("title") or slug,
                "description": item.get("description") or "",
                "author": item.get("author") or "",
                "icon_url": item.get("icon_url") or "",
                "downloads": int(item.get("downloads") or 0),
                "follows": int(item.get("follows") or 0),
                "categories": cats,
                "loaders": seen_loaders,
                "game_versions": item.get("versions") or [],
                "latest_version": item.get("latest_version") or "",
                "server_side": item.get("server_side") or "unknown",
                "project_type": ptype,
                "url": f"https://modrinth.com/{ptype}/{slug}",
            })

        result = {
            "hits": hits,
            "total_hits": int(raw.get("total_hits") or len(hits)),
            "offset": off,
            "limit": lim,
        }
        self._search_cache[cache_key] = (now, result)
        return result

    async def get_project_details(self, project_id: str) -> Dict[str, Any]:
        """Fetches Modrinth project metadata and server-compatible versions."""
        pid = str(project_id or "").strip()
        if not pid:
            raise ValueError("project_id inválido")

        now = time.time()
        cached = self._project_cache.get(pid)
        if cached and (now - cached[0] < 60.0):
            return cached[1]

        async with httpx.AsyncClient(timeout=15.0, headers=MODRINTH_HEADERS) as client:
            p_resp, v_resp = await asyncio.gather(
                client.get(f"{MODRINTH_API_BASE}/project/{pid}"),
                client.get(f"{MODRINTH_API_BASE}/project/{pid}/version"),
            )
            p_resp.raise_for_status()
            v_resp.raise_for_status()
            proj_raw = p_resp.json()
            vers_raw = v_resp.json()

        ptype = str(proj_raw.get("project_type") or "modpack").lower()
        slug = proj_raw.get("slug") or proj_raw.get("id") or pid
        proj_loaders = [l.lower() for l in (proj_raw.get("loaders") or []) if str(l).lower() in SUPPORTED_LOADERS]

        versions_out: List[Dict[str, Any]] = []
        for v in vers_raw:
            v_loaders = [str(l).lower() for l in (v.get("loaders") or []) if str(l).lower() in SUPPORTED_LOADERS]
            files = v.get("files") or []
            if not v_loaders or not files:
                continue

            if ptype == "modpack":
                primary = next(
                    (f for f in files if f.get("primary") and str(f.get("filename", "")).lower().endswith(".mrpack")),
                    None,
                ) or next((f for f in files if str(f.get("filename", "")).lower().endswith(".mrpack")), files[0])
            else:
                primary = next((f for f in files if f.get("primary")), files[0])

            versions_out.append({
                "id": v.get("id"),
                "name": v.get("name") or v.get("version_number"),
                "version_number": v.get("version_number") or v.get("id"),
                "version_type": str(v.get("version_type") or "release").lower(),
                "date_published": v.get("date_published"),
                "changelog": (v.get("changelog") or "")[:300],
                "downloads": int(v.get("downloads") or 0),
                "game_versions": v.get("game_versions") or [],
                "loaders": v_loaders,
                "dependencies": v.get("dependencies") or [],
                "primary_file": {
                    "filename": primary.get("filename"),
                    "url": primary.get("url"),
                    "size": int(primary.get("size") or 0),
                    "hashes": primary.get("hashes") or {},
                },
            })

        result = {
            "project": {
                "project_id": proj_raw.get("id") or pid,
                "slug": slug,
                "title": proj_raw.get("title") or slug,
                "description": proj_raw.get("description") or "",
                "icon_url": proj_raw.get("icon_url") or "",
                "downloads": int(proj_raw.get("downloads") or 0),
                "followers": int(proj_raw.get("followers") or 0),
                "categories": proj_raw.get("categories") or [],
                "loaders": proj_loaders,
                "game_versions": proj_raw.get("game_versions") or [],
                "server_side": proj_raw.get("server_side") or "unknown",
                "project_type": ptype,
                "url": f"https://modrinth.com/{ptype}/{slug}",
            },
            "versions": versions_out,
        }
        self._project_cache[pid] = (now, result)
        return result

    async def resolve_mod_dependencies(
        self,
        version_obj: Dict[str, Any],
        loader: str,
        mc_version: str,
        client: Optional[httpx.AsyncClient] = None,
        max_depth: int = 4,
        max_deps: int = 40,
        allow_beta: bool = False,
    ) -> List[Dict[str, Any]]:
        """Recursively resolves required server-side dependencies for an individual mod version."""
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=15.0, headers=MODRINTH_HEADERS)

        resolved: List[Dict[str, Any]] = []
        visited_projects: set = set()
        proj_meta_cache: Dict[str, Dict[str, Any]] = {}

        def _extract_primary(ver: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            files = ver.get("files") or []
            if not files:
                return None
            return next((f for f in files if f.get("primary")), files[0])

        async def _get_project_meta(pid: str) -> Dict[str, Any]:
            if pid in proj_meta_cache:
                return proj_meta_cache[pid]
            resp = await client.get(f"{MODRINTH_API_BASE}/project/{pid}")
            resp.raise_for_status()
            meta = resp.json()
            proj_meta_cache[pid] = meta
            return meta

        try:
            root_pid = version_obj.get("project_id")
            root_title = version_obj.get("project_title") or ""
            if root_pid and not root_title:
                try:
                    root_meta = await _get_project_meta(root_pid)
                    root_title = root_meta.get("title") or root_meta.get("slug") or root_pid
                except Exception:
                    root_title = str(root_pid)

            root_file = _extract_primary(version_obj)
            if not root_file:
                raise ValueError("La versión seleccionada del mod no contiene archivos descargables")

            if root_pid:
                visited_projects.add(root_pid)

            root_hashes = root_file.get("hashes") or {}
            resolved.append({
                "project_id": root_pid,
                "project_title": root_title or version_obj.get("name"),
                "version_id": version_obj.get("id"),
                "version_number": version_obj.get("version_number") or version_obj.get("name"),
                "filename": root_file.get("filename"),
                "url": root_file.get("url"),
                "sha512": root_hashes.get("sha512"),
                "sha1": root_hashes.get("sha1"),
                "size": int(root_file.get("size") or 0),
                "is_root": True,
            })

            queue: List[Tuple[Dict[str, Any], int]] = [
                (dep, 1)
                for dep in (version_obj.get("dependencies") or [])
                if dep.get("dependency_type") == "required"
            ]

            while queue and len(resolved) < (max_deps + 1):
                dep, depth = queue.pop(0)
                if depth > max_depth:
                    continue

                dep_vid = dep.get("version_id")
                dep_pid = dep.get("project_id")
                if dep_pid and dep_pid in visited_projects:
                    continue

                dep_ver: Optional[Dict[str, Any]] = None
                try:
                    if dep_vid:
                        v_resp = await client.get(f"{MODRINTH_API_BASE}/version/{dep_vid}")
                        v_resp.raise_for_status()
                        dep_ver = v_resp.json()
                        dep_pid = dep_pid or dep_ver.get("project_id")
                    elif dep_pid:
                        v_resp = await client.get(
                            f"{MODRINTH_API_BASE}/project/{dep_pid}/version",
                            params={
                                "loaders": json.dumps([loader]),
                                "game_versions": json.dumps([mc_version]),
                            },
                        )
                        v_resp.raise_for_status()
                        candidates = v_resp.json() or []
                        if candidates:
                            allowed_dep_types = ("release", "beta") if allow_beta else ("release",)
                            dep_ver = next(
                                (
                                    c
                                    for c in candidates
                                    if str(c.get("version_type") or "release").lower() in allowed_dep_types
                                ),
                                None,
                            )
                except Exception as exc:
                    logger.warning("[Modpack] Could not resolve dependency (%s/%s): %s", dep_pid, dep_vid, exc)
                    continue

                if not dep_ver or not dep_pid or dep_pid in visited_projects:
                    continue

                visited_projects.add(dep_pid)

                dep_title = str(dep_pid)
                try:
                    meta = await _get_project_meta(dep_pid)
                    if str(meta.get("server_side", "")).lower() == "unsupported":
                        continue
                    dep_title = meta.get("title") or meta.get("slug") or dep_title
                except Exception:
                    pass

                dfile = _extract_primary(dep_ver)
                if not dfile:
                    continue

                dhashes = dfile.get("hashes") or {}
                resolved.append({
                    "project_id": dep_pid,
                    "project_title": dep_title,
                    "version_id": dep_ver.get("id"),
                    "version_number": dep_ver.get("version_number") or dep_ver.get("name"),
                    "filename": dfile.get("filename"),
                    "url": dfile.get("url"),
                    "sha512": dhashes.get("sha512"),
                    "sha1": dhashes.get("sha1"),
                    "size": int(dfile.get("size") or 0),
                    "is_root": False,
                })

                if depth < max_depth:
                    for sub_dep in dep_ver.get("dependencies") or []:
                        if sub_dep.get("dependency_type") == "required":
                            queue.append((sub_dep, depth + 1))
        finally:
            if own_client:
                await client.aclose()

        return resolved

    async def inspect_version_requirements(
        self,
        project_id: str,
        version_id: str,
        preferred_loader: Optional[str] = None,
        preferred_mc_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns loader, Minecraft version, recommended Java/RAM, and dependencies without heavy downloads."""
        pid = str(project_id or "").strip()
        vid = str(version_id or "").strip()
        if not pid or not vid:
            raise ValueError("Se requieren project_id y version_id")

        async with httpx.AsyncClient(timeout=15.0, headers=MODRINTH_HEADERS) as client:
            p_resp, v_resp = await asyncio.gather(
                client.get(f"{MODRINTH_API_BASE}/project/{pid}"),
                client.get(f"{MODRINTH_API_BASE}/version/{vid}"),
            )
            p_resp.raise_for_status()
            v_resp.raise_for_status()
            proj = p_resp.json()
            ver = v_resp.json()

            ptype = str(proj.get("project_type") or "modpack").lower()
            v_loaders = [str(l).lower() for l in (ver.get("loaders") or []) if str(l).lower() in SUPPORTED_LOADERS]
            if not v_loaders:
                raise ValueError("Esta versión no utiliza un cargador de servidor compatible (Fabric, NeoForge, Forge o Quilt)")

            req_loader = str(preferred_loader or "").strip().lower()
            loader = req_loader if req_loader in v_loaders else v_loaders[0]
            mc_version = self._pick_preferred_mc_version(ver.get("game_versions") or [], preferred=preferred_mc_version)
            recommended_java = JavaManager.get_recommended_java(mc_version) if mc_version else 21

            files = ver.get("files") or []
            primary = next((f for f in files if f.get("primary")), files[0] if files else {})
            pack_size = int(primary.get("size") or 0)
            desc_text = f"{proj.get('description') or ''}\n{proj.get('body') or ''}"

            if ptype == "modpack":
                recommended_ram = self._estimate_recommended_ram(
                    loader=loader,
                    project_type="modpack",
                    pack_size_bytes=pack_size,
                    description_text=desc_text,
                )
                return {
                    "project_id": proj.get("id") or pid,
                    "project_title": proj.get("title") or proj.get("slug"),
                    "project_type": "modpack",
                    "version_id": ver.get("id") or vid,
                    "version_name": ver.get("name") or ver.get("version_number"),
                    "mc_version": mc_version,
                    "loader": loader,
                    "available_loaders": v_loaders,
                    "available_game_versions": ver.get("game_versions") or [],
                    "recommended_java": recommended_java,
                    "recommended_ram": recommended_ram,
                    "pack_filename": primary.get("filename"),
                    "pack_size_bytes": pack_size,
                    "dependencies": [],
                    "total_files": 1,
                    "total_size_bytes": pack_size,
                }

            ver_with_title = dict(ver)
            ver_with_title["project_id"] = ver.get("project_id") or proj.get("id") or pid
            ver_with_title["project_title"] = proj.get("title") or proj.get("slug")
            deps_all = await self.resolve_mod_dependencies(
                ver_with_title,
                loader=loader,
                mc_version=mc_version,
                client=client,
            )
            deps_only = [d for d in deps_all if not d.get("is_root")]
            total_bytes = sum(int(d.get("size") or 0) for d in deps_all)
            recommended_ram = self._estimate_recommended_ram(
                loader=loader,
                project_type="mod",
                mod_count=len(deps_all),
                total_mod_bytes=total_bytes,
                description_text=desc_text,
            )
            return {
                "project_id": proj.get("id") or pid,
                "project_title": proj.get("title") or proj.get("slug"),
                "project_type": "mod",
                "version_id": ver.get("id") or vid,
                "version_name": ver.get("name") or ver.get("version_number"),
                "mc_version": mc_version,
                "loader": loader,
                "available_loaders": v_loaders,
                "available_game_versions": ver.get("game_versions") or [],
                "recommended_java": recommended_java,
                "recommended_ram": recommended_ram,
                "pack_filename": primary.get("filename"),
                "pack_size_bytes": int(primary.get("size") or 0),
                "dependencies": deps_only,
                "total_files": len(deps_all),
                "total_size_bytes": total_bytes,
            }

    @staticmethod
    def parse_mrpack_manifest(mrpack_path: Path) -> Dict[str, Any]:
        """Parses modrinth.index.json inside an .mrpack archive and filters server-compatible files."""
        with zipfile.ZipFile(mrpack_path, "r") as zf:
            if "modrinth.index.json" not in zf.namelist():
                raise ValueError("El archivo .mrpack no contiene 'modrinth.index.json'")
            manifest = json.loads(zf.read("modrinth.index.json").decode("utf-8"))

        if manifest.get("formatVersion") != 1 or manifest.get("game") != "minecraft":
            raise ValueError("Formato .mrpack no compatible (se requiere formatVersion=1 para Minecraft)")

        deps = manifest.get("dependencies") or {}
        mc_version = str(deps.get("minecraft") or "").strip()
        if not mc_version:
            raise ValueError("El manifiesto .mrpack no especifica la versión de Minecraft")

        loader_map = (
            ("fabric-loader", "fabric"),
            ("neoforge", "neoforge"),
            ("forge", "forge"),
            ("quilt-loader", "quilt"),
        )
        loader_type = None
        loader_version = None
        for dep_key, canonical in loader_map:
            if deps.get(dep_key):
                loader_type = canonical
                loader_version = str(deps[dep_key]).strip()
                break

        if not loader_type or not loader_version:
            raise ValueError("El archivo .mrpack no especifica un cargador compatible (Fabric, NeoForge, Forge o Quilt)")

        server_files: List[Dict[str, Any]] = []
        client_only_files: List[Dict[str, Any]] = []
        skipped_client_files = 0
        for entry in manifest.get("files", []):
            env_info = entry.get("env") or {}
            if str(env_info.get("server", "required")).lower() == "unsupported":
                skipped_client_files += 1
                rel_p = str(entry.get("path") or "").replace("\\", "/")
                if rel_p.startswith("mods/") and rel_p.lower().endswith(".jar"):
                    client_only_files.append(entry)
                continue
            server_files.append(entry)

        return {
            "name": manifest.get("name") or mrpack_path.stem,
            "version_id": manifest.get("versionId") or "",
            "summary": manifest.get("summary") or "",
            "mc_version": mc_version,
            "loader_type": loader_type,
            "loader_version": loader_version,
            "server_files": server_files,
            "client_only_files": client_only_files,
            "skipped_client_files": skipped_client_files,
        }

    BUILTIN_LOADER_MOD_IDS = {
        "minecraft",
        "java",
        "fabricloader",
        "fabric-loader",
        "fabric",
        "fabric-api",
        "fabric_api",
        "quilt_loader",
        "quilt-loader",
        "quilt_base",
        "forge",
        "neoforge",
        "fml",
    }

    @classmethod
    def _inspect_mod_jar_metadata(cls, jar_path: Path) -> Dict[str, Any]:
        """Extracts provided mod IDs, required mod IDs, and environment from a mod JAR archive."""
        provided: set = set()
        required: set = set()
        environment = "*"
        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                names = set(zf.namelist())
                if "fabric.mod.json" in names:
                    raw = zf.read("fabric.mod.json").decode("utf-8", errors="replace")
                    fmj = json.loads(raw, strict=False)
                    if isinstance(fmj, dict):
                        environment = str(fmj.get("environment") or "*").strip().lower()
                        mid = str(fmj.get("id") or "").strip()
                        if mid:
                            provided.add(mid)
                        for p in (fmj.get("provides") or []):
                            if isinstance(p, str) and p.strip():
                                provided.add(p.strip())
                        for j in (fmj.get("jars") or []):
                            jfile = j.get("file") if isinstance(j, dict) else None
                            if jfile and jfile in names:
                                try:
                                    with zipfile.ZipFile(io.BytesIO(zf.read(jfile)), "r") as nzf:
                                        if "fabric.mod.json" in nzf.namelist():
                                            nfmj = json.loads(
                                                nzf.read("fabric.mod.json").decode("utf-8", errors="replace"),
                                                strict=False,
                                            )
                                            if isinstance(nfmj, dict):
                                                nmid = str(nfmj.get("id") or "").strip()
                                                if nmid:
                                                    provided.add(nmid)
                                                for np in (nfmj.get("provides") or []):
                                                    if isinstance(np, str) and np.strip():
                                                        provided.add(np.strip())
                                except Exception:
                                    pass
                        if environment != "client" and isinstance(fmj.get("depends"), dict):
                            for dep_k in fmj["depends"].keys():
                                dk = str(dep_k or "").strip()
                                if dk and dk not in cls.BUILTIN_LOADER_MOD_IDS:
                                    required.add(dk)
                elif "quilt.mod.json" in names:
                    raw = zf.read("quilt.mod.json").decode("utf-8", errors="replace")
                    qmj = json.loads(raw, strict=False)
                    ql = (qmj.get("quilt_loader") or {}) if isinstance(qmj, dict) else {}
                    mc_env = ((qmj.get("minecraft") or {}).get("environment") or "*") if isinstance(qmj, dict) else "*"
                    environment = str(mc_env).strip().lower()
                    mid = str(ql.get("id") or "").strip()
                    if mid:
                        provided.add(mid)
                    for p in (ql.get("provides") or []):
                        pid = p.get("id") if isinstance(p, dict) else str(p)
                        if pid and str(pid).strip():
                            provided.add(str(pid).strip())
                    if environment != "client":
                        for dep in (ql.get("depends") or []):
                            did = dep.get("id") if isinstance(dep, dict) else str(dep)
                            is_opt = bool(dep.get("optional")) if isinstance(dep, dict) else False
                            if did and not is_opt and str(did).strip() not in cls.BUILTIN_LOADER_MOD_IDS:
                                required.add(str(did).strip())
                else:
                    for toml_path in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                        if toml_path in names:
                            txt = zf.read(toml_path).decode("utf-8", errors="replace")
                            try:
                                import tomllib

                                parsed_toml = tomllib.loads(txt)
                                for mod_entry in (parsed_toml.get("mods") or []):
                                    if isinstance(mod_entry, dict):
                                        mid = str(mod_entry.get("modId") or "").strip()
                                        if mid:
                                            provided.add(mid)
                                deps_section = parsed_toml.get("dependencies")
                                if isinstance(deps_section, dict):
                                    for dep_list in deps_section.values():
                                        if not isinstance(dep_list, list):
                                            continue
                                        for dep_item in dep_list:
                                            if not isinstance(dep_item, dict):
                                                continue
                                            did = str(dep_item.get("modId") or "").strip()
                                            if not did or did.lower() in cls.BUILTIN_LOADER_MOD_IDS:
                                                continue
                                            side = str(dep_item.get("side") or "BOTH").strip().upper()
                                            if side == "CLIENT":
                                                continue
                                            dep_type = str(dep_item.get("type") or "").strip().lower()
                                            is_req = (dep_type == "required") if dep_type else bool(dep_item.get("mandatory", False))
                                            if is_req:
                                                required.add(did)
                            except Exception:
                                for m in re.finditer(r'modId\s*=\s*["\']([^"\']+)["\']', txt):
                                    mid = m.group(1).strip()
                                    if mid:
                                        provided.add(mid)
                            break
        except Exception:
            pass
        return {"provided_ids": provided, "required_ids": required, "environment": environment}

    @classmethod
    def _find_missing_mod_ids_in_dir(cls, mods_dir: Path) -> set:
        """Scans active .jar files in mods_dir and returns any required mod IDs that are not provided."""
        if not mods_dir.is_dir():
            return set()
        all_provided = set(cls.BUILTIN_LOADER_MOD_IDS)
        all_required: set = set()
        for jar in mods_dir.iterdir():
            if not jar.is_file() or not jar.name.lower().endswith(".jar"):
                continue
            meta = cls._inspect_mod_jar_metadata(jar)
            for pid in meta["provided_ids"]:
                all_provided.add(pid)
                all_provided.add(pid.lower())
                all_provided.add(pid.lower().replace("-", "_"))
                all_provided.add(pid.lower().replace("_", "-"))
            if meta["environment"] != "client":
                for rid in meta["required_ids"]:
                    all_required.add(rid)
        missing = set()
        for rid in all_required:
            rl = rid.lower()
            if (
                rid not in all_provided
                and rl not in all_provided
                and rl.replace("-", "_") not in all_provided
                and rl.replace("_", "-") not in all_provided
            ):
                missing.add(rid)
        return missing

    async def _rescue_missing_mrpack_dependencies(
        self,
        client: httpx.AsyncClient,
        target_root: Path,
        client_only_files: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Rescues shared library JARs mis-tagged as server=unsupported in .mrpack if required by installed server mods."""
        if not client_only_files:
            return []
        mods_dir = target_root / "mods"
        rescued: List[Dict[str, Any]] = []
        attempted_paths: set = set()

        for _ in range(3):
            missing_ids = await asyncio.to_thread(self._find_missing_mod_ids_in_dir, mods_dir)
            if not missing_ids:
                break

            candidates: List[Dict[str, Any]] = []
            for entry in client_only_files:
                rel = str(entry.get("path") or "").replace("\\", "/")
                if rel in attempted_paths:
                    continue
                fname_low = Path(rel).stem.lower()
                tokens = set(re.split(r"[^a-z0-9]+", fname_low))
                for mid in missing_ids:
                    ml = mid.lower()
                    ml_flat = re.sub(r"[^a-z0-9]", "", ml)
                    fname_flat = re.sub(r"[^a-z0-9]", "", fname_low)
                    if ml in tokens or fname_low.startswith(ml) or (len(ml_flat) >= 3 and fname_flat.startswith(ml_flat)):
                        candidates.append(entry)
                        break

            if not candidates:
                break

            rescued_in_pass = 0
            for entry in candidates:
                rel = str(entry.get("path") or "").replace("\\", "/")
                attempted_paths.add(rel)
                dest = self._safe_target_path(target_root, rel)
                hashes = entry.get("hashes") or {}
                try:
                    await self._download_verified_file(
                        client,
                        entry.get("downloads") or [],
                        dest,
                        expected_sha512=hashes.get("sha512"),
                        expected_sha1=hashes.get("sha1"),
                    )
                    meta = await asyncio.to_thread(self._inspect_mod_jar_metadata, dest)
                    if meta["environment"] == "client":
                        dest.unlink(missing_ok=True)
                        continue
                    sha512_val = hashes.get("sha512") or self._compute_file_sha512(dest)
                    rescued.append({
                        "rel_path": rel,
                        "dest_path": dest,
                        "sha512": sha512_val,
                    })
                    rescued_in_pass += 1
                    logger.info("[Modpacks] Rescued required server dependency from .mrpack: %s", rel)
                except Exception as exc:
                    dest.unlink(missing_ok=True)
                    logger.warning("[Modpacks] Failed rescuing dependency %s: %s", rel, exc)

            if rescued_in_pass == 0:
                break

        return rescued

    async def auto_heal_missing_server_dependencies(
        self,
        target_root: Optional[Path] = None,
        loader: Optional[str] = None,
        mc_version: Optional[str] = None,
        log_cb: Optional[Callable[[str], Any]] = None,
    ) -> List[str]:
        """Scans mods/ for missing required mod IDs (e.g. athena, fusion) and auto-installs them from Modrinth."""
        root_dir = target_root or settings.data_dir
        mods_dir = root_dir / "mods"
        if not mods_dir.is_dir():
            return []

        cfg = settings.runtime_config
        ldr = str(loader or cfg.get("server_type") or "").lower().strip()
        mc = str(mc_version or cfg.get("server_version") or "").strip()
        if ldr not in SUPPORTED_LOADERS or not mc:
            return []

        missing_ids = await asyncio.to_thread(self._find_missing_mod_ids_in_dir, mods_dir)
        if not missing_ids:
            return []

        async def _emit(msg: str) -> None:
            logger.info(msg)
            if log_cb:
                res = log_cb(msg)
                if asyncio.iscoroutine(res):
                    await res

        await _emit(
            f"[Dockraft] Detectadas dependencias requeridas faltantes en mods/ ({', '.join(sorted(missing_ids))}). Auto-reparando desde Modrinth..."
        )
        healed_files: List[str] = []
        manifest = self.read_manifest(root_dir)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
            for mid in sorted(missing_ids):
                # Re-check in case an earlier healed dependency already satisfied it
                still_missing = await asyncio.to_thread(self._find_missing_mod_ids_in_dir, mods_dir)
                if mid not in still_missing:
                    continue

                candidate_pids: List[str] = [mid]
                try:
                    s_resp = await client.get(
                        f"{MODRINTH_API_BASE}/search",
                        params={
                            "query": mid,
                            "limit": 5,
                            "facets": json.dumps([
                                [f"categories:{ldr}"],
                                [f"versions:{mc}"],
                                ["project_type:mod"],
                            ]),
                        },
                    )
                    if s_resp.status_code == 200:
                        for hit in (s_resp.json().get("hits") or []):
                            hpid = hit.get("project_id")
                            if hpid and hpid not in candidate_pids:
                                candidate_pids.append(hpid)
                except Exception:
                    pass

                for cpid in candidate_pids:
                    try:
                        v_resp = await client.get(
                            f"{MODRINTH_API_BASE}/project/{cpid}/version",
                            params={"loaders": json.dumps([ldr]), "game_versions": json.dumps([mc])},
                        )
                        if v_resp.status_code != 200:
                            continue
                        vers = v_resp.json() or []
                        chosen = (
                            self._select_compatible_version(vers, ldr, mc, allow_beta=False)
                            or self._select_compatible_version(vers, ldr, mc, allow_beta=True)
                        )
                        if not chosen:
                            continue
                        files = chosen.get("files") or []
                        pfile = next((f for f in files if f.get("primary")), files[0] if files else None)
                        if not pfile or not pfile.get("url"):
                            continue
                        fname = Path(str(pfile.get("filename") or f"{mid}.jar")).name
                        tmp_dest = mods_dir / f".heal_{uuid.uuid4().hex[:8]}_{fname}"
                        hashes = pfile.get("hashes") or {}
                        await self._download_verified_file(
                            client,
                            [pfile["url"]],
                            tmp_dest,
                            expected_sha512=hashes.get("sha512"),
                            expected_sha1=hashes.get("sha1"),
                        )
                        meta = await asyncio.to_thread(self._inspect_mod_jar_metadata, tmp_dest)
                        prov_norm = {p.lower().replace("-", "_") for p in meta["provided_ids"]}
                        mid_norm = mid.lower().replace("-", "_")
                        if meta["environment"] == "client" or (meta["provided_ids"] and mid_norm not in prov_norm):
                            tmp_dest.unlink(missing_ok=True)
                            continue

                        final_dest = self._safe_target_path(root_dir, f"mods/{fname}")
                        tmp_dest.replace(final_dest)
                        healed_files.append(fname)
                        sha_val = hashes.get("sha512") or self._compute_file_sha512(final_dest)
                        if manifest is not None:
                            mfiles = [
                                e for e in (manifest.get("managed_files") or [])
                                if e.get("path") != f"mods/{fname}"
                            ]
                            mfiles.append({
                                "path": f"mods/{fname}",
                                "sha512": sha_val,
                                "origin": "modpack",
                                "project_id": chosen.get("project_id") or cpid,
                                "version_id": chosen.get("id"),
                            })
                            manifest["managed_files"] = mfiles
                        await _emit(f"[Dockraft] Dependencia instalada automáticamente: {fname}")
                        break
                    except Exception:
                        continue

        if healed_files and manifest is not None:
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.write_manifest(root_dir, manifest)

        return healed_files

    async def _download_verified_file(
        self,
        client: httpx.AsyncClient,
        urls: List[str],
        dest_path: Path,
        expected_sha512: Optional[str] = None,
        expected_sha1: Optional[str] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """Streams a file from validated HTTPS URLs with retries and SHA-512/SHA-1 verification."""
        if not urls:
            raise ValueError(f"Sin URLs de descarga disponibles para {dest_path.name}")

        validated_urls = [self._validate_download_url(u) for u in urls]
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        last_err: Optional[Exception] = None

        for url in validated_urls:
            for attempt in range(1, 4):
                tmp_path = dest_path.parent / f".{dest_path.name}.tmp.{uuid.uuid4().hex[:8]}"
                try:
                    sha512_h = hashlib.sha512() if expected_sha512 else None
                    sha1_h = hashlib.sha1() if expected_sha1 else None

                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()
                        self._validate_download_url(str(resp.url))
                        total = int(resp.headers.get("content-length", 0) or 0)
                        downloaded = 0

                        with open(tmp_path, "wb") as fh:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                fh.write(chunk)
                                if sha512_h:
                                    sha512_h.update(chunk)
                                if sha1_h:
                                    sha1_h.update(chunk)
                                downloaded += len(chunk)
                                if progress_cb:
                                    progress_cb(downloaded, total)

                    if expected_sha512 and sha512_h:
                        actual_512 = sha512_h.hexdigest().lower()
                        if actual_512 != expected_sha512.strip().lower():
                            raise ValueError(f"Fallo verificación SHA-512 en {dest_path.name}")
                    if expected_sha1 and sha1_h:
                        actual_1 = sha1_h.hexdigest().lower()
                        if actual_1 != expected_sha1.strip().lower():
                            raise ValueError(f"Fallo verificación SHA-1 en {dest_path.name}")

                    tmp_path.replace(dest_path)
                    return dest_path
                except Exception as exc:
                    last_err = exc
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    if attempt < 3:
                        await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(f"Error descargando {dest_path.name}: {last_err}")

    def _extract_mrpack_overrides(
        self, mrpack_path: Path, data_dir: Path, preserve_server_properties: bool = False
    ) -> int:
        """Extracts overrides/ and then server-overrides/ into data_dir safely."""
        max_entries = 25000
        max_total_bytes = 2 * 1024 * 1024 * 1024
        max_ratio = 100.0
        total_extracted = 0
        files_written = 0
        data_resolved = data_dir.resolve()

        with zipfile.ZipFile(mrpack_path, "r") as zf:
            members = zf.infolist()
            if len(members) > max_entries:
                raise ValueError(f"El archivo .mrpack excede el límite de entradas ({max_entries})")

            for info in members:
                if info.is_dir():
                    continue
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise ValueError(f"Entrada symlink no permitida en .mrpack: {info.filename}")
                if info.compress_size > 0 and (info.file_size / info.compress_size) > max_ratio:
                    raise ValueError(f"Ratio de compresión sospechoso en {info.filename}")
                total_extracted += info.file_size
                if total_extracted > max_total_bytes:
                    raise ValueError("El contenido extraído de .mrpack excede el límite máximo permitido")

            for prefix in ("overrides/", "server-overrides/"):
                for info in members:
                    if info.is_dir():
                        continue
                    norm_name = info.filename.replace("\\", "/")
                    if not norm_name.startswith(prefix):
                        continue
                    rel = norm_name[len(prefix):]
                    if not rel or rel.endswith("/"):
                        continue

                    try:
                        target = self._safe_target_path(data_resolved, rel)
                    except ValueError as ve:
                        # Skip protected Dockraft internal files cleanly, but re-raise traversal attempts
                        if "protegido" in str(ve):
                            continue
                        raise

                    if preserve_server_properties and "/" not in rel.strip("/") and rel.lower() in PRESERVED_CONFIG_ON_UPDATE and target.exists():
                        continue

                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, "r") as src, open(target, "wb") as dst:
                        while True:
                            chunk = src.read(65536)
                            if not chunk:
                                break
                            dst.write(chunk)
                    files_written += 1

        return files_written

    async def _install_loader(
        self,
        downloader_obj: Any,
        loader_type: str,
        mc_version: str,
        loader_version: Optional[str],
        java_bin: str,
        stage_cb: Callable[[str, int, Optional[str]], None],
    ) -> str:
        """Downloads and installs the exact mod loader server binary for Fabric, NeoForge, Forge, or Quilt."""
        ldr = loader_type.lower().strip()
        stage_cb(
            "installing_loader",
            30,
            f"Instalando {ldr.upper()} ({mc_version}" + (f" · {loader_version}" if loader_version else "") + ")...",
        )

        if ldr == "fabric":
            dl_url = await downloader_obj.get_fabric_download_url(mc_version, loader_version=loader_version)
            try:
                await downloader_obj.download_file(
                    dl_url,
                    "server.jar",
                    verify_integrity=True,
                    allowed_hosts={"fabricmc.net"},
                    complete_on_finish=False,
                )
            except Exception as exc:
                if loader_version and "404" in str(exc):
                    logger.warning("[Modpack] Exact Fabric loader %s failed with 404, falling back to latest", loader_version)
                    fallback_url = await downloader_obj.get_fabric_download_url(mc_version, loader_version=None)
                    await downloader_obj.download_file(
                        fallback_url,
                        "server.jar",
                        verify_integrity=True,
                        allowed_hosts={"fabricmc.net"},
                        complete_on_finish=False,
                    )
                else:
                    raise
            return "server.jar"

        if ldr == "neoforge":
            nf_ver = loader_version
            dl_url = await downloader_obj.get_neoforge_download_url(mc_version, neoforge_version=nf_ver)
            try:
                installer_path = await downloader_obj.download_file(
                    dl_url,
                    "neoforge-installer.jar",
                    verify_integrity=True,
                    allowed_hosts={"neoforged.net"},
                    complete_on_finish=False,
                )
            except Exception as exc:
                if nf_ver and "404" in str(exc):
                    fallback_url = await downloader_obj.get_neoforge_download_url(mc_version, neoforge_version=None)
                    installer_path = await downloader_obj.download_file(
                        fallback_url,
                        "neoforge-installer.jar",
                        verify_integrity=True,
                        allowed_hosts={"neoforged.net"},
                        complete_on_finish=False,
                    )
                else:
                    raise
            stage_cb("installing_loader", 40, "Ejecutando instalador de servidor NeoForge...")
            res = await downloader_obj.install_neoforge_server(installer_path, java_bin=java_bin)
            return res.get("server_file", "run.bat" if os.name == "nt" else "run.sh")

        if ldr == "forge":
            clean_forge_build = loader_version
            if clean_forge_build and clean_forge_build.startswith(f"{mc_version}-"):
                clean_forge_build = clean_forge_build[len(mc_version) + 1:]
            dl_url = await downloader_obj.get_forge_download_url(mc_version, forge_build=clean_forge_build)
            try:
                installer_path = await downloader_obj.download_file(
                    dl_url,
                    "forge-installer.jar",
                    verify_integrity=True,
                    allowed_hosts={"minecraftforge.net"},
                    complete_on_finish=False,
                )
            except Exception as exc:
                if clean_forge_build and "404" in str(exc):
                    fallback_url = await downloader_obj.get_forge_download_url(mc_version, forge_build=None)
                    installer_path = await downloader_obj.download_file(
                        fallback_url,
                        "forge-installer.jar",
                        verify_integrity=True,
                        allowed_hosts={"minecraftforge.net"},
                        complete_on_finish=False,
                    )
                else:
                    raise
            stage_cb("installing_loader", 40, "Ejecutando instalador de servidor Forge...")
            res = await downloader_obj.install_forge_server(installer_path, java_bin=java_bin)
            return res.get("server_file", "run.bat" if os.name == "nt" else "run.sh")

        if ldr == "quilt":
            q_info = await downloader_obj.get_quilt_installer_info()
            installer_path = await downloader_obj.download_file(
                q_info["url"],
                "quilt-installer.jar",
                verify_integrity=True,
                expected_sha256=q_info.get("sha256"),
                allowed_hosts={"quiltmc.org"},
                complete_on_finish=False,
            )
            stage_cb("installing_loader", 40, "Ejecutando instalador de servidor Quilt...")
            res = await downloader_obj.install_quilt_server(
                installer_path,
                mc_version=mc_version,
                loader_version=loader_version,
                java_bin=java_bin,
            )
            return res.get("server_file", "quilt-server-launch.jar")

        raise ValueError(f"Cargador de mods no soportado: {loader_type}")

    async def install_from_mrpack(
        self,
        mrpack_path: Path,
        downloader_obj: Any,
        activity_manager_obj: Any,
        server_name: str = "Mi Servidor Dockraft",
        min_ram: str = "2G",
        max_ram: str = "4G",
        aikar_flags: bool = True,
        cpu_cores: int = 2,
        disk_limit_gb: float = 10.0,
        java_path: Optional[str] = None,
        force: bool = False,
        pack_meta: Optional[Dict[str, Any]] = None,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Installs a complete modded server from a validated .mrpack archive."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("preparing", 25, "Analizando manifiesto modrinth.index.json...")

        manifest = await asyncio.to_thread(self.parse_mrpack_manifest, mrpack_path)
        mc_version = manifest["mc_version"]
        loader_type = manifest["loader_type"]
        loader_version = manifest["loader_version"]
        server_files = manifest["server_files"]
        skipped_client = manifest["skipped_client_files"]

        resolved_java = java_path if (java_path and java_path != "java") else await asyncio.to_thread(
            JavaManager.get_best_java_path, mc_version
        )

        if force:
            await asyncio.to_thread(self._clean_previous_modded_install, settings.data_dir)

        default_server_file = (
            ("run.bat" if os.name == "nt" else "run.sh")
            if loader_type in ("forge", "neoforge")
            else ("quilt-server-launch.jar" if loader_type == "quilt" else "server.jar")
        )
        meta = pack_meta or {}
        pack_name = meta.get("modpack_name") or manifest["name"]
        base_cfg = {
            "server_type": loader_type,
            "server_version": mc_version,
            "server_file": default_server_file,
            "server_name": server_name or pack_name,
            "java_path": resolved_java or "java",
            "min_ram": min_ram or "2G",
            "max_ram": max_ram or "4G",
            "aikar_flags": bool(aikar_flags),
            "cpu_cores": int(cpu_cores or 2),
            "disk_limit_gb": float(disk_limit_gb or 10.0),
            "loader_version": loader_version,
            "modpack_id": meta.get("modpack_id"),
            "modpack_slug": meta.get("modpack_slug"),
            "modpack_name": pack_name,
            "modpack_version_id": meta.get("modpack_version_id") or manifest["version_id"],
            "modpack_version_name": meta.get("modpack_version_name") or manifest["version_id"],
            "modpack_type": meta.get("modpack_type") or "modpack",
            "modpack_source": meta.get("modpack_source") or "mrpack",
        }
        settings.save_runtime_config(base_cfg)

        resolved_file = await self._install_loader(
            downloader_obj=downloader_obj,
            loader_type=loader_type,
            mc_version=mc_version,
            loader_version=loader_version,
            java_bin=resolved_java or "java",
            stage_cb=cb,
        )
        settings.save_runtime_config({"server_file": resolved_file})

        total_mods = len(server_files)
        completed_mods = 0
        managed_records: List[Dict[str, Any]] = []
        if total_mods > 0:
            cb("downloading_mods", 45, f"Descargando mods (0/{total_mods})...")
            sem = asyncio.Semaphore(6)
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                async def _dl_entry(entry: Dict[str, Any]) -> None:
                    nonlocal completed_mods
                    dest = self._safe_target_path(settings.data_dir, entry["path"])
                    hashes = entry.get("hashes") or {}
                    urls = entry.get("downloads") or []
                    async with sem:
                        await self._download_verified_file(
                            client,
                            urls,
                            dest,
                            expected_sha512=hashes.get("sha512"),
                            expected_sha1=hashes.get("sha1"),
                        )
                        sha512_val = hashes.get("sha512") or self._compute_file_sha512(dest)
                        managed_records.append({
                            "path": entry["path"].replace("\\", "/"),
                            "sha512": sha512_val,
                            "origin": "modpack",
                        })
                        completed_mods += 1
                        pct = 45 + int((completed_mods / total_mods) * 40)
                        cb("downloading_mods", min(85, pct), f"Descargando mods ({completed_mods}/{total_mods})...")

                await asyncio.gather(*[_dl_entry(item) for item in server_files])

                rescued = await self._rescue_missing_mrpack_dependencies(
                    client, settings.data_dir, manifest.get("client_only_files") or []
                )
                for r_item in rescued:
                    managed_records.append({
                        "path": r_item["rel_path"],
                        "sha512": r_item["sha512"],
                        "origin": "modpack",
                    })
                    total_mods += 1
                    skipped_client = max(0, skipped_client - 1)

        await self.auto_heal_missing_server_dependencies(
            target_root=settings.data_dir, loader=loader_type, mc_version=mc_version
        )

        cb("extracting_overrides", 88, "Extrayendo configuraciones y overrides del servidor...")
        overrides_written = await asyncio.to_thread(self._extract_mrpack_overrides, mrpack_path, settings.data_dir)

        cb("installing", 96, "Aceptando EULA y configurando server.properties...")
        downloader_obj.accept_eula()
        downloader_obj.ensure_initial_config(sync_initial_defaults=True)
        settings.save_runtime_config({"server_file": resolved_file, "eula_accepted": True})

        self.write_manifest(
            settings.data_dir,
            {
                "install_mode": "modpack",
                "project_id": meta.get("modpack_id"),
                "slug": meta.get("modpack_slug"),
                "name": pack_name,
                "version_id": meta.get("modpack_version_id") or manifest["version_id"],
                "version_number": meta.get("modpack_version_name") or manifest["version_id"],
                "version_type": meta.get("modpack_version_type") or "release",
                "mc_version": mc_version,
                "loader_type": loader_type,
                "loader_version": loader_version,
                "managed_files": managed_records,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        activity_manager_obj.log(
            category="install",
            action="Modpack instalado",
            details=(
                f"{pack_name} ({loader_type.upper()} {mc_version} · {loader_version}). "
                f"Mods servidor: {total_mods}, omitidos cliente: {skipped_client}, overrides: {overrides_written}"
            ),
            user="admin",
            status="success",
        )
        cb("completed", 100, f"¡{pack_name} instalado ({total_mods} archivos)!")

        return {
            "status": "completed",
            "pack_name": pack_name,
            "mc_version": mc_version,
            "loader_type": loader_type,
            "loader_version": loader_version,
            "server_file": resolved_file,
            "java_path": resolved_java,
            "installed_files": total_mods,
            "skipped_client_files": skipped_client,
            "overrides_written": overrides_written,
        }

    async def install_modrinth_modpack(
        self,
        project_id: str,
        version_id: str,
        downloader_obj: Any,
        activity_manager_obj: Any,
        server_name: str = "Mi Servidor Dockraft",
        min_ram: str = "2G",
        max_ram: str = "4G",
        aikar_flags: bool = True,
        cpu_cores: int = 2,
        disk_limit_gb: float = 10.0,
        java_path: Optional[str] = None,
        force: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Downloads a Modrinth .mrpack modpack and executes full server provisioning."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("downloading_modpack", 2, "Consultando información del modpack en Modrinth...")

        details = await self.get_project_details(project_id)
        proj = details["project"]
        ver = next((v for v in details["versions"] if v["id"] == version_id), None)
        if not ver:
            raise ValueError(f"Versión '{version_id}' no encontrada para el modpack '{project_id}'")

        pfile = ver["primary_file"]
        dl_url = pfile.get("url")
        hashes = pfile.get("hashes") or {}
        if not dl_url:
            raise ValueError("El modpack no tiene URL de descarga .mrpack válida")

        if int(pfile.get("size") or 0) > MAX_MRPACK_BYTES:
            raise ValueError("El archivo .mrpack supera el tamaño máximo permitido (512 MB)")

        tmp_mrpack = settings.data_dir / f".modpack_{uuid.uuid4().hex[:8]}.mrpack"
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                def _mrpack_dl_progress(done: int, total: int) -> None:
                    pct = 3 + int((done / total) * 20) if total > 0 else 10
                    cb("downloading_modpack", min(23, pct), f"Descargando modpack ({min(100, int((done / total) * 100)) if total else 0}%)...")

                await self._download_verified_file(
                    client,
                    [dl_url],
                    tmp_mrpack,
                    expected_sha512=hashes.get("sha512"),
                    expected_sha1=hashes.get("sha1"),
                    progress_cb=_mrpack_dl_progress,
                )

            pack_meta = {
                "modpack_id": proj["project_id"],
                "modpack_slug": proj["slug"],
                "modpack_name": proj["title"],
                "modpack_version_id": ver["id"],
                "modpack_version_name": ver["name"] or ver["version_number"],
                "modpack_version_type": ver.get("version_type") or "release",
                "modpack_type": "modpack",
                "modpack_source": "modrinth",
            }
            return await self.install_from_mrpack(
                mrpack_path=tmp_mrpack,
                downloader_obj=downloader_obj,
                activity_manager_obj=activity_manager_obj,
                server_name=server_name or proj["title"],
                min_ram=min_ram,
                max_ram=max_ram,
                aikar_flags=aikar_flags,
                cpu_cores=cpu_cores,
                disk_limit_gb=disk_limit_gb,
                java_path=java_path,
                force=force,
                pack_meta=pack_meta,
                stage_cb=cb,
            )
        finally:
            try:
                tmp_mrpack.unlink(missing_ok=True)
            except OSError:
                pass

    async def install_modrinth_mod(
        self,
        project_id: str,
        version_id: str,
        downloader_obj: Any,
        activity_manager_obj: Any,
        preferred_loader: Optional[str] = None,
        preferred_mc_version: Optional[str] = None,
        server_name: str = "Mi Servidor Dockraft",
        min_ram: str = "2G",
        max_ram: str = "4G",
        aikar_flags: bool = True,
        cpu_cores: int = 2,
        disk_limit_gb: float = 10.0,
        java_path: Optional[str] = None,
        force: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Installs an individual Modrinth mod alongside its mod loader and all required dependencies."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("preparing", 5, "Resolviendo cargador y dependencias obligatorias...")

        reqs = await self.inspect_version_requirements(
            project_id,
            version_id,
            preferred_loader=preferred_loader,
            preferred_mc_version=preferred_mc_version,
        )
        mc_version = reqs["mc_version"]
        loader_type = reqs["loader"]
        proj_title = reqs["project_title"]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
            v_resp = await client.get(f"{MODRINTH_API_BASE}/version/{version_id}")
            v_resp.raise_for_status()
            ver_obj = dict(v_resp.json())
            ver_obj["project_title"] = proj_title
            mods_to_install = await self.resolve_mod_dependencies(
                ver_obj,
                loader=loader_type,
                mc_version=mc_version,
                client=client,
            )

        resolved_java = java_path if (java_path and java_path != "java") else await asyncio.to_thread(
            JavaManager.get_best_java_path, mc_version
        )
        if force:
            await asyncio.to_thread(self._clean_previous_modded_install, settings.data_dir)

        default_server_file = (
            ("run.bat" if os.name == "nt" else "run.sh")
            if loader_type in ("forge", "neoforge")
            else ("quilt-server-launch.jar" if loader_type == "quilt" else "server.jar")
        )
        settings.save_runtime_config({
            "server_type": loader_type,
            "server_version": mc_version,
            "server_file": default_server_file,
            "server_name": server_name or proj_title,
            "java_path": resolved_java or "java",
            "min_ram": min_ram or "2G",
            "max_ram": max_ram or "4G",
            "aikar_flags": bool(aikar_flags),
            "cpu_cores": int(cpu_cores or 2),
            "disk_limit_gb": float(disk_limit_gb or 10.0),
            "loader_version": None,
            "modpack_id": reqs["project_id"],
            "modpack_slug": project_id,
            "modpack_name": proj_title,
            "modpack_version_id": reqs["version_id"],
            "modpack_version_name": reqs["version_name"],
            "modpack_type": "mod",
            "modpack_source": "modrinth",
        })

        resolved_file = await self._install_loader(
            downloader_obj=downloader_obj,
            loader_type=loader_type,
            mc_version=mc_version,
            loader_version=None,
            java_bin=resolved_java or "java",
            stage_cb=cb,
        )
        settings.save_runtime_config({"server_file": resolved_file})

        total_mods = len(mods_to_install)
        completed = 0
        mods_dir = settings.data_dir / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        cb("downloading_mods", 45, f"Descargando mod y dependencias (0/{total_mods})...")

        sem = asyncio.Semaphore(6)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
            async def _dl_mod(item: Dict[str, Any]) -> None:
                nonlocal completed
                fname = Path(str(item.get("filename") or f"{item['version_id']}.jar")).name
                dest = self._safe_target_path(settings.data_dir, f"mods/{fname}")
                async with sem:
                    await self._download_verified_file(
                        client,
                        [item["url"]],
                        dest,
                        expected_sha512=item.get("sha512"),
                        expected_sha1=item.get("sha1"),
                    )
                    completed += 1
                    pct = 45 + int((completed / max(1, total_mods)) * 47)
                    cb("downloading_mods", min(92, pct), f"Descargando mod y dependencias ({completed}/{total_mods})...")

            await asyncio.gather(*[_dl_mod(m) for m in mods_to_install])

        cb("installing", 95, "Aceptando EULA y configurando server.properties...")
        downloader_obj.accept_eula()
        downloader_obj.ensure_initial_config(sync_initial_defaults=True)
        settings.save_runtime_config({"server_file": resolved_file, "eula_accepted": True})

        activity_manager_obj.log(
            category="install",
            action="Servidor con mods instalado",
            details=f"{proj_title} + {max(0, total_mods - 1)} dependencias ({loader_type.upper()} {mc_version})",
            user="admin",
            status="success",
        )
        cb("completed", 100, f"¡{proj_title} y {max(0, total_mods - 1)} dependencias instalados!")

        return {
            "status": "completed",
            "pack_name": proj_title,
            "mc_version": mc_version,
            "loader_type": loader_type,
            "loader_version": None,
            "server_file": resolved_file,
            "java_path": resolved_java,
            "installed_files": total_mods,
            "skipped_client_files": 0,
            "overrides_written": 0,
        }

    # --- Local Manifest & Strict Version Helpers ---

    @staticmethod
    def _compute_file_sha512(file_path: Path) -> str:
        """Computes lowercase SHA-512 hex digest using bounded 64KB chunks."""
        hasher = hashlib.sha512()
        with open(file_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest().lower()

    @staticmethod
    def read_manifest(data_dir: Path) -> Optional[Dict[str, Any]]:
        """Reads .dockraft_modpack_manifest.json safely if present and valid."""
        mpath = data_dir / MANIFEST_FILENAME
        if not mpath.is_file():
            return None
        try:
            data = json.loads(mpath.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception as exc:
            logger.warning("[Modpacks] Failed reading manifest: %s", exc)
            return None

    @staticmethod
    def write_manifest(data_dir: Path, payload: Dict[str, Any]) -> None:
        """Atomically persists .dockraft_modpack_manifest.json inside data_dir."""
        mpath = data_dir / MANIFEST_FILENAME
        atomic_write_json(mpath, payload, indent=2)

    @staticmethod
    def _select_compatible_version(
        versions: List[Dict[str, Any]],
        loader: str,
        mc_version: str,
        allow_beta: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Selects newest version matching loader + MC version, strictly requiring release unless allow_beta."""
        ldr = str(loader or "").lower().strip()
        mc = str(mc_version or "").strip()
        allowed_types = ("release", "beta") if allow_beta else ("release",)

        for ver in versions:
            v_loaders = [str(l).lower() for l in (ver.get("loaders") or [])]
            v_mcs = [str(g).strip() for g in (ver.get("game_versions") or [])]
            v_type = str(ver.get("version_type") or "release").lower()
            files = ver.get("files") or []
            if not files and ver.get("primary_file"):
                files = [ver["primary_file"]]
            if ldr in v_loaders and mc in v_mcs and files and v_type in allowed_types:
                return ver
        return None

    async def _batch_lookup_hashes(
        self, client: httpx.AsyncClient, hashes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Batch resolves Modrinth version objects by SHA-512 hash in chunks of 50."""
        out: Dict[str, Dict[str, Any]] = {}
        clean = [h.lower() for h in hashes if h]
        for i in range(0, len(clean), 50):
            batch = clean[i:i + 50]
            resp = await client.post(
                f"{MODRINTH_API_BASE}/version_files",
                json={"hashes": batch, "algorithm": "sha512"},
            )
            resp.raise_for_status()
            data = resp.json() or {}
            for k, v in data.items():
                out[str(k).lower()] = v
        return out

    async def _batch_lookup_projects(
        self, client: httpx.AsyncClient, project_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Batch resolves Modrinth project metadata objects in chunks of 50."""
        out: Dict[str, Dict[str, Any]] = {}
        unique = list(dict.fromkeys([pid for pid in project_ids if pid]))
        for i in range(0, len(unique), 50):
            batch = unique[i:i + 50]
            resp = await client.get(
                f"{MODRINTH_API_BASE}/projects",
                params={"ids": json.dumps(batch)},
            )
            resp.raise_for_status()
            for proj in (resp.json() or []):
                pid = proj.get("id")
                if pid:
                    out[pid] = proj
        return out

    async def _check_batch_updates_strict(
        self,
        client: httpx.AsyncClient,
        hashes: List[str],
        target_loader: str,
        target_mc: str,
        allow_beta: bool = False,
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Queries Modrinth /version_files/update and enforces release-only when allow_beta is False."""
        if not hashes or target_loader not in SUPPORTED_LOADERS or not target_mc:
            return {}

        updates: Dict[str, Optional[Dict[str, Any]]] = {}
        clean = list(dict.fromkeys([h.lower() for h in hashes if h]))

        for i in range(0, len(clean), 50):
            batch = clean[i:i + 50]
            resp = await client.post(
                f"{MODRINTH_API_BASE}/version_files/update",
                json={
                    "hashes": batch,
                    "algorithm": "sha512",
                    "loaders": [target_loader],
                    "game_versions": [target_mc],
                },
            )
            resp.raise_for_status()
            raw = resp.json() or {}
            for h_key, cand_ver in raw.items():
                hk = str(h_key).lower()
                if not isinstance(cand_ver, dict):
                    updates[hk] = None
                    continue

                v_type = str(cand_ver.get("version_type") or "release").lower()
                allowed = ("release", "beta") if allow_beta else ("release",)
                if v_type in allowed:
                    updates[hk] = cand_ver
                    continue

                # Modrinth /version_files/update returned a beta/alpha when strict stable is requested:
                # inspect /project/{pid}/version filtered cleanly for latest stable release.
                pid = cand_ver.get("project_id")
                if pid:
                    try:
                        p_vers_resp = await client.get(
                            f"{MODRINTH_API_BASE}/project/{pid}/version",
                            params={
                                "loaders": json.dumps([target_loader]),
                                "game_versions": json.dumps([target_mc]),
                            },
                        )
                        p_vers_resp.raise_for_status()
                        stable_match = self._select_compatible_version(
                            p_vers_resp.json() or [], target_loader, target_mc, allow_beta=allow_beta
                        )
                        updates[hk] = stable_match
                    except Exception:
                        updates[hk] = None
                else:
                    updates[hk] = None

        return updates

    @staticmethod
    def _collect_incompatible_pairs(
        version_map: Dict[str, Dict[str, Any]],
        title_map: Dict[str, str],
    ) -> List[Dict[str, str]]:
        """Detects any mutual `incompatible` dependencies among resolved project IDs."""
        conflicts: List[Dict[str, str]] = []
        seen_pairs: set = set()
        active_pids = set(version_map.keys())
        for pid, ver_obj in version_map.items():
            for dep in (ver_obj.get("dependencies") or []):
                if str(dep.get("dependency_type") or "").lower() != "incompatible":
                    continue
                target_pid = dep.get("project_id")
                if target_pid and target_pid in active_pids and target_pid != pid:
                    pair = tuple(sorted((pid, target_pid)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    conflicts.append({
                        "project_a": pid,
                        "mod_a": title_map.get(pid, pid),
                        "project_b": target_pid,
                        "mod_b": title_map.get(target_pid, target_pid),
                        "reason": f"{title_map.get(pid, pid)} es incompatible con {title_map.get(target_pid, target_pid)}",
                    })
        return conflicts

    # --- Multi-Mod Stack Builder ---

    async def resolve_mod_stack(
        self,
        project_ids: List[str],
        loader: str,
        mc_version: str,
        allow_beta: bool = False,
        max_mods: int = 40,
    ) -> Dict[str, Any]:
        """Resolves a multi-mod compatible stack, deduplicating required deps and checking conflicts."""
        ldr = str(loader or "").lower().strip()
        mc = str(mc_version or "").strip()
        if ldr not in SUPPORTED_LOADERS:
            raise ValueError(f"Cargador no soportado: {loader}")
        if not mc:
            raise ValueError("Debes indicar una versión de Minecraft válida")

        unique_pids = [str(p).strip() for p in dict.fromkeys(project_ids or []) if str(p).strip()][:max_mods]
        if not unique_pids:
            raise ValueError("Selecciona al menos un mod para resolver sus requerimientos")

        selected_mods: List[Dict[str, Any]] = []
        auto_deps_by_pid: Dict[str, Dict[str, Any]] = {}
        missing: List[Dict[str, Any]] = []
        resolved_ver_by_pid: Dict[str, Dict[str, Any]] = {}
        title_by_pid: Dict[str, str] = {}
        selected_pid_set: set = set()

        async with httpx.AsyncClient(timeout=20.0, headers=MODRINTH_HEADERS) as client:
            proj_meta_map = await self._batch_lookup_projects(client, unique_pids)

            for req_pid in unique_pids:
                proj = proj_meta_map.get(req_pid)
                if not proj:
                    try:
                        p_resp = await client.get(f"{MODRINTH_API_BASE}/project/{req_pid}")
                        p_resp.raise_for_status()
                        proj = p_resp.json()
                    except Exception:
                        missing.append({"project_id": req_pid, "title": req_pid, "reason": "Proyecto no encontrado en Modrinth"})
                        continue

                canonical_pid = proj.get("id") or req_pid
                title = proj.get("title") or proj.get("slug") or canonical_pid
                title_by_pid[canonical_pid] = title
                if str(proj.get("server_side", "")).lower() == "unsupported":
                    missing.append({
                        "project_id": canonical_pid,
                        "title": title,
                        "reason": "Mod exclusivo de cliente (unsupported en servidor)",
                    })
                    continue

                v_resp = await client.get(
                    f"{MODRINTH_API_BASE}/project/{canonical_pid}/version",
                    params={"loaders": json.dumps([ldr]), "game_versions": json.dumps([mc])},
                )
                v_resp.raise_for_status()
                vers_raw = v_resp.json() or []

                chosen = self._select_compatible_version(vers_raw, ldr, mc, allow_beta=allow_beta)
                if not chosen:
                    beta_exists = (not allow_beta) and bool(
                        self._select_compatible_version(vers_raw, ldr, mc, allow_beta=True)
                    )
                    reason = (
                        f"Solo tiene compilaciones Beta para {ldr.upper()} {mc}; activa 'Incluir betas' si deseas probarla"
                        if beta_exists
                        else f"Sin versión disponible para {ldr.upper()} {mc}"
                    )
                    missing.append({"project_id": canonical_pid, "title": title, "reason": reason, "beta_only": beta_exists})
                    continue

                chosen_with_title = dict(chosen)
                chosen_with_title["project_id"] = canonical_pid
                chosen_with_title["project_title"] = title
                selected_pid_set.add(canonical_pid)
                resolved_ver_by_pid[canonical_pid] = chosen_with_title

                stack_items = await self.resolve_mod_dependencies(
                    chosen_with_title,
                    loader=ldr,
                    mc_version=mc,
                    client=client,
                    allow_beta=allow_beta,
                )
                for item in stack_items:
                    ipid = item.get("project_id")
                    if item.get("is_root"):
                        selected_mods.append({
                            **item,
                            "version_type": str(chosen.get("version_type") or "release").lower(),
                        })
                    elif ipid and ipid not in selected_pid_set and ipid not in auto_deps_by_pid:
                        auto_deps_by_pid[ipid] = item
                        title_by_pid[ipid] = item.get("project_title") or ipid
                        if item.get("version_id") and ipid not in resolved_ver_by_pid:
                            try:
                                dv_resp = await client.get(f"{MODRINTH_API_BASE}/version/{item['version_id']}")
                                if dv_resp.status_code == 200:
                                    resolved_ver_by_pid[ipid] = dv_resp.json()
                            except Exception:
                                pass

        auto_dependencies = [d for d in auto_deps_by_pid.values() if d.get("project_id") not in selected_pid_set]
        conflicts = self._collect_incompatible_pairs(resolved_ver_by_pid, title_by_pid)
        all_files = list(selected_mods) + list(auto_dependencies)
        total_size_bytes = sum(int(f.get("size") or 0) for f in all_files)
        recommended_ram = self._estimate_recommended_ram(
            loader=ldr,
            project_type="mod",
            mod_count=len(all_files),
            total_mod_bytes=total_size_bytes,
        )

        return {
            "loader": ldr,
            "mc_version": mc,
            "allow_beta": bool(allow_beta),
            "recommended_java": JavaManager.get_recommended_java(mc),
            "recommended_ram": recommended_ram,
            "selected_mods": selected_mods,
            "auto_dependencies": auto_dependencies,
            "all_files": all_files,
            "missing": missing,
            "conflicts": conflicts,
            "can_install": bool(selected_mods and not missing and not conflicts),
            "total_files": len(all_files),
            "total_size_bytes": total_size_bytes,
        }

    async def install_mod_stack(
        self,
        project_ids: List[str],
        loader: str,
        mc_version: str,
        downloader_obj: Any,
        activity_manager_obj: Any,
        server_name: str = "Mi Servidor Dockraft",
        min_ram: str = "2G",
        max_ram: str = "4G",
        aikar_flags: bool = True,
        cpu_cores: int = 2,
        disk_limit_gb: float = 10.0,
        java_path: Optional[str] = None,
        allow_beta: bool = False,
        force: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Installs a custom stack of compatible mods and deduplicated dependencies cleanly."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("preparing", 5, "Verificando compatibilidad y resolviendo dependencias del stack...")

        plan = await self.resolve_mod_stack(
            project_ids=project_ids,
            loader=loader,
            mc_version=mc_version,
            allow_beta=allow_beta,
        )
        if plan["conflicts"]:
            raise ModConflictError("; ".join(c["reason"] for c in plan["conflicts"]))
        if plan["missing"]:
            raise ValueError("; ".join(f"{m['title']}: {m['reason']}" for m in plan["missing"]))
        if not plan["all_files"]:
            raise ValueError("No se encontraron archivos compatibles para instalar")

        loader_type = plan["loader"]
        mc_ver = plan["mc_version"]
        all_files = plan["all_files"]
        resolved_java = java_path if (java_path and java_path != "java") else await asyncio.to_thread(
            JavaManager.get_best_java_path, mc_ver
        )

        # Stage and SHA-512 verify all mods in a temporary folder before modifying live files
        stage_dir = settings.data_dir / f".modstack_stage_{uuid.uuid4().hex[:8]}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        total_mods = len(all_files)
        completed = 0
        staged_records: List[Dict[str, Any]] = []

        try:
            cb("downloading_mods", 15, f"Descargando y verificando mods (0/{total_mods})...")
            sem = asyncio.Semaphore(6)
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                async def _dl_mod(item: Dict[str, Any]) -> None:
                    nonlocal completed
                    fname = Path(str(item.get("filename") or f"{item['version_id']}.jar")).name
                    dest = stage_dir / fname
                    async with sem:
                        await self._download_verified_file(
                            client,
                            [item["url"]],
                            dest,
                            expected_sha512=item.get("sha512"),
                            expected_sha1=item.get("sha1"),
                        )
                        sha512_val = item.get("sha512") or self._compute_file_sha512(dest)
                        staged_records.append({
                            "staged_path": dest,
                            "filename": fname,
                            "sha512": sha512_val,
                            "project_id": item.get("project_id"),
                            "version_id": item.get("version_id"),
                        })
                        completed += 1
                        pct = 15 + int((completed / max(1, total_mods)) * 45)
                        cb("downloading_mods", min(60, pct), f"Descargando y verificando mods ({completed}/{total_mods})...")

                await asyncio.gather(*[_dl_mod(m) for m in all_files])

            if force:
                await asyncio.to_thread(self._clean_previous_modded_install, settings.data_dir)

            default_server_file = (
                ("run.bat" if os.name == "nt" else "run.sh")
                if loader_type in ("forge", "neoforge")
                else ("quilt-server-launch.jar" if loader_type == "quilt" else "server.jar")
            )
            stack_names = [m.get("project_title") or m["filename"] for m in plan["selected_mods"][:3]]
            display_name = server_name or (" + ".join(stack_names))

            settings.save_runtime_config({
                "server_type": loader_type,
                "server_version": mc_ver,
                "server_file": default_server_file,
                "server_name": display_name,
                "java_path": resolved_java or "java",
                "min_ram": min_ram or "2G",
                "max_ram": max_ram or "4G",
                "aikar_flags": bool(aikar_flags),
                "cpu_cores": int(cpu_cores or 2),
                "disk_limit_gb": float(disk_limit_gb or 10.0),
                "loader_version": None,
                "modpack_id": None,
                "modpack_slug": None,
                "modpack_name": display_name,
                "modpack_version_id": None,
                "modpack_version_name": f"{total_mods} mods ({loader_type.upper()})",
                "modpack_type": "custom_mods",
                "modpack_source": "modrinth",
            })

            resolved_file = await self._install_loader(
                downloader_obj=downloader_obj,
                loader_type=loader_type,
                mc_version=mc_ver,
                loader_version=None,
                java_bin=resolved_java or "java",
                stage_cb=cb,
            )

            mods_dir = settings.data_dir / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)
            manifest_entries: List[Dict[str, Any]] = []
            for rec in staged_records:
                target_jar = self._safe_target_path(settings.data_dir, f"mods/{rec['filename']}")
                rec["staged_path"].replace(target_jar)
                manifest_entries.append({
                    "path": f"mods/{rec['filename']}",
                    "sha512": rec["sha512"],
                    "origin": "manual",
                    "project_id": rec.get("project_id"),
                    "version_id": rec.get("version_id"),
                })

            cb("installing", 95, "Aceptando EULA y configurando server.properties...")
            downloader_obj.accept_eula()
            downloader_obj.ensure_initial_config(sync_initial_defaults=True)
            settings.save_runtime_config({"server_file": resolved_file, "eula_accepted": True})

            self.write_manifest(
                settings.data_dir,
                {
                    "install_mode": "custom_mods",
                    "project_id": None,
                    "slug": None,
                    "name": display_name,
                    "version_id": None,
                    "version_number": None,
                    "version_type": "release",
                    "mc_version": mc_ver,
                    "loader_type": loader_type,
                    "loader_version": None,
                    "managed_files": manifest_entries,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            activity_manager_obj.log(
                category="install",
                action="Servidor con mods instalado",
                details=f"{display_name}: {len(plan['selected_mods'])} mods + {len(plan['auto_dependencies'])} dependencias ({loader_type.upper()} {mc_ver})",
                user="admin",
                status="success",
            )
            cb("completed", 100, f"¡Servidor instalado con {total_mods} archivos ({loader_type.upper()} {mc_ver})!")

            return {
                "status": "completed",
                "pack_name": display_name,
                "mc_version": mc_ver,
                "loader_type": loader_type,
                "server_file": resolved_file,
                "java_path": resolved_java,
                "installed_files": total_mods,
                "selected_mods": len(plan["selected_mods"]),
                "auto_dependencies": len(plan["auto_dependencies"]),
            }
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    # --- Modpack Updater (Prism / CurseForge Style) ---

    async def get_modpack_update_status(self, allow_beta: bool = False) -> Dict[str, Any]:
        """Checks Modrinth for available stable (or beta) updates for the installed modpack."""
        cfg = settings.runtime_config
        manifest = self.read_manifest(settings.data_dir) or {}

        project_id = cfg.get("modpack_id") or manifest.get("project_id")
        modpack_type = cfg.get("modpack_type") or manifest.get("install_mode")
        modpack_source = cfg.get("modpack_source") or "modrinth"
        if not project_id or modpack_type != "modpack" or modpack_source != "modrinth":
            return {"has_modpack": False}

        current_ver_id = cfg.get("modpack_version_id") or manifest.get("version_id") or ""
        current_ver_name = cfg.get("modpack_version_name") or manifest.get("version_number") or current_ver_id
        current_mc = cfg.get("server_version") or manifest.get("mc_version") or ""
        current_loader = cfg.get("server_type") or manifest.get("loader_type") or ""

        # Force fresh fetch (do not rely on stale 60s cache if checking explicitly)
        self._project_cache.pop(str(project_id), None)
        details = await self.get_project_details(str(project_id))
        proj = details["project"]
        all_vers = details["versions"]

        allowed_types = ("release", "beta") if allow_beta else ("release",)
        filtered_versions: List[Dict[str, Any]] = []
        for v in all_vers:
            v_type = str(v.get("version_type") or "release").lower()
            is_curr = v.get("id") == current_ver_id
            if v_type not in allowed_types and not is_curr:
                continue
            pfile = v.get("primary_file") or {}
            fname = str(pfile.get("filename") or "")
            if not fname.lower().endswith(".mrpack"):
                continue

            gvs = v.get("game_versions") or []
            target_mc = self._pick_preferred_mc_version(gvs, preferred=current_mc)
            ldrs = v.get("loaders") or []
            target_ldr = current_loader if current_loader in ldrs else (ldrs[0] if ldrs else current_loader)
            filtered_versions.append({
                "id": v.get("id"),
                "name": v.get("name") or v.get("version_number"),
                "version_number": v.get("version_number"),
                "version_type": v_type,
                "date_published": v.get("date_published"),
                "target_mc_version": target_mc,
                "target_loader": target_ldr,
                "changes_mc_version": bool(current_mc and target_mc and target_mc != current_mc),
                "is_current": is_curr,
                "size": int(pfile.get("size") or 0),
                "changelog": v.get("changelog") or "",
            })

        stable_candidates = [v for v in filtered_versions if v["version_type"] in allowed_types]
        latest = stable_candidates[0] if stable_candidates else None
        update_available = bool(latest and latest["id"] != current_ver_id)

        return {
            "has_modpack": True,
            "project_id": proj.get("project_id") or project_id,
            "slug": proj.get("slug") or cfg.get("modpack_slug"),
            "name": proj.get("title") or cfg.get("modpack_name") or manifest.get("name"),
            "icon_url": proj.get("icon_url") or "",
            "url": proj.get("url") or "",
            "current_version_id": current_ver_id,
            "current_version_name": current_ver_name,
            "current_mc_version": current_mc,
            "current_loader": current_loader,
            "allow_beta": bool(allow_beta),
            "update_available": update_available,
            "latest_version": latest,
            "versions": filtered_versions[:30],
        }

    async def stage_modpack_update(
        self,
        project_id: str,
        target_version_id: str,
        allow_beta: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Downloads and SHA-512 verifies all new modpack files into a staging directory before touching live data."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("downloading_modpack", 5, "Verificando versión de actualización en Modrinth...")

        details = await self.get_project_details(project_id)
        proj = details["project"]
        ver = next((v for v in details["versions"] if v["id"] == target_version_id), None)
        if not ver:
            raise ValueError(f"Versión '{target_version_id}' no encontrada en Modrinth")

        v_type = str(ver.get("version_type") or "release").lower()
        allowed = ("release", "beta") if allow_beta else ("release",)
        if v_type not in allowed:
            raise ValueError(
                f"La versión seleccionada es de tipo '{v_type}'. Activa 'Incluir betas' explícitamente si deseas instalarla."
            )

        pfile = ver.get("primary_file") or {}
        dl_url = pfile.get("url")
        hashes = pfile.get("hashes") or {}
        if not dl_url or int(pfile.get("size") or 0) > MAX_MRPACK_BYTES:
            raise ValueError("URL o tamaño .mrpack inválido")

        tmp_mrpack = settings.data_dir / f".modpack_upd_{uuid.uuid4().hex[:8]}.mrpack"
        stage_dir = settings.data_dir / f".modpack_stage_{uuid.uuid4().hex[:8]}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                def _mr_prog(done: int, total: int) -> None:
                    pct = 5 + int((done / total) * 20) if total > 0 else 10
                    cb("downloading_modpack", min(25, pct), f"Descargando modpack actualizado ({int((done / total) * 100) if total else 0}%)...")

                await self._download_verified_file(
                    client,
                    [dl_url],
                    tmp_mrpack,
                    expected_sha512=hashes.get("sha512"),
                    expected_sha1=hashes.get("sha1"),
                    progress_cb=_mr_prog,
                )

                manifest = await asyncio.to_thread(self.parse_mrpack_manifest, tmp_mrpack)
                server_files = manifest["server_files"]
                total = len(server_files)
                completed = 0
                staged_files: List[Dict[str, Any]] = []

                if total > 0:
                    cb("downloading_mods", 28, f"Pre-descargando y verificando mods ({completed}/{total})...")
                    sem = asyncio.Semaphore(6)

                    async def _dl_staged(entry: Dict[str, Any]) -> None:
                        nonlocal completed
                        rel = str(entry["path"]).replace("\\", "/")
                        self._safe_target_path(settings.data_dir, rel)
                        staged_dest = self._safe_target_path(stage_dir, rel)
                        ehashes = entry.get("hashes") or {}
                        async with sem:
                            await self._download_verified_file(
                                client,
                                entry.get("downloads") or [],
                                staged_dest,
                                expected_sha512=ehashes.get("sha512"),
                                expected_sha1=ehashes.get("sha1"),
                            )
                            sha512_val = ehashes.get("sha512") or self._compute_file_sha512(staged_dest)
                            staged_files.append({
                                "rel_path": rel,
                                "staged_path": staged_dest,
                                "sha512": sha512_val,
                            })
                            completed += 1
                            pct = 28 + int((completed / total) * 32)
                            cb("downloading_mods", min(60, pct), f"Pre-descargando y verificando mods ({completed}/{total})...")

                    await asyncio.gather(*[_dl_staged(e) for e in server_files])

                    rescued_staged = await self._rescue_missing_mrpack_dependencies(
                        client, stage_dir, manifest.get("client_only_files") or []
                    )
                    for r_item in rescued_staged:
                        staged_files.append({
                            "rel_path": r_item["rel_path"],
                            "staged_path": r_item["dest_path"],
                            "sha512": r_item["sha512"],
                        })
                        manifest["skipped_client_files"] = max(0, int(manifest.get("skipped_client_files") or 0) - 1)

            return {
                "mrpack_path": tmp_mrpack,
                "stage_dir": stage_dir,
                "manifest": manifest,
                "staged_files": staged_files,
                "version_meta": ver,
                "project_meta": proj,
            }
        except Exception:
            tmp_mrpack.unlink(missing_ok=True)
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

    async def apply_staged_modpack_update(
        self,
        staged: Dict[str, Any],
        downloader_obj: Any,
        activity_manager_obj: Any,
        update_custom_mods: bool = True,
        allow_beta: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Applies a pre-verified staged modpack update after server stop & backup."""
        cb = stage_cb or (lambda s, p, d=None: None)
        mrpack_path: Path = staged["mrpack_path"]
        stage_dir: Path = staged["stage_dir"]
        manifest: Dict[str, Any] = staged["manifest"]
        staged_files: List[Dict[str, Any]] = staged["staged_files"]
        ver = staged["version_meta"]
        proj = staged["project_meta"]

        try:
            old_cfg = settings.runtime_config
            old_manifest = self.read_manifest(settings.data_dir) or {}
            old_mc = str(old_cfg.get("server_version") or old_manifest.get("mc_version") or "")
            old_loader = str(old_cfg.get("server_type") or old_manifest.get("loader_type") or "")
            old_loader_ver = str(old_cfg.get("loader_version") or old_manifest.get("loader_version") or "")

            target_mc = manifest["mc_version"]
            target_loader = manifest["loader_type"]
            target_loader_ver = manifest["loader_version"]

            old_managed = {
                str(m.get("path", "")).replace("\\", "/")
                for m in (old_manifest.get("managed_files") or [])
                if m.get("origin", "modpack") == "modpack"
            }
            new_managed_paths = {sf["rel_path"] for sf in staged_files}

            # 1. Detect custom user-added mods in mods/ prior to swap
            mods_dir = settings.data_dir / "mods"
            custom_jars: List[Dict[str, str]] = []
            if mods_dir.is_dir():
                for item in mods_dir.iterdir():
                    if not item.is_file() or not item.name.lower().endswith(".jar"):
                        continue
                    rel_mod = f"mods/{item.name}"
                    if rel_mod not in old_managed and rel_mod not in new_managed_paths:
                        custom_jars.append({
                            "path": rel_mod,
                            "filename": item.name,
                            "sha512": self._compute_file_sha512(item),
                        })

            # 2. Recompute Java runtime and upgrade loader if MC/loader version changed
            resolved_java = old_cfg.get("java_path") or "java"
            if target_mc != old_mc or resolved_java == "java":
                resolved_java = await asyncio.to_thread(JavaManager.get_best_java_path, target_mc)

            resolved_file = old_cfg.get("server_file") or "server.jar"
            if target_loader != old_loader or target_mc != old_mc or target_loader_ver != old_loader_ver:
                resolved_file = await self._install_loader(
                    downloader_obj=downloader_obj,
                    loader_type=target_loader,
                    mc_version=target_mc,
                    loader_version=target_loader_ver,
                    java_bin=resolved_java or "java",
                    stage_cb=cb,
                )

            # 3. Remove obsolete managed modpack files cleanly (preserving worlds, configs & custom mods)
            cb("updating", 72, "Limpiando mods obsoletos de la versión anterior...")
            for rel_old in old_managed:
                if rel_old not in new_managed_paths:
                    try:
                        old_p = self._safe_target_path(settings.data_dir, rel_old)
                        if old_p.is_file():
                            old_p.unlink()
                    except Exception:
                        pass

            # 4. Move verified staged files into data_dir
            cb("updating", 78, f"Instalando {len(staged_files)} archivos nuevos del modpack...")
            managed_records: List[Dict[str, Any]] = []
            for sf in staged_files:
                dest = self._safe_target_path(settings.data_dir, sf["rel_path"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                sf["staged_path"].replace(dest)
                managed_records.append({
                    "path": sf["rel_path"],
                    "sha512": sf["sha512"],
                    "origin": "modpack",
                })

            # 5. Extract server/config overrides while preserving user server.properties/whitelist/ops
            cb("extracting_overrides", 85, "Actualizando configuraciones del modpack (conservando server.properties)...")
            await asyncio.to_thread(
                self._extract_mrpack_overrides,
                mrpack_path,
                settings.data_dir,
                True,
            )

            # 6. Check/migrate custom user-added mods if MC version or loader changed
            disabled_custom: List[str] = []
            updated_custom: List[str] = []
            if custom_jars and (target_mc != old_mc or target_loader != old_loader):
                cb("updating", 90, f"Verificando compatibilidad de {len(custom_jars)} mods personalizados...")
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                    hash_map = await self._check_batch_updates_strict(
                        client,
                        [c["sha512"] for c in custom_jars],
                        target_loader=target_loader,
                        target_mc=target_mc,
                        allow_beta=allow_beta,
                    )
                    for cj in custom_jars:
                        cpath = settings.data_dir / "mods" / cj["filename"]
                        if not cpath.exists():
                            continue
                        cand = hash_map.get(cj["sha512"])
                        if cand and update_custom_mods:
                            files = cand.get("files") or []
                            pfile = next((f for f in files if f.get("primary")), files[0] if files else None)
                            if pfile and pfile.get("url"):
                                new_fname = Path(pfile["filename"]).name
                                new_dest = self._safe_target_path(settings.data_dir, f"mods/{new_fname}")
                                hashes = pfile.get("hashes") or {}
                                await self._download_verified_file(
                                    client,
                                    [pfile["url"]],
                                    new_dest,
                                    expected_sha512=hashes.get("sha512"),
                                    expected_sha1=hashes.get("sha1"),
                                )
                                if new_dest != cpath and cpath.exists():
                                    cpath.unlink()
                                updated_custom.append(new_fname)
                                managed_records.append({
                                    "path": f"mods/{new_fname}",
                                    "sha512": hashes.get("sha512") or self._compute_file_sha512(new_dest),
                                    "origin": "manual",
                                })
                                continue
                        # Incompatible or non-updatable custom mod on new MC/loader -> disable safely
                        disabled_path = cpath.with_name(f"{cpath.name}.disabled")
                        cpath.replace(disabled_path)
                        disabled_custom.append(cj["filename"])
            else:
                # Keep custom jars recorded cleanly in manifest
                for cj in custom_jars:
                    managed_records.append({
                        "path": cj["path"],
                        "sha512": cj["sha512"],
                        "origin": "manual",
                    })

            # Preserve previously manually-tracked mods that remained intact
            new_paths_check = {r["path"] for r in managed_records}
            for old_entry in (old_manifest.get("managed_files") or []):
                op = str(old_entry.get("path") or "")
                if old_entry.get("origin") == "manual" and op not in new_paths_check:
                    if (settings.data_dir / op).exists():
                        managed_records.append(old_entry)

            downloader_obj.ensure_initial_config(sync_initial_defaults=False)

            ver_name = ver.get("name") or ver.get("version_number") or manifest["version_id"]
            settings.save_runtime_config({
                "server_type": target_loader,
                "server_version": target_mc,
                "server_file": resolved_file,
                "loader_version": target_loader_ver,
                "java_path": resolved_java or "java",
                "modpack_id": proj.get("project_id") or old_cfg.get("modpack_id"),
                "modpack_slug": proj.get("slug") or old_cfg.get("modpack_slug"),
                "modpack_name": proj.get("title") or manifest["name"],
                "modpack_version_id": ver.get("id"),
                "modpack_version_name": ver_name,
                "modpack_version_type": ver.get("version_type") or "release",
            })

            self.write_manifest(
                settings.data_dir,
                {
                    "install_mode": "modpack",
                    "project_id": proj.get("project_id") or old_cfg.get("modpack_id"),
                    "slug": proj.get("slug") or old_cfg.get("modpack_slug"),
                    "name": proj.get("title") or manifest["name"],
                    "version_id": ver.get("id"),
                    "version_number": ver_name,
                    "version_type": ver.get("version_type") or "release",
                    "mc_version": target_mc,
                    "loader_type": target_loader,
                    "loader_version": target_loader_ver,
                    "managed_files": managed_records,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            activity_manager_obj.log(
                category="update",
                action="Modpack actualizado",
                details=f"{proj.get('title') or manifest['name']} → {ver_name} ({target_loader.upper()} {target_mc}). Mods custom actualizados: {len(updated_custom)}, desactivados: {len(disabled_custom)}",
                user="admin",
                status="success",
            )

            return {
                "status": "completed",
                "pack_name": proj.get("title") or manifest["name"],
                "version_id": ver.get("id"),
                "version_name": ver_name,
                "mc_version": target_mc,
                "loader_type": target_loader,
                "loader_version": target_loader_ver,
                "installed_files": len(staged_files),
                "skipped_client_files": manifest["skipped_client_files"],
                "updated_custom_mods": updated_custom,
                "disabled_incompatible_mods": disabled_custom,
            }
        finally:
            try:
                mrpack_path.unlink(missing_ok=True)
            except OSError:
                pass
            shutil.rmtree(stage_dir, ignore_errors=True)

    # --- Installed Mods Manager & Compatibility Checks ---

    def _scan_installed_mods_sync(self, data_dir: Path) -> List[Dict[str, Any]]:
        """Scans mods/ directory synchronously for .jar and .jar.disabled files and computes SHA-512."""
        mods_dir = data_dir / "mods"
        if not mods_dir.is_dir():
            return []

        items: List[Dict[str, Any]] = []
        for entry in sorted(mods_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file():
                continue
            nl = entry.name.lower()
            if nl.endswith(".jar"):
                enabled = True
            elif nl.endswith(".jar.disabled"):
                enabled = False
            else:
                continue
            stat_info = entry.stat()
            items.append({
                "filename": entry.name,
                "enabled": enabled,
                "size": stat_info.st_size,
                "mtime": stat_info.st_mtime,
                "sha512": self._compute_file_sha512(entry),
            })
        return items

    async def list_installed_mods(
        self, check_updates: bool = True, allow_beta: bool = False
    ) -> Dict[str, Any]:
        """Lists installed mods in mods/, enriches via Modrinth SHA-512 hash lookup, and checks stable updates."""
        cfg = settings.runtime_config
        server_type = str(cfg.get("server_type") or "").lower()
        server_version = str(cfg.get("server_version") or "")
        manifest = self.read_manifest(settings.data_dir) or {}
        manifest_origins: Dict[str, str] = {}
        for m in (manifest.get("managed_files") or []):
            mpath = str(m.get("path") or "").replace("\\", "/")
            if mpath.startswith("mods/"):
                manifest_origins[Path(mpath).name.lower()] = str(m.get("origin") or "modpack")

        scanned = await asyncio.to_thread(self._scan_installed_mods_sync, settings.data_dir)
        if not scanned:
            return {
                "server_type": server_type,
                "server_version": server_version,
                "modpack_name": cfg.get("modpack_name"),
                "allow_beta": bool(allow_beta),
                "mods": [],
                "updates_available_count": 0,
                "unrecognized_count": 0,
                "conflicts": [],
            }

        hashes = [m["sha512"] for m in scanned]
        hash_to_ver: Dict[str, Dict[str, Any]] = {}
        proj_map: Dict[str, Dict[str, Any]] = {}
        hash_to_update: Dict[str, Optional[Dict[str, Any]]] = {}

        async with httpx.AsyncClient(timeout=20.0, headers=MODRINTH_HEADERS) as client:
            try:
                hash_to_ver = await self._batch_lookup_hashes(client, hashes)
                pids = [v.get("project_id") for v in hash_to_ver.values() if v.get("project_id")]
                if pids:
                    proj_map = await self._batch_lookup_projects(client, pids)

                if check_updates and server_type in SUPPORTED_LOADERS and server_version:
                    active_hashes = [m["sha512"] for m in scanned if m["enabled"] and m["sha512"] in hash_to_ver]
                    if active_hashes:
                        hash_to_update = await self._check_batch_updates_strict(
                            client,
                            active_hashes,
                            target_loader=server_type,
                            target_mc=server_version,
                            allow_beta=allow_beta,
                        )
            except Exception as exc:
                logger.warning("[Mods] Modrinth metadata/update lookup error: %s", exc)

        mods_out: List[Dict[str, Any]] = []
        active_ver_map: Dict[str, Dict[str, Any]] = {}
        active_title_map: Dict[str, str] = {}
        updates_count = 0
        unrecognized = 0

        for item in scanned:
            sha = item["sha512"]
            base_name = item["filename"][:-9] if item["filename"].lower().endswith(".disabled") else item["filename"]
            origin = manifest_origins.get(base_name.lower(), "manual")
            ver_obj = hash_to_ver.get(sha)

            rec: Dict[str, Any] = {
                "filename": item["filename"],
                "enabled": item["enabled"],
                "size": item["size"],
                "sha512": sha,
                "origin": origin,
                "recognized": bool(ver_obj),
                "project_id": None,
                "slug": None,
                "title": base_name.rsplit(".", 1)[0],
                "icon_url": "",
                "url": "",
                "version_id": None,
                "version_number": None,
                "version_type": "release",
                "update_available": False,
                "latest_version_id": None,
                "latest_version_number": None,
                "latest_version_type": None,
                "latest_filename": None,
                "latest_url": None,
                "latest_sha512": None,
                "latest_sha1": None,
                "latest_size": 0,
                "latest_dependencies": [],
            }

            if ver_obj:
                pid = ver_obj.get("project_id")
                proj = proj_map.get(pid, {})
                title = proj.get("title") or proj.get("slug") or rec["title"]
                slug = proj.get("slug") or pid
                rec.update({
                    "project_id": pid,
                    "slug": slug,
                    "title": title,
                    "icon_url": proj.get("icon_url") or "",
                    "url": f"https://modrinth.com/mod/{slug}" if slug else "",
                    "version_id": ver_obj.get("id"),
                    "version_number": ver_obj.get("version_number") or ver_obj.get("name"),
                    "version_type": str(ver_obj.get("version_type") or "release").lower(),
                })
                if item["enabled"] and pid:
                    active_ver_map[pid] = ver_obj
                    active_title_map[pid] = title

                upd = hash_to_update.get(sha)
                if item["enabled"] and upd and upd.get("id") and upd.get("id") != ver_obj.get("id"):
                    ufiles = upd.get("files") or []
                    pfile = next((f for f in ufiles if f.get("primary")), ufiles[0] if ufiles else None)
                    if pfile and pfile.get("url"):
                        uhashes = pfile.get("hashes") or {}
                        upd_sha512 = str(uhashes.get("sha512") or "").lower()
                        if upd_sha512 != sha:
                            updates_count += 1
                            rec.update({
                                "update_available": True,
                                "latest_version_id": upd.get("id"),
                                "latest_version_number": upd.get("version_number") or upd.get("name"),
                                "latest_version_type": str(upd.get("version_type") or "release").lower(),
                                "latest_filename": pfile.get("filename"),
                                "latest_url": pfile.get("url"),
                                "latest_sha512": upd_sha512 or None,
                                "latest_sha1": uhashes.get("sha1"),
                                "latest_size": int(pfile.get("size") or 0),
                                "latest_dependencies": upd.get("dependencies") or [],
                            })
            else:
                unrecognized += 1

            mods_out.append(rec)

        conflicts = self._collect_incompatible_pairs(active_ver_map, active_title_map)
        return {
            "server_type": server_type,
            "server_version": server_version,
            "modpack_name": cfg.get("modpack_name"),
            "allow_beta": bool(allow_beta),
            "mods": mods_out,
            "updates_available_count": updates_count,
            "unrecognized_count": unrecognized,
            "conflicts": conflicts,
        }

    async def add_mod_to_installed_server(
        self,
        project_id: str,
        version_id: Optional[str] = None,
        allow_beta: bool = False,
        activity_manager_obj: Any = None,
    ) -> Dict[str, Any]:
        """Adds a compatible mod + missing required dependencies to the existing modded server."""
        cfg = settings.runtime_config
        server_type = str(cfg.get("server_type") or "").lower()
        server_version = str(cfg.get("server_version") or "")
        if server_type not in SUPPORTED_LOADERS or not server_version:
            raise ValueError("El servidor actual no utiliza un cargador de mods compatible o no tiene versión detectada")

        current_info = await self.list_installed_mods(check_updates=False, allow_beta=allow_beta)
        enabled_pids = {m["project_id"] for m in current_info["mods"] if m["enabled"] and m.get("project_id")}
        title_map = {m["project_id"]: m["title"] for m in current_info["mods"] if m.get("project_id")}

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
            p_resp = await client.get(f"{MODRINTH_API_BASE}/project/{project_id}")
            p_resp.raise_for_status()
            proj = p_resp.json()
            canon_pid = proj.get("id") or project_id
            proj_title = proj.get("title") or proj.get("slug") or canon_pid
            title_map[canon_pid] = proj_title

            if str(proj.get("server_side", "")).lower() == "unsupported":
                raise ValueError(f"El mod '{proj_title}' es exclusivo de cliente (unsupported en servidor)")

            if version_id:
                v_resp = await client.get(f"{MODRINTH_API_BASE}/version/{version_id}")
                v_resp.raise_for_status()
                chosen = v_resp.json()
                v_type = str(chosen.get("version_type") or "release").lower()
                if v_type not in (("release", "beta") if allow_beta else ("release",)):
                    raise ValueError(f"La versión seleccionada es '{v_type}'; activa 'Incluir betas' para instalarla")
            else:
                v_resp = await client.get(
                    f"{MODRINTH_API_BASE}/project/{canon_pid}/version",
                    params={"loaders": json.dumps([server_type]), "game_versions": json.dumps([server_version])},
                )
                v_resp.raise_for_status()
                chosen = self._select_compatible_version(v_resp.json() or [], server_type, server_version, allow_beta=allow_beta)
                if not chosen:
                    raise ValueError(f"No hay versión estable de '{proj_title}' para {server_type.upper()} {server_version}")

            # Check incompatibility against installed enabled mods BEFORE downloading anything
            for dep in (chosen.get("dependencies") or []):
                if str(dep.get("dependency_type") or "").lower() == "incompatible":
                    tpid = dep.get("project_id")
                    if tpid and tpid in enabled_pids:
                        raise ModConflictError(f"{proj_title} es incompatible con '{title_map.get(tpid, tpid)}' ya instalado")

            chosen_with_title = dict(chosen)
            chosen_with_title["project_id"] = canon_pid
            chosen_with_title["project_title"] = proj_title
            to_install_all = await self.resolve_mod_dependencies(
                chosen_with_title,
                loader=server_type,
                mc_version=server_version,
                client=client,
                allow_beta=allow_beta,
            )

            # Filter out dependencies already installed & enabled in mods/
            to_download = [
                m for m in to_install_all
                if m.get("is_root") or m.get("project_id") not in enabled_pids
            ]

            mods_dir = settings.data_dir / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)
            stage_dir = settings.data_dir / f".modadd_stage_{uuid.uuid4().hex[:8]}"
            stage_dir.mkdir(parents=True, exist_ok=True)
            installed_names: List[str] = []

            try:
                staged_pairs: List[Tuple[Path, Dict[str, Any], str]] = []
                for item in to_download:
                    fname = Path(str(item.get("filename") or f"{item['version_id']}.jar")).name
                    st_path = stage_dir / fname
                    await self._download_verified_file(
                        client,
                        [item["url"]],
                        st_path,
                        expected_sha512=item.get("sha512"),
                        expected_sha1=item.get("sha1"),
                    )
                    sha512_val = item.get("sha512") or self._compute_file_sha512(st_path)
                    staged_pairs.append((st_path, {**item, "filename": fname}, sha512_val))

                manifest = self.read_manifest(settings.data_dir)
                for st_path, item, sha512_val in staged_pairs:
                    dest = self._safe_target_path(settings.data_dir, f"mods/{item['filename']}")
                    st_path.replace(dest)
                    installed_names.append(item["filename"])
                    if manifest is not None:
                        mfiles = manifest.setdefault("managed_files", [])
                        mfiles = [e for e in mfiles if e.get("path") != f"mods/{item['filename']}"]
                        mfiles.append({
                            "path": f"mods/{item['filename']}",
                            "sha512": sha512_val,
                            "origin": "manual",
                            "project_id": item.get("project_id"),
                            "version_id": item.get("version_id"),
                        })
                        manifest["managed_files"] = mfiles

                if manifest is not None:
                    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self.write_manifest(settings.data_dir, manifest)
            finally:
                shutil.rmtree(stage_dir, ignore_errors=True)

        if activity_manager_obj:
            activity_manager_obj.log(
                category="install",
                action="Mod añadido",
                details=f"{proj_title} ({', '.join(installed_names)}) para {server_type.upper()} {server_version}",
                user="admin",
                status="success",
            )

        return {
            "status": "installed",
            "title": proj_title,
            "installed_files": installed_names,
        }

    async def stage_mods_update(
        self,
        filenames: Optional[List[str]] = None,
        allow_beta: bool = False,
        stage_cb: Optional[Callable[[str, int, Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        """Stages and SHA-512 verifies mod updates before stopping or touching existing mods."""
        cb = stage_cb or (lambda s, p, d=None: None)
        cb("downloading_mods", 10, "Comprobando actualizaciones de mods compatibles...")

        info = await self.list_installed_mods(check_updates=True, allow_beta=allow_beta)
        requested = {Path(f).name for f in filenames} if filenames else None
        candidates = [
            m for m in info["mods"]
            if m["enabled"] and m["update_available"] and (requested is None or m["filename"] in requested)
        ]
        if not candidates:
            raise ValueError("No hay actualizaciones pendientes para los mods seleccionados")

        stage_dir = settings.data_dir / f".mods_upd_stage_{uuid.uuid4().hex[:8]}"
        stage_dir.mkdir(parents=True, exist_ok=True)
        replacements: List[Dict[str, Any]] = []
        total = len(candidates)

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
                for idx, mod in enumerate(candidates, start=1):
                    new_fname = Path(str(mod["latest_filename"] or mod["filename"])).name
                    st_path = stage_dir / f"{idx}_{new_fname}"
                    await self._download_verified_file(
                        client,
                        [mod["latest_url"]],
                        st_path,
                        expected_sha512=mod.get("latest_sha512"),
                        expected_sha1=mod.get("latest_sha1"),
                    )
                    sha_val = mod.get("latest_sha512") or self._compute_file_sha512(st_path)
                    replacements.append({
                        "old_filename": mod["filename"],
                        "new_filename": new_fname,
                        "staged_path": st_path,
                        "sha512": sha_val,
                        "project_id": mod.get("project_id"),
                        "version_id": mod.get("latest_version_id"),
                        "title": mod.get("title"),
                        "old_version": mod.get("version_number"),
                        "new_version": mod.get("latest_version_number"),
                        "origin": mod.get("origin") or "manual",
                    })
                    pct = 15 + int((idx / total) * 40)
                    cb("downloading_mods", min(55, pct), f"Pre-descargando actualizaciones ({idx}/{total})...")

            return {"stage_dir": stage_dir, "replacements": replacements}
        except Exception:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise

    def apply_staged_mods_update(
        self,
        staged: Dict[str, Any],
        activity_manager_obj: Any = None,
    ) -> Dict[str, Any]:
        """Atomically swaps verified staged mod JARs into mods/ and updates manifest."""
        stage_dir: Path = staged["stage_dir"]
        replacements: List[Dict[str, Any]] = staged["replacements"]
        updated_names: List[str] = []

        try:
            manifest = self.read_manifest(settings.data_dir)
            for rep in replacements:
                old_p = self._safe_target_path(settings.data_dir, f"mods/{rep['old_filename']}")
                new_p = self._safe_target_path(settings.data_dir, f"mods/{rep['new_filename']}")
                rep["staged_path"].replace(new_p)
                if old_p != new_p and old_p.is_file():
                    old_p.unlink()
                updated_names.append(f"{rep['title']} ({rep['old_version']} → {rep['new_version']})")

                if manifest is not None:
                    mfiles = [
                        e for e in (manifest.get("managed_files") or [])
                        if e.get("path") not in (f"mods/{rep['old_filename']}", f"mods/{rep['new_filename']}")
                    ]
                    mfiles.append({
                        "path": f"mods/{rep['new_filename']}",
                        "sha512": rep["sha512"],
                        "origin": rep["origin"],
                        "project_id": rep.get("project_id"),
                        "version_id": rep.get("version_id"),
                    })
                    manifest["managed_files"] = mfiles

            if manifest is not None:
                manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.write_manifest(settings.data_dir, manifest)

            if activity_manager_obj:
                activity_manager_obj.log(
                    category="update",
                    action="Mods actualizados",
                    details=f"{len(updated_names)} mod(s): {', '.join(updated_names[:5])}",
                    user="admin",
                    status="success",
                )

            return {"status": "completed", "updated": updated_names, "count": len(updated_names)}
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    @staticmethod
    def _validate_mod_filename(filename: str) -> Path:
        """Validates a single mod filename inside mods/ safely against path traversal."""
        raw = str(filename or "").strip()
        if not raw or "/" in raw or "\\" in raw or ".." in raw or "\x00" in raw:
            raise ValueError("Nombre de archivo de mod inválido")
        nl = raw.lower()
        if not (nl.endswith(".jar") or nl.endswith(".jar.disabled")):
            raise ValueError("El archivo debe tener extensión .jar o .jar.disabled")
        mods_root = (settings.data_dir / "mods").resolve()
        candidate = (mods_root / raw).resolve()
        if not candidate.is_relative_to(mods_root) or candidate.parent != mods_root:
            raise ValueError("Ruta de mod fuera de mods/")
        return candidate

    def toggle_mod(self, filename: str) -> Dict[str, Any]:
        """Enables (.jar.disabled -> .jar) or disables (.jar -> .jar.disabled) an installed mod."""
        src = self._validate_mod_filename(filename)
        if not src.is_file():
            raise FileNotFoundError(f"No existe el mod '{filename}'")

        if src.name.lower().endswith(".jar.disabled"):
            new_name = src.name[:-9]
            enabled = True
        else:
            new_name = f"{src.name}.disabled"
            enabled = False

        dst = self._validate_mod_filename(new_name)
        src.replace(dst)
        return {"filename": dst.name, "enabled": enabled}

    def delete_mod(self, filename: str) -> Dict[str, Any]:
        """Deletes a single mod file from mods/ and updates the manifest."""
        target = self._validate_mod_filename(filename)
        if not target.is_file():
            raise FileNotFoundError(f"No existe el mod '{filename}'")

        target.unlink()
        manifest = self.read_manifest(settings.data_dir)
        if manifest is not None:
            base = target.name[:-9] if target.name.lower().endswith(".disabled") else target.name
            manifest["managed_files"] = [
                e for e in (manifest.get("managed_files") or [])
                if e.get("path") not in (f"mods/{target.name}", f"mods/{base}")
            ]
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.write_manifest(settings.data_dir, manifest)

        return {"deleted": target.name}

    async def check_mods_compatibility_for_target(
        self,
        target_mc: str,
        target_loader: Optional[str] = None,
        allow_beta: bool = False,
    ) -> Dict[str, Any]:
        """Checks which enabled mods in mods/ have compatible stable versions for target MC version."""
        cfg = settings.runtime_config
        ldr = str(target_loader or cfg.get("server_type") or "").lower()
        mc = str(target_mc or "").strip()

        info = await self.list_installed_mods(check_updates=False, allow_beta=allow_beta)
        enabled_mods = [m for m in info["mods"] if m["enabled"]]

        compatible: List[Dict[str, Any]] = []
        incompatible: List[Dict[str, Any]] = []
        unknown: List[Dict[str, Any]] = []

        if ldr not in SUPPORTED_LOADERS or not mc:
            return {
                "target_mc": mc,
                "target_loader": ldr,
                "allow_beta": bool(allow_beta),
                "compatible": [],
                "incompatible": [],
                "unknown": enabled_mods,
                "all_compatible": len(enabled_mods) == 0,
            }

        recognized = [m for m in enabled_mods if m.get("recognized") and m.get("sha512")]
        unknown = [{"filename": m["filename"], "title": m["title"]} for m in enabled_mods if not m.get("recognized")]

        if recognized:
            async with httpx.AsyncClient(timeout=25.0, headers=MODRINTH_HEADERS) as client:
                hash_updates = await self._check_batch_updates_strict(
                    client,
                    [m["sha512"] for m in recognized],
                    target_loader=ldr,
                    target_mc=mc,
                    allow_beta=allow_beta,
                )
            for m in recognized:
                cand = hash_updates.get(m["sha512"])
                if cand:
                    files = cand.get("files") or []
                    pfile = next((f for f in files if f.get("primary")), files[0] if files else {})
                    uhashes = pfile.get("hashes") or {}
                    compatible.append({
                        "filename": m["filename"],
                        "title": m["title"],
                        "project_id": m.get("project_id"),
                        "target_version_id": cand.get("id"),
                        "target_version_number": cand.get("version_number") or cand.get("name"),
                        "target_version_type": str(cand.get("version_type") or "release").lower(),
                        "target_filename": pfile.get("filename"),
                        "target_url": pfile.get("url"),
                        "target_sha512": uhashes.get("sha512"),
                        "target_sha1": uhashes.get("sha1"),
                    })
                else:
                    incompatible.append({
                        "filename": m["filename"],
                        "title": m["title"],
                        "project_id": m.get("project_id"),
                        "current_version": m.get("version_number"),
                    })

        return {
            "target_mc": mc,
            "target_loader": ldr,
            "allow_beta": bool(allow_beta),
            "compatible": compatible,
            "incompatible": incompatible,
            "unknown": unknown,
            "all_compatible": len(incompatible) == 0 and len(unknown) == 0,
        }

    async def migrate_mods_for_mc_upgrade(
        self,
        target_mc: str,
        target_loader: str,
        allow_beta: bool = False,
        activity_manager_obj: Any = None,
    ) -> Dict[str, Any]:
        """Upgrades compatible mods to target_mc and safely disables incompatible ones as .jar.disabled."""
        plan = await self.check_mods_compatibility_for_target(
            target_mc=target_mc, target_loader=target_loader, allow_beta=allow_beta
        )
        updated: List[str] = []
        disabled: List[str] = []

        mods_dir = settings.data_dir / "mods"
        manifest = self.read_manifest(settings.data_dir)

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=MODRINTH_HEADERS) as client:
            for item in plan["compatible"]:
                if not item.get("target_url") or not item.get("target_filename"):
                    continue
                old_p = self._safe_target_path(settings.data_dir, f"mods/{item['filename']}")
                new_fname = Path(item["target_filename"]).name
                new_p = self._safe_target_path(settings.data_dir, f"mods/{new_fname}")
                await self._download_verified_file(
                    client,
                    [item["target_url"]],
                    new_p,
                    expected_sha512=item.get("target_sha512"),
                    expected_sha1=item.get("target_sha1"),
                )
                if old_p != new_p and old_p.is_file():
                    old_p.unlink()
                updated.append(new_fname)
                if manifest is not None:
                    sha_val = item.get("target_sha512") or self._compute_file_sha512(new_p)
                    mfiles = [
                        e for e in (manifest.get("managed_files") or [])
                        if e.get("path") not in (f"mods/{item['filename']}", f"mods/{new_fname}")
                    ]
                    mfiles.append({
                        "path": f"mods/{new_fname}",
                        "sha512": sha_val,
                        "origin": "manual",
                        "project_id": item.get("project_id"),
                        "version_id": item.get("target_version_id"),
                    })
                    manifest["managed_files"] = mfiles

        for bad in plan["incompatible"] + plan["unknown"]:
            bad_p = mods_dir / bad["filename"]
            if bad_p.is_file() and bad_p.name.lower().endswith(".jar"):
                bad_p.replace(bad_p.with_name(f"{bad_p.name}.disabled"))
                disabled.append(bad["filename"])

        if manifest is not None:
            manifest["mc_version"] = target_mc
            manifest["loader_type"] = target_loader
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.write_manifest(settings.data_dir, manifest)

        if activity_manager_obj:
            activity_manager_obj.log(
                category="update",
                action="Migración de mods por actualización MC",
                details=f"Objetivo {target_loader.upper()} {target_mc}: actualizados {len(updated)}, desactivados {len(disabled)}",
                user="admin",
                status="success",
            )
        return {"updated": updated, "disabled": disabled}


modpack_manager = ModpackManager()
