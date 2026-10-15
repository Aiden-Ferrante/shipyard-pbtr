import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ArgumentPage } from './argument'
import { GoalPicker, useStored } from './kit'
import { GraphPage } from './graph'
import { Boundary, Facet, Loading } from './ui'
import { ProblemDrawer } from './outline'

/* One goal, opened over the chart. The essay is the body — this is only the
   frame — so opening a goal never navigates away from the tree you were
   reading, and closing it puts you back on the same row. */
function GoalWindow({ row, onClose }) {
  // Scaffold on open rather than behind a "create" button: a window you opened to
  // write in should not first ask permission to exist. POST is create-only and
  // returns the existing essay untouched, so re-opening is a no-op.
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let live = true
    setReady(false)
    fetch(`/api/problems/${row.id}/argument`, { method: 'POST' })
      .finally(() => { if (live) setReady(true) })
    return () => { live = false }
  }, [row.id])

  return (
    <div className="fleet-dialog-scrim" onClick={onClose}>
        <div className="fleet-dialog p-0 w-[min(48rem,100%)]" role="dialog" aria-modal="true" aria-label={row.title}
          onClick={e => e.stopPropagation()}>
          <div className="flex items-start gap-3 border-b px-6 py-4 border-border">
            <div className="min-w-0">
              <p className="fleet-label">Goal</p>
              <h2 className="text-title font-semibold tracking-tight">{row.title}</h2>
            </div>
            <button onClick={onClose} aria-label="close"
              className="fleet-btn fleet-btn-sm ml-auto shrink-0">
              Esc
            </button>
          </div>
          <div className="px-6 py-5">
            {ready
              ? <ArgumentPage pid={row.id} onClose={onClose} embedded />
              : <p className="fleet-loading">opening…</p>}
          </div>
        </div>
    </div>
  )
}

/* The goals page — the authoring surface for the whole chart. Outline on the
   left because a goal tree cannot be built through dialogs; rail on the right
   because the reasoning needs somewhere to live. */

/* Row geometry lives in `./outline`, shared with the project page's chart so the
   same data reads as the same diagram at both scopes. Behaviour stays here —
   re-parenting is deliberately goals-only. */

export /* Evidence strength reads at a glance: what is settled, what is arguable, what is
   somebody's press release. */
/* At a glance means a glance. The essay holds the full sentence; the rail holds
   enough to recognise which claim this is, with the rest on hover. */
function gist(text, limit = 88) {
  // Cut at the first clause only when that clause is a claim in its own right.
  // "Spending-composition advice" is a topic; the sentence it opens is the claim.
  const head = String(text).split(/[:—]|\.\s/)[0].trim()
  const t = head.length >= 45 ? head : String(text).trim()
  if (t.length <= limit) return t
  let cut = t.slice(0, t.lastIndexOf(' ', limit) || limit).trim()
  // Cutting on a word boundary still lands on "…too thin and" or "…for another; the",
  // which reads as a truncation bug rather than a deliberate summary. Walk back off
  // any word that cannot end a phrase.
  while (DANGLING.test(cut)) cut = cut.replace(DANGLING, '')
  return cut.replace(/[,;:—–.-]+$/, '') + '…'
}

const DANGLING = /[\s,;:]+(?:and|or|but|nor|the|an?|of|to|in|on|at|by|for|with|from|than|that|which|whose|is|are|was|were|as|its|their|this|these|not|only)$/i

/* One quiet tint per top-level domain, so scrolling a long outline tells you where
   you are without reading. Deliberately washed out: today 73% of the chart is
   one domain, and a saturated rail would be a wall of one colour claiming to be
   information. (These were washed out to leave the loud channel to soundings;
   soundings are no longer drawn, but a domain rail is still wayfinding, not
   signal, so the restraint stays.) */
const DOMAIN_TINT = [
  'bg-accent/50', 'bg-ok/50', 'bg-warn/50', 'bg-danger/40', 'bg-zinc-400/50',
]

/* Each row's top-level domain, by walking the outline — the API sends a flat list
   with depths, so ancestry is position, not a field. */
function domainsOf(outline) {
  const map = {}
  const order = []
  let current = null
  for (const n of outline || []) {
    if (n.depth === 1) {
      current = n.title
      if (!order.includes(current)) order.push(current)
    } else if (n.depth === 0) {
      current = null
    }
    map[n.id] = current
  }
  return { map, order }
}

const TAG_STYLE = {
  robust: 'text-ok ring-ok/30',
  mixed: 'text-accent ring-accent/30',
  'weak/contested': 'text-warn ring-warn/30',
  weak: 'text-warn ring-warn/30',
}

function ArgumentPanel({ row, onWaypoint }) {
  const [doc, setDoc] = useState(undefined)
  const [wp, setWp] = useState('')
  useEffect(() => { setWp(row?.waypoint ?? '') }, [row.id])

  const load = useCallback(() => {
    fetch(`/api/problems/${row.id}/argument`).then(r => r.json()).then(setDoc)
  }, [row.id])
  useEffect(load, [load])

  const create = () =>
    fetch(`/api/problems/${row.id}/argument`, { method: 'POST' })
      .then(() => { window.location.hash = `#/argument/${row.id}` })

  return (
    <div className="mt-5 border-t pt-4 border-border">
      <p className="fleet-label">Argument</p>

      {/* The waypoint lives here rather than in a field of its own because it is
          the thesis — the same sentence the essay exists to defend. Two boxes for
          one sentence invited them to drift apart. */}
      <textarea
        value={wp} onChange={e => setWp(e.target.value)} onBlur={() => onWaypoint(wp)}
        rows={2} placeholder="The thesis — what would you observe if it were working?"
        className="mt-1.5 w-full resize-none rounded-lg border bg-transparent px-2 py-1.5
            text-body focus:border-accent border-zinc-700"
      />
      {row.draft && (
        <p className="mt-1 text-micro text-warn">
          No waypoint yet — nothing can be attacked until it has one.
        </p>
      )}

      {doc === undefined ? null : !doc.exists ? (
        <>
          <p className="mt-1.5 text-micro text-faint">
            The waypoint is the thesis. Nothing defends it yet.
          </p>
          <button onClick={create}
            className="fleet-btn fleet-btn-sm mt-2">
            write the argument
          </button>
        </>
      ) : (
        <>
          {/* The verdict-vs-sounding mismatch banner lived here. It only ever
              said "your argument concluded one sounding and the chart records
              another", which is not a sentence this UI can still show. The
              backend still computes `mismatch`; nothing reads it. */}
          <a href={`#/argument/${row.id}`}
            className="mt-2 flex items-center gap-2 rounded-lg border px-2.5 py-2
               text-micro transition hover:border-accent hover:text-accent border-border text-dim">
            <span className="truncate">{doc.name}</span>
            <span className="ml-auto">read →</span>
          </a>

          {/* At a glance: what was concluded and what it rests on, so the reasoning
              is recallable without reopening 1,500 words. */}
          {doc.thesis?.length > 0 && (
            <div className="mt-3 space-y-1">
              {doc.thesis.slice(0, 4).map((t, i) => (
                <div key={i} title={t}
                  className="flex gap-2 text-micro leading-snug text-dim">
                  <span className="shrink-0 tabular-nums text-faint">
                    {i + 1}
                  </span>
                  <span className="truncate">{gist(t)}</span>
                </div>
              ))}
              {doc.thesis.length > 4 && (
                <p className="pl-4 text-micro text-faint">
                  +{doc.thesis.length - 4} more
                </p>
              )}
            </div>
          )}

          {doc.evidence?.length > 0 && (
            <div className="mt-3 space-y-1 border-t pt-2.5 border-border">
              {doc.evidence.slice(0, 2).map((e, i) => (
                <div key={i} title={e.text}
                  className="flex items-baseline gap-2 text-micro leading-snug text-faint">
                  <span className={`shrink-0 rounded-full px-1.5 text-micro
                    ring-1 ring-inset ${TAG_STYLE[e.tag] || TAG_STYLE.mixed}`}>
                    {e.tag === 'weak/contested' ? 'weak' : e.tag}
                  </span>
                  <span className="truncate">{gist(e.text, 62)}</span>
                </div>
              ))}
              {doc.evidence.length > 2 && (
                <p className="pt-0.5 text-micro text-faint">
                  +{doc.evidence.length - 2} more in the essay
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export /* Templates: a starting shape, never a standard. Applying one stamps a subtree with
   its waypoints and then forgets where it came from — nothing here will ever tell you
   a project has drifted from its template, which is the line between a seed and the
   checklist that got deleted in v0.5.0. */
function Templates({ row, onChanged, onError }) {
  const [list, setList] = useState(null)
  const [mode, setMode] = useState(null)      // null | 'apply' | 'save'
  const [name, setName] = useState('')

  useEffect(() => { setMode(null); setName('') }, [row?.id])

  const open = () => {
    setMode('apply')
    fetch('/api/templates').then(r => r.json()).then(d => setList(d.templates || []))
  }

  const apply = slug =>
    fetch(`/api/problems/${row.id}/template`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(d => {
        setMode(null)
        onChanged()
        // A document template adds nothing visible to the chart, so say where the
        // page went or applying it looks like nothing happened.
        if (d.document?.path) {
          onError(d.document.created
            ? `wrote ${d.document.path.split('/').pop()}`
            : `${d.document.path.split('/').pop()} already exists — left alone`)
        }
      })
      .catch(e => { setMode(null); onError(e.message) })

  const saveAs = () =>
    fetch('/api/templates', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, from_problem: row.id }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setMode(null); setName('') })
      .catch(e => { setMode(null); onError(e.message) })

  return (
    <div className="mt-5 border-t pt-4 border-border">
      <p className="fleet-label">Template</p>

      {mode === 'apply' ? (
        <div className="mt-1.5">
          {list === null && <Loading inline />}
          {list?.length === 0 && (
            <span className="text-micro text-faint">
              none yet — build a shape you like, then save it from here
            </span>
          )}
          <div className="flex flex-col gap-1">
            {(list || []).map(t => (
              <button key={t.slug} onClick={() => apply(t.slug)} title={t.description}
                className="fleet-btn fleet-btn-sm text-left">
                {t.name}
                <span className="ml-1.5 text-faint">
                  {t.count > 0 && `${t.count} problems`}
                  {t.count > 0 && t.document && ' · '}
                  {t.document && 'a page to fill in'}
                </span>
              </button>
            ))}
          </div>
          <button onClick={() => setMode(null)}
            className="mt-2 text-micro text-faint">cancel</button>
        </div>
      ) : mode === 'save' ? (
        <div className="mt-1.5">
          <input
            autoFocus value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && name.trim()) saveAs()
                              if (e.key === 'Escape') setMode(null) }}
            placeholder="Template name"
            className="w-full rounded-lg border bg-transparent px-2 py-1 text-meta
                focus:border-accent border-zinc-700"
          />
          <p className="mt-1 text-micro text-faint">
            Saves everything beneath “{row.title}” as a reusable shape.
          </p>
          <div className="mt-2 flex gap-2">
            <button onClick={saveAs} disabled={!name.trim()}
              className="rounded-lg bg-accent px-2.5 py-1 text-micro text-white disabled:opacity-40">Save</button>
            <button onClick={() => setMode(null)}
              className="text-micro text-faint">cancel</button>
          </div>
        </div>
      ) : (
        <div className="mt-1.5 flex flex-wrap gap-3">
          <button onClick={open} className="text-micro text-accent hover:underline">
            apply a template…
          </button>
          {row.child_count > 0 && (
            <button onClick={() => setMode('save')}
              className="text-micro text-faint hover:text-accent">
              save this shape…
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/* Copying, as distinct from sharing. "Also serve another goal" keeps one node in
   several places; this makes a second node that will diverge. Both are legitimate and
   conflating them is how a chart quietly stops meaning anything. */
function Copy({ row, onChanged, onError }) {
  const [picking, setPicking] = useState(false)
  const [all, setAll] = useState([])

  useEffect(() => { setPicking(false) }, [row?.id])

  const open = () => {
    setPicking(true)
    fetch('/api/goals').then(r => r.json())
      .then(d => setAll(d.outline.filter(r2 => !r2.reference && r2.id !== row.id)))
  }

  const copyTo = parentId =>
    fetch(`/api/problems/${row.id}/duplicate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_id: parentId }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setPicking(false); onChanged() })
      .catch(e => { setPicking(false); onError(e.message) })

  return (
    <div className="mt-5 border-t pt-4 border-border">
      <p className="fleet-label">Copy</p>
      {picking ? (
        <div className="mt-1.5">
          <p className="mb-1.5 text-micro text-faint">
            A separate goal that starts the same and diverges. Copy under…
          </p>
          <div className="flex flex-wrap gap-1.5">
            <button onClick={() => copyTo(null)}
              className="fleet-btn fleet-btn-sm">nothing — a new top-level goal</button>
            {all.map(o => (
              <button key={o.id} onClick={() => copyTo(o.id)}
                className="fleet-btn fleet-btn-sm">{o.title}</button>
            ))}
          </div>
          <button onClick={() => setPicking(false)}
            className="mt-2 text-micro text-faint">cancel</button>
        </div>
      ) : (
        <>
          <button onClick={open} className="mt-1.5 text-micro text-accent hover:underline">
            copy this block…
          </button>
          <p className="mt-1 text-micro text-faint">
            For the same goal in two places, use <b>Serves</b> instead — that keeps one node.
          </p>
        </>
      )}
    </div>
  )
}

/* What this problem serves. Multi-parent is the whole reason the chart is a DAG —
   several domains can all serve one economic goal, and saying so
   should not mean writing the goal three times. */
function Bearings({ row, onChanged, onError }) {
  const [spine, setSpine] = useState(null)
  const [picking, setPicking] = useState(false)
  const [all, setAll] = useState([])
  const [outline, setOutline] = useState([])

  const load = useCallback(() => {
    fetch(`/api/chart/${row.id}`).then(r => r.json()).then(setSpine)
  }, [row.id])
  useEffect(() => { setPicking(false); load() }, [load])

  const open = () => {
    setPicking(true)
    fetch('/api/goals').then(r => r.json()).then(d => {
      const mine = new Set((spine?.parents || []).map(p => p.id))
      setOutline(d.outline)
      setAll(d.outline.filter(r2 => !r2.reference && r2.id !== row.id && !mine.has(r2.id)))
    })
  }

  const attach = pid =>
    fetch(`/api/problems/${row.id}/parents`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parent_id: pid }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setPicking(false); load(); onChanged() })
      .catch(e => { setPicking(false); onError(e.message) })

  const detach = pid =>
    fetch(`/api/problems/${row.id}/parents/${pid}`, { method: 'DELETE' })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { load(); onChanged() })
      .catch(e => onError(e.message))

  const parents = spine?.parents || []

  return (
    <div className="mt-5 border-t pt-4 border-border">
      <p className="fleet-label">Serves</p>

      {parents.length === 0 && !picking && (
        <p className="mt-1.5 text-micro text-faint">
          Nothing — this is a top-level goal.
        </p>
      )}

      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {parents.map(p => (
          <span key={p.id}
            className="group/b flex items-center gap-1 rounded-full px-2 py-0.5 text-micro
                ring-1 ring-inset text-dim ring-zinc-700">
            {p.title}
            <button onClick={() => detach(p.id)} aria-label={`stop serving ${p.title}`}
              className="opacity-0 transition group-hover/b:opacity-100 hover:text-danger">×</button>
          </span>
        ))}
      </div>

      {picking ? (
        <div className="mt-2">
          <GoalPicker rows={all} outline={outline} empty="nothing else to serve"
            onPick={o => attach(o.id)} onCancel={() => setPicking(false)} />
        </div>
      ) : (
        <button onClick={open}
          className="mt-2 text-micro text-accent hover:underline">
          also serve another goal…
        </button>
      )}
    </div>
  )
}

/* Attaching a repo to a problem — the moment reasoning becomes work.
 *
 * This lived on the board as a dialog behind a ghost card. The board is gone,
 * and the rail is where a problem is acted on, so it lives here: a problem with
 * no repo offers the repos not already attached to one, and a problem with a
 * repo can let it go. `PUT .../repo` treats an empty value as the unlink, which
 * is why one control does both directions.
 *
 * Only unlinked repos are offered. A repo attacking two problems would make
 * "which goal does this serve" ambiguous, and the chart answers that by holding
 * exactly one edge. The list is fetched on open rather than on mount — it is
 * one request per rail otherwise, on a panel that re-renders per selection. */
function LinkRepo({ row, onChanged, onError }) {
  const [repos, setRepos] = useState(null)
  const [open, setOpen] = useState(false)

  useEffect(() => { setOpen(false); setRepos(null) }, [row.id])
  useEffect(() => {
    if (!open) return
    fetch('/api/unlinked').then(r => r.json())
      .then(d => setRepos(d.repos || [])).catch(() => setRepos([]))
  }, [open])

  const link = repo =>
    fetch(`/api/problems/${row.id}/repo`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setOpen(false); onChanged() })
      .catch(e => onError(e.message))

  if (row.repo) {
    return (
      <div className="mt-4">
        <p className="fleet-label">Attacked by</p>
        <div className="mt-1 flex items-center gap-2">
          <code className="text-micro text-dim">{row.repo}</code>
          <button onClick={() => link(null)}
            className="ml-auto text-micro text-faint transition hover:text-danger">
            unlink
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mt-4">
      <button onClick={() => setOpen(v => !v)}
        className="fleet-btn fleet-btn-sm flex w-full items-center gap-2">
        {open ? 'never mind' : 'attack this with a repo'}
      </button>
      {open && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {repos === null && <span className="text-micro text-faint">reading…</span>}
          {repos?.length === 0 && (
            <span className="text-micro text-faint">every repo is already attached</span>
          )}
          {repos?.map(r => (
            <button key={r.id} onClick={() => link(r.id)}
              className="fleet-btn fleet-btn-sm">{r.name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

/* One problem's controls.
 *
 * `embedded` renders it inside the drawer instead of as its own column. With the
 * outline gone the drawer is the only per-node surface left, and a rail beside the
 * canvas as well would rebuild the three-column clutter that removing the outline
 * was meant to end — so this drops its card and lets the drawer supply the frame.
 *
 * `onAddChild` and the rename field arrived with the outline's removal: they were
 * row buttons, and rows are what went away. Rename is an input rather than a
 * click-to-edit title because there is no row to click any more, and decomposition
 * is the motion this page exists for, so adding a child stays one action from the
 * problem being decomposed. */
export function GoalRail({ row, onChanged, onDeleted, onError, onOpenWindow,
                           embedded = false, onAddChild = null }) {
  const [confirming, setConfirming] = useState(null)
  const [title, setTitle] = useState('')
  useEffect(() => { setConfirming(null); setTitle(row?.title ?? '') }, [row?.id, row?.title])

  /* Commit a pending rename when this goes away.
   *
   * onBlur alone loses the edit in the one case you would most expect to work:
   * typing a title and clicking the drawer's close button unmounts the input, and
   * an input that no longer exists never blurs. Same for clicking straight to
   * another node.
   *
   * The ref is written by typing, never during render: it carries the id and
   * original title of the row the keystrokes were aimed at. Assigning
   * `{ title, row }` during render meant the ref already held the *new* row by
   * the time the cleanup below ran on a selection change — so switching from an
   * edited A to B sent A's edit to B, silently renaming the wrong problem.
   *
   * Deliberately a bare fetch: onChanged() would setState on a component that is
   * already gone, and the caller reloads on close anyway. */
  const pending = useRef(null)
  useEffect(() => () => {
    const p = pending.current
    pending.current = null
    if (!p) return
    const v = (p.title || '').trim()
    if (!v || v === p.base) return
    fetch(`/api/problems/${p.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: v }),
    }).catch(() => { /* the drawer is gone; there is nowhere to show this */ })
  }, [row?.id])

  if (!row) {
    return <div className="rounded-card border p-4 text-body text-faint border-border">Select a problem.</div>
  }

  /* A tag name and a class, NOT a component.
   *
   * This was `const Wrap = ({children}) => <div>…</div>`, defined in the render
   * body — so every render produced a new component type, React unmounted the
   * whole subtree and remounted it, and the rename field lost its state and focus
   * on the first keystroke. It looked like the patch never fired; the input had
   * simply been replaced by a fresh one before blur could read it. */
  const Wrap = embedded ? 'div' : 'aside'
  const wrapClass = embedded
    ? 'mt-5 border-t pt-4 border-border'
    : 'sticky top-20 h-fit rounded-card border p-4 border-border'

  const patch = (body) =>
    fetch(`/api/problems/${row.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail); onChanged() })
      .catch(e => onError(e.message))

  const del = cascade =>
    fetch(`/api/problems/${row.id}?token=${encodeURIComponent(confirming?.token || '')}${cascade ? '&cascade=true' : ''}`, { method: 'DELETE' })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setConfirming(null); onDeleted?.() })
      .catch(e => onError(e.message))

  return (
    /* Sticky: the tree is long enough that selecting a deep row used to leave its
       own controls scrolled off the top. */
    <Wrap className={wrapClass}>
      {/* The drawer's header already names the node, so in there this is the
          editor rather than a second copy of the title. */}
      {embedded ? (
        <Facet label="Title">
          <input
            value={title}
            onChange={e => {
              setTitle(e.target.value)
              pending.current = { id: row.id, base: row.title, title: e.target.value }
            }}
            onBlur={() => {
              pending.current = null
              const t = title.trim()
              if (t && t !== row.title) patch({ title: t })
              else setTitle(row.title)
            }}
            onKeyDown={e => {
              if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() }
              if (e.key === 'Escape') {
                e.preventDefault(); pending.current = null; setTitle(row.title)
              }
            }}
            aria-label={`rename ${row.title}`}
            className="w-full rounded-lg border bg-transparent px-2 py-1 text-meta
                focus:border-accent border-zinc-700"
          />
        </Facet>
      ) : (
        <h2 className="text-body font-medium text-ink">{row.title}</h2>
      )}
      {row.draft && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <span className="text-micro text-warn">no waypoint yet</span>
        </div>
      )}

      {/* The way into this goal's own space, above the structural controls: it is
          what you reach for after clicking a row, and it should not be hunted for
          under pinning and bearings. */}
      <button
        onClick={() => onOpenWindow(row)}
        className="fleet-btn fleet-btn-accent fleet-btn-sm mt-3 flex w-full items-center gap-2 bg-accent/5 text-accent">
        <span>Open this goal</span>
        <span className="ml-auto" aria-hidden="true">⤢</span>
      </button>

      {/* Pinning is a decision about looking, held apart from decomposing: you add
          a sub-problem because the thinking demands it, not to get another column.
          So the chart grows to any depth while Fleet's groups stay a handful wide. */}
      <button
        onClick={() => fetch(`/api/problems/${row.id}/pin`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pinned: !row.pinned }),
        }).then(onChanged).catch(e => onError(e.message))}
        className={`mt-4 flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5
          text-micro transition ${row.pinned
            ? 'border-accent/40 bg-accent/5 text-accent'
            : 'text-faint hover:border-accent hover:text-accent border-border'}`}>
        {row.pinned ? '★ heads a Fleet group' : '☆ make this a Fleet grouping'}
      </button>

      {/* Taking the slot. Only offered on a problem that can actually be started —
          a blocked one is refused by the API anyway, and a button whose only
          outcome is an error message is worse than no button. The refusal still
          matters when a *sibling* holds the slot, and that message names it. */}
      <button
        disabled={row.standing === 'blocked' || row.standing === 'done'}
        title={row.standing === 'blocked'
          ? 'blocked — a subproblem beneath this is unsolved'
          : row.standing === 'done' ? 'already solved'
            : 'one problem per domain can be running at a time'}
        onClick={() => fetch(`/api/problems/${row.id}/active`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active: !row.active }),
        })
          .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
          .then(onChanged)
          .catch(e => onError(e.message))}
        className={`mt-2 flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5
          text-micro transition disabled:cursor-not-allowed disabled:opacity-50
          ${row.active
            ? 'border-accent/40 bg-accent/5 text-accent'
            : 'text-faint hover:border-accent hover:text-accent border-border'}`}>
        {row.active ? '● running now' : '○ start working on this'}
      </button>

      <dl className="mt-4 space-y-1 text-micro text-faint">
        <div>{row.child_count} problem{row.child_count === 1 ? '' : 's'} beneath</div>
        {row.anchored && <div title={row.anchor_basis}>anchored {row.anchored_at}</div>}
      </dl>

      <LinkRepo row={row} onChanged={onChanged} onError={onError} />

      {/* Templates describe how a *project* is attacked, not how a goal is reasoned
          about. A goal's shape comes from thinking; only work has recurring shapes. */}
      {row.repo && <Templates row={row} onChanged={onChanged} onError={onError} />}

      <Copy row={row} onChanged={onChanged} onError={onError} />

      <Bearings row={row} onChanged={onChanged} onError={onError} />

      {/* Linking a repo used to live on the board. The rail is where a problem is
          acted on, and attaching one is the moment reasoning becomes work — so
          it came here when the board went. */}
      <ArgumentPanel row={row} onWaypoint={v => patch({ waypoint: v })} />

      {confirming ? (
        <div className="mt-4 rounded-lg border border-danger/50 bg-danger/5 p-3">
          <p className="text-meta text-danger">Delete “{confirming.title}”?</p>
          {confirming.children.length > 0 ? (
            <p className="mt-1.5 text-micro text-danger">
              {confirming.children.length} problem{confirming.children.length === 1 ? '' : 's'} beneath
              {confirming.becomes_root
                ? ' become goals in their own right'
                : ` move up to ${confirming.new_parents.join(', ')}`} — nothing is destroyed.
            </p>
          ) : (
            <p className="mt-1.5 text-micro text-danger">Nothing sits beneath it.</p>
          )}
          {confirming.repo && (
            <p className="mt-1 text-micro text-danger">
              {confirming.repo} stays on disk and becomes uncharted.
            </p>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <button
              onClick={() => del(false)}
              className="fleet-btn fleet-btn-sm text-danger">
              {confirming.children.length > 0 ? 'Delete only this' : 'Delete'}
            </button>
            {confirming.cascade_count > 1 && (
              <button onClick={() => del(true)}
                className="fleet-btn fleet-btn-sm bg-danger/10 text-danger">
                Delete the branch ({confirming.cascade_count})
              </button>
            )}
            <button onClick={() => setConfirming(null)}
              className="text-micro text-faint">Keep</button>
          </div>
          {confirming.cascade_spared?.length > 0 && (
            <p className="mt-1.5 text-micro text-faint">
              Spared either way — {confirming.cascade_spared.join(', ')} (served elsewhere too)
            </p>
          )}
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-4">
          {/* Decomposition is the motion this page exists for, so it stays one
              action from the problem being decomposed — it was a row button, and
              the rows are what went away. */}
          {onAddChild && (
            <button onClick={() => onAddChild(row)}
              className="text-micro text-accent hover:underline">
              add a problem beneath
            </button>
          )}
          <button
            onClick={() => fetch(`/api/problems/${row.id}/deletion`)
              .then(r => r.json()).then(setConfirming)}
            className="ml-auto text-micro text-faint transition hover:text-danger">
            delete…
          </button>
        </div>
      )}
    </Wrap>
  )
}

/* What the chart looks like, without traversing it. Five pinned domains implies five
   comparable branches; the counts are how you find out that is not true. */
function Shape({ outline, only, onOnly }) {
  const [open, setOpen] = useStored('shipyard.goals.shape', [])
  const real = (outline || []).filter(n => !n.reference)
  const { map, order } = domainsOf(outline)

  const per = order.map(d => {
    const rows = real.filter(n => map[n.id] === d)
    return { name: d, rows: rows.length, leaves: rows.filter(n => !n.child_count).length }
  })
  const widest = Math.max(1, ...per.map(p => p.rows))
  const counts = {
    blind: real.filter(n => n.draft && n.child_count > 0).length,
    draft: real.filter(n => n.draft).length,
    leaf: real.filter(n => !n.child_count).length,
    argued: real.filter(n => n.has_argument).length,
  }
  const shown = open.has('shape')

  return (
    <div className="mb-3 rounded-card border px-3 py-2 border-border">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => setOpen(shown ? new Set() : new Set(['shape']))}
          className="fleet-label hover:text-accent">
          Shape
        </button>
        {[['blind', 'nothing to observe'], ['draft', 'no waypoint'],
          ['leaf', 'leaves'], ['argued', 'argued']].map(([k, label]) => (
          <button key={k} onClick={() => onOnly(only === k ? null : k)}
            className={`rounded-full px-2 py-0.5 text-micro ring-1 ring-inset transition ${
              only === k ? 'bg-accent/10 text-accent ring-accent/30'
                         : 'text-faint hover:text-accent ring-zinc-700'}`}>
            {counts[k]} {label}
          </button>
        ))}
        {only && (
          <button onClick={() => onOnly(null)}
            className="text-micro text-accent hover:underline">show the tree</button>
        )}
      </div>

      {shown && (
        <div className="mt-2 space-y-1 border-t pt-2 border-border">
          {per.map((p, i) => (
            <div key={p.name} className="flex items-center gap-3 text-micro">
              <span className="w-24 shrink-0 truncate text-faint">{p.name}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                <div className={`h-full rounded-full ${DOMAIN_TINT[i % DOMAIN_TINT.length]}`}
                  style={{ width: `${Math.max(2, (p.rows / widest) * 100)}%` }} />
              </div>
              <span className="w-24 shrink-0 text-right tabular-nums text-faint">
                {p.rows} · {p.leaves} leaves
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const COLLAPSE_KEY = 'shipyard.goals.collapsed'
// Below this the whole outline fits on a screen and collapsing it would only hide
// things. Above it, scrolling past the leaves is the cost of every navigation.
const COLLAPSE_ABOVE = 20

// Reads out beside the count on the canvas: "13 nodes without a waypoint" rather
// than "13 nodes match", because a chip is a question with a name.
const FACET_LABEL = {
  blind: 'broken down with nothing to observe',
  draft: 'without a waypoint',
  leaf: 'with nothing beneath',
  argued: 'with an argument',
}

/* When several problems hold exactly the same bearings, the thing they have in
   common has no name — so it cannot carry a waypoint, be argued for, or be moved
   as a unit. Naming it is the fix, and the chart can spot where it is wanted. */
function Groupings({ onApplied, onError }) {
  const [groups, setGroups] = useState([])
  const [open, setOpen] = useState(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    fetch('/api/chart-groupings').then(r => r.json())
      .then(d => setGroups(d.groupings || [])).catch(() => setGroups([]))
  }, [])
  useEffect(load, [load])

  const apply = (g) => {
    setBusy(true)
    fetch('/api/chart-groupings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        bearing_ids: g.bearings.map(b => b.id),
        child_ids: g.children.map(c => c.id),
      }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(out => { setOpen(null); setTitle(''); load(); onApplied?.(out.id) })
      .catch(e => onError?.(e.message))
      .finally(() => setBusy(false))
  }

  if (!groups.length) return null

  return (
    <div className="mb-3 space-y-2">
      {groups.map((g, i) => (
        <div key={i} className="rounded-card border border-warn/40 bg-warn/5 px-3 py-2">
          <p className="text-meta text-warn">
            <b>{g.children.length} problems</b> serve exactly{' '}
            {g.bearings.map((b, j) => (
              <span key={b.id}>
                {j > 0 && ' and '}<b>{b.title}</b>
              </span>
            ))}
            {' '}— {g.edges_now} connections saying one thing.
          </p>

          {open === i ? (
            <div className="mt-2">
              <p className="text-micro text-faint">
                Name what they have in common. It becomes one problem serving those
                bearings, with these {g.children.length} beneath it —{' '}
                {g.edges_now} connections become {g.edges_after}.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {g.children.map(c => (
                  <span key={c.id} className="rounded-full px-2 py-0.5 text-micro text-faint ring-1 ring-inset ring-zinc-700">{c.title}</span>
                ))}
              </div>
              <div className="mt-2 flex gap-2">
                <input
                  value={title} onChange={e => setTitle(e.target.value)} autoFocus
                  placeholder="What are these, together?"
                  className="min-w-0 flex-1 rounded-lg border bg-transparent px-2 py-1 text-meta
                      focus:border-accent border-zinc-700"
                />
                <button onClick={() => apply(g)} disabled={busy || !title.trim()}
                  className="fleet-btn fleet-btn-sm text-accent disabled:opacity-40">
                  {busy ? 'grouping…' : 'group them'}
                </button>
                <button onClick={() => { setOpen(null); setTitle('') }}
                  className="text-micro text-faint">cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={() => { setOpen(i); setTitle('') }}
              className="mt-1 text-micro text-accent hover:underline">
              name what they have in common…
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

/* The drawer's selection lives in the URL, not in component state: reload keeps it
   open on the same node and Back closes it. Deliberately a query on #/goals rather
   than its own route — #/problem/<id> stays the full page, so a node is still
   linkable and bookmarkable. */
const nodeFromHash = () => {
  const q = window.location.hash.split('?')[1]
  const v = q && new URLSearchParams(q).get('node')
  return v ? decodeURIComponent(v) : null
}
const setNodeInHash = id => {
  const next = id ? `#/goals?node=${encodeURIComponent(id)}` : '#/goals'
  if (window.location.hash !== next) window.location.hash = next
}

/* The focus strip — what is actually being worked on, one slot per domain.
 *
 * The chart lists everything that matters and by itself says nothing about what is
 * running now. This is the borrowed half of a focus tree: slots are **scarce**, and
 * an empty one is drawn as loudly as a full one, because "this domain has nothing
 * going" is the reading worth having. A count of filled slots would hide exactly
 * that, so the slots are drawn individually and never summarised.
 *
 * Domains are the pinned goals — the same pins the board sections by. No second
 * notion of "domain" gets invented here. */
function FocusStrip({ nonce, onChanged, onError }) {
  const [slots, setSlots] = useState(null)

  useEffect(() => {
    fetch('/api/focus')
      .then(r => { if (!r.ok) throw new Error('focus slots did not load'); return r.json() })
      .then(d => setSlots(d.slots))
      .catch(e => onError(e.message))
  }, [nonce, onError])

  const release = pid =>
    fetch(`/api/problems/${pid}/active`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: false }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(onChanged)
      .catch(e => onError(e.message))

  if (!slots?.length) return null

  return (
    <div className="mb-4 flex flex-wrap items-stretch gap-2">
      {slots.map(s => (
        <div key={s.domain_id}
          className={`min-w-44 rounded-card border px-3 py-2 ${s.problem
            ? 'border-accent/40 bg-accent/5'
            : 'border-dashed border-zinc-700'}`}>
          <p className="fleet-label">{s.domain}</p>
          {s.problem ? (
            <div className="mt-0.5 flex items-baseline gap-2">
              <a href={`#/problem/${encodeURIComponent(s.problem.id)}`}
                className="min-w-0 truncate text-meta text-accent hover:underline">
                {s.problem.title}
              </a>
              <button onClick={() => release(s.problem.id)}
                title="release this slot" aria-label={`release ${s.problem.title}`}
                className="ml-auto shrink-0 text-micro text-faint hover:text-danger">
                release
              </button>
            </div>
          ) : (
            <p className="mt-0.5 text-meta italic text-faint">
              nothing running
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

export function GoalsPage({ onClose }) {
  const [data, setData] = useState(undefined)
  const [sel, setSel] = useState(null)
  const [inspect, setInspect] = useState(nodeFromHash)   // the node shown in the drawer
  // The URL is the source of truth for the drawer, so Back/Forward close and
  // reopen it the way every other route in the app behaves.
  useEffect(() => {
    const sync = () => setInspect(nodeFromHash())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  const [windowed, setWindowed] = useState(null)   // the goal opened over the chart
  const [only, setOnly] = useState(null)   // null | 'blind' | 'draft' | 'leaf' | 'argued'
  // Outline and graph are two renderings of one chart, not two pages. They
  // already shared a collapse key before they shared a tab.
  const [collapsed, setCollapsed] = useStored(COLLAPSE_KEY, [])
  // Whether this browser has ever had an opinion. Read before useStored's effect
  // writes the key, so a first visit is distinguishable from "deliberately empty".
  const [seeded, setSeeded] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) !== null } catch { return false }
  })
  // The same question, captured separately and never reassigned. `seeded` flips as
  // soon as the OUTLINE applies its default, so by the time the graph mounts it can
  // no longer tell "the user folded this" from "we folded it a moment ago" — which
  // is why the graph's own seeding never ran. This stays true to the user.
  const [userChose] = useState(() => {
    try { return localStorage.getItem(COLLAPSE_KEY) !== null } catch { return false }
  })
  const [err, setErr] = useState(null)

  const load = useCallback((keep) => {
    return fetch('/api/goals').then(r => r.json()).then(d => {
      setData(d)
      if (keep) setSel(keep)
      else if (!sel && d.outline.length) setSel(d.outline[0].id)
      return d
    })
  }, [sel])
  useEffect(() => { load() }, [])

  // A big outline opens as an overview, not as a wall: everything with children
  // below the top level starts closed, so you see the shape and expand into one
  // branch. Only on a first visit — after that this browser's own choices win.
  const branches = (data?.outline ?? [])
    .filter(n => n.depth >= 1 && n.child_count > 0 && !n.reference)
    .map(n => n.id)
  useEffect(() => {
    if (seeded || !data?.outline) return
    if (data.outline.length > COLLAPSE_ABOVE) setCollapsed(new Set(branches))
    setSeeded(true)
  }, [data, seeded])

  /* Search moved to the canvas. The graph derives its own hit set and unfolds
     the path to each — transiently, without writing the collapse key — so the
     outline's version of this had no consumer left once the outline went. */

  const domain = domainsOf(data?.outline)
  const domainIndex = {}
  for (const [id, name] of Object.entries(domain.map)) {
    domainIndex[id] = domain.order.indexOf(name)
  }

  /* A facet is a saved query, not a mode.
   *
   * It used to flatten the outline into a list of matches — "when you are asking
   * which of these are X, the tree is the thing in the way" — which was true of a
   * list and is not true of a canvas. On the graph the tree is the answer: where
   * the waypointless nodes SIT is the thing you cannot get from a count. So a
   * chip now hands the graph a set and gets the search treatment: ringed, the
   * rest receded, the path to each unfolded. */
  const MATCH = {
    blind: r => r.draft && r.child_count > 0,
    draft: r => r.draft,
    leaf: r => r.child_count === 0,
    argued: r => r.has_argument,
  }
  const facet = only
    ? new Set((data?.outline ?? []).filter(r => !r.reference && MATCH[only](r)).map(r => r.id))
    : null

  // Where the stopping rule was skipped: children exist, an observable does not.
  const blind = (data?.outline ?? [])
    .filter(r => !r.reference && r.draft && r.child_count > 0).length

  const selected = data?.outline.find(r => r.id === sel && !r.reference)

  const api = (url, opts) =>
    fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .catch(e => { setErr(e.message); throw e })

  // Unfold the parent first, or the node you just made is created inside a fold and
  // never appears. Then select it: with the outline gone there is no row to drop an
  // inline editor into, so the new problem opens in the drawer where its title field
  // is — which is also where you were already looking when you asked for it.
  const addChild = (row) => {
    setCollapsed(c => { const n = new Set(c); n.delete(row.id); return n })
    api('/api/problems', {
      method: 'POST',
      body: JSON.stringify({ title: 'Untitled', waypoint: '', draft: true,
                             parent_id: row.id }),
    }).then(d => load(d.id).then(() => setNodeInHash(d.id)))
  }


  if (!data) return <Loading label="Reading goals" />

  /* The chart is the one surface that earns the whole window: it is a tree that gets
     deeper every time a problem is descended, and at max-w-6xl the deep rows wrapped
     while two thirds of a wide monitor sat empty. Every other page stays centred. */
  return (
    <div className="px-6 py-6">
      <button onClick={onClose}
        className="mb-4 text-meta text-faint transition hover:text-accent">← fleet</button>

      <div className="mb-4 flex flex-wrap items-baseline gap-3">
        <h1 className="text-page font-semibold tracking-tight">Long Term Goal Chart</h1>
        <span className="text-meta text-faint">{data.total} problems</span>
        {blind > 0 && (
          <span className="text-meta text-warn"
            title="decomposed before there was anything to observe — the stopping rule skipped">
            {blind} broken down with nothing to observe
          </span>
        )}
        {data.drafts > 0 && (
          <span className="text-meta text-faint">{data.drafts} without a waypoint</span>
        )}
        {/* The search box moved onto the canvas, beside Fit — the last piece of the
            outline's header still living up here. Two reasons, and the second is the
            one that forced it: the project's chart is the same component and had no
            search at all, and once the canvas could fill the window this box went
            behind it, so fullscreen was the one state where nothing could be found.
            The collapse-all toggle went the same way earlier. */}
      </div>

      {err && (
        <p className="mb-3 rounded-card border border-danger/40 bg-danger/5 px-3 py-2 text-meta text-danger">
          {err} <button onClick={() => setErr(null)} className="ml-2 underline">dismiss</button>
        </p>
      )}
      {/* The undo banner went with drag-to-reparent. It only ever undid a move,
          and a move is now an explicit add-then-remove in Bearings — two deliberate
          clicks, neither of which can happen by dropping a row on the wrong line. */}

      {/* Above the chart, because "what am I on" is read before "what exists". */}
      <FocusStrip nonce={data} onChanged={() => load()} onError={setErr} />

      <Shape outline={data.outline} only={only} onOnly={setOnly} />

      <Groupings onApplied={id => load(id)} onError={setErr} />

      <Boundary label="The graph">
        {/* `firstVisit` has to come from here. The graph cannot work it out for
            itself: useStored has already written the shared key by the time this
            mounts, so every visit would look like a return visit. */}
        {/* Fold state is handed down, not mirrored: `useStored` is a useState per
            component, so two copies of one key drift the moment either writes. */}
        {/* `onCreated` is the graph telling this page its outline is stale. The
            canvas has already refetched itself and written the hash; what it cannot
            do is refresh the payload the drawer, the Shape strip and the counts all
            read from. Without it a node made on the canvas opened an empty drawer
            and the header still said one fewer problem. */}
        <GraphPage embedded selected={inspect} onPick={setNodeInHash}
          firstVisit={!userChose}
          collapsed={collapsed} onCollapsed={setCollapsed}
          highlight={facet} highlightLabel={FACET_LABEL[only] || ''}
          nonce={data} onCreated={id => load(id)} />
      </Boundary>

      {/* Outside the outline/graph branch, because the drawer belongs to the chart
          and not to one drawing of it: the graph had no way to show a node without
          leaving the page, which is the same friction the outline fixed. It is
          `fixed`-positioned, so sitting outside the outline's grid costs it
          nothing. */}
      {inspect && (() => {
        // The whole outline payload, not anything the canvas is currently drawing:
        // a node folded away, dimmed by a facet or missed by the search box is still
        // the node you have open, and reading it from a filtered set would close the
        // drawer under you as you typed.
        const n = (data?.outline ?? []).find(r => r.id === inspect)
        if (!n) return null
        // The row is already loaded, so this passes it rather than an id: the
        // drawer only fetches for callers that have nothing but an id, and the
        // app's primary surface keeps opening without a loading flash.
        return (
          <ProblemDrawer node={n} onClose={() => setNodeInHash(null)}>
            <GoalRail embedded row={n} onAddChild={addChild}
              onChanged={() => load(n.id)}
              onDeleted={() => { setNodeInHash(null); load() }}
              onError={setErr} onOpenWindow={setWindowed} />
          </ProblemDrawer>
        )
      })()}

      {/* Reloads on close: the essay's first line can become the waypoint, and the
          outline behind should not still be showing the old one. */}
      {windowed && (
        <GoalWindow row={windowed}
          onClose={() => { setWindowed(null); load(sel) }} />
      )}
    </div>
  )
}

/* The rail says whether an argument exists and whether it agrees with the chart.
   Reading and writing it happens on its own page — an essay in a 300px column is
   not an essay anyone will write. */
