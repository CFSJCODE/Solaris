import { useEffect, useMemo, useState } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { Project, formatDate } from '../projectApi'
import Modal from '../components/Modal'

export default function ProjectsPage({ projects, onChanged, onOpen }: { projects: Project[]; onChanged: () => Promise<void>; onOpen: (id: number) => void }) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('updated')
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { void onChanged() }, [onChanged])
  const filtered = useMemo(() => projects.filter(p => `${p.name} ${p.description ?? ''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).sort((a,b) => sort === 'name' ? a.name.localeCompare(b.name) : sort === 'created' ? b.id-a.id : b.updated_at.localeCompare(a.updated_at)), [projects,query,sort])
  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const id = await invoke<number>('create_project', {name:name.trim(),description:description.trim() || null})
      await onChanged(); setCreating(false); setName(''); setDescription(''); onOpen(id)
    } catch (err) { setError(String(err)) } finally {setBusy(false)}
  }
  async function pin(p: Project) {
    try { await invoke('project_settings',{id:p.id,instructions:p.instructions,pinned:!p.pinned}); await onChanged() }
    catch (err) {setError(String(err))}
  }
  function group(title: string, list: Project[]) {
    if (!list.length) return null
    return <section className="project-section"><h2>{title} <span>{list.length}</span></h2><div className="project-grid">{list.map(p => <article className="project-tile" key={p.id}>
      <button className="project-open" onClick={() => onOpen(p.id)}>
        <span className="project-monogram" aria-hidden="true">{p.name.slice(0,2).toUpperCase()}</span>
        <span><strong>{p.name}</strong><span className="project-summary">{p.description || 'Adicione arquivos, instruções e conversas.'}</span>
        <span className="project-meta">{p.conversation_count} conversas · {p.file_count} arquivos · {formatDate(p.updated_at)}</span></span>
      </button>
      <button className="project-pin" aria-label={p.pinned ? `Desafixar ${p.name}` : `Fixar ${p.name}`} aria-pressed={p.pinned} onClick={() => void pin(p)}>{p.pinned ? 'Fixado' : 'Fixar'}</button>
    </article>)}</div></section>
  }
  return <section className="workspace-page">
    <header className="workspace-heading"><div><span className="workspace-eyebrow">SEU ESPAÇO DE TRABALHO</span><h1>Projetos</h1><p>Arquivos, memórias e conversas que permanecem juntos.</p></div><button className="btn-primary" onClick={() => setCreating(true)}>Novo projeto</button></header>
    <div className="workspace-filters"><label className="sr-only" htmlFor="project-search">Buscar projetos</label><input id="project-search" className="workspace-input" type="search" placeholder="Buscar por nome ou descrição" value={query} onChange={e => setQuery(e.target.value)} /><label>Ordenar por <select className="workspace-select" value={sort} onChange={e => setSort(e.target.value)}><option value="updated">Atividade recente</option><option value="created">Criação</option><option value="name">Nome</option></select></label></div>
    {error && <p role="alert" className="workspace-error">{error}</p>}
    {group('Fixados',filtered.filter(p => p.pinned))}
    {group('Todos os projetos',filtered.filter(p => !p.pinned))}
    {!filtered.length && <div className="workspace-empty"><span className="workspace-eyebrow">UM LUGAR PARA CADA IDEIA</span><h2>{query ? 'Nenhum projeto encontrado' : 'Comece pelo seu primeiro projeto'}</h2><p>{query ? 'Tente outro nome ou descrição.' : 'Reúna os documentos de referência e escreva o que a IA deve considerar em todas as conversas.'}</p>{!query && <button className="btn-primary" onClick={() => setCreating(true)}>Criar projeto</button>}</div>}
    {creating && <Modal title="Novo projeto" onClose={() => {if(!busy)setCreating(false)}}><form className="workspace-form" onSubmit={e => void create(e)}><label>Nome<input autoFocus className="workspace-input" value={name} onChange={e => setName(e.target.value)} maxLength={120} required /></label><label>Descrição<textarea className="workspace-input" rows={3} value={description} onChange={e => setDescription(e.target.value)} maxLength={2000} placeholder="Qual é o objetivo deste projeto?" /></label><p className="workspace-muted">O projeto terá arquivos Markdown de referência e memória próprios.</p>{error && <p role="alert" className="workspace-error">{error}</p>}<button className="btn-primary" disabled={busy || !name.trim()}>{busy ? 'Criando…' : 'Criar projeto'}</button></form></Modal>}
  </section>
}
