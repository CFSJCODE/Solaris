"""Real s/x weight updates and ONNX exports, isolated; never promotes test models."""

# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import base64
import json
import os
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-engine"))


def main():
    import cv2
    import numpy as np
    from ultralytics import YOLO

    from app.vision import learning
    from app.vision.learning_worker import digest

    config = json.loads((ROOT / "storage/learning/runtime.json").read_text(encoding="utf-8"))
    target = ROOT / "storage" / ("learning-queue-" + time.strftime("%Y%m%d-%H%M%S"))
    target.mkdir()
    os.environ["SOLARIS_STORAGE"] = str(target)
    reference = Path(config["reference"])
    images = sorted((reference / "images/train2017").glob("*.jpg"))
    subset = target / "reference"
    for image in images[:16]:
        for kind, source in [
            ("images", image),
            ("labels", reference / "labels/train2017" / image.with_suffix(".txt").name),
        ]:
            dest = subset / kind / "train2017" / source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
    config = {**config, "reference": str(subset), "reference_sha256": digest(images[0])}
    image = images[16]
    frame = cv2.imread(str(image))
    assert frame is not None, f"Imagem ilegível: {image}"
    height, width = frame.shape[:2]
    from app.vision.detector import LABELS

    boxes = []
    for row in (
        (reference / "labels/train2017" / image.with_suffix(".txt").name).read_text().splitlines()
    ):
        cls, cx, cy, w, h = map(float, row.split())
        boxes.append(
            {
                "label": LABELS[int(cls)],
                "source": "human",
                "x": max(0, (cx - w / 2) * width),
                "y": max(0, (cy - h / 2) * height),
                "width": min(w * width, width - max(0, (cx - w / 2) * width)),
                "height": min(h * height, height - max(0, (cy - h / 2) * height)),
            }
        )
    if "--new-class" in sys.argv:
        frame = np.full((128, 128, 3), 70, np.uint8)
        cv2.rectangle(frame, (20, 15), (110, 115), (180, 180, 180), -1)
        for y in (45, 75):
            cv2.line(frame, (20, y), (110, y), (30, 30, 30), 2)
        _, encoded = cv2.imencode(".jpg", frame)
        payload = {
            "image": "data:image/jpeg;base64," + base64.b64encode(encoded).decode(),
            "width": 128,
            "height": 128,
            "detections": [
                {
                    "label": "gaveteiro",
                    "source": "human",
                    "x": 20,
                    "y": 15,
                    "width": 90,
                    "height": 100,
                }
            ],
        }
    else:
        payload = {
            "image": "data:image/jpeg;base64," + base64.b64encode(image.read_bytes()).decode(),
            "width": width,
            "height": height,
            "detections": boxes,
        }
    learning.atomic_json(
        learning.root() / "runtime.json",
        {
            **config,
            "reference_files": {
                str(p.relative_to(subset)): digest(p) for p in subset.rglob("*") if p.is_file()
            },
        },
    )
    with patch.object(learning, "start_worker"):
        learning.incorporate(1, 1, payload, True)
    # Simulate a pending request interrupted during a previous application session.
    with learning.connect() as conn:
        conn.execute("UPDATE training_requests SET state='training' WHERE model='yolo26s'")
    started = time.monotonic()
    learning.start_worker()
    try:
        while time.monotonic() - started < 900:
            state = learning.status(1)
            requests = state["requests"]
            print(
                json.dumps(
                    {
                        "requests": [(r["model"], r["state"]) for r in requests],
                        "message": state["message"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if len(requests) == 2 and all(r["state"] == "evaluated" for r in requests):
                break
            if any(r["state"] in ("failed", "blocked") for r in requests):
                raise AssertionError(requests)
            time.sleep(5)
        else:
            raise TimeoutError("Fila não concluiu em 15 minutos.")
        with learning.connect() as conn:
            jobs = [dict(r) for r in conn.execute("SELECT * FROM jobs")]
        reports = [json.loads(j["metrics"]) for j in jobs]
        assert {r["model"] for r in reports} == {"yolo26s", "yolo26x"}
        assert all(
            r["weights_changed"] and r["cpu_threads"] == 1 and not r["approved"] for r in reports
        )
        if "--new-class" in sys.argv:
            for job in jobs:
                candidate = YOLO(learning.root() / "runs" / job["id"] / "candidate/weights/best.pt")
                assert len(candidate.names) == 81 and candidate.names[80] == "chest of drawers"
                del candidate
        assert not list((learning.root() / "active").glob("*.json"))
        learning.atomic_json(
            target / "results.json",
            {
                "requests": requests,
                "reports": reports,
                "restart_recovery": True,
                "activated": False,
                "synthetic_new_class": ("--new-class" in sys.argv),
            },
        )
        print("QUEUE_CYCLE_RESULT " + str(target / "results.json"), flush=True)
    finally:
        learning.status(1, False)
        learning.stop_worker()


if __name__ == "__main__":
    main()
