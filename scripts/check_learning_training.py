"""Real evaluation compatibility and checkpoint-on-pause checks; no model promotion."""
# torch/ultralytics/transformers/psutil existem só no runtime de aprendizado separado (%APPDATA%), não no venv do engine.
# pyright: reportMissingImports=false, reportMissingModuleSource=false
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))


def main():
    import torch
    from ultralytics import YOLO
    from app.vision.learning_worker import metrics,approved
    torch.set_num_threads(2)
    root=ROOT/'storage/learning'
    config=json.loads((root/'runtime.json').read_text(encoding='utf-8'))
    data=root/'benchmark/dataset/data.yaml'
    original=YOLO(config['checkpoint'])
    candidate=YOLO(root/'benchmark/train/weights/best.pt')
    assert all(original.names[i]==candidate.names[i] for i in range(80))
    before=metrics(original,data,data)
    after=metrics(candidate,data,data)
    class Pause(Exception):
        pass
    def pause(trainer):
        trainer.save_model()
        raise Pause()
    original.add_callback('on_train_batch_end',pause)
    try:
        original.train(data=str(data),device='cpu',batch=1,imgsz=320,epochs=3,workers=0,freeze=22,
            optimizer='SGD',lr0=.0005,amp=False,cache=False,plots=False,save=True,save_period=1,
            project=str(root/'benchmark'),name='pause',exist_ok=True,verbose=False,mosaic=0,close_mosaic=0)
    except Pause:
        saved=root/'benchmark/pause/weights/last.pt'
        assert saved.is_file()
        restored=YOLO(saved)
        assert restored.model.yaml['scale']=='x'
    else:
        raise AssertionError('Treino não foi pausado.')
    report={'known_ids_preserved':True,'evaluation_80_against_81_supported':True,'pause_checkpoint_loads':True,
        'baseline_proxy':before['local_proxy'],'candidate_proxy':after['local_proxy'],
        'would_pass_gate':approved(before,after),'active':False,'note':'Dados do ensaio não medem generalização.'}
    (root/'benchmark/training-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
