# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['bitcoin_monitor_windows.py'],
    pathex=[],
    binaries=[('C:\\Users\\vitor\\AppData\\Local\\Programs\\Python\\Python313\\vcruntime140.dll', '.'), ('C:\\Users\\vitor\\AppData\\Local\\Programs\\Python\\Python313\\vcruntime140_1.dll', '.')],
    datas=[],
    hiddenimports=[],
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
    name='BitcoinMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
