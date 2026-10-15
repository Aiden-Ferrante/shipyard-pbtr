import React, { useEffect, useState } from 'react'
import {
  PageHeader, SectionHeading, Chip, Mono, Loading, ErrorState, EmptyState,
} from './ui'
import { PageTabs } from './fleet'

/* The manual — two pages that were always in the app and never reachable.
 *
 * Shipyard reports every other repo's missing README from a page that had no way
 * to show its own. Both surfaces here are reads of endpoints that already existed:
 * `/api/conventions` has answered "what has teeth" since v0.28.0, and the document
 * list has been on every project card since v0.11.0. Neither needed building —
 * both needed a door.
 *
 * They are pages rather than bands because of the Yard's own waypoint: that page
 * shows the queue, the gate and receiving, and NOTHING else. Standards sat below
 * all of it in a collapsed section, which is where a convention goes to be
 * indistinguishable from one that does not exist.
 *
 * Read-only, both of them. A standard's home is the repo that enforces it and a
 * document's home is the repo that wrote it; showing them without offering to edit
 * is the same boundary `doc.jsx` already draws. */

/* Shipyard's own manifest id. Hardcoded deliberately: this page is not "a project's
   docs" — the project card already does that for any repo — it is *this app's*
   manual, and parameterising it would invite a second, worse project page. */
const SELF = 'shipyard'

export function StandardsPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/conventions')
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch(e => setError(e.message))
  }, [])

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <PageTabs />

      <PageHeader title="Standards">
        {data && (
          <>
            {data.enforced} of {data.standards.length} have teeth. What this fleet runs
            on {'—'} never whether a repo complies. Read from disk on every load: a
            template or an ADR added to a repo shows up here without an edit.
          </>
        )}
      </PageHeader>

      {error ? (
        <ErrorState title="Could not read the standards" detail={error} />
      ) : !data ? (
        <Loading label="Reading the standards" />
      ) : !data.standards?.length ? (
        <EmptyState title="No standards declared"
          detail="Nothing in conventions.py — which is itself a finding, not an empty page." />
      ) : (
        <>
          <SectionHeading aside="the enforcer column is the point — a rule you believe is holding and nothing checks has already drifted">
            The rules
          </SectionHeading>
          <div className="mt-2 flex flex-col gap-2">
            {data.standards.map(s => (
              <div key={s.id}
                className="rounded-card border px-4 py-3 border-border">
                <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                  <span className="text-title font-semibold tracking-tight">{s.title}</span>
                  {s.enforcer
                    ? <Chip tone={s.enforcer_present === false ? 'danger' : 'ok'} mono>
                      {s.enforcer_present === false ? `${s.enforcer} — missing` : s.enforcer}
                    </Chip>
                    : <Chip>prose only</Chip>}
                  {s.where && (
                    <Mono>{s.where}{s.present === false ? ' — not found' : ''}</Mono>
                  )}
                </div>
                <p className="mt-1.5 text-meta leading-relaxed text-dim">
                  {s.what}
                </p>
                {s.note && (
                  <p className="mt-1.5 text-micro leading-relaxed text-faint">
                    {s.note}
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="mt-4 text-micro leading-relaxed text-faint">
            Not <Mono>standards.yaml</Mono>, which was deleted in v0.5.0 for scoring repos
            against a checklist when conformance was never the point. Nothing on this page
            reads a repo. The failure it exists to catch is a convention that was converged
            by hand, drifted back within days, and had no script that would have said so.
          </p>
        </>
      )}
    </main>
  )
}

/* What shipyard is for, and its own documents — the same ones the project card
   lists, opened through the same reader, so there is one rendering of a document
   and not two that can disagree. */
export function DocsPage({ onOpenDoc, onDecisions }) {
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`/api/projects/${SELF}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(d => setDocs(d.documents || []))
      .catch(e => setError(e.message))
  }, [])

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <PageTabs />

      <PageHeader title="What shipyard is">
        One pleasant front end over the tools that already hold the truth. It reads and
        writes them, and owns no complex logic of its own.
      </PageHeader>

      <SectionHeading aside="the questions it answers, and the ones it deliberately refuses">
        The problem it solves
      </SectionHeading>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        {[
          ['Why does this repo exist?',
            'The chart — problems, each with an observable, and the repo that attacks it. This is the one thing shipyard owns; everything else it reads from where that thing already lives.'],
          ['What may I start next?',
            'The Yard. A thought waits in the queue until it has a waypoint, the gate says which repos could open a cycle today, and receiving is where a repo enters at all.'],
          ['What did I finish?',
            'Cycles, read off git tags. A record with no tag is open, a record with a tag is closed, and cutting the tag is what moves it — the state is read from disk rather than typed into.'],
          ['What is this repo made of?',
            'The project page: version, branch, debt, documents, decisions, and the chart rooted at the problem it attacks.'],
        ].map(([q, a]) => (
          <div key={q} className="rounded-card border px-4 py-3 border-border">
            <p className="text-meta font-semibold">{q}</p>
            <p className="mt-1 text-meta leading-relaxed text-dim">{a}</p>
          </div>
        ))}
      </div>

      <p className="mt-3 text-micro leading-relaxed text-faint">
        And what it is not: not a process supervisor (Mission Control answers <i>is it
        running</i>), not a task tracker (<Mono>Backlog.md</Mono>), not a study tracker
        (Learn Hub), not a compliance enforcer. When a feature would duplicate one of
        those, the answer is a read, not a table.
      </p>

      <div className="mt-8">
        <SectionHeading aside="shipyard's own repo, read in place — the same documents the project card lists">
          The documents
        </SectionHeading>
        {error ? (
          <ErrorState title="Could not read the documents" detail={error} />
        ) : !docs ? (
          <Loading label="Reading the documents" />
        ) : !docs.length ? (
          <EmptyState title="No documents"
            detail="No README, ARCHITECTURE or CHANGELOG found — which for this repo would be a bug." />
        ) : (
          <div className="mt-2 flex flex-col gap-1.5">
            {docs.map(d => d.kind === 'dir' ? (
              <button key={d.label} onClick={onDecisions}
                className="fleet-btn flex items-baseline gap-2 text-left text-accent">
                {d.label} <Mono>{d.count}</Mono>
              </button>
            ) : d.kind === 'url' ? (
              <a key={d.label} href={d.href} target="_blank" rel="noreferrer"
                className="flex items-baseline gap-2 rounded-lg border px-3 py-2 text-meta
                   text-accent transition hover:border-accent/60 border-border">
                {d.label} <span className="text-micro text-faint">↗</span>
              </a>
            ) : (
              <button key={d.label} onClick={() => onOpenDoc(d.path)}
                className="fleet-btn flex items-baseline gap-2 text-left text-accent">
                {d.label} <Mono>{d.path}</Mono>
              </button>
            ))}
          </div>
        )}
      </div>
    </main>
  )
}
