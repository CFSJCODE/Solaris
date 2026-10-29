"""Entrypoint para PyInstaller — inicia o uvicorn programaticamente."""
import sys
import os

# Quando rodando como .exe empacotado pelo PyInstaller,
# sys._MEIPASS aponta para a pasta temporária de extração.
# Adicionar ao path garante que os imports da 'app' funcionem.
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    os.chdir(bundle_dir)
    sys.path.insert(0, bundle_dir)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8765,
        log_level="warning",
    )
