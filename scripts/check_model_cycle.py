"""Real s/x weight updates and ONNX exports, isolated; never promotes test models."""
# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import base64
import json
import os
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))

def main():
    import cv2
    import numpy as np
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO
    from app.vision import learning
    from app.vision.learning_worker import train,digest
    config=json.loads((ROOT/'storage/learning/runtime.json').read_text(encoding='utf-8'))
    target=ROOT/'storage'/('model-cycle-'+time.strftime('%Y%m%d-%H%M%S'))
    target.mkdir()
    os.environ['SOLARIS_STORAGE']=str(target)
    reference=Path(config['reference'])
    images=sorted((reference/'images/train2017').glob('*.jpg'))
    subset=target/'reference'
    for image in images[:16]:
        for kind,source in [('images',image),('labels',reference/'labels/train2017'/image.with_suffix('.txt').name)]:
            dest=subset/kind/'train2017'/source.name
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    config={**config,'reference':str(subset),'reference_sha256':digest(images[0])}
    image=images[16]
    frame=cv2.imread(str(image))
    assert frame is not None,f'Imagem ilegível: {image}'
    height,width=frame.shape[:2]
    from app.vision.detector import LABELS
    boxes=[]
    for row in (reference/'labels/train2017'/image.with_suffix('.txt').name).read_text().splitlines():
        cls,cx,cy,w,h=map(float,row.split())
        boxes.append({'label':LABELS[int(cls)],'source':'human','x':max(0,(cx-w/2)*width),'y':max(0,(cy-h/2)*height),
                      'width':min(w*width,width-max(0,(cx-w/2)*width)),'height':min(h*height,height-max(0,(cy-h/2)*height))})
    payload={'image':'data:image/jpeg;base64,'+base64.b64encode(image.read_bytes()).decode(),'width':width,'height':height,'detections':boxes}
    with patch.object(learning,'start_worker'):
        receipt=learning.incorporate(1,1,payload,True)
    results=[]
    torch.set_num_threads(1)
    for model in ('yolo26s','yolo26x'):
        started=time.perf_counter()
        assert train('project-1',config,model,True)
        with learning.connect() as conn:
            job=conn.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 1').fetchone()
        report=json.loads(job['metrics'])
        assert report['weights_changed'],report
        assert not report['approved'] and job['state'] in ('rejected','awaiting_evidence'),report
        checkpoint=learning.root()/'runs'/job['id']/'candidate/weights/best.pt'
        candidate=YOLO(checkpoint)
        assert candidate.model.yaml['scale']==model[-1]
        exported=Path(candidate.export(format='onnx',imgsz=640,nms=False,dynamic=False,simplify=False,device='cpu',opset=17))
        options=ort.SessionOptions();options.intra_op_num_threads=1
        session=ort.InferenceSession(str(exported),sess_options=options,providers=['CPUExecutionProvider'])
        output=np.asarray(session.run(None,{session.get_inputs()[0].name:np.zeros((1,3,640,640),np.float32)})[0])
        assert output.shape==(1,300,6) and np.isfinite(output).all()
        results.append({'model':model,'seconds':time.perf_counter()-started,'weights_changed':True,'active':False,'export_shape':list(output.shape),'report':report})
        del candidate,session
    assert not list((learning.root()/'active').glob('*.json'))
    learning.atomic_json(target/'results.json',{'receipt':receipt,'models':results,'note':'Ensaio técnico em dados públicos; não mede melhora no ambiente real.'})
    print('MODEL_CYCLE_RESULT '+str(target/'results.json'),flush=True)

if __name__=='__main__':main()
