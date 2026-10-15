import React, { useEffect, useState, useCallback, useRef } from 'react'
import { marked } from 'marked'
import { Loading } from './ui'

/* An argument: the essay defending one waypoint. Reading and writing get a
   whole page, because an essay in a 300px column is an essay nobody writes.

   `embedded` drops the page's own centring and back link so the same component
   can be the body of the goal window on the chart. One essay surface, two
   frames — a second editor would be a second place for the reasoning to live. */

export function ArgumentPage({ pid, onClose, embedded = false }) {
  const [doc, setDoc] = useState(undefined)
  const [problem, setProblem] = useState(null)
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState('')
  const [status, setStatus] = useState('')       // '', 'saving', 'saved', or an error
  const box = useRef(null)
  const dirty = useRef(false)
  const mtime = useRef(null)

  const load = useCallback(() => {
    fetch(`/api/chart/${pid}`).then(r => r.ok ? r.json() : null)
      .then(d => setProblem(d?.node ?? null))
    return fetch(`/api/problems/${pid}/argument`).then(r => r.json())
      .then(d => { setDoc(d); setBody(d.body || ''); mtime.current = d.mtime })
  }, [pid])
  useEffect(() => { load() }, [load])

  const save = useCallback((text) => {
    setStatus('saving')
    return fetch(`/api/problems/${pid}/argument`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: text, mtime: mtime.current }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(d => {
        // Keep the new mtime or the guard fires against our own last save.
        mtime.current = d.mtime
        setDoc(d); dirty.current = false; setStatus('saved')
      })
      .catch(e => setStatus(e.message))
  }, [pid])

  // Autosave on a pause. Writing should never involve remembering to save, and the
  // mtime guard still protects a file edited somewhere else.
  useEffect(() => {
    if (!editing || !dirty.current) return
    const t = setTimeout(() => save(body), 1200)
    return () => clearTimeout(t)
  }, [body, editing, save])

  const grow = () => {
    const el = box.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }
  useEffect(() => { if (editing) grow() }, [editing, body])

  const onType = e => { dirty.current = true; setStatus(''); setBody(e.target.value) }

  const wrap = (mark) => {
    const el = box.current
    if (!el) return
    const { selectionStart: a, selectionEnd: b, value } = el
    const next = value.slice(0, a) + mark + value.slice(a, b) + mark + value.slice(b)
    dirty.current = true
    setBody(next)
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(a + mark.length, b + mark.length)
    })
  }

  const onKey = e => {
    const cmd = e.metaKey || e.ctrlKey
    if (cmd && e.key.toLowerCase() === 's') { e.preventDefault(); save(body) }
    if (cmd && e.key.toLowerCase() === 'b') { e.preventDefault(); wrap('**') }
    if (cmd && e.key.toLowerCase() === 'i') { e.preventDefault(); wrap('_') }
  }

  useEffect(() => {
    const onKeyGlobal = e => {
      if (e.key === 'Escape' && !/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) onClose()
    }
    window.addEventListener('keydown', onKeyGlobal)
    return () => window.removeEventListener('keydown', onKeyGlobal)
  }, [onClose])

  if (doc === undefined) {
    return <div className={embedded ? '' : 'mx-auto max-w-3xl'}>
      <Loading label="Reading the argument" />
    </div>
  }

  const visible = (doc.body || '').replace(/^---\n[\s\S]*?\n---\n/, '')
  // Local, single-author markdown rendered for reading. Not sanitised: the only
  // person who can write here is the person reading it.
  const html = marked.parse(visible, { breaks: false })
  const words = visible.trim() ? visible.trim().split(/\s+/).length : 0

  return (
    <div className={embedded ? '' : 'mx-auto max-w-3xl px-6 py-6'}>
      {!embedded && (
        <button onClick={onClose}
          className="mb-5 text-meta text-faint transition hover:text-accent">← goals</button>
      )}

      {problem && (
        <div className="mb-6 rounded-card border p-3 border-border">
          <p className="fleet-label">Thesis</p>
          <p className="mt-1 text-body text-dim">
            {problem.waypoint || 'no waypoint yet'}
          </p>
          {problem.reasoning && (
            <p className="mt-2 text-meta text-faint">{problem.reasoning}</p>
          )}
        </div>
      )}

      {/* The mismatch banner compared this essay's verdict against the chart's
          sounding. With soundings undrawn there is no second number to disagree
          with, so it went. `## Verdict` still parses and still exports. */}

      <div className="mb-4 flex items-center gap-3 border-b pb-2 border-border">
        <button onClick={() => { if (editing && dirty.current) save(body); setEditing(v => !v) }}
          className="text-meta text-accent hover:underline">
          {editing ? 'read' : 'write'}
        </button>
        {editing && (
          <span className="text-micro text-faint">
            <kbd className="font-sans">⌘B</kbd> bold · <kbd className="font-sans">⌘I</kbd> italic
          </span>
        )}
        <span className="ml-auto flex items-center gap-3 text-micro text-faint">
          <span>{words} words</span>
          {status === 'saving' && <span>saving…</span>}
          {status === 'saved' && <span className="text-ok">saved</span>}
          {status && !['saving', 'saved'].includes(status) && (
            <span className="text-danger">{status}</span>
          )}
          {doc.editor_url && (
            <a href={doc.editor_url} className="hover:text-accent">open in editor</a>
          )}
        </span>
      </div>

      {editing ? (
        <textarea
          ref={box} value={body} onChange={onType} onKeyDown={onKey} onInput={grow}
          autoFocus spellCheck
          placeholder="Make the case. What has to be true, and what would show it isn't?"
          className="md-editor"
        />
      ) : (
        <article className="md-prose" dangerouslySetInnerHTML={{ __html: html }} />
      )}
    </div>
  )
}
