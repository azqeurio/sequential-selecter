# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Collect all data files
datas = [
    ('src/i18n', 'src/i18n'),  # Translation files
    ('src/resources', 'src/resources'),  # Camera logos, assets
]

# Hidden imports for PySide6 and image processing libraries
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
# The app only uses QtWidgets, QtCore, QtGui
excludes = [
    # Qt WebEngine (~200MB+)
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    # Qt 3D (~50MB+)
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DAnimation',
    # Qt Quick / QML (~100MB+)
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2',
    'PySide6.QtQmlModels',
    # Qt Multimedia (~30MB+)
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    # Qt Network / SQL
    'PySide6.QtNetwork',
    'PySide6.QtSql',
    # Qt Peripherals / IoT
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtSerialPort',
    'PySide6.QtSerialBus',
    'PySide6.QtSensors',
    'PySide6.QtPositioning',
    'PySide6.QtRemoteObjects',
    # Qt Design / Test / Help
    'PySide6.QtDesigner',
    'PySide6.QtHelp',
    'PySide6.QtTest',
    'PySide6.QtUiTools',
    # Qt SVG / OpenGL
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    # Qt Data / Charts
    'PySide6.QtDataVisualization',
    'PySide6.QtCharts',
    'PySide6.QtStateMachine',
    # Qt XML / DBus / PDF
    'PySide6.QtXml',
    'PySide6.QtDBus',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    # Other heavy modules
    'PySide6.QtWebSockets',
    'PySide6.QtHttpServer',
    'PySide6.QtSpatialAudio',
    'PySide6.QtTextToSpeech',
    'PySide6.QtShaderTools',
    'PySide6.QtScxml',
    # Third-party heavy libs (optional, user installs at runtime)
    'torch',
    'torchvision',
    'torchaudio',
    'spandrel',
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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SequentialSelector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI application, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='sqs.ico',
)
