"""Physical camera plus autonomous model updates, isolated from installed model pointers."""
import base64,hashlib,json,os,queue,shutil,sqlite3,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))

def main():
    import cv2,psutil
    installed=Path(os.environ['APPDATA'])/'com.cfsjcode.solaris/storage'
    target=ROOT/'storage'/('concurrent-scan-'+time.strftime('%Y%m%d-%H%M%S'))
    target.mkdir()
    os.environ['SOLARIS_STORAGE']=str(target)
    from app.vision import learning
    config=json.loads((installed/'learning/runtime.json').read_text(encoding='utf-8'))
    reference=Path(config['reference']);subset=target/'reference'
    for image in sorted((reference/'images/train2017').glob('*.jpg'))[:16]:
        for kind,source in [('images',image),('labels',reference/'labels/train2017'/image.with_suffix('.txt').name)]:
            dest=subset/kind/'train2017'/source.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    config={**config,'reference':str(subset),'reference_files':{str(p.relative_to(subset)):hashlib.sha256(p.read_bytes()).hexdigest() for p in subset.rglob('*') if p.is_file()}}
    learning.atomic_json(learning.root()/'runtime.json',config)
    (target/'models').mkdir()
    for model in ('yolo26x','yolo26s','yolo26n'):
        source=installed/'models'/f'{model}.onnx'
        if not source.exists():source=ROOT/'storage/models'/f'{model}.onnx'
        shutil.copyfile(source,target/'models'/source.name)
    shutil.copyfile(installed/'learning/live.json',learning.root()/'live.json')
    # Unlabeled real scans are verified again; never convert them into human annotations.
    with sqlite3.connect((installed/'learning/learning.sqlite3').as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        scans=conn.execute("SELECT * FROM samples WHERE scope='general' AND state!='archived' ORDER BY created DESC LIMIT 24").fetchall()
    imported=0
    with learning.connect() as conn:
        conn.execute("INSERT INTO settings(scope,enabled) VALUES('general',1)")
        for row in scans:
            source=installed/'learning'/row['image']
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=row['id']:continue
            dest=learning.root()/'samples/general'/source.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
            conn.execute('INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?)',(row['id'],'general','technical-camera-episode',row['created'],row['signature'],str(dest.relative_to(learning.root())),dest.stat().st_size,row['model'],row['detections'],None,'pending'))
            imported+=1
    assert imported>=4,'Poucas observações reais disponíveis para o ensaio.'
    cap=cv2.VideoCapture(0,cv2.CAP_DSHOW)
    if not cap.isOpened():cap.release();cap=cv2.VideoCapture(0,cv2.CAP_MSMF)
    assert cap.isOpened(),'Câmera física indisponível; ensaio não comprovado.'
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    environment={**os.environ,'SOLARIS_STORAGE':str(target),'PYTHONUTF8':'1'}
    errors=(target/'engine-errors.log').open('w',encoding='utf-8')
    process=subprocess.Popen([str(ROOT/'python-engine/.venv/Scripts/python.exe'),str(ROOT/'python-engine/app/main.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    responses=queue.Queue()
    def reader():
        for line in process.stdout:
            try:responses.put(json.loads(line))
            except ValueError:responses.put({'type':'error','message':'Saída fora do protocolo.'})
    threading.Thread(target=reader,daemon=True).start()
    sequence=0
    def request(body):
        nonlocal sequence
        sequence+=1
        process.stdin.write(json.dumps({'id':str(sequence),**body})+'\n');process.stdin.flush()
        value=responses.get(timeout=40)
        if value.get('type')=='error':raise RuntimeError(value.get('message'))
        assert value['id']==str(sequence),value
        return value
    frames=0;measurements=[];states=[];started=time.monotonic();last_status=0;children=[]
    try:
        while time.monotonic()-started<900:
            tick=time.perf_counter()
            ok,frame=cap.read()
            if not ok:raise RuntimeError('Captura da câmera falhou durante o ensaio.')
            if frame.shape[1]>640:frame=cv2.resize(frame,(640,round(frame.shape[0]*640/frame.shape[1])))
            ok,jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,80]);assert ok
            result=request({'type':'vision_detect','adapt':True,'content_b64':base64.b64encode(jpeg).decode()})
            frames+=1
            measurements.append({'t':round(time.monotonic()-started,2),'inference_ms':result['elapsed_ms'],'pipeline_ms':(time.perf_counter()-tick)*1000})
            if time.monotonic()-last_status>5:
                state=request({'type':'learning_status'})
                states.append({'t':round(time.monotonic()-started,2),'frames':frames,'samples':state['samples'],'jobs':[(j['state'],json.loads(j['metrics']).get('model') if j['metrics'] else None) for j in state['jobs']]})
                print(json.dumps({'frames':frames,'samples':state['samples'],'message':state['message']},ensure_ascii=False),flush=True)
                last_status=time.monotonic()
                reports=[json.loads(j['metrics']) for j in state['jobs'] if j['metrics']]
                completed={r['model'] for r in reports if r.get('weights_changed')}
                if completed=={'yolo26s','yolo26x'} and frames>=20:
                    assert not state['requests'],'O ensaio autônomo não deve depender de pedidos manuais.'
                    training_states=[r for r in states if any(s[0]=='training' for s in r['jobs'])]
                    assert len(training_states)>=2 and training_states[-1]['frames']>training_states[0]['frames']
                    report={'physical_camera':True,'frames':frames,'manual_requests':0,'manual_labels':0,'imported_unlabeled_scans':imported,'reports':reports,'states':states,'measurements':measurements,'reserved_learning_cpu':state.get('learning_cpu'),'seconds':time.monotonic()-started,'scope':'isolated technical run; no installed model adopted'}
                    learning.atomic_json(target/'results.json',report)
                    print('CONCURRENT_SCAN_RESULT '+str(target/'results.json'),flush=True)
                    break
        else:raise TimeoutError('O escaneamento não produziu dois ajustes válidos em 15 min; verificar exemplos/recursos sem relaxar filtros.')
    finally:
        cap.release()
        children=psutil.Process(process.pid).children(recursive=True)
        process.stdin.close();process.wait(timeout=25);errors.close()
        _,alive=psutil.wait_procs(children,timeout=10)
        assert not [p for p in alive if p.is_running()],'Processo auxiliar órfão.'

if __name__=='__main__':main()
