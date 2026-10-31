import { useEffect, useRef, ReactNode } from 'react'

export default function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const el = ref.current; el?.showModal(); return () => el?.close() }, [])
  return <dialog ref={ref} className="workspace-modal" aria-label={title} onCancel={e => {e.preventDefault(); onClose()}}>
    <header><h2>{title}</h2><button className="btn-ghost" onClick={onClose}>Fechar</button></header>
    {children}
  </dialog>
}
