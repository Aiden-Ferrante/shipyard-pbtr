import React, { useEffect, useRef } from 'react'

/* The design system, as components — thin now.
 *
 * Since fleet.css v2 (2026-09-04) the visual vocabulary lives in the fleet's
 * class kit: .fleet-btn, .fleet-chip, .fleet-status, .fleet-table, .fleet-card,
 * .fleet-dialog / .fleet-drawer, .fleet-tabs, .fleet-kv, the three async states.
 * What is left here is the React wrapper each surface reaches for: props that
 * name a MEANING (tone, state) and emit the kit's class. `kit.jsx` still holds
 * shipyard's domain helpers — what "stale" means, how a date reads.
 *
 * Three rules the whole system rests on, unchanged:
 *   1. The accent is for INTERACTION ONLY. `ok`/`warn`/`danger` never borrow it.
 *   2. Status is SHAPE and colour, never colour alone (the kit's four glyphs).
 *   3. Machine facts are monospace; prose is not.
 */

/* ---------- page furniture ---------- */

export function PageHeader({ title, children, actions }) {
  return (
    <header className="mb-6 flex flex-wrap items-start gap-x-4 gap-y-2">
      <div className="min-w-0">
        <h1 className="text-page font-semibold tracking-tight text-balance">{title}</h1>
        {children && <p className="mt-1 max-w-[68ch] text-meta text-faint">{children}</p>}
      </div>
      {actions && <div className="ml-auto flex shrink-0 gap-2">{actions}</div>}
    </header>
  )
}

/* `aside` is pushed right and allowed to wrap: it is the sentence explaining
   what the section means, and it belongs at the far edge where it does not
   compete with the heading for the start of the line. */
export function SectionHeading({ children, aside }) {
  return (
    <div className="mb-2.5 mt-8 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border pb-1.5 first:mt-0">
      <h2 className="text-section font-semibold tracking-tight">{children}</h2>
      {aside && <span className="ml-auto max-w-[46ch] text-right text-meta text-faint">{aside}</span>}
    </div>
  )
}

/* A label for a rail section: the kit's label register. */
export function SideHeading({ children }) {
  return <h3 className="fleet-label mb-2 mt-6 first:mt-0">{children}</h3>
}

/* ---------- tabs ----------
   A real tablist: arrow keys move, Home/End jump, and the selected tab is
   announced. Drawn by .fleet-tabs. */

export function Tabs({ tabs, value, onChange, label = 'View' }) {
  const onKey = e => {
    const i = tabs.findIndex(t => (t.value ?? t) === value)
    const go = n => { e.preventDefault(); onChange(tabs[n].value ?? tabs[n]) }
    if (e.key === 'ArrowRight') go((i + 1) % tabs.length)
    if (e.key === 'ArrowLeft') go((i - 1 + tabs.length) % tabs.length)
    if (e.key === 'Home') go(0)
    if (e.key === 'End') go(tabs.length - 1)
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className="fleet-tabs">
      {tabs.map(t => {
        const v = t.value ?? t
        const on = v === value
        return (
          <button key={v} role="tab" aria-selected={on} tabIndex={on ? 0 : -1}
            onClick={() => onChange(v)} className="fleet-tab">
            {t.label ?? v}
            {t.count != null && <span className="ml-1.5 t-num text-faint">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

/* ---------- status: shape + colour ----------
   The kit's one renderer. Shipyard's states map onto its four tones. */

const TONE = { running: 'ok', stopped: 'off', unhealthy: 'warn', failed: 'danger', unknown: '' }
export const statusTone = state => TONE[state] ?? ''

export function StatusGlyph({ state = 'unknown' }) {
  return <span aria-hidden="true" className={`fleet-status ${statusTone(state)}`} />
}

export function Status({ state = 'unknown', children }) {
  return <span className={`fleet-status ${statusTone(state)}`}>{children ?? state}</span>
}

/* ---------- chip ---------- */

const CHIP = { quiet: '', ok: 'ok', warn: 'warn', danger: 'danger', accent: 'accent' }

export function Chip({ tone = 'quiet', mono = false, title, children }) {
  return (
    <span title={title} className={`fleet-chip ${CHIP[tone] ?? ''}${mono ? ' mono' : ''}`}>
      {children}
    </span>
  )
}

/* Machine facts. A port is not prose. */
export function Mono({ children, className = '' }) {
  return <span className={`font-mono text-micro text-faint ${className}`}>{children}</span>
}

/* ---------- table ----------
   Cards are for dashboards; tables are for work. What you scan DOWN A COLUMN
   belongs here; a group that holds a write or a handful of rows stays a card
   even though it is countable (fleet/CONVENTIONS.md §1). The wrap is the one
   legal sideways scroll on a phone. */

export function Table({ columns, children, empty }) {
  return (
    <div className="fleet-table-wrap">
      <table className="fleet-table">
        <thead>
          <tr>
            {columns.map(c => (
              <th key={c.key ?? c.label} style={c.width ? { width: c.width } : undefined}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {React.Children.count(children) === 0
            ? <tr><td colSpan={columns.length} className="py-8 text-center text-faint">{empty}</td></tr>
            : children}
        </tbody>
      </table>
    </div>
  )
}

export function Row({ onClick, selected, children }) {
  return (
    <tr
      onClick={onClick}
      tabIndex={onClick ? 0 : undefined}
      role={onClick ? 'button' : undefined}
      aria-selected={onClick ? !!selected : undefined}
      onKeyDown={e => {
        if (!onClick) return
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() }
      }}
      className={`${onClick ? 'cursor-pointer' : ''} ${selected ? 'bg-accent/10' : ''}`}
    >
      {children}
    </tr>
  )
}

export function Cell({ children, className = '' }) {
  return <td className={`align-middle ${className}`}>{children}</td>
}

/* ---------- the three states every async surface owes ---------- */

export function Loading({ label = 'Reading', inline = false }) {
  if (inline) return <span className="text-micro text-faint">{label} {'…'}</span>
  return <p className="fleet-loading my-3" role="status">{label} {'…'}</p>
}

export function ErrorState({ title, detail, onRetry }) {
  return (
    <div className="fleet-error my-3 flex-wrap" role="alert">
      <span className="fleet-chip danger">error</span>
      <span className="font-medium">{title}</span>
      {detail && <span className="text-dim">{detail}</span>}
      {onRetry && <Button className="ml-auto" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

/* An empty state that names the fix is the difference between a tool and a
   blank div — so `detail` is required, not decorative. */
export function EmptyState({ glyph = '◍', title, detail, actions }) {
  return (
    <div className="fleet-empty flex-col items-center px-6 py-10 text-center">
      <p className="font-mono text-section text-faint m-0">{glyph}</p>
      <p className="mt-2 text-title font-semibold text-ink m-0">{title}</p>
      <p className="mx-auto mt-1 max-w-[46ch] text-meta m-0">{detail}</p>
      {actions && <div className="mt-4 flex justify-center gap-2">{actions}</div>}
    </div>
  )
}

/* ---------- buttons ---------- */

const BTN = { quiet: '', danger: 'fleet-btn-danger', primary: 'fleet-btn-accent', ok: 'fleet-btn-ok', ghost: 'fleet-btn-ghost' }

export function Button({ tone = 'quiet', size, onClick, className = '', children, ...rest }) {
  return (
    <button onClick={onClick} {...rest}
      className={`fleet-btn ${BTN[tone] ?? ''} ${size === 'sm' ? 'fleet-btn-sm' : ''} ${className}`}>
      {children}
    </button>
  )
}

/* ---------- inspector ----------
   List left, detail right, context kept. The kit's drawer: Escape closes,
   focus lands inside and returns to the opener. */

export function Inspector({ title, badge, onClose, children }) {
  const ref = useRef(null)
  useEffect(() => {
    const opener = document.activeElement
    const onKey = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener && typeof opener.focus === 'function') opener.focus()
    }
  }, [onClose])

  return (
    <>
      <div onClick={onClose} className="fleet-drawer-scrim" />
      <aside ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="fleet-drawer p-0">
        <div className="sticky top-0 flex items-center gap-3 border-b border-border bg-surface px-5 py-3.5">
          <h3 className="truncate text-section font-semibold tracking-tight">{title}</h3>
          {badge}
          <button onClick={onClose} aria-label="Close" className="fleet-btn fleet-btn-sm ml-auto">Esc</button>
        </div>
        <div className="flex flex-col gap-5 px-5 pb-10 pt-4">{children}</div>
      </aside>
    </>
  )
}

/* One facet of an object that has several. The label names its source, because
   "where does this fact come from" is half of what the inspector is for. */
export function Facet({ label, source, children }) {
  return (
    <section className="border-l-2 border-border pl-3.5">
      <p className="fleet-label mb-1.5">
        {label}
        {source && <span className="ml-1 font-mono normal-case tracking-normal text-accent-text">{source}</span>}
      </p>
      {children}
    </section>
  )
}

export function KeyValues({ rows }) {
  return (
    <dl className="fleet-kv">
      {rows.filter(Boolean).map(([k, v]) => (
        <React.Fragment key={k}>
          <dt>{k}</dt>
          <dd className="font-mono text-micro break-words">{v}</dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

/* ---------- the yard: strips and bays (v0.28.0, D7) ----------
   One strip, one vocabulary, one fixed field order:
   lamp · name (mono second line) · stage · position-or-blocker · evidence · age.
   The lamp is the kit's status glyph so state stays shape + colour. The strip
   is wide by design and scrolls inside its bay on a phone. */

const LAMP_STATE = { ok: 'running', warn: 'unhealthy', danger: 'failed', off: 'stopped' }

export function Strip({
  lamp = 'off', name, sub, manned, stage, evidence, age,
  cocked, tone = 'warn', onClick, children,
}) {
  /* `off` is the one sanctioned grey: inert means out of service, never
     de-emphasis — every other strip keeps full contrast. */
  const inert = lamp === 'off'
  return (
    <div
      onClick={onClick}
      tabIndex={onClick ? 0 : undefined}
      role={onClick ? 'button' : undefined}
      onKeyDown={e => {
        if (!onClick) return
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() }
      }}
      className={`grid min-w-[44rem] items-baseline gap-x-3 rounded-sm border border-border bg-surface
        px-3 py-1.5 text-meta
        [grid-template-columns:1.1rem_11rem_5.5rem_minmax(0,1fr)_10.5rem_4.5rem]
        ${cocked
          /* The attention idiom: spatial offset plus a heavy left rule — no
             extra hue spent beyond the tone the strip already carries. */
          ? `translate-x-2 border-l-[3px] ${tone === 'danger' ? 'border-l-danger' : 'border-l-warn'}`
          : ''}
        ${onClick ? 'cursor-pointer transition hover:border-zinc-600' : ''}`}>
      <span className="self-center"><StatusGlyph state={LAMP_STATE[lamp] || 'unknown'} /></span>
      <span className="min-w-0">
        <span className={`block truncate font-medium ${inert ? 'text-faint' : 'text-ink'}`}>
          {name}
          {manned && <span className="ml-1.5 font-mono text-micro font-semibold text-accent-text">◆ manned</span>}
        </span>
        {sub && <Mono className="block truncate">{sub}</Mono>}
      </span>
      <span className="self-center">{stage}</span>
      <span className={`min-w-0 self-center ${inert ? 'text-faint' : 'text-dim'}`}>{children}</span>
      <Mono className="truncate">{evidence}</Mono>
      <Mono className="block text-right">{age}</Mono>
    </div>
  )
}

/* A bay names the one reason its strips cannot enter the line: the heading is
   the blocker, the aside is the sentence explaining it, and within the bay the
   order is admission time only — never merit. Callers must not render a bay
   with no strips; an empty bay is scaffolding, and absence is the honest state. */
export function Bay({ lamp = 'off', title, count, countTone = 'quiet', aside, children }) {
  return (
    <section className="mt-6 first:mt-0">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="self-center"><StatusGlyph state={LAMP_STATE[lamp] || 'unknown'} /></span>
        <h3 className="text-title font-semibold tracking-tight">{title}</h3>
        {count != null && <Chip tone={countTone}>{count}</Chip>}
        {aside && <span className="ml-auto max-w-[52ch] text-right text-micro text-faint">{aside}</span>}
      </div>
      <div className="fleet-table-wrap plain">
        <div className="flex flex-col gap-1.5">{children}</div>
      </div>
    </section>
  )
}

/* ---------- moved from kit.jsx in v0.19.0 (D1: one status renderer, one skeleton) ---------- */

/* Runtime liveness for a repo's Mission Control services. Distinct from StatusGlyph:
   that one renders a known state, this one summarises several services and pings when
   something is actually up. */
export function StatusDot({ mcInfo }) {
  if (!mcInfo?.length) return null
  const up = mcInfo.some(m => (m.status || '').toLowerCase().includes('run') || m.health === true)
  const known = mcInfo.some(m => m.status || m.health !== undefined)
  const state = !known ? 'unknown' : up ? 'running' : 'failed'
  return (
    <span className="relative flex shrink-0" title={mcInfo.map(m => `${m.id}: ${m.status ?? 'unknown'}`).join(', ')}>
      <StatusGlyph state={state} />
    </span>
  )
}

export function Skeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="fleet-card">
          <span className="fleet-skeleton mb-3 w-1/2" />
          <span className="fleet-skeleton mb-2" />
          <span className="fleet-skeleton w-2/3" />
        </div>
      ))}
    </div>
  )
}

/* The render-time twin of a .catch. A throw inside a subtree unmounts the whole
   tree and leaves a blank pane that only a full page reload recovers — which is
   indistinguishable from "there is nothing here", and is why the graph vanishing
   has been hard to diagnose: no console error survives, because the failure is in
   render rather than in a fetch.

   A class is not a style choice: getDerivedStateFromError has no hook equivalent.

   `onReset` lets a caller clear the state that caused the throw, so recovering
   does not require reloading the page. */
export class Boundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Keep the stack: this is the only place it exists once React has unmounted.
    console.error('[boundary]', this.props.label || '', error, info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <ErrorState
        title={`${this.props.label || 'This view'} stopped rendering`}
        detail={`${this.state.error.message || String(this.state.error)} — the stack is in the console.`}
        onRetry={() => {
          this.props.onReset?.()
          this.setState({ error: null })
        }} />
    )
  }
}
