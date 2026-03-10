# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

datas = [
    ('src/i18n', 'src/i18n'),
    ('src/resources', 'src/resources'),
]

hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'rawpy',
    'pillow_heif',
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    'PIL.ImageEnhance',
    'PIL.ImageFilter',
    'PIL.ImageQt',
    'PIL.ExifTags',
    'exifread',
    'numpy',
    'json',
    'concurrent.futures',
]

# Exclude unused Qt/PySide6 modules to drastically reduce bundle size
excludes = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2', 'PySide6.QtQmlModels',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtNetwork', 'PySide6.QtSql',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtSerialPort',
    'PySide6.QtSerialBus', 'PySide6.QtSensors', 'PySide6.QtPositioning',
    'PySide6.QtRemoteObjects',
    'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtTest', 'PySide6.QtUiTools',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
    'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    'PySide6.QtDataVisualization', 'PySide6.QtCharts', 'PySide6.QtStateMachine',
    'PySide6.QtXml', 'PySide6.QtDBus', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtWebSockets', 'PySide6.QtHttpServer',
    'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech',
    'PySide6.QtShaderTools', 'PySide6.QtScxml',
    'torch', 'torchvision', 'torchaudio', 'spandrel',
]

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
