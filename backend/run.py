"""Entrypoint para PyInstaller — inicia o uvicorn programaticamente."""

# Importa as bibliotecas necessárias
import os
import sys

# Quando rodando como .exe empacotado pelo PyInstaller,
# sys._MEIPASS aponta para a pasta temporária de extração.
# Adicionar ao path garante que os imports da 'app' funcionem.
if getattr(sys, "frozen", False):
    bundle_dir = str(sys._MEIPASS)  # type: ignore[attr-defined]
    os.chdir(bundle_dir)
    sys.path.insert(0, bundle_dir)

# Importa o uvicorn dinamicamente para evitar falha na análise estática
# quando o ambiente de desenvolvimento não tem os stubs/dependências instalados.
from importlib import import_module

# Inicia o servidor uvicorn com a aplicação FastAPI
if __name__ == "__main__":
    uvicorn = import_module("uvicorn")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8765,
        log_level="warning",
    )
