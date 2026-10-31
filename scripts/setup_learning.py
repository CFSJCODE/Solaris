"""Provision the optional local learning runtime; no credentials or cloud services."""
# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen,Request

ROOT = Path(__file__).resolve().parents[1]


def download(url,path):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        return
    temporary = path.with_suffix('.download')
    with urlopen(Request(url,headers={'User-Agent':'Solaris-learning-setup'}),timeout=120) as response,temporary.open('wb') as output:
        while chunk:=response.read(1024*1024):
            output.write(chunk)
    temporary.replace(path)


def run(args):
    subprocess.run([str(x) for x in args],check=True,cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storage',type=Path,default=ROOT/'storage')
    parser.add_argument('--assets-only',action='store_true')
    args = parser.parse_args()
    storage = args.storage.resolve()
    runtime = storage/'learning-runtime'
    python = runtime/'Scripts'/'python.exe'
    if not python.is_file():
        run(['py','-3.10','-m','venv',runtime])
    if not args.assets_only:
        run([python,'-m','pip','install','--upgrade','pip'])
        run([python,'-m','pip','install','torch==2.10.0','torchvision==0.25.0','--index-url','https://download.pytorch.org/whl/cpu'])
        run([python,'-m','pip','install','-r',ROOT/'python-engine'/'requirements-learning.txt'])
    # Provision assets with the same interpreter that will consume them.
    run([python,Path(__file__),'--provision',storage])
    run([python,ROOT/'scripts/benchmark_learning.py',storage])


def provision(storage):
    sys.path.insert(0,str(ROOT/'python-engine'))
    from app.vision import learning
    from app.vision.learning_worker import digest
    from huggingface_hub import snapshot_download,HfApi
    from ultralytics import YOLO
    import torch
    import yaml
    os.environ['SOLARIS_STORAGE']=str(storage)
    torch.set_num_threads(2)
    assets = learning.root()/'assets'
    assets.mkdir(parents=True,exist_ok=True)
    hashes = {}
    for name in ('yolo26x','yolo26n','yolo26s'):
        path = assets/f'{name}.pt'
        download(f'https://github.com/ultralytics/assets/releases/download/v8.4.0/{name}.pt',path)
        model = YOLO(path)
        if model.model.yaml.get('scale')!=name[-1]:
            raise ValueError('Checkpoint com escala divergente.')
        hashes[path.name] = digest(path)
        if name!='yolo26x':
            exported = Path(model.export(format='onnx',imgsz=640,nms=False,dynamic=False,simplify=False,opset=17,device='cpu'))
            destination = storage/'models'/exported.name
            destination.parent.mkdir(parents=True,exist_ok=True)
            import shutil
            shutil.copyfile(exported,destination)
            hashes[destination.name]=digest(destination)
    # Use an immutable revision in the saved configuration, never rolling 'main' in operation.
    revision = HfApi().model_info('google/owlv2-base-patch16-ensemble').sha
    owl = snapshot_download('google/owlv2-base-patch16-ensemble',revision=revision,
        cache_dir=str(assets/'hf'),allow_patterns=['*.json','*.txt','model.safetensors'])
    archive = assets/'coco128.zip'
    download('https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip',archive)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not (assets/member.filename).resolve().is_relative_to(assets.resolve()):
                raise ValueError('Caminho inválido no dataset de referência.')
        zipped.extractall(assets)
    reference = assets/'coco128'
    # Even files are replay; odd files remain exclusively in reference evaluation.
    images = sorted((reference/'images'/'train2017').glob('*.jpg'))
    (reference/'eval.txt').write_text('\n'.join(str(p.resolve()) for p in images[1::2]),encoding='utf-8')
    names = YOLO(assets/'yolo26x.pt').names
    reference_yaml = reference/'reference.yaml'
    reference_yaml.write_text(yaml.safe_dump({'path':str(reference),'train':'eval.txt','val':'eval.txt','names':names}),encoding='utf-8')
    config = {'python':str(storage/'learning-runtime'/'Scripts'/'python.exe'),'checkpoint':str(assets/'yolo26x.pt'),
        'checkpoint_sha256':hashes['yolo26x.pt'],'owl':owl,'owl_revision':revision,'reference':str(reference),
        'reference_yaml':str(reference_yaml),'reference_sha256':digest(archive),'assets':hashes,
        'reference_files':{str(p.relative_to(reference)):digest(p) for p in reference.rglob('*') if p.is_file()},
        'validated':False}
    learning.atomic_json(learning.root()/'runtime.json',config)
    print('Motor preparado em ambiente separado. Falta benchmark/validação local antes de ativar o serviço.')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--provision':
        provision(Path(sys.argv[2]))
    else:
        main()
