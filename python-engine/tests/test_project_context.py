import io
import json
import sys
import unittest
import zipfile
import subprocess
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.chat.memory_stream import MemoryStream
from app.rag.chunker import extract_text


class ProjectContextTests(unittest.TestCase):
    def test_chat_protocol_uses_context_and_separates_memory_without_paid_calls(self):
        engine=Path(__file__).resolve().parents[1]
        harness=r'''
import sys, types, runpy, asyncio, json
sys.path.insert(0,sys.argv[1])
providers=types.ModuleType('app.chat.providers')
async def fake(messages,model,system=None):
    assert '17 de dezembro' in system
    for text in ['O prazo é 17 de dezembro. [requisitos.md]', '<solaris_', 'memory>{"updates":[{"file":"DECISOES.md","content":"Decisão confirmada: usar CPU."}]}</solaris_memory>']:
        yield {'type':'delta','text':text}
    yield {'type':'done','usage':{'model':'fixture','provider':'fixture'}}
providers.stream_anthropic=fake
providers.stream_openrouter=fake
sys.modules['app.chat.providers']=providers
amr=types.ModuleType('app.chat.amr');amr.route=lambda _:None
sys.modules['app.chat.amr']=amr
module=runpy.run_path(sys.argv[1]+'/app/main.py',run_name='fixture')
asyncio.run(module['handle_chat_stream']({'id':'test','messages':[{'role':'user','content':'Qual é o prazo?'}],'model':'fixture','provider':'anthropic','system':'Arquivo requisitos.md: prazo 17 de dezembro.','memory_files':['DECISOES.md']}))
'''
        run=subprocess.run([sys.executable,'-c',harness,str(engine)],capture_output=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)
        events=[json.loads(line) for line in run.stdout.splitlines()]
        visible=''.join(e['text'] for e in events if e['type']=='chat_delta')
        self.assertIn('17 de dezembro',visible);self.assertNotIn('solaris_memory',visible)
        self.assertEqual(next(e for e in events if e['type']=='memory_updates')['updates'][0]['file'],'DECISOES.md')
        self.assertEqual(events[-1]['type'],'chat_done')
        required=harness.replace("'memory_files':['DECISOES.md']", "'memory_required':True,'memory_files':['DECISOES.md']")
        run=subprocess.run([sys.executable,'-c',required,str(engine)],capture_output=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)
        events=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertFalse(any(e['type']=='chat_delta' for e in events))
        self.assertTrue(any(e['type']=='memory_updates' for e in events))
        missing=re.sub(r"for text in \[[^\n]+\]:", "for text in ['Vou salvar na memória.']:", required)
        run=subprocess.run([sys.executable,'-c',missing,str(engine)],capture_output=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)
        events=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertFalse(any(e['type'] in ('memory_updates','chat_delta') for e in events))
        self.assertTrue(any(e['type']=='memory_update_warning' for e in events))


    def test_metadata_is_hidden_at_every_stream_boundary(self):
        metadata=json.dumps({'updates':[{'file':'DECISOES.md','content':'Decisão confirmada: usar CPU.'}]},ensure_ascii=False)
        text='Resposta com acentuação.\n<solaris_memory>'+metadata+'</solaris_memory>'
        for step in (1,2,7,1000):
            stream=MemoryStream()
            visible=''.join(stream.feed(text[i:i+step]) for i in range(0,len(text),step))
            tail,updates,warning=stream.finish()
            self.assertEqual(visible+tail,'Resposta com acentuação.\n')
            self.assertEqual(updates[0]['file'],'DECISOES.md')
            self.assertIsNone(warning)

    def test_invalid_or_interrupted_metadata_never_becomes_a_write(self):
        for content in ('{"updates":[',json.dumps({'updates':[{'file':'../../README.md','content':'x'}]})+'</solaris_memory>'):
            stream=MemoryStream();visible=stream.feed('Resposta<solaris_memory>'+content)
            tail,updates,warning=stream.finish()
            self.assertEqual(visible+tail,'Resposta');self.assertEqual(updates,[]);self.assertIsNotNone(warning)
        stream=MemoryStream();self.assertEqual(stream.feed('Curta')+stream.finish()[0],'Curta')

    def test_markdown_bom_and_docx_are_read_as_text(self):
        self.assertEqual(extract_text(b'\xef\xbb\xbf# Memoria','text/plain'),'# Memoria')
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Decisão local</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(extract_text(output.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),'Decisão local')
        with self.assertRaisesRegex(ValueError,'Formato não suportado'):
            extract_text(b'\0\1','application/octet-stream')


if __name__=='__main__':unittest.main()
