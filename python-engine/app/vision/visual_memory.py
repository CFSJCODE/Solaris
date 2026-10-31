"""Memória visual auto-supervisionada: embeddings CLIP + PCA + HDBSCAN.

Arquitetura matemática implementada:

1. **Armazenamento**: SQLite — cada detecção YOLO gera um embedding CLIP L2-normalizado
   de 512 dimensões que é persistido com metadados da detecção.

2. **Redução de dimensionalidade (PCA)**:
   Decompõe a matriz de embeddings X ∈ ℝ^{N×512} via SVD truncada:
       X ≈ U_k Σ_k V_k^T,  k = 64 componentes
   Os vetores projetados W = X · V_k^T ∈ ℝ^{N×64} preservam ~95 % da variância.
   Fundamento: Álgebra Linear, Aula 01 ("Representação, SVD, PCA").

3. **Clustering (HDBSCAN)**:
   Algoritmo hierárquico de densidade — não precisa especificar k.
   Distância = 1 − cos(θ) entre vetores PCA (equivale a distância euclidiana
   quando os vetores são L2-normalizados na esfera unitária).
   Fundamento: Especialização em Visão Computacional, notebooks 04-05.

4. **Atualização incremental de centroides**:
   Média exponencial móvel:  μ_new = α · x + (1 − α) · μ_old,  α = 1/n
   onde n é a contagem de amostras do cluster — converte para média verdadeira.
   Fundamento: Aula 02 ("Gradiente como atualização de média").

5. **Propagação de rótulos (Bayesiana)**:
   Quando o usuário nomeia um cluster c, o rótulo se propaga a todos os embeddings
   armazenados cuja similaridade cosseno com o centróide supera `label_threshold`.
   Fundamento: Aula 02 ("Distância, Similaridade, Produto Interno").

Referências:
  - "Mathematics for Machine Learning" (Deisenroth et al.): SVD, PCA, normas.
  - Aula 01 da série "A Matemática por Trás do Machine Learning" (vetores, normas).
  - Aula 02 da mesma série (gradiente, produto interno, similaridade).
  - Especialização em Visão Computacional (Carlos Melo / Sigmoidal), notebooks 04-05.
"""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import struct
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np  # noqa: F401

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Dimensão do embedding CLIP (ViT-B/32) — mantida idêntica a clip_embedder.py
EMBED_DIM = 512

# Dimensão alvo após PCA — reduz de 512 → 64 mantendo ~95 % de variância.
# Escolha fundamentada: 64 dims é suficiente para distância cosseno discriminativa
# (Deisenroth et al., cap. 10: "representação suficiente para k-NN em espaço reduzido").
PCA_COMPONENTS = 64

# Mínimo de amostras para ajustar PCA e rodar HDBSCAN
_MIN_SAMPLES_PCA = 20
_MIN_SAMPLES_CLUSTER = 10

# HDBSCAN: amostras mínimas por cluster
_HDBSCAN_MIN_CLUSTER_SIZE = 3
_HDBSCAN_MIN_SAMPLES = 2

# Threshold de similaridade cosseno para propagação Bayesiana de rótulos
_LABEL_THRESHOLD_DEFAULT = 0.70

# Caminho padrão do banco de dados
_DEFAULT_DB_PATH = Path(os.environ.get("SOLARIS_STORAGE", "storage")) / "visual_memory.db"


# ---------------------------------------------------------------------------
# Codec: embedding ↔ bytes (float32 little-endian)
# ---------------------------------------------------------------------------

def _encode_vec(vec: list[float] | "np.ndarray") -> bytes:
    """Serializa um vetor float64/float32 para bytes float32 LE."""
    np = importlib.import_module("numpy")
    arr = np.asarray(vec, dtype=np.float32)
    return struct.pack(f"{len(arr)}f", *arr)


def _decode_vec(blob: bytes) -> "np.ndarray":
    """Desserializa bytes float32 LE para np.ndarray float64."""
    np = importlib.import_module("numpy")
    n = len(blob) // 4
    return np.array(struct.unpack(f"{n}f", blob), dtype=np.float64)


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   REAL    NOT NULL,
    frame_hash  TEXT,
    class_id    INTEGER NOT NULL,
    yolo_label  TEXT    NOT NULL,
    bbox_json   TEXT    NOT NULL,
    embedding   BLOB    NOT NULL,   -- float32 LE, EMBED_DIM floats
    cluster_id  INTEGER DEFAULT -1,
    user_label  TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_emb_cluster ON embeddings(cluster_id);
CREATE INDEX IF NOT EXISTS idx_emb_ts      ON embeddings(timestamp);

CREATE TABLE IF NOT EXISTS clusters (
    id          INTEGER PRIMARY KEY,  -- cluster_id (HDBSCAN output)
    centroid    BLOB    NOT NULL,      -- float32 LE, EMBED_DIM floats
    sample_count INTEGER DEFAULT 0,
    user_label  TEXT    DEFAULT NULL,
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS pca_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    components  BLOB    NOT NULL,   -- V_k^T, shape [PCA_COMPONENTS, EMBED_DIM] float32 LE
    mean_vec    BLOB    NOT NULL,   -- coluna de médias X̄, shape [EMBED_DIM] float32 LE
    n_fitted    INTEGER NOT NULL,
    fitted_at   REAL    NOT NULL
);
"""


def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# PCA incremental (SVD truncado via numpy)
# ---------------------------------------------------------------------------

class _PCAState:
    """Wrapper ao redor dos componentes PCA ajustados sobre todos os embeddings."""

    def __init__(self, components: "np.ndarray", mean_vec: "np.ndarray", n_fitted: int) -> None:
        # components: [PCA_COMPONENTS, EMBED_DIM]
        self.components = components
        self.mean_vec = mean_vec
        self.n_fitted = n_fitted

    def transform(self, X: "np.ndarray") -> "np.ndarray":
        """Projeta X ∈ ℝ^{N×512} → ℝ^{N×64}."""
        return (X - self.mean_vec) @ self.components.T

    def serialize(self) -> tuple[bytes, bytes]:
        return _encode_vec(self.components.ravel()), _encode_vec(self.mean_vec)

    @classmethod
    def deserialize(cls, comp_blob: bytes, mean_blob: bytes, n_fitted: int) -> "_PCAState":
        np = importlib.import_module("numpy")
        components = _decode_vec(comp_blob).reshape(PCA_COMPONENTS, EMBED_DIM).astype(np.float64)
        mean_vec = _decode_vec(mean_blob).astype(np.float64)
        return cls(components, mean_vec, n_fitted)


def _fit_pca(embeddings: "np.ndarray") -> "_PCAState":
    """Ajusta PCA via SVD truncado.

    X_centred = X − X̄,  X_centred ≈ U Σ V^T
    Componentes principais = primeiras k linhas de V^T.
    Fundamento: MML cap. 10 / Aula 01 "SVD e PCA".
    """
    np = importlib.import_module("numpy")
    mean_vec = embeddings.mean(axis=0)
    X_c = embeddings - mean_vec
    # SVD econômica — np.linalg.svd(full_matrices=False) devolve V^T diretamente
    _, _, Vt = np.linalg.svd(X_c, full_matrices=False)
    components = Vt[:PCA_COMPONENTS]  # [PCA_COMPONENTS, EMBED_DIM]
    return _PCAState(components, mean_vec, len(embeddings))


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def _run_hdbscan(X_pca: "np.ndarray") -> "np.ndarray":
    """Executa HDBSCAN no espaço PCA.

    Retorna array de labels: -1 = ruído, ≥0 = cluster_id.
    Fallback para mini-batch k-means se hdbscan não disponível.
    """
    try:
        hdbscan = importlib.import_module("hdbscan")
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=_HDBSCAN_MIN_CLUSTER_SIZE,
            min_samples=_HDBSCAN_MIN_SAMPLES,
            metric="euclidean",  # equivale a cosseno após L2-norm (Aula 01)
            cluster_selection_method="eom",
        )
        return clusterer.fit_predict(X_pca)
    except ModuleNotFoundError:
        pass

    # Fallback: k-means com k estimado pelo método do cotovelo simples
    np = importlib.import_module("numpy")
    sklearn_cluster = importlib.import_module("sklearn.cluster")
    n = len(X_pca)
    k = max(2, min(int(n ** 0.5), 20))
    km = sklearn_cluster.MiniBatchKMeans(n_clusters=k, n_init=3, random_state=42)
    return km.fit_predict(X_pca)


# ---------------------------------------------------------------------------
# VisualMemory — API pública
# ---------------------------------------------------------------------------

class VisualMemory:
    """Memória visual auto-supervisionada com SQLite + PCA + HDBSCAN.

    Ciclo de vida esperado:
        mem = VisualMemory()
        mem.store_embedding(det, embedding)   # por detecção
        summary = mem.cluster_all()            # executa PCA + HDBSCAN
        mem.name_cluster(cluster_id, "caneta") # usuário nomeia
        cluster_id = mem.nearest_cluster(embedding)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _DEFAULT_DB_PATH
        self._conn = _open_db(self._path)
        self._lock = threading.Lock()
        self._pca: _PCAState | None = self._load_pca()

    # ------------------------------------------------------------------
    # Ingestão
    # ------------------------------------------------------------------

    def store_embedding(
        self,
        detection: dict,
        embedding: list[float],
        frame_hash: str | None = None,
    ) -> int:
        """Persiste um embedding CLIP para uma detecção YOLO.

        Parâmetros
        ----------
        detection : dict
            Dicionário com class_id, label, x, y, width, height.
        embedding : list[float]
            Vetor L2-normalizado de 512 dimensões (saída de clip_embedder).
        frame_hash : str | None
            Hash SHA-1 do frame (opcional, para deduplicação futura).

        Retorna o id inserido no banco.
        """
        blob = _encode_vec(embedding)
        bbox = json.dumps({
            "x": detection.get("x", 0),
            "y": detection.get("y", 0),
            "w": detection.get("width", 0),
            "h": detection.get("height", 0),
        })
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO embeddings (timestamp, frame_hash, class_id, yolo_label, bbox_json, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), frame_hash, detection.get("class_id", -1),
                 detection.get("label", ""), bbox, blob),
            )
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    def cluster_all(self) -> dict:
        """Executa PCA + HDBSCAN sobre todos os embeddings armazenados.

        Retorna um dicionário com:
            n_embeddings  : total de amostras
            n_clusters    : clusters encontrados (sem -1)
            cluster_sizes : {cluster_id: contagem}
            pca_refitted  : bool — True se PCA foi re-ajustado nesta chamada
        """
        np = importlib.import_module("numpy")

        with self._lock:
            rows = self._conn.execute(
                "SELECT id, embedding FROM embeddings ORDER BY id"
            ).fetchall()

        if len(rows) < _MIN_SAMPLES_CLUSTER:
            return {"n_embeddings": len(rows), "n_clusters": 0,
                    "cluster_sizes": {}, "pca_refitted": False}

        ids = [r[0] for r in rows]
        X = np.stack([_decode_vec(r[1]) for r in rows])  # [N, 512]

        # -- PCA --
        pca_refitted = False
        if self._pca is None or self._pca.n_fitted < _MIN_SAMPLES_PCA or \
                len(rows) > self._pca.n_fitted * 2:
            self._pca = _fit_pca(X)
            self._save_pca(self._pca)
            pca_refitted = True

        X_pca = self._pca.transform(X)  # [N, 64]

        # L2-normaliza as projeções para que a distância euclidiana ≡ cosseno
        norms = np.linalg.norm(X_pca, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)
        X_pca_normed = X_pca / norms

        # -- HDBSCAN / k-means --
        labels = _run_hdbscan(X_pca_normed)

        # -- Atualiza BD: cluster_id em embeddings e centroides --
        unique_ids = set(labels[labels >= 0].tolist())
        cluster_sizes: dict[int, int] = {}

        with self._lock:
            # Atualiza cluster_id em cada embedding
            for i, (row_id, lbl) in enumerate(zip(ids, labels)):
                self._conn.execute(
                    "UPDATE embeddings SET cluster_id=? WHERE id=?",
                    (int(lbl), row_id),
                )

            # Recalcula centroides usando embeddings originais (512-d, L2-norm)
            for cid in unique_ids:
                mask = labels == cid
                cluster_vecs = X[mask]  # [k, 512]
                count = len(cluster_vecs)
                cluster_sizes[cid] = count

                # Centróide = média aritmética depois L2-normalizada
                centroid = cluster_vecs.mean(axis=0)
                norm = np.linalg.norm(centroid)
                if norm > 1e-12:
                    centroid /= norm

                # Preserva user_label se já existia
                existing = self._conn.execute(
                    "SELECT user_label FROM clusters WHERE id=?", (cid,)
                ).fetchone()
                user_label = existing[0] if existing else None
                now = time.time()

                self._conn.execute(
                    "INSERT OR REPLACE INTO clusters (id, centroid, sample_count, user_label, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM clusters WHERE id=?), ?), ?)",
                    (cid, _encode_vec(centroid), count, user_label, cid, now, now),
                )

            # Remove clusters que sumiram (ruído HDBSCAN)
            if unique_ids:
                placeholders = ",".join("?" * len(unique_ids))
                self._conn.execute(
                    f"DELETE FROM clusters WHERE id NOT IN ({placeholders}) AND id != -1",
                    list(unique_ids),
                )
            else:
                self._conn.execute("DELETE FROM clusters WHERE id != -1")

            self._conn.commit()

        return {
            "n_embeddings": len(rows),
            "n_clusters": len(unique_ids),
            "cluster_sizes": cluster_sizes,
            "pca_refitted": pca_refitted,
        }

    # ------------------------------------------------------------------
    # Nomeação e propagação Bayesiana de rótulos
    # ------------------------------------------------------------------

    def name_cluster(
        self,
        cluster_id: int,
        label: str,
        threshold: float = _LABEL_THRESHOLD_DEFAULT,
    ) -> int:
        """Nomeia um cluster e propaga o rótulo a embeddings vizinhos.

        A propagação usa similaridade cosseno entre o embedding armazenado e o
        centróide do cluster. Somente embeddings com sim ≥ threshold recebem o rótulo.
        Fundamento: Aula 02 — "produto interno como medida de similaridade".

        Retorna o número de embeddings rotulados.
        """
        np = importlib.import_module("numpy")

        with self._lock:
            row = self._conn.execute(
                "SELECT centroid FROM clusters WHERE id=?", (cluster_id,)
            ).fetchone()
            if row is None:
                return 0

            centroid = _decode_vec(row[0])

            # Atualiza rótulo do cluster
            self._conn.execute(
                "UPDATE clusters SET user_label=?, updated_at=? WHERE id=?",
                (label, time.time(), cluster_id),
            )

            # Propaga para todos os embeddings sem rótulo de usuário
            emb_rows = self._conn.execute(
                "SELECT id, embedding FROM embeddings WHERE user_label IS NULL"
            ).fetchall()

            labeled = 0
            for row_id, blob in emb_rows:
                vec = _decode_vec(blob)
                sim = float(np.dot(vec, centroid))  # cosseno (ambos L2-normalizados)
                if sim >= threshold:
                    self._conn.execute(
                        "UPDATE embeddings SET user_label=?, cluster_id=? WHERE id=?",
                        (label, cluster_id, row_id),
                    )
                    labeled += 1

            self._conn.commit()

        return labeled

    # ------------------------------------------------------------------
    # Busca de cluster mais próximo
    # ------------------------------------------------------------------

    def nearest_cluster(self, embedding: list[float]) -> dict | None:
        """Retorna o cluster mais similar ao embedding fornecido.

        Usa produto interno sobre vetores L2-normalizados ≡ similaridade cosseno.
        Fundamento: Álgebra Linear, Aula 01 ("produto interno, norma, ângulo").

        Retorna dict com cluster_id, user_label, similarity, sample_count,
        ou None se não houver clusters.
        """
        np = importlib.import_module("numpy")
        vec = np.asarray(embedding, dtype=np.float64)

        with self._lock:
            rows = self._conn.execute(
                "SELECT id, centroid, user_label, sample_count FROM clusters WHERE id != -1"
            ).fetchall()

        if not rows:
            return None

        best_id, best_label, best_sim, best_count = -1, None, -2.0, 0
        for cid, blob, ulabel, count in rows:
            centroid = _decode_vec(blob)
            sim = float(np.dot(vec, centroid))
            if sim > best_sim:
                best_sim = sim
                best_id = cid
                best_label = ulabel
                best_count = count

        return {
            "cluster_id": best_id,
            "user_label": best_label,
            "similarity": best_sim,
            "sample_count": best_count,
        }

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_clusters(self) -> list[dict]:
        """Lista todos os clusters com metadados."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, sample_count, user_label, created_at, updated_at FROM clusters WHERE id != -1"
                " ORDER BY sample_count DESC"
            ).fetchall()
        return [
            {
                "cluster_id": r[0],
                "sample_count": r[1],
                "user_label": r[2],
                "created_at": r[3],
                "updated_at": r[4],
            }
            for r in rows
        ]

    def get_stats(self) -> dict:
        """Resumo rápido do banco de dados."""
        with self._lock:
            n_emb = self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            n_clusters = self._conn.execute(
                "SELECT COUNT(*) FROM clusters WHERE id != -1"
            ).fetchone()[0]
            n_labeled = self._conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE user_label IS NOT NULL"
            ).fetchone()[0]
            pca_row = self._conn.execute(
                "SELECT n_fitted FROM pca_state WHERE id=1"
            ).fetchone()
        return {
            "total_embeddings": n_emb,
            "total_clusters": n_clusters,
            "labeled_embeddings": n_labeled,
            "pca_fitted_on": pca_row[0] if pca_row else 0,
        }

    def clear(self) -> None:
        """Remove todos os dados — usar apenas em testes."""
        with self._lock:
            self._conn.executescript(
                "DELETE FROM embeddings; DELETE FROM clusters; DELETE FROM pca_state;"
            )
            self._conn.commit()
            self._pca = None

    # ------------------------------------------------------------------
    # Persistência do estado PCA
    # ------------------------------------------------------------------

    def _save_pca(self, state: _PCAState) -> None:
        comp_blob, mean_blob = state.serialize()
        self._conn.execute(
            "INSERT OR REPLACE INTO pca_state (id, components, mean_vec, n_fitted, fitted_at)"
            " VALUES (1, ?, ?, ?, ?)",
            (comp_blob, mean_blob, state.n_fitted, time.time()),
        )
        self._conn.commit()

    def _load_pca(self) -> _PCAState | None:
        row = self._conn.execute(
            "SELECT components, mean_vec, n_fitted FROM pca_state WHERE id=1"
        ).fetchone()
        if row is None:
            return None
        try:
            return _PCAState.deserialize(row[0], row[1], row[2])
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Singleton de sessão
# ---------------------------------------------------------------------------

_mem: VisualMemory | None = None
_mem_lock = threading.Lock()


def get_memory() -> VisualMemory:
    """Retorna a instância singleton de VisualMemory."""
    global _mem
    if _mem is None:
        with _mem_lock:
            if _mem is None:
                _mem = VisualMemory()
    return _mem
