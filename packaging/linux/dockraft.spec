# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent

hidden_imports = (
    collect_submodules("uvicorn")
    + collect_submodules("app")
    + [
        "pystray._appindicator",
        "pystray._gtk",
        "pystray._xorg",
        "Xlib",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.font",
        "PIL.ImageTk",
        "PIL._tkinter_finder",
        "multipart",
        "tzdata",
    ]
)

try:
    import gi  # noqa: F401
    hidden_imports += collect_submodules("gi")
except ImportError:
    pass

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "CHANGELOG.md"), "."),
    (str(ROOT / "packaging" / "linux" / "dockraft.png"), "packaging/linux"),
] + collect_data_files("tzdata")

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dockraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ROOT / "packaging" / "linux" / "dockraft.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Dockraft",
)
