# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — compila o python-engine como sidecar para Tauri

from pathlib import Path

block_cipher = None

# Detector suplementar Open Images V7: entra no pacote só se foi exportado
# (scripts/export_oiv7.py); sem ele o app segue só com o YOLO principal.
_oiv7 = [
    (str(p), 'models')
    for p in (Path('../storage/models/yolov8n-oiv7.onnx'), Path('../storage/models/yolov8n-oiv7.labels.json'))
    if p.is_file()
]

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    # Nunca empacotar o .env: as chaves ficariam dentro do executável distribuído.
    datas=[('../storage/models/yolov8n.onnx', 'models'), ('../storage/models/yolo26x.onnx', 'models'),
           ('app/vision/*.py', 'learning_code/app/vision')] + _oiv7,
    hiddenimports=[
        'anthropic',
        'httpx',
        'onnxruntime',
        'tokenizers',
        'numpy',
        'chromadb',
        'chromadb.api',
        'chromadb.db.impl.sqlite',
        'pdfminer',
        'pdfminer.high_level',
        'pdfminer.layout',
        'app.chat.providers',
        'app.chat.amr',
        'app.chat.memory_stream',
        'app.rag.embeddings',
        'app.rag.vector_store',
        'app.rag.chunker',
        'app.vision.detector',
        'app.vision.environment',
        'app.vision.learning',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'ultralytics', 'fastapi', 'uvicorn'],
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
    name='solaris-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # stdin/stdout pipe — precisa de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
