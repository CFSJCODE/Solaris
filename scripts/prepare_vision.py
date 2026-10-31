"""Fetch the pinned model used in local builds and verify its checksum."""

from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

REVISION = "66e5888954d3454da709847e77b36df31f756aa9"
URL = f"https://huggingface.co/unileon-robotics/YOLO8-ONNX/resolve/{REVISION}/dynamic/yolov8n.onnx"
SHA256 = "01d7aa04e4f6a21784ec5dee4b8377d4bd83bec2b85078c99815ec3d3093d49e"


MODELS = [
    ("yolov8n.onnx", URL, SHA256),
    (
        "yolo26x.onnx",
        "https://huggingface.co/prithivMLmods/YOLO26-ONNX/resolve/c526dae7a5a5b4f1d79d704903b4406011da2716/yolo26x/yolo26x.onnx",
        "a879d5b533db9291eeb8ba332f1ef2b7a8f3a10003f35baa1dbdf3be872a3e6f",
    ),
]


def main():
    root = Path(__file__).resolve().parents[1] / "storage/models"
    root.mkdir(parents=True, exist_ok=True)
    for name, url, expected in MODELS:
        target = root / name
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"Outro modelo encontrado: {name}. Arquivo preservado.")
            print(f"{name}: checksum verificado.")
            continue
        temporary = target.with_suffix(".download")
        digest = sha256()
        with urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError(f"Checksum divergente: {name}. Modelo não ativado.")
        temporary.rename(target)
        print(f"{name}: pronto para o build.")


if __name__ == "__main__":
    main()
