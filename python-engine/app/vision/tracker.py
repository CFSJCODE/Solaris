"""Rastreador de múltiplos objetos baseado em correspondência IoU entre frames.

Implementa SORT-lite (Simple Online Realtime Tracking sem filtro de Kalman),
adaptado para inferência CPU-only no SOLARIS.

Matemática:
  - IoU (Jaccard): mede sobreposição de caixas delimitadoras entre frames consecutivos.
  - Correspondência gulosa: pares (detecção, track) ordenados por IoU decrescente.
  - Threshold de IoU configurable; tracks morrem após _MAX_AGE frames sem match.

Referência teórica: Especialização em Visão Computacional (Carlos Melo / Sigmoidal),
notebooks 04 e 05; padrão ByteTrack/SORT com supervision.sv.ByteTracker.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

_IOU_THRESHOLD: float = 0.30
_MAX_AGE: int = 5   # frames sem match antes de encerrar o track
_MIN_HITS: int = 2  # confirmações para o track ser considerado estável


# ---------------------------------------------------------------------------
# IoU entre caixas [x, y, w, h]
# ---------------------------------------------------------------------------

def _iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-Union entre duas caixas [x, y, w, h]."""
    ax2, ay2 = a[0] + a[2], a[1] + a[3]
    bx2, by2 = b[0] + b[2], b[1] + b[3]
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0.0 else 0.0


# ---------------------------------------------------------------------------
# Ponto dentro de polígono (Ray Casting — ponto-no-polígono)
# Usado pelo monitoramento de zonas.
# ---------------------------------------------------------------------------

def point_in_polygon(px: float, py: float, polygon: list[tuple[float, float]]) -> bool:
    """Retorna True se (px, py) está dentro do polígono convexo ou côncavo.

    Algoritmo de ray-casting:
      Lança um raio horizontal a partir do ponto e conta o número de
      interseções com as arestas do polígono. Impar → dentro; par → fora.
    """
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Track interno
# ---------------------------------------------------------------------------

@dataclass
class _Track:
    track_id: int
    box: list[float]    # [x, y, w, h] — atualizado a cada match
    class_id: int
    label: str
    confidence: float
    hits: int = 1       # número de vezes que o track foi confirmado
    age: int = 0        # frames desde o último match (0 = matchou este frame)

    @property
    def stable(self) -> bool:
        """Track é estável quando confirmado >= _MIN_HITS vezes e vivo."""
        return self.hits >= _MIN_HITS


# ---------------------------------------------------------------------------
# Rastreador público
# ---------------------------------------------------------------------------

class ObjectTracker:
    """Rastreador por sessão de câmera — instanciar um por feed.

    Uso:
        tracker = ObjectTracker()
        # a cada frame:
        enriched = tracker.update(detections)
        # cada detecção ganha a chave "track_id" (int >= 1, ou -1 se ainda instável)
    """

    def __init__(self) -> None:
        self._tracks: list[_Track] = []
        self._next_id: int = 1
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    def update(self, detections: list[dict]) -> list[dict]:
        """Atualiza os tracks com as detecções do frame atual.

        Parâmetros
        ----------
        detections:
            Lista de dicts com chaves ``x``, ``y``, ``width``, ``height``,
            ``class_id``, ``label``, ``confidence`` — mesmo formato de
            ``detector.detect()``.

        Retorno
        -------
        Lista com os mesmos dicts + chave ``track_id``:
        - Valor >= 1: ID estável (hit confirmado).
        - Valor -1: track recém-criado, ainda aguardando confirmação.
        """
        with self._lock:
            return self._update_locked(detections)

    def reset(self) -> None:
        """Reinicia o rastreador (troca de câmera, nova sessão de vídeo)."""
        with self._lock:
            self._tracks.clear()
            self._next_id = 1

    def active_count(self) -> int:
        """Quantidade de tracks estáveis e vivos neste momento."""
        with self._lock:
            return sum(1 for t in self._tracks if t.stable and t.age == 0)

    # ------------------------------------------------------------------
    # Núcleo interno (chamado com o lock já adquirido)
    # ------------------------------------------------------------------

    def _update_locked(self, detections: list[dict]) -> list[dict]:
        # 1. Envelhece todos os tracks.
        for t in self._tracks:
            t.age += 1

        # 2. Monta a lista de (iou, idx_det, idx_track) e ordena por IoU ↓.
        pairs: list[tuple[float, int, int]] = []
        for di, det in enumerate(detections):
            det_box = [det["x"], det["y"], det["width"], det["height"]]
            for ti, track in enumerate(self._tracks):
                if track.class_id != det["class_id"]:
                    continue
                score = _iou(det_box, track.box)
                if score >= _IOU_THRESHOLD:
                    pairs.append((score, di, ti))

        pairs.sort(key=lambda p: p[0], reverse=True)

        # 3. Correspondência gulosa — cada índice é usado no máximo uma vez.
        matched_det: set[int] = set()
        matched_trk: set[int] = set()
        det_to_track: dict[int, int] = {}  # di → track_id

        for _, di, ti in pairs:
            if di in matched_det or ti in matched_trk:
                continue
            track = self._tracks[ti]
            track.box = [detections[di]["x"], detections[di]["y"],
                         detections[di]["width"], detections[di]["height"]]
            track.confidence = detections[di]["confidence"]
            track.hits += 1
            track.age = 0
            det_to_track[di] = track.track_id
            matched_det.add(di)
            matched_trk.add(ti)

        # 4. Cria novos tracks para detecções sem match.
        for di, det in enumerate(detections):
            if di not in matched_det:
                new_track = _Track(
                    track_id=self._next_id,
                    box=[det["x"], det["y"], det["width"], det["height"]],
                    class_id=det["class_id"],
                    label=det["label"],
                    confidence=det["confidence"],
                )
                self._tracks.append(new_track)
                det_to_track[di] = new_track.track_id
                self._next_id += 1

        # 5. Remove tracks expirados.
        self._tracks = [t for t in self._tracks if t.age <= _MAX_AGE]

        # 6. Constrói o mapa track_id → stable para anotar as detecções.
        stable_ids: set[int] = {t.track_id for t in self._tracks if t.stable}

        # 7. Devolve detecções enriquecidas com track_id.
        result: list[dict] = []
        for di, det in enumerate(detections):
            d = dict(det)
            raw_id = det_to_track.get(di, -1)
            d["track_id"] = raw_id if raw_id in stable_ids else -1
            result.append(d)

        return result


# ---------------------------------------------------------------------------
# Filtragem por zona poligonal
# ---------------------------------------------------------------------------

def filter_by_zone(
    detections: list[dict],
    polygon: list[tuple[float, float]],
    *,
    use_center: bool = True,
) -> list[dict]:
    """Retorna apenas as detecções cujo ponto de referência está dentro do polígono.

    Parâmetros
    ----------
    detections:
        Lista de dicts com ``x``, ``y``, ``width``, ``height``.
    polygon:
        Lista de vértices (x, y) em pixels da imagem original.
    use_center:
        Se True (padrão), usa o centro da caixa como ponto de referência.
        Se False, usa o ponto inferior central (base da caixa), útil para pessoas.
    """
    result = []
    for det in detections:
        if use_center:
            px = det["x"] + det["width"] / 2.0
            py = det["y"] + det["height"] / 2.0
        else:
            px = det["x"] + det["width"] / 2.0
            py = det["y"] + det["height"]
        if point_in_polygon(px, py, polygon):
            result.append(det)
    return result


def count_in_zone(
    detections: list[dict],
    polygon: list[tuple[float, float]],
    *,
    label: str | None = None,
    use_center: bool = True,
) -> int:
    """Conta detecções dentro de uma zona; filtra por rótulo se especificado."""
    inside = filter_by_zone(detections, polygon, use_center=use_center)
    if label is not None:
        inside = [d for d in inside if d["label"] == label]
    return len(inside)
