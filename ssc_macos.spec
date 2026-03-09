# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

datas = [
    ('src/i18n', 'src/i18n'),
]

hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtOpenGLWidgets',
    'rawpy',
    'pillow_heif',
    'PIL',
    'PIL.Image',
    'PIL.ImageQt',
    'numpy',
]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SequentialSelector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=True,  # Required for macOS
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SequentialSelector',
)

app = BUNDLE(
    coll,
    name='SequentialSelector.app',
    icon=None,  # Add 'sqs.icns' here once you convert sqs.ico to icns
    bundle_identifier='com.ssc.sequentialselector',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDocumentTypes': [],
        'NSHighResolutionCapable': True,
    },
)
