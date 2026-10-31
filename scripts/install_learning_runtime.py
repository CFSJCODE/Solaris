"""Copy the validated learning runtime into application storage, preserving user data."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from app.vision.learning import atomic_json
from app.vision.learning_worker import digest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'storage')
    parser.add_argument('--target',type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve();target=args.target.resolve()
    if source==target:
        raise ValueError('Origem e destino devem ser diferentes.')
    config=json.loads((source/'learning/runtime.json').read_text(encoding='utf-8'))
    if not config.get('validated'):
        raise ValueError('Ambiente ainda não validado.')
    target_runtime=target/'learning-runtime'
    target_assets=target/'learning/assets'
    if (target/'learning/runtime.json').exists():
        raise ValueError('Configuração de aprendizado existente preservada; revise antes de atualizar.')
    shutil.copytree(source/'learning-runtime',target_runtime,dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    target_assets.mkdir(parents=True,exist_ok=True)
    for name in ('yolo26x.pt','yolo26n.pt','yolo26s.pt'):
        shutil.copyfile(source/'learning/assets'/name,target_assets/name)
    owl=target_assets/'owlv2'
    shutil.copytree(config['owl'],owl,dirs_exist_ok=True)
    reference=target_assets/'coco128'
    shutil.copytree(config['reference'],reference,dirs_exist_ok=True)
    images=sorted((reference/'images/train2017').glob('*.jpg'))
    (reference/'eval.txt').write_text('\n'.join(str(p.resolve()) for p in images[1::2]),encoding='utf-8')
    # JSON is accepted by YAML readers and avoids depending on YAML in setup's interpreter.
    reference_yaml=reference/'reference.yaml'
    old_reference=Path(config['reference'])
    original=(old_reference/'reference.yaml').read_text(encoding='utf-8')
    reference_yaml.write_text(original.replace(str(old_reference),str(reference)),encoding='utf-8')
    config.update(python=str(target_runtime/'Scripts/python.exe'),checkpoint=str(target_assets/'yolo26x.pt'),
        owl=str(owl),reference=str(reference),reference_yaml=str(reference_yaml),
        reference_files={str(p.relative_to(reference)):digest(p) for p in reference.rglob('*') if p.is_file()})
    (target/'models').mkdir(parents=True,exist_ok=True)
    for name in ('yolo26n','yolo26s'):
        shutil.copyfile(source/'models'/f'{name}.onnx',target/'models'/f'{name}.onnx')
    atomic_json(target/'learning/live.json',json.loads((source/'learning/live.json').read_text(encoding='utf-8')))
    (target/'learning/benchmark').mkdir(exist_ok=True)
    shutil.copyfile(source/'learning/benchmark/results.json',target/'learning/benchmark/results.json')
    import subprocess
    subprocess.run([config['python'],'-c',"import torch,ultralytics,transformers,psutil,onnxruntime; assert '+cpu' in torch.__version__; print('Runtime CPU independente do projeto: OK')"],check=True)
    if digest(config['checkpoint'])!=config['checkpoint_sha256']:
        raise ValueError('Checkpoint copiado divergiu do validado.')
    atomic_json(target/'learning/runtime.json',config)
    print('Motor de aprendizado instalado nos dados do aplicativo. Nenhuma conversa ou memória existente foi alterada.')


if __name__=='__main__':
    main()
