"""
YOLOv8n object detection via ultralytics.
Captures one frame from webcam, runs inference, returns detections as JSON.
CPU-only — no GPU required.
"""
from __future__ import annotations

import base64
import io
from typing import Any

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        _model = YOLO("yolov8n.pt")  # downloads ~6 MB on first use
    return _model


def detect_frame(source: int = 0, conf: float = 0.35) -> dict[str, Any]:
    """
    Capture one frame from the webcam, run YOLOv8n inference.
    Returns {"jpeg_b64": str, "detections": [{"label":str,"conf":float,"box":[x1,y1,x2,y2]}]}.
    """
    import cv2
    import numpy as np

    model = _get_model()

    cap = cv2.VideoCapture(source, cv2.CAP_DSHOW if _is_windows() else cv2.CAP_ANY)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        raise RuntimeError("Não foi possível capturar frame da webcam.")

    results = model(frame, conf=conf, verbose=False)[0]

    detections: list[dict] = []
    for box in results.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        label = results.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        detections.append({
            "label": label,
            "conf": round(confidence, 3),
            "box": [round(x1), round(y1), round(x2), round(y2)],
        })

    # Annotate frame
    annotated = results.plot()

    # Encode as JPEG → base64
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
    jpeg_b64 = base64.b64encode(buf.tobytes()).decode()

    return {"jpeg_b64": jpeg_b64, "detections": detections}


def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"
