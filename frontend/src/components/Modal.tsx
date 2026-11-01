import { useEffect, useRef, ReactNode } from "react"

export default function Modal({
  title,
  children,
  onClose,
}: {
  title: string
  children: ReactNode
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Contextual transition: the dialog grows from the control that opened it.
    const opener = document.activeElement as HTMLElement | null
    const from = opener && opener !== document.body ? opener.getBoundingClientRect() : null
    el.showModal()
    if (from) {
      const box = el.getBoundingClientRect()
      const x = from.left + from.width / 2 - box.left
      const y = from.top + from.height / 2 - box.top
      el.style.transformOrigin = `${Math.round(x)}px ${Math.round(y)}px`
    }
    return () => {
      el.close()
      // Return focus to the opener (Fluent dialog pattern).
      if (opener && document.contains(opener)) opener.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className="workspace-modal"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
    >
      <header>
        <h2>{title}</h2>
        <button className="btn-ghost" onClick={onClose}>
          Fechar
        </button>
      </header>
      {children}
    </dialog>
  )
}
