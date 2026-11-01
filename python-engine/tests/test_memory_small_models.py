"""Desvios típicos de modelos menores (Haiku, Gemma) no bloco <solaris_memory>."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.chat.memory_stream import MemoryStream


def parse(text: str, files=None, require_tag=True):
    stream = MemoryStream(files, require_tag=require_tag)
    visible = stream.feed(text)
    tail, updates, warning = stream.finish()
    return visible + tail, updates, warning


class SmallModelMemoryTests(unittest.TestCase):
    def test_code_fence_raw_newlines_and_trailing_comma(self):
        text = (
            "Análise feita.\n<solaris_memory>\n```json\n"
            '{"updates":[{"file":"DECISOES.md","content":"- Usar Tauri\n- CPU-only",},]}\n'
            "```\n</solaris_memory>"
        )
        visible, updates, warning = parse(text)
        self.assertEqual(visible, "Análise feita.\n")
        self.assertEqual(updates, [{"file": "DECISOES.md", "content": "- Usar Tauri\n- CPU-only"}])
        self.assertIsNone(warning)

    def test_missing_closing_tag_and_case_variations(self):
        text = '<SOLARIS_MEMORY>{"updates":[{"file":"decisoes","content":"Decisão A"}]}'
        _, updates, _ = parse(text)
        self.assertEqual(updates, [{"file": "DECISOES.md", "content": "Decisão A"}])

    def test_one_bad_item_does_not_discard_the_batch(self):
        payload = {
            "updates": [
                {"file": "../segredo.md", "content": "x"},
                {"file": "NOTAS.md", "content": "arquivo inexistente"},
                {"file": "memory.md", "content": ["Ryzen 5 4600G", "32 GB RAM"]},
            ]
        }
        _, updates, warning = parse("<solaris_memory>" + json.dumps(payload) + "</solaris_memory>")
        self.assertEqual(
            updates, [{"file": "MEMORY.md", "content": "- Ryzen 5 4600G\n- 32 GB RAM"}]
        )
        self.assertIsNone(warning)

    def test_long_content_is_split_within_storage_limit(self):
        content = "\n".join(
            f"- Decisão {i}: usar acentuação e explicar a origem." for i in range(200)
        )
        block = json.dumps({"updates": [{"file": "DECISOES.md", "content": content}]})
        _, updates, _ = parse("<solaris_memory>" + block + "</solaris_memory>")
        self.assertGreater(len(updates), 1)
        self.assertLessEqual(len(updates), 5)
        for item in updates:
            self.assertLessEqual(len(item["content"].encode("utf-8")), 4000)

    def test_credentials_are_redacted_and_placeholders_ignored(self):
        payload = {
            "updates": [
                {"file": "MEMORY.md", "content": "Chave sk-ant-abcdefghijklmnopqrstu usada"},
                {"file": "DECISOES.md", "content": "decisão confirmada ou proposta, com origem"},
            ]
        }
        _, updates, _ = parse("<solaris_memory>" + json.dumps(payload) + "</solaris_memory>")
        self.assertEqual(len(updates), 1)
        self.assertNotIn("sk-ant-", updates[0]["content"])

    def test_tag_mentioned_in_prose_before_real_block(self):
        text = (
            "Vou gerar o bloco <solaris_memory> pedido.\n"
            '<solaris_memory>{"updates":[{"file":"DECISOES.md","content":"Decisão B"}]}</solaris_memory>'
        )
        _, updates, _ = parse(text)
        self.assertEqual(updates[0]["content"], "Decisão B")

    def test_bare_json_only_accepted_when_save_was_requested(self):
        text = '```json\n{"updates":[{"file":"DECISOES.md","content":"Decisão C"}]}\n```'
        self.assertEqual(parse(text)[1], [])
        self.assertEqual(parse(text, require_tag=False)[1][0]["content"], "Decisão C")

    def test_empty_allowed_list_falls_back_to_default_files(self):
        text = '<solaris_memory>{"updates":[{"file":"DECISOES.md","content":"D"}]}</solaris_memory>'
        self.assertEqual(parse(text, files=[])[1][0]["file"], "DECISOES.md")

    def test_required_save_retries_once_when_first_output_is_invalid(self):
        engine = Path(__file__).resolve().parents[1]
        harness = r"""
import sys, types, runpy, asyncio
sys.path.insert(0,sys.argv[1])
calls=[]
providers=types.ModuleType('app.chat.providers')
async def fake(messages,model,system=None):
    calls.append(len(messages))
    text = ('Resumo das decisões do AGENTS.md em prosa, sem bloco.' if len(calls)==1 else
            '<solaris_memory>{"updates":[{"file":"DECISOES.md","content":"- Decisão do AGENTS.md"}]}</solaris_memory>')
    yield {'type':'delta','text':text}
    yield {'type':'done','usage':{'model':'fixture','provider':'fixture','input_tokens':10,'output_tokens':5,'cost_usd':0.001}}
providers.stream_anthropic=fake
providers.stream_openrouter=fake
sys.modules['app.chat.providers']=providers
amr=types.ModuleType('app.chat.amr');amr.route=lambda _:None
sys.modules['app.chat.amr']=amr
module=runpy.run_path(sys.argv[1]+'/app/main.py',run_name='fixture')
asyncio.run(module['handle_chat_stream']({'id':'t','messages':[{'role':'user','content':'salve as decisões'}],'model':'claude-haiku-5-5','provider':'anthropic','memory_required':True,'memory_files':['DECISOES.md','MEMORY.md']}))
assert calls==[1,3], calls
"""
        run = subprocess.run(
            [sys.executable, "-c", harness, str(engine)],
            capture_output=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        events = [json.loads(line) for line in run.stdout.splitlines()]
        updates = next(e for e in events if e["type"] == "memory_updates")["updates"]
        self.assertEqual(updates[0]["file"], "DECISOES.md")
        self.assertFalse(any(e["type"] == "memory_update_warning" for e in events))
        done = events[-1]
        self.assertEqual(done["type"], "chat_done")
        self.assertEqual(done["usage"]["input_tokens"], 20)
        self.assertAlmostEqual(done["usage"]["cost_usd"], 0.002)


if __name__ == "__main__":
    unittest.main()
