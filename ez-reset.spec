# -*- mode: python ; coding: utf-8 -*-

# Windows: pyinstaller ez-reset.spec
# Include the original devices.xml from the fork as-is.
a = Analysis(
    ['src\\ez_reset\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src\\ez_reset\\devices.xml', 'ez_reset'),
        ('src\\ez_reset\\wic_candidates.csv', 'ez_reset'),
    ],
    hiddenimports=['pywin32', 'win32file', 'win32print', 'win32ui', 'win32con'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='ez-reset', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)
