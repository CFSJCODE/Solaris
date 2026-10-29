"""Configurações centrais lidas de variáveis de ambiente / .env."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    # Banco (SQLite por padrão — zero instalação)
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'storage' / 'solaris.db'}"

    # Armazenamento local (sem MinIO — pasta simples)
    storage_dir: Path = BASE_DIR / "storage"

    # Anthropic
    anthropic_api_key: str = ""

    # OpenRouter
    openrouter_api_key: str = ""

    # Embeddings (multilingual-e5-small ONNX)
    embeddings_model_path: Path = BASE_DIR / "models" / "multilingual-e5-small.onnx"

    # Visão (YOLOv8n ONNX)
    yolo_model_path: Path = BASE_DIR / "models" / "yolov8n.onnx"
    yolo_confidence: float = 0.35

    def model_post_init(self, _context):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "models").mkdir(parents=True, exist_ok=True)


settings = Settings()
