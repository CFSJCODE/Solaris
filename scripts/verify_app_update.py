"""Backup and verify local conversations and Markdown around an application update."""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path


def inspect(storage):
    with closing(sqlite3.connect((storage/'solaris.db').as_uri()+'?mode=ro',uri=True)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts={name:conn.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in names}
    hashes={str(p.relative_to(storage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (storage/'memory').rglob('*.md')}
    learning_counts={}
    learner=storage/'learning/learning.sqlite3'
    if learner.exists():
        with closing(sqlite3.connect(learner.as_uri()+'?mode=ro',uri=True)) as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                learning_counts[name]=conn.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]
    return {'tables':counts,'markdown':hashes,'learning_tables':learning_counts}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['snapshot','verify'])
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--version',default='0.4.0')
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',args.version):
        raise ValueError('Versão inválida.')
    storage=Path(os.environ['APPDATA'])/'com.cfsjcode.solaris/storage'
    if args.action=='snapshot':
        backup=storage.parent/'backups'/('antes-'+args.version+'-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        with closing(sqlite3.connect((storage/'solaris.db').as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(backup/'solaris.db')) as target:
            source.backup(target)
        learner=storage/'learning/learning.sqlite3'
        if learner.exists():
            with closing(sqlite3.connect(learner.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(backup/'learning.sqlite3')) as target:
                source.backup(target)
        for name in ('learning/active','learning/versions'):
            if (storage/name).is_dir():shutil.copytree(storage/name,backup/name)
        for name in ('memory','environment'):
            if (storage/name).is_dir():
                shutil.copytree(storage/name,backup/name)
        manifest=backup/'manifest.json'
        manifest.write_text(json.dumps(inspect(storage),ensure_ascii=False,indent=2),encoding='utf-8')
        # Local pointer contains no credentials or file contents.
        pointer=Path(__file__).resolve().parents[1]/f'storage/update-{args.version}-manifest.txt'
        pointer.write_text(str(manifest),encoding='utf-8')
        print('Backup consistente do banco e dos documentos concluído.')
    else:
        manifest=args.manifest or Path((Path(__file__).resolve().parents[1]/f'storage/update-{args.version}-manifest.txt').read_text(encoding='utf-8'))
        before=json.loads(manifest.read_text(encoding='utf-8'))
        after=inspect(storage)
        assert all(after['tables'].get(k,-1)>=v for k,v in before['tables'].items()),'Contagem de registros diminuiu.'
        assert all(after['markdown'].get(k)==v for k,v in before['markdown'].items()),'Documento anterior foi alterado.'
        assert all(after['learning_tables'].get(k,-1)>=v for k,v in before.get('learning_tables',{}).items()),'Registros de aprendizado diminuíram.'
        print('Bancos íntegros, registros de conversas/aprendizado preservados e Markdown anteriores inalterados.')


if __name__=='__main__':
    main()
