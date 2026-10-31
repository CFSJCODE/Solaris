import { useEffect, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { MemoryFile } from '../projectApi'
import Modal from './Modal'

export default function MemoryPanel({ projectId }: {projectId:number | null}) {
  const [history,setHistory]=useState<{id:string;content:string;saved_at:number}[]|null>(null)
  const [files,setFiles]=useState<MemoryFile[]>([])
  const [active,setActive]=useState('MEMORY.md')
  const [draft,setDraft]=useState('')
  const [revision,setRevision]=useState<string | null>(null)
  const [editing,setEditing]=useState(false)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  useEffect(() => {
    let live=true
    invoke<MemoryFile[]>('project_memory_files',{projectId}).then(list => {if(live){setFiles(list);setActive('MEMORY.md');setEditing(false)}}).catch(err => {if(live)setError(String(err))})
    return () => {live=false}
  },[projectId])
  const file=files.find(f=>f.name===active)
  function edit(){if(file){setDraft(file.content);setRevision(file.revision);setEditing(true);setNotice('')}}
  async function save(){setBusy(true);setError('');try{
    const updated=await invoke<MemoryFile>('project_memory_save',{projectId,name:active,content:draft,revision})
    setFiles(prev=>[...prev.filter(f=>f.name!==updated.name),updated].sort((a,b)=>a.name.localeCompare(b.name)))
    setEditing(false);setNotice('Memória salva. A versão anterior foi preservada.')
  }catch(err){setError(String(err))}finally{setBusy(false)}}
  async function importMemory(input:FileList | null){
    const imported=input?.[0];if(!imported)return
    setBusy(true);setError('')
    try{
      if(!imported.name.toLowerCase().endsWith('.md') || imported.size>256000)throw new Error('Use Markdown de até 256 KB.')
      const text=await imported.text()
      const current=files.find(f=>f.name.toLowerCase()===imported.name.toLowerCase())
      if(current){setActive(current.name);setDraft(text);setRevision(current.revision);setEditing(true);setNotice('Confira o conteúdo importado antes de substituir a memória existente. A versão anterior será preservada.')}
      else{const added=await invoke<MemoryFile>('project_memory_save',{projectId,name:imported.name,content:text,revision:null});setFiles(prev=>[...prev,added]);setActive(added.name);setNotice('Arquivo Markdown adicionado à memória do projeto.')}
    }catch(err){setError(String(err))}finally{setBusy(false)}
  }
  async function showHistory(){try{setHistory(await invoke('project_memory_history',{projectId,name:active}))}catch(err){setError(String(err))}}
  return <section className="memory-workspace">
    <div className="workspace-section-heading"><div><h2>Documentos vivos</h2><p>Contexto e decisões que atravessam as conversas deste projeto.</p></div><label className="btn-ghost file-button">Importar Markdown<input type="file" accept=".md" disabled={busy || editing} onChange={e=>{void importMemory(e.target.files);e.target.value=''}} /></label></div>
    <p className="workspace-muted">O chat consulta estes arquivos e acrescenta registros nas respostas com decisões ou mudanças duráveis. Cada atualização automática identifica a conversa de origem e preserva uma cópia anterior.</p>
    {error && <p role="alert" className="workspace-error">{error}</p>}{notice && <p role="status" className="workspace-notice">{notice}</p>}
    <div className="memory-layout"><nav aria-label="Arquivos de memória">{files.map(f=><button key={f.name} disabled={editing} className={active===f.name?'active':''} onClick={()=>{setActive(f.name);setNotice('');setError('')}}>{f.name}<span>{f.content.length.toLocaleString('pt-BR')} caracteres</span></button>)}</nav>
      <div className="memory-editor"><header><strong>{active}</strong><div className="workspace-actions">{editing?<><button className="btn-ghost" disabled={busy} onClick={()=>{setEditing(false);setError('')}}>Cancelar</button><button className="btn-primary" disabled={busy} onClick={()=>void save()}>{busy?'Salvando…':'Salvar memória'}</button></>:<><button className="btn-ghost" disabled={!file || busy} onClick={()=>void showHistory()}>Histórico</button><button className="btn-ghost" disabled={!file || busy} onClick={edit}>Editar documento</button></>}</div></header>
      {editing?<textarea aria-label={`Editar ${active}`} className="memory-textarea" value={draft} onChange={e=>setDraft(e.target.value)} spellCheck={false}/>:<div className="workspace-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{file?.content ?? 'Carregando memória…'}</ReactMarkdown></div>}
      </div></div>
    {history && <Modal title={`Histórico de ${active}`} onClose={()=>setHistory(null)}><p className="workspace-muted">Até 20 versões anteriores. Recuperar abre uma edição; a versão atual só muda ao salvar.</p>{history.map(version=><details key={version.id} className="memory-history-entry"><summary>{new Date(version.saved_at*1000).toLocaleString('pt-BR')}</summary><pre className="file-preview">{version.content}</pre><button className="btn-ghost" onClick={()=>{setDraft(version.content);setRevision(file?.revision??null);setEditing(true);setHistory(null)}}>Recuperar para edição</button></details>)}{!history.length&&<p>Nenhuma versão anterior ainda.</p>}</Modal>}
  </section>
}
