"""YOLO ONNX CPU detection with optional class-only supplements; never downloads weights."""

# Importa as bibliotecas necessárias
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import sys
import threading
from pathlib import Path
from time import perf_counter

# Variáveis globais para armazenar a sessão ONNX, o caminho do modelo carregado, o estado de carregamento e erros
_session = None
_loaded_path = None
_loading = False
_load_error = None
_load_lock = threading.Lock()
_load_thread = None
_adapted_session = None
_adapted_path = None
_adapted_labels = None
_adapted_model = None
_adapted_lock = threading.Lock()
_supplemental_session = None
_supplemental_path = None
_supplemental_lock = threading.Lock()
_active_labels: list[str] | None = None

# Função para obter o caminho do modelo YOLOv8, verificando diferentes diretórios e selecionando o modelo mais adequado
LABELS_EN = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic_light",
    "fire_hydrant",
    "stop_sign",
    "parking_meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports_ball",
    "kite",
    "baseball_bat",
    "baseball_glove",
    "skateboard",
    "surfboard",
    "tennis_racket",
    "bottle",
    "wine_glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot_dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted_plant",
    "bed",
    "dining_table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell_phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy_bear",
    "hair_drier",
    "toothbrush",
]

# Função para obter o caminho do modelo YOLOv8, verificando diferentes diretórios e selecionando o modelo mais adequado
LABELS = [
    "pessoa",
    "bicicleta",
    "carro",
    "motocicleta",
    "avião",
    "ônibus",
    "trem",
    "caminhão",
    "barco",
    "semáforo",
    "hidrante",
    "placa de pare",
    "parquímetro",
    "banco",
    "pássaro",
    "gato",
    "cachorro",
    "cavalo",
    "ovelha",
    "vaca",
    "elefante",
    "urso",
    "zebra",
    "girafa",
    "mochila",
    "guarda-chuva",
    "bolsa",
    "gravata",
    "mala",
    "frisbee",
    "esquis",
    "prancha de neve",
    "bola esportiva",
    "pipa",
    "taco de beisebol",
    "luva de beisebol",
    "skate",
    "prancha de surfe",
    "raquete de tênis",
    "garrafa",
    "taça de vinho",
    "xícara",
    "garfo",
    "faca",
    "colher",
    "tigela",
    "banana",
    "maçã",
    "sanduíche",
    "laranja",
    "brócolis",
    "cenoura",
    "cachorro-quente",
    "pizza",
    "rosquinha",
    "bolo",
    "cadeira",
    "sofá",
    "planta em vaso",
    "cama",
    "mesa de jantar",
    "vaso sanitário",
    "televisor",
    "notebook",
    "mouse",
    "controle remoto",
    "teclado",
    "celular",
    "micro-ondas",
    "forno",
    "torradeira",
    "pia",
    "geladeira",
    "livro",
    "relógio",
    "vaso",
    "tesoura",
    "urso de pelúcia",
    "secador de cabelo",
    "escova de dentes",
]


# Função para obter o caminho do modelo YOLOv8, verificando diferentes diretórios e selecionando o modelo mais adequado
def model_path() -> Path:
    local = Path(os.environ.get("SOLARIS_STORAGE", "storage")) / "models"
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "models"
    candidates: list[tuple[int, int, int, Path]] = []
    for directory in (bundled, local):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.onnx"):
            stem = path.stem.lower().replace(" ", "")
            # OIV7 family: yolov8n-oiv7, yolov8s-oiv7, etc. — priority 30 (above yolo26=26)
            oiv7_match = re.fullmatch(r"(yolov8)([nsmlx])-oiv7", stem)
            if oiv7_match:
                _, scale = oiv7_match.groups()
                candidates.append(
                    (
                        {"n": 0, "s": 1, "m": 2, "l": 3, "x": 4}[scale],
                        30,
                        int(directory == local),
                        path,
                    )
                )
                continue
            match = re.fullmatch(r"(yolo26|yolo11|yolov8)([nsmlx])", stem)
            if match:
                family, scale = match.groups()
                candidates.append(
                    (
                        {"n": 0, "s": 1, "m": 2, "l": 3, "x": 4}[scale],
                        {"yolov8": 8, "yolo11": 11, "yolo26": 26}[family],
                        int(directory == local),
                        path,
                    )
                )
    return max(candidates, key=lambda item: item[:3])[3] if candidates else local / "yolo26x.onnx"


# Função para verificar se o modelo YOLOv8 está disponível, carregado e sem erros
def status() -> dict[str, bool | str | None]:
    path = _loaded_path or model_path()
    return {
        "model_available": path.is_file(),
        "model": path.stem,
        "device": "CPU",
        "loaded": _session is not None,
        "loading": _loading,
        "error": _load_error,
        "policy": "largest_installed",
    }


# Função para carregar o modelo YOLOv8, verificando compatibilidade e inicializando a sessão ONNX
def load() -> None:
    global _session, _loaded_path, _loading, _load_error, _active_labels
    with _load_lock:
        if _session is not None:
            return
        _loading = True
        _load_error = None
        try:
            np = importlib.import_module("numpy")
            ort = importlib.import_module("onnxruntime")
            path = model_path()
            if not path.is_file():
                raise ValueError(
                    "Modelo ausente. Instale um detector ONNX na pasta de modelos do SOLARIS."
                )
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            spec = session.get_inputs()[0]
            size = (
                spec.shape[2]
                if isinstance(spec.shape[2], int)
                else (320 if path.stem == "yolov8n" else 640)
            )
            if spec.type != "tensor(float)" or len(spec.shape) != 4 or not 32 <= size <= 640:
                raise ValueError("Modelo ONNX incompatível com o detector CPU.")
            # Load label sidecar (e.g. yolov8n-oiv7.labels.json) if present.
            sidecar = path.with_suffix("").with_suffix(".labels.json")
            labels_for_model: list[str] | None = None
            if sidecar.is_file():
                try:
                    labels_for_model = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
            sample = session.run(None, {spec.name: np.zeros((1, 3, size, size), dtype=np.float32)})[
                0
            ]
            postprocess(sample, size, size, 1, 0, 0, labels=labels_for_model or LABELS)
            _loaded_path = path
            _session = session
            _active_labels = labels_for_model
        except Exception as exc:
            _load_error = str(exc)
            raise
        finally:
            _loading = False


# Função para iniciar o carregamento do modelo YOLOv8 em segundo plano, se ainda não estiver carregado
def start_loading() -> None:
    global _load_thread

    def background():
        try:
            load()
        except Exception:
            pass  # status() exposes the load error; no silent smaller-model fallback.

    if _load_thread is None:
        _load_thread = threading.Thread(target=background, daemon=True, name="solaris-vision-load")
        _load_thread.start()


# Função para processar a saída do modelo YOLOv8, convertendo as coordenadas e filtrando as detecções com base na confiança e nas classes
def postprocess(output, width: int, height: int, scale: float, pad_x: int, pad_y: int, labels=None):
    import cv2

    np = importlib.import_module("numpy")
    labels = LABELS if labels is None else labels

    # Verifica se a saída do modelo é compatível com os formatos esperados e processa as detecções, aplicando filtros de confiança e classes válidas
    predictions = np.asarray(output)
    if predictions.ndim == 3 and predictions.shape[0] == 1 and predictions.shape[2] == 6:
        rows = predictions[0]
        rows = rows[np.isfinite(rows).all(axis=1)]
        rows = rows[
            (rows[:, 4] >= 0.35)
            & (rows[:, 5] >= 0)
            & (rows[:, 5] < len(labels))
            & (rows[:, 5] == np.floor(rows[:, 5]))
        ]
        boxes = []
        for x1, y1, x2, y2, confidence, cls in rows[np.argsort(rows[:, 4])[::-1]][:100]:
            x1 = max(0.0, min(float(width), (float(x1) - pad_x) / scale))
            x2 = max(0.0, min(float(width), (float(x2) - pad_x) / scale))
            y1 = max(0.0, min(float(height), (float(y1) - pad_y) / scale))
            y2 = max(0.0, min(float(height), (float(y2) - pad_y) / scale))
            if x2 > x1 and y2 > y1:
                boxes.append(
                    dict(
                        class_id=int(cls),
                        label=labels[int(cls)],
                        confidence=float(confidence),
                        x=x1,
                        y=y1,
                        width=x2 - x1,
                        height=y2 - y1,
                    )
                )
        return boxes
    if predictions.ndim != 3 or predictions.shape[0] != 1 or predictions.shape[1] != 84:
        raise ValueError("Modelo incompatível: esperado detector COCO [1,84,N] ou [1,N,6].")
    rows = predictions[0].T
    rows = rows[np.isfinite(rows).all(axis=1)]
    class_ids = rows[:, 4:].argmax(axis=1)
    scores = rows[:, 4:].max(axis=1)
    candidates = np.flatnonzero(scores >= 0.35)
    candidates = candidates[np.argsort(scores[candidates])[::-1]][:3000]
    boxes, kept_scores, kept_classes = [], [], []
    for i in candidates:
        cx, cy, w, h = rows[i, :4]
        x1 = max(0.0, min(float(width), (float(cx - w / 2) - pad_x) / scale))
        y1 = max(0.0, min(float(height), (float(cy - h / 2) - pad_y) / scale))
        x2 = max(0.0, min(float(width), (float(cx + w / 2) - pad_x) / scale))
        y2 = max(0.0, min(float(height), (float(cy + h / 2) - pad_y) / scale))
        if x2 > x1 and y2 > y1:
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            kept_scores.append(float(scores[i]))
            kept_classes.append(int(class_ids[i]))
    selected = []
    for cls in sorted(set(kept_classes)):
        indices = [i for i, c in enumerate(kept_classes) if c == cls]
        keep = cv2.dnn.NMSBoxes(
            [boxes[i] for i in indices], [kept_scores[i] for i in indices], 0.35, 0.45
        )
        selected.extend(indices[int(i)] for i in np.asarray(keep).flatten())
    return [
        dict(
            class_id=kept_classes[i],
            label=LABELS[kept_classes[i]],
            confidence=kept_scores[i],
            x=boxes[i][0],
            y=boxes[i][1],
            width=boxes[i][2],
            height=boxes[i][3],
        )
        for i in sorted(selected, key=lambda i: kept_scores[i], reverse=True)[:100]
    ]


# Função para selecionar a sessão ONNX adaptada, verificando compatibilidade, carregando o modelo e retornando a sessão, caminho, rótulos e avisos
def selected_session(project_id=None, live=False):
    """Warm and verify candidates before use; keep the original resident for recovery."""
    global _adapted_session, _adapted_path, _adapted_labels, _adapted_model
    from app.vision import learning

    ort = importlib.import_module("onnxruntime")
    np = importlib.import_module("numpy")
    key = learning.scope(project_id)
    pointer = learning.root() / "active" / f"{key}.json"
    if live and (learning.root() / "active" / f"{key}-yolo26s.json").exists():
        pointer = learning.root() / "active" / f"{key}-yolo26s.json"
    path = None
    labels = LABELS
    warning = None
    version: dict = {}
    try:
        if pointer.exists():
            version = json.loads(pointer.read_text(encoding="utf-8"))
            path = Path(version["onnx"]).resolve()
            if (
                not path.is_relative_to((learning.root() / "runs").resolve())
                or version.get("scope") != key
            ):
                raise ValueError("Versão de modelo fora do projeto ou diretório permitido.")
            labels = version["names_pt"]
            if not isinstance(labels, list) or labels[:80] != LABELS or len(labels) > 200:
                raise ValueError("Catálogo de classes incompatível.")
        elif live:
            config_file = learning.root() / "live.json"
            if config_file.exists():
                config = json.loads(config_file.read_text(encoding="utf-8"))
                if config.get("model") in ("yolo26n", "yolo26s"):
                    path = learning.root().parent / "models" / (config["model"] + ".onnx")
                    version = {"sha256": config["sha256"]}
        if path is not None:
            with _adapted_lock:
                if _adapted_path != path:
                    if hashlib.sha256(path.read_bytes()).hexdigest() != version["sha256"]:
                        raise ValueError("Checksum divergente no modelo selecionado.")
                    options = ort.SessionOptions()
                    options.intra_op_num_threads = 3
                    options.inter_op_num_threads = 1
                    session = ort.InferenceSession(
                        str(path), sess_options=options, providers=["CPUExecutionProvider"]
                    )
                    spec = session.get_inputs()[0]
                    if spec.shape != [1, 3, 640, 640] or spec.type != "tensor(float)":
                        raise ValueError("Entrada do modelo incompatível.")
                    output = session.run(None, {spec.name: np.zeros((1, 3, 640, 640), np.float32)})[
                        0
                    ]
                    if output.shape != (1, 300, 6) or not np.isfinite(output).all():
                        raise ValueError("Saída do modelo incompatível.")
                    _adapted_session = session
                    _adapted_path = path
                    _adapted_labels = labels
                    _adapted_model = version.get("model", path.stem)
                return _adapted_session, path, _adapted_labels, None
    except Exception as exc:
        warning = f"Modelo adaptado indisponível; usando referência original. {exc}"
        if pointer.exists():
            # Preserve the failed manifest and atomically restore the prior approved version.
            try:
                version = json.loads(pointer.read_text(encoding="utf-8"))
                pointer.replace(
                    pointer.with_suffix(f".failed-{int(__import__('time').time())}.json")
                )
                if version.get("previous"):
                    learning.atomic_json(pointer, version["previous"])
                with learning.connect() as conn:
                    learning.event(
                        conn, key, "Reversão automática: falha ao carregar a versão adaptada."
                    )
            except (OSError, ValueError):
                pass
    return _session, _loaded_path or model_path(), LABELS, warning


# Função para detectar objetos em uma imagem codificada em base64, processando a imagem, redimensionando-a, aplicando o modelo YOLOv8 e retornando as detecções com informações de tempo e modelo
def supplemental_session(project_id, model):
    """Load an isolated new-class model without replacing the base detector."""
    global _supplemental_session, _supplemental_path
    if model not in ("yolo26s", "yolo26x"):
        return None, None
    from app.vision import learning

    key = learning.scope(project_id)
    pointer = learning.root() / "active" / f"{key}-supplement-{model}.json"
    if not pointer.exists():
        return None, None
    ort = importlib.import_module("onnxruntime")
    np = importlib.import_module("numpy")
    try:
        version = json.loads(pointer.read_text(encoding="utf-8"))
        path = Path(version["onnx"]).resolve()
        if (
            not path.is_relative_to((learning.root() / "runs").resolve())
            or version.get("scope") != key
            or version.get("model") != model
        ):
            raise ValueError("Complemento de classes fora do projeto ou modelo incompatível.")
        labels = version.get("names_pt")
        class_ids = version.get("class_ids")
        if (
            version.get("metrics", {}).get("class_only_provisional") is not True
            or not isinstance(labels, list)
            or labels[:80] != LABELS
            or len(labels) > 200
            or not isinstance(class_ids, list)
            or not class_ids
            or any(
                type(index) is not int or index < 80 or index >= len(labels) for index in class_ids
            )
            or len(set(class_ids)) != len(class_ids)
        ):
            raise ValueError("Catálogo de classes provisório incompatível.")
        with _supplemental_lock:
            if _supplemental_path != path:
                if hashlib.sha256(path.read_bytes()).hexdigest() != version["sha256"]:
                    raise ValueError("Checksum divergente no complemento de classes.")
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(
                    str(path), sess_options=options, providers=["CPUExecutionProvider"]
                )
                spec = session.get_inputs()[0]
                if spec.shape != [1, 3, 640, 640] or spec.type != "tensor(float)":
                    raise ValueError("Entrada do complemento de classes incompatível.")
                output = session.run(None, {spec.name: np.zeros((1, 3, 640, 640), np.float32)})[0]
                if output.shape != (1, 300, 6) or not np.isfinite(output).all():
                    raise ValueError("Saída do complemento de classes incompatível.")
                _supplemental_session = session
                _supplemental_path = path
            return (_supplemental_session, path, labels, class_ids), None
    except Exception as exc:
        warning = f"Complemento provisório indisponível; detector principal preservado. {exc}"
        try:
            version = json.loads(pointer.read_text(encoding="utf-8"))
            pointer.replace(pointer.with_suffix(f".failed-{int(__import__('time').time())}.json"))
            if version.get("previous_supplemental"):
                learning.atomic_json(pointer, version["previous_supplemental"])
            with learning.connect() as conn:
                learning.event(
                    conn,
                    key,
                    "Complemento provisório indisponível; detector principal preservado. "
                    + str(exc)[:160],
                )
        except (OSError, ValueError):
            pass
        return None, warning


def class_only_detections(detections, class_ids):
    allowed = set(class_ids)
    return [detection for detection in detections if detection["class_id"] in allowed]


def merge_supplemental_detections(base_detections, supplemental_detections, labels, class_ids):
    class_names = {labels[index] for index in class_ids}
    retained = [detection for detection in base_detections if detection["label"] not in class_names]
    return retained + class_only_detections(supplemental_detections, class_ids)


def detect(content_b64: str, project_id=None, live=False) -> dict:
    global _session
    import cv2

    np = importlib.import_module("numpy")

    if len(content_b64) > 16_000_000:
        raise ValueError("Imagem muito grande (máximo 12 MB).")
    data = base64.b64decode(content_b64, validate=True)
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Imagem inválida. Use PNG ou JPEG.")
    height, width = image.shape[:2]
    if width * height > 20_000_000:
        raise ValueError("Use uma imagem de até 20 megapixels.")
    load()
    session, path, labels, warning = selected_session(project_id, live)
    spec = session.get_inputs()[0]
    shape = spec.shape
    size = shape[2] if isinstance(shape[2], int) else (320 if path.stem == "yolov8n" else 640)
    if size < 32 or size > 640 or (isinstance(shape[3], int) and shape[3] != size):
        raise ValueError("Use um modelo ONNX com entrada quadrada de até 640 px.")
    started = perf_counter()
    scale = min(size / width, size / height)
    new_w, new_h = round(width * scale), round(height * scale)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    resized = cv2.resize(image, (new_w, new_h))
    padded = np.full((size, size, 3), 114, dtype=np.uint8)
    padded[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    tensor = (
        np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
    )
    output = session.run(None, {spec.name: tensor})[0]
    detections = postprocess(output, width, height, scale, pad_x, pad_y, labels)
    model_name = (
        f"{_adapted_model} adaptado {path.parents[2].name[:8]}"
        if path.is_relative_to(
            Path(os.environ.get("SOLARIS_STORAGE", "storage")).resolve() / "learning/runs"
        )
        else path.stem
    )
    model_kind = (
        _adapted_model
        if path.is_relative_to(
            Path(os.environ.get("SOLARIS_STORAGE", "storage")).resolve() / "learning/runs"
        )
        else path.stem
    )
    supplemental, supplement_warning = supplemental_session(project_id, model_kind)
    if supplemental:
        class_session, _, class_labels, class_ids = supplemental
        class_spec = class_session.get_inputs()[0]
        class_size = class_spec.shape[2]
        class_scale = min(class_size / width, class_size / height)
        class_w, class_h = round(width * class_scale), round(height * class_scale)
        class_pad_x, class_pad_y = (class_size - class_w) // 2, (class_size - class_h) // 2
        class_resized = cv2.resize(image, (class_w, class_h))
        class_padded = np.full((class_size, class_size, 3), 114, dtype=np.uint8)
        class_padded[class_pad_y : class_pad_y + class_h, class_pad_x : class_pad_x + class_w] = (
            class_resized
        )
        class_tensor = (
            np.ascontiguousarray(
                class_padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32
            )
            / 255.0
        )
        class_output = class_session.run(None, {class_spec.name: class_tensor})[0]
        class_detections = postprocess(
            class_output, width, height, class_scale, class_pad_x, class_pad_y, class_labels
        )
        detections = merge_supplemental_detections(
            detections, class_detections, class_labels, class_ids
        )
        supplemental_labels = {class_labels[index] for index in class_ids}
        model_name = f"{model_kind} + classes provisórias"
        warning = "; ".join(
            value
            for value in (
                warning,
                f"Classes provisórias: {', '.join(sorted(supplemental_labels))}; treinadas com marcações humanas, sem generalização comprovada.",
            )
            if value
        )
    elif supplement_warning:
        warning = "; ".join(value for value in (warning, supplement_warning) if value)
    return dict(
        detections=detections,
        width=width,
        height=height,
        elapsed_ms=round((perf_counter() - started) * 1000, 1),
        model=model_name,
        device="CPU",
        model_warning=warning,
    )
