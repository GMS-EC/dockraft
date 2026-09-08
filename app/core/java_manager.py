import os
import shutil
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

class JavaManager:
    @staticmethod
    def get_java_version(binary_path: str) -> Optional[int]:
        """Runs '<binary> -version' and extracts the major version (8, 11, 17, 21)."""
        try:
            res = subprocess.run(
                [binary_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3
            )
            output = res.stderr or res.stdout
            # Match 1.8.0_xxx or 11.0.x or 17.0.x or 21.0.x
            match = re.search(r'version "(1\.)?(\d+)', output)
            if match:
                major = int(match.group(2))
                return major
        except Exception:
            pass
        return None

    @classmethod
    def detect_runtimes(cls) -> List[Dict[str, Any]]:
        """Finds all available Java runtimes on the machine."""
        found: List[Dict[str, Any]] = []
        checked_paths = set()

        # 1. Check default 'java' in PATH
        default_java = shutil.which("java")
        if default_java:
            v = cls.get_java_version(default_java)
            checked_paths.add(os.path.normpath(default_java).lower())
            found.append({
                "name": f"Java {v or 'Default'} (PATH)",
                "path": default_java,
                "version": v,
                "is_default": True
            })

        # 2. Check common Linux JVM directories
        linux_jvm_dirs = [
            Path("/usr/lib/jvm"),
            Path("/usr/java"),
            Path("/opt/java"),
            Path("/docker-java-home")
        ]
        for base in linux_jvm_dirs:
            if base.exists() and base.is_dir():
                for sub in base.iterdir():
                    bin_candidate = sub / "bin" / "java"
                    if bin_candidate.is_file() and os.access(bin_candidate, os.X_OK):
                        norm = str(bin_candidate.resolve()).lower()
                        if norm not in checked_paths:
                            checked_paths.add(norm)
                            v = cls.get_java_version(str(bin_candidate))
                            found.append({
                                "name": f"Java {v or sub.name} ({sub.name})",
                                "path": str(bin_candidate),
                                "version": v,
                                "is_default": False
                            })

        # 3. Check Windows Program Files directories
        win_dirs = [
            Path(r"C:\Program Files\Java"),
            Path(r"C:\Program Files\Eclipse Adoptium"),
            Path(r"C:\Program Files\BellSoft"),
            Path(r"C:\Program Files\Zulu")
        ]
        for base in win_dirs:
            if base.exists() and base.is_dir():
                for sub in base.iterdir():
                    bin_candidate = sub / "bin" / "java.exe"
                    if bin_candidate.is_file():
                        norm = str(bin_candidate.resolve()).lower()
                        if norm not in checked_paths:
                            checked_paths.add(norm)
                            v = cls.get_java_version(str(bin_candidate))
                            found.append({
                                "name": f"Java {v or sub.name} ({sub.name})",
                                "path": str(bin_candidate),
                                "version": v,
                                "is_default": False
                            })

        return found

    @staticmethod
    def get_recommended_java(minecraft_version: str) -> int:
        """Returns the recommended Java major version for a given Minecraft version."""
        try:
            parts = [int(p) for p in re.findall(r'\d+', minecraft_version)]
            if len(parts) >= 1:
                major = parts[0]
                minor = parts[1] if len(parts) > 1 else 0
                patch = parts[2] if len(parts) > 2 else 0

                if major >= 25 or (major == 1 and minor >= 25):
                    return 25
                elif major == 1:
                    if minor < 17:
                        return 8
                    elif minor < 20 or (minor == 20 and patch <= 4):
                        return 17
                    elif minor <= 24:
                        return 21
                    else:
                        return 25
        except Exception:
            pass
        return 25

    @classmethod
    def get_best_java_path(cls, minecraft_version: str) -> str:
        """
        Returns the path to the best installed Java binary matching the Minecraft version.
        Prioritizes container paths (/opt/java/java-XX/bin/java) or detected runtimes matching the target version.
        """
        target_version = cls.get_recommended_java(minecraft_version)

        # 1. Direct container paths check
        candidates = {
            25: Path("/opt/java/java-25/bin/java"),
            21: Path("/opt/java/java-21/bin/java"),
            17: Path("/opt/java/java-17/bin/java")
        }
        if target_version in candidates and candidates[target_version].exists():
            return str(candidates[target_version])

        # 2. Check detected runtimes for an exact version match
        runtimes = cls.detect_runtimes()
        for rt in runtimes:
            if rt.get("version") == target_version:
                return rt["path"]

        # 3. Fallback: closest compatible version or default 'java'
        if target_version >= 21:
            for v in [25, 21]:
                if v in candidates and candidates[v].exists():
                    return str(candidates[v])
                for rt in runtimes:
                    if rt.get("version") == v:
                        return rt["path"]
        elif target_version >= 17:
            for v in [17, 21]:
                if v in candidates and candidates[v].exists():
                    return str(candidates[v])
                for rt in runtimes:
                    if rt.get("version") == v:
                        return rt["path"]

        return "java"
