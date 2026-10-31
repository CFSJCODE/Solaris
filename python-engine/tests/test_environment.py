import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.vision.environment import Scene
from app.vision.detector import LABELS, LABELS_EN
from app.vision.object_vocabulary import EXTRA, canonical_object_name
from app.vision.learning_worker import EXTRA as OWL_EXTRA


class EnvironmentTests(unittest.TestCase):
    def test_temporal_stability_learning_and_reload_without_images(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'ambiente.json';scene=Scene(path)
            frame={'width':640,'height':480,'detections':[{'class_id':28,'label':'mala','confidence':.9,'x':50.,'y':60.,'width':100.,'height':80.}]}
            first=scene.observe(copy.deepcopy(frame),100)
            self.assertFalse(first['detections'][0]['stable']);track=first['detections'][0]['track_id']
            for i in range(1,35):result=scene.observe(copy.deepcopy(frame),100+i)
            self.assertEqual(result['detections'][0]['track_id'],track)
            self.assertTrue(result['detections'][0]['stable']);self.assertIn('mala',result['environment']['recurring'])
            self.assertTrue(path.is_file())
            saved=json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('image',saved);self.assertNotIn('detections',saved)
            self.assertGreater(Scene(path).profile['classes']['28']['observations'],0)
            self.assertEqual(len(Scene(path).tracks),0)

    def test_transient_or_different_class_does_not_become_stable(self):
        with tempfile.TemporaryDirectory() as d:
            scene=Scene(Path(d)/'scene.json')
            for i in range(5):
                box={'class_id':i,'label':LABELS[i],'confidence':.9,'x':0.,'y':0.,'width':50.,'height':50.}
                result=scene.observe({'width':640,'height':480,'detections':[box]},100+i)
                self.assertFalse(result['detections'][0]['stable'])
            self.assertFalse(scene.profile['classes'])

    def test_portuguese_coco_labels_keep_the_original_identifiers(self):
        self.assertEqual(len(LABELS),80)
        self.assertEqual(LABELS[28],'mala');self.assertEqual(LABELS[0],'pessoa');self.assertEqual(LABELS[5],'ônibus')

    def test_local_vocabulary_normalizes_requested_objects_and_synonyms(self):
        examples={
            'caixas de som':'speaker',
            'powerbank':'power bank',
            'bateria externa':'power bank',
            'armários':'cabinet',
            'armário de cozinha':'kitchen cabinet',
            'janelas':'window',
            'porta':'door',
            'multímetro digital':'multimeter',
        }
        for label,canonical in examples.items():
            with self.subTest(label=label):
                self.assertEqual(canonical_object_name(label),canonical)
        self.assertTrue({'speaker','power bank','cabinet','kitchen cabinet','window','door','multimeter'} <=
                        {name for name,_ in EXTRA})
        self.assertTrue({'speaker','power bank','cabinet','kitchen cabinet','window','door','multimeter'} <=
                        {name for name,_ in OWL_EXTRA})

    def test_room_hypotheses_prioritize_contextual_object_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            scene=Scene(Path(directory)/'bedroom.json')
            bed={'class_id':59,'label':'cama','confidence':.9,'x':0.,'y':0.,'width':40.,'height':30.}
            for now in range(8):
                result=scene.observe({'width':64,'height':64,'detections':[copy.deepcopy(bed)]},100+now)
            self.assertEqual(result['environment']['context']['hypothesis'],'quarto')
            self.assertTrue({'cabinet','window','door','speaker','power bank'} <=
                            set(result['environment']['context']['queries']))

    def test_office_context_prioritizes_electronics_and_tool_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            scene=Scene(Path(directory)/'office.json')
            boxes=[
                {'class_id':LABELS_EN.index(name),'label':name,'confidence':.9,
                 'x':index*15.,'y':0.,'width':12.,'height':12.}
                for index,name in enumerate(('laptop','keyboard','mouse'))
            ]
            for now in range(8):
                result=scene.observe({'width':64,'height':64,'detections':copy.deepcopy(boxes)},100+now)
            self.assertEqual(result['environment']['context']['hypothesis'],'escritório')
            self.assertTrue({'speaker','power bank','multimeter','tool cabinet'} <=
                            set(result['environment']['context']['queries']))


if __name__=='__main__':unittest.main()
