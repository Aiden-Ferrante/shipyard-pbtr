import React, { useEffect, useState, useCallback } from 'react'
import { FLEET_APPS, appUrl } from './vendor/fleet-ui/apps.js'
import { ArgumentPage } from './argument'
import { Board } from './board'
import { DocPage } from './doc'
import { GoalsPage } from './goals'
import { StandardsPage, DocsPage } from './manual'
import { FleetPage } from './fleet'
import { CommandPalette } from './palette'
import { ProjectPage } from './project'
import { ProblemPage } from './problem'


/* Routing and chrome, nothing else. The URL is the source of truth for which
   surface is showing, so browser back works and anything can be linked to. */
export default function App() {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)
  const [palette, setPalette] = useState(false)
  const [goals, setGoals] = useState(false)
  const [yard, setYard] = useState(false)
  const [argument, setArgument] = useState(null)
  const [problem, setProblem] = useState(null)
  const [doc, setDoc] = useState(null)
  const [manual, setManual] = useState(null)   // 'standards' | 'docs'

  const load = useCallback(() => {
    fetch('/api/projects').then(r => r.json()).then(setData)
  }, [])
  useEffect(load, [load])

  // The URL is the source of truth for which project is open, so browser back
  // works and a project can be linked to. `open` just mirrors the hash.
  useEffect(() => {
    const sync = () => {
      const h = window.location.hash
      // #/fleet was this page's name until the tab became Yard. A stale
      // bookmark landing silently on the board is indistinguishable from a
      // broken link, so forward it. replace(), not assign: the dead route must
      // not sit in history where Back would walk straight back into it.
      if (h === '#/fleet') { window.location.replace('#/yard'); return }
      // startsWith, not ===, so #/goals?node=<id> still matches: the goal
      // inspector keeps its selection in the URL rather than in component state.
      setGoals(h === '#/goals' || h.startsWith('#/goals?'))
      setYard(h === '#/yard')
      // The Yard's own tabs. Separate pages rather than sections because the Yard
      // shows the queue, the gate and receiving and nothing else — see v0.31.0.
      setManual(h === '#/standards' ? 'standards' : h === '#/docs' ? 'docs' : null)
      const a = h.match(/^#\/argument\/(.+)$/)
      setArgument(a ? decodeURIComponent(a[1]) : null)
      // #/doc/<project>/<repo-relative path> — the path is encoded, so its own
      // slashes survive and the match stays unambiguous.
      const d = h.match(/^#\/doc\/([^/]+)\/(.+)$/)
      setDoc(d ? { pid: decodeURIComponent(d[1]), path: decodeURIComponent(d[2]) } : null)
      // #/problem/<id> — a problem's own page. Matched before #/project so the
      // two prefixes cannot shadow each other as more routes are added.
      const pr = h.match(/^#\/problem\/(.+)$/)
      setProblem(pr ? decodeURIComponent(pr[1]) : null)
      const m = h.match(/^#\/project\/(.+)$/)
      setOpen(m ? decodeURIComponent(m[1]) : null)
    }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  const openProject = id => { window.location.hash = `#/project/${encodeURIComponent(id)}` }
  const closeProject = () => {
    if (window.history.length > 1) window.history.back()
    else window.location.hash = ''
  }

  useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault(); setPalette(v => !v)
      }
      // Bare "/" is the other convention for search; ignore it while typing.
      if (e.key === '/' && !/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) {
        e.preventDefault(); setPalette(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const projects = data?.projects ?? []
  /* The header used to lead with "N quiet >14d" in alarm yellow — a nag that
     fires on fourteen of twenty projects and that you cannot act on directly.
     It reports coverage instead: how much of the fleet answers to a problem at
     all. It briefly reported evidence quality too ("N/M above assumed"); that
     went with the rest of the sounding UI. */
  const charted = projects.filter(p => p.sounding)

  return (
    <div className="min-h-screen bg-bg text-ink">
      <header className="fleet-header">
        <div className={`mx-auto px-6 ${goals ? '' : 'max-w-6xl'}`}>
          {/* Tier one: which app you are in. The list is src/vendor/fleet-ui/apps.js. */}
          <nav className="fleet-apps" aria-label="Fleet">
            <p className="fleet-wordmark">fleet</p>
            {FLEET_APPS.map(a => a.id === 'shipyard' ? (
              <span key={a.id} className="fleet-app" aria-current="page">{a.label}</span>
            ) : (
              <a key={a.id} className="fleet-app" href={appUrl(a)} title={a.blurb}>{a.label}</a>
            ))}
          </nav>

          {/* Tier two: shipyard's own surfaces, and the one control that is its
              alone. The header tracks the page under it — the chart runs
              full-bleed, and a nav stopping at 72rem over a chart reaching the
              edge read as a misalignment rather than a choice. */}
          <div className="fleet-sections">
            <h1 className="fleet-brand">Shipyard</h1>
            {data && (
              <p className="fleet-sub">
                {projects.length} projects · {charted.length} charted
              </p>
            )}
            <nav className="fleet-nav ml-6" aria-label="Sections">
              {/* Yard leads, then Projects, then the chart — widest lens first,
                  narrowing left to right. Note the order is presentational only:
                  Projects is still the no-hash landing view, so the first tab is
                  deliberately not the page you open on. Making them agree means
                  giving Projects its own hash and rewriting what a bare URL
                  means, which is a routing change, not a reorder. */}
              {[['#/yard', 'Yard'], ['', 'Projects'], ['#/goals', 'Long Term Goal Chart']].map(([href, label]) => {
                const active = href
                  ? window.location.hash === href
                  : !goals && !yard && !open && !argument && !problem && !doc
                return (
                  <a key={label} href={href || '#'}
                    aria-current={active ? 'page' : undefined}
                    onClick={e => { if (!href) { e.preventDefault(); window.location.hash = '' } }}
                    className={active ? 'active' : undefined}>
                    {label}
                  </a>
                )
              })}
            </nav>
            <div className="fleet-actions">
              <button
                onClick={() => setPalette(true)}
                className="fleet-btn fleet-btn-sm flex items-center gap-2"
              >
                Jump to…
                <kbd className="rounded border px-1 font-sans text-micro border-zinc-700">⌘K</kbd>
              </button>
            </div>
          </div>
        </div>
      </header>

      {doc ? (
        // history.back(), not a fixed destination: a document is reachable from a
        // project card and now from the manual too, and sending both to the project
        // page strands whoever came from the other. Same call as ProblemPage.
        <DocPage pid={doc.pid} path={doc.path}
          onClose={() => window.history.back()} />
      ) : argument ? (
        <ArgumentPage pid={argument} onClose={() => { window.location.hash = '#/goals' }} />
      ) : problem ? (
        // history.back() rather than a fixed destination: a problem is reachable
        // from the chart outline, the graph and a project's own tab, and sending
        // every one of them to the same page would strand two of the three.
        <ProblemPage pid={problem} onClose={() => window.history.back()} />
      ) : goals ? (
        <GoalsPage onClose={closeProject} />
      ) : open ? (
        <ProjectPage pid={open} onClose={closeProject} onChanged={load} />
      ) : manual === 'standards' ? (
        <StandardsPage />
      ) : manual === 'docs' ? (
        <DocsPage
          onOpenDoc={path => { window.location.hash = `#/doc/shipyard/${encodeURIComponent(path)}` }}
          onDecisions={() => openProject('shipyard')} />
      ) : yard ? (
        <FleetPage onOpen={openProject} />
      ) : (
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Board onOpen={openProject} onChanged={load} />
        </main>
      )}
      {palette && (
        <CommandPalette
          projects={projects}
          onPick={id => { setPalette(false); openProject(id) }}
          onClose={() => setPalette(false)}
        />
      )}
    </div>
  )
}
