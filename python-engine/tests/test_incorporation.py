import base64
import copy
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
from app.vision import learning
from app.vision.environment import Scene
from app.vision.learning_worker import (
    concurrent_delay,
    fail_request,
    interrupted,
    loss_value,
    merge_human,
    next_sample,
    resources,
)


class IncorporationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SOLARIS_STORAGE": self.folder.name})
        self.env.start()
        self.worker = patch.object(learning, "start_worker")
        self.worker.start()
        _, data = cv2.imencode(".png", np.zeros((64, 64, 3), np.uint8))
        self.payload = {
            "image": "data:image/png;base64," + base64.b64encode(data).decode(),
            "width": 64,
            "height": 64,
            "detections": [
                {
                    "label": "televisão",
                    "x": 1,
                    "y": 2,
                    "width": 30,
                    "height": 30,
                    "source": "human",
                },
                {"label": "mala", "x": 35, "y": 2, "width": 20, "height": 30},
            ],
        }

    def tearDown(self):
        self.worker.stop()
        self.env.stop()
        self.folder.cleanup()

    def test_concurrent_training_does_not_require_idle_or_stopped_camera(self):
        import time
        import types

        learning.status(1, True)
        with learning.connect() as conn:
            conn.execute(
                "INSERT INTO live_context(scope,latency,frames,updated) VALUES(?,?,?,?)",
                ("project-1", 250, 50, time.time()),
            )
            conn.execute(
                "UPDATE settings SET last_live=? WHERE scope=?", (time.time(), "project-1")
            )
        fake = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(available=8 * 1024**3, percent=50),
            cpu_percent=lambda **kw: 40,
        )
        with (
            patch.dict(sys.modules, {"psutil": fake}),
            patch(
                "app.vision.learning_worker.shutil.disk_usage",
                return_value=types.SimpleNamespace(free=10 * 1024**3),
            ),
        ):
            self.assertTrue(resources())
        self.assertFalse(interrupted("project-1"))
        with patch("app.vision.learning_worker.time.sleep") as sleep:
            concurrent_delay()
            self.assertGreaterEqual(sleep.call_args.args[0], 0.1)
        with learning.connect() as conn:
            conn.execute("UPDATE live_context SET latency=4000")
        self.assertTrue(interrupted("project-1"))

    def test_low_available_memory_does_not_block_training_start(self):
        import types

        fake = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(available=128 * 1024**2, percent=99),
            cpu_percent=lambda **kw: 40,
        )
        with (
            patch.dict(sys.modules, {"psutil": fake}),
            patch(
                "app.vision.learning_worker.shutil.disk_usage",
                return_value=types.SimpleNamespace(free=10 * 1024**3),
            ),
        ):
            self.assertTrue(resources())

    def test_cpu_and_disk_limits_still_block_training_start(self):
        import types

        low_disk = types.SimpleNamespace(free=8 * 1024**3)
        fake = types.SimpleNamespace(
            virtual_memory=lambda: types.SimpleNamespace(available=128 * 1024**2, percent=99),
            cpu_percent=lambda **kw: 90,
        )
        with (
            patch.dict(sys.modules, {"psutil": fake}),
            patch(
                "app.vision.learning_worker.shutil.disk_usage",
                return_value=types.SimpleNamespace(free=10 * 1024**3),
            ),
        ):
            self.assertFalse(resources())
        fake.cpu_percent = lambda **kw: 40
        with (
            patch.dict(sys.modules, {"psutil": fake}),
            patch(
                "app.vision.learning_worker.shutil.disk_usage",
                return_value=low_disk,
            ),
        ):
            self.assertFalse(resources())

    def test_loss_components_support_dictionary_and_reject_nonfinite(self):
        self.assertEqual(loss_value({"box": 2, "class": 3}), 5)
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                loss_value({"box": value})

    def test_partial_does_not_confirm_suggestions_and_requests_both_models(self):
        first = learning.incorporate(1, 42, self.payload)
        with learning.connect() as conn:
            row = conn.execute("SELECT * FROM human_reviews").fetchone()
            self.assertEqual(json.loads(row["labels"])[0]["name"], "tv")
            self.assertEqual(len(json.loads(row["labels"])), 1)
            self.assertIsNone(conn.execute("SELECT labels FROM samples").fetchone()[0])
            requests = conn.execute("SELECT model,state FROM training_requests").fetchall()
            self.assertEqual({r["model"] for r in requests}, {"yolo26s"})
        second = learning.incorporate(1, 42, self.payload)
        self.assertEqual(first["request_ids"], second["request_ids"])
        self.assertEqual(learning.status(2)["requests"], [])

    def test_edit_during_training_creates_new_requests_without_losing_previous_work(self):
        first = learning.incorporate(1, 1, self.payload, True)
        with learning.connect() as conn:
            conn.execute("UPDATE training_requests SET state='training'")
        self.payload["detections"][0]["label"] = "gaveteiro"
        second = learning.incorporate(1, 2, self.payload, True)
        self.assertFalse(set(first["request_ids"]) & set(second["request_ids"]))
        with learning.connect() as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM training_requests").fetchone()[0], 2
            )

    def test_pending_context_requests_are_reused_and_duplicates_coalesced(self):
        first = learning.request_training(None)
        with learning.connect() as conn:
            conn.execute(
                "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample",
                    "general",
                    "session",
                    1,
                    "signature",
                    "samples/general/sample.jpg",
                    1,
                    "test",
                    "[]",
                    "[]",
                    "labeled",
                ),
            )
        second = learning.request_training(None)
        self.assertEqual(first["request_ids"], second["request_ids"])
        with learning.connect() as conn:
            for model in ("yolo26s",):
                conn.execute(
                    "INSERT INTO training_requests(id,scope,model,created,state,message,sample_id,job_id,source_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        "duplicate-" + model,
                        "general",
                        model,
                        2,
                        "queued",
                        "duplicate",
                        None,
                        None,
                        "duplicate-hash",
                    ),
                )
            learning.coalesce_training_requests(conn, "general")
            states = conn.execute(
                "SELECT model,state FROM training_requests ORDER BY model,created"
            ).fetchall()
        self.assertEqual(sum(row["state"] == "queued" for row in states), 1)
        self.assertEqual(sum(row["state"] == "superseded" for row in states), 1)

    def test_labeled_sample_requests_are_grouped_into_one_model_cycle(self):
        with learning.connect() as conn:
            for sample_id in ("sample-a", "sample-b"):
                conn.execute(
                    "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        sample_id,
                        "general",
                        "session",
                        1,
                        sample_id,
                        "samples/general/" + sample_id + ".jpg",
                        1,
                        "test",
                        "[]",
                        "[]",
                        "labeled",
                    ),
                )
            for model in ("yolo26s",):
                for index, sample_id in enumerate(("sample-a", "sample-a", "sample-b")):
                    conn.execute(
                        "INSERT INTO training_requests(id,scope,model,created,state,message,sample_id,job_id,source_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            f"{model}-{index}",
                            "general",
                            model,
                            index,
                            "queued",
                            "duplicate",
                            sample_id,
                            None,
                            f"hash-{index}",
                        ),
                    )
            learning.coalesce_training_requests(conn, "general")
            rows = conn.execute(
                "SELECT id,model,state,sample_id FROM training_requests ORDER BY model,created"
            ).fetchall()
        for model in ("yolo26s",):
            pending = [row for row in rows if row["model"] == model and row["state"] == "queued"]
            grouped = [
                row for row in rows if row["model"] == model and row["state"] == "superseded"
            ]
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["id"], f"{model}-2")
            self.assertIsNone(pending[0]["sample_id"])
            self.assertEqual(len(grouped), 2)

    def test_repeated_pending_review_requests_are_verified_only_once(self):
        with learning.connect() as conn:
            conn.execute(
                "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample-pending",
                    "general",
                    "session",
                    1,
                    "pending-signature",
                    "samples/general/pending.jpg",
                    1,
                    "test",
                    "[]",
                    None,
                    "pending",
                ),
            )
            for index in range(3):
                conn.execute(
                    "INSERT INTO training_requests(id,scope,model,created,state,message,sample_id,job_id,source_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        f"pending-{index}",
                        "general",
                        "yolo26x",
                        index,
                        "queued",
                        "duplicate",
                        "sample-pending",
                        None,
                        f"hash-{index}",
                    ),
                )
            learning.coalesce_training_requests(conn, "general")
            rows = conn.execute(
                "SELECT state FROM training_requests WHERE model=? ORDER BY created", ("yolo26x",)
            ).fetchall()
        self.assertEqual(sum(row["state"] == "queued" for row in rows), 1)
        self.assertEqual(sum(row["state"] == "superseded" for row in rows), 2)

    def test_failed_training_request_shows_diagnostic_instead_of_staying_queued(self):
        receipt = learning.request_training(None)
        fail_request(
            "general", receipt["request_ids"][0], FileNotFoundError("missing reference annotation")
        )
        with learning.connect() as conn:
            row = conn.execute(
                "SELECT state,message FROM training_requests WHERE id=?",
                (receipt["request_ids"][0],),
            ).fetchone()
        self.assertEqual(row["state"], "failed")
        self.assertIn("missing reference annotation", row["message"])

    def test_explicit_training_preempts_unrelated_pending_scans(self):
        with learning.connect() as conn:
            for sample_id in ("older-scan", "reviewed-frame"):
                conn.execute(
                    "INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        sample_id,
                        "general",
                        "session",
                        1,
                        sample_id,
                        "samples/general/" + sample_id + ".jpg",
                        1,
                        "test",
                        "[]",
                        None,
                        "pending",
                    ),
                )
            self.assertIsNone(next_sample(conn, "general", {"sample_id": None}))
            selected = next_sample(conn, "general", {"sample_id": "reviewed-frame"})
        assert selected is not None
        self.assertEqual(selected["id"], "reviewed-frame")

    def test_complete_review_confirms_all_boxes_and_changed_labels_invalidate_dataset(self):
        learning.incorporate(None, 1, self.payload, True)
        with learning.connect() as conn:
            row = conn.execute("SELECT state,labels FROM samples").fetchone()
            self.assertEqual(row["state"], "labeled")
            self.assertEqual(len(json.loads(row["labels"])), 2)
        self.payload["detections"][0]["label"] = "gaveteiro"
        learning.incorporate(None, 2, self.payload, True)
        with learning.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM samples").fetchone()[0], 1)
            self.assertEqual(
                json.loads(conn.execute("SELECT labels FROM samples").fetchone()[0])[0]["name"],
                "chest of drawers",
            )

    def test_validation_rejects_nonfinite_outside_and_unconfirmed_boxes(self):
        for value in (float("nan"), float("inf"), -1, 65):
            payload = copy.deepcopy(self.payload)
            payload["detections"][0]["x"] = value
            with self.assertRaises(ValueError):
                learning.incorporate(None, 1, payload)
        self.payload["detections"] = self.payload["detections"][1:]
        with self.assertRaises(ValueError):
            learning.incorporate(None, 1, self.payload)
        with self.assertRaises(ValueError):
            learning.request_training(2, "not-owned")
        with learning.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM samples").fetchone()[0], 0)

    def test_new_portuguese_object_names_are_canonicalized_for_training(self):
        labels = ("caixa de som", "powerbank", "armários", "janela", "porta", "multímetro")
        self.payload["detections"] = [
            {
                "label": label,
                "x": index * 9.0,
                "y": 30.0,
                "width": 7.0,
                "height": 7.0,
                "source": "human",
            }
            for index, label in enumerate(labels)
        ]
        learning.incorporate(1, 43, self.payload)
        with learning.connect() as conn:
            row = conn.execute(
                "SELECT labels FROM human_reviews WHERE scope=?", ("project-1",)
            ).fetchone()
        self.assertEqual(
            [box["name"] for box in json.loads(row["labels"])],
            ["speaker", "power bank", "cabinet", "window", "door", "multimeter"],
        )

    def test_partial_human_override_requires_teacher_and_preserves_other_verified_objects(self):
        human = [{"name": "gaveteiro", "xyxy": [0, 0, 20, 20], "source": "human"}]
        self.assertIsNone(merge_human(None, human))
        auto = [
            {"name": "suitcase", "xyxy": [0, 0, 20, 20]},
            {"name": "tv", "xyxy": [40, 0, 60, 20]},
        ]
        merged = merge_human(auto, human)
        assert merged is not None
        self.assertEqual([b["name"] for b in merged], ["tv", "gaveteiro"])

    def test_context_does_not_modify_detection_or_hallucinate_and_expires(self):
        scene = Scene(Path(self.folder.name) / "scene.json")
        box = {
            "class_id": 59,
            "label": "cama",
            "confidence": 0.8,
            "x": 0.0,
            "y": 0.0,
            "width": 40.0,
            "height": 30.0,
        }
        frame = {"width": 64, "height": 64, "detections": [box]}
        result: dict = {}
        for i in range(8):
            result = scene.observe(copy.deepcopy(frame), 100 + i)
        self.assertEqual(result["environment"]["context"]["hypothesis"], "quarto")
        self.assertIn("wardrobe", result["environment"]["context"]["queries"])
        self.assertEqual(len(result["detections"]), 1)
        self.assertEqual(result["detections"][0]["confidence"], 0.8)
        self.assertEqual(
            scene.observe({"width": 64, "height": 64, "detections": []}, 200)["environment"][
                "context"
            ]["hypothesis"],
            "desconhecido",
        )

    def test_scene_only_sends_queries_to_same_project(self):
        _, data = cv2.imencode(
            ".jpg", np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8)
        )
        with patch.object(learning, "_last", {}):
            learning.capture(
                1,
                base64.b64encode(data).decode(),
                {
                    "model": "s",
                    "detections": [],
                    "elapsed_ms": 100,
                    "environment": {"context": {"hypothesis": "quarto", "queries": ["wardrobe"]}},
                },
            )
        with learning.connect() as conn:
            row = conn.execute(
                "SELECT scene FROM live_context WHERE scope=?", ("project-1",)
            ).fetchone()
            self.assertEqual(json.loads(row[0])["queries"], ["wardrobe"])
            self.assertIsNone(
                conn.execute(
                    "SELECT scene FROM live_context WHERE scope=?", ("project-2",)
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
