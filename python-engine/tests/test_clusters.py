import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.vision import clusters, learning


def unit(*values):
    vector = np.zeros(clusters.EMBEDDING_DIM, dtype=np.float32)
    vector[: len(values)] = values
    return clusters.normalize(vector)


class ClusterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"SOLARIS_STORAGE": self.folder.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def test_similar_vectors_share_a_cluster_and_different_ones_split(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            pen_a = clusters.store_region(
                conn, "general", "s1", 0, [0, 0, 30, 30], "caneta", "oiv7", unit(1, 0.05)
            )
            pen_b = clusters.store_region(
                conn, "general", "s2", 0, [0, 0, 30, 30], "caneta", "oiv7", unit(1, -0.05)
            )
            bottle = clusters.store_region(
                conn, "general", "s3", 0, [0, 0, 30, 30], "garrafa", "", unit(0, 1)
            )
            sizes = dict(conn.execute("SELECT id,size FROM visual_clusters").fetchall())
        self.assertEqual(pen_a, pen_b)
        self.assertNotEqual(pen_a, bottle)
        self.assertEqual(sizes[pen_a], 2)

    def test_close_centroids_merge_but_human_names_are_never_fused(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            first = clusters.assign(conn, "general", unit(1, 0))
            second = clusters.assign(conn, "general", unit(0.6, 0.8))  # abaixo do limiar de entrada
            # Aproxima o segundo centróide do primeiro para simular grupos que convergiram.
            conn.execute(
                "UPDATE visual_clusters SET centroid=? WHERE id=?",
                (clusters.to_blob(unit(1, 0.2)), second),
            )
            conn.execute("UPDATE visual_clusters SET name='minha caneta' WHERE id=?", (first,))
            conn.execute("UPDATE visual_clusters SET name='lápis' WHERE id=?", (second,))
            self.assertEqual(clusters.merge_close(conn, "general"), 0)
            conn.execute("UPDATE visual_clusters SET name=NULL WHERE id=?", (second,))
            self.assertEqual(clusters.merge_close(conn, "general"), 1)
            rows = conn.execute("SELECT name,size FROM visual_clusters").fetchall()
        self.assertEqual([(r[0], r[1]) for r in rows], [("minha caneta", 2)])

    def test_rebuild_regroups_from_stored_vectors_and_keeps_named_groups(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            named = clusters.store_region(conn, "general", "s1", 0, [0, 0, 30, 30], "", "", unit(1))
            conn.execute("UPDATE visual_clusters SET name='caneca' WHERE id=?", (named,))
            clusters.store_region(conn, "general", "s2", 0, [0, 0, 30, 30], "", "", unit(0, 1))
            clusters.store_region(
                conn, "general", "s3", 0, [0, 0, 30, 30], "", "", unit(0, 1, 0.02)
            )
            self.assertEqual(clusters.rebuild(conn, "general"), 2)
            groups = conn.execute(
                "SELECT name,size FROM visual_clusters ORDER BY size DESC,id"
            ).fetchall()
        self.assertEqual([(g[0], g[1]) for g in groups], [(None, 2), ("caneca", 1)])

    def test_near_tie_between_two_groups_is_left_uncertain(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            clusters.assign(conn, "general", unit(1, 0.3))
            clusters.assign(conn, "general", unit(1, -0.3))
            # Equidistante dos dois centróides e acima do limiar de ambos.
            cluster_id = clusters.store_region(
                conn, "general", "s", 0, [0, 0, 30, 30], "", "", unit(1, 0)
            )
            state = conn.execute("SELECT state FROM region_embeddings").fetchone()[0]
        self.assertIsNone(cluster_id)
        self.assertEqual(state, "uncertain")

    def test_neighbor_frames_count_as_one_view_and_new_sessions_add_views(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            args = ("general", "", "", unit(1, 0.01))
            first = clusters.store_region(
                conn, args[0], "a", 0, [0, 0, 40, 40], *args[1:], session="s1", observed=100
            )
            clusters.store_region(
                conn, args[0], "b", 0, [2, 2, 42, 42], *args[1:], session="s1", observed=103
            )
            clusters.store_region(
                conn, args[0], "c", 0, [2, 2, 42, 42], *args[1:], session="s2", observed=400
            )
            views = conn.execute(
                "SELECT views FROM visual_clusters WHERE id=?", (first,)
            ).fetchone()[0]
        self.assertEqual(views, 2)

    def test_adaptive_threshold_uses_group_spread_within_bounds(self):
        self.assertEqual(clusters.acceptance_threshold(2, 0.95, 0.0), clusters.ASSIGN_THRESHOLD)
        tight = clusters.acceptance_threshold(10, 0.97, 10 * 0.0001)
        loose = clusters.acceptance_threshold(10, 0.90, 10 * 0.01)
        self.assertEqual(tight, clusters.ADAPTIVE_CEILING)
        self.assertEqual(loose, clusters.ADAPTIVE_FLOOR)

    def test_quality_filter_rejects_dark_and_flat_crops(self):
        rng = np.random.default_rng(0)
        textured = rng.integers(40, 220, (64, 64, 3), dtype=np.uint8)
        self.assertTrue(clusters.quality_ok(textured))
        self.assertFalse(clusters.quality_ok(np.full((64, 64, 3), 5, dtype=np.uint8)))
        self.assertFalse(clusters.quality_ok(np.full((64, 64, 3), 128, dtype=np.uint8)))

    def test_pca_requires_enough_samples_and_is_off_by_default(self):
        self.assertFalse(clusters.PCA_ENABLED)
        with self.assertRaisesRegex(ValueError, "insuficientes"):
            clusters.pca_basis(np.ones((10, 512)), components=64)
        mean, basis = clusters.pca_basis(np.random.default_rng(1).normal(size=(80, 512)), 16)
        self.assertEqual((mean.shape, basis.shape), ((512,), (16, 512)))

    def test_regions_skip_small_and_low_confidence_boxes(self):
        detections = [
            {"x": 0, "y": 0, "width": 100, "height": 80, "confidence": 0.9, "label": "notebook"},
            {"x": 0, "y": 0, "width": 10, "height": 10, "confidence": 0.9, "label": "minúsculo"},
            {"x": 0, "y": 0, "width": 60, "height": 60, "confidence": 0.1, "label": "incerto"},
        ]
        self.assertEqual([r[2] for r in clusters.regions(detections, 640, 480)], ["notebook"])

    def test_invalid_vectors_are_rejected(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            with self.assertRaisesRegex(ValueError, "inválido"):
                clusters.store_region(conn, "general", "s", 0, [0, 0, 1, 1], "", "", np.zeros(512))
            with self.assertRaisesRegex(ValueError, "Dimensão"):
                clusters.store_region(conn, "general", "s", 0, [0, 0, 1, 1], "", "", np.ones(10))

    def test_rename_is_scoped_to_the_project(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            cluster_id = clusters.assign(conn, "project-1", unit(1))
        self.assertEqual(
            clusters.rename_cluster(1, cluster_id, "  minha caneta ")["name"], "minha caneta"
        )
        with self.assertRaisesRegex(ValueError, "não encontrado"):
            clusters.rename_cluster(None, cluster_id, "outro projeto")
        listing = clusters.list_clusters(1)
        self.assertEqual(listing["clusters"][0]["name"], "minha caneta")
        self.assertFalse(listing["clusters"][0]["stable"])

    def test_schema_is_idempotent(self):
        with learning.connect() as conn:
            clusters.ensure_schema(conn)
            clusters.ensure_schema(conn)
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        self.assertTrue({"region_embeddings", "visual_clusters", "embedded_samples"} <= tables)
        self.assertIsInstance(conn, sqlite3.Connection)


if __name__ == "__main__":
    unittest.main()
