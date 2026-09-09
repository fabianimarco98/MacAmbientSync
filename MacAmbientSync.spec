# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('config.example.yaml', '.')],
    hiddenimports=['PyQt6', 'mss', 'PIL', 'yaml'],
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
    [],
    exclude_binaries=True,
    name='MacAmbientSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MacAmbientSync',
)
app = BUNDLE(
    coll,
    name='MacAmbientSync.app',
    icon=None,
    bundle_identifier='com.marcofabiani.macambientsync',
    info_plist={
        'CFBundleName': 'MacAmbientSync',
        'CFBundleDisplayName': 'MacAmbientSync',
        'CFBundleIdentifier': 'com.marcofabiani.macambientsync',
        'CFBundleVersion': '1.2.0',
        'CFBundleShortVersionString': '1.2.0',
        'NSHighResolutionCapable': True,
        'NSScreenCaptureUsageDescription': 'MacAmbientSync requires screen recording permissions to synchronize lights with videos and active windows.',
        'NSCameraUsageDescription': 'MacAmbientSync requires screen recording permissions.',
    }
)
