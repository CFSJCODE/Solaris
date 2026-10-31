"""Exporta yolov8n-oiv7 (Open Images V7, 601 classes) para ONNX FP32.

Execute no ambiente de aprendizado do SOLARIS (onde ultralytics está disponível):

    python-engine\\.venv-learning\\Scripts\\python scripts\\export_oiv7.py

O arquivo ONNX e o sidecar de rótulos são salvos em storage\\models\\.
"""

import json
import sys
from pathlib import Path

# --- configuração ----------------------------------------------------------
MODEL_NAME = "yolov8n-oiv7"
IMGSZ = 640
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "storage" / "models"
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "ultralytics não encontrado. Execute este script no ambiente de aprendizado:\n"
            r"  python-engine\.venv-learning\Scripts\python scripts\export_oiv7.py",
            file=sys.stderr,
        )
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = OUTPUT_DIR / f"{MODEL_NAME}.onnx"
    labels_path = OUTPUT_DIR / f"{MODEL_NAME}.labels.json"

    if onnx_path.exists():
        print(f"ONNX já existe: {onnx_path}")
    else:
        print(f"Baixando e exportando {MODEL_NAME} → ONNX FP32 (imgsz={IMGSZ})…")
        model = YOLO(f"{MODEL_NAME}.pt")
        exported = model.export(format="onnx", imgsz=IMGSZ, dynamic=False, simplify=True)
        src = Path(exported)
        src.rename(onnx_path)
        print(f"ONNX salvo em: {onnx_path}")

    # Extrai rótulos em português usando TRADUCOES do SOLARIS
    if not labels_path.exists():
        print("Gerando sidecar de rótulos…")
        try:
            from ultralytics import YOLO as _YOLO

            model = _YOLO(f"{MODEL_NAME}.pt")
            names_en: list[str] = [model.names[i] for i in range(len(model.names))]
        except Exception as exc:
            print(f"Não foi possível extrair nomes do modelo: {exc}", file=sys.stderr)
            sys.exit(1)

        # Traduz usando o dicionário completo do SOLARIS (oiv7_labels_pt.py)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-engine"))
        try:
            from app.vision.oiv7_labels_pt import TRADUCOES  # noqa: PLC0415

            def _translate(name: str) -> str:
                return TRADUCOES.get(name.lower(), name)

        except Exception:

            def _translate(name: str) -> str:  # type: ignore[misc]
                return name

        labels_pt = [_translate(n) for n in names_en]
        labels_path.write_text(json.dumps(labels_pt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rótulos salvos em: {labels_path}")
        print(f"Total de classes: {len(labels_pt)}")

        # Mostra as classes relevantes para o SOLARIS
        relevant = ["door", "window", "cabinet", "shelf", "lamp", "chair", "table", "person"]
        print("\nClasses relevantes encontradas:")
        for i, name in enumerate(names_en):
            if any(r in name.lower() for r in relevant):
                print(f"  [{i:3d}] {name} → {labels_pt[i]}")
    else:
        print(f"Sidecar de rótulos já existe: {labels_path}")

    print("\nConcluído. Reinicie o SOLARIS para carregar o novo detector.")
    print(f"O modelo OIV7 ({MODEL_NAME}) atuará como detector suplementar (YOLO26 é o primário).")


if __name__ == "__main__":
    main()
