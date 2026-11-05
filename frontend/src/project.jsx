import React, { useEffect, useState, useCallback } from 'react'
// Extends the documented exception (project → graph) with `goals`, for GoalRail.
// The outline this page used to carry was its only authoring surface; deleting it
// in favour of the canvas would have taken rename, delete and decomposition with it
// unless the rail came across too — and a SECOND rail written here is how two
// surfaces that edit one chart start disagreeing about what editing it means.
import { GraphPage } from './graph'
import { GoalRail } from './goals'
import { Heatmap, CycleChip, activityTone, relTime } from './kit'
import { Boundary, Chip, ErrorState, Loading, Mono, SideHeading, Status, Tabs } from './ui'

/* One project as a page: its chart, its open work nested under the problems it
   serves, and its links, activity and runtime status.

   The page's own furniture now comes from `ui.jsx`; what stays here is the five
   panels, which are each big enough to be their own surface. Raw `text-body` /
   `text-meta` / `text-micro` are gone from the shell — styles.css says a raw
   pixel size is a bug rather than a choice, and this file held two dozen. */

export function LinkRow({ label, href }) {
  if (!href) return null
  const url = String(href)
  return (
    <div className="flex gap-3 py-1 text-meta">
      <span className="w-14 shrink-0 text-faint">{label}</span>
      {url.startsWith('http')
        ? <a href={url} target="_blank" rel="noreferrer"
            className="break-all text-accent hover:underline">{url}</a>
        : <Mono className="break-all">{url}</Mono>}
    </div>
  )
}

export { SideHeading }

/* ---------- state ---------- */

/* What state the repo is in, read entirely out of git and Mission Control.

   A single version number would be a lie of omission — a repo thirteen commits
   past its last tag is not "v0.14.0" — so the released tag, the unnamed work on
   top of it, and whether the tree and remote agree are all separate chips. */
export function StateStrip({ pid, version, changelog, behind }) {
  if (!version) return null
  const { tag, ahead, dirty, unpushed, has_remote: hasRemote, branch } = version
  const openChangelog = () => {
    if (changelog?.path) {
      window.location.hash =
        `#/doc/${encodeURIComponent(pid)}/${encodeURIComponent(changelog.path)}`
    }
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <Chip title="latest git tag">
        <code>{tag || 'untagged'}</code>
      </Chip>
      {ahead > 0 && (
        <Chip tone="warn" title={`${ahead} commits since ${tag} — released work and current work differ`}>
          {ahead} ahead
        </Chip>
      )}
      {branch && branch !== 'main' && branch !== 'master' && (
        <Chip title="current branch">{branch}</Chip>
      )}
      {dirty > 0
        ? <Chip tone="warn" title="uncommitted changes in the working tree">
            {dirty} uncommitted
          </Chip>
        : <Chip tone="ok" title="working tree is clean">clean</Chip>}
      {!hasRemote
        ? <Chip tone="danger" title="no upstream — nothing here can be shown to anyone else">
            no remote
          </Chip>
        : unpushed > 0
          ? <Chip tone="warn" title="commits that exist only on this machine">
              {unpushed} unpushed
            </Chip>
          : null}
      {behind && (
        <Chip tone="danger"
          title="the running process started before the newest commit — it is serving old code">
          running old code
        </Chip>
      )}
      {/* The audit chip: read one curated summary instead of every commit, and
          notice when the summary has stopped keeping up. */}
      {changelog?.drift && (
        <button onClick={openChangelog} className="text-left">
          <Chip tone="warn"
            title={`Not written down in ${changelog.path || 'a changelog'}:\n` +
              changelog.unlogged.map(u => `  ${u.sha}  ${u.subject}`).join('\n')}>
            {changelog.unlogged.length} unlogged
          </Chip>
        </button>
      )}
      {changelog?.release_behind && (
        <button onClick={openChangelog} className="text-left">
          <Chip tone="warn"
            title={`the changelog's newest entry is ${changelog.latest_documented}, but the newest tag is ${tag}`}>
            changelog at {changelog.latest_documented}
          </Chip>
        </button>
      )}
    </div>
  )
}

/* ---------- documentation ---------- */

function DocRow({ pid, doc }) {
  const open = e => {
    e.preventDefault()
    window.location.hash = `#/doc/${encodeURIComponent(pid)}/${encodeURIComponent(doc.path)}`
  }
  if (doc.kind === 'url') {
    return (
      <a href={doc.href} target="_blank" rel="noreferrer"
        className="flex items-baseline gap-2 py-1 text-meta text-accent hover:underline">
        {doc.label} <span className="text-micro text-faint">↗</span>
      </a>
    )
  }
  return (
    <a href="#" onClick={open}
      className="block py-1 text-meta text-accent hover:underline">{doc.label}</a>
  )
}

function Documents({ pid, documents, onDecisions }) {
  if (!documents?.length) {
    return (
      <p className="py-1 text-meta leading-relaxed text-faint">
        No README, ARCHITECTURE or CHANGELOG in this repo yet.
      </p>
    )
  }
  return documents.map(d => d.kind === 'dir' ? (
    <a key={d.label} href="#"
      onClick={e => { e.preventDefault(); onDecisions() }}
      className="flex items-baseline gap-2 py-1 text-meta text-accent hover:underline">
      {d.label}
      <Mono>{d.count}</Mono>
    </a>
  ) : <DocRow key={d.label} pid={pid} doc={d} />)
}

/* ---------- orientation ---------- */

const num = n => (n ?? 0).toLocaleString()

/* Why this project exists, above what it is made of.

   Orient answered "what is this code" — lines, layout, where the attention went —
   and nothing about what any of it is for. The chart already knew: a project is a
   problem with a repo, so the goal it serves is its parent and the case for it is
   the argument on its own node. Both were one tab away and neither was on the page
   you land on.

   Renders only for a charted project. Seventeen of nineteen have no chart node, and
   putting "nothing records why this exists" on all of them would be a nag you cannot
   act on from here — the drift inbox already owns that conversation. */
function Purpose({ pid }) {
  const [c, setC] = useState(null)
  const [arg, setArg] = useState(null)
  const [planned, setPlanned] = useState([])

  useEffect(() => {
    let live = true
    setC(null); setArg(null); setPlanned([])
    fetch(`/api/chart/${encodeURIComponent(pid)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!live || !d?.node) return
        setC(d)
        return fetch(`/api/problems/${d.node.id}/argument`)
          .then(r => (r.ok ? r.json() : null))
          .then(a => { if (live) setArg(a) })
      })
      .catch(() => {})
    // A planned cycle is a record with no tag behind it. It is the state you are
    // *in* while working, so it belongs on the page you land on rather than one
    // tab over with the finished ones.
    fetch(`/api/projects/${encodeURIComponent(pid)}/cycles`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (live && d?.planned) setPlanned(d.planned) })
      .catch(() => {})
    return () => { live = false }
  }, [pid])

  if (!c?.node) return null
  const parents = c.parents || []

  return (
    <div className="rounded-lg border p-4 border-border">
      {/* What is running right now, first — because on returning to a project that
          is the one thing you cannot reconstruct by reading the code. Conditional:
          with nothing in flight the block is absent rather than empty, so the page
          looks exactly as it did before a cycle was opened. */}
      {planned.length > 0 && (
        <div className="mb-4">
          <SideHeading>In flight</SideHeading>
          {planned.map(p => (
            <div key={p.version} className="mt-0.5 flex items-baseline gap-2">
              <code className="shrink-0 rounded px-1 font-mono text-micro ring-1 ring-inset text-dim
                  ring-zinc-700">v{p.version}</code>
              <span className="text-body">{p.title}</span>
            </div>
          ))}
          <p className="mt-1 text-micro text-faint">
            Planned, not yet cut — the plan is in the vault, and tagging
            {' '}<code>v{planned[0].version}</code> is what closes it.
          </p>
        </div>
      )}

      {/* The goal this spawns out of. A project that serves several says so rather
          than picking one, because which parent "counts" is exactly the judgement
          shipyard is not entitled to make. */}
      {parents.length > 0 && (
        <div className="mb-4">
          <SideHeading>Serves</SideHeading>
          {/* Shown, not linked. The chart tab is rooted at this project's own
              problem so it cannot display a parent, and there is no deep link into
              the goals outline — a click that lands somewhere unable to show what
              was promised is worse than plain text. */}
          {parents.map(p => (
            <div key={p.id} className="mt-0.5">
              <p className="text-body">{p.title}</p>
              {p.waypoint && (
                <p className="mt-0.5 text-meta text-faint">⌖ {p.waypoint}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className={arg?.exists ? 'mb-4' : undefined}>
        <SideHeading>What would tell me this is working</SideHeading>
        <p className="mt-0.5 text-body">{c.node.waypoint || <span className="text-warn">no waypoint</span>}</p>
      </div>

      {/* The case: not "is the claim true" but "is this worth the hours". Shown as
          its thesis, because a claim list is readable at a glance and an essay is not. */}
      {arg?.exists ? (
        <div>
          <SideHeading>The case</SideHeading>
          {arg.thesis?.length > 0 && (
            <ol className="mt-0.5 space-y-1">
              {arg.thesis.map((t, i) => (
                <li key={i} className="flex gap-2 text-body">
                  <span className="shrink-0 tabular-nums text-faint">{i + 1}.</span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          )}
          <a href={`#/argument/${encodeURIComponent(c.node.id)}`}
            className="mt-2 inline-block text-meta text-accent hover:underline">
            Read the argument →
          </a>
        </div>
      ) : (
        <div>
          <SideHeading>The case</SideHeading>
          <p className="mt-0.5 text-meta text-faint">
            Nothing written yet on why this project is worth the time.{' '}
            <a href={`#/argument/${encodeURIComponent(c.node.id)}`}
              className="text-accent hover:underline">Start it →</a>
          </p>
        </div>
      )}
    </div>
  )
}

/* What the code shows about itself. Every panel here is derived from the tree, so
   it is never empty for a repo that exists — which matters because the declared
   artifacts it used to rely on (architecture notes, changelogs, ADRs, backlogs)
   exist in 3, 4, 3 and 1 of nineteen projects. */
function Orient({ pid }) {
  const [s, setS] = useState(null)
  const [sErr, setSErr] = useState(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    setS(null); setSErr(null)
    fetch(`/api/projects/${encodeURIComponent(pid)}/survey`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setS).catch(e => setSErr(e.message))
  }, [pid])

  if (sErr) return <ErrorState title="Could not read the repo" detail={sErr} />
  if (!s) return <Loading label="Reading the tree" />
  const shape = s.shape
  if (!shape) return <p className="text-body text-faint">Nothing readable on disk.</p>

  const widest = Math.max(1, ...(s.layout || []).map(g => g.lines))
  return (
    <div className="space-y-6">
      <Purpose pid={pid} />

      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-body">
        <span><b>{num(shape.lines)}</b> <span className="text-faint">lines</span></span>
        <span><b>{num(shape.files)}</b> <span className="text-faint">files</span></span>
        {shape.primary && <span className="text-faint">mostly <b className="text-dim">{shape.primary}</b></span>}
        <span className={shape.test_files ? 'text-faint' : 'text-warn'}>
          {shape.test_files
            ? <>{shape.test_files} test files · {Math.round(shape.test_ratio * 100)}% of lines</>
            : 'no tests'}
        </span>
      </div>

      {/* Where it actually lives. The header shows the path in passing; orient is
          where you go to find the thing, so it gets a line you can copy. */}
      {s.path && (
        <div>
          <SideHeading>On disk</SideHeading>
          <button
            onClick={() => navigator.clipboard?.writeText(s.path).then(
              () => setCopied(true)).then(() => setTimeout(() => setCopied(false), 1200))}
            title="copy the path"
            className="fleet-btn fleet-btn-sm flex w-full items-center gap-2 text-left">
            <code className="min-w-0 flex-1 truncate text-dim">{s.path}</code>
            <span className="shrink-0 text-micro text-faint">
              {copied ? 'copied' : 'copy'}
            </span>
          </button>
        </div>
      )}

      {s.layout?.length > 0 && (
        <div>
          <SideHeading>Layout</SideHeading>
          <div className="space-y-1">
            {s.layout.map(g => (
              <div key={g.name} className="flex items-center gap-3 text-meta">
                <code className="w-40 shrink-0 truncate text-dim">{g.name}</code>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-ok/60"
                    style={{ width: `${Math.max(2, (g.lines / widest) * 100)}%` }} />
                </div>
                <span className="w-24 shrink-0 text-right tabular-nums text-faint">
                  {num(g.lines)} · {g.primary || '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Layout says where the weight sits; churn says where the attention went. A
          big directory nobody has touched in a quarter and a small one rewritten
          last week are the two things worth telling apart on return. */}
      {s.churn?.length > 0 && (
        <div>
          <SideHeading>Moving lately</SideHeading>
          <div className="space-y-1">
            {s.churn.map(c => (
              <div key={c.name} className="flex items-center gap-3 text-meta">
                <code className="w-40 shrink-0 truncate text-dim">{c.name}</code>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-ok/50"
                    style={{ width: `${Math.max(2, (c.commits / s.churn[0].commits) * 100)}%` }} />
                </div>
                <span className="w-24 shrink-0 text-right tabular-nums text-faint">
                  {c.commits} commit{c.commits === 1 ? '' : 's'}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-micro text-faint">last 90 days</p>
        </div>
      )}

      {s.start_here?.length > 0 && (
        <div>
          <SideHeading>Start reading here</SideHeading>
          <div className="space-y-1">
            {s.start_here.map(e => (
              <div key={e.file} className="flex items-baseline gap-3 text-meta">
                <code className="min-w-0 flex-1 truncate text-dim"
                  title={e.file}>{e.file}</code>
                <span className="shrink-0 tabular-nums text-faint">
                  imported by {e.imported_by}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {Object.keys(s.dependencies || {}).length > 0 && (
        <div>
          <SideHeading>Leans on</SideHeading>
          {Object.entries(s.dependencies).map(([eco, d]) => (
            <div key={eco} className="mb-2">
              <p className="mb-1 text-micro text-faint">
                {eco} · {d.count}
              </p>
              <div className="flex flex-wrap gap-1">
                {d.names.map(n => (
                  <span key={n} className="rounded px-1.5 py-0.5 text-micro bg-surface-2 text-faint">{n}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ---------- recent work ---------- */

/* Replaces a tab that read a per-repo backlog. One of nineteen repos had one, so
   it read zero almost everywhere. Git knows what happened without being told. */
function Recent({ pid }) {
  const [w, setW] = useState(null)
  const [wErr, setWErr] = useState(null)
  useEffect(() => {
    setW(null); setWErr(null)
    fetch(`/api/projects/${encodeURIComponent(pid)}/recent`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setW).catch(e => setWErr(e.message))
  }, [pid])

  if (wErr) return <ErrorState title="Could not read recent work" detail={wErr} />
  if (!w) return <Loading />

  return (
    <div className="space-y-6">
      <div>
        <SideHeading>
          {w.span ? `Since ${w.span}` : 'Recent commits'}
        </SideHeading>
        {w.commits?.length ? (
          <div className="divide-y divide-border">
            {w.commits.map(c => (
              <div key={c.sha} className="flex items-baseline gap-3 py-1.5 text-meta">
                <code className="shrink-0 text-faint">{c.sha}</code>
                <span className="min-w-0 flex-1 truncate text-dim"
                  title={c.subject}>{c.subject}</span>
                <span className="shrink-0 tabular-nums text-faint">{c.date}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-meta text-faint">
            Nothing since the last release — the tag and the code agree.
          </p>
        )}
      </div>

      <div>
        <SideHeading>Working tree</SideHeading>
        {w.dirty?.length ? (
          <div className="space-y-0.5">
            {w.dirty.map(d => (
              <div key={d.file} className="flex items-baseline gap-2 text-meta">
                <code className="w-6 shrink-0 text-warn">{d.state}</code>
                <code className="truncate text-faint">{d.file}</code>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-meta text-ok">Clean.</p>
        )}
      </div>
    </div>
  )
}

/* ---------- cycles ---------- */

const WEIGHT = {
  super: ['super-cycle', 'text-ok'],
  sub: ['sub-cycle', 'text-dim'],
  light: ['light', 'text-faint'],
  first: ['first', 'text-faint'],
}

/* Under Development Protocol 1.0 a cycle is atomic: it passes plan-build-test-review
   and cuts a version, or it cuts nothing. The tags already are the history, so this
   only joins them to what each produced and what was learned. Nothing here grades —
   the protocol is the owner's, and a tool that failed cycles on his behalf would be
   inventing authority it was never given. */
function Cycles({ pid }) {
  const [c, setC] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    fetch(`/api/projects/${encodeURIComponent(pid)}/cycles`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setC).catch(e => setErr(e.message))
  }, [pid])
  useEffect(() => { setC(null); setErr(null); load() }, [pid, load])

  const mirror = () => {
    setBusy(true); setErr(null)
    fetch(`/api/projects/${encodeURIComponent(pid)}/cycles/mirror`, { method: 'POST' })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(load)
      .catch(e => setErr(e.message))
      .finally(() => setBusy(false))
  }

  if (err) return <ErrorState title="Could not read cycles" detail={err} />
  if (!c) return <Loading />
  const counts = c.counts || {}

  return (
    <div className="space-y-6">
      {c.open && (
        <div className="rounded-card border border-warn/40 bg-warn/5 px-3 py-2">
          <p className="text-meta text-warn">
            <b>{c.open.commits} commit{c.open.commits === 1 ? '' : 's'}</b> since{' '}
            <code>{c.open.since || 'the beginning'}</code>, with no version cut.
          </p>
          <p className="mt-1 text-micro text-faint">
            A cycle is atomic — it cuts a version or it cuts nothing. No version, no credit.
          </p>
        </div>
      )}

      {/* Planned cycles sit above the cut ones because they are the present tense,
          and outside the `cycles.length` branch because a project can have a plan
          before it has ever tagged anything — which is exactly the state opening a
          first cycle creates.

          This pairs with the open-commits warning above: that one is work with no
          name, this one is a name with no tag. Both are "in flight", and a cycle
          wants to end up as neither. */}
      {c.planned?.length > 0 && (
        <div>
          <SideHeading>Planned · {c.planned.length}</SideHeading>
          <div className="divide-y divide-border">
            {c.planned.map(x => (
              <div key={x.version} className="flex items-baseline gap-3 py-2 text-meta">
                <code className="w-16 shrink-0 font-mono text-dim">v{x.version}</code>
                <span className="w-20 shrink-0 text-micro text-warn">open</span>
                <span className="min-w-0 flex-1 truncate text-faint"
                  title={x.path}>{x.title}</span>
                <span className="shrink-0 text-micro text-faint">
                  not cut
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-micro text-faint">
            A record with no tag behind it. Tagging the version is what closes the
            cycle — there is nothing here to mark done.
          </p>
        </div>
      )}

      {c.cycles?.length > 0 ? (
        <div>
          <SideHeading>
            Cut · {counts.cut}
            {counts.recorded < counts.cut && (
              <span className="ml-2 font-normal normal-case tracking-normal text-warn">
                {counts.cut - counts.recorded} without a record
              </span>
            )}
          </SideHeading>
          <div className="divide-y divide-border">
            {c.cycles.map(x => {
              const [label, tone] = WEIGHT[x.weight] || WEIGHT.light
              return (
                <div key={x.tag} className="flex items-baseline gap-3 py-2 text-meta">
                  <code className="w-16 shrink-0 text-dim">{x.tag}</code>
                  <span className={`w-20 shrink-0 text-micro ${tone}`}>{label}</span>
                  <span className="min-w-0 flex-1 truncate text-faint"
                    title={x.record ? x.record.path : 'no cycle record'}>
                    {x.record
                      ? x.record.title
                      : <span className="text-faint">no record</span>}
                  </span>
                  {!x.logged && (
                    <span className="shrink-0 text-micro text-warn">unlogged</span>
                  )}
                  <span className="shrink-0 tabular-nums text-faint">
                    {x.date}
                  </span>
                </div>
              )
            })}
          </div>
          {c.records_dir && (
            <p className="mt-2 text-micro text-faint">
              records read from <code>{c.records_dir}</code>
            </p>
          )}

          {/* The vault is the source; the repo keeps a copy so the record of
              finished work survives a clone, the way docs/chart.md mirrors a chart
              that lives in gitignored sqlite. */}
          {c.mirror?.total > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3 text-micro
               border-border">
              {c.mirror.behind > 0 ? (
                <>
                  <span className="text-warn">
                    {c.mirror.behind} of {c.mirror.total} not mirrored into{' '}
                    <code>{c.mirror.dir}</code>
                  </span>
                  <button onClick={mirror} disabled={busy}
                    className="fleet-btn fleet-btn-sm disabled:opacity-40">
                    {busy ? 'copying…' : 'mirror to the repo'}
                  </button>
                </>
              ) : (
                <span className="text-ok">
                  all {c.mirror.total} mirrored into <code>{c.mirror.dir}</code>
                </span>
              )}
            </div>
          )}

          {err && <p className="mt-2 text-micro text-danger">{err}</p>}
        </div>
      ) : (
        <p className="text-body leading-relaxed text-faint">
          No versions cut yet. A cycle ends with a changelog entry, a tag and a retro —
          until one is tagged, there is nothing finished to show.
        </p>
      )}
    </div>
  )
}

/* ---------- decisions ---------- */

function Decisions({ pid }) {
  const [items, setItems] = useState(null)
  const [dErr, setDErr] = useState(null)
  useEffect(() => {
    fetch(`/api/projects/${encodeURIComponent(pid)}/decisions`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(b => setItems(b.decisions || []))
      .catch(e => setDErr(e.message))
  }, [pid])

  if (dErr) return <ErrorState title="Could not read decisions" detail={dErr} />
  if (!items) return <Loading />
  if (!items.length) {
    return (
      <p className="text-body leading-relaxed text-faint">
        No ADRs yet. A decision record is worth writing when a choice closes off
        alternatives someone would otherwise reopen — put them in <code>docs/adr/</code>.
      </p>
    )
  }
  return (
    <div className="divide-y divide-border">
      {items.map(d => (
        <a key={d.path} href="#"
          onClick={e => {
            e.preventDefault()
            window.location.hash =
              `#/doc/${encodeURIComponent(pid)}/${encodeURIComponent(d.path)}`
          }}
          className="block py-2.5 transition hover:text-accent">
          <div className="text-body">{d.title}</div>
          <code className="text-micro text-faint">{d.name}</code>
        </a>
      ))}
    </div>
  )
}


/* ---------- one problem's cycles, in the drawer ---------- */

/* Which cycle addressed this problem, and starting the next one.
 *
 * This was the outline's, and it is the one thing on that surface the canvas has no
 * answer for: a graph draws structure, and "v0.27.0 ran against this node" is not
 * structure. So it moved into the drawer rather than going with the rows — the
 * project page is where a cycle is opened, and losing that to a layout change would
 * have been a deletion disguised as a refactor.
 *
 * Everything it needs comes from `/api/problems/<id>/cycle-options`: the tags that
 * exist, which are already linked, and the version this problem's ROLE proposes —
 * leaf PATCH, branch MINOR, bearing MAJOR. Proposed, never imposed: the field stays
 * editable, because the bump is a claim about scope and only the author can make it. */
function CycleSection({ pid, onChanged }) {
  const [opts, setOpts] = useState(null)
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [version, setVersion] = useState('')
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    setErr(null)
    fetch(`/api/problems/${encodeURIComponent(pid)}/cycle-options`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => { setOpts(d); setVersion(v => v || d.proposed || '') })
      .catch(e => setErr(e.message))
  }, [pid])
  useEffect(() => { setOpts(null); setOpen(false); setTitle(''); setVersion(''); load() }, [load])

  const after = () => { load(); onChanged?.() }
  const send = (url, opt) =>
    fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opt })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(after)
      .catch(e => setErr(e.message))

  const link = v => send(`/api/problems/${encodeURIComponent(pid)}/cycles`,
    { method: 'POST', body: JSON.stringify({ version: v }) })
  const unlink = v => send(
    `/api/problems/${encodeURIComponent(pid)}/cycles/${encodeURIComponent(v)}`,
    { method: 'DELETE' })
  const start = () => {
    const body = { version: version.trim(), title: title.trim() }
    if (opts?.repos?.length === 1) body.repo = opts.repos[0]
    send(`/api/problems/${encodeURIComponent(pid)}/cycles/open`,
      { method: 'POST', body: JSON.stringify(body) })
      .then(() => { setOpen(false); setTitle('') })
  }

  if (!opts) return null
  const linked = opts.linked || []
  const unlinked = (opts.options || []).filter(o => !o.linked)

  return (
    <div className="mt-5 border-t pt-4 border-border">
      <p className="fleet-label">Addressed by</p>

      {/* "Addressed by", never "solved by" — whether it worked is a separate
          judgement, so three cycles beside an unsolved problem reads as effort with
          nothing to show for it, which is the state worth seeing. */}
      {linked.length === 0 ? (
        <p className="mt-1.5 text-micro text-faint">No cycle has run against this yet.</p>
      ) : (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {linked.map(v => {
            const inFlight = (opts.open || []).includes(v)
            return (
              <button key={v} onClick={() => unlink(v)}
                title={inFlight
                  ? `v${v} is open — planned, not yet cut. Click to unlink.`
                  : `v${v} ran against this — click to unlink`}
                className={`rounded px-1.5 py-0.5 font-mono text-micro ring-1 ring-inset
                  transition hover:text-danger hover:ring-danger/40 ${inFlight
                    ? 'text-accent ring-accent/40'
                    : 'text-faint ring-zinc-700'}`}>
                v{v}{inFlight && ' ·open'}
              </button>
            )
          })}
        </div>
      )}

      {unlinked.length > 0 && (
        <div className="mt-2">
          <p className="text-micro text-faint">already cut — record after the fact</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {unlinked.slice(0, 8).map(o => (
              <button key={`${o.repo}-${o.version}`} onClick={() => link(o.version)}
                title={`${o.repo} · ${o.date || 'undated'}`}
                className="fleet-btn fleet-btn-sm font-mono">
                {o.version}
              </button>
            ))}
          </div>
        </div>
      )}

      {opts.repos?.length === 0 ? (
        <p className="mt-2 text-micro text-faint">
          No repo beneath this problem — a cycle cuts a version, and there is none to cut.
        </p>
      ) : open ? (
        <div className="mt-2">
          <p className="text-micro text-faint">
            {opts.role} · {opts.bump}
            {opts.composition?.children > 0 && (
              <> · {opts.composition.with_cycles}/{opts.composition.children} children have cycles</>
            )}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <input value={version} onChange={e => setVersion(e.target.value)} placeholder="v0.1.0"
              className="w-24 rounded border bg-transparent px-1.5 py-0.5 font-mono text-micro
                  focus:border-accent border-zinc-700" />
            <input value={title} onChange={e => setTitle(e.target.value)} autoFocus
              placeholder="what this cycle is called"
              onKeyDown={e => { if (e.key === 'Enter' && title.trim() && version.trim()) start() }}
              className="min-w-0 flex-1 rounded border bg-transparent px-1.5 py-0.5 text-micro
                  focus:border-accent border-zinc-700" />
          </div>
          {opts.repos?.length > 1 && (
            <p className="mt-1 text-micro text-warn">
              {opts.repos.join(' and ')} both sit beneath this — name the repo before starting.
            </p>
          )}
          <div className="mt-1.5 flex items-center gap-2">
            <button onClick={start} disabled={!title.trim() || !version.trim()}
              className="rounded bg-accent px-2 py-0.5 text-micro text-white disabled:opacity-40">
              Start
            </button>
            <button onClick={() => setOpen(false)} className="text-micro text-faint">cancel</button>
          </div>
        </div>
      ) : (
        <button onClick={() => setOpen(true)}
          className="mt-2 text-micro text-accent hover:underline">
          start a cycle against this…
        </button>
      )}

      {err && <p className="mt-1.5 text-micro text-danger">{err}</p>}
    </div>
  )
}

const TABS = [
  { value: 'orient', label: 'Orient' },
  { value: 'chart', label: 'Problem Chart' },
  { value: 'work', label: 'Work' },
  { value: 'cycles', label: 'Cycles' },
  { value: 'decisions', label: 'Decisions' },
]

export function ProjectPage({ pid, onClose, onChanged }) {
  const [p, setP] = useState(null)
  const [err, setErr] = useState(null)
  const [view, setView] = useState('orient')
  // Whatever the chart's own rail could not report. It lives up here rather than in
  // the rail because the rail is unmounted by the very actions that can fail — a
  // delete closes the drawer — and an error message that dies with its cause is a
  // silent failure.
  const [chartErr, setChartErr] = useState(null)
  // The old version had no `.catch`: a failed load left "loading…" on screen
  // forever, which reads as a slow page rather than a broken one.
  const load = useCallback(() => {
    setErr(null)
    fetch(`/api/projects/${pid}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setP)
      .catch(e => setErr(e.message))
  }, [pid])
  useEffect(load, [load])

  // Clear on the way in, not just on the way back. Without this the previous
  // project stayed on screen for the whole of the next one's fetch — about a
  // second, since the project view shells out to git — and every panel described
  // the wrong repo. That was survivable while the panels were static facts; it
  // stopped being survivable once orient started reporting a cycle in flight,
  // because a stale reading there says work is running on a project where none is.
  useEffect(() => { setP(null) }, [pid])

  useEffect(() => {
    const onKey = e => {
      if (e.key === 'Escape' && !/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const links = p?.links || {}

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      {err ? (
          <ErrorState title="Could not read this project"
            detail={`${err} — the scan shells out to git, so a repo that has just moved or lost its manifest will do this.`}
            onRetry={load} />
        ) : !p ? (
          <Loading label="Reading the repo" />
        ) : (
          <>
            <button onClick={onClose}
              className="mb-4 text-meta text-faint transition hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
              ← all projects
            </button>
            <header className="flex items-start justify-between gap-4 border-b pb-5 border-border">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-page font-semibold tracking-tight text-balance">
                    {p.name || p.id}
                  </h2>
                  <CycleChip cycles={p.cycles} />
                </div>
                {p.description && (
                  <p className="mt-1.5 max-w-[68ch] text-body text-faint">
                    {p.description}
                  </p>
                )}
                {/* Path is a machine fact and reads as one. */}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Mono>{p.path}</Mono>
                  <span className={`text-meta ${activityTone(p.last_activity)}`}>
                    · {relTime(p.last_activity)}
                  </span>
                </div>
                <StateStrip pid={p.id} version={p.version} changelog={p.changelog}
                  behind={p.running_behind} />
              </div>
            </header>

            {/* minmax(0,…) and min-w-0, both deliberate: a grid item defaults to
                min-width:auto, so it refuses to shrink below its content's
                min-content width. The chart tab's rows carry a fixed-width title
                cell, which made this column blow out past the viewport and put a
                horizontal scrollbar on the whole page. minmax fixes the track at
                lg+; min-w-0 fixes the item at every width. */}
            {/* The chart drops the sidebar and takes the whole column, for the same
                reason the Chart tab is the one page that runs full-bleed: the rows
                are a fixed-width title against a waypoint that has to stay readable,
                and at 1.6fr the waypoint collapsed to ~99px. Every other tab keeps
                the two-column layout. */}
            <div className={view === 'chart'
              ? 'py-6'
              : 'grid gap-10 py-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]'}>
              <div className="min-w-0">
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <Tabs tabs={TABS} value={view} onChange={setView} label="Project view" />
                </div>

                {view === 'orient' && <Orient pid={p.id} />}

                {/* One drawing of the chart, not two. The outline and the canvas were
                    the same subtree rendered twice, and the pair of them meant every
                    per-node action had to be written on both or exist on one — which
                    is how "you can add a problem here but not rename it" happened.
                    The canvas keeps the structure; the rail keeps the authoring. */}
                {view === 'chart' && (
                  <>
                    {chartErr && (
                      <p className="mb-3 rounded-card border border-danger/40 bg-danger/5 px-3
                        py-2 text-meta text-danger">
                        {chartErr}
                        <button onClick={() => setChartErr(null)} className="ml-2 underline">
                          dismiss
                        </button>
                      </p>
                    )}
                    <Boundary label="The graph">
                      <GraphPage embedded root={p.id} onCreated={load}
                        emptyDetail={'Nothing charted for this project yet — no record of why it exists. '
                          + 'A repo enters the chart by being attached to a problem, which happens on the Goals page.'}
                        rail={(node, api) => (
                          <>
                            <GoalRail embedded row={node}
                              onAddChild={api.addChild}
                              onChanged={() => { api.reload(); load() }}
                              onDeleted={() => { api.close(); load() }}
                              onError={setChartErr}
                              // There is no goal window on this page, and the essay is
                              // what that button was reaching for anyway.
                              onOpenWindow={r => {
                                window.location.hash = `#/argument/${encodeURIComponent(r.id)}`
                              }} />
                            <CycleSection pid={node.id} onChanged={() => { api.reload(); load() }} />
                          </>
                        )} />
                    </Boundary>
                  </>
                )}

                {view === 'work' && <Recent pid={p.id} />}

                {view === 'cycles' && <Cycles pid={p.id} />}

                {view === 'decisions' && <Decisions pid={p.id} />}
              </div>

              {view !== 'chart' && (
              <aside>
                <div className="mb-5"><Heatmap pid={p.id} /></div>

                {/* Reading material and running things answer different questions,
                    so they stop being one undifferentiated list of links. */}
                <SideHeading>Documentation</SideHeading>
                <Documents pid={p.id} documents={p.documents}
                  onDecisions={() => setView('decisions')} />

                {p.mc_info?.length > 0 && (
                  <>
                    <SideHeading>Running</SideHeading>
                    {p.mc_info.map(m => {
                      const up = (m.status || '').toLowerCase().includes('run') || m.health === true
                      return (
                        <div key={m.id} className="flex items-center gap-2 py-1">
                          <Status state={up ? 'running' : 'stopped'}>{m.name}</Status>
                          {m.ports?.length > 0 && <Mono>:{m.ports.join(' :')}</Mono>}
                        </div>
                      )
                    })}
                  </>
                )}

                <SideHeading>Links</SideHeading>
                <LinkRow label="app" href={links.app} />
                <LinkRow label="github" href={links.github} />
                {links.extra && Object.entries(links.extra).map(([k, v]) =>
                  <LinkRow key={k} label={k} href={v} />)}

                {/* This block and the one below had drifted out to top-level
                    indentation inside the rail — a bad paste that rendered fine
                    and read as broken source. */}
                {(p.also_serves?.length > 0 || p.child_count > 0) && (
                  <>
                    <SideHeading>Beneath</SideHeading>
                    <div className="flex flex-wrap gap-x-3 text-meta text-faint">
                      {p.child_count > 0 && <span>{p.child_count} below</span>}
                      {p.also_serves?.length > 0 && (
                        <span title={p.also_serves.join(', ')}>
                          also serves {p.also_serves.length} other bearing
                          {p.also_serves.length > 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                  </>
                )}

                {p.tags?.length > 0 && (
                  <>
                    <SideHeading>Tags</SideHeading>
                    <div className="flex flex-wrap gap-1.5">
                      {p.tags.map(t => (
                        <span key={t} className="rounded-md px-2 py-0.5 text-micro bg-surface-2 text-faint">{t}</span>
                      ))}
                    </div>
                  </>
                )}
              </aside>
              )}
            </div>
          </>
        )}
    </div>
  )
}
