"""Automatic cleanup restricted to generated learning artifacts, never imported files."""

# Importa as bibliotecas necessárias
import json
import re
import shutil
import time
from pathlib import Path

from app.vision import learning as store


# Função para remover diretórios gerados, garantindo que estejam dentro do armazenamento permitido e correspondam a um padrão de hash
def remove_generated(directory, category):
    root = (store.root() / category).resolve()
    path = Path(directory).resolve()
    if path.parent != root or not re.fullmatch("[0-9a-f]{32}", path.name):
        raise ValueError("Limpeza recusada: caminho fora dos artefatos gerados.")
    shutil.rmtree(path)


# Função para realizar a limpeza de trabalhos antigos e amostras, mantendo apenas os mais recentes e protegendo aqueles que estão ativos ou aguardando evidências
def cleanup():
    protected = set()
    for pointer in (store.root() / "active").glob("*.json"):
        if not re.fullmatch(
            r"(general|project-[0-9]+)(-yolo26s|-supplement-yolo26[sx])?", pointer.stem
        ):
            continue
        try:
            version = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in (version, version.get("previous"), version.get("previous_supplemental")):
            if item:
                protected.add(item["id"])
    with store.connect() as conn:
        protected.update(
            r[0]
            for r in conn.execute(
                "SELECT id FROM jobs WHERE state IN ('paused','interrupted','training')"
            )
        )
        awaiting = conn.execute(
            "SELECT id,scope,dataset FROM jobs WHERE state='awaiting_evidence' ORDER BY created DESC"
        ).fetchall()
        latest = set()
        for row in awaiting:
            key = (row["scope"], row["dataset"].split(":")[0])
            if key not in latest:
                protected.add(row["id"])
                latest.add(key)
        jobs = conn.execute("SELECT id,scope,created FROM jobs ORDER BY created DESC").fetchall()
    # Keep two additional recent experiments, plus all active/recoverable versions.
    protected.update(r["id"] for r in jobs[:2])
    size = sum(
        p.stat().st_size
        for category in ("runs", "datasets")
        for p in (store.root() / category).rglob("*")
        if p.is_file()
    )
    for job in reversed(jobs):
        if job["id"] in protected:
            continue
        if time.time() - job["created"] < 7 * 86400 and size < 8 * 1024**3:
            continue
        for category in ("runs", "datasets"):
            directory = store.root() / category / job["id"]
            if directory.is_dir():
                amount = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
                remove_generated(directory, category)
                size -= amount
        with store.connect() as conn:
            conn.execute("UPDATE versions SET state='archived' WHERE id=?", (job["id"],))
            # Keep job metrics/manifests for audit, without repeating deleted file paths as recoverable checkpoints.
            conn.execute("UPDATE jobs SET checkpoint=NULL WHERE id=?", (job["id"],))
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id,scope,image,byte_size,created FROM samples WHERE state!='archived' ORDER BY created DESC"
        ).fetchall()
        size = sum(r["byte_size"] for r in rows)
        count = len(rows)
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if index < 512 or (
                size < 900_000_000 and count < 2700 and time.time() - row["created"] < 30 * 86400
            ):
                continue
            if conn.execute(
                "SELECT 1 FROM training_requests WHERE scope=? AND sample_id=? AND state IN ('queued','verifying','training','paused')",
                (row["scope"], row["id"]),
            ).fetchone():
                continue
            path = (store.root() / row["image"]).resolve()
            if (
                not path.is_relative_to((store.root() / "samples").resolve())
                or path.name != row["id"] + ".jpg"
            ):
                raise ValueError("Limpeza recusada: exemplo fora do armazenamento gerado.")
            path.unlink(missing_ok=True)
            conn.execute(
                "UPDATE samples SET state='archived',byte_size=0,signature=? WHERE id=? AND scope=?",
                ("archived-" + row["id"], row["id"], row["scope"]),
            )
            size -= row["byte_size"]
            count -= 1
