# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
WEB_RESOURCE = ROOT / "src/auto_check/web"
DATA_RESOURCE = ROOT / "src/auto_check/resources"

a = Analysis(
    [str(SRC / "auto_check" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(WEB_RESOURCE), "auto_check/web"),
        (str(DATA_RESOURCE), "auto_check/resources"),
    ],
    hiddenimports=[
        'py7zr',
        'rarfile',
        'psycopg',
        'psycopg_binary',
        'psycopg.pq',
        'pymysql',
        'auto_check.resources',
        'auto_check.resources.data',
    ],
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
    name="auto-check",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
