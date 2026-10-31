"""Instala o CLIP ViT-B/32 (revisão fixa) para a descoberta visual auto-supervisionada.

Execute no runtime de aprendizado do SOLARIS (onde torch/transformers existem):

    %APPDATA%\\com.cfsjcode.solaris\\storage\\learning-runtime\\Scripts\\python scripts\\setup_clip.py

Baixa só os arquivos necessários para PyTorch, verifica o carregamento e registra caminho,
revisão e SHA-256 em learning/runtime.json. Sem credenciais; nada é enviado.
"""

# torch/transformers/huggingface_hub existem só no runtime de aprendizado separado.
# pyright: reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = "openai/clip-vit-base-patch32"
REVISION = "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268"
FILES = [
    "config.json",
    "preprocessor_config.json",
    "pytorch_model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "special_tokens_map.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    storage = Path(
        os.environ.get("SOLARIS_STORAGE")
        or Path(os.environ["APPDATA"]) / "com.cfsjcode.solaris" / "storage"
    )
    learning = storage / "learning"
    runtime_file = learning / "runtime.json"
    if not runtime_file.is_file():
        sys.exit(f"Runtime de aprendizado não encontrado: {runtime_file}")
    target = learning / "assets" / "clip-vit-base-patch32"

    from huggingface_hub import hf_hub_download

    for name in FILES:
        hf_hub_download(REPO, name, revision=REVISION, local_dir=target)
        print(f"ok {name}")

    import torch
    from transformers import CLIPModel, CLIPProcessor

    CLIPProcessor.from_pretrained(target, local_files_only=True)
    model = CLIPModel.from_pretrained(target, local_files_only=True).eval()
    with torch.inference_mode():
        features = model.get_image_features(pixel_values=torch.zeros(1, 3, 224, 224))
    if tuple(features.shape) != (1, 512) or not torch.isfinite(features).all():
        sys.exit("CLIP carregado, mas a saída é incompatível; runtime.json não alterado.")

    config = json.loads(runtime_file.read_text(encoding="utf-8"))
    config.update(
        clip=str(target),
        clip_revision=REVISION,
        clip_sha256=sha256(target / "pytorch_model.bin"),
    )
    temporary = runtime_file.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, runtime_file)
    print(f"CLIP pronto em {target}; registrado em runtime.json.")


if __name__ == "__main__":
    main()
