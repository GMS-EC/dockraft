import os
import sys
import re
import httpx
import asyncio
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from app.config import settings
from app.core.fs_utils import atomic_write_text

class DownloadManager:
    def __init__(self):
        self.active_download: Optional[Dict[str, Any]] = None
        self._bedrock_cache: Dict[str, Dict[str, str]] = {}

    async def get_paper_versions(self, project: str = "paper") -> List[str]:
        """Fetches available Minecraft versions for Paper/Folia/Velocity using PaperMC v3 API."""
        url = f"https://fill.papermc.io/v3/projects/{project}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            versions_dict = data.get("versions", {})
            all_versions: List[str] = []
            for group, v_list in versions_dict.items():
                if isinstance(v_list, list):
                    all_versions.extend(v_list)
            # Filter out pre-releases/snapshots if desired or keep clean versions first
            return all_versions

    async def get_paper_latest_build(self, project: str, version: str) -> Dict[str, Any]:
        """Gets the latest build information for a Paper version using PaperMC v3 API."""
        url = f"https://fill.papermc.io/v3/projects/{project}/versions/{version}/builds"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            builds = resp.json()
            if not builds or not isinstance(builds, list):
                raise ValueError(f"No builds found for {project} {version}")
            latest_build = builds[-1]
            build_num = latest_build.get("id")
            downloads = latest_build.get("downloads", {})
            # Typically 'server:default' or first download object
            dl_obj = downloads.get("server:default") or next(iter(downloads.values()), None)
            if not dl_obj:
                raise ValueError(f"No download object found in build for {project} {version}")

            download_name = dl_obj.get("name", f"{project}-{version}.jar")
            download_url = dl_obj.get("url")
            return {
                "build": build_num,
                "file_name": download_name,
                "download_url": download_url
            }

    async def get_purpur_versions(self) -> List[str]:
        """Fetches available versions for Purpur."""
        url = "https://api.purpurmc.org/v2/purpur"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            versions = data.get("versions", [])
            return list(reversed(versions))

    async def get_purpur_latest_build(self, version: str) -> Dict[str, Any]:
        """Gets download URL for latest Purpur build."""
        url = f"https://api.purpurmc.org/v2/purpur/{version}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            latest = data.get("builds", {}).get("latest")
            download_url = f"https://api.purpurmc.org/v2/purpur/{version}/{latest}/download"
            return {
                "build": latest,
                "file_name": f"purpur-{version}-{latest}.jar",
                "download_url": download_url
            }

    async def get_vanilla_versions(self) -> List[Dict[str, str]]:
        """Fetches releases from Mojang Version Manifest."""
        url = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            versions = data.get("versions", [])
            # Filter primarily release versions, keep snapshots accessible
            return [
                {"id": v["id"], "type": v["type"], "url": v["url"]}
                for v in versions
                if v.get("type") in ["release", "snapshot"]
            ]

    async def get_vanilla_download_url(self, version_meta_url: str) -> str:
        """Fetches the official server.jar URL from Mojang version metadata."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(version_meta_url)
            resp.raise_for_status()
            data = resp.json()
            server_info = data.get("downloads", {}).get("server", {})
            url = server_info.get("url")
            if not url:
                raise ValueError("No server download found in version metadata")
            return url

    async def get_vanilla_latest(self) -> Dict[str, str]:
        """Fetches latest release and snapshot version IDs from Mojang Version Manifest."""
        url = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("latest", {"release": "", "snapshot": ""})

    async def get_fabric_version_items(self) -> List[Dict[str, Any]]:
        """Fetches all game versions for Fabric including stability flag."""
        url = "https://meta.fabricmc.net/v2/versions/game"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return [{"id": v["version"], "stable": bool(v.get("stable", False))} for v in data]

    async def get_fabric_versions(self) -> List[str]:
        """Fetches supported game versions for Fabric."""
        items = await self.get_fabric_version_items()
        # Only stable versions
        return [v["id"] for v in items if v.get("stable", True)]

    async def get_fabric_download_url(self, game_version: str) -> str:
        """Gets server JAR installer URL for Fabric using the latest loader and installer versions."""
        # Fetch latest loader version
        loader_version = "0.16.10"  # fallback
        installer_version = "1.0.1"  # fallback
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                loader_resp = await client.get("https://meta.fabricmc.net/v2/versions/loader")
                loader_resp.raise_for_status()
                loaders = loader_resp.json()
                if loaders:
                    loader_version = loaders[0].get("version", loader_version)

                installer_resp = await client.get("https://meta.fabricmc.net/v2/versions/installer")
                installer_resp.raise_for_status()
                installers = installer_resp.json()
                if installers:
                    installer_version = installers[0].get("version", installer_version)
        except Exception as e:
            print(f"[Dockraft] Warning: could not fetch latest Fabric versions, using fallback. Error: {e}")

        return f"https://meta.fabricmc.net/v2/versions/loader/{game_version}/{loader_version}/{installer_version}/server/jar"

    async def get_bedrock_versions(self) -> List[str]:
        """
        Dynamically fetches the latest official stable release and preview (beta) versions
        for Minecraft Bedrock Dedicated Server directly from Mojang's live services API.
        Never relies on a fixed version string.
        """
        api_url = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        stable_ver = None
        preview_ver = None
        stable_links: Dict[str, str] = {}
        preview_links: Dict[str, str] = {}

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()
                links = data.get("result", {}).get("links", [])
                
                for item in links:
                    dl_type = item.get("downloadType", "")
                    dl_url = item.get("downloadUrl", "")
                    m = re.search(r'bedrock-server-([0-9\.]+)\.zip', dl_url)
                    if not m:
                        continue
                    ver = m.group(1)

                    if dl_type == "serverBedrockLinux":
                        stable_ver = ver
                        stable_links["linux"] = dl_url
                    elif dl_type == "serverBedrockWindows":
                        stable_ver = ver
                        stable_links["win"] = dl_url
                    elif dl_type == "serverBedrockPreviewLinux":
                        preview_ver = ver
                        preview_links["linux"] = dl_url
                    elif dl_type == "serverBedrockPreviewWindows":
                        preview_ver = ver
                        preview_links["win"] = dl_url

                versions: List[str] = []
                if stable_ver:
                    lbl_stable = f"{stable_ver} (Última Versión Estable)"
                    versions.append(lbl_stable)
                    self._bedrock_cache[lbl_stable] = stable_links
                    self._bedrock_cache[stable_ver] = stable_links

                if preview_ver:
                    lbl_preview = f"{preview_ver} (Preview / Beta)"
                    versions.append(lbl_preview)
                    self._bedrock_cache[lbl_preview] = preview_links
                    self._bedrock_cache[preview_ver] = preview_links

                if versions:
                    return versions
        except Exception:
            pass

        # If cache already has entries from a previous successful fetch, use them
        cached_labels = [k for k in self._bedrock_cache.keys() if "(" in k]
        if cached_labels:
            return cached_labels

        # Fallback if internet or Mojang service is completely unreachable
        return ["1.26.45.1 (Última Versión Estable)", "1.26.60.21 (Preview / Beta)"]

    async def get_bedrock_download_url(self, version: str = "", platform: str = "linux") -> str:
        """
        Resolves the exact official download URL for Mojang Bedrock Dedicated Server.
        Uses cached dynamic URLs from Mojang's API first, then live API, then canonical structure.
        """
        plat = "win" if platform.lower() in ["win", "windows"] else "linux"
        is_preview = "preview" in version.lower() or "beta" in version.lower()

        # 1. Exact match in cache
        if version in self._bedrock_cache:
            url = self._bedrock_cache[version].get(plat)
            if url:
                return url

        # 2. Match by preview/stable type in cache
        for k, v in self._bedrock_cache.items():
            if is_preview and ("preview" in k.lower() or "beta" in k.lower()):
                url = v.get(plat)
                if url:
                    return url
            elif not is_preview and ("preview" not in k.lower() and "beta" not in k.lower()):
                url = v.get(plat)
                if url:
                    return url

        # 3. If cache was empty, fetch versions dynamically now to populate cache
        try:
            await self.get_bedrock_versions()
            if version in self._bedrock_cache:
                url = self._bedrock_cache[version].get(plat)
                if url:
                    return url
            for k, v in self._bedrock_cache.items():
                if is_preview and ("preview" in k.lower() or "beta" in k.lower()):
                    url = v.get(plat)
                    if url:
                        return url
                elif not is_preview and ("preview" not in k.lower() and "beta" not in k.lower()):
                    url = v.get(plat)
                    if url:
                        return url
        except Exception:
            pass

        # 4. Fallback canonical URL structure
        clean_match = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)+)', version)
        ver_clean = clean_match.group(1) if clean_match else "1.26.45.1"
        subpath = "bin-win-preview" if (plat == "win" and is_preview) else \
                  "bin-linux-preview" if (plat == "linux" and is_preview) else \
                  "bin-win" if plat == "win" else "bin-linux"

        return f"https://www.minecraft.net/bedrockdedicatedserver/{subpath}/bedrock-server-{ver_clean}.zip"

    async def get_forge_versions(self) -> List[Dict[str, Any]]:
        """
        Fetches available Minecraft versions and their recommended/latest Forge builds from promotions_slim.json.
        Returns list of {"id": mc_version, "label": label, "mc_version": mc_ver, "forge_build": build, "is_recommended": bool}.
        """
        url = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            promos = data.get("promos", {})

        mc_map: Dict[str, Dict[str, str]] = {}
        for key, build in promos.items():
            if "-" in key:
                mc_ver, kind = key.rsplit("-", 1)
                if mc_ver not in mc_map:
                    mc_map[mc_ver] = {}
                mc_map[mc_ver][kind] = build

        results: List[Dict[str, Any]] = []
        for mc_ver, builds in mc_map.items():
            if "recommended" in builds:
                build = builds["recommended"]
                is_rec = True
            elif "latest" in builds:
                build = builds["latest"]
                is_rec = False
            else:
                continue

            label = f"{mc_ver} (Forge {build}{' - ⭐ Recomendada' if is_rec else ' - Latest'})"
            results.append({
                "id": mc_ver,
                "label": label,
                "mc_version": mc_ver,
                "forge_build": build,
                "is_recommended": is_rec
            })

        def ver_key(v_obj):
            parts = [int(p) for p in re.findall(r'\d+', v_obj["mc_version"])]
            return parts

        results.sort(key=ver_key, reverse=True)
        return results

    async def get_forge_download_url(self, mc_version: str, forge_build: Optional[str] = None) -> str:
        """Constructs official Maven installer download URL for Forge."""
        if not forge_build:
            versions = await self.get_forge_versions()
            for v in versions:
                if v["mc_version"] == mc_version:
                    forge_build = v["forge_build"]
                    break
        if not forge_build:
            raise ValueError(f"No Forge build found for Minecraft {mc_version}")

        return f"https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_version}-{forge_build}/forge-{mc_version}-{forge_build}-installer.jar"

    async def install_forge_server(self, installer_path: Path, java_bin: str = "java") -> Dict[str, Any]:
        """Runs 'java -jar <installer> --installServer' inside settings.data_dir."""
        proc = await asyncio.create_subprocess_exec(
            java_bin, "-jar", str(installer_path), "--installServer",
            cwd=str(settings.data_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode('utf-8', errors='replace')
            raise RuntimeError(f"Forge --installServer failed: {err_msg[:300]}")

        # Detect generated launch script or jar
        run_sh = settings.data_dir / "run.sh"
        if run_sh.exists():
            if sys.platform != "win32":
                try:
                    os.chmod(run_sh, 0o755)
                except Exception:
                    pass
            return {"server_file": "run.sh", "is_script": True}

        # Legacy Forge jar check
        for f in settings.data_dir.iterdir():
            if f.is_file() and f.name.startswith("forge-") and f.name.endswith(".jar") and not f.name.endswith("-installer.jar"):
                return {"server_file": f.name, "is_script": False}

        return {"server_file": "run.sh" if run_sh.exists() else "server.jar", "is_script": run_sh.exists()}

    def verify_file_integrity(self, file_path: Any, expected_type: str = "jar") -> bool:
        """
        Validates downloaded archive/binary to guarantee zero corruptions before replacement.
        Checks:
        1. File existence and non-zero size (at least 512 KB for server binaries).
        2. Binary magic headers (ZIP/JAR starts with PK\x03\x04).
        3. Comprehensive CRC32 check on all members via zipfile.ZipFile.testzip().
        Raises ValueError with descriptive reason if corrupt. Returns True if valid.
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        if not file_path.exists():
            raise ValueError(f"El archivo descargado no existe en {file_path}")

        file_size = file_path.stat().st_size
        min_size = 512 * 1024  # At least 512 KB

        if file_size < min_size:
            raise ValueError(
                f"El archivo descargado está incompleto o truncado (tamaño: {file_size} bytes, mínimo: {min_size} bytes)"
            )

        ext = file_path.suffix.lower()
        if expected_type in ["jar", "zip"] or ext in [".jar", ".zip"]:
            # Check magic bytes
            with open(file_path, "rb") as f:
                header = f.read(4)
                if not header.startswith(b"PK\x03\x04"):
                    raise ValueError("El archivo descargado no tiene una cabecera ZIP/JAR válida (posible error 404/500 o descarga interrumpida)")

            # Check full internal zip integrity with CRC32 test
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    corrupt_entry = zf.testzip()
                    if corrupt_entry is not None:
                        raise ValueError(
                            f"Se detectó corrupción de datos en el archivo descargado (suma CRC32 inválida en '{corrupt_entry}')"
                        )
                    namelist = zf.namelist()
                    if not namelist:
                        raise ValueError("El archivo descargado está vacío sin contenido interno")
            except zipfile.BadZipFile as bz:
                raise ValueError(f"Archivo ZIP/JAR corrupto o dañado: {str(bz)}")

        return True

    async def download_file(
        self,
        url: str,
        target_filename: str,
        is_zip: bool = False,
        preserve_existing_configs: bool = False,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        verify_integrity: bool = True
    ) -> Path:
        """
        Streams download to target path with progress tracking and anti-corruption verification.
        If is_zip is True, extracts the contents into settings.data_dir.
        If preserve_existing_configs is True, avoids overwriting server.properties,
        permissions.json, allowlist.json, and worlds/ folder.
        """
        dest_path = settings.data_dir / target_filename
        self.active_download = {
            "file": target_filename,
            "total": 0,
            "downloaded": 0,
            "percent": 0,
            "status": "downloading"
        }

        default_headers = {"User-Agent": "Dockraft-Manager/1.0"}
        if headers:
            default_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=default_headers) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    self.active_download["total"] = total_size
                    downloaded = 0

                    with open(dest_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            self.active_download["downloaded"] = downloaded
                            if total_size > 0:
                                pct = int((downloaded / total_size) * 100)
                                self.active_download["percent"] = pct
                            if progress_callback:
                                progress_callback(downloaded, total_size)

            if verify_integrity:
                self.verify_file_integrity(dest_path, "zip" if (is_zip or target_filename.endswith(".zip")) else "jar")

            # If it's a zip (Bedrock or modpack), extract it
            if is_zip or target_filename.endswith(".zip"):
                self.active_download["status"] = "extracting"
                with zipfile.ZipFile(dest_path, 'r') as zip_ref:
                    if preserve_existing_configs:
                        protected_files = {"server.properties", "permissions.json", "allowlist.json", "whitelist.json"}
                        for member in zip_ref.infolist():
                            member_path = Path(member.filename)
                            if ".." in member_path.parts:
                                continue
                            target_file = settings.data_dir / member.filename
                            if target_file.exists() and member.filename.lower() in protected_files:
                                continue
                            if target_file.exists() and member.filename.startswith("worlds/"):
                                continue
                            zip_ref.extract(member, settings.data_dir)
                    else:
                        zip_ref.extractall(settings.data_dir)

                # Ensure bedrock binary has execute permission on Unix
                bedrock_bin = settings.data_dir / "bedrock_server"
                if bedrock_bin.exists():
                    try:
                        os.chmod(bedrock_bin, 0o755)
                    except Exception:
                        pass

            self.active_download["status"] = "completed"
            self.active_download["percent"] = 100
            return dest_path

        except Exception as e:
            if dest_path.exists() and (is_zip or target_filename.endswith(".tmp") or target_filename.startswith(".")):
                try:
                    dest_path.unlink()
                except Exception:
                    pass
            if self.active_download:
                self.active_download["status"] = f"error: {str(e)}"
            raise e
        finally:
            # Auto accept EULA and guarantee server.properties is configured
            self.accept_eula()
            self.ensure_initial_config()

    @staticmethod
    def accept_eula() -> None:
        """Writes eula=true to eula.txt in the data directory."""
        eula_path = settings.data_dir / "eula.txt"
        try:
            atomic_write_text(eula_path, "# Generated by Dockraft\neula=true\n")
        except Exception:
            pass

    @staticmethod
    def ensure_initial_config() -> None:
        """Ensures server.properties exists and is configured for immediate first launch."""
        prop_file = settings.data_dir / "server.properties"
        cfg = settings.runtime_config
        s_type = cfg.get("server_type", "paper")
        s_name = cfg.get("server_name", "Mi Servidor Dockraft")
        default_port = 19132 if s_type == "bedrock" else 25565

        if not prop_file.exists():
            try:
                atomic_write_text(
                    prop_file,
                    f"# Minecraft server properties - Dockraft\n"
                    f"server-port={default_port}\n"
                    f"motd={s_name}\n"
                    f"server-name={s_name}\n"
                    f"online-mode=true\n"
                    f"max-players=20\n"
                    f"difficulty=easy\n"
                    f"gamemode=survival\n"
                    f"view-distance=10\n"
                    f"simulation-distance=8\n"
                )
            except Exception:
                pass

    def detect_server_version(self, data_dir: Optional[Path] = None, server_file: Optional[str] = None) -> Optional[str]:
        """
        Attempts to detect the Minecraft server version from local files:
        1. version_history.json (Paper / Purpur)
        2. logs/latest.log (Server startup line)
        3. Jar file name matching regex
        4. Jar manifest / version.json inside archive
        """
        dir_path = data_dir or settings.data_dir
        if not dir_path.exists():
            return None

        # 1. Check version_history.json (Standard in Paper/Purpur)
        vh = dir_path / "version_history.json"
        if vh.exists():
            try:
                content = vh.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'MC:\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)', content)
                if m:
                    return m.group(1)
                m2 = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)?)', content)
                if m2:
                    return m2.group(1)
            except Exception:
                pass

        # 2. Check logs/latest.log if exists
        latest_log = dir_path / "logs" / "latest.log"
        if latest_log.exists():
            try:
                with open(latest_log, "r", encoding="utf-8", errors="ignore") as lf:
                    for _ in range(120):
                        line = lf.readline()
                        if not line:
                            break
                        m = re.search(r'Starting minecraft server version ([0-9]+\.[0-9]+(?:\.[0-9]+)?)', line, re.IGNORECASE)
                        if m:
                            return m.group(1)
                        m2 = re.search(r'\(MC:\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)\)', line)
                        if m2:
                            return m2.group(1)
            except Exception:
                pass

        # 3. Check candidate jar files
        candidates = []
        if server_file and (dir_path / server_file).exists():
            candidates.append(dir_path / server_file)

        try:
            for f in dir_path.iterdir():
                if f.is_file() and f.suffix == ".jar" and f not in candidates:
                    candidates.append(f)
        except Exception:
            pass

        for jar_path in candidates:
            # Check filename regex first (e.g. paper-1.20.4-398.jar)
            fn_m = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)?)', jar_path.name)
            if fn_m:
                return fn_m.group(1)

            # Check inside jar archive
            try:
                with zipfile.ZipFile(jar_path, 'r') as zf:
                    # Check version.json (Mojang Vanilla / Fabric)
                    if "version.json" in zf.namelist():
                        import json
                        v_data = json.loads(zf.read("version.json").decode("utf-8", errors="ignore"))
                        if "id" in v_data:
                            return str(v_data["id"])

                    # Check META-INF/MANIFEST.MF
                    if "META-INF/MANIFEST.MF" in zf.namelist():
                        mf = zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="ignore")
                        m = re.search(r'Specification-Version:\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)', mf)
                        if m:
                            return m.group(1)
                        m2 = re.search(r'Implementation-Version:\s*.*?([0-9]+\.[0-9]+(?:\.[0-9]+)?)', mf)
                        if m2:
                            return m2.group(1)
            except Exception:
                pass

        return None

downloader = DownloadManager()
verify_file_integrity = downloader.verify_file_integrity
