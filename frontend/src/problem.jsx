import React, { useCallback, useEffect, useState } from 'react'
import { SideHeading, Loading, ErrorState } from './ui'

/* One problem, as a page of its own.
 *
 * The chart could already show a problem in three places — a row in an outline, a
 * node in the graph, the rail on the goals page — and none of them was somewhere
 * the problem could *accumulate*. The rail is a control panel that changes as soon
 * as you click elsewhere; the argument is one document about the waypoint, not a
 * home for everything else. So a problem gets an address.
 *
 * Deliberately close to empty. This is the shell for what lands here next —
 * cycles, a description, notes — and the sections below are stubs saying so
 * rather than features. An empty section that names itself is a promise; an empty
 * section that pretends to be finished is a lie. Nothing here invents storage: when
 * notes arrive they will arrive as a decision about where they live, not as a
 * field that appeared because a page had room for it.
 *
 * Reads `/api/chart/{ref}` — the spine — because it already returns the node with
 * its bearings and children, which is the whole of what this page can honestly say
 * today. */

function Stub({ title, children }) {
  return (
    <section className="mt-6">
      <SideHeading>{title}</SideHeading>
      <p className="mt-1 text-meta text-faint">{children}</p>
    </section>
  )
}

/* Which cycles ran against this problem.
 *
 * "Addressed by", never "solved by" — whether the work landed is what the sounding
 * says, so three cycles beside an `assumed` stays legible as effort spent with
 * nothing yet to show for it. That distinction is the backend's, and this screen
 * must not quietly undo it by rendering a link as a tick.
 *
 * Versions are offered from real git tags rather than typed. `chart.address`
 * validates the shape of a version, not that anything ever cut it, so a free-text
 * box would happily record a phantom cycle no repo can corroborate.
 *
 * A linked version with no tag behind it is a cycle in flight, not a mistake: the
 * tag is what closes it, so there is no "done" state here for anyone to maintain. */
function Cycles({ node }) {
  const [opts, setOpts] = useState(undefined)
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => {
    fetch(`/api/problems/${encodeURIComponent(node.id)}/cycle-options`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setOpts)
      .catch(e => setErr(e.message))
  }, [node.id])
  useEffect(load, [load])

  const send = (url, method) =>
    fetch(url, { method })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail || 'rejected'); return r.json() })
      .then(() => { setErr(null); setAdding(false); load() })
      .catch(e => setErr(e.message))

  const link = version =>
    fetch(`/api/problems/${encodeURIComponent(node.id)}/cycles`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail || 'rejected'); return r.json() })
      .then(() => { setErr(null); setAdding(false); load() })
      .catch(e => setErr(e.message))

  const unlink = version =>
    send(`/api/problems/${encodeURIComponent(node.id)}/cycles/${encodeURIComponent(version)}`, 'DELETE')

  const linked = opts?.linked ?? []
  const open = new Set(opts?.open ?? [])
  const unlinked = (opts?.options ?? []).filter(o => !o.linked)

  return (
    <section className="mt-6">
      <SideHeading>Cycles</SideHeading>

      {opts === undefined && !err && (
        <p className="mt-1 text-meta text-faint">reading tags…</p>
      )}

      {linked.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {linked.map(v => (
            <span key={v}
              title={open.has(v)
                ? `v${v} is open — planned, not yet cut`
                : `v${v} ran against this`}
              className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 font-mono
                text-micro ring-1 ring-inset ${open.has(v)
                  ? 'text-accent ring-accent/40'
                  : 'text-dim ring-zinc-700'}`}>
              v{v}{open.has(v) && ' · open'}
              <button onClick={() => unlink(v)} aria-label={`unlink v${v}`}
                className="text-faint transition hover:text-danger">×</button>
            </span>
          ))}
        </div>
      )}

      {opts && linked.length === 0 && !adding && (
        <p className="mt-1 text-meta text-faint">
          No cycle has been linked to this problem yet.
        </p>
      )}

      {err && <p className="mt-2 text-meta text-danger">{err}</p>}

      {opts && !adding && (
        <button onClick={() => setAdding(true)}
          className="mt-2 text-meta text-accent hover:underline">link a cycle →</button>
      )}

      {adding && (
        <div className="mt-2 rounded-lg border p-2.5 border-border">
          {unlinked.length === 0 ? (
            <p className="text-meta text-faint">
              {opts.repos?.length
                ? `Nothing left to link — no other cycle has been cut in ${opts.repos.join(', ')}.`
                : 'No repo sits under this problem, so there are no cycles to offer.'}
            </p>
          ) : (
            <div className="flex flex-col gap-1">
              {unlinked.map(o => (
                <button key={`${o.repo}-${o.version}`} onClick={() => link(o.version)}
                  className="flex items-center gap-2 rounded px-1.5 py-1 text-left text-meta
                      transition hover:text-accent text-dim hover:bg-zinc-800/60">
                  <code className="font-mono text-micro">v{o.version}</code>
                  <span className="text-faint">{o.repo}</span>
                  {o.date && <span className="ml-auto text-micro text-faint">{o.date}</span>}
                </button>
              ))}
            </div>
          )}
          <button onClick={() => setAdding(false)}
            className="mt-2 text-micro text-faint">cancel</button>
        </div>
      )}
    </section>
  )
}

/* Free prose the user wrote. `whitespace-pre-wrap` rather than a markdown render:
   the text is stored verbatim and shown verbatim, so paragraphs and lists survive
   without this page quietly acquiring a second opinion about formatting.
   Empty is a link into the editor, not a dead sentence — the same move the empty
   waypoint makes, for the same reason. */
function Prose({ title, text, empty, onWrite }) {
  const body = (text || '').trim()
  return (
    <section className="mt-6">
      <SideHeading>{title}</SideHeading>
      {body ? (
        <p className="mt-1 whitespace-pre-wrap text-body leading-relaxed text-dim">{body}</p>
      ) : (
        <button onClick={onWrite}
          className="mt-1 text-meta transition hover:text-accent text-faint">{empty} <span className="text-accent">Write one →</span></button>
      )}
    </section>
  )
}

/* Editing a problem in place.
 *
 * This is what the goals outline gave up when a click became navigation: renaming
 * had to leave the row, because mousedown focuses it and focus selects it, so every
 * click looked like a click on an already-selected row. It lands here instead,
 * which is the better home anyway — a title, its waypoint and its falsifier are one
 * thought, and the row only ever had space to edit two of them.
 *
 * `sounding` is deliberately absent from the body rather than sent unchanged. The
 * API treats a missing field as "leave it alone", and evidence is not something a
 * rename is entitled to touch — a form that posted it back would silently rewrite
 * the one column nothing on this page displays. */
function EditForm({ node, onSaved, onCancel }) {
  const [title, setTitle] = useState(node.title)
  const [waypoint, setWaypoint] = useState(node.waypoint || '')
  const [falsifier, setFalsifier] = useState(node.falsifier || '')
  const [description, setDescription] = useState(node.description || '')
  const [notes, setNotes] = useState(node.notes || '')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  const save = () => {
    setBusy(true); setErr(null)
    fetch(`/api/problems/${encodeURIComponent(node.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, waypoint, falsifier, description, notes }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail || 'rejected'); return r.json() })
      // PATCH answers with the spine — the same shape the page loaded with — so the
      // saved state comes from the server rather than from what we hoped we sent.
      .then(onSaved)
      .catch(e => { setErr(e.message); setBusy(false) })
  }

  const field = 'w-full rounded-lg border border-zinc-700 bg-transparent px-2.5 py-1.5 text-body ' +
    ' focus:border-accent border-zinc-700'

  return (
    <div onKeyDown={e => {
      if (e.key === 'Escape') { e.stopPropagation(); onCancel() }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save()
    }}>
      <input autoFocus value={title} onChange={e => setTitle(e.target.value)}
        placeholder="Title" className={`${field} text-title font-semibold`} />

      <label className="mt-3 block fleet-label">
        Waypoint
      </label>
      <textarea value={waypoint} onChange={e => setWaypoint(e.target.value)} rows={3}
        placeholder="What would you observe if it were working?"
        className={`${field} mt-1 resize-none`} />
      {!waypoint.trim() && (
        <p className="mt-1 text-micro text-warn">
          Saving without a waypoint leaves this a draft — nothing can be attacked until it has one.
        </p>
      )}

      <label className="mt-3 block fleet-label">
        Falsified by
      </label>
      <textarea value={falsifier} onChange={e => setFalsifier(e.target.value)} rows={2}
        placeholder="The characteristic way this fails while still looking fine"
        className={`${field} mt-1 resize-none`} />

      {/* Description and notes are the only fields here that are not part of the
          method — they are prose, so they get room to breathe and no warning when
          left empty. A problem with no description is not in a bad state. */}
      <label className="mt-3 block fleet-label">
        Description
      </label>
      <textarea value={description} onChange={e => setDescription(e.target.value)} rows={4}
        placeholder="What this problem is"
        className={`${field} mt-1`} />

      <label className="mt-3 block fleet-label">
        Notes
      </label>
      <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={6}
        placeholder="Whatever you learn while working it"
        className={`${field} mt-1`} />

      {err && <p className="mt-2 text-meta text-danger">{err}</p>}

      <div className="mt-3 flex items-center gap-2">
        <button onClick={save} disabled={busy}
          className="rounded-lg bg-accent px-3 py-1.5 text-meta text-white disabled:opacity-50">
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={onCancel}
          className="fleet-btn">Cancel</button>
        <span className="ml-auto text-micro text-faint">
          ⌘⏎ save · esc cancel
        </span>
      </div>
    </div>
  )
}


/* The loop, per problem. Three marks are clicked; Build is read off git and is
   deliberately not clickable — a tick that could disagree with the repo would be
   worse than no tick. `known: false` (no repo linked) renders as a dash, not an
   empty box: "git was never asked" must not look like "not done". */
function Loop({ node, onChanged }) {
  const [busy, setBusy] = useState(null)
  const set = (k, v) => {
    setBusy(k)
    fetch(`/api/problems/${encodeURIComponent(node.id)}/phases`, {
      method: 'PATCH', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ [k]: v }),
    }).then(r => r.json()).then(() => onChanged()).finally(() => setBusy(null))
  }
  const b = node.build || { known: false, ticked: false, why: '' }
  const marks = [
    { k: 'plan', label: 'Plan', on: !!node.phase_plan, manual: true },
    { k: 'build', label: 'Build', on: b.ticked, manual: false, known: b.known, why: b.why },
    { k: 'test', label: 'Test', on: !!node.phase_test, manual: true },
    { k: 'review', label: 'Review', on: !!node.phase_review, manual: true },
  ]
  return (
    <section className="mt-6">
      <SideHeading>Loop</SideHeading>
      <div className="mt-1 flex flex-wrap gap-2">
        {marks.map(m => {
          const unknown = m.manual === false && !m.known
          return (
            <button key={m.k} type="button" disabled={!m.manual || busy === m.k}
              onClick={() => m.manual && set(m.k, !m.on)}
              title={m.manual ? 'click to toggle' : (m.why || 'derived from commits')}
              className={`flex items-center gap-2 rounded-card border px-3 py-1.5 text-meta
                transition ${m.manual ? 'hover:border-accent' : 'cursor-default'}
                ${m.on ? 'border-ok/45 bg-ok/5 text-ink'
                       : 'border-border text-faint'}`}>
              <span className={`grid size-4 shrink-0 place-items-center rounded border text-micro text-white ${m.on ? 'border-ok bg-ok' : 'border-zinc-400'}`}>
                {m.on ? '✓' : unknown ? <span className="text-faint">–</span> : ''}
              </span>
              <span className="font-semibold">{m.label}</span>
              {!m.manual && <span className="text-micro text-faint">{m.why}</span>}
            </button>
          )
        })}
      </div>
    </section>
  )
}

/* Solved is a tick, set by hand. It does not cascade from children: a parent
   problem is not the sum of its parts, which is why it carries its own waypoint. */
function Solved({ node, children: kids = [], onChanged }) {
  const done = kids.filter(k => k.solved).length
  const set = () => fetch(`/api/problems/${encodeURIComponent(node.id)}/solved`, {
    method: 'PATCH', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ solved: !node.solved }),
  }).then(() => onChanged())
  return (
    <button type="button" onClick={set}
      className={`mt-4 flex w-fit items-center gap-2 text-meta transition
        ${node.solved ? 'font-semibold text-ok' : 'text-faint hover:text-accent'}`}>
      <span className={`grid size-5 place-items-center rounded-md border text-micro text-white
        ${node.solved ? 'border-ok bg-ok' : 'border-zinc-400'}`}>{node.solved ? '✓' : ''}</span>
      {node.solved ? 'Solved' : 'Not solved'}
      {kids.length > 0 && (
        <span className="text-micro text-faint">· {done}/{kids.length} beneath</span>
      )}
    </button>
  )
}

const VERDICTS = [['', 'untested'], ['worked', 'worked'], ['failed', 'failed'], ['abandoned', 'abandoned']]

/* Approaches considered, and the one being taken. A verdict outlives the choice
   moving on — try A, it fails, switch to B, and "A — failed" stays. That row is
   the most useful thing on this page. */
function Approaches({ node, onChanged }) {
  const list = node.approaches || []
  const [adding, setAdding] = useState('')
  const post = (url, body, method = 'PATCH') =>
    fetch(url, { method, headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body) }).then(() => onChanged())
  const add = e => {
    e.preventDefault()
    if (!adding.trim()) return
    post(`/api/problems/${encodeURIComponent(node.id)}/approaches`, { name: adding.trim() }, 'POST')
      .then(() => setAdding(''))
  }
  return (
    <section className="mt-6">
      <SideHeading>Approaches</SideHeading>
      {list.length === 0 && (
        <p className="mt-1 text-meta text-faint">
          Nothing considered yet — what are the options, and which one are you taking?
        </p>
      )}
      <div className="mt-1 flex flex-col gap-1.5">
        {list.map(a => (
          <div key={a.id}
            className={`rounded-card border p-2.5 ${a.chosen
              ? 'border-accent/50 bg-accent/5' : 'border-border'}`}>
            <div className="flex items-center gap-2">
              <button type="button" title="take this approach"
                onClick={() => post(`/api/approaches/${a.id}`, { chosen: true })}
                className={`grid size-4 shrink-0 place-items-center rounded-full border
                  ${a.chosen ? 'border-accent' : 'border-zinc-400'}`}>
                {a.chosen && <span className="size-2 rounded-full bg-accent" />}
              </button>
              <span className="text-meta font-semibold">{a.name}</span>
              {a.chosen && <span className="text-micro text-accent">going with this</span>}
              <select value={a.verdict || ''}
                onChange={e => post(`/api/approaches/${a.id}`,
                  { verdict: e.target.value || null, set_verdict: true })}
                className={`ml-auto rounded border bg-transparent px-1 py-0.5 text-micro ${a.verdict === 'failed' ? 'border-danger/40 text-danger'
                    : a.verdict === 'worked' ? 'border-ok/40 text-ok'
                    : 'text-faint border-border'}`}>
                {VERDICTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <button type="button" title="remove"
                onClick={() => post(`/api/approaches/${a.id}`, {}, 'DELETE')}
                className="text-micro text-faint hover:text-danger">✕</button>
            </div>
            {a.rationale && <p className="mt-1 pl-6 text-meta text-faint">{a.rationale}</p>}
          </div>
        ))}
      </div>
      <form onSubmit={add} className="mt-1.5">
        <input value={adding} onChange={e => setAdding(e.target.value)}
          placeholder="+ another approach"
          className="w-full rounded-card border border-dashed bg-transparent px-2.5 py-1.5 text-meta
              placeholder:text-faint focus:border-accent border-zinc-700" />
      </form>
    </section>
  )
}

/* Freeze/thaw, rehomed from the deleted chart.jsx (2026-08-14). Anchoring was
   displayed in five places and settable in none — the only control lived in a file
   nothing rendered. It belongs here: this is the page that already shows the state. */
function AnchorControl({ p, onChanged }) {
  const [mode, setMode] = useState(null)        // null | 'freeze' | 'thaw'
  const [basis, setBasis] = useState('')
  const [impact, setImpact] = useState(null)
  const [err, setErr] = useState(null)

  const openThaw = () => {
    // Never offer the action before the consequences — hiding a blast radius
    // trains you to click through it.
    fetch(`/api/problems/${p.id}/impact`).then(r => r.json())
      .then(d => { setImpact(d); setMode('thaw') })
  }

  const doFreeze = () => {
    fetch(`/api/problems/${p.id}/anchor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ basis }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setMode(null); setBasis(''); onChanged() })
      .catch(e => setErr(e.message))
  }

  const doThaw = () => {
    fetch(`/api/problems/${p.id}/anchor?token=${encodeURIComponent(impact?.token || '')}`, { method: 'DELETE' })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { setMode(null); setImpact(null); onChanged() })
      .catch(e => setErr(e.message))
  }

  if (mode === 'freeze') {
    return (
      <div className="mt-2 rounded-lg border border-accent/50 p-2.5">
        <p className="text-micro text-faint">
          Why are you willing to stop questioning this?
        </p>
        <input value={basis} onChange={e => setBasis(e.target.value)} autoFocus
          placeholder="Basis"
          className="mt-1.5 w-full rounded-lg border bg-transparent px-2 py-1 text-meta
               focus:border-accent border-zinc-700" />
        {err && <p className="mt-1.5 text-micro text-danger">{err}</p>}
        <div className="mt-2 flex gap-2">
          <button onClick={doFreeze}
            className="rounded-lg bg-accent px-2.5 py-1 text-micro text-white">Freeze</button>
          <button onClick={() => setMode(null)}
            className="text-micro text-faint">Cancel</button>
        </div>
      </div>
    )
  }

  if (mode === 'thaw') {
    const orphaned = impact?.orphaned ?? []
    const survives = impact?.survives ?? []
    return (
      <div className="mt-2 rounded-lg border border-warn/50 bg-warn/5 p-2.5">
        <p className="text-meta text-warn">
          Thawing puts {impact?.affected ?? 0} problem{impact?.affected === 1 ? '' : 's'} in question.
        </p>
        {survives.length > 0 && (
          <p className="mt-1.5 text-micro text-ok">
            Survives — {survives.map(n => `${n.title} (kept by ${n.kept_by.join(', ')})`).join(' · ')}
          </p>
        )}
        {orphaned.length > 0 && (
          <p className="mt-1 text-micro text-danger">
            Falls to drift — {orphaned.map(n => n.title).join(' · ')}
          </p>
        )}
        <div className="mt-2 flex gap-2">
          <button onClick={doThaw}
            className="fleet-btn fleet-btn-sm border-warn text-warn">
            Thaw anyway
          </button>
          <button onClick={() => setMode(null)} className="text-micro text-faint">Keep frozen</button>
        </div>
      </div>
    )
  }

  return (
    <button
      onClick={() => (p.anchored ? openThaw() : setMode('freeze'))}
      className="mt-1.5 text-micro hover:text-accent text-faint"
    >
      {p.anchored ? 'thaw…' : 'freeze…'}
    </button>
  )
}


export function ProblemPage({ pid, onClose }) {
  const [data, setData] = useState(undefined)
  const [err, setErr] = useState(null)
  const [editing, setEditing] = useState(false)

  const load = useCallback(() => {
    setErr(null)
    fetch(`/api/chart/${encodeURIComponent(pid)}`)
      .then(r => {
        // 404 is not a failure to answer, it IS the answer: nothing is charted
        // under this id. Told apart from a real error so a deleted problem — or a
        // stale link someone kept — reads as "this is gone" rather than as the
        // server being broken.
        if (r.status === 404) return null
        if (!r.ok) return Promise.reject(new Error(`HTTP ${r.status}`))
        return r.json()
      })
      .then(setData)
      .catch(e => setErr(e.message))
  }, [pid])
  useEffect(load, [load])

  // Escape leaves the page — unless a form is open, where it means "cancel the
  // edit". The form stops propagation too, but guarding here as well means the
  // page never depends on React's synthetic event reaching window to stay correct.
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape' && !editing) onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, editing])

  if (err) return (
    <main className="mx-auto max-w-3xl px-6 py-6">
      <ErrorState title="Could not read this problem" detail={err} onRetry={load} />
    </main>
  )
  if (data === undefined) return (
    <main className="mx-auto max-w-3xl px-6 py-6"><Loading label="Reading the chart" /></main>
  )
  if (!data?.node) return (
    <main className="mx-auto max-w-3xl px-6 py-6">
      <ErrorState title="Nothing charted here"
        detail={`No problem answers to '${pid}'. It may have been deleted.`} />
    </main>
  )

  const { node, parents = [], children = [] } = data

  return (
    <main className="mx-auto max-w-3xl px-6 py-6">
      <button onClick={onClose}
        className="mb-4 text-meta text-faint transition hover:text-accent">← back</button>

      {editing ? (
        <EditForm node={node}
          onSaved={d => { setData(d); setEditing(false) }}
          onCancel={() => setEditing(false)} />
      ) : (
        <>
          <div className="flex items-start gap-3">
            <h1 className="text-page font-semibold tracking-tight">{node.title}</h1>
            <button onClick={() => setEditing(true)}
              className="mt-1.5 ml-auto shrink-0 text-micro transition hover:text-accent text-faint">edit</button>
          </div>

          {/* The waypoint sits directly under the title with no heading of its own: it
              is not a property of the problem, it is what the problem *means*.
              "Waypoint — ", not the ⌖ glyph the project page uses: it has no coverage
              in the default font stack and renders as tofu. Same wording as the export. */}
          {node.waypoint
            ? (
              <p className="mt-2 text-body text-dim">
                <span className="text-faint">Waypoint — </span>{node.waypoint}
              </p>
            )
            : (
              <button onClick={() => setEditing(true)}
                className="mt-2 block text-left text-body text-warn hover:underline">
                No waypoint yet — nothing here can be attacked. Write one →
              </button>
            )}

          {node.falsifier && (
            <p className="mt-1.5 text-body text-faint">
              <span className="text-faint">Falsified by — </span>{node.falsifier}
            </p>
          )}
        </>
      )}

      <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-micro text-faint">
        {node.repo && <div>attacked by <code className="text-dim">{node.repo}</code></div>}
        <div>{children.length} problem{children.length === 1 ? '' : 's'} beneath</div>
        {node.anchored && <div title={node.anchor_basis || ''}>anchored {node.anchored_at}</div>}
      </dl>

      <AnchorControl p={node} onChanged={load} />

      {/* Where it sits. Two lists, not a breadcrumb: a problem can serve more than
          one bearing, and picking one to show would be the judgement the chart
          exists to avoid making. */}
      <Solved node={node} children={children} onChanged={load} />
      <Loop node={node} onChanged={load} />
      <Approaches node={node} onChanged={load} />

      {parents.length > 0 && (
        <section className="mt-6">
          <SideHeading>Serves</SideHeading>
          {parents.map(p => (
            <a key={p.id} href={`#/problem/${encodeURIComponent(p.id)}`}
              className="mt-0.5 block text-body text-accent hover:underline">{p.title}</a>
          ))}
        </section>
      )}

      {children.length > 0 && (
        <section className="mt-6">
          <SideHeading>Attacked by</SideHeading>
          {children.map(c => (
            <a key={c.id} href={`#/problem/${encodeURIComponent(c.id)}`}
              className="mt-0.5 block text-body text-accent hover:underline">{c.title}</a>
          ))}
        </section>
      )}

      <div className="mt-8 border-t pt-2 border-border">
        <Prose title="Description" text={node.description}
          empty="Nothing written yet." onWrite={() => setEditing(true)} />
        <Prose title="Notes" text={node.notes}
          empty="Nothing yet." onWrite={() => setEditing(true)} />
        <Cycles node={node} />
        <Stub title="Argument">
          <a href={`#/argument/${encodeURIComponent(node.id)}`}
            className="text-accent hover:underline">Open the argument →</a>
        </Stub>
      </div>
    </main>
  )
}
