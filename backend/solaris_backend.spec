# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para compilar o backend FastAPI como executável Windows

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Inclui arquivos de configuração e modelos
        ('.env', '.'),
    ],
    hiddenimports=[
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'aiosqlite',
        'greenlet',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.ext.asyncio',
        'anthropic',
        'httpx',
        'app.core.config',
        'app.core.database',
        'app.modules.chat.router',
        'app.modules.chat.models',
        'app.modules.chat.providers',
        'app.modules.chat.router_amr',
        'app.modules.projects.router',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'PIL', 'cv2', 'ultralytics'],
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
    name='solaris-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # sem janela de console no Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
