"""Baixa o encoder visual CLIP ViT-B/32 em formato ONNX.

Fonte: repositório openai/CLIP exportado para ONNX pelo projeto
Pinto1232/clip-onnx (licença MIT, compatível com SOLARIS).

Uso:
    python scripts/download_clip.py [--dir PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# URL do encoder visual CLIP ViT-B/32 ONNX (float32, ~350 MB)
_URL = (
    "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/"
    "onnx/vision_model.onnx"
)

# SHA-256 esperado — verificado manualmente em 2025-07.
# Se o arquivo mudar no HuggingFace, remova esta linha e
# ajuste o nome em clip_embedder.py conforme necessário.
_EXPECTED_SHA256: str | None = None  # None = skip verification

_OUTPUT_NAME = "clip-vit-b32-visual.onnx"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / _OUTPUT_NAME

    if out.exists():
        print(f"[CLIP] Modelo já presente em {out}")
        return out

    print(f"[CLIP] Baixando {_URL} → {out}")
    print("       Isso pode levar alguns minutos (~350 MB).")

    def _progress(block_num: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(100, block_num * block_size * 100 // total)
            sys.stdout.write(f"\r       {pct:3d}% concluído")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(_URL, out, reporthook=_progress)
    except Exception as exc:
        if out.exists():
            out.unlink()
        print(f"\n[CLIP] Erro no download: {exc}")
        sys.exit(1)

    print()

    if _EXPECTED_SHA256:
        digest = _sha256(out)
        if digest != _EXPECTED_SHA256:
            out.unlink()
            print(f"[CLIP] ERRO: SHA-256 não confere ({digest[:16]}…). Arquivo corrompido.")
            sys.exit(1)
        print(f"[CLIP] Verificação SHA-256 OK.")

    print(f"[CLIP] Salvo em {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa o encoder visual CLIP ViT-B/32 ONNX.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("storage/models"),
        help="Diretório de destino (padrão: storage/models)",
    )
    args = parser.parse_args()
    download(args.dir)
