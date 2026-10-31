"""
Script para incorporar bancada_eletronica_claudio.jpeg ao banco de aprendizado SOLARIS.
Execute a partir de: D:\Solaris_PlataformaDeIA\solaris\python-engine
"""
import base64, json, sys
from pathlib import Path

engine_dir = Path(r"D:\Solaris_PlataformaDeIA\solaris\python-engine")
sys.path.insert(0, str(engine_dir))

img_path = engine_dir.parent / "training_data" / "bancada_eletronica_claudio.jpeg"
if not img_path.exists():
    print(f"ERRO: imagem nao encontrada em {img_path}")
    sys.exit(1)

print(f"Carregando imagem: {img_path}")
with open(img_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
image_data = "data:image/jpeg;base64," + b64

W, H = 1280, 591

detections = [
    {"label": "estacao de solda",     "x": 130, "y": 175, "width": 195, "height": 155, "source": "human"},
    {"label": "estacao de ar quente", "x":  75, "y": 115, "width": 205, "height": 195, "source": "human"},
    {"label": "multimetro",           "x": 340, "y": 125, "width": 130, "height": 195, "source": "human"},
    {"label": "caixa de som",         "x": 680, "y":  88, "width": 385, "height": 255, "source": "human"},
    {"label": "caderno",              "x":  90, "y": 330, "width": 315, "height": 225, "source": "human"},
    {"label": "estojo",               "x": 435, "y": 378, "width": 260, "height": 175, "source": "human"},
    {"label": "power bank",           "x":1040, "y": 375, "width": 160, "height": 165, "source": "human"},
    {"label": "cabo USB",             "x": 620, "y": 395, "width": 205, "height": 145, "source": "human"},
    {"label": "motor DC",             "x":   0, "y": 295, "width": 125, "height": 255, "source": "human"},
]

payload = {"image": image_data, "width": W, "height": H, "detections": detections}

from app.vision import learning
print(f"Incorporando {len(detections)} objetos com complete=True...")
result = learning.incorporate(project_id=None, revision_id=99001, payload=payload, complete=True)
print("Resultado:", json.dumps(result, ensure_ascii=False, indent=2))

with learning.connect() as conn:
    row = conn.execute(
        "SELECT id, state, labels FROM samples ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    if row:
        labels = json.loads(row["labels"] or "[]")
        print(f"\nAmostra salva: id={row['id']}, state={row['state']}, {len(labels)} rotulos")
        for lb in labels:
            pt = lb.get("name_pt", lb.get("name", ""))
            en = lb.get("name", "")
            print(f"  - {pt} -> {en}")
    else:
        print("Nenhuma amostra encontrada.")

print("\nConcluido!")
