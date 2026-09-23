# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for vj-remote: one-file Windows exe (console kept on).

Build locally (Windows):   pyinstaller vj-remote.spec
Automated:                  .github/workflows/build.yml builds this on
                            windows-latest and attaches dist/vj-remote.exe
                            to a GitHub Release on tags v*.

NOTE on separators: datas below is a list of (src, dest) tuples — in a
.spec file PyInstaller applies the platform's path separator automatically,
so this same spec builds on Windows (;) and Linux (:). The ";" form only
matters on the pyinstaller *command line*.
"""

from PyInstaller.utils.hooks import collect_submodules

# Imported lazily / dynamically at runtime, so PyInstaller's static
# analysis would miss them without these.
hiddenimports = (
    collect_submodules("websockets")
    + collect_submodules("pythonosc")
    + collect_submodules("qrcode")
)

a = Analysis(
    ["server.py"],
    pathex=[],
    binaries=[],
    datas=[("web", "web")],          # bundled -> sys._MEIPASS/web at runtime
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="vj-remote",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                    # KEEP the console: it IS the "it's running" indicator
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
