import React, { useEffect, useState } from 'react'

/* Shared primitives. Product-blind: these know how to render a cycle chip or a
   relative date, and nothing about boards, charts or goals. */

// Quiet past two weeks is worth noticing; past a month is worth saying out loud.

const STALE_DAYS = 14

const COLD_DAYS = 30

function daysSince(iso) {
  if (!iso) return null
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return null
  return Math.floor((Date.now() - then.getTime()) / 86400000)
}

export function relTime(iso) {
  const d = daysSince(iso)
  if (d === null) return 'no git history'
  if (d === 0) return 'today'
  if (d === 1) return 'yesterday'
  if (d < 30) return `${d}d ago`
  const m = Math.floor(d / 30)
  return m < 12 ? `${m}mo ago` : `${Math.floor(d / 365)}y ago`
}

/* Recency reads as hue: quiet is warn, cold is danger. An all-grey version of
   this was tried and reverted — with age carried only by lightness, the
   difference between a repo touched yesterday and one cold for a month was two
   steps of grey nobody could see. */
export function activityTone(iso) {
  const d = daysSince(iso)
  if (d === null) return 'text-faint'
  if (d >= COLD_DAYS) return 'text-danger'
  if (d >= STALE_DAYS) return 'text-warn'
  return 'text-dim'
}

/* Soundings kept their data but lost their pixels — `assumed`/`proxy`/`observed`
   still ride on every problem and still cap through `effective_sounding`, they
   are simply not drawn anywhere. If they come back, they come back here: this is
   where `Sounding` and `SoundingTrack` lived (see git history at 7cbb154). */

/* What a repo's cycles say about it, in the slot `stage` used to hold.
 *
 * `stage` was the dial `standards.yaml` used to decide which bands of requirement
 * a repo owed — spike owed the floor, product owed everything. That file was
 * deleted in v0.5.0 and the field outlived its meaning by twenty-four versions,
 * rendering as a coloured word nothing read. What belongs in a strip's third
 * column is the fact the page exists to surface: may I start work here.
 *
 * Two states, because the gate has two answers. A count when nothing is running —
 * a track record, and the thing a bare tag cannot tell you. `cycle open` when a
 * record is in flight, which is precisely when `_open_gate` will refuse a second.
 */
export function CycleChip({ cycles }) {
  if (!cycles) return <span className="text-micro text-faint">—</span>
  if (cycles.open) {
    return (
      <span className="rounded-full bg-warn/12 px-2 py-0.5 text-micro font-medium
        uppercase tracking-wide text-warn ring-1 ring-inset ring-warn/25">
        cycle open
      </span>
    )
  }
  if (!cycles.closed) {
    return <span className="text-micro text-faint">no cycles yet</span>
  }
  return (
    <span className="text-micro text-faint">
      {cycles.closed} cycle{cycles.closed === 1 ? '' : 's'}
    </span>
  )
}


export function Heatmap({ pid }) {
  const [days, setDays] = useState(null)
  const [weeks, setWeeks] = useState(26)

  useEffect(() => {
    fetch(`/api/projects/${pid}/activity`)
      .then(r => r.json())
      .then(d => { setDays(d.days || {}); setWeeks(d.weeks || 26) })
  }, [pid])

  if (!days) return null
  const counts = Object.values(days)
  const max = counts.length ? Math.max(...counts) : 0
  const active = counts.length

  // Sunday-ending columns, oldest on the left — the GitHub shape.
  const today = new Date()
  const cols = []
  for (let w = weeks - 1; w >= 0; w--) {
    const col = []
    for (let d = 0; d < 7; d++) {
      const dt = new Date(today)
      dt.setDate(today.getDate() - (w * 7 + (6 - d)))
      const key = dt.toISOString().slice(0, 10)
      col.push({ key, n: days[key] || 0 })
    }
    cols.push(col)
  }

  const shade = n => {
    if (!n) return 'bg-surface-2'
    const r = max ? n / max : 0
    if (r > 0.66) return 'bg-accent'
    if (r > 0.33) return 'bg-accent/70'
    return 'bg-accent/40'
  }

  return (
    <div>
      <div className="mb-1.5 flex items-baseline gap-2">
        <h3 className="fleet-label">Activity</h3>
        <span className="text-micro text-faint">
          {active === 0 ? 'no commits in this window'
            : `${active} active day${active === 1 ? '' : 's'} in ${weeks} weeks`}
        </span>
      </div>
      <div className="flex gap-[3px] overflow-x-auto pb-1">
        {cols.map((col, i) => (
          <div key={i} className="flex flex-col gap-[3px]">
            {col.map(c => (
              <span key={c.key} title={`${c.key} · ${c.n} commit${c.n === 1 ? '' : 's'}`}
                className={`size-[9px] rounded-[2px] ${shade(c.n)}`} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/* Where a row sits, for anywhere a title alone is ambiguous. The outline is flat
   with a depth on each row, so the ancestors are the nearest preceding rows of
   decreasing depth. Two goals called "Model risk" are indistinguishable without it. */
export function pathOf(outline, row) {
  const out = []
  let want = row.depth - 1
  for (let i = outline.indexOf(row) - 1; i >= 0 && want >= 0; i--) {
    if (outline[i].depth === want) { out.unshift(outline[i].title); want-- }
  }
  return out
}

/* Choosing one goal out of the whole chart.
 *
 * Forty-five bare pills with no hierarchy is not a chooser: type to narrow, and
 * every candidate carries the path it sits on. Both places that pick a goal are
 * this one widget — the chart's "also serve another goal" and the board's "add a
 * group" — because two pickers over one chart is how they drift apart. */
export function GoalPicker({ rows, outline, noun = 'goals', empty, onPick, onCancel }) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const hits = rows.filter(o =>
    !q || (o.title + ' ' + pathOf(outline, o).join(' ')).toLowerCase().includes(q))

  return (
    <div>
      <input
        value={query} onChange={e => setQuery(e.target.value)} autoFocus
        placeholder={`filter ${rows.length} ${noun}…`}
        className="w-full rounded-lg border bg-transparent px-2 py-1 text-meta
            focus:border-accent border-zinc-700"
      />
      <div className="mt-1.5 max-h-64 space-y-0.5 overflow-y-auto">
        {rows.length === 0 && <span className="text-micro text-faint">{empty}</span>}
        {rows.length > 0 && hits.length === 0 && (
          <span className="text-micro text-faint">nothing matches “{query.trim()}”</span>
        )}
        {hits.slice(0, 40).map(o => {
          const trail = pathOf(outline, o)
          return (
            <button key={o.id} onClick={() => onPick(o)}
              className="block w-full rounded-lg px-2 py-1 text-left transition hover:bg-surface-2">
              <span className="block truncate text-micro text-dim">
                {o.title}
              </span>
              {trail.length > 0 && (
                <span className="block truncate text-micro text-faint">
                  {trail.join(' › ')}
                </span>
              )}
            </button>
          )
        })}
      </div>
      <button onClick={onCancel} className="mt-2 text-micro text-faint">cancel</button>
    </div>
  )
}

/* View state that is about *looking*, not about the data, so it belongs to this
   browser rather than to the chart. Shared by the board's section filter and the
   goals outline's collapse state. */
export function useStored(key, initial) {
  const [v, setV] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(key)) ?? initial) }
    catch { return new Set(initial) }
  })
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify([...v])) } catch { /* private mode */ }
  }, [key, v])
  return [v, setV]
}
