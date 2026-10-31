"""Temporal scene adaptation. Learns bounded class statistics, never YOLO weights."""
# Copyright (c) 2024 Solaris Plataforma de IA. All rights reserved.

# Importa as bibliotecas necessárias
from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from app.vision.object_vocabulary import canonical_object_name

# Variável global para armazenar as cenas e um bloqueio para sincronização de threads
_scenes = {}
_lock = threading.Lock()

# Classe para representar o contexto do ambiente, armazenando evidências e inferindo hipóteses sobre o tipo de ambiente
def _iou(a, b):
    intersection = max(0, min(a['x']+a['width'], b['x']+b['width'])-max(a['x'],b['x'])) * max(0, min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y']))
    return intersection/max(1, a['width']*a['height']+b['width']*b['height']-intersection)


# Heuristics for investigation only. Scores are support, not calibrated probabilities.
ROOMS = {
    'quarto': ({'bed':2.0,'tv':.5,'wardrobe':1.5,'chest of drawers':1.0},
               ['wardrobe','chest of drawers','nightstand','cabinet','window','door','speaker','power bank','bed','tv']),
    'sala': ({'couch':2.0,'tv':.7,'remote':.4,'dining table':.4},
             ['couch','tv','speaker','cabinet','window','door','power bank','remote','chair']),
    'cozinha': ({'refrigerator':2.0,'oven':1.5,'microwave':1.0,'sink':.5},
                ['refrigerator','kitchen cabinet','cabinet','window','door','microwave','sink','oven']),
    'escritório': ({'laptop':1.0,'keyboard':1.0,'mouse':.8,'book':.3},
                   ['laptop','keyboard','mouse','monitor','desk','speaker','power bank','multimeter','tool cabinet','router','window','door']),
}

# Classe para representar o contexto do ambiente, armazenando evidências e inferindo hipóteses sobre o tipo de ambiente
class Context:
    def __init__(self):
        self.evidence={}
        self.last=None
        self.empty_since=None

    # Observa as caixas detectadas, atualiza as evidências e infere hipóteses sobre o tipo de ambiente com base nas evidências acumuladas
    def observe(self, boxes, now):
        from app.vision.detector import LABELS_EN
        if self.last is not None and now-self.last>30:
            self.evidence.clear()
        elapsed=max(0,now-self.last) if self.last is not None else 0
        self.last=now
        decay=math.exp(-elapsed/15)
        self.evidence={name:value*decay for name,value in self.evidence.items() if value*decay>.01}
        names=set()
        for box in boxes:
            if box.get('stable') and box.get('confidence',0)>=.5:
                idx=box.get('class_id',-1)
                name=LABELS_EN[idx].replace('_',' ') if 0<=idx<len(LABELS_EN) else {'gaveteiro':'chest of drawers','guarda-roupa':'wardrobe','mesa de cabeceira':'nightstand','escrivaninha':'desk'}.get(box['label'],box['label'])
                name=canonical_object_name(name)
                names.add(name)
        for name in names:
            self.evidence[name]=min(5,self.evidence.get(name,0)+1)
        candidates=[]
        for room,(cues,queries) in ROOMS.items():
            support=sum(weight*min(1,self.evidence.get(name,0)/3) for name,weight in cues.items())
            if support>=1.5:
                candidates.append((support,room,queries))
        candidates.sort(reverse=True)
        if not candidates or (len(candidates)>1 and candidates[0][0]-candidates[1][0]<.5):
            return {'hypothesis':'desconhecido','queries':[],'evidence':sorted(names),'kind':'hipótese heurística, não probabilidade'}
        support,room,queries=candidates[0]
        return {'hypothesis':room,'support':round(support,2),'queries':queries,
                'evidence':sorted(names),'kind':'hipótese heurística, não probabilidade'}

# Classe para representar uma cena, armazenando o contexto, as trilhas de detecção, o perfil do ambiente e gerenciando a observação e o salvamento do perfil
class Scene:
    def __init__(self, path: Path):
        self.context=Context()
        self.path = path
        self.tracks = []
        self.counter = 0
        self.last_save = 0
        self.profile = {'version': 1, 'frames': 0, 'classes': {}}
        self.warning = None
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('version') != 1 or not isinstance(data.get('classes'), dict):
                    raise ValueError('Perfil incompatível')
                self.profile = data
            except (ValueError, OSError):
                self.warning = 'Perfil anterior inválido; ele foi preservado e não será sobrescrito.'

    # Observa os resultados de detecção, atualiza as trilhas, o perfil do ambiente e salva o perfil periodicamente, retornando as detecções com informações adicionais sobre o ambiente
    def observe(self, result, now):
        self.profile['frames'] += 1
        # Tracks are short-lived and session-local: no identification of individuals.
        self.tracks = [t for t in self.tracks if now-t['last'] < 8]
        matched = set()
        boxes = []
        changed = False
        counts = {}
        for box in result['detections']:
            candidates = [(i, _iou(t['box'], box)) for i,t in enumerate(self.tracks) if i not in matched and t['box']['class_id']==box['class_id']]
            best = max(candidates, key=lambda item:item[1], default=(-1,0))
            if best[1] >= 0.25:
                index = best[0]
                track = self.tracks[index]
                track['hits'] = track['hits']+1 if now-track['last']<4 else 1
                if best[1] >= 0.7:
                    box = {**box, **{k: 0.75*box[k]+0.25*track['box'][k] for k in ('x','y','width','height')}}
                track.update(box=box, last=now)
            else:
                self.counter += 1
                track = {'id':self.counter, 'hits':1, 'last':now, 'box':dict(box)}
                self.tracks.append(track)
                index = len(self.tracks)-1
            matched.add(index)
            key = str(box['class_id'])
            stable = track['hits'] >= 3
            learned = self.profile['classes'].get(key, {}).get('observations',0)
            boxes.append({**box, 'track_id':track['id'], 'stable':stable, 'familiar':learned>=30})
            if stable:
                counts[key] = counts.get(key,0)+1
                state = self.profile['classes'].setdefault(key, {'observations':0,'label':box['label'],'mean_box':[0,0,0,0]})
                state['label'] = box['label']
                state['observations'] += 1
                features = [box['x']/result['width'],box['y']/result['height'],box['width']/result['width'],box['height']/result['height']]
                n = state['observations']
                state['mean_box'] = [old+(value-old)/n for old,value in zip(state['mean_box'],features)]
                changed = True
        context=self.context.observe(boxes,now)
        self.profile['context']=context
        # Only stable observations influence recurring-scene statistics.
        if not self.warning and (now-self.last_save >= 30) and changed:
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temporary=self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(self.profile,ensure_ascii=False,indent=2),encoding='utf-8')
                temporary.replace(self.path)
                self.last_save=now
            except OSError:
                self.warning='Não foi possível salvar o perfil do ambiente.'
        self.tracks = self.tracks[-200:]
        return {**result, 'detections':boxes, 'environment':{
            'frames':self.profile['frames'], 'stable_count':sum(b['stable'] for b in boxes),
            'recurring':[v['label'] for v in self.profile['classes'].values() if v['observations']>=30],
            'warning':self.warning,'context':context,
        }}

# Função para observar o resultado de detecção em um projeto específico, gerenciando a cena correspondente e retornando as detecções com informações adicionais sobre o ambiente
def observe(project_id, result):
    if project_id is not None and (not isinstance(project_id,int) or project_id<1):
        raise ValueError('Projeto inválido.')
    scope = f'project-{project_id}' if project_id is not None else 'general'
    root = Path(os.environ.get('SOLARIS_STORAGE','storage'))/'environment'
    key = (str(root.resolve()), scope)
    with _lock:
        if key not in _scenes:
            _scenes[key] = Scene(root/f'{scope}.json')
        return _scenes[key].observe(result,time.monotonic())
