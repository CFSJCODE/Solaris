"""Real CPU training/export smoke test, isolated from active model versions."""
from __future__ import annotations
import gc
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))


def main():
    import cv2
    import numpy as np
    import onnxruntime as ort
    import psutil
    import torch
    import yaml
    from ultralytics import YOLO
    from app.vision import learning
    from app.vision.learning_worker import Teachers,digest,metrics
    storage = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'storage'
    os.environ['SOLARIS_STORAGE']=str(storage)
    config_path = learning.root()/'runtime.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    reference = Path(config['reference'])
    image_path = sorted((reference/'images'/'train2017').glob('*.jpg'))[0]
    image = cv2.imread(str(image_path))
    torch.set_num_threads(2)
    measurements = {}
    sample = np.zeros((1,3,640,640),np.float32)
    for name in ('yolo26n','yolo26s'):
        options=ort.SessionOptions();options.intra_op_num_threads=3;options.inter_op_num_threads=1
        session=ort.InferenceSession(str(storage/'models'/f'{name}.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        spec=session.get_inputs()[0]
        session.run(None,{spec.name:sample})
        times=[]
        for _ in range(5):
            started=time.perf_counter();session.run(None,{spec.name:sample});times.append((time.perf_counter()-started)*1000)
        measurements[name]={'median_ms':float(np.median(times)),'samples_ms':times}
        del session
    chosen = 'yolo26s' if measurements['yolo26s']['median_ms']<250 else 'yolo26n'
    learning.atomic_json(learning.root()/'live.json',{'model':chosen,'sha256':digest(storage/'models'/f'{chosen}.onnx'),'benchmark':measurements})
    teacher=Teachers(config)
    started=time.perf_counter()
    labels=teacher.label(image,'benchmark')
    measurements['teachers']={'seconds':time.perf_counter()-started,'accepted_boxes':len(labels or [])}
    del teacher
    gc.collect()
    dataset=learning.root()/'benchmark'/'dataset'
    for path in sorted((reference/'images'/'train2017').glob('*.jpg'))[:2]:
        for split in ('train','val'):
            target=dataset/'images'/split/path.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
            label=dataset/'labels'/split/path.with_suffix('.txt').name
            label.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(reference/'labels'/'train2017'/path.with_suffix('.txt').name,label)
    model=YOLO(config['checkpoint'])
    if model.model.yaml.get('scale')!='x':
        raise ValueError('Esperado YOLO26x.')
    yaml_path=dataset/'data.yaml'
    expanded_names={**model.names,80:'toolbox'}
    yaml_path.write_text(yaml.safe_dump({'path':str(dataset),'train':'images/train','val':'images/val','names':expanded_names}),encoding='utf-8')
    peak=[0]
    def memory(_):
        peak[0]=max(peak[0],psutil.Process().memory_info().rss)
    model.add_callback('on_train_batch_end',memory)
    started=time.perf_counter()
    model.train(data=str(yaml_path),device='cpu',batch=1,imgsz=320,epochs=1,workers=0,freeze=22,
        optimizer='SGD',lr0=.0005,amp=False,cache=False,plots=False,save=True,save_period=1,
        project=str(learning.root()/'benchmark'),name='train',exist_ok=True,verbose=False,mosaic=0,close_mosaic=0)
    measurements['yolo26x_training']={'seconds':time.perf_counter()-started,'images':2,'epochs':1,'observed_rss_bytes':peak[0],
        'note':'Teste técnico com treino e validação nas mesmas duas imagens; não mede generalização.'}
    trained=learning.root()/'benchmark'/'train'/'weights'/'best.pt'
    candidate=YOLO(trained)
    if len(candidate.names)!=81 or candidate.names[80]!='toolbox':
        raise ValueError('Expansão de classes não preservou o catálogo esperado.')
    measurements['registry']={'classes':len(candidate.names),'new_class':'toolbox','new_class_accuracy_tested':False}
    measurements['evaluation_api']=metrics(candidate,yaml_path,yaml_path)
    exported=Path(candidate.export(format='onnx',imgsz=640,nms=False,dynamic=False,simplify=False,opset=17,device='cpu'))
    options=ort.SessionOptions();options.intra_op_num_threads=2
    session=ort.InferenceSession(str(exported),sess_options=options,providers=['CPUExecutionProvider'])
    output=session.run(None,{session.get_inputs()[0].name:sample})[0]
    if output.shape!=(1,300,6) or not np.isfinite(output).all():
        raise ValueError('Saída ONNX divergente.')
    measurements['export']={'shape':list(output.shape),'sha256':digest(exported),'active':False}
    learning.atomic_json(learning.root()/'benchmark'/'results.json',measurements)
    config['validated']=True
    learning.atomic_json(config_path,config)
    print(json.dumps(measurements,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
