import React, { useEffect, useState, useCallback } from 'react'
import { relTime, CycleChip } from './kit'
import {
  PageHeader, SectionHeading, Table, Row, Cell, Chip, Mono, Status,
  Inspector, Facet, KeyValues, Button, Loading, ErrorState, EmptyState,
  Strip, Bay,
} from './ui'

/* Fleet — the factory floor (v0.28.0, the yard).
 *
 * One question: WHAT MAY START NEXT. Three stages answer it — a thought waits in
 * the queue until it has a waypoint, the gate says which repos could open a cycle
 * today, and receiving is where a repo enters at all.
 *
 * v0.29.3 deleted the other half. The line, the portfolio and the rhythm measured
 * the operator rather than the fleet, and two of them measured nothing at all:
 * `hill_snapshots` held zero rows and no problem ever carried a due date. A page
 * built to start work had become a telemetry page whose telemetry was never
 * recorded, and was not opened.
 *
 * Read from git, the chart and Mission Control on every load — there is
 * nothing here to keep up to date. The board still owns authoring. */

const OWED_TONE = {
  uncommitted: 'danger', unpushed: 'danger', 'running-old-code': 'danger',
  /* no-remote wears danger like the lamp does: it is the one-disk-failure-from-
     gone state, and a chip disagreeing with its own strip's lamp reads as a bug. */
  'no-remote': 'danger', untagged: 'warn', unlogged: 'warn', uncharted: 'quiet',
  'no-waypoint': 'warn',
}
const OWED_LABEL = {
  uncommitted: 'uncommitted', unpushed: 'unpushed', 'no-remote': 'no remote',
  untagged: 'untagged', unlogged: 'unlogged', uncharted: 'uncharted',
  'running-old-code': 'running old code', 'no-waypoint': 'no waypoint',
}

function BlockerChips({ items }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {items.map(it => (
        <Chip key={it.kind} tone={OWED_TONE[it.kind] || 'warn'} title={it.detail || undefined}>
          {it.n ? `${it.n} ` : ''}{OWED_LABEL[it.kind] || it.kind}
        </Chip>
      ))}
    </span>
  )
}

function fmtUptime(s) {
  if (typeof s !== 'number') return null
  if (s < 3600) return `${Math.round(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
  return `${Math.floor(s / 86400)}d`
}

/* One derivation of who the gate would refuse, shared by the map and the gate
   band — two counts of the same thing is how they come to disagree. */
function gateRefusals(owes) {
  return (owes?.strips || [])
    .filter(s => (s.blockers || []).some(b => GATED_KINDS.includes(b.kind)))
    .map(s => s.name || s.id)
}

/* The map — the story, drawn instead of narrated. Counts are live, from reads the
   page already makes; each stage jumps to its band. Flow order is queue → gate →
   receiving, which is the order work actually moves in: an idea becomes startable,
   a repo becomes admissible, and a directory becomes a project. */
function MapStage({ target, label, value, sub, tone }) {
  /* A button scrolling by id, not an <a href="#...">: the app routes on the hash
     (#/yard), so an anchor would rewrite the route instead of moving the page. */
  return (
    <button type="button"
      onClick={() => document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      className="fleet-btn flex min-w-[9.5rem] flex-1 flex-col gap-0.5 text-left">
      <span className="fleet-label">{label}</span>
      <span className={`text-section font-semibold tracking-tight ${tone === 'warn' ? 'text-warn' : ''}`}>
        {value}
      </span>
      <span className="text-micro text-faint">{sub}</span>
    </button>
  )
}

function MapBand({ yard, receiving, owesBay }) {
  if (!yard) return null
  const queued = (yard.queue || []).length
  const refusals = gateRefusals(owesBay)
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-stretch gap-2">
        <MapStage target="queue" label="The queue" value={queued}
          sub={queued ? 'captured, needs a waypoint' : 'nothing waiting'} />
        <span className="self-center text-faint" aria-hidden="true">→</span>
        <MapStage target="gate" label="The gate"
          value={refusals.length} tone={refusals.length ? 'warn' : undefined}
          sub={refusals.length ? 'would be refused today' : 'refuses nothing today'} />
        <span className="self-center text-faint" aria-hidden="true">→</span>
        <MapStage target="receiving" label="Receiving"
          value={receiving == null ? '—' : receiving}
          sub={receiving ? 'on disk, not yet adopted' : 'nothing waiting'} />
      </div>
      <p className="mt-2 text-micro text-faint">
        One question, three stages: what may start next. A thought is captured in the
        queue and leaves it by gaining a waypoint; the gate says which repos could
        open a cycle today; receiving is where a repo enters at all.
      </p>
    </div>
  )
}

/* The strip's mono second line: ports · version — machine facts, never prose. */
function subOf(s) {
  const ports = s.runtime?.ports || []
  const left = ports.length ? ports.map(n => `:${n}`).join(' ') : 'no port'
  return `${left} · ${s.version || 'untagged'}`
}

/* Evidence: what the machine can attest right now. Runtime when Mission Control
   knows it; otherwise the chart group it stands under. */
function evidenceOf(s) {
  if (s.runtime) {
    const up = fmtUptime(s.runtime.uptime_s)
    return up ? `${s.runtime.state} · ${up} up` : s.runtime.state
  }
  return s.goal ? `under ${s.goal}` : '—'
}

/* Bays arrive in display order from the backend and an empty bay never arrives
   at all, so this map carries only what the payload cannot: the doctrine hue for
   the bay lamp and count. Unknown keys default restrictive — amber, not green. */
const BAY_META = {
  clear: { lamp: 'ok', tone: 'ok' },
  owes: { lamp: 'warn', tone: 'warn' },
  uncharted: { lamp: 'warn', tone: 'warn' },
  'no-waypoint': { lamp: 'warn', tone: 'warn' },
  shelved: { lamp: 'off', tone: 'quiet' },
}

/* The gate's detail: every repo in the bay that names what blocks it (v0.29.3).
 *
 * This is `YardBand` returning, and the return is the point. It was replaced in
 * `6641975` by a ledger that grouped the same repos by *motion* — moving, slowing,
 * dormant — which answered a question about the operator rather than about what may
 * start. The ledger is gone with the rest of the self-measurement; the bays it
 * displaced were always the gate's own data, and they come back underneath it where
 * the 422 can be read row by row.
 *
 * The third column is now the cycle chip. It used to be `stage`, which stopped
 * meaning anything when `standards.yaml` was deleted. */
function BayBand({ bays, scanned, onOpen }) {
  return (
    <div id="bays" className="mt-6">
      {bays.length === 0 ? (
        scanned === 0 ? (
          <EmptyState glyph="◫" title="Nothing scanned"
            detail="No manifests found under the code root — adopt a repo below to give the gate something to hold." />
        ) : (
          <p className="text-meta text-faint">
            Nothing is held {'—'} all {scanned} repos could open a cycle today.
          </p>
        )
      ) : (
        bays.map(bay => {
          const meta = BAY_META[bay.key] || { lamp: 'warn', tone: 'warn' }
          return (
            <Bay key={bay.key} lamp={meta.lamp} title={bay.title}
              count={bay.strips.length} countTone={meta.tone} aside={bay.why}>
              {bay.strips.map(s => (
                <Strip key={s.id}
                  lamp={s.lamp}
                  name={s.name || s.id}
                  sub={subOf(s)}
                  manned={s.manned}
                  stage={<CycleChip cycles={s.cycles} />}
                  evidence={evidenceOf(s)}
                  age={relTime(s.last_activity)}
                  /* Cocked = attention, spent on the owes bay and nowhere else.
                     Refusal is narrower (GATED_KINDS) — the gate band names it. */
                  cocked={bay.key === 'owes'}
                  tone={s.lamp === 'danger' ? 'danger' : 'warn'}
                  onClick={() => onOpen(s.id)}>
                  {s.blockers?.length
                    ? <BlockerChips items={s.blockers} />
                    : <span className="line-clamp-1">{s.why || s.goal || '—'}</span>}
                </Strip>
              ))}
            </Bay>
          )
        })
      )}
      <p className="mt-3 text-micro text-faint">
        Ranked by nothing {'—'} a bay says why a repo cannot start, and within one the
        order is the roster, never merit.
      </p>
    </div>
  )
}

/* Three tabs, one of which is the page you are on. Plain hash links, not buttons:
   the app routes on the hash, so a link is the honest control and middle-click works.

   Exported and drawn by all three pages rather than by the Yard alone. A tab strip
   you can only reach from one of its own tabs is a one-way door: you would reach
   Standards from the Yard and then have to go back to reach the manual. One more
   view→view edge, in a codebase that already has `goals → argument, graph` and
   `project → graph, goals`; ARCHITECTURE.md lists them and says the list is either
   a rule or it is not. */
export function PageTabs() {
  const here = window.location.hash
  const tabs = [['#/yard', 'The yard'], ['#/standards', 'Standards'], ['#/docs', 'What this is']]
  return (
    <nav className="mb-6 flex flex-wrap gap-1 border-b border-border"
      aria-label="Yard sections">
      {tabs.map(([href, label]) => {
        const active = here === href
        return (
          <a key={href} href={href} aria-current={active ? 'page' : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-meta transition ${active
              ? 'border-accent font-medium text-ink'
              : 'border-transparent text-faint hover:text-ink'}`}>
            {label}
          </a>
        )
      })}
    </nav>
  )
}

/* The queue (v0.29.2) — captured, not yet startable.
 *
 * A draft is a problem someone wrote down before they had its observable, which
 * `create_problem(draft=true)` has always allowed on the grounds that you cannot
 * demand a waypoint between pressing Enter and having the next thought. What it
 * never had was a place that asks you to finish it.
 *
 * There is no promote button, and that is the design: promotion IS writing the
 * waypoint. The moment a draft has one it stops being a draft, the open gate stops
 * refusing it, and a cycle can be cut against it — so the row links to the problem
 * and the chart's own editor does the rest. A second verb here would be a second
 * way to do the one thing, which is how two surfaces come to disagree. */
function QueueBand({ queue }) {
  const rows = queue || []
  return (
    <div id="queue" className="mt-8">
      <SectionHeading aside="captured but not yet startable — a waypoint is what lets one out">
        The queue
      </SectionHeading>
      {rows.length === 0 ? (
        <EmptyState title="Nothing waiting"
          detail="Every problem on the chart carries an observable. A thought captured without one lands here." />
      ) : (
        <>
          <Table columns={[
            { key: 'title', label: 'Captured' },
            { key: 'serves', label: 'Serves', width: '18rem' },
            { key: 'waiting', label: 'Waiting', width: '8rem' },
          ]}>
            {rows.map(q => (
              <Row key={q.id} onClick={() => { window.location.hash = `#/problem/${q.id}` }}>
                <Cell className="font-medium text-ink">{q.title}</Cell>
                <Cell>{q.parent
                  ? <span className="text-faint">{q.parent}</span>
                  : <Chip tone="warn">nothing</Chip>}</Cell>
                <Cell><Mono>{relTime(q.created_at)}</Mono></Cell>
              </Row>
            ))}
          </Table>
          <p className="mt-3 text-micro text-faint">
            Oldest first {'—'} the one that has waited longest is the one being asked
            about. Groupings are not listed: a problem with others beneath it has no
            observable of its own and never will.
          </p>
        </>
      )}
    </div>
  )
}

/* The gate, as a band: the rule as a chip, and the one sentence naming who it
   would refuse today — derived from the yard's owes bay, no second fetch, so the
   band and the bay can never disagree. Refusal *events* land here next cycle,
   once the 422 has actually fired at the API. */
/* Only uncommitted and unpushed are gate kinds (D4) — the owes bay holds more
   (untagged, unlogged, no-remote), so naming the whole bay here would overstate
   what the 422 enforces. The band claims exactly what the API refuses. */
const GATED_KINDS = ['uncommitted', 'unpushed']

function GateBand({ owes }) {
  const names = gateRefusals(owes)
  return (
    <div id="gate">
      <SectionHeading aside="what stops a sloppy cycle from closing — enforced at the API, not advised">
        The gate
      </SectionHeading>
      <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1.5 text-meta text-dim">
        <Chip tone="danger" mono>422 — review refuses an owing repo</Chip>
        <span>
          {names.length ? (
            <>
              Today it would refuse{' '}
              {names.map((n, i) => (
                <React.Fragment key={n}>
                  {i > 0 && (i === names.length - 1 ? ' and ' : ', ')}
                  <span className="font-medium text-ink">{n}</span>
                </React.Fragment>
              ))}
              {' — each owes the work its strip names below.'}
            </>
          ) : (
            <>It would refuse nothing today {'—'} nothing owes uncommitted or unpushed work.</>
          )}
        </span>
      </p>
    </div>
  )
}

/* Git repos on disk with no PROJECT.yaml — the fleet's blind spot, since every
   other reading here starts from a manifest. Adopting one writes the manifest
   into that repo, which is the one place shipyard writes outside itself, so it
   stays an explicit per-repo action rather than anything bulk.

   Receiving, in the console order: the last band, because work enters here. */
function Importable({ repos, reload, onImported }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const adopt = r => {
    setBusy(r.path); setErr(null)
    fetch('/api/importable', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: r.path, name: r.name }),
    })
      .then(async res => { if (!res.ok) throw new Error((await res.json()).detail); return res.json() })
      .then(() => { reload(); onImported?.() })
      .catch(e => setErr(e.message))
      .finally(() => setBusy(null))
  }

  // Renders at zero, unlike the bays. A bay is one of several and an empty one is
  // noise; receiving is one of the map's three stages, and a tile that scrolls to
  // nothing is worse than a heading that says "nothing waiting". `repos` may still
  // be null while the fetch is in flight — that is not the same as empty.
  const waiting = repos?.length ?? 0

  return (
    <section id="receiving" className="mt-10 border-t pt-5 border-border">
      <SectionHeading aside="repos on disk shipyard cannot see yet — adopting one is how work enters">
        <button onClick={() => setOpen(v => !v)}
          className="inline-flex items-baseline gap-2 transition hover:text-accent
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
          Receiving
          <Chip>{repos == null ? '…' : waiting}</Chip>
          <span className="text-meta font-normal text-faint">{open ? '▾' : '▸'}</span>
        </button>
      </SectionHeading>

      {err && <p className="mb-2 text-meta text-danger">{err}</p>}

      {repos != null && waiting === 0 && (
        <p className="text-meta text-faint">
          Every git repo under the code root has a <Mono>PROJECT.yaml</Mono>. Nothing is
          waiting to be adopted.
        </p>
      )}

      {open && (
        <Table columns={[
          { key: 'name', label: 'Repo', width: '14rem' },
          { key: 'path', label: 'Path' },
          { key: 'last', label: 'Last commit', width: '9rem' },
          { key: 'act', label: '', width: '7rem' },
        ]}>
          {repos.map(r => (
            <Row key={r.path}>
              <Cell className="whitespace-nowrap font-medium text-ink">
                {r.name}
              </Cell>
              <Cell><Mono>{r.path.replace(/^.*\/code\//, 'code/')}</Mono></Cell>
              <Cell>
                <Mono>{r.last_activity ? r.last_activity.slice(0, 10) : 'no commits'}</Mono>
              </Cell>
              <Cell>
                <Button onClick={() => adopt(r)} disabled={busy === r.path}>
                  {busy === r.path ? 'Importing…' : 'Import'}
                </Button>
              </Cell>
            </Row>
          ))}
        </Table>
      )}
    </section>
  )
}

export function FleetPage({ onOpen }) {
  const [yard, setYard] = useState(null)
  const [yardErr, setYardErr] = useState(null)
  const [projects, setProjects] = useState(null)
  const [sel, setSel] = useState(null)
  const [importable, setImportable] = useState(null)

  useEffect(() => {
    let live = true
    fetch('/api/projects')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => live && setProjects(Object.fromEntries((d.projects || []).map(p => [p.id, p]))))
      .catch(() => live && setProjects({}))
    return () => { live = false }
  }, [])

  /* Lifted out of Importable so the map and the band read one fetch — a count
     and the list it counts must not be able to disagree. */
  const loadImportable = useCallback(() => {
    fetch('/api/importable').then(r => r.json())
      .then(d => setImportable(d.repos || [])).catch(() => setImportable([]))
  }, [])
  useEffect(loadImportable, [loadImportable])

  const loadYard = useCallback(() => {
    setYardErr(null)
    fetch('/api/yard')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`yard: HTTP ${r.status}`))))
      .then(setYard)
      .catch(e => setYardErr(e.message))
  }, [])
  useEffect(loadYard, [loadYard])

  const bays = yard?.bays || []
  const owesBay = bays.find(b => b.key === 'owes')
  const clearN = bays.find(b => b.key === 'clear')?.strips.length ?? 0
  const heldN = bays.filter(b => b.key !== 'clear')
    .reduce((n, b) => n + b.strips.length, 0)
  // One repo, one set of facts. Indexed by id so the inspector reads the same strip
  // the band drew rather than a second copy that could disagree with it.
  const stripsById = Object.fromEntries(
    bays.flatMap(b => b.strips.map(s => [s.id, s])))

  // The inspector reads the strip it was opened from; a reload that removes the
  // strip closes the drawer honestly rather than showing a repo that moved.
  let selStrip = null, selBayKey = null
  if (sel) {
    for (const b of bays) {
      const s = b.strips.find(x => x.id === sel)
      if (s) { selStrip = s; selBayKey = b.key; break }
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader title="Yard">
        {yard && (
          <>
            {clearN} of {yard.scanned} could open a cycle today · {heldN} held.
            Read from git, the chart and Mission Control on every load {'—'} only the
            shelf is stored.
          </>
        )}
      </PageHeader>

      {/* The Yard's own tabs. Standards used to be a collapsed section at the very
          bottom of this page, which is where a convention goes to be indistinguishable
          from one that does not exist — and this page's waypoint says it shows the
          queue, the gate and receiving and nothing else. Both moved out to pages of
          their own rather than being deleted or left buried. */}
      <PageTabs />

      {/* Flow order, top to bottom: the map, then the stages it names — queue,
         gate and its bays — then the standards, then receiving as the collapsed
         intake at the bottom, where the map's last stage jumps to it. */}
      <MapBand yard={yard} owesBay={owesBay}
        receiving={importable ? importable.length : null} />

      {yard && <QueueBand queue={yard.queue} />}

      {yardErr ? (
        <ErrorState title="Could not read the yard" detail={yardErr} onRetry={loadYard} />
      ) : !yard ? (
        <Loading label="Reading the yard" />
      ) : (
        <div className="mt-8">
          <GateBand owes={owesBay} />
          <BayBand bays={bays} scanned={yard.scanned} onOpen={setSel} />
        </div>
      )}

      <Importable repos={importable} reload={loadImportable} onImported={loadYard} />

      {selStrip && (
        <RepoInspector
          strip={selStrip}
          bayKey={selBayKey}
          onChanged={loadYard}
          p={projects?.[selStrip.id]}
          onClose={() => setSel(null)}
          onOpen={onOpen}
        />
      )}
    </main>
  )
}

/* The gate checklist: named binary facts, grouped, never summed. Missing items
   are the same words as the strip's chips and the bay's name — one vocabulary,
   three densities. Built from the strip's blockers plus the chart facts; a fact
   this payload cannot decide is omitted rather than guessed green. */
function gateChecklist(strip, bayKey, p) {
  const blockers = strip.blockers || []
  const by = Object.fromEntries(blockers.map(b => [b.kind, b]))
  const used = new Set()
  const whyOf = k => {
    const b = by[k]
    if (!b) return null
    return b.detail || (b.n != null ? `${b.n} ${OWED_LABEL[k] || k}` : OWED_LABEL[k] || k)
  }
  const items = []
  const req = (kinds, label, metWhy) => {
    kinds.forEach(k => used.add(k))
    const hit = kinds.find(k => by[k])
    if (hit) items.push({ ok: false, label, why: whyOf(hit) })
    else items.push({ ok: true, label, why: metWhy })
  }

  req(['uncommitted'], 'committed', 'clean tree')
  req(['unpushed', 'no-remote'], 'pushed', 'remote up to date')
  req(['untagged'], 'tagged', strip.version || null)
  req(['unlogged'], 'logged', 'changelog current')

  used.add('uncharted'); used.add('no-waypoint')
  const charted = bayKey !== 'uncharted' && !by.uncharted && !!(strip.goal || p?.why)
  items.push(charted
    ? { ok: true, label: 'charted', why: strip.goal ? `under “${strip.goal}”` : null }
    : { ok: false, label: 'charted', why: 'no chart node records why this exists' })
  if (charted) {
    if (bayKey === 'no-waypoint' || by['no-waypoint']) {
      items.push({ ok: false, label: 'waypoint', why: 'nothing records what entering the line would mean' })
    } else if (p?.waypoint) {
      items.push({ ok: true, label: 'waypoint', why: p.waypoint })
    } else if (bayKey === 'clear') {
      // Clear is defined as charted AND waypointed; the bay is the evidence.
      items.push({ ok: true, label: 'waypoint', why: null })
    }
    // Otherwise this payload cannot decide it — no row, no false signal.
  }

  // Any blocker kind the fixed rows did not claim still surfaces: nothing a
  // strip owes is allowed to vanish between the chips and the checklist.
  for (const b of blockers) {
    if (used.has(b.kind)) continue
    items.push({ ok: false, label: OWED_LABEL[b.kind] || b.kind, why: b.detail || (b.n != null ? String(b.n) : null) })
  }
  return items
}

function StandingFacet({ strip, onChanged }) {
  const [busy, setBusy] = useState(null)
  const state = strip.standing               // 'carried' | 'shelved' | null

  const call = async (label, req) => {
    setBusy(label)
    try {
      const r = await req()
      if (!r.ok) throw new Error(await r.text())
      onChanged()
    } catch (e) {
      // Surfaced in place rather than as a page-level error: this is a mutation,
      // and blowing away the drawer would take the context with it.
      setBusy(`failed — ${String(e.message || e).slice(0, 80)}`)
      return
    }
    setBusy(null)
  }

  const post = (url, body) => fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  return (
    <>
      <Facet label="Standing —" source="repo_standing">
        <p className="mb-2 text-meta">
          {state === 'carried' ? 'Carried — declared as work you mean to do.'
            : state === 'shelved' ? 'Shelved — deliberately out of service.'
              : 'Not ruled on. Every unshelved repo is drawn either way.'}
        </p>
        <div className="flex flex-wrap gap-2">
          {state !== 'carried' && (
            <Button tone="accent" onClick={() =>
              call('carry', () => post('/api/carried', { repo: strip.id }))}>
              Carry
            </Button>
          )}
          {state === 'carried' && (
            <Button onClick={() => call('uncarry', () =>
              fetch(`/api/carried/${encodeURIComponent(strip.id)}`, { method: 'DELETE' }))}>
              Stop carrying
            </Button>
          )}
          {state !== 'shelved' && (
            <Button onClick={() => call('shelve', () =>
              post('/api/shelved', { repo: strip.id }))}>
              Shelve
            </Button>
          )}
          {state === 'shelved' && (
            <Button onClick={() => call('restore', () =>
              fetch(`/api/shelved/${encodeURIComponent(strip.id)}`, { method: 'DELETE' }))}>
              Unshelve
            </Button>
          )}
        </div>
        {busy && <p className="mt-2 text-micro text-faint">{busy}</p>}
      </Facet>

    </>
  )
}

function RepoInspector({ strip, bayKey, p, onClose, onOpen, onChanged }) {
  const rt = strip.runtime
  const up = fmtUptime(rt?.uptime_s)
  const why = p?.why ?? strip.why
  const checklist = gateChecklist(strip, bayKey, p)

  return (
    <Inspector
      title={strip.name || strip.id}
      badge={rt ? <Status state={rt.state} /> : null}
      onClose={onClose}
    >
      <StandingFacet strip={strip} onChanged={onChanged} />
      <Facet label="Why —" source="chart">
        {why ? (
          <>
            <p className="text-body">{why}</p>
            {p?.waypoint && (
              <p className="mt-1.5 text-meta text-faint">
                <span className="text-faint">Waypoint {'— '}</span>
                {p.waypoint}
              </p>
            )}
          </>
        ) : (
          <p className="text-body text-warn">Nothing records why this exists.</p>
        )}
      </Facet>

      <Facet label="Gate —" source="owed + chart">
        <ul className="space-y-1 text-meta">
          {checklist.map(it => (
            <li key={it.label} className="flex items-baseline gap-2.5">
              <span className={`w-4 shrink-0 font-mono font-semibold ${it.ok ? 'text-ok' : 'text-danger'}`}>
                {it.ok ? '✓' : '✕'}
              </span>
              <span className={it.ok ? 'text-faint' : 'font-medium text-danger'}>
                {it.label}
                {it.why && (
                  <span className="ml-1.5 text-micro font-normal text-faint">
                    {'· '}{it.why}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Facet>

      <Facet label="What —" source="PROJECT.yaml">
        {p?.description && (
          <p className="mb-2 text-body text-dim">{p.description}</p>
        )}
        <KeyValues rows={[
          ['Cycles', strip.cycles?.open ? 'one open' : `${strip.cycles?.closed ?? 0} cut`],
          ['Released', strip.version || 'untagged'],
          p && ['Branch', p.version?.branch || '—'],
          ['Activity', relTime(strip.last_activity ?? p?.last_activity)],
          p && ['Path', p.path?.replace(/^.*\/code\//, 'code/') || '—'],
        ]} />
      </Facet>

      <Facet label="Runtime —" source="apps.yaml">
        {rt ? (
          <KeyValues rows={[
            ['Status', up ? `${rt.state} · ${up}` : rt.state],
            ['Ports', rt.ports?.length ? rt.ports.join(', ') : 'none'],
            p && ['MC id', (p.mc || []).join(', ') || '—'],
          ]} />
        ) : (
          <p className="text-meta text-faint">
            Not registered with Mission Control {'—'} this is not something you start.
          </p>
        )}
      </Facet>

      <div className="flex flex-wrap gap-2">
        <Button tone="primary" onClick={() => { onClose(); onOpen(strip.id) }}>Open project</Button>
        {p?.links?.app && <Button onClick={() => window.open(p.links.app, '_blank')}>Open app</Button>}
      </div>

      <p className="text-micro text-faint">
        One vocabulary, three densities {'—'} the bay{'’'}s name, the strip{'’'}s
        chips and this checklist are the same words at three zoom levels.
      </p>
    </Inspector>
  )
}
