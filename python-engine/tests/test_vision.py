import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.vision import detector, learning


class VisionTests(unittest.TestCase):
    def test_yolo26_end_to_end_boxes_are_mapped_and_invalid_classes_rejected(self):
        output = np.array(
            [[[110, 110, 210, 210, 0.9, 5], [0, 0, 10, 10, 0.8, 999], [0, 0, 10, 10, 0.1, 0]]],
            dtype=np.float32,
        )
        boxes = detector.postprocess(output, 640, 320, 0.5, 0, 80)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0]["label"], "ônibus")
        self.assertEqual(boxes[0]["x"], 220)
        self.assertEqual(boxes[0]["y"], 60)

    def test_largest_installed_scale_then_newest_family_is_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "models").mkdir()
            for name in ["yolov8n", "yolo26l", "yolov8x", "yolo26x"]:
                (root / "models" / f"{name}.onnx").touch()
            with (
                patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
                patch.object(sys, "_MEIPASS", folder, create=True),
            ):
                self.assertEqual(detector.model_path().stem, "yolo26x")
                (root / "models/yolo26x.onnx").unlink()
                self.assertEqual(detector.model_path().stem, "yolov8x")

    def test_letterbox_mapping_and_per_class_nms(self):
        output = np.zeros((1, 84, 3), dtype=np.float32)
        output[0, :4, :] = np.array(
            [[160, 160, 160], [160, 160, 160], [100, 100, 100], [100, 100, 100]]
        )
        output[0, 4, :2] = [0.9, 0.8]
        output[0, 5, 2] = 0.85
        boxes = detector.postprocess(output, 640, 320, 0.5, 0, 80)
        self.assertEqual(len(boxes), 2)
        self.assertEqual({b["label"] for b in boxes}, {"pessoa", "bicicleta"})
        self.assertEqual(boxes[0]["x"], 220)
        self.assertEqual(boxes[0]["y"], 60)

    def test_empty_predictions_and_incompatible_export(self):
        self.assertEqual(detector.postprocess(np.zeros((1, 84, 1)), 320, 320, 1, 0, 0), [])
        with self.assertRaisesRegex(ValueError, "incompatível"):
            detector.postprocess(np.zeros((1, 6, 10)), 320, 320, 1, 0, 0)

    def test_supplemental_inference_keeps_only_new_class_predictions(self):
        boxes = [
            {
                "class_id": 0,
                "label": "pessoa",
                "confidence": 0.9,
                "x": 0,
                "y": 0,
                "width": 10,
                "height": 10,
            },
            {
                "class_id": 80,
                "label": "bateria externa",
                "confidence": 0.8,
                "x": 10,
                "y": 10,
                "width": 20,
                "height": 20,
            },
        ]
        self.assertEqual(detector.class_only_detections(boxes, [80]), [boxes[1]])

    def test_supplemental_predictions_replace_only_their_own_class(self):
        baseline = [
            {"class_id": 0, "label": "pessoa", "confidence": 0.9},
            {"class_id": 80, "label": "bateria externa", "confidence": 0.2},
        ]
        supplemental = [
            {"class_id": 0, "label": "pessoa", "confidence": 0.99},
            {"class_id": 80, "label": "bateria externa", "confidence": 0.8},
        ]
        labels = [""] * 80 + ["bateria externa"]
        result = detector.merge_supplemental_detections(baseline, supplemental, labels, [80])
        self.assertEqual(result, [baseline[0], supplemental[1]])

    def test_invalid_supplement_does_not_replace_base_session(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            pointer = learning.root() / "active" / "general-supplement-yolo26s.json"
            learning.atomic_json(
                pointer,
                {
                    "scope": "general",
                    "model": "yolo26s",
                    "onnx": str(Path(folder) / "outside.onnx"),
                    "sha256": "invalid",
                    "names_pt": detector.LABELS + ["bateria externa"],
                    "class_ids": [80],
                },
            )
            base_session = object()
            with patch.object(detector, "_session", base_session):
                result, warning = detector.supplemental_session(None, "yolo26s")
                self.assertIsNone(result)
                self.assertIn("detector principal preservado", warning)
                self.assertIs(detector._session, base_session)
            self.assertFalse(pointer.exists())
            self.assertEqual(len(list(pointer.parent.glob("*.failed-*.json"))), 1)

    def test_supplement_requires_provisional_class_only_manifest(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            root = learning.root()
            pointer = root / "active" / "general-supplement-yolo26s.json"
            learning.atomic_json(
                pointer,
                {
                    "scope": "general",
                    "model": "yolo26s",
                    "onnx": str(root / "runs" / "candidate.onnx"),
                    "sha256": "unused",
                    "names_pt": detector.LABELS + ["bateria externa"],
                    "class_ids": [80],
                },
            )
            with patch.object(detector.importlib, "import_module", return_value=object()):
                result, warning = detector.supplemental_session(None, "yolo26s")
            self.assertIsNone(result)
            self.assertIn("Catálogo de classes provisório incompatível", warning)
            self.assertFalse(pointer.exists())
            self.assertEqual(len(list(pointer.parent.glob("*.failed-*.json"))), 1)

    def test_invalid_image_does_not_load_model(self):
        with self.assertRaises(ValueError):
            detector.detect(base64.b64encode(b"not an image").decode())

    def test_missing_model_is_actionable(self):
        ok, encoded = cv2.imencode(".png", np.zeros((64, 64, 3), dtype=np.uint8))
        self.assertTrue(ok)
        with (
            patch.object(detector, "_session", None),
            patch.object(detector, "model_path", return_value=Path("missing-model.onnx")),
        ):
            with self.assertRaisesRegex(ValueError, "Modelo ausente"):
                detector.detect(base64.b64encode(encoded).decode())


if __name__ == "__main__":
    unittest.main()
