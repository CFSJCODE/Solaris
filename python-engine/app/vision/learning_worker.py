"""CPU learning service. Launched by the engine, never writes to its stdout pipe."""
# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false

# Importa as bibliotecas necessárias
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path para permitir imports relativos
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.vision import learning as store
from app.vision.object_vocabulary import EXTRA as OBJECT_EXTRA

# Explicit vocabulary seeds, not claims that arbitrary objects can name themselves.
EXTRA = [
    ("toolbox", "caixa de ferramentas"),
    ("safety helmet", "capacete de segurança"),
    ("suitcase with wheels", "mala com rodas"),
    ("cardboard box", "caixa de papelão"),
    ("electric drill", "furadeira"),
    ("screwdriver", "chave de fenda"),
    ("pliers", "alicate"),
    ("monitor", "monitor"),
    ("desk", "escrivaninha"),
    ("wardrobe", "guarda-roupa"),
    ("chest of drawers", "gaveteiro"),
    ("nightstand", "mesa de cabeceira"),
    ("power strip", "filtro de linha"),
    ("headphones", "fone de ouvido"),
    ("water dispenser", "bebedouro"),
    *OBJECT_EXTRA,
]


# Função para calcular o hash SHA-256 de um arquivo, lendo-o em blocos de 1 MB
def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# Função para verificar se há recursos suficientes disponíveis, incluindo memória, CPU e espaço em disco
def reference_label(reference, image):
    return Path(reference) / "labels" / "train2017" / Path(image).with_suffix(".txt").name


# Função para verificar se há recursos suficientes disponíveis, incluindo memória, CPU e espaço em disco
def labeled_reference_images(reference, images=None):
    candidates = (
        sorted((Path(reference) / "images" / "train2017").glob("*.jpg"))
        if images is None
        else images
    )
    return [image for image in candidates if reference_label(reference, image).is_file()]


# Função para configurar o uso da CPU, limitando o número de threads para evitar sobrecarga
def configure_cpu():
    import torch
    import ultralytics.utils.torch_utils as torch_utils

    # select_device() otherwise resets the caller's thread limit to Ultralytics' default.
    torch_utils.NUM_THREADS = 1
    torch.set_num_threads(1)


# Função para calcular o hash de um modelo treinável, considerando apenas os parâmetros que requerem gradiente
def trainable_digest(model):
    h = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            h.update(name.encode())
            h.update(parameter.detach().cpu().float().numpy().tobytes())
    return h.hexdigest()


# Função para calcular o valor da perda, lidando com diferentes tipos de entrada e verificando se o valor é finito
def loss_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        values = [loss_value(v) for v in value.values()]
        return sum(v for v in values if v is not None)
    if hasattr(value, "detach"):
        value = value.detach().sum().cpu()
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Perda não finita; candidata recusada.")
    return result


# Função para calcular a interseção sobre união (IoU) entre duas caixas delimitadoras, retornando o valor da IoU
def resources(immediate=False):
    import psutil

    return (
        psutil.cpu_percent(interval=0.2) < 85 and shutil.disk_usage(store.root()).free > 8 * 1024**3
    )


# Função para verificar se o processo de aprendizado foi interrompido, consultando o banco de dados para determinar se a chave está habilitada e se há condições críticas que exigem interrupção
def interrupted(key, immediate=False):
    with store.connect() as conn:
        row = conn.execute("SELECT enabled FROM settings WHERE scope=?", (key,)).fetchone()
        critical = conn.execute(
            "SELECT 1 FROM live_context WHERE updated>? AND frames>=5 AND latency>3000 LIMIT 1",
            (time.time() - 10,),
        ).fetchone()
    return row is None or not row["enabled"] or critical is not None


# Função para verificar se o processo de aprendizado foi interrompido, consultando o banco de dados para determinar se a chave está habilitada e se há condições críticas que exigem interrupção
def fail_request(key, request_id, exc):
    if not request_id:
        return
    message = f"Falha ao preparar ou executar o treino: {type(exc).__name__}: {str(exc)[:180]}"
    with store.connect() as conn:
        changed = conn.execute(
            "UPDATE training_requests SET state='failed',message=? WHERE id=? AND scope=? "
            "AND state IN ('queued','preparing','verifying','training','paused')",
            (message, request_id, key),
        ).rowcount
        if changed:
            store.event(conn, key, message)


# Função para verificar se o processo de aprendizado foi interrompido, consultando o banco de dados para determinar se a chave está habilitada e se há condições críticas que exigem interrupção
def next_sample(conn, key, request):
    if request:
        if not request["sample_id"]:
            return None
        return conn.execute(
            "SELECT * FROM samples WHERE scope=? AND id=? AND state='pending'",
            (key, request["sample_id"]),
        ).fetchone()
    return conn.execute(
        "SELECT s.* FROM samples s WHERE scope=? AND state='pending' "
        "ORDER BY EXISTS(SELECT 1 FROM human_reviews h WHERE h.scope=s.scope AND h.sample_id=s.id) DESC,created LIMIT 1",
        (key,),
    ).fetchone()


# Função para introduzir um atraso entre lotes de processamento, permitindo que a câmera ou a entrada do usuário continuem sem interrupção
def concurrent_delay():
    # Yield between batches rather than requiring the camera or user input to stop.
    with store.connect() as conn:
        latency = conn.execute(
            "SELECT max(latency) FROM live_context WHERE updated>?", (time.time() - 10,)
        ).fetchone()[0]
    if latency is not None:
        time.sleep(min(1.0, max(0.1, (latency - 200) / 600)))


# Função para calcular a interseção sobre união (IoU) entre duas caixas delimitadoras, retornando o valor da IoU
def iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap / max(
        1e-9, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    )


# Função para verificar se duas listas de caixas delimitadoras são consistentes, comparando-as com base na IoU e mantendo apenas as caixas que atendem a um determinado limiar
def consistent(first, second, threshold=0.65):
    """Two-view agreement is a label filter, never an independent accuracy metric."""
    used = set()
    kept = []
    for a in first:
        matches = [
            (i, iou(a["xyxy"], b["xyxy"]))
            for i, b in enumerate(second)
            if i not in used and a["name"] == b["name"]
        ]
        idx, score = max(matches, key=lambda x: x[1], default=(-1, 0))
        if score >= threshold:
            used.add(idx)
            kept.append({**a, "score": min(a["score"], second[idx]["score"])})
    return kept


# Função para verificar se duas listas de caixas delimitadoras são consistentes, comparando-as com base na IoU e mantendo apenas as caixas que atendem a um determinado limiar
def verified_labels(stable, owl):
    # For bags, two views of the same YOLO error are not enough evidence.
    for box in stable:
        if box["name"] in ("suitcase", "handbag", "backpack") and not any(
            other["name"] == box["name"] and iou(box["xyxy"], other["xyxy"]) >= 0.5 for other in owl
        ):
            return None
    result = list(stable)
    for candidate in owl:
        if all(iou(candidate["xyxy"], b["xyxy"]) < 0.5 for b in result):
            result.append(candidate)
    return result if result else None


# Função para mesclar caixas delimitadoras automáticas e humanas, mantendo apenas as caixas automáticas que não se sobrepõem significativamente com as caixas humanas
def merge_human(automatic, human):
    if automatic is None:
        return None
    kept = [box for box in automatic if not any(iou(box["xyxy"], h["xyxy"]) >= 0.3 for h in human)]
    return kept + human


# Função para verificar se duas listas de caixas delimitadoras são consistentes, comparando-as com base na IoU e mantendo apenas as caixas que atendem a um determinado limiar
class Teachers:
    def __init__(self, config):
        from ultralytics import YOLO

        configure_cpu()
        self.yolo = YOLO(config["checkpoint"])
        self.config = config
        self.owl = None
        self.processor = None
        self.trackers = {}

    # Função para detectar caixas delimitadoras usando o modelo YOLO, retornando as caixas detectadas e os resultados da predição
    def yolo_boxes(self, image, flip=False):
        results = self.yolo.predict(image, device="cpu", imgsz=640, conf=0.35, verbose=False)[0]
        width = image.shape[1]
        boxes = []
        for xyxy, cls, confidence in zip(
            results.boxes.xyxy.tolist(), results.boxes.cls.tolist(), results.boxes.conf.tolist()
        ):
            if flip:
                xyxy = [width - xyxy[2], xyxy[1], width - xyxy[0], xyxy[3]]
            boxes.append(
                {
                    "name": results.names[int(cls)],
                    "score": confidence,
                    "xyxy": xyxy,
                    "source": "yolo26x_two_views",
                }
            )
        return boxes, results

    # Função para rotular uma imagem, combinando as caixas detectadas pelo YOLO e pelo OWL, verificando a consistência entre as duas visões e retornando as caixas finais com informações adicionais sobre o rastreamento
    def label(self, image, key, extra_names=()):
        from types import SimpleNamespace

        import cv2
        from ultralytics.trackers.byte_tracker import BYTETracker

        first, raw = self.yolo_boxes(image)
        second, _ = self.yolo_boxes(cv2.flip(image, 1), True)
        # Compare ByteTrack continuity on chronological selected observations.
        tracker = self.trackers.setdefault(
            key,
            BYTETracker(
                SimpleNamespace(
                    track_high_thresh=0.5,
                    track_low_thresh=0.1,
                    new_track_thresh=0.6,
                    track_buffer=30,
                    match_thresh=0.8,
                    fuse_score=True,
                )
            ),
        )
        tracked = tracker.update(raw.boxes.cpu().numpy(), image)
        stable = consistent(first, second)
        for box in stable:
            box["tracker"] = "ByteTrack"
            box["tracked"] = any(iou(box["xyxy"], t[:4]) > 0.5 for t in tracked)
        # Disagreement can indicate missing objects: don't teach them as background.
        if len(stable) != len(first) or len(stable) != len(second):
            return None
        vocabulary = list(
            dict.fromkeys(
                ["suitcase", "handbag", "backpack"]
                + list(extra_names)[:24]
                + [name for name, _ in EXTRA]
                + [b["name"] for b in stable]
            )
        )[:80]
        extra = self.owl_boxes(image, names=vocabulary)
        extra_flip = self.owl_boxes(cv2.flip(image, 1), True, names=vocabulary)
        extra = consistent(extra, extra_flip, 0.5)
        return verified_labels(stable, extra)

    # Função para detectar caixas delimitadoras usando o modelo OWL, retornando as caixas detectadas com base em consultas de texto e a imagem fornecida
    def owl_boxes(self, image, flip=False, names=None):
        import torch
        from PIL import Image
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        if self.owl is None:
            self.processor = Owlv2Processor.from_pretrained(
                self.config["owl"], local_files_only=True
            )
            self.owl = Owlv2ForObjectDetection.from_pretrained(
                self.config["owl"], local_files_only=True
            ).eval()
        processor, owl = self.processor, self.owl
        assert processor is not None and owl is not None
        names = names or [name for name, _ in EXTRA]
        queries = [[f"a photo of a {name}" for name in names]]
        inputs = processor(
            text=queries, images=Image.fromarray(image[:, :, ::-1]), return_tensors="pt"
        )
        with torch.inference_mode():
            output = owl(**inputs)
        detected = processor.post_process_object_detection(
            output, target_sizes=torch.tensor([image.shape[:2]]), threshold=0.25
        )[0]
        result = []
        width = image.shape[1]
        for box, index, score in zip(
            detected["boxes"].tolist(), detected["labels"].tolist(), detected["scores"].tolist()
        ):
            if flip:
                box = [width - box[2], box[1], width - box[0], box[3]]
            result.append(
                {"name": names[index], "score": score, "xyxy": box, "source": "owlv2_two_views"}
            )
        return result[:50]


# Função para calcular a interseção sobre união (IoU) entre duas caixas delimitadoras, retornando o valor da IoU
def eligible_names(rows, base_names):
    evidence = {}
    for row in rows:
        for name in {b["name"] for b in json.loads(row["labels"])}:
            counts, sessions = evidence.setdefault(name, [0, set()])
            evidence[name][0] = counts + 1
            sessions.add(row["session"])
    return base_names + [
        name
        for name, _ in EXTRA
        if name not in base_names
        and evidence.get(name, [0, set()])[0] >= 20
        and len(evidence.get(name, [0, set()])[1]) >= 3
    ]


def canonical_dataset_name(name, existing_names):
    from app.vision.object_vocabulary import canonical_object_name

    canonical = canonical_object_name(name)
    for existing in existing_names:
        if canonical_object_name(existing).casefold() == canonical.casefold():
            return existing
    return canonical


# Função para calcular a interseção sobre união (IoU) entre duas caixas delimitadoras, retornando o valor da IoU
def build_dataset(key, job_id, config, model="yolo26x", force=False):
    import cv2
    import yaml

    from app.vision.detector import LABELS_EN

    base = [n.replace("_", " ") for n in LABELS_EN]
    active_file = store.root() / "active" / f"{key}{'-yolo26s' if model == 'yolo26s' else ''}.json"
    if active_file.exists():
        active = json.loads(active_file.read_text(encoding="utf-8"))
        base = active["names"]
    target_base_names = list(base)
    other = store.root() / "active" / f"{key}{'' if model == 'yolo26s' else '-yolo26s'}.json"
    if other.exists():
        for name in json.loads(other.read_text(encoding="utf-8"))["names"]:
            if name not in base:
                base.append(name)
    with store.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM samples WHERE scope=? AND state='labeled' ORDER BY created DESC LIMIT 512",
                (key,),
            ).fetchall()
        ]
    if not rows or (not force and len(rows) < 4):
        return None
    for row in rows:
        labels = json.loads(row["labels"])
        for box in labels:
            if isinstance(box.get("name"), str):
                box["name"] = canonical_dataset_name(box["name"], base)
        row["labels"] = json.dumps(labels, ensure_ascii=False)
    current_ids = sorted((r["id"], r["labels"]) for r in rows)
    dataset_hash = model + ":v3:" + hashlib.sha256(json.dumps(current_ids).encode()).hexdigest()
    with store.connect() as conn:
        last = conn.execute(
            "SELECT dataset,state,created FROM jobs WHERE scope=? AND dataset=? ORDER BY created DESC LIMIT 1",
            (key, dataset_hash),
        ).fetchone()
    if (
        last
        and last["dataset"] == dataset_hash
        and last["state"] not in ("paused", "interrupted")
        and not (last["state"] == "failed" and time.time() - last["created"] > 86400)
    ):
        return None
    names = eligible_names(rows, base)
    for row in rows:
        for box in json.loads(row["labels"]):
            if box.get("source") == "human" and box["name"] not in names and len(names) < 200:
                names.append(box["name"])
    new_classes = names[len(target_base_names) :]
    # Don't silently discard unconfirmed new-class boxes and teach them as background.
    rows = [r for r in rows if all(b["name"] in names for b in json.loads(r["labels"]))]
    if not rows or (not force and len(rows) < 4):
        return None
    starts = {
        session: min(r["created"] for r in rows if r["session"] == session)
        for session in {r["session"] for r in rows}
    }
    sessions = sorted(starts, key=lambda session: starts[session])
    validation_session = sessions[-1] if len(sessions) > 1 else None
    # Keep a newly marked class in training when its only examples are in the
    # held-out session. The reference split remains the independent safeguard.
    if validation_session:
        for name in new_classes:
            support = [r for r in rows if any(b["name"] == name for b in json.loads(r["labels"]))]
            if support and all(r["session"] == validation_session for r in support):
                validation_session = None
                break
    # Purge near-neighbour frames around the held-out session boundary.
    if validation_session:
        boundary = starts[validation_session]
        rows = [
            r for r in rows if r["session"] == validation_session or r["created"] <= boundary - 30
        ]
        if not any(r["session"] != validation_session for r in rows):
            return None
    directory = store.root() / "datasets" / job_id
    manifest = {
        "scope": key,
        "samples": [],
        "names": names,
        "validation_session": validation_session,
        "hash": dataset_hash,
        "validation_kind": "separate_session" if validation_session else "reference_only",
        "promotion_ready": validation_session is not None
        and sum(r["session"] == validation_session for r in rows) >= 8,
        "reference_sha256": config["reference_sha256"],
        "model": model,
    }
    for row in rows:
        split = "val" if row["session"] == validation_session else "train"
        source = store.root() / row["image"]
        image = cv2.imread(str(source))
        if image is None or digest(source) != row["id"]:
            raise ValueError("Exemplo ausente ou checksum divergente.")
        h, w = image.shape[:2]
        target = directory / "images" / split / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        label = directory / "labels" / split / (source.stem + ".txt")
        label.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for box in json.loads(row["labels"]):
            x1, y1, x2, y2 = box["xyxy"]
            x1, x2 = max(0, min(w, x1)), max(0, min(w, x2))
            y1, y2 = max(0, min(h, y1)), max(0, min(h, y2))
            if x2 > x1 and y2 > y1:
                lines.append(
                    f"{names.index(box['name'])} {(x1 + x2) / 2 / w} {(y1 + y2) / 2 / h} {(x2 - x1) / w} {(y2 - y1) / h}"
                )
        label.write_text("\n".join(lines), encoding="utf-8")
        human_classes = sorted(
            {
                b["name"]
                for b in json.loads(row["labels"])
                if b.get("source") == "human" and b["name"] in new_classes
            }
        )
        manifest["samples"].append(
            {
                "sha256": row["id"],
                "image": str(target.resolve()),
                "split": split,
                "session": row["session"],
                "human_classes": human_classes,
            }
        )
    # Labeled reference replay and evaluation are disjoint, fixed at setup time.
    reference = Path(config["reference"])
    reference_images = sorted((reference / "images" / "train2017").glob("*.jpg"))
    replay_images = labeled_reference_images(reference, reference_images[::2])
    if not replay_images:
        raise ValueError("Referência sem imagens anotadas para preservar as classes existentes.")
    for image in replay_images:
        target = directory / "images" / "train" / ("reference-" + image.name)
        shutil.copyfile(image, target)
        shutil.copyfile(
            reference_label(reference, image),
            directory / "labels" / "train" / ("reference-" + image.with_suffix(".txt").name),
        )
    if not validation_session:
        validation_images = labeled_reference_images(reference, reference_images[1::4])
        if not validation_images:
            raise ValueError("Referência sem imagens anotadas suficientes para validação.")
        for image in validation_images:
            target = directory / "images" / "val" / ("reference-" + image.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image, target)
            label = directory / "labels" / "val" / ("reference-" + image.with_suffix(".txt").name)
            label.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(reference_label(reference, image), label)
    # Full promotion needs independent evidence; a marked example can be used
    # by the isolated class-only route without replacing the existing detector.
    class_evidence = {}
    provisional_human_classes = []
    for name in new_classes:
        support = [r for r in rows if any(b["name"] == name for b in json.loads(r["labels"]))]
        human_support = [
            r
            for r in support
            if any(
                b["name"] == name and b.get("source") == "human" for b in json.loads(r["labels"])
            )
        ]
        train_support = [r for r in support if r["session"] != validation_session]
        validation_support = [
            r for r in support if validation_session and r["session"] == validation_session
        ]
        class_evidence[name] = {
            "samples": len(support),
            "sessions": len({r["session"] for r in support}),
            "human_samples": len(human_support),
            "human_train_samples": sum(r in train_support for r in human_support),
            "validation_samples": len(validation_support),
        }
        full_evidence = (
            len(support) >= 20
            and len({r["session"] for r in support}) >= 3
            and len(validation_support) >= 5
        )
        if not full_evidence:
            manifest["promotion_ready"] = False
        if human_support and any(r in train_support for r in human_support):
            provisional_human_classes.append(name)
    manifest["class_evidence"] = class_evidence
    manifest["provisional_human_classes"] = provisional_human_classes
    yaml_path = directory / "data.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(directory),
                "train": "images/train",
                "val": "images/val",
                "names": dict(enumerate(names)),
            }
        ),
        encoding="utf-8",
    )
    store.atomic_json(directory / "manifest.json", manifest)
    return yaml_path, manifest


# Função para verificar se a referência foi preservada, comparando os valores de referência e classes entre o modelo base e o candidato
def reference_preserved(base, candidate):
    values = [
        base["reference"],
        candidate["reference"],
        *base["classes"].values(),
        *candidate["classes"].values(),
    ]
    return (
        all(math.isfinite(v) for v in values)
        and candidate["reference"] >= base["reference"] - 0.005
        and all(candidate["classes"].get(k, 0) >= v - 0.02 for k, v in base["classes"].items())
    )


# Função para verificar se o candidato foi aprovado, considerando a preservação da referência, a preservação das classes locais e os valores de referência e proxy local
def approved(base, candidate):
    """No automatic promotion from confidence or training loss alone."""
    import math

    values = [
        base["reference"],
        candidate["reference"],
        base["local_proxy"],
        candidate["local_proxy"],
    ]
    if not all(math.isfinite(x) for x in values):
        return False
    per_class = all(candidate["classes"].get(k, 0) >= v - 0.02 for k, v in base["classes"].items())
    local_classes = all(
        candidate.get("local_classes", {}).get(k, 0) >= v - 0.02
        for k, v in base.get("local_classes", {}).items()
    )
    return (
        per_class
        and local_classes
        and candidate["reference"] >= base["reference"] - 0.005
        and candidate["local_proxy"] >= base["local_proxy"] + 0.01
    )


# Função para calcular métricas de avaliação do modelo, comparando o desempenho do modelo em relação a uma referência e a um conjunto local de dados
def supplemental_approved(manifest, weight_hashes, class_ap):
    """Allow human-taught classes as an isolated add-on, never as a base-model replacement."""
    names = manifest.get("provisional_human_classes", [])
    if (
        not names
        or not weight_hashes.get("after")
        or weight_hashes.get("after") == weight_hashes.get("before")
    ):
        return False
    evidence = manifest.get("class_evidence", {})
    for name in names:
        try:
            score = float(class_ap[name])
        except (KeyError, TypeError, ValueError):
            return False
        if (
            evidence.get(name, {}).get("human_train_samples", 0) < 1
            or not math.isfinite(score)
            or score < 0.5
            or score > 1
        ):
            return False
    return True


def metrics(model, reference, local):
    configure_cpu()
    kwargs = dict(
        device="cpu",
        imgsz=640,
        batch=1,
        workers=0,
        plots=False,
        verbose=False,
        project=str(Path(local).parent),
        name="evaluation",
        exist_ok=True,
    )
    known = model.val(data=str(reference), **kwargs)
    proxy = model.val(data=str(local), **kwargs)
    return {
        "reference": float(known.box.map),
        "classes": {str(k): float(v) for k, v in zip(known.box.ap_class_index, known.box.ap)},
        "local_proxy": float(proxy.box.map),
        "local_classes": {str(k): float(v) for k, v in zip(proxy.box.ap_class_index, proxy.box.ap)},
        "local_is_pseudo_labeled": True,
    }


def provisional_class_metrics(model, manifest, directory):
    import yaml

    samples = [
        sample["image"]
        for sample in manifest["samples"]
        if sample["split"] == "train"
        and set(sample["human_classes"]) & set(manifest["provisional_human_classes"])
    ]
    if not samples:
        return {}
    image_list = directory / "provisional-images.txt"
    image_list.write_text("\n".join(samples), encoding="utf-8")
    provisional_yaml = directory / "provisional.yaml"
    provisional_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(directory),
                "train": "images/train",
                "val": str(image_list),
                "names": dict(enumerate(manifest["names"])),
            }
        ),
        encoding="utf-8",
    )
    configure_cpu()
    result = model.val(
        data=str(provisional_yaml),
        device="cpu",
        imgsz=640,
        batch=1,
        workers=0,
        plots=False,
        verbose=False,
        project=str(directory),
        name="provisional-evaluation",
        exist_ok=True,
    )
    scores = {int(k): float(v) for k, v in zip(result.box.ap_class_index, result.box.ap)}
    return {
        name: scores.get(manifest["names"].index(name), 0.0)
        for name in manifest["provisional_human_classes"]
    }


# Função para treinar o modelo, verificando o armazenamento disponível, preparando o conjunto de dados, configurando o checkpoint e executando o treinamento com monitoramento de progresso e interrupções
def train(key, config, model="yolo26x", force=False, request_id=None):
    import torch
    from ultralytics import YOLO

    size = sum(
        p.stat().st_size
        for directory in ("runs", "datasets")
        for p in (store.root() / directory).rglob("*")
        if p.is_file()
    )
    if size > 12 * 1024**3:
        message = "Treino não iniciado: o armazenamento de experiências/datasets atingiu o limite de 12 GB."
        with store.connect() as conn:
            conn.execute("UPDATE settings SET message=? WHERE scope=?", (message, key))
            if request_id:
                conn.execute(
                    "UPDATE training_requests SET state='blocked',message=? WHERE id=?",
                    (message, request_id),
                )
        return False
    job_id = uuid.uuid4().hex
    if model not in ("yolo26x", "yolo26s"):
        raise ValueError("Modelo de treino não permitido.")
    prepared = build_dataset(key, job_id, config, model, force)
    if prepared is None:
        message = "Treino não iniciado: o conjunto atual já foi processado ou ainda não tem exemplos verificados/diversidade suficientes. Novos exemplos válidos poderão iniciar outro ciclo."
        with store.connect() as conn:
            conn.execute("UPDATE settings SET message=? WHERE scope=?", (message, key))
            if request_id:
                conn.execute(
                    "UPDATE training_requests SET state='blocked',message=? WHERE id=?",
                    (message, request_id),
                )
        return False
    data, manifest = prepared
    with store.connect() as conn:
        dataset_hash = manifest["hash"]
        conn.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)",
            (
                job_id,
                key,
                time.time(),
                "training",
                f"Treinando {model.upper()}",
                dataset_hash,
                None,
                None,
            ),
        )
        if request_id:
            conn.execute(
                "UPDATE training_requests SET state='training',job_id=?,message=? WHERE id=?",
                (job_id, f"Ajustando pesos de {model.upper()} em CPU.", request_id),
            )
        store.event(conn, key, f"Treinando uma candidata {model.upper()} em CPU.")
    directory = store.root() / "runs" / job_id
    directory.mkdir(parents=True, exist_ok=True)
    with store.connect() as conn:
        conn.execute(
            "UPDATE jobs SET checkpoint=? WHERE id=?",
            (str(directory / "candidate" / "weights" / "last.pt"), job_id),
        )
    active_file = store.root() / "active" / f"{key}{'-yolo26s' if model == 'yolo26s' else ''}.json"
    previous = json.loads(active_file.read_text(encoding="utf-8")) if active_file.exists() else None
    original = Path(config["checkpoint"]).with_name(model + ".pt")
    checkpoint = previous["checkpoint"] if previous else str(original)
    expected = (
        previous["checkpoint_sha256"]
        if previous
        else (
            config["checkpoint_sha256"] if model == "yolo26x" else config["assets"][model + ".pt"]
        )
    )
    if digest(checkpoint) != expected:
        raise ValueError("Checkpoint de treinamento com checksum divergente.")
    # A recovered checkpoint is a warm start; baseline evaluation remains the active model.
    baseline_checkpoint = checkpoint
    with store.connect() as conn:
        recovery = conn.execute(
            "SELECT checkpoint,id FROM jobs WHERE scope=? AND dataset=? AND state IN ('paused','interrupted') AND checkpoint IS NOT NULL ORDER BY created DESC LIMIT 1",
            (key, dataset_hash),
        ).fetchone()
    if recovery and Path(recovery[0]).is_file():
        checkpoint = recovery[0]
        with store.connect() as conn:
            conn.execute(
                "UPDATE jobs SET state='recovered',message='Pesos recuperados em novo ciclo.' WHERE id=?",
                (recovery[1],),
            )
    if not recovery:
        with store.connect() as conn:
            pending = conn.execute(
                "SELECT checkpoint,metrics FROM jobs WHERE scope=? AND state='awaiting_evidence' AND dataset LIKE ? ORDER BY created DESC LIMIT 1",
                (key, model + ":%"),
            ).fetchone()
        if pending and pending["checkpoint"] and Path(pending["checkpoint"]).is_file():
            pending_report = json.loads(pending["metrics"])
            if pending_report.get("baseline_sha256") == expected and digest(
                pending["checkpoint"]
            ) == pending_report.get("candidate_sha256"):
                checkpoint = pending["checkpoint"]
    teacher = YOLO(checkpoint)
    if teacher.model.yaml.get("scale") != model[-1]:
        raise ValueError("Treinamento recusado: escala do checkpoint divergente.")
    configure_cpu()
    started = time.monotonic()
    weight_hashes = {}
    progress = {"batch": 0, "last": 0.0}

    def before_training(trainer):
        weight_hashes["before"] = trainable_digest(trainer.model)

    def after_training(trainer):
        weight_hashes["after"] = trainable_digest(trainer.model)

    class Paused(Exception):
        pass

    def guard(trainer):
        import psutil

        loss = loss_value(trainer.tloss)
        progress["batch"] += 1
        if time.monotonic() - progress["last"] > 3:
            message = (
                f"{model.upper()} · lote {progress['batch']}/{len(trainer.train_loader)} · perda {loss:.4f}"
                if loss is not None
                else f"Treinando {model.upper()}"
            )
            with store.connect() as conn:
                conn.execute("UPDATE jobs SET message=? WHERE id=?", (message, job_id))
                conn.execute("UPDATE settings SET message=? WHERE scope=?", (message, key))
            progress["last"] = time.monotonic()
        if (
            interrupted(key, force)
            or psutil.virtual_memory().available < 3 * 1024**3
            or time.monotonic() - started > 1800
        ):
            trainer.save_model()
            raise Paused("Treino pausado no fim do lote; pesos e estado preservados.")
        concurrent_delay()

    teacher.add_callback("on_train_batch_end", guard)
    teacher.add_callback("on_train_start", before_training)
    teacher.add_callback("on_train_end", after_training)
    try:
        teacher.train(
            data=str(data),
            device="cpu",
            batch=1,
            imgsz=320,
            epochs=1,
            workers=0,
            freeze=22,
            optimizer="SGD",
            lr0=0.0005,
            amp=False,
            cache=False,
            plots=False,
            save=True,
            save_period=1,
            project=str(directory),
            name="candidate",
            exist_ok=True,
            verbose=False,
            mosaic=0,
            close_mosaic=0,
        )
        candidate_path = directory / "candidate" / "weights" / "best.pt"
        if interrupted(key, force):
            with store.connect() as conn:
                conn.execute(
                    "UPDATE jobs SET state=?,message=?,checkpoint=? WHERE id=?",
                    (
                        "paused",
                        "Treino interrompido; checkpoint preservado.",
                        str(directory / "candidate" / "weights" / "last.pt"),
                        job_id,
                    ),
                )
            return True
        candidate = YOLO(candidate_path)
        if not all(torch.isfinite(p).all() for p in candidate.model.parameters()):
            raise ValueError("Pesos não finitos; candidata recusada.")
        baseline = YOLO(baseline_checkpoint)

        def evaluation_guard(_):
            if interrupted(key, force):
                raise Paused("Avaliação pausada para preservar a detecção ao vivo.")

        candidate.add_callback("on_val_batch_end", evaluation_guard)
        baseline.add_callback("on_val_batch_end", evaluation_guard)
        # Reference YAML must use the same expanded registry; original IDs stay 0..79.
        import yaml

        reference_yaml = directory / "reference.yaml"
        reference_test = directory / "reference-test.txt"
        reference_images = sorted((Path(config["reference"]) / "images/train2017").glob("*.jpg"))
        heldout = labeled_reference_images(config["reference"], reference_images[3::4])
        if not heldout:
            raise ValueError("Referência de teste independente insuficiente.")
        reference_test.write_text("\n".join(str(p.resolve()) for p in heldout), encoding="utf-8")
        reference_yaml.write_text(
            yaml.safe_dump(
                {
                    "path": config["reference"],
                    "train": str(reference_test),
                    "val": str(reference_test),
                    "names": dict(enumerate(manifest["names"])),
                }
            ),
            encoding="utf-8",
        )
        with store.connect() as conn:
            conn.execute(
                "UPDATE jobs SET message=? WHERE id=?",
                (f"{model.upper()} · medindo referência antes do ajuste.", job_id),
            )
            conn.execute(
                "UPDATE settings SET message=? WHERE scope=?",
                (f"Avaliando referência de {model.upper()} antes do ajuste.", key),
            )
        before = metrics(baseline, reference_yaml, data)
        with store.connect() as conn:
            conn.execute(
                "UPDATE jobs SET message=? WHERE id=?",
                (f"{model.upper()} · medindo candidata após ajuste dos pesos.", job_id),
            )
            conn.execute(
                "UPDATE settings SET message=? WHERE scope=?",
                (f"Avaliando candidata {model.upper()} após ajuste dos pesos.", key),
            )
        after = metrics(candidate, reference_yaml, data)
        reference_safe = reference_preserved(before, after)
        provisional_class_ap = (
            provisional_class_metrics(candidate, manifest, directory)
            if manifest["provisional_human_classes"]
            else {}
        )
        weights_changed = bool(
            weight_hashes.get("after") and weight_hashes.get("before") != weight_hashes["after"]
        )
        standard_approved = (
            manifest["promotion_ready"] and weights_changed and approved(before, after)
        )
        class_only_approved = not standard_approved and supplemental_approved(
            manifest, weight_hashes, provisional_class_ap
        )
        report = {
            "baseline_sha256": expected,
            "candidate_sha256": digest(candidate_path),
            "reference_preserved": reference_safe,
            "before": before,
            "after": after,
            "approved": standard_approved or class_only_approved,
            "activation_mode": "full"
            if standard_approved
            else "class_only_provisional"
            if class_only_approved
            else "not_activated",
            "class_only_provisional": class_only_approved,
            "provisional_classes": manifest["provisional_human_classes"],
            "class_evidence": manifest["class_evidence"],
            "provisional_class_ap_in_sample": provisional_class_ap,
            "provisional_generalization_tested": False,
            "base_detector_preserved": class_only_approved,
            "model": model,
            "separate_local_session": manifest["validation_kind"] == "separate_session",
            "reference_test_images": len(heldout),
            "reference_test_disjoint_from_training": True,
            "local_evaluation_available": manifest["validation_kind"] != "reference_only",
            "weights_changed": weights_changed,
            "weight_digests": weight_hashes,
            "training_seconds": time.monotonic() - started,
            "cpu_threads": 1,
            "evaluation_limit": "A avaliação provisória mede a marcação usada no treino; ela não comprova generalização. O detector original continua responsável pelas classes anteriores.",
        }
        store.atomic_json(directory / "evaluation.json", report)
        if not report["approved"]:
            with store.connect() as conn:
                conn.execute(
                    "UPDATE jobs SET state=?,message=?,metrics=? WHERE id=?",
                    (
                        "awaiting_evidence" if reference_safe else "rejected",
                        "Pesos ajustados; candidata aguarda evidência local."
                        if reference_safe
                        else "Candidata recusada: preservar referência e classes anteriores.",
                        json.dumps(report),
                        job_id,
                    ),
                )
                store.event(
                    conn,
                    key,
                    f"Candidata {model.upper()} não ativada: avaliação/evidência insuficiente.",
                )
            return True
        exported = Path(
            candidate.export(
                format="onnx",
                imgsz=640,
                nms=False,
                dynamic=False,
                simplify=False,
                device="cpu",
                opset=17,
            )
        )
        import numpy as np
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(
            str(exported), sess_options=options, providers=["CPUExecutionProvider"]
        )
        output = np.asarray(
            session.run(
                None, {session.get_inputs()[0].name: np.zeros((1, 3, 640, 640), np.float32)}
            )[0]
        )
        if output.shape != (1, 300, 6) or not np.isfinite(output).all():
            raise ValueError("Exportação ONNX incompatível; modelo anterior preservado.")
        from app.vision.detector import LABELS

        translations = dict(EXTRA)
        if previous:
            previous = {**previous, "previous": None}
        version = {
            "id": job_id,
            "model": model,
            "scope": key,
            "checkpoint": str(candidate_path),
            "checkpoint_sha256": digest(candidate_path),
            "onnx": str(exported),
            "sha256": digest(exported),
            "names": manifest["names"],
            "names_pt": LABELS + [translations.get(n, n) for n in manifest["names"][80:]],
            "metrics": report,
            "class_ids": [
                manifest["names"].index(name) for name in manifest["provisional_human_classes"]
            ]
            if class_only_approved
            else [],
            "previous": None if class_only_approved else previous,
        }
        if class_only_approved:
            supplemental_file = store.root() / "active" / f"{key}-supplement-{model}.json"
            previous_supplemental = (
                json.loads(supplemental_file.read_text(encoding="utf-8"))
                if supplemental_file.exists()
                else None
            )
            if previous_supplemental:
                previous_supplemental = {**previous_supplemental, "previous_supplemental": None}
            version["previous_supplemental"] = previous_supplemental
            store.atomic_json(supplemental_file, version)
            version_state = "provisional"
            message = f"{model.upper()} · classes novas disponibilizadas como complemento provisório; detector original preservado."
        else:
            # File activation is atomic. Engine validates hashes and warms before swapping sessions.
            store.atomic_json(active_file, version)
            version_state = "active"
            message = f"{model.upper()} aprovado e disponibilizado."
        store.atomic_json(store.root() / "versions" / f"{job_id}.json", version)
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO versions VALUES(?,?,?,?,?)",
                (job_id, key, time.time(), version_state, json.dumps(version)),
            )
            conn.execute(
                "UPDATE jobs SET state=?,message=?,metrics=?,checkpoint=? WHERE id=?",
                ("approved", message, json.dumps(report), str(candidate_path), job_id),
            )
            store.event(conn, key, message + " Rótulos automáticos não são verdade humana.")
        memory = store.root().parent / "memory" / key / "APRENDIZADO.md"
        memory.parent.mkdir(parents=True, exist_ok=True)
        if memory.exists():
            history = memory.parent / "history"
            history.mkdir(exist_ok=True)
            shutil.copyfile(memory, history / (str(uuid.uuid4()) + "-APRENDIZADO.md"))
        with memory.open("a", encoding="utf-8") as stream:
            stream.write(
                f"\n## Atualização automática {time.strftime('%Y-%m-%d %H:%M')}\n{model.upper()} versão {job_id}. "
                f"Avaliação de referência separada: {after['reference']:.4f}; referência local automática: {after['local_proxy']:.4f}. "
                + (
                    "Classes novas servidas como complemento provisório, sem substituir o detector anterior; "
                    "a avaliação da classe usa as marcações de treino e não comprova generalização. "
                    if class_only_approved
                    else ""
                )
                + "Rótulos locais não são confirmações humanas. Versão anterior preservada.\n"
            )
        return True
    except Paused as exc:
        checkpoint = directory / "candidate" / "weights" / "last.pt"
        with store.connect() as conn:
            conn.execute(
                "UPDATE jobs SET state=?,message=?,checkpoint=? WHERE id=?",
                ("paused", str(exc), str(checkpoint), job_id),
            )
            store.event(
                conn, key, "Treinamento pausado; retomada automática a partir dos pesos salvos."
            )
        return True
    except Exception:
        with store.connect() as conn:
            conn.execute(
                "UPDATE jobs SET state=?,message=? WHERE id=?",
                ("failed", "Falha no motor local; diagnóstico preservado no registro.", job_id),
            )
            store.event(
                conn, key, "Falha no treinamento; versão atual preservada. Consulte o histórico."
            )
        raise


# Função principal para configurar o ambiente, gerenciar bloqueios de serviço, monitorar o processo pai e executar o loop principal de treinamento e avaliação de modelos
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", required=True)
    parser.add_argument("--parent", type=int, required=True)
    args = parser.parse_args()
    os.environ["SOLARIS_STORAGE"] = args.storage
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    # Only one learner may claim this database, including when two app windows exist.
    service_lock = store.root() / "service.lock"
    service_lock.parent.mkdir(parents=True, exist_ok=True)
    lock_file = service_lock.open("a+b")
    lock_file.seek(0)
    lock_file.write(b"0")
    lock_file.flush()
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
    import psutil

    me = psutil.Process()
    if os.name == "nt":
        me.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            cpus = me.cpu_affinity()
            reserved = os.environ.get("SOLARIS_LEARNING_CPU", "")
            me.cpu_affinity([int(reserved)] if reserved else cpus[-1:])
        except (psutil.Error, OSError):
            pass
    config = json.loads((store.root() / "runtime.json").read_text(encoding="utf-8"))
    if not config.get("validated"):
        raise ValueError("Runtime ainda não validado.")
    for relative, expected in config["reference_files"].items():
        if digest(Path(config["reference"]) / relative) != expected:
            raise ValueError("Referência de avaliação foi alterada; serviço não iniciado.")
    teachers = None
    encoder = None
    with store.connect() as conn:
        conn.execute(
            "UPDATE jobs SET state='interrupted',message='Processo anterior interrompido; checkpoint preservado.' WHERE state='training'"
        )
        conn.execute(
            "UPDATE training_requests SET state='paused',message='Retomando solicitação após reinício.' WHERE state='training'"
        )
        conn.execute(
            "UPDATE training_requests SET state='queued',message='Retomando preparação após reinício.' WHERE state='preparing'"
        )
        scopes = [r[0] for r in conn.execute("SELECT scope FROM settings")]
        for key in scopes:
            store.coalesce_training_requests(conn, key)
    # Parent identity prevents continuing after shutdown or PID reuse.
    parent = psutil.Process(args.parent)
    parent_started = parent.create_time()
    import threading

    def watch():
        while True:
            try:
                if psutil.Process(args.parent).create_time() != parent_started:
                    os._exit(0)
            except psutil.Error:
                os._exit(0)
            time.sleep(2)

    threading.Thread(target=watch, daemon=True).start()
    last_cleanup = 0
    active_request_id = None
    while True:
        key = None
        try:
            if time.time() - last_cleanup > 600:
                from app.vision.learning_retention import cleanup

                cleanup()
                last_cleanup = time.time()
            with store.connect() as conn:
                keys = [
                    r[0]
                    for r in conn.execute(
                        "SELECT scope FROM settings WHERE enabled=1 ORDER BY last_live"
                    )
                ]
            for key in keys:
                with store.connect() as conn:
                    immediate = (
                        conn.execute(
                            "SELECT count(*) FROM training_requests WHERE scope=? AND state IN ('queued','verifying','paused')",
                            (key,),
                        ).fetchone()[0]
                        > 0
                    )
                if interrupted(key, immediate):
                    with store.connect() as conn:
                        conn.execute(
                            "UPDATE settings SET message=? WHERE scope=?",
                            (
                                "Aprendizado pausado ou latência crítica; detecção permanece disponível.",
                                key,
                            ),
                        )
                    continue
                if not resources(immediate):
                    with store.connect() as conn:
                        conn.execute(
                            "UPDATE settings SET message=? WHERE scope=?",
                            (
                                "Aguardando espaço em disco ou redução da carga de CPU para iniciar o processamento.",
                                key,
                            ),
                        )
                    continue
                with store.connect() as conn:
                    pending_request = conn.execute(
                        "SELECT * FROM training_requests WHERE scope=? AND state IN ('queued','verifying','paused') ORDER BY created LIMIT 1",
                        (key,),
                    ).fetchone()
                    row = next_sample(conn, key, pending_request)
                    human = (
                        conn.execute(
                            "SELECT * FROM human_reviews WHERE scope=? AND sample_id=?",
                            (key, row["id"]),
                        ).fetchone()
                        if row
                        else None
                    )
                    human_names = {
                        b["name"]
                        for r in conn.execute(
                            "SELECT labels FROM human_reviews WHERE scope=? ORDER BY created DESC LIMIT 64",
                            (key,),
                        )
                        for b in json.loads(r[0])
                    }
                if row:
                    import cv2

                    if teachers is None:
                        teachers = Teachers(config)
                    path = store.root() / row["image"]
                    if digest(path) != row["id"]:
                        raise ValueError("Checksum de imagem divergente.")
                    with store.connect() as conn:
                        scene = conn.execute(
                            "SELECT scene,updated FROM live_context WHERE scope=?", (key,)
                        ).fetchone()
                    context = (
                        json.loads(scene["scene"])
                        if scene and time.time() - scene["updated"] < 300
                        else {}
                    )
                    queries = context.get("queries", [])[:8]
                    labels = teachers.label(
                        cv2.imread(str(path)), key, sorted(human_names)[:16] + queries
                    )
                    if human:
                        labels = merge_human(labels, json.loads(human["labels"]))
                    with store.connect() as conn:
                        conn.execute(
                            "UPDATE samples SET state=?,labels=? WHERE id=? AND scope=?",
                            (
                                "labeled" if labels else "uncertain",
                                json.dumps(labels),
                                row["id"],
                                key,
                            ),
                        )
                        conn.execute(
                            "UPDATE settings SET message=? WHERE scope=?",
                            ("Verificando exemplos com YOLO26x, ByteTrack e OWLv2.", key),
                        )
                # Descoberta visual sem rótulo: CLIP + agrupamento incremental, em lotes pequenos.
                if config.get("clip"):
                    from app.vision import clusters

                    if encoder is None:
                        encoder = clusters.Encoder(config["clip"])
                    clusters.process_pending(key, encoder, limit=2)
                with store.connect() as conn:
                    request = conn.execute(
                        "SELECT * FROM training_requests WHERE scope=? AND state IN ('queued','verifying','paused') ORDER BY created LIMIT 1",
                        (key,),
                    ).fetchone()
                    source = (
                        conn.execute(
                            "SELECT state FROM samples WHERE scope=? AND id=?",
                            (key, request["sample_id"]),
                        ).fetchone()
                        if request and request["sample_id"]
                        else None
                    )
                    count = conn.execute(
                        "SELECT count(*) FROM samples WHERE scope=? AND state='labeled'", (key,)
                    ).fetchone()[0]
                    conn.execute("INSERT OR IGNORE INTO cycle_state(scope) VALUES(?)", (key,))
                    cycle = conn.execute(
                        "SELECT * FROM cycle_state WHERE scope=?", (key,)
                    ).fetchone()
                if request and source and source["state"] != "labeled":
                    with store.connect() as conn:
                        state = "verifying" if source["state"] == "pending" else "blocked"
                        conn.execute(
                            "UPDATE training_requests SET state=?,message=? WHERE id=?",
                            (
                                state,
                                "Revisão parcial: aguardando verificação do restante da imagem. Corrija ou confirme a imagem completa se a verificação for inconclusiva.",
                                request["id"],
                            ),
                        )
                    continue
                automatic = (
                    count >= 4
                    and count - cycle["last_count"] >= 4
                    and time.time() - cycle["last_started"] >= 60
                )
                if request or automatic:
                    teachers = None  # Release teacher RAM before loading training model.
                    encoder = None
                    import gc

                    gc.collect()
                    models = [request["model"]] if request else ["yolo26s", "yolo26x"]
                    did_train = False
                    if request:
                        active_request_id = request["id"]
                        with store.connect() as conn:
                            conn.execute(
                                "UPDATE training_requests SET state='preparing',message=? WHERE id=?",
                                (
                                    f"Preparando exemplos verificados para YOLO26{request['model'][-1].upper()}.",
                                    request["id"],
                                ),
                            )
                    if automatic and not request:
                        with store.connect() as conn:
                            conn.execute(
                                "UPDATE cycle_state SET last_count=?,last_started=? WHERE scope=?",
                                (count, time.time(), key),
                            )
                    for target in models:
                        if interrupted(key, bool(request)):
                            if request:
                                with store.connect() as conn:
                                    conn.execute(
                                        "UPDATE training_requests SET state='paused',message=? WHERE id=?",
                                        (
                                            "Treino pausado até que a câmera/recursos permitam continuar.",
                                            request["id"],
                                        ),
                                    )
                            break
                        did_train = train(
                            key, config, target, bool(request), request["id"] if request else None
                        )
                        if request:
                            with store.connect() as conn:
                                req = conn.execute(
                                    "SELECT job_id,state,message FROM training_requests WHERE id=?",
                                    (request["id"],),
                                ).fetchone()
                                job = (
                                    conn.execute(
                                        "SELECT state,message FROM jobs WHERE id=?", (req[0],)
                                    ).fetchone()
                                    if req[0]
                                    else None
                                )
                                if job:
                                    state = {
                                        "rejected": "evaluated",
                                        "awaiting_evidence": "evaluated",
                                    }.get(job["state"], job["state"])
                                    message = job["message"]
                                elif req["state"] in ("preparing", "queued"):
                                    state = "blocked"
                                    message = "Treino não iniciado: nenhum conjunto utilizável disponível neste momento."
                                else:
                                    state, message = req["state"], req["message"]
                                conn.execute(
                                    "UPDATE training_requests SET state=?,message=? WHERE id=?",
                                    (state, message, request["id"]),
                                )
                            active_request_id = None
                        if not did_train and not request:
                            with store.connect() as conn:
                                row = conn.execute(
                                    "SELECT count(*) n,count(DISTINCT session) sessions FROM samples WHERE scope=? AND state='labeled'",
                                    (key,),
                                ).fetchone()
                                conn.execute(
                                    "UPDATE settings SET message=? WHERE scope=?",
                                    (
                                        f"Aguardando contexto variado: {row['n']} exemplos verificados, {row['sessions']} janelas. Ciclo automático: quatro exemplos verificados novos, sem esperar a câmera parar.",
                                        key,
                                    ),
                                )
        except Exception as exc:
            print(
                f"{time.strftime('%Y-%m-%d %H:%M')} {type(exc).__name__}: {str(exc)[:400]}",
                flush=True,
            )
            if key is not None:
                fail_request(key, active_request_id, exc)
            active_request_id = None
            with store.connect() as conn:
                conn.execute(
                    "UPDATE jobs SET state='failed',message='Falha no motor local; diagnóstico no registro.' WHERE state='training'"
                )
                conn.execute(
                    "UPDATE training_requests SET state='failed',message='Falha no processamento; diagnóstico no registro local.' WHERE state='training'"
                )
                if "key" in locals():
                    conn.execute(
                        "UPDATE settings SET message=? WHERE scope=?",
                        (
                            "Aprendizado aguardando recuperação; diagnóstico preservado no registro local.",
                            key,
                        ),
                    )
            time.sleep(30)
        time.sleep(5)


# Ponto de entrada principal do script, que chama a função main() para iniciar o processo de treinamento e avaliação de modelos.
if __name__ == "__main__":
    main()
