"""Extração de embeddings visuais com CLIP ViT-B/32 ONNX.

Matematicamente, CLIP mapeia uma região de imagem para um vetor
x ∈ ℝ⁵¹² no espaço latente visual. A normalização L2

    x̂ = x / ‖x‖₂   onde ‖x‖₂ = √(x₁² + … + x₅₁₂²)

converte distância euclidiana em distância angular (cosseno), tornando
a similaridade invariante à escala — fundamento direto de Álgebra Linear,
Aula 01 da série "A Matemática por Trás do Machine Learning".

CLAHE (Contrast Limited Adaptive Histogram Equalization) é aplicado
ao canal L do espaço LAB antes de enviar o crop para o CLIP, conforme
o notebook 02 da Especialização em Visão Computacional (equalização
adaptativa de histogramas para robustez a variações de iluminação).

Referências teóricas usadas neste módulo:
  - Aula 01 (Representação): vetores, normalização, produto interno.
  - Notebook 02 (Fundamentos de Imagens): CLAHE, espaço LAB.
  - "Mathematics for Machine Learning" (Deisenroth et al.): normas, PCA.
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np  # noqa: F401

# Dimensão dos embeddings CLIP ViT-B/32
EMBED_DIM = 512

# Tamanho de entrada do encoder visual CLIP ViT-B/32
_CLIP_SIZE = 224

# Normalização de pixel ImageNet (média e desvio padrão por canal RGB)
# Derivada dos parâmetros de pré-treinamento do CLIP — não alterar.
_MEAN = (0.48145466, 0.4578275, 0.40821073)
_STD = (0.26862954, 0.26130258, 0.27577711)

# Globals de sessão ONNX
_clip_session = None
_clip_path: Path | None = None
_clip_load_error: str | None = None
_clip_loading: bool = False
_clip_lock = threading.Lock()
_clip_thread: threading.Thread | None = None


# ---------------------------------------------------------------------------
# Localização do modelo
# ---------------------------------------------------------------------------

def clip_model_path() -> Path | None:
    """Retorna o caminho para clip-vit-b32-visual.onnx ou None se ausente."""
    local = Path(os.environ.get("SOLARIS_STORAGE", "storage")) / "models"
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3])) / "models"
    names = ("clip-vit-b32-visual.onnx", "clip_vit_b32_visual.onnx")
    for directory in (local, bundled):
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Carregamento do modelo
# ---------------------------------------------------------------------------

def load_clip() -> None:
    global _clip_session, _clip_path, _clip_load_error, _clip_loading
    with _clip_lock:
        if _clip_session is not None:
            return
        _clip_loading = True
        _clip_load_error = None
        try:
            np = importlib.import_module("numpy")
            ort = importlib.import_module("onnxruntime")
            path = clip_model_path()
            if path is None:
                _clip_load_error = (
                    "clip-vit-b32-visual.onnx não encontrado. "
                    "Execute scripts/download_clip.py para baixar o modelo."
                )
                return
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            # Warmup com tensor nulo
            spec = session.get_inputs()[0]
            dummy = np.zeros((1, 3, _CLIP_SIZE, _CLIP_SIZE), dtype=np.float32)
            out = session.run(None, {spec.name: dummy})[0]
            if out.shape[-1] != EMBED_DIM:
                _clip_load_error = f"Modelo CLIP incompatível: embedding dim={out.shape[-1]}, esperado {EMBED_DIM}."
                return
            _clip_session = session
            _clip_path = path
        except Exception as exc:
            _clip_load_error = str(exc)
        finally:
            _clip_loading = False


def start_loading_clip() -> None:
    global _clip_thread
    if _clip_thread is None:
        def _bg():
            try:
                load_clip()
            except Exception:
                pass
        _clip_thread = threading.Thread(target=_bg, daemon=True, name="solaris-clip-load")
        _clip_thread.start()


def clip_status() -> dict:
    available = clip_model_path()
    return {
        "clip_available": available is not None,
        "clip_loaded": _clip_session is not None,
        "clip_loading": _clip_loading,
        "clip_error": _clip_load_error,
    }


# ---------------------------------------------------------------------------
# Pré-processamento: CLAHE + redimensionamento + normalização ImageNet
# ---------------------------------------------------------------------------

def _preprocess_crop(image_bgr, box: dict):
    """Extrai e pré-processa um crop para o CLIP.

    Pipeline:
    1. Extrai ROI com margem de 10 px (melhora o contexto visual).
    2. CLAHE no canal L do espaço LAB — equalização adaptativa de histograma
       (notebook 02 da Especialização em Visão Computacional).
    3. Redimensiona para 224×224.
    4. Converte BGR → RGB e normaliza com média/desvio ImageNet.
    5. Transpõe para [C, H, W] e adiciona batch dim.
    """
    import cv2

    np = importlib.import_module("numpy")
    h, w = image_bgr.shape[:2]
    margin = 10
    x1 = max(0, int(box["x"]) - margin)
    y1 = max(0, int(box["y"]) - margin)
    x2 = min(w, int(box["x"] + box["width"]) + margin)
    y2 = min(h, int(box["y"] + box["height"]) + margin)
    if x2 <= x1 or y2 <= y1:
        return None

    crop = image_bgr[y1:y2, x1:x2]

    # CLAHE: equalização adaptativa no canal L (luminância) do espaço LAB.
    # Referência: notebook 02, "Equalização de Histogramas".
    # Aplica sobre o canal de brilho para preservar a cor original.
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    crop = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Redimensiona para 224×224 (entrada do CLIP ViT-B/32).
    crop = cv2.resize(crop, (_CLIP_SIZE, _CLIP_SIZE), interpolation=cv2.INTER_LINEAR)

    # BGR → RGB, float32 em [0,1].
    rgb = crop[:, :, ::-1].astype(np.float32) / 255.0

    # Normalização ImageNet — subtrai média, divide por desvio padrão canal a canal.
    # Fórmula: x̂_c = (x_c - μ_c) / σ_c  para c ∈ {R, G, B}
    mean = np.array(_MEAN, dtype=np.float32)
    std = np.array(_STD, dtype=np.float32)
    rgb = (rgb - mean) / std

    # [H, W, C] → [1, C, H, W]
    tensor = rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
    return tensor


# ---------------------------------------------------------------------------
# Extração de embeddings
# ---------------------------------------------------------------------------

def l2_normalize(vec):
    """Normalização L2: x̂ = x / ‖x‖₂ (Álgebra Linear, Aula 01)."""
    np = importlib.import_module("numpy")
    norm = np.linalg.norm(vec)
    if norm < 1e-12:
        return vec
    return vec / norm


def embed_crops(image_bgr, detections: list[dict]) -> list[tuple[dict, list[float]]]:
    """Extrai embedding CLIP para cada detecção.

    Retorna lista de (detecção, embedding_l2_normalizado).
    Detecções sem crop válido são omitidas.
    Retorna lista vazia se o CLIP não estiver carregado.
    """
    with _clip_lock:
        session = _clip_session
    if session is None:
        return []

    np = importlib.import_module("numpy")
    spec = session.get_inputs()[0]
    results: list[tuple[dict, list[float]]] = []

    for det in detections:
        tensor = _preprocess_crop(image_bgr, det)
        if tensor is None:
            continue
        try:
            raw = session.run(None, {spec.name: tensor})[0]  # shape [1, 512]
            vec = l2_normalize(raw[0].astype(np.float64))
            results.append((det, vec.tolist()))
        except Exception:
            continue

    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores L2-normalizados.

    Como ambos são unitários: cos(θ) = a·b (produto interno).
    Fórmula: Álgebra Linear, Aula 01.
    """
    np = importlib.import_module("numpy")
    return float(np.dot(np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)))
