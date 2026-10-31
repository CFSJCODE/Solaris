import base64
import json
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
from app.vision.learning_retention import cleanup, remove_generated
from app.vision.learning_worker import (
    approved,
    build_dataset,
    consistent,
    digest,
    eligible_names,
    labeled_reference_images,
    provisional_class_metrics,
    supplemental_approved,
    verified_labels,
)


class LearningTests(unittest.TestCase):
    def test_suitcase_self_prediction_needs_independent_agreement(self):
        box = {"name": "suitcase", "score": 0.9, "xyxy": [0, 0, 10, 10]}
        self.assertIsNone(verified_labels([box], []))
        self.assertIsNone(verified_labels([box], [{**box, "name": "cardboard box"}]))
        verified = verified_labels([box], [box])
        assert verified is not None
        self.assertEqual(len(verified), 1)

    def test_retention_preserves_active_previous_and_recent_runs(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            identifiers = [str(i) * 32 for i in range(1, 7)]
            with learning.connect() as conn:
                for i, identifier in enumerate(identifiers):
                    conn.execute(
                        "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                        (identifier, "general", i, "rejected", "test", "hash", None, None),
                    )
                    path = learning.root() / "runs" / identifier
                    path.mkdir(parents=True)
                    (path / "artifact").write_text("test")
            learning.atomic_json(
                learning.root() / "active/general-yolo26s.json",
                {"id": identifiers[0], "previous": {"id": identifiers[1]}},
            )
            learning.atomic_json(
                learning.root() / "active/general-supplement-yolo26s.json",
                {"id": identifiers[2], "previous_supplemental": {"id": identifiers[1]}},
            )
            cleanup()
            self.assertTrue((learning.root() / "runs" / identifiers[0]).exists())
            self.assertTrue((learning.root() / "runs" / identifiers[1]).exists())
            self.assertTrue((learning.root() / "runs" / identifiers[2]).exists())
            self.assertFalse((learning.root() / "runs" / identifiers[3]).exists())
            self.assertTrue((learning.root() / "runs" / identifiers[4]).exists())
            self.assertTrue((learning.root() / "runs" / identifiers[5]).exists())
            outside = Path(folder) / "user-files"
            outside.mkdir()
            with self.assertRaises(ValueError):
                remove_generated(outside, "runs")
            self.assertTrue(outside.exists())

    def test_dataset_holds_out_whole_sessions_and_reference_replay(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            root = learning.root()
            reference = Path(folder) / "reference"
            for name in ("a", "b", "c", "d"):
                path = reference / "images/train2017" / f"{name}.jpg"
                path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(path), np.full((16, 16, 3), 100, dtype=np.uint8))
                if name != "a":
                    label = reference / "labels/train2017" / f"{name}.txt"
                    label.parent.mkdir(parents=True, exist_ok=True)
                    label.write_text("0 .5 .5 .5 .5")
            rng = np.random.default_rng(123)
            with learning.connect() as conn:
                for i in range(128):
                    path = root / "samples" / f"{i}.jpg"
                    path.parent.mkdir(exist_ok=True)
                    cv2.imwrite(str(path), rng.integers(0, 255, (16, 16, 3), dtype=np.uint8))
                    labels = json.dumps([{"name": "person", "xyxy": [1, 1, 10, 10]}])
                    conn.execute(
                        "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            digest(path),
                            "project-1",
                            ["z", "m", "a"][i // 43],
                            (i // 43) * 200 + i % 43,
                            str(i),
                            str(path.relative_to(root)),
                            path.stat().st_size,
                            "test",
                            "[]",
                            labels,
                            "labeled",
                        ),
                    )
            prepared = build_dataset(
                "project-1", "test-job", {"reference": str(reference), "reference_sha256": "test"}
            )
            self.assertIsNotNone(prepared)
            data, manifest = prepared
            train = {r["session"] for r in manifest["samples"] if r["split"] == "train"}
            val = {r["session"] for r in manifest["samples"] if r["split"] == "val"}
            self.assertFalse(train & val)
            self.assertEqual(len(manifest["samples"]), 128)
            self.assertEqual(val, {"a"})
            self.assertTrue(manifest["promotion_ready"])
            self.assertFalse((data.parent / "images/train/reference-a.jpg").exists())
            self.assertTrue((data.parent / "images/train/reference-c.jpg").exists())
            self.assertFalse((data.parent / "images/train/reference-b.jpg").exists())
            self.assertEqual(
                {image.name for image in labeled_reference_images(reference)},
                {"b.jpg", "c.jpg", "d.jpg"},
            )
            with learning.connect() as conn:
                conn.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
                    ("j", "project-1", 999, "rejected", "test", manifest["hash"], None, None),
                )
            self.assertIsNone(
                build_dataset(
                    "project-1",
                    "duplicate",
                    {"reference": str(reference), "reference_sha256": "test"},
                )
            )

    def test_single_human_new_class_is_trained_and_canonicalized(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            root = learning.root()
            reference = Path(folder) / "reference"
            for name in ("a", "b", "c", "d"):
                path = reference / "images/train2017" / f"{name}.jpg"
                path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(path), np.full((16, 16, 3), 100, dtype=np.uint8))
                if name != "a":
                    label = reference / "labels/train2017" / f"{name}.txt"
                    label.parent.mkdir(parents=True, exist_ok=True)
                    label.write_text("0 .5 .5 .5 .5")
            with learning.connect() as conn:
                for i, session in enumerate(("first", "second", "third", "fourth")):
                    path = root / "samples" / f"{i}.jpg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(path), np.full((16, 16, 3), 40 + i, dtype=np.uint8))
                    labels = [{"name": "person", "xyxy": [1, 1, 10, 10]}]
                    if i == 3:
                        labels.append(
                            {"name": "Powerbank", "xyxy": [2, 2, 12, 12], "source": "human"}
                        )
                    conn.execute(
                        "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            digest(path),
                            "general",
                            session,
                            i * 200,
                            str(i),
                            str(path.relative_to(root)),
                            path.stat().st_size,
                            "test",
                            "[]",
                            json.dumps(labels),
                            "labeled",
                        ),
                    )
            prepared = build_dataset(
                "general",
                "powerbank-job",
                {"reference": str(reference), "reference_sha256": "test"},
            )
            self.assertIsNotNone(prepared)
            data, manifest = prepared
            self.assertEqual(manifest["names"][80], "power bank")
            self.assertIsNone(manifest["validation_session"])
            self.assertEqual(manifest["provisional_human_classes"], ["power bank"])
            evidence = manifest["class_evidence"]["power bank"]
            self.assertEqual(evidence["human_train_samples"], 1)
            sample = next(item for item in manifest["samples"] if item["human_classes"])
            self.assertEqual(sample["split"], "train")
            label = data.parent / "labels" / "train" / f"{Path(sample['image']).stem}.txt"
            self.assertIn("80 ", label.read_text(encoding="utf-8"))
            self.assertTrue(manifest["hash"].startswith("yolo26x:v3:"))

            class Model:
                def val(self, data, **kwargs):
                    import yaml

                    settings = yaml.safe_load(Path(data).read_text(encoding="utf-8"))
                    self.images = Path(settings["val"]).read_text(encoding="utf-8").splitlines()
                    return type(
                        "Metrics",
                        (),
                        {"box": type("Box", (), {"ap_class_index": [80], "ap": [0.69]})()},
                    )()

            candidate = Model()
            with patch("app.vision.learning_worker.configure_cpu"):
                scores = provisional_class_metrics(candidate, manifest, data.parent)
            self.assertEqual(scores, {"power bank": 0.69})
            self.assertEqual(candidate.images, [sample["image"]])

    def test_class_only_candidate_needs_changed_weights_and_human_train_ap(self):
        manifest = {
            "provisional_human_classes": ["power bank"],
            "class_evidence": {"power bank": {"human_train_samples": 1}},
        }
        hashes = {"before": "old", "after": "new"}
        self.assertTrue(supplemental_approved(manifest, hashes, {"power bank": 0.69}))
        self.assertFalse(supplemental_approved(manifest, hashes, {"power bank": 0.49}))
        self.assertFalse(
            supplemental_approved(manifest, {"before": "old", "after": "old"}, {"power bank": 0.9})
        )
        self.assertFalse(supplemental_approved(manifest, hashes, {}))

    def test_capture_is_scoped_deduplicated_and_pause_preserves_samples(self):
        image = np.random.default_rng(42).integers(0, 255, (96, 96, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", image)
        payload = base64.b64encode(encoded).decode()
        result = {"model": "yolo26x", "detections": []}
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
            patch.object(learning, "_last", {}),
            patch.object(learning, "start_worker"),
        ):
            learning.capture(1, payload, result)
            learning.capture(2, payload, result)
            learning._last.clear()
            learning.capture(1, payload, result)
            self.assertEqual(learning.status(1)["samples"], {"pending": 1})
            self.assertEqual(learning.status(2)["samples"], {"pending": 1})
            learning.status(1, False)
            learning._last.clear()
            learning.capture(1, payload, result)
            self.assertEqual(learning.status(1)["samples"], {"pending": 1})
            self.assertEqual(len(list((Path(folder) / "learning/samples").rglob("*.jpg"))), 2)

    def test_blurry_images_are_not_collected(self):
        _, encoded = cv2.imencode(".jpg", np.full((96, 96, 3), 100, dtype=np.uint8))
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
            patch.object(learning, "_last", {}),
        ):
            learning.capture(
                None, base64.b64encode(encoded).decode(), {"model": "x", "detections": []}
            )
            self.assertEqual(learning.status(None)["samples"], {})

    def test_two_views_cannot_match_the_same_box_twice(self):
        a = {"name": "suitcase", "score": 0.9, "xyxy": [0, 0, 10, 10]}
        self.assertEqual(len(consistent([a, a], [a])), 1)
        self.assertEqual(consistent([a], [{**a, "name": "box"}]), [])

    def test_promotion_requires_reference_and_proxy_improvement(self):
        before = {"reference": 0.4, "local_proxy": 0.5, "classes": {"0": 0.6, "28": 0.5}}
        after = {"reference": 0.401, "local_proxy": 0.52, "classes": {"0": 0.59, "28": 0.51}}
        self.assertTrue(approved(before, after))
        self.assertFalse(approved(before, {**after, "reference": 0.38}))
        self.assertFalse(approved(before, {**after, "classes": {"0": 0.2, "28": 0.6}}))
        self.assertFalse(approved(before, {**after, "local_proxy": float("nan")}))
        self.assertFalse(approved(before, {**after, "local_proxy": 0.5}))

    def test_new_class_requires_diverse_sessions(self):
        rows = [{"session": "same", "labels": json.dumps([{"name": "toolbox"}])} for _ in range(30)]
        self.assertEqual(eligible_names(rows, ["person"]), ["person"])
        for i, row in enumerate(rows):
            row["session"] = str(i % 3)
        self.assertEqual(eligible_names(rows, ["person"]), ["person", "toolbox"])

    def test_adapted_labels_are_not_limited_to_coco(self):
        labels = detector.LABELS + ["caixa de ferramentas"]
        result = detector.postprocess(
            np.array([[[0, 0, 10, 10, 0.9, 80]]]), 640, 640, 1, 0, 0, labels
        )
        self.assertEqual(result[0]["label"], "caixa de ferramentas")

    def test_invalid_candidate_restores_previous_manifest(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"SOLARIS_STORAGE": folder}),
        ):
            pointer = learning.root() / "active" / "project-1.json"
            previous = {"id": "old"}
            learning.atomic_json(
                pointer,
                {
                    "scope": "project-1",
                    "onnx": str(Path(folder) / "outside.onnx"),
                    "previous": previous,
                },
            )
            _, _, _, warning = detector.selected_session(1)
            self.assertIn("referência original", warning)
            self.assertEqual(json.loads(pointer.read_text()), previous)
            self.assertEqual(len(list(pointer.parent.glob("*.failed-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
