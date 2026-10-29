# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — compila o python-engine como sidecar para Tauri

from pathlib import Path

block_cipher = None

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('.env', '.'),
    ],
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
        'app.rag.embeddings',
        'app.rag.vector_store',
        'app.rag.chunker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'cv2', 'ultralytics', 'fastapi', 'uvicorn'],
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
