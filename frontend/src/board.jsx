import React, { useEffect, useState, useCallback } from 'react'
import { GoalPicker, CycleChip, activityTone, relTime, useStored } from './kit'
import { Skeleton, StatusDot } from './ui'

/* The board — the chart viewed at one altitude. Root problems are sections;
   projects and ghosts are what sits beneath them. */

export function Card({ p, onOpen, innerRef, dragId, onDragStart, onDragEnd }) {
  return (
    <button
      ref={innerRef}
      onClick={() => onOpen(p.id)}
      draggable={!!dragId}
      onDragStart={e => {
        if (!dragId) return
        e.dataTransfer.setData('text/plain', dragId)
        e.dataTransfer.effectAllowed = 'move'
        onDragStart?.(dragId)
      }}
      onDragEnd={() => onDragEnd?.()}
      className={`group flex w-full flex-col rounded-card border p-4 text-left
           transition duration-150 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-lg hover:shadow-accent/5 focus-visible:outline-none focus-visible:ring-2
           focus-visible:ring-accent/60 border-border bg-zinc-900/70 hover:border-accent/60 hover:bg-zinc-900 ${dragId ? 'cursor-grab active:cursor-grabbing' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-title font-semibold tracking-tight text-ink">
              {p.name || p.id}
            </h3>
            <StatusDot mcInfo={p.mc_info} />
          </div>
          <p className="mt-1 flex items-center gap-2 text-meta">
            <CycleChip cycles={p.cycles} />
            <span className={activityTone(p.last_activity)}>{relTime(p.last_activity)}</span>
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {/* The card has been draggable all along; nothing said so, which is why
              re-homing a project read as missing rather than as undiscovered. The
              grip is the affordance, not the mechanism — the whole card still
              drags, so this only has to be seen, never hit. */}
          {dragId && (
            <span aria-hidden="true" title="drag onto another group"
              className="text-micro leading-none opacity-0 transition group-hover:opacity-100 text-dim">⠿</span>
          )}
          {/* Charted is now a binary: either this project answers to a problem
              or it does not. How well-evidenced that problem is no longer shows
              on the card. */}
          {!p.sounding && (
            <span className="rounded-full px-2 py-0.5 text-micro ring-1 ring-inset text-faint ring-zinc-800">
              uncharted
            </span>
          )}
          {p.open_tasks > 0 && (
            <span className="text-micro text-faint">
              {p.open_tasks} open
            </span>
          )}
        </div>
      </div>

      {p.description && (
        <p className="mt-3 line-clamp-2 text-body text-faint">
          {p.description}
        </p>
      )}

      {(p.also_serves?.length > 0 || p.child_count > 0) && (
        <div className="mt-2 flex flex-wrap gap-x-3 text-micro text-faint">
          {p.child_count > 0 && (
            <span title="subproblems solved">
              {p.solved_below > 0 ? `${p.solved_below}/${p.child_count} solved` : `${p.child_count} below`}
            </span>
          )}
          {p.also_serves?.length > 0 && (
            <span title={p.also_serves.join(', ')}>
              also serves {p.also_serves.length} other bearing{p.also_serves.length > 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      {p.tags?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {p.tags.slice(0, 4).map(t => (
            <span key={t} className="rounded-md px-1.5 py-0.5 text-micro bg-surface-2 text-faint">{t}</span>
          ))}
        </div>
      )}
    </button>
  )
}

/* A card is a `<button>`, and a button inside a button is invalid HTML that React
   will happily render and browsers then disagree about — so the shelve control sits
   BESIDE the card rather than in it, pinned to the corner and out of the content
   flow so it never collides with a chip or a tag. */
function Slot({ children, onShelve, name }) {
  return (
    <div className="group/slot relative">
      {children}
      {onShelve && (
        <button
          onClick={onShelve}
          aria-label={`shelve ${name}`}
          title={`Shelve ${name} — off the board, no files touched. Restorable from “shelved”.`}
          className="fleet-btn fleet-btn-danger fleet-btn-sm absolute -right-1.5 -top-1.5 grid size-5 place-items-center leading-none opacity-0 group-hover/slot:opacity-100"
        >×</button>
      )}
    </div>
  )
}

export function GhostCard({ c, onPromote }) {
  return (
    <div className="flex w-full flex-col rounded-card border border-dashed bg-transparent p-4
        border-zinc-700">
      <h3 className="truncate text-title text-dim">{c.title}</h3>
      {c.waypoint ? (
        <p className="mt-1 text-meta text-faint">
          <span className="text-faint">Waypoint — </span>{c.waypoint}
        </p>
      ) : (
        <p className="mt-1 text-meta italic text-faint">no waypoint yet</p>
      )}
      <button onClick={() => onPromote(c)}
        className="fleet-btn fleet-btn-sm mt-3 self-start">
        link a repo
      </button>
    </div>
  )
}

/* The board IS the chart: sections are root problems, cards are what sits beneath
   them. Organised by purpose; maturity is a field, not the grouping.

   Two things it used to own now live where they belong, and are deliberately not
   duplicated back: importing an unmanaged repo is on Fleet, because that is about
   repos; attaching a repo to a problem is in the Chart rail, because that is
   where a problem is acted on — and the rail can unlink, which the dialog here
   never could. A ghost card still says "link a repo" and hands off to Chart. */

const UNCHARTED = '__uncharted__'
const UNGROUPED = '__ungrouped__'

export function Board({ onOpen, onChanged }) {
  const [data, setData] = useState(undefined)
  const [over, setOver] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(null)      // the chart outline, once fetched
  const [showShelf, setShowShelf] = useState(false)
  const [hidden, setHidden] = useStored('shipyard.board.hidden', [])
  const [collapsed, setCollapsed] = useStored('shipyard.board.collapsed', [])

  // A load with no .catch cannot report failure, and every write below reloads to
  // confirm itself — so a dropped request would have left the board showing the
  // state you tried to change, silently. It says so now.
  const load = useCallback(() => {
    fetch('/api/board')
      .then(r => { if (!r.ok) throw new Error(`the board did not load (${r.status})`); return r.json() })
      .then(setData)
      .catch(e => setErr(e.message))
  }, [])
  useEffect(load, [load])

  // Every write is confirmed by re-reading the board rather than assumed. These
  // reshape which section a card lives under, and guessing that wrong is worse
  // than a round trip on loopback.
  const write = (url, body) =>
    fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { load(); onChanged?.() })
      .catch(e => setErr(e.message))

  const reparent = (problemId, sectionId) => {
    setOver(null)
    setDragging(false)
    write(`/api/problems/${problemId}/parent`, { parent_id: sectionId })
  }

  /* Removing a group is unpinning it. That changes no edges: the projects keep
     their bearings and simply stop having a heading of their own, which is why
     the word "delete" does not appear here and why there is no confirm — one
     click puts it back. */
  const setPinned = (pid, on) => {
    setAdding(null)
    write(`/api/problems/${pid}/pin`, { pinned: on })
  }

  /* Off the board, nothing on disk touched. Keyed by repo id rather than by problem
     so it survives the chart node being deleted or re-linked. */
  const shelve = repo =>
    fetch('/api/shelved', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(() => { load(); onChanged?.() })
      .catch(e => setErr(e.message))

  const restore = repo =>
    fetch(`/api/shelved/${repo}`, { method: 'DELETE' })
      .then(async r => { if (!r.ok) throw new Error('could not restore'); return r.json() })
      .then(() => { load(); onChanged?.() })
      .catch(e => setErr(e.message))

  const openPicker = () =>
    fetch('/api/goals')
      .then(r => { if (!r.ok) throw new Error('could not read the chart'); return r.json() })
      .then(d => setAdding(d.outline))
      .catch(e => setErr(e.message))

  if (!data) return err
    ? <p className="rounded-card border border-danger/40 bg-danger/5 px-3 py-2 text-body text-danger">
        {err} <button onClick={load} className="ml-2 underline">retry</button>
      </p>
    : <Skeleton />

  const toggle = (setter, id) => setter(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  })

  const ungrouped = data.ungrouped || []
  const shelvedRepos = data.shelved || []
  const all = [
    ...data.sections.map(s2 => ({ id: s2.id, title: s2.title, count: s2.cards.length })),
    ...(ungrouped.length
      ? [{ id: UNGROUPED, title: 'Ungrouped', count: ungrouped.length }] : []),
    ...(data.uncharted.length
      ? [{ id: UNCHARTED, title: 'Uncharted', count: data.uncharted.length }] : []),
  ]
  const shown = all.filter(s2 => !hidden.has(s2.id))
  const filtered = shown.length !== all.length

  /* Sections are pinned goals, falling back to the chart's roots when nothing is
     pinned. The fallback is the whole reason adding a group needs a warning: from
     roots the first pin does not add a heading, it replaces every heading. */
  const pinnedMode = data.sections.some(s2 => s2.pinned)
  const pinnedIds = new Set(data.sections.filter(s2 => s2.pinned).map(s2 => s2.id))
  const candidates = (adding || []).filter(r => !r.reference && !pinnedIds.has(r.id))

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-center gap-1.5">
        {all.length > 1 && all.map(s2 => {
            const on = !hidden.has(s2.id)
            return (
              <button key={s2.id} onClick={() => toggle(setHidden, s2.id)}
                aria-pressed={on}
                className={`rounded-full px-2.5 py-0.5 text-micro ring-1 ring-inset transition
                  ${on
                    ? 'bg-accent/10 text-accent ring-accent/30'
                    : 'text-faint line-through hover:text-ink ring-zinc-700'}`}>
              {s2.title}
              <span className="ml-1.5 tabular-nums opacity-60">{s2.count}</span>
            </button>
          )
        })}
        {/* A filtered board that looks like a whole board is how you forget a
            branch exists — so say so, and offer the way back. */}
        {filtered && (
          <span className="ml-1 text-micro text-warn">
            showing {shown.length} of {all.length}
            <button onClick={() => setHidden(new Set())}
              className="ml-1.5 underline">show all</button>
          </span>
        )}
        {/* Managing the board from the board. This was on the Chart page only,
            so changing a heading meant leaving, finding the node in a 57-row
            outline, pinning it, and coming back. */}
        <button onClick={() => (adding ? setAdding(null) : openPicker())}
          className="ml-auto rounded-full px-2.5 py-0.5 text-micro text-faint ring-1 ring-inset
              transition hover:text-accent hover:ring-accent/40 ring-zinc-700">
          {adding ? 'cancel' : '+ group'}
        </button>
        {/* Shelving is the one thing this app chooses not to show you, so the count
            is never conditional on having remembered it. A hidden project you cannot
            find is indistinguishable from a lost one. */}
        {shelvedRepos.length > 0 && (
          <button onClick={() => setShowShelf(s => !s)} aria-expanded={showShelf}
            className="rounded-full px-2.5 py-0.5 text-micro text-faint ring-1 ring-inset transition
                hover:text-accent hover:ring-accent/40 ring-zinc-700">
            {shelvedRepos.length} shelved
          </button>
        )}
      </div>

      {showShelf && shelvedRepos.length > 0 && (
        <div className="max-w-md rounded-card border p-3 border-border">
          <p className="mb-2 text-micro text-faint">
            Off the board by choice. The files were never touched, and Fleet still
            lists them — put one back and it returns exactly where it was.
          </p>
          <div className="space-y-0.5">
            {shelvedRepos.map(s2 => (
              <div key={s2.repo} className="flex items-center gap-2">
                <span className="truncate text-micro text-dim">
                  {s2.repo}
                </span>
                <span className="text-micro text-faint">
                  {s2.shelved_at?.slice(0, 10)}
                </span>
                <button onClick={() => restore(s2.repo)}
                  className="ml-auto text-micro text-accent hover:underline">restore</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {adding && (
        <div className="max-w-md rounded-card border p-3 border-border">
          <p className="mb-2 text-micro text-faint">
            Any goal on the chart can head a group. Its projects gather under it.
          </p>
          {!pinnedMode && (
            <p className="mb-2 text-micro text-warn">
              Nothing is pinned yet, so these headings are the chart's roots. The first
              group you add replaces them — the projects stay put either way.
            </p>
          )}
          <GoalPicker rows={candidates} outline={adding} empty="every goal already heads a group"
            onPick={o => setPinned(o.id, true)} onCancel={() => setAdding(null)} />
        </div>
      )}

      {err && (
        <p className="rounded-card border border-danger/40 bg-danger/5 px-3 py-2 text-body text-danger">
          {err} <button onClick={() => setErr(null)} className="ml-2 underline">dismiss</button>
        </p>
      )}

      {data.sections.length === 0 && data.uncharted.length === 0 && (
        <p className="text-body text-faint">Nothing yet. Open a project and start a chart.</p>
      )}

      {/* Every section says it will take the card the moment a drag starts.
          Highlighting only the one under the cursor tells you where you are, never
          where you could go — which is why the drop targets read as absent rather
          than as unlit. */}
      {data.sections.filter(sec => !hidden.has(sec.id)).map(sec => (
        <section
          key={sec.id}
          onDragOver={e => { e.preventDefault(); setOver(sec.id) }}
          onDragLeave={() => setOver(o => (o === sec.id ? null : o))}
          onDrop={e => {
            e.preventDefault()
            const pid = e.dataTransfer.getData('text/plain')
            if (pid) reparent(pid, sec.id)
          }}
          className={`group/sec rounded-card p-1 transition ${
            over === sec.id ? 'bg-accent/5 ring-1 ring-accent/40'
              : dragging ? 'ring-1 ring-accent/15' : ''}`}
        >
          {/* A bearing is the top of the hierarchy, so it is allowed to look like
              it. This was 14px/500 — the same weight as a card title, one step
              from body text — which is why the board read as one long list. */}
          <div className="mb-1 flex flex-wrap items-center gap-3">
            <button onClick={() => toggle(setCollapsed, sec.id)}
              aria-label={collapsed.has(sec.id) ? `expand ${sec.title}` : `collapse ${sec.title}`}
              className="text-section font-semibold tracking-tight hover:text-accent text-ink">
              {sec.title}
            </button>
            {/* The count came back when SoundingTrack left — the track had been
                carrying it, and a bearing with no number beside it gives no
                sense of how much sits underneath. */}
            <span className="text-meta tabular-nums text-faint">
              {sec.cards.length}
            </span>
            {sec.anchored && <span className="text-micro text-ok">anchored</span>}
            <div className="h-px flex-1 bg-surface-2" />
            {/* Remove, never delete — and only where there is a pin to pull. In
                fallback mode a heading is a chart root nobody chose, so there is
                nothing here to take away. */}
            {sec.pinned && (
              <button onClick={() => setPinned(sec.id, false)}
                title={sec.cards.length === 0
                  ? 'Remove this heading. Nothing sits under it.'
                  : sec.cards.length === 1
                    ? 'Remove this heading. Its 1 project keeps its place in the chart.'
                    : `Remove this heading. Its ${sec.cards.length} projects keep their place in the chart.`}
                className="text-micro opacity-0 transition hover:text-danger focus-visible:opacity-100 group-hover/sec:opacity-100 text-dim">
                remove
              </button>
            )}
          </div>
          {/* A waypoint is what would tell you this bearing is moving. Sixteen of
              them are blank, and the old markup rendered the label anyway — a
              dangling "Waypoint —" that read as a broken row rather than as the
              missing answer it is. */}
          {!collapsed.has(sec.id) && (
            sec.waypoint ? (
              <p className="mb-3 max-w-2xl text-meta text-faint">
                <span className="text-faint">Waypoint — </span>{sec.waypoint}
              </p>
            ) : (
              <p className="mb-3 text-meta italic text-faint">
                no waypoint — nothing here says what progress would look like
              </p>
            )
          )}

          {/* Collapsed keeps the section on screen as a header. Hiding removes it
              from view entirely; these are different things and both are wanted. */}
          {collapsed.has(sec.id) ? null : sec.cards.length === 0 ? (
            <p className="px-1 pb-3 text-body text-faint">
              {over === sec.id ? 'drop here' : 'nothing serves this yet'}
            </p>
          ) : (
            <div className="grid gap-4 px-1 pb-2 sm:grid-cols-2 lg:grid-cols-3">
              {sec.cards.map(c => (
                c.ghost ? (
                  <GhostCard key={c.problem_id} c={c}
                    onPromote={() => { window.location.hash = '#/goals' }} />
                ) : (
                  /* A ghost has no repo, so there is nothing to shelve — shelving is
                     a decision about a repo, not about a problem. */
                  <Slot key={c.problem_id} name={c.name || c.id}
                    onShelve={() => shelve(c.id)}>
                    <Card p={c} onOpen={onOpen} dragId={c.problem_id}
                      onDragStart={() => setDragging(true)}
                      onDragEnd={() => { setDragging(false); setOver(null) }} />
                  </Slot>
                )
              ))}
            </div>
          )}
        </section>
      ))}

      {/* Where a project lands when the heading above it is removed. It is on the
          chart and it has a problem node — what it lacks is a group — so it must
          not read as uncharted, and it must not silently not-be-anywhere, which is
          what removing a group used to do to it. Still draggable: the way out is
          to drop it onto a section. */}
      {ungrouped.length > 0 && !hidden.has(UNGROUPED) && (
        <section>
          <div className="mb-3 flex items-baseline gap-3">
            <h2 className="text-title font-semibold text-faint">Ungrouped</h2>
            <span className="text-meta tabular-nums text-faint">{ungrouped.length}</span>
            <span className="text-meta text-faint">
              charted, but no group heads them — drag one onto a section
            </span>
            <div className="h-px flex-1 bg-surface-2" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {ungrouped.map(c => (
              c.ghost ? (
                <GhostCard key={c.problem_id} c={c}
                  onPromote={() => { window.location.hash = '#/goals' }} />
              ) : (
                <Slot key={c.problem_id} name={c.name || c.id} onShelve={() => shelve(c.id)}>
                  <Card p={c} onOpen={onOpen} dragId={c.problem_id}
                    onDragStart={() => setDragging(true)}
                    onDragEnd={() => { setDragging(false); setOver(null) }} />
                </Slot>
              )
            ))}
          </div>
        </section>
      )}

      {data.uncharted.length > 0 && !hidden.has(UNCHARTED) && (
        <section>
          {/* Deliberately below the bearings and deliberately quieter than them:
              eighteen of thirty-one cards live here, and rendering the section
              that holds the least information at full heading weight is what made
              the chart — the actual idea — look like the footnote. */}
          <div className="mb-3 flex items-baseline gap-3">
            <h2 className="text-title font-semibold text-faint">Uncharted</h2>
            <span className="text-meta tabular-nums text-faint">{data.uncharted.length}</span>
            <span className="text-meta text-faint">
              nothing records why these exist
            </span>
            <div className="h-px flex-1 bg-surface-2" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.uncharted.map(p => (
              <Slot key={p.id} name={p.name || p.id} onShelve={() => shelve(p.id)}>
                <Card p={p} onOpen={onOpen} />
              </Slot>
            ))}
          </div>
        </section>
      )}

    </div>
  )
}
