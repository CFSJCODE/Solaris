"""Exercise the real pipe engine/worker lifecycle in isolated application storage."""

# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    import psutil

    installed = Path(os.environ["APPDATA"]) / "com.cfsjcode.solaris/storage"
    config = json.loads((installed / "learning/runtime.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="solaris-learning-") as folder:
        target = Path(folder)
        (target / "learning").mkdir()
        (target / "models").mkdir()
        (target / "learning/runtime.json").write_text(json.dumps(config), encoding="utf-8")
        shutil.copyfile(installed / "learning/live.json", target / "learning/live.json")
        for name in ("yolo26n", "yolo26s"):
            shutil.copyfile(
                installed / "models" / f"{name}.onnx", target / "models" / f"{name}.onnx"
            )
        shutil.copyfile(ROOT / "storage/models/yolo26x.onnx", target / "models/yolo26x.onnx")
        command = (
            [sys.argv[1]]
            if len(sys.argv) > 1
            else [
                str(ROOT / "python-engine/.venv/Scripts/python.exe"),
                str(ROOT / "python-engine/app/main.py"),
            ]
        )
        environment = {**os.environ, "SOLARIS_STORAGE": str(target), "PYTHONUTF8": "1"}
        log = (target / "engine-errors.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdin is not None and process.stdout is not None
        stdin, stdout = process.stdin, process.stdout

        def request(value):
            stdin.write(json.dumps({"id": "test", **value}) + "\n")
            stdin.flush()
            response = json.loads(stdout.readline())
            if response.get("type") == "error":
                raise RuntimeError(response.get("message"))
            return response

        children = None
        try:
            state = request({"type": "learning_status"})
            assert state["runtime_ready"] and state["worker_running"], state
            health = {}
            for _ in range(30):
                health = request({"type": "health"})
                if health["vision"]["loaded"]:
                    break
                time.sleep(1)
            assert health["vision"]["model"] == "yolo26x" and health["vision"]["loaded"], health
            image = sorted((Path(config["reference"]) / "images/train2017").glob("*.jpg"))[0]
            result = request(
                {
                    "type": "vision_detect",
                    "adapt": True,
                    "content_b64": base64.b64encode(image.read_bytes()).decode(),
                }
            )
            assert result["model"] == "yolo26s", result["model"]
            assert all(
                d["label"] not in ("person", "suitcase", "bus") for d in result["detections"]
            )
            status = request({"type": "learning_status"})
            assert sum(status["samples"].values()) == 1, status
            revision = {
                "image": "data:image/jpeg;base64," + base64.b64encode(image.read_bytes()).decode(),
                "width": result["width"],
                "height": result["height"],
                "detections": [{**result["detections"][0], "source": "human"}],
            }
            receipt = request(
                {
                    "type": "learning_incorporate",
                    "revision_id": 1,
                    "payload": revision,
                    "complete": False,
                }
            )
            assert receipt["incorporated"] == 1 and len(receipt["request_ids"]) == 2, receipt
            queued = request({"type": "learning_status"})
            assert {r["model"] for r in queued["requests"]} == {"yolo26s", "yolo26x"}, queued
            paused = request({"type": "learning_status", "enabled": False})
            assert paused["enabled"] == 0
            children = psutil.Process(process.pid).children(recursive=True)
            reserved = status.get("learning_cpu")
            if reserved is not None:
                engines = [
                    p
                    for p in [psutil.Process(process.pid), *children]
                    if "solaris-engine" in p.name().lower()
                ]
                if engines:
                    assert any(reserved not in p.cpu_affinity() for p in engines)
                learners = [p for p in children if "learning_worker.py" in " ".join(p.cmdline())]
                assert learners and all(p.cpu_affinity() == [reserved] for p in learners), [
                    (p.pid, p.cpu_affinity()) for p in learners
                ]
            print(
                json.dumps(
                    {
                        "preloaded": health["vision"]["model"],
                        "live_detector": result["model"],
                        "detections": len(result["detections"]),
                        "collected": sum(status["samples"].values()),
                        "worker_running": status["worker_running"],
                        "pause_verified": True,
                        "incorporation_and_both_requests_verified": True,
                        "scene_context_present": "context" in result.get("environment", {}),
                        "concurrent": status.get("concurrent"),
                        "reserved_learning_cpu": reserved,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            process.stdin.close()
            process.wait(timeout=20)
            log.close()
            if children is not None:
                _, alive = psutil.wait_procs(children, timeout=10)
                assert not [p for p in alive if p.is_running()], (
                    "Processo de aprendizado permaneceu órfão."
                )


if __name__ == "__main__":
    main()
