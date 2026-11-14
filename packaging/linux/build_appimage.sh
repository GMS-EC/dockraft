#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Pick Python interpreter (.venv first, then python3)
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY_EXE="$REPO_ROOT/.venv/bin/python"
else
    PY_EXE="$(command -v python3 || command -v python)"
fi

if [[ -z "${PY_EXE:-}" ]]; then
    echo "Error: Python 3 not found." >&2
    exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|aarch64) ;;
    arm64) ARCH="aarch64" ;;
    *)
        echo "Warning: uncommon architecture '$ARCH', passing through to appimagetool." >&2
        ;;
esac

if [[ -n "${DOCKRAFT_VERSION:-}" ]]; then
    VERSION="${DOCKRAFT_VERSION#v}"
else
    VERSION="$("$PY_EXE" - <<'PY'
import re
from pathlib import Path
text = Path("CHANGELOG.md").read_text(encoding="utf-8") if Path("CHANGELOG.md").is_file() else ""
m = re.search(r"^##\s+\[(\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?)\]", text, re.MULTILINE)
print(m.group(1) if m else "1.6.0")
PY
)"
fi

echo "[1/4] Checking PyInstaller ($PY_EXE)..."
if ! "$PY_EXE" -m PyInstaller --version >/dev/null 2>&1; then
    echo "      Installing Linux packaging dependencies..."
    "$PY_EXE" -m pip install -r "$REPO_ROOT/requirements.txt" -r "$SCRIPT_DIR/requirements-linux.txt"
fi

echo "[2/4] Building Dockraft Linux bundle with PyInstaller..."
BUILD_WORK="$REPO_ROOT/build/linux"
DIST_WORK="$REPO_ROOT/dist/linux"
rm -rf "$BUILD_WORK/Dockraft" "$DIST_WORK/Dockraft"
"$PY_EXE" -m PyInstaller --noconfirm --clean \
    --workpath "$BUILD_WORK" \
    --distpath "$DIST_WORK" \
    "$SCRIPT_DIR/dockraft.spec"

echo "[3/4] Staging Dockraft.AppDir..."
APPDIR="$BUILD_WORK/Dockraft.AppDir"
rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST_WORK/Dockraft/." "$APPDIR/usr/bin/"
cp "$SCRIPT_DIR/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/Dockraft"

cp "$SCRIPT_DIR/dockraft.desktop" "$APPDIR/dockraft.desktop"
cp "$SCRIPT_DIR/dockraft.desktop" "$APPDIR/usr/share/applications/dockraft.desktop"
cp "$SCRIPT_DIR/dockraft.png" "$APPDIR/dockraft.png"
cp "$SCRIPT_DIR/dockraft.png" "$APPDIR/.DirIcon"
cp "$SCRIPT_DIR/dockraft.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/dockraft.png"

# Ensure executable permissions on bundled AppRun/binary
APPIMAGETOOL="$(command -v appimagetool || command -v "appimagetool-${ARCH}.AppImage" || true)"
if [[ -z "$APPIMAGETOOL" ]]; then
    TOOL_CACHE="$BUILD_WORK/tools/appimagetool-${ARCH}.AppImage"
    if [[ ! -x "$TOOL_CACHE" ]]; then
        echo "appimagetool not found in PATH; downloading continuous release for $ARCH..."
        mkdir -p "$(dirname "$TOOL_CACHE")"
        TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
        curl -fL --retry 3 -o "$TOOL_CACHE" "$TOOL_URL"
        chmod +x "$TOOL_CACHE"
    fi
    APPIMAGETOOL="$TOOL_CACHE"
fi

echo "[4/4] Packaging AppImage..."
OUT_APPIMAGE="$REPO_ROOT/dist/Dockraft-${VERSION}-${ARCH}.AppImage"
mkdir -p "$REPO_ROOT/dist"
rm -f "$OUT_APPIMAGE"

ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$OUT_APPIMAGE"
chmod +x "$OUT_APPIMAGE"

echo "Done! AppImage ready at: $OUT_APPIMAGE"
