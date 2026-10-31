"""Descoberta visual auto-supervisionada: embeddings CLIP de regiões + agrupamento incremental.

Fluxo: cada amostra coletada pela câmera tem caixas do detector (YOLO26 + OIV7). O worker de
aprendizado recorta essas regiões, extrai um vetor de aparência com o CLIP (só no runtime de
aprendizado, nunca no engine principal) e agrupa vetores parecidos sem rótulo humano. Um nome é
opcional; a sugestão vem da maioria dos rótulos do detector entre os membros e é apenas hipótese.

Conceitos aplicados (docs/conceitos-matematicos-aplicados.md):
- Representação vetorial e norma L2 (aula 1; MML cap. 3): vetores unitários, similaridade = cosseno.
- Modelos de mistura (MML cap. 11): cada grupo mantém média e variância (Welford) das
  similaridades dos membros ao centróide; o limiar de entrada é adaptativo (média − 2σ), limitado
  por um piso e um teto calibrados em quadros reais.
- Incerteza (notas): região quase empatada entre dois grupos fica "incerta" e não altera centróides.
- Risco empírico e independência (MML §8.2; AGENTS.md, regra 4): quadros vizinhos não são evidência
  independente. Mesma caixa (IoU) na mesma sessão em poucos segundos conta como a mesma vista; a
  estabilidade exige vistas independentes e mais de uma sessão.
- Qualidade visual e CLAHE (notebooks do ZIP de visão): recortes borrados, escuros ou estourados
  são descartados; CLAHE no canal L (LAB) reduz a sensibilidade à iluminação antes do CLIP.
- PCA (MML cap. 10): preparado, desligado por padrão — instável com poucas amostras.
Não substitui avaliação: grupos podem fundir objetos muito parecidos.
"""

# torch/transformers/PIL só existem no runtime de aprendizado; o engine nunca carrega o Encoder.
# pyright: reportMissingImports=false

from __future__ import annotations

import base64
import json
import math
import time
from collections import Counter

import numpy as np

from app.vision import learning as store

EMBEDDING_DIM = 512
# Calibrado em quadros reais (CLIP ViT-B/32): mesmo objeto ~0,86–0,93; objetos diferentes
# chegam a 0,78–0,89 (ex.: pessoa sentada x cadeira).
ASSIGN_THRESHOLD = 0.88  # limiar enquanto o grupo tem poucos membros
ADAPTIVE_FLOOR = 0.85  # o limiar adaptativo nunca desce abaixo disto
ADAPTIVE_CEILING = 0.92  # nem sobe acima disto (grupos compactos ainda crescem)
ADAPTIVE_MIN_MEMBERS = 4
AMBIGUITY_MARGIN = 0.015  # diferença mínima entre os dois melhores grupos
MERGE_THRESHOLD = 0.92  # cosseno entre centróides para unir dois grupos
SAME_VIEW_SECONDS = 10.0
SAME_VIEW_IOU = 0.5
MIN_REGION_PX = 24
MIN_CONFIDENCE = 0.35
MIN_SHARPNESS = 20.0  # variância do Laplaciano
MIN_BRIGHTNESS, MAX_BRIGHTNESS = 20.0, 240.0
STABLE_VIEWS = 10
STABLE_SESSIONS = 2
MAX_REGIONS_PER_SAMPLE = 12
PCA_ENABLED = False
PCA_COMPONENTS = 64


def ensure_schema(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS region_embeddings(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
        sample_id TEXT NOT NULL, box_index INTEGER NOT NULL, hint TEXT NOT NULL, source TEXT NOT NULL,
        box TEXT NOT NULL, vector BLOB NOT NULL, cluster_id INTEGER, created REAL NOT NULL,
        UNIQUE(scope, sample_id, box_index));
      CREATE INDEX IF NOT EXISTS region_embeddings_cluster ON region_embeddings(scope, cluster_id);
      CREATE TABLE IF NOT EXISTS visual_clusters(id INTEGER PRIMARY KEY, scope TEXT NOT NULL,
        centroid BLOB NOT NULL, size INTEGER NOT NULL, name TEXT, created REAL NOT NULL,
        updated REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS embedded_samples(scope TEXT NOT NULL, sample_id TEXT NOT NULL,
        created REAL NOT NULL, PRIMARY KEY(scope, sample_id));
    """)
    _add_columns(
        conn,
        "region_embeddings",
        {
            "session": "TEXT NOT NULL DEFAULT ''",
            "observed": "REAL NOT NULL DEFAULT 0",
            "independent": "INTEGER NOT NULL DEFAULT 1",
            "state": "TEXT NOT NULL DEFAULT 'grouped'",
        },
    )
    _add_columns(
        conn,
        "visual_clusters",
        {
            "views": "INTEGER NOT NULL DEFAULT 0",
            "sim_n": "INTEGER NOT NULL DEFAULT 0",
            "sim_mean": "REAL NOT NULL DEFAULT 0",
            "sim_m2": "REAL NOT NULL DEFAULT 0",
        },
    )


def _add_columns(conn, table, columns):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def to_blob(vector) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def normalize(vector) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm == 0:
        raise ValueError("Vetor de aparência inválido.")
    return vector / norm


def iou(a, b) -> float:
    """IoU entre caixas [x1, y1, x2, y2]."""
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def acceptance_threshold(sim_n, sim_mean, sim_m2) -> float:
    """Limiar adaptativo por grupo: média − 2σ das similaridades dos membros, limitado."""
    if sim_n < ADAPTIVE_MIN_MEMBERS:
        return ASSIGN_THRESHOLD
    std = math.sqrt(max(sim_m2 / (sim_n - 1), 0.0))
    return min(ADAPTIVE_CEILING, max(ADAPTIVE_FLOOR, sim_mean - 2 * std))


def quality_ok(crop) -> bool:
    """Descarta recortes borrados, escuros ou estourados antes de gastar CPU com o CLIP."""
    import cv2

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    return (
        MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS
        and float(cv2.Laplacian(gray, cv2.CV_64F).var()) >= MIN_SHARPNESS
    )


def clahe(crop):
    """Equalização adaptativa no canal L (LAB), preservando a cor."""
    import cv2

    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def regions(detections, width, height):
    """Caixas utilizáveis como recortes: confiança mínima, tamanho mínimo, dentro da imagem."""
    selected = []
    for index, box in enumerate(detections):
        if float(box.get("confidence", 0)) < MIN_CONFIDENCE:
            continue
        x1 = max(0, int(box["x"]))
        y1 = max(0, int(box["y"]))
        x2 = min(width, int(box["x"] + box["width"]))
        y2 = min(height, int(box["y"] + box["height"]))
        if x2 - x1 < MIN_REGION_PX or y2 - y1 < MIN_REGION_PX:
            continue
        selected.append((index, (x1, y1, x2, y2), str(box.get("label", "")), box.get("source", "")))
    selected.sort(key=lambda item: -float(detections[item[0]].get("confidence", 0)))
    return selected[:MAX_REGIONS_PER_SAMPLE]


def ranked_clusters(conn, key, vector):
    rows = conn.execute(
        "SELECT id,centroid,size,sim_n,sim_mean,sim_m2 FROM visual_clusters WHERE scope=?", (key,)
    ).fetchall()
    scored = [(float(np.dot(from_blob(row["centroid"]), vector)), row) for row in rows]
    return sorted(scored, key=lambda item: -item[0])


def assign(conn, key, vector, now=None):
    """Coloca um vetor normalizado no grupo mais parecido, cria um novo, ou devolve None (incerta).

    Incerta = os dois melhores grupos aceitariam o vetor quase com a mesma similaridade.
    """
    now = time.time() if now is None else now
    ranked = ranked_clusters(conn, key, vector)
    accepted = [
        (score, row)
        for score, row in ranked[:2]
        if score >= acceptance_threshold(row["sim_n"], row["sim_mean"], row["sim_m2"])
    ]
    if len(accepted) == 2 and accepted[0][0] - accepted[1][0] < AMBIGUITY_MARGIN:
        return None
    if accepted:
        score, row = accepted[0]
        size = int(row["size"])
        centroid = normalize(from_blob(row["centroid"]) * size + vector)
        # Welford: média e variância das similaridades ao centróide, sem guardar o histórico.
        n = int(row["sim_n"]) + 1
        delta = score - float(row["sim_mean"])
        mean = float(row["sim_mean"]) + delta / n
        m2 = float(row["sim_m2"]) + delta * (score - mean)
        conn.execute(
            "UPDATE visual_clusters SET centroid=?,size=?,sim_n=?,sim_mean=?,sim_m2=?,updated=? WHERE id=?",
            (to_blob(centroid), size + 1, n, mean, m2, now, row["id"]),
        )
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO visual_clusters(scope,centroid,size,created,updated) VALUES(?,?,1,?,?)",
        (key, to_blob(vector), now, now),
    )
    return cursor.lastrowid


def merge_close(conn, key, now=None) -> int:
    """Une grupos cujos centróides ficaram muito próximos; preserva o nome dado por pessoa."""
    now = time.time() if now is None else now
    merged = 0
    while True:
        rows = conn.execute(
            "SELECT id,centroid,size,name,views,sim_n,sim_mean,sim_m2 FROM visual_clusters "
            "WHERE scope=? ORDER BY size DESC,id",
            (key,),
        ).fetchall()
        pair = None
        for i, first in enumerate(rows):
            for second in rows[i + 1 :]:
                if first["name"] and second["name"] and first["name"] != second["name"]:
                    continue  # nomes humanos diferentes nunca são fundidos automaticamente
                score = float(np.dot(from_blob(first["centroid"]), from_blob(second["centroid"])))
                if score >= MERGE_THRESHOLD:
                    pair = (first, second)
                    break
            if pair:
                break
        if not pair:
            return merged
        keep, drop = pair
        size = int(keep["size"]) + int(drop["size"])
        centroid = normalize(
            from_blob(keep["centroid"]) * int(keep["size"])
            + from_blob(drop["centroid"]) * int(drop["size"])
        )
        # Combinação de Welford (Chan et al.) para as estatísticas de similaridade.
        na, nb = int(keep["sim_n"]), int(drop["sim_n"])
        n = na + nb
        delta = float(drop["sim_mean"]) - float(keep["sim_mean"])
        mean = float(keep["sim_mean"]) + delta * nb / n if n else 0.0
        m2 = float(keep["sim_m2"]) + float(drop["sim_m2"]) + (delta**2 * na * nb / n if n else 0)
        conn.execute(
            "UPDATE visual_clusters SET centroid=?,size=?,views=?,sim_n=?,sim_mean=?,sim_m2=?,"
            "name=coalesce(name,?),updated=? WHERE id=?",
            (
                to_blob(centroid),
                size,
                int(keep["views"]) + int(drop["views"]),
                n,
                mean,
                m2,
                drop["name"],
                now,
                keep["id"],
            ),
        )
        conn.execute(
            "UPDATE region_embeddings SET cluster_id=? WHERE scope=? AND cluster_id=?",
            (keep["id"], key, drop["id"]),
        )
        conn.execute("DELETE FROM visual_clusters WHERE id=?", (drop["id"],))
        merged += 1


def same_view(conn, key, cluster_id, session, observed, box) -> bool:
    """Mesma caixa (IoU) na mesma sessão poucos segundos antes: é a mesma vista do objeto."""
    if not session:
        return False
    for row in conn.execute(
        "SELECT box FROM region_embeddings WHERE scope=? AND cluster_id=? AND session=? "
        "AND abs(observed-?)<=?",
        (key, cluster_id, session, observed, SAME_VIEW_SECONDS),
    ):
        if iou(json.loads(row["box"]), box) >= SAME_VIEW_IOU:
            return True
    return False


def store_region(
    conn, key, sample_id, box_index, box, hint, source, vector, session="", observed=0.0, now=None
):
    now = time.time() if now is None else now
    vector = normalize(vector)
    if vector.shape != (EMBEDDING_DIM,):
        raise ValueError("Dimensão do vetor de aparência incompatível.")
    cluster_id = assign(conn, key, vector, now)
    independent = cluster_id is not None and not same_view(
        conn, key, cluster_id, session, observed, box
    )
    conn.execute(
        "INSERT OR IGNORE INTO region_embeddings(scope,sample_id,box_index,hint,source,box,vector,"
        "cluster_id,created,session,observed,independent,state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            key,
            sample_id,
            box_index,
            hint,
            source,
            json.dumps(list(box)),
            to_blob(vector),
            cluster_id,
            now,
            session,
            observed,
            int(independent),
            "grouped" if cluster_id is not None else "uncertain",
        ),
    )
    if independent:
        conn.execute("UPDATE visual_clusters SET views=views+1 WHERE id=?", (cluster_id,))
    return cluster_id


def rebuild(conn, key) -> int:
    """Refaz os grupos a partir dos vetores já extraídos (sem CLIP), p. ex. após calibrar limiares.

    Grupos com nome dado por pessoa são preservados com seus membros; só os demais são refeitos.
    """
    named = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM visual_clusters WHERE scope=? AND name IS NOT NULL", (key,)
        )
    }
    placeholders = ",".join("?" * len(named))
    keep_clause = f" AND id NOT IN ({placeholders})" if named else ""
    conn.execute(f"DELETE FROM visual_clusters WHERE scope=?{keep_clause}", (key, *named))
    rows = conn.execute(
        "SELECT id,vector,cluster_id,session,observed,box FROM region_embeddings "
        "WHERE scope=? ORDER BY observed,id",
        (key,),
    ).fetchall()
    moved = 0
    for row in rows:
        if row["cluster_id"] in named:
            continue
        conn.execute("UPDATE region_embeddings SET cluster_id=NULL WHERE id=?", (row["id"],))
        cluster_id = assign(conn, key, from_blob(row["vector"]))
        independent = cluster_id is not None and not same_view(
            conn, key, cluster_id, row["session"], row["observed"], json.loads(row["box"])
        )
        conn.execute(
            "UPDATE region_embeddings SET cluster_id=?,independent=?,state=? WHERE id=?",
            (
                cluster_id,
                int(independent),
                "grouped" if cluster_id is not None else "uncertain",
                row["id"],
            ),
        )
        if independent:
            conn.execute("UPDATE visual_clusters SET views=views+1 WHERE id=?", (cluster_id,))
        moved += 1
    merge_close(conn, key)
    return moved


def pca_basis(vectors, components=PCA_COMPONENTS):
    """Base PCA (MML cap. 10) para compactar descritores. Desligada por padrão (PCA_ENABLED)."""
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or len(matrix) <= components:
        raise ValueError("Amostras insuficientes para PCA estável.")
    mean = matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(matrix - mean, full_matrices=False)
    return mean, vt[:components]


def pending_samples(conn, key, limit):
    return conn.execute(
        "SELECT s.id,s.image,s.detections,s.session,s.created FROM samples s WHERE s.scope=? "
        "AND s.state!='archived' AND NOT EXISTS(SELECT 1 FROM embedded_samples e "
        "WHERE e.scope=s.scope AND e.sample_id=s.id) ORDER BY s.created LIMIT ?",
        (key, limit),
    ).fetchall()


class Encoder:
    """CLIP ViT-B/32 em CPU (runtime de aprendizado). Carregado só quando há trabalho."""

    def __init__(self, model_dir):
        import torch
        from transformers import CLIPModel, CLIPProcessor

        torch.set_num_threads(2)
        self.torch = torch
        self.processor = CLIPProcessor.from_pretrained(model_dir, local_files_only=True)
        self.model = CLIPModel.from_pretrained(model_dir, local_files_only=True).eval()

    def embed(self, crops_bgr):
        from PIL import Image

        images = [Image.fromarray(clahe(crop)[:, :, ::-1]) for crop in crops_bgr]
        inputs = self.processor(images=images, return_tensors="pt")
        with self.torch.inference_mode():
            features = self.model.get_image_features(**inputs)
        return features.cpu().numpy()


def process_pending(key, encoder, limit=4) -> int:
    """Embeda as regiões de até `limit` amostras novas e atualiza os grupos. Retorna regiões."""
    import cv2

    with store.connect() as conn:
        ensure_schema(conn)
        rows = pending_samples(conn, key, limit)
    total = skipped = 0
    for row in rows:
        image = cv2.imread(str(store.root() / row["image"]))
        found, vectors = [], []
        if image is not None:
            height, width = image.shape[:2]
            candidates = regions(json.loads(row["detections"] or "[]"), width, height)
            found = [
                r for r in candidates if quality_ok(image[r[1][1] : r[1][3], r[1][0] : r[1][2]])
            ]
            skipped += len(candidates) - len(found)
            if found:
                vectors = encoder.embed(
                    [image[y1:y2, x1:x2] for _, (x1, y1, x2, y2), _, _ in found]
                )
        with store.connect() as conn:
            ensure_schema(conn)
            for (index, box, hint, source), vector in zip(found, vectors, strict=True):
                store_region(
                    conn,
                    key,
                    row["id"],
                    index,
                    box,
                    hint,
                    source,
                    vector,
                    session=row["session"],
                    observed=float(row["created"]),
                )
                total += 1
            conn.execute(
                "INSERT OR IGNORE INTO embedded_samples(scope,sample_id,created) VALUES(?,?,?)",
                (key, row["id"], time.time()),
            )
    if rows:
        with store.connect() as conn:
            merge_close(conn, key)
            count = conn.execute(
                "SELECT count(*) FROM visual_clusters WHERE scope=?", (key,)
            ).fetchone()[0]
            store.event(
                conn,
                key,
                f"Descoberta visual: {total} regiões agrupadas ({skipped} descartadas por "
                f"qualidade); {count} grupos de objetos.",
            )
    return total


def thumbnail(sample_path, box, size=96):
    import cv2

    image = cv2.imread(str(sample_path))
    if image is None:
        return None
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    scale = size / max(crop.shape[:2])
    crop = cv2.resize(
        crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale)))
    )
    ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(encoded.tobytes()).decode() if ok else None


def list_clusters(project_id, limit=60):
    """Grupos para a interface: vistas, sessões, nome opcional, sugestão do detector e miniatura."""
    key = store.scope(project_id)
    with store.connect() as conn:
        ensure_schema(conn)
        clusters = conn.execute(
            "SELECT id,size,views,name,updated,centroid FROM visual_clusters WHERE scope=? "
            "ORDER BY views DESC,size DESC,updated DESC LIMIT ?",
            (key, limit),
        ).fetchall()
        result = []
        for cluster in clusters:
            members = conn.execute(
                "SELECT r.hint,r.box,r.vector,r.session,s.image FROM region_embeddings r "
                "JOIN samples s ON s.scope=r.scope AND s.id=r.sample_id "
                "WHERE r.scope=? AND r.cluster_id=?",
                (key, cluster["id"]),
            ).fetchall()
            hints = Counter(m["hint"] for m in members if m["hint"])
            hint, votes = hints.most_common(1)[0] if hints else ("", 0)
            sessions = len({m["session"] for m in members if m["session"]})
            centroid = from_blob(cluster["centroid"])
            cover = (
                max(members, key=lambda m: float(np.dot(from_blob(m["vector"]), centroid)))
                if members
                else None
            )
            result.append(
                {
                    "id": cluster["id"],
                    "size": cluster["size"],
                    "views": cluster["views"],
                    "sessions": sessions,
                    "name": cluster["name"],
                    "suggestion": hint,
                    "suggestion_share": round(votes / len(members), 2) if members else 0,
                    "stable": cluster["views"] >= STABLE_VIEWS and sessions >= STABLE_SESSIONS,
                    "updated": cluster["updated"],
                    "thumbnail": thumbnail(store.root() / cover["image"], json.loads(cover["box"]))
                    if cover
                    else None,
                }
            )
        regions_total, uncertain = conn.execute(
            "SELECT count(*),coalesce(sum(state='uncertain'),0) FROM region_embeddings WHERE scope=?",
            (key,),
        ).fetchone()
    return {
        "clusters": result,
        "regions": regions_total,
        "uncertain": uncertain,
        "stable_views": STABLE_VIEWS,
        "stable_sessions": STABLE_SESSIONS,
    }


def rename_cluster(project_id, cluster_id, name):
    key = store.scope(project_id)
    name = (name or "").strip()[:60] or None
    if type(cluster_id) is not int:
        raise ValueError("Grupo inválido.")
    with store.connect() as conn:
        ensure_schema(conn)
        changed = conn.execute(
            "UPDATE visual_clusters SET name=?,updated=? WHERE id=? AND scope=?",
            (name, time.time(), cluster_id, key),
        ).rowcount
        if not changed:
            raise ValueError("Grupo não encontrado neste projeto.")
    return {"id": cluster_id, "name": name}
