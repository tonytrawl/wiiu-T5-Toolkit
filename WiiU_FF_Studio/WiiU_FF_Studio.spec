# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['wiiu_ff_studio.py'],
    pathex=[],
    binaries=[],
    datas=[('wiiu_ff.py', '.'), ('salsa20.py', '.'), ('zone_validate.py', '.'), ('ff_assets.py', '.'), ('studio.ico', '.')],
    hiddenimports=['wiiu_ff', 'salsa20', 'zone_validate', 'ff_assets'],
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
    name='WiiU_FF_Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['studio.ico'],
)
