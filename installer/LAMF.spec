# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the one-file LAMF.exe Windows GUI installer.

    pyinstaller --clean --noconfirm installer/LAMF.spec

Produces ``dist/LAMF.exe``: a single, windowed (no console) executable that
carries the whole LAMF package as data under ``payload/``.

Design notes
------------
* The payload is *data*, not analysed Python. ``installer/windows_gui.py`` is
  the only analysed entry point; ``install.py`` and the ``lamf`` runtime are
  copied verbatim so the installed tree is byte-identical to the source
  package and is imported/executed from its PERMANENT location after staging.
* ``console=False`` — the finished EXE never shows a console window. Every
  child process the GUI spawns uses CREATE_NO_WINDOW for the same reason.
* Nothing here bakes ``_MEIPASS`` into anything: windows_gui.py stages the
  payload out of the temp unpack directory before install.py ever runs.
"""
import os
import sys
from pathlib import Path

# SPECPATH is injected by PyInstaller; fall back for direct execution/linting.
PROJECT_ROOT = Path(globals().get("SPECPATH", Path.cwd())).resolve().parent
INSTALLER_DIR = PROJECT_ROOT / "installer"
ENTRY_SCRIPT = INSTALLER_DIR / "windows_gui.py"

# Kept in sync with windows_gui.PAYLOAD_ITEMS / STAGE_EXCLUDE_* by
# runtime/tests/installer_gui_test.py, which fails the build contract if they
# drift apart.
PAYLOAD_DIR_NAME = "payload"
PAYLOAD_ITEMS = (
    "installer",
    "runtime",
    "05_INTEGRATIONS",
    "VERSION",
    "LICENSE",
    "README.md",
    "INSTALL.md",
    "SECURITY.md",
)
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def collect_payload(root: Path):
    """(source, dest_dir) tuples placing the package under ``payload/`` in the bundle."""
    collected = []
    for item in PAYLOAD_ITEMS:
        src = root / item
        if not src.exists():
            print(f"[LAMF.spec] payload item not found, skipping: {item}")
            continue
        if src.is_file():
            collected.append((str(src), PAYLOAD_DIR_NAME))
            continue
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if EXCLUDE_DIRS.intersection(rel.parts):
                continue
            if path.suffix in EXCLUDE_SUFFIXES:
                continue
            collected.append((str(path), str(Path(PAYLOAD_DIR_NAME) / rel.parent)))
    if not collected:
        raise SystemExit(f"[LAMF.spec] no payload collected from {root}")
    print(f"[LAMF.spec] payload files: {len(collected)}")
    return collected


def read_version(root: Path) -> str:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip() or "2.0.0"
    except OSError:
        return "2.0.0"


VERSION = read_version(PROJECT_ROOT)


def version_tuple(text: str):
    parts = [int(p) for p in text.split(".") if p.isdigit()][:4]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def windows_version_resource():
    """Windows file-properties resource, so the EXE is not anonymous."""
    if sys.platform != "win32":
        return None
    try:
        from PyInstaller.utils.win32.versioninfo import (
            FixedFileInfo, StringFileInfo, StringStruct, StringTable,
            VarFileInfo, VarStruct, VSVersionInfo,
        )
    except ImportError:
        return None
    numbers = version_tuple(VERSION)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F,
                          flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "LAMF"),
                StringStruct("FileDescription", "LAMF Installer — Local Agent Memory Fabric"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "LAMF"),
                StringStruct("LegalCopyright", "MIT licensed. See LICENSE."),
                StringStruct("OriginalFilename", "LAMF.exe"),
                StringStruct("ProductName", "LAMF Installer"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )


ICON = INSTALLER_DIR / "lamf.ico"

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(INSTALLER_DIR)],
    binaries=[],
    datas=collect_payload(PROJECT_ROOT),
    # install.py is loaded dynamically from the bundled payload for the GUI's
    # single-source-of-truth catalogs. Its stdlib-only imports are therefore
    # not visible to static analysis; platform is otherwise omitted.
    hiddenimports=["platform"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The GUI is stdlib + tkinter only. Excluding the usual heavyweights keeps
    # the one-file EXE small and its startup fast.
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PIL", "IPython",
        "pytest", "pydoc_data", "test", "unittest.test",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# a.zipfiles disappeared in newer PyInstaller releases; stay compatible with both.
_payload_args = [a.binaries]
_zipfiles = getattr(a, "zipfiles", None)
if _zipfiles is not None:
    _payload_args.append(_zipfiles)
_payload_args.append(a.datas)

exe = EXE(
    pyz,
    a.scripts,
    *_payload_args,
    [],
    name="LAMF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                 # no console window in the final EXE
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,               # installs per-user; never silently elevates
    icon=str(ICON) if ICON.is_file() else None,
    version=windows_version_resource(),
)
