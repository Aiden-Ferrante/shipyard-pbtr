import React, { useEffect, useState, useRef, useMemo } from 'react'
import { CycleChip } from './kit'

/* Jump to a project. Navigation only — despite the name, it runs no commands.
   The kit's dialog, with the roles a combobox owes: listbox, options, the
   active descendant, Escape. */

export function CommandPalette({ projects, onPick, onClose }) {
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const hits = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return projects
    return projects.filter(p =>
      `${p.name} ${p.id} ${(p.tags || []).join(' ')}`
        .toLowerCase().includes(needle))
  }, [q, projects])

  useEffect(() => { setI(0) }, [q])

  const onKey = e => {
    if (e.key === 'Escape') return onClose()
    if (e.key === 'ArrowDown') { e.preventDefault(); setI(v => Math.min(v + 1, hits.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setI(v => Math.max(v - 1, 0)) }
    if (e.key === 'Enter' && hits[i]) { e.preventDefault(); onPick(hits[i].id) }
  }

  return (
    <div className="fleet-dialog-scrim" onClick={onClose}>
      <div className="fleet-dialog narrow p-0" role="dialog" aria-modal="true" aria-label="Jump to project"
        onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef} value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey}
          placeholder="Jump to project…"
          role="combobox" aria-expanded="true" aria-controls="jump-list"
          aria-activedescendant={hits[i] ? `jump-opt-${i}` : undefined}
          className="w-full border-0 border-b border-border bg-transparent px-4 py-3 text-body text-ink
            outline-offset-[-2px] placeholder:text-faint"
        />
        <ul id="jump-list" role="listbox" className="m-0 max-h-72 list-none overflow-y-auto p-0 py-1">
          {hits.length === 0 && (
            <li className="px-4 py-3 text-body text-faint" aria-disabled="true">no matches</li>
          )}
          {hits.map((p, idx) => (
            <li key={p.id} id={`jump-opt-${idx}`} role="option" aria-selected={idx === i}>
              <button
                tabIndex={-1}
                onMouseEnter={() => setI(idx)}
                onClick={() => onPick(p.id)}
                className={`flex w-full cursor-pointer items-center justify-between gap-3 border-0 bg-transparent px-4 py-2 text-left text-body
                  ${idx === i ? 'bg-accent/10 text-accent-text' : 'text-dim'}`}
              >
                <span className="truncate">{p.name || p.id}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="text-meta text-faint">{p.open_tasks || 0} open</span>
                  <CycleChip cycles={p.cycles} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
