"""Bounded, project-scoped capture queue. Heavy learning runs outside the engine."""

# Importações de módulos necessários para o funcionamento do código, incluindo bibliotecas padrão e módulos específicos do projeto
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

# Variáveis globais para gerenciar o processo de aprendizado, incluindo o processo do trabalhador, CPU reservada, log do trabalhador, bloqueio de thread e sessões ativas
_worker = None
_reserved_cpu = None
_worker_log = None
_lock = threading.Lock()
_last = {}
_sessions = {}

# Função para obter o diretório raiz de armazenamento, verificando a variável de ambiente SOLARIS_STORAGE e retornando o caminho padrão se não estiver definida
def root() -> Path:
    return Path(os.environ.get('SOLARIS_STORAGE', 'storage')).resolve() / 'learning'

# Função para gerar o escopo do projeto com base no ID do projeto, retornando "general" se o ID for None e validando o ID do projeto
def scope(project_id):
    if project_id is not None and (type(project_id) is not int or project_id < 1):
        raise ValueError('Projeto inválido.')
    return f'project-{project_id}' if project_id is not None else 'general'

# Função para conectar-se ao banco de dados SQLite, criando as tabelas necessárias e garantindo a integridade do esquema, além de fornecer um contexto para operações atômicas
@contextmanager
def connect():
    directory = root()
    directory.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(directory/'learning.sqlite3', timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS settings(scope TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
        last_live REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT 'Aguardando observações');
      CREATE TABLE IF NOT EXISTS samples(id TEXT NOT NULL, scope TEXT NOT NULL, session TEXT NOT NULL,
        created REAL NOT NULL, signature TEXT NOT NULL, image TEXT NOT NULL, byte_size INTEGER NOT NULL,
        model TEXT NOT NULL, detections TEXT NOT NULL, labels TEXT, state TEXT NOT NULL DEFAULT 'pending',
        PRIMARY KEY(scope,id), UNIQUE(scope, signature));
      CREATE INDEX IF NOT EXISTS samples_scope_state ON samples(scope,state);
      CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, scope TEXT NOT NULL, created REAL NOT NULL,
        state TEXT NOT NULL, message TEXT NOT NULL, dataset TEXT, metrics TEXT, checkpoint TEXT);
      CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, scope TEXT NOT NULL, created REAL NOT NULL,
        state TEXT NOT NULL, manifest TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, scope TEXT NOT NULL, created REAL NOT NULL,
        message TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS human_reviews(scope TEXT NOT NULL, sample_id TEXT NOT NULL,
        revision_id INTEGER NOT NULL, labels TEXT NOT NULL, complete INTEGER NOT NULL, created REAL NOT NULL,
        PRIMARY KEY(scope,sample_id));
      CREATE TABLE IF NOT EXISTS training_requests(id TEXT PRIMARY KEY, scope TEXT NOT NULL, model TEXT NOT NULL,
        created REAL NOT NULL, state TEXT NOT NULL, message TEXT NOT NULL, sample_id TEXT, job_id TEXT);
      CREATE TABLE IF NOT EXISTS cycle_state(scope TEXT PRIMARY KEY, last_count INTEGER NOT NULL DEFAULT 0, last_started REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS live_context(scope TEXT PRIMARY KEY, latency REAL NOT NULL,
        frames INTEGER NOT NULL, updated REAL NOT NULL);
    ''')
    request_columns={r[1] for r in conn.execute('PRAGMA table_info(training_requests)')}
    if 'source_hash' not in request_columns:
        try:conn.execute("ALTER TABLE training_requests ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            if 'source_hash' not in {r[1] for r in conn.execute('PRAGMA table_info(training_requests)')}:raise
    columns={r[1] for r in conn.execute('PRAGMA table_info(live_context)')}
    if 'scene' not in columns:
        try:
            conn.execute("ALTER TABLE live_context ADD COLUMN scene TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError:
            if 'scene' not in {r[1] for r in conn.execute('PRAGMA table_info(live_context)')}:raise
    try:
        with conn:
            yield conn
    finally:
        conn.close()

# Função para gravar um arquivo JSON de forma atômica, garantindo que o arquivo seja escrito completamente antes de substituir o arquivo existente
def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

# Função para obter o caminho do arquivo de log do trabalhador, garantindo que o diretório exista e retornando o caminho completo do arquivo de log
def event(conn, key, message):
    conn.execute('UPDATE settings SET message=? WHERE scope=?', (message, key))
    conn.execute('INSERT INTO events(scope,created,message) VALUES(?,?,?)', (key,time.time(),message))

# Função para obter o caminho do arquivo de log do trabalhador, garantindo que o diretório exista e retornando o caminho completo do arquivo de log
def coalesce_training_requests(conn, key):
    rows = conn.execute(
        "SELECT id,model,sample_id,state,created FROM training_requests WHERE scope=? "
        "AND state IN ('queued','preparing','verifying','paused') ORDER BY created,id",
        (key,),
    ).fetchall()
    models={row['model'] for row in rows}
    for model in models:
        model_rows=[row for row in rows if row['model']==model]
        generic=[row for row in model_rows if row['sample_id'] is None]
        specific=[row for row in model_rows if row['sample_id'] is not None]
        labeled=[]
        pending_by_sample={}
        for row in specific:
            sample=conn.execute('SELECT state FROM samples WHERE scope=? AND id=?',(key,row['sample_id'])).fetchone()
            if sample and sample['state']=='labeled':
                labeled.append(row)
            elif sample and sample['state']=='pending':
                pending_by_sample.setdefault(row['sample_id'],[]).append(row)
            else:
                conn.execute(
                    "UPDATE training_requests SET state='blocked',message=? WHERE id=?",
                    ('Exemplo ausente ou sem verificação suficiente; corrija a revisão ou aguarde novos dados.',row['id']),
                )

        if labeled:
            candidates=generic+labeled
            keeper=max(candidates,key=lambda row:(row['created'],row['id']))
            source=[tuple(sample) for sample in conn.execute(
                "SELECT id,labels FROM samples WHERE scope=? AND state='labeled' ORDER BY id",(key,)
            )]
            source_hash=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
            active=conn.execute(
                "SELECT 1 FROM training_requests WHERE scope=? AND model=? AND state='training' LIMIT 1",
                (key,model),
            ).fetchone()
            message=('Amostras agrupadas; aguardando a conclusão do treino atual deste modelo.' if active
                     else 'Solicitações agrupadas; o treino usará todas as amostras verificadas deste projeto.')
            conn.execute(
                "UPDATE training_requests SET sample_id=NULL,source_hash=?,state='queued',message=? WHERE id=?",
                (source_hash,message,keeper['id']),
            )
            for row in candidates:
                if row['id']!=keeper['id']:
                    conn.execute(
                        "UPDATE training_requests SET state='superseded',message=? WHERE id=?",
                        ('Incluído no ciclo agrupado do mesmo modelo; as amostras verificadas foram preservadas.',row['id']),
                    )
        elif generic:
            keeper=max(generic,key=lambda row:(row['created'],row['id']))
            for row in generic:
                if row['id']!=keeper['id']:
                    conn.execute(
                        "UPDATE training_requests SET state='superseded',message=? WHERE id=?",
                        ('Solicitação agrupada com outro ciclo pendente do mesmo modelo.',row['id']),
                    )

        for sample_rows in pending_by_sample.values():
            keeper=max(sample_rows,key=lambda row:(row['created'],row['id']))
            for row in sample_rows:
                if row['id']!=keeper['id']:
                    conn.execute(
                        "UPDATE training_requests SET state='superseded',message=? WHERE id=?",
                        ('Revisão repetida agrupada; a amostra pendente será verificada uma vez.',row['id']),
                    )

# Função para obter o caminho do arquivo de log do trabalhador, garantindo que o diretório exista e retornando o caminho completo do arquivo de log
def runtime():
    config = root()/'runtime.json'
    if not config.is_file():
        return None
    try:
        data = json.loads(config.read_text(encoding='utf-8'))
        python = Path(data['python'])
        return python if python.is_file() and data.get('validated') is True else None
    except (OSError,ValueError,KeyError,TypeError):
        return None

# Função para reservar uma CPU lógica para o processo de aprendizado, mantendo uma CPU fora da afinidade do processo de inferência no Windows
def reserve_learning_cpu():
    """Keep one logical CPU outside the inference process affinity on Windows."""
    global _reserved_cpu
    if _reserved_cpu is not None or os.name!='nt':return _reserved_cpu
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
    kernel.SetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.c_size_t]
    current=ctypes.c_size_t();system=ctypes.c_size_t();handle=kernel.GetCurrentProcess()
    if kernel.GetProcessAffinityMask(handle,ctypes.byref(current),ctypes.byref(system)):
        cpus=[i for i in range(current.value.bit_length()) if current.value & (1<<i)]
        if len(cpus)>=4 and kernel.SetProcessAffinityMask(handle,current.value & ~(1<<cpus[-1])):
            _reserved_cpu=cpus[-1]
    return _reserved_cpu

# Função para iniciar o processo de aprendizado em segundo plano, garantindo que apenas um processo seja executado por vez e configurando o ambiente do subprocesso com variáveis de ambiente específicas
def start_worker():
    global _worker, _worker_log
    with _lock:
        if _worker is not None and _worker.poll() is None:
            return
        python = runtime()
        if python is None:
            return
        # Source files are bundled as data; PyTorch never enters the chat executable.
        worker = Path(__file__).with_name('learning_worker.py')
        if getattr(sys, 'frozen', False):
            worker = Path(sys._MEIPASS)/'learning_code'/'app'/'vision'/'learning_worker.py'
        if _worker_log:
            _worker_log.close()
        _worker_log = (root()/'worker.log').open('a',encoding='utf-8')
        allowed={'USERNAME','SYSTEMROOT','WINDIR','TEMP','TMP','PATH','PATHEXT','COMSPEC','USERPROFILE','LOCALAPPDATA','APPDATA',
            'PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE','SYSTEMDRIVE'}
        environment={k:v for k,v in os.environ.items() if k.upper() in allowed}
        reserved=reserve_learning_cpu()
        environment.update(SOLARIS_STORAGE=str(root().parent),PYTHONUTF8='1',HF_HUB_OFFLINE='1',SOLARIS_LEARNING_CPU=str(reserved) if reserved is not None else '')
        _worker = subprocess.Popen([str(python),str(worker),'--storage',str(root().parent),'--parent',str(os.getpid())],
            stdout=_worker_log,stderr=_worker_log,stdin=subprocess.DEVNULL,
            env=environment,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

# Função para interromper o processo de aprendizado em segundo plano, garantindo que o processo seja encerrado corretamente e liberando os recursos associados
def stop_worker():
    global _worker
    with _lock:
        if _worker and _worker.poll() is None:
            _worker.terminate()
            try:
                _worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _worker.kill()
        _worker = None

# Função para verificar se o processo de aprendizado em segundo plano está em execução, retornando True se estiver ativo e False caso contrário
def capture(project_id, content_b64, result):
    import cv2  # type: ignore[import-untyped]
    import numpy as np
    key = scope(project_id)
    now = time.time()
    with connect() as conn:
        conn.execute('INSERT OR IGNORE INTO settings(scope) VALUES(?)',(key,))
        latency=float(result.get('elapsed_ms',0))
        if 0<=latency<120000:
            conn.execute('INSERT INTO live_context(scope,latency,frames,updated,scene) VALUES(?,?,1,?,?) ON CONFLICT(scope) DO UPDATE SET latency=CASE WHEN excluded.updated-live_context.updated>10 THEN excluded.latency ELSE 0.8*latency+0.2*excluded.latency END,frames=CASE WHEN excluded.updated-live_context.updated>10 THEN 1 ELSE frames+1 END,updated=excluded.updated,scene=excluded.scene',(key,latency,now,json.dumps(result.get('environment',{}).get('context',{}),ensure_ascii=False)))
        last_live = conn.execute('SELECT last_live FROM settings WHERE scope=?',(key,)).fetchone()[0]
        if key not in _sessions or now-last_live>120 or int(now//120)!=int(last_live//120):
            _sessions[key]=uuid.uuid4().hex
        conn.execute('UPDATE settings SET last_live=? WHERE scope=?',(now,key))
        enabled = conn.execute('SELECT enabled FROM settings WHERE scope=?',(key,)).fetchone()[0]
        if not enabled or now-_last.get(key,0) < 3:
            return
        _last[key] = now
        image = cv2.imdecode(np.frombuffer(base64.b64decode(content_b64,validate=True),np.uint8),cv2.IMREAD_COLOR)
        if image is None:
            return
        gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        if cv2.Laplacian(gray,cv2.CV_64F).var() < 35 or gray.mean() < 15 or gray.mean() > 245:
            return
        small = cv2.resize(gray,(9,8))
        signature = ''.join('1' if x else '0' for x in (small[:,1:]>small[:,:-1]).flat)
        recent = conn.execute("SELECT signature FROM samples WHERE scope=? AND state!='archived' ORDER BY created DESC LIMIT 256",(key,)).fetchall()
        if any(sum(a!=b for a,b in zip(signature,r[0])) < 7 for r in recent):
            return
        count,size = conn.execute("SELECT count(*),coalesce(sum(byte_size),0) FROM samples WHERE state!='archived'").fetchone()
        if count >= 3000 or size >= 1_000_000_000:
            conn.execute('UPDATE settings SET message=? WHERE scope=?',('Limite de coleta atingido; exemplos preservados.',key))
            return
        ok, encoded = cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])
        if not ok:
            return
        data = encoded.tobytes()
        sample_id = hashlib.sha256(data).hexdigest()
        relative = Path('samples')/key/f'{sample_id}.jpg'
        target = root()/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        conn.execute("DELETE FROM samples WHERE scope=? AND id=? AND state='archived'",(key,sample_id))
        conn.execute('INSERT OR IGNORE INTO samples(id,scope,session,created,signature,image,byte_size,model,detections) VALUES(?,?,?,?,?,?,?,?,?)',
            (sample_id,key,_sessions[key],now,signature,str(relative),len(data),result['model'],json.dumps(result['detections'])))
    start_worker()

# Função para remover diretórios de artefatos gerados, garantindo que o caminho esteja dentro do armazenamento permitido e que o nome do diretório seja um hash válido
def status(project_id, enabled=None):
    key = scope(project_id)
    with connect() as conn:
        conn.execute('INSERT OR IGNORE INTO settings(scope) VALUES(?)',(key,))
        if enabled is not None:
            if type(enabled) is not bool:
                raise ValueError('Estado de aprendizado inválido.')
            conn.execute('UPDATE settings SET enabled=? WHERE scope=?',(int(enabled),key))
        coalesce_training_requests(conn,key)
        setting = dict(conn.execute('SELECT * FROM settings WHERE scope=?',(key,)).fetchone())
        counts = {r['state']:r['n'] for r in conn.execute("SELECT state,count(*) n FROM samples WHERE scope=? AND state!='archived' GROUP BY state",(key,))}
        jobs = [dict(r) for r in conn.execute('SELECT id,state,message,created,metrics FROM jobs WHERE scope=? ORDER BY created DESC LIMIT 5',(key,))]
        events = [dict(r) for r in conn.execute('SELECT created,message FROM events WHERE scope=? ORDER BY id DESC LIMIT 8',(key,))]
        requests=[dict(r) for r in conn.execute('SELECT id,model,state,message,job_id FROM training_requests WHERE scope=? ORDER BY created DESC LIMIT 6',(key,))]
    start_worker()
    return {**setting,'runtime_ready':runtime() is not None,'worker_running':_worker is not None and _worker.poll() is None,
        'samples':counts,'jobs':jobs,'events':events,'requests':requests,'concurrent':True,'learning_cpu':_reserved_cpu,'training_model':'yolo26x + yolo26s','collection_limit':3000,
        'message':setting['message'] if runtime() else 'Motor de aprendizado ainda não instalado.'}

# Função para solicitar o treinamento de um modelo
def request_training(project_id,sample_id=None):
    key=scope(project_id)
    identifiers=[]
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('INSERT OR IGNORE INTO settings(scope) VALUES(?)',(key,))
        if sample_id is not None and not conn.execute('SELECT 1 FROM samples WHERE scope=? AND id=?',(key,sample_id)).fetchone():
            raise ValueError('Exemplo não encontrado neste projeto.')
        conn.execute('UPDATE settings SET enabled=1 WHERE scope=?',(key,))
        if sample_id:
            review=conn.execute('SELECT labels,complete FROM human_reviews WHERE scope=? AND sample_id=?',(key,sample_id)).fetchone()
            source=[[(b['name'],b['xyxy']) for b in json.loads(review['labels'])],review['complete']] if review else []
        else:
            source=[tuple(r) for r in conn.execute("SELECT id,labels FROM samples WHERE scope=? AND state='labeled' ORDER BY id",(key,))]
        source_hash=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
        for model in ('yolo26s','yolo26x'):
            if sample_id is None:
                existing=conn.execute("SELECT id FROM training_requests WHERE scope=? AND model=? AND sample_id IS NULL AND state IN ('queued','preparing','verifying','training','paused') ORDER BY created LIMIT 1",(key,model)).fetchone()
            else:
                existing=conn.execute("SELECT id FROM training_requests WHERE scope=? AND model=? AND sample_id=? AND source_hash=? AND state IN ('queued','preparing','verifying','training','paused') ORDER BY created DESC LIMIT 1",(key,model,sample_id,source_hash)).fetchone()
            identifier=existing[0] if existing else uuid.uuid4().hex
            if not existing:
                conn.execute('INSERT INTO training_requests(id,scope,model,created,state,message,sample_id,job_id,source_hash) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,key,model,time.time(),'queued','Solicitação registrada; aguardando processamento.',sample_id,None,source_hash))
            elif sample_id is None:
                conn.execute("UPDATE training_requests SET source_hash=? WHERE id=? AND state!='training'",(source_hash,identifier))
            identifiers.append(identifier)
        event(conn,key,'Treinamento de YOLO26s e YOLO26x solicitado. Métricas serão medidas, não alteradas manualmente.')
    start_worker()
    return {'request_ids':identifiers,'runtime_ready':runtime() is not None,'message':'Solicitação registrada para os dois modelos. A ativação depende de avaliação e evidência suficiente.'}


def incorporate(project_id,revision_id,payload,complete=False):
    import cv2  # type: ignore[import-untyped]
    import numpy as np
    from app.vision.detector import LABELS,LABELS_EN
    from app.vision.object_vocabulary import canonical_object_name
    key=scope(project_id)
    if type(complete) is not bool or type(revision_id) is not int or revision_id<1:
        raise ValueError('Revisão inválida.')
    encoded=payload.get('image','')
    if not encoded.startswith(('data:image/jpeg;base64,','data:image/png;base64,')) or len(encoded)>16_000_000:
        raise ValueError('Imagem da revisão inválida.')
    image=cv2.imdecode(np.frombuffer(base64.b64decode(encoded.split(',',1)[1],validate=True),np.uint8),cv2.IMREAD_COLOR)
    if image is None or image.shape[0]*image.shape[1]>20_000_000:
        raise ValueError('Imagem da revisão inválida.')
    h,w=image.shape[:2]
    if payload.get('width')!=w or payload.get('height')!=h:
        raise ValueError('Dimensões da revisão não correspondem à imagem.')
    boxes=payload.get('detections',[])
    if not isinstance(boxes,list) or len(boxes)>100:
        raise ValueError('Quantidade de marcações inválida.')
    canonical={pt.casefold():en.replace('_',' ') for pt,en in zip(LABELS,LABELS_EN)}
    canonical.update({en.replace('_',' ').casefold():en.replace('_',' ') for en in LABELS_EN})
    canonical.update({'televisão':'tv','televisor':'tv','televisao':'tv','sofá':'couch','sofa':'couch','celular':'cell phone','notebook':'laptop','gaveteiro':'chest of drawers','guarda-roupa':'wardrobe','guarda roupa':'wardrobe','mesa de cabeceira':'nightstand'})
    labels=[]
    for box in boxes:
        if not complete and box.get('source')!='human':
            continue
        name=box.get('label','').strip()
        values=[box.get(k) for k in ('x','y','width','height')]
        if not name or len(name)>120 or not all(type(v) in (float,int) and __import__('math').isfinite(v) for v in values):
            raise ValueError('Marcação inválida ou sem nome.')
        x,y,bw,bh=values
        if min(x,y)<0 or min(bw,bh)<=0 or x+bw>w+.01 or y+bh>h+.01:
            raise ValueError('Marcação fora da imagem.')
        labels.append({'name':canonical.get(name.casefold(),canonical_object_name(name)),'name_pt':name,'xyxy':[x,y,x+bw,y+bh],
            'score':1,'source':'human','revision_id':revision_id})
    if not labels:
        raise ValueError('Desenhe/corrija uma marcação ou confirme a revisão completa da imagem.')
    ok,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,90])
    if not ok:raise ValueError('Falha ao preparar imagem da revisão.')
    data=jpeg.tobytes();sample_id=hashlib.sha256(data).hexdigest()
    relative=Path('samples')/key/f'{sample_id}.jpg'
    target=root()/relative;target.parent.mkdir(parents=True,exist_ok=True)
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        size=conn.execute('SELECT coalesce(sum(byte_size),0) FROM samples').fetchone()[0]
        old=conn.execute('SELECT byte_size FROM samples WHERE scope=? AND id=?',(key,sample_id)).fetchone()
        count=conn.execute("SELECT count(*) FROM samples WHERE state!='archived'").fetchone()[0]
        if (not old and count>=3000) or size-(old[0] if old else 0)+len(data)>1_000_000_000:raise ValueError('Limite de armazenamento de exemplos atingido.')
        target.write_bytes(data)
        conn.execute('INSERT INTO human_reviews VALUES(?,?,?,?,?,?) ON CONFLICT(scope,sample_id) DO UPDATE SET revision_id=excluded.revision_id,labels=excluded.labels,complete=excluded.complete,created=excluded.created',
            (key,sample_id,revision_id,json.dumps(labels,ensure_ascii=False),int(complete),time.time()))
        conn.execute("INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(scope,id) DO UPDATE SET labels=excluded.labels,state=excluded.state,detections=excluded.detections,byte_size=excluded.byte_size",
            (sample_id,key,_sessions.get(key,uuid.uuid4().hex),time.time(),'human-'+sample_id,str(relative),len(data),payload.get('model','revisão humana'),json.dumps(boxes),json.dumps(labels) if complete else None,'labeled' if complete else 'pending'))
        event(conn,key,'Revisão humana incorporada. Sugestões não confirmadas serão verificadas separadamente.')
    return {**request_training(project_id,sample_id),'incorporated':len(labels),'revision_id':revision_id}
