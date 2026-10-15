import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useStored } from './kit'
import { ProblemDrawer } from './outline'
import { PageHeader, Button, Loading, ErrorState, EmptyState } from './ui'

/* The chart drawn as a tree you can actually read at scale.
 *
 * Five things this gets right that the first version did not, all of which only
 * showed up once the chart passed fifty nodes:
 *
 *   Sideways.  Depth runs horizontally — six levels is ~1200px and fits — and
 *   breadth runs down, where scrolling is natural and unbounded. Top-down made a
 *   19-wide row into a 3700px sideways crawl through a nearly flat wall.
 *
 *   Tidy.  A real tree layout: children are packed in order and every parent sits
 *   at the midpoint of its own children, so a node's position finally says
 *   something about its lineage. The old centred rows meant the eye could not
 *   follow a line from parent to child.
 *
 *   Collapsed by default.  Fifty-three nodes is past reading and five hundred is
 *   hopeless, so it opens two levels deep and everything below is a badge you
 *   click. Collapse state is shared with the goals outline, deliberately: two
 *   views of one chart disagreeing about what is open is its own confusion.
 *
 *   Re-rootable.  Focus a node and it becomes the tree, with a breadcrumb back.
 *   The answer to five hundred goals is never rendering five hundred.
 *
 *   Semantic zoom.  Size and detail follow altitude. Every node being an
 *   identical box is the same "altitude is invisible" failure the outline had.
 *
 * A tree, not a DAG, because that is very nearly what the data is — 57 nodes, 57
 * edges, one shared. Where a node does have several bearings, the first one places
 * it and the rest become dashed links, so sharing stays visible without giving up
 * a layout that a tree can have and a DAG cannot.
 *
 * Those dashed links are drawn ONLY while one of their two ends is hovered. They
 * are the lines that ignore the layout and cut across it, so at rest they read as
 * noise over the tree the eye is following — and they scale badly, since every new
 * cross-link is a chord across the whole canvas. What does not depend on hover is
 * the *fact*: a node with extra bearings carries a permanent dot marker. Hiding a
 * line is a density decision; hiding a fact would be a lie.
 */

// Collapse is shared with the goals outline on purpose — same key as goals.jsx.
const COLLAPSE_KEY = 'shipyard.goals.collapsed'
const OPEN_TO_DEPTH = 2
// The ceiling `seedCollapse` searches down from. Deeper than this is past reading
// on any chart big enough for the search to matter.
const MAX_OPEN_DEPTH = 5
const LEGEND_KEY = 'shipyard.graph.legend'

/* The zoom below which this stops being a chart.
 *
 * Derived, not taste: the deepest tier sets its title at 11.5px, and 8px is about
 * where a title stops being a word you read and becomes a shape you infer. 8/11.5
 * is 0.70. Measured before this existed, the 64-node chart fitted at k=0.27 and
 * rendered every label between 2.7 and 3.8 real pixels — the whole diagram opened
 * as grey texture, and the first thing anyone did was zoom.
 *
 * Fitting everything is not a virtue when everything is unreadable. Past this
 * floor we show LESS of the chart, legibly, and pan — which is what the canvas is
 * for. `seedCollapse` then makes that a fair trade by folding the tree until what
 * remains genuinely fits at this zoom. */
const MIN_LEGIBLE_K = 0.7

/* The focus-tree borrow: three states, legible without reading anything.
 *
 * Carried by hue and by a mark, never by dimming. A desaturated palette was tried
 * on this app in August and rejected on sight — "hard to see" — so `blocked` is
 * recessive by being *plain*, not by being faded, and every title in the chart
 * stays at full contrast whatever state it is in.
 *
 * `open` is the one that earns emphasis: it is the frontier, the set of problems
 * nothing beneath is holding up. That is the question this whole borrow exists to
 * answer, so it is the thing the eye should land on. */
const STANDING = {
  open: { stroke: 'stroke-accent/70', fill: 'fill-surface' },
  done: { stroke: 'stroke-ok/60', fill: 'fill-ok/8 fill-ok/12' },
  blocked: { stroke: 'stroke-zinc-700',
             fill: 'fill-surface' },
}

/* Size by altitude. A root carries its waypoint; a leaf carries a name. */
const TIER = [
  { w: 250, h: 62, title: 14, sub: 11, showWaypoint: true },
  { w: 205, h: 50, title: 12.5, sub: 10, showWaypoint: true },
  { w: 176, h: 34, title: 11.5, sub: 0, showWaypoint: false },
]
const tier = d => TIER[Math.min(d, TIER.length - 1)]
const V_GAP = 12
const H_GAP = 64

function relations(nodes, edges) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const parents = new Map(nodes.map(n => [n.id, []]))
  const kids = new Map(nodes.map(n => [n.id, []]))
  for (const e of edges) {
    if (!byId.has(e.child) || !byId.has(e.parent)) continue
    parents.get(e.child).push(e.parent)
    kids.get(e.parent).push(e.child)
  }
  return { byId, parents, kids }
}

/* Tidy tree, left to right. Leaves take the next vertical slot; a parent centres
   on its children. O(n), exact for trees, and the extra bearings of a shared node
   are returned separately rather than bending the layout out of shape. */
function layout(nodes, edges, { focus, collapsed }) {
  const { byId, parents, kids } = relations(nodes, edges)

  const roots = focus && byId.has(focus)
    ? [focus]
    : nodes.filter(n => parents.get(n.id).length === 0).map(n => n.id)

  // The parent that places a node: its first bearing. Every other bearing becomes
  // a dashed link so a shared goal is still visibly shared.
  const primary = new Map()
  for (const n of nodes) {
    const ps = parents.get(n.id)
    if (ps.length) primary.set(n.id, ps[0])
  }

  const placed = new Map()
  const hidden = new Map()          // collapsed node -> how many are folded inside
  // node -> how many children the TREE gives it, folded or not. `hidden` only knows
  // about folded nodes, so without this an expanded branch had no way to say it was
  // a branch — and the fold control could only ever appear on things already folded,
  // which is the one state from which you do not need to discover it.
  const owned = new Map()
  let cursor = 0
  let maxDepth = 0

  const countBelow = (id, seen = new Set()) => {
    if (seen.has(id)) return 0
    seen.add(id)
    return kids.get(id).reduce((a, k) =>
      (primary.get(k) === id ? a + 1 + countBelow(k, seen) : a), 0)
  }

  const walk = (id, depth, seen) => {
    if (seen.has(id)) return null
    seen = new Set(seen).add(id)
    maxDepth = Math.max(maxDepth, depth)

    const own = kids.get(id).filter(k => primary.get(k) === id)
    owned.set(id, own.length)
    const folded = collapsed.has(id) && own.length > 0
    if (folded) hidden.set(id, countBelow(id))

    const t = tier(depth)
    let y
    if (folded || own.length === 0) {
      y = cursor
      cursor += t.h + V_GAP
    } else {
      const ys = own.map(k => walk(k, depth + 1, seen)).filter(v => v !== null)
      y = ys.length ? (ys[0] + ys[ys.length - 1]) / 2 : cursor
      if (!ys.length) cursor += t.h + V_GAP
    }
    placed.set(id, { y, depth })
    return y
  }

  roots.forEach(r => { walk(r, 0, new Set()); cursor += V_GAP * 2 })

  // Depth columns are only as wide as the tier that lives in them.
  const colX = []
  for (let d = 0; d <= maxDepth; d++) {
    colX[d] = d === 0 ? 0 : colX[d - 1] + tier(d - 1).w + H_GAP
  }
  for (const [id, p] of placed) p.x = colX[p.depth]

  const drawn = []
  for (const e of edges) {
    const c = placed.get(e.child), p = placed.get(e.parent)
    if (!c || !p) continue
    if (collapsed.has(e.parent)) continue
    drawn.push({ ...e, secondary: primary.get(e.child) !== e.parent })
  }

  // Room on the right for the fold toggle and the add-a-child control, which hang
  // off a node's trailing edge — without it the deepest column's controls sat outside
  // the fitted width and `Fit` cut them off.
  const width = (colX[maxDepth] ?? 0) + tier(maxDepth).w + 76
  const height = Math.max(cursor, 80) + 20
  return { placed, hidden, owned, edges: drawn, width, height, maxDepth }
}

/* Zoom that shows as much as fits without going under the legibility floor. */
function fitK(tree, box) {
  const raw = Math.min(1, (box.width - 24) / tree.width, (box.height - 24) / tree.height)
  return Math.max(MIN_LEGIBLE_K, raw)
}

/* Every node that has children and sits at or below `depth`, i.e. the fold set
   that leaves exactly `depth` levels showing. */
function collapseToDepth(nodes, edges, depth) {
  const { parents, kids } = relations(nodes, edges)
  const fold = new Set()
  const walk = (id, d, seen) => {
    if (seen.has(id)) return
    seen = new Set(seen).add(id)
    if (d >= depth && kids.get(id).length) fold.add(id)
    kids.get(id).forEach(k => walk(k, d + 1, seen))
  }
  nodes.filter(n => !parents.get(n.id).length).forEach(r => walk(r.id, 0, new Set()))
  return fold
}

/* How deep to open on first load.
 *
 * The old answer was a constant — two levels, always — which is a guess about the
 * shape of a chart the constant cannot see. At 64 nodes it left 61 showing and
 * 1736px of tree in a 502px frame, so the view that greeted you was the whole
 * chart at 27%.
 *
 * This asks the layout instead: take the deepest opening that still fits above the
 * legibility floor. On a small chart that is everything, and nothing is folded
 * that did not need to be. On a large one it folds until what is left can be read
 * — the same principle as focusing a node, applied on arrival. */
function seedCollapse(nodes, edges, box, maxDepth) {
  for (let d = maxDepth; d >= 1; d--) {
    const fold = collapseToDepth(nodes, edges, d)
    const t = layout(nodes, edges, { focus: null, collapsed: fold })
    if (fitK(t, box) > MIN_LEGIBLE_K) return fold
  }
  return collapseToDepth(nodes, edges, 1)
}

/* The graph has an id and nothing else — /api/graph is a layout payload and carries
   no prose — so the fetch lives here and the shape comes from `outline`.
 *
 * `base` is the canvas's own node, merged UNDER the fetched one: `standing` is
 * derived across the whole chart by /api/graph and is absent from the spine, so a
 * rail that disables "start working on this" for a blocked problem would otherwise
 * offer a button whose only outcome is a 422.
 *
 * `rail` is what a host hangs off the drawer when this component owns it —
 * the same seam `children` already is on ProblemDrawer, one level up. It is called
 * with the loaded node and a `reload` that refetches both the panel and the canvas,
 * so an edit made in the drawer is drawn behind it. */
function FetchedDrawer({ id, title, base = null, rail = null, onAddChild, onReload, onClose }) {
  const [node, setNode] = useState(null)
  const [err, setErr] = useState(null)
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let live = true                       // a fast second click must not land twice
    setNode(null)
    setErr(null)
    fetch(`/api/chart/${encodeURIComponent(id)}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(v => { if (live) setNode({ ...base, ...v.node, child_count: v.children.length }) })
      .catch(e => { if (live) setErr(String(e.message || e)) })
    return () => { live = false }
  }, [id, nonce])
  const reload = useCallback(() => { setNonce(n => n + 1); onReload?.() }, [onReload])
  return (
    <ProblemDrawer node={node} title={title} onClose={onClose}
      pending={err ? <ErrorState title="That problem would not load" detail={err} /> : null}>
      {node && rail?.(node, { reload, close: onClose, addChild: onAddChild })}
    </ProblemDrawer>
  )
}

/* Making a problem where you are already looking at the chart.
 *
 * Its own component, with its own state, for a reason that is not tidiness: the
 * canvas re-renders every node and every edge, and holding the two fields in
 * GraphPage meant a keystroke redrew ninety SVG groups. It also has to survive the
 * empty chart, which returns before GraphPage has a `byId` to name a parent with —
 * so the parent arrives as a title, never as an id to look up.
 *
 * Waypoint is optional and says so. The API refuses a problem with no observable
 * only where it matters (a waypointless node is a `draft`, and the chart counts
 * them); demanding one here would mean the thought has to arrive finished. */
function Composer({ parentTitle, canTopLevel, onTopLevel, onCreate, onCancel, onOpen,
                    busy, error, made = [] }) {
  const [title, setTitle] = useState('')
  const [waypoint, setWaypoint] = useState('')
  const first = useRef(null)

  /* Add and stay open, because nobody decomposes ONE thing.
   *
   * A form that closes on submit made breaking a problem into five subproblems five
   * trips through the toolbar — which is the motion the outline did for free and the
   * single thing its deletion cost. Clearing happens only on success: wiping the
   * title after a 422 would mean retyping the thing the server just refused. */
  const submit = after => {
    if (!title.trim() || busy) return
    onCreate({ title: title.trim(), waypoint: waypoint.trim(), after })
      .then(ok => {
        if (!ok || after === 'close') return
        setTitle('')
        setWaypoint('')
        first.current?.focus()
      })
  }
  const onFieldKey = e => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    submit(e.shiftKey ? 'descend' : 'stay')
  }

  return (
    <div className="mb-3 shrink-0 rounded-card border border-accent/40 bg-accent/5 p-3"
      onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); onCancel() } }}>
      <p className="text-micro text-faint">
        {parentTitle
          ? <>Beneath <b className="font-medium">{parentTitle}</b></>
          : 'A new top-level goal — nothing sits above it.'}
        {canTopLevel && parentTitle && (
          <button onClick={onTopLevel} className="ml-2 text-accent hover:underline">
            make it top-level instead
          </button>
        )}
      </p>
      <input
        ref={first} value={title} onChange={e => setTitle(e.target.value)} autoFocus
        placeholder="the problem"
        onKeyDown={onFieldKey}
        className="mt-2 w-full rounded-lg border bg-transparent px-2 py-1 text-body
             focus:border-accent border-zinc-700"
      />
      <input
        value={waypoint} onChange={e => setWaypoint(e.target.value)}
        placeholder="what would you observe if it were solved? (optional — leaves it a draft)"
        onKeyDown={onFieldKey}
        className="mt-1.5 w-full rounded-lg border bg-transparent px-2 py-1 text-meta
             focus:border-accent border-zinc-700"
      />
      {error && <p className="mt-1.5 text-micro text-danger">{error}</p>}

      {/* What this session has made. The form clears itself, so without this
          "add and keep going" is indistinguishable from "the button did nothing" —
          and the names are the way back to a node you have not opened. */}
      {made.length > 0 && (
        <p className="mt-2 flex flex-wrap items-baseline gap-1.5 text-micro text-faint">
          <span>added</span>
          {made.map(m => (
            <button key={m.id} onClick={() => onOpen(m.id)}
              className="rounded-full px-2 py-0.5 text-accent ring-1 ring-inset ring-accent/30
                hover:bg-accent/10">
              {m.title}
            </button>
          ))}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button tone="primary" onClick={() => submit('stay')} disabled={!title.trim() || busy}
          className="disabled:opacity-40">
          {busy ? 'adding…' : 'Add'}
        </Button>
        <Button onClick={() => submit('descend')} disabled={!title.trim() || busy}
          title="add it, then aim at what you just added"
          className="disabled:opacity-40">
          Add &amp; go beneath
        </Button>
        <span className="text-micro text-faint">
          Enter adds another here · Shift-Enter descends · Escape closes
        </span>
        <button onClick={onCancel} className="ml-auto text-micro text-faint">done</button>
      </div>
    </div>
  )
}

function clip(text, chars) {
  return text.length > chars ? text.slice(0, chars - 1) + '…' : text
}

/* `embedded` is how this renders as a mode of Chart rather than its own page:
   Chart already owns the title, the counts and the back link, so the graph
   contributes only its canvas and the controls that belong to it. It stopped
   being a tab because it is the same chart the outline draws — the two even
   share a collapse key on purpose, which was the code admitting they were one
   view before the nav did. */
/* `root` scopes the graph to one problem's subtree — the same scoping the outline
   already had, so a project can draw its own canvas instead of the fleet's. Null
   means the whole chart, which is what the Chart tab asks for. */
/* A plain click opens the node beside the canvas. ALWAYS — every graph in the app,
   not only the Chart's.
   `onPick` is for a host that already owns a drawer and a selection: Chart passes it
   because its selection lives in the URL and is shared with the outline. Without it
   this draws its own drawer, which is what the project page's Problem Chart needs —
   it had no drawer, so a click there still left the page for #/problem/<id>. Making
   navigation the fallback looked like a safe default and was really a second
   behaviour for the same gesture, decided by which page you happened to be on.
   `selected` is what the host's drawer is showing, so the canvas and a drawer this
   component does not own still agree about which node is open. */
/* `onCreated` and `rail` are the two seams authoring needs.
 *
 * The canvas replaced the outline on the goals page and is about to replace the
 * project's, and an outline could always be typed into. A diagram you can only read
 * is a diagram that has to be left to change anything — so `＋ New problem` and the
 * drawer's rail are what carry the authoring across. `onCreated` tells a host its
 * own copy of the chart is stale; `rail` is what a host that does NOT own the drawer
 * hangs inside the one this component owns. */
/* Search lives HERE, not on the page that hosts the canvas.
 *
 * It used to be an input in the goals page header, left over from when the outline
 * owned it. Two things were wrong with that. It was on one surface only, so the
 * project's chart — the same component, the same 90-node problem — had no way to find
 * anything. And the moment this view could cover the window, the box went behind the
 * layer: fullscreen is exactly when you most need to find a node, and it was the one
 * state where you could not. The graph is what derives the hit set, dims the misses
 * and unfolds the path to each, so the box belongs beside those controls. */
export function GraphPage({ onClose, embedded = false, root = null,
                            onPick = null, selected = null, firstVisit = null,
                            collapsed: hostCollapsed = null, onCollapsed = null,
                            highlight = null, highlightLabel = '', nonce = null,
                            onCreated = null, rail = null, emptyDetail = null }) {
  const [query, setQuery] = useState('')
  const searchRef = useRef(null)
  const [data, setData] = useState(undefined)
  const [err, setErr] = useState(null)
  const [hover, setHover] = useState(null)
  const [focus, setFocus] = useState(null)
  // Only used when no host owns the selection; `marked` is the one the ring follows
  // either way, so the canvas looks the same whichever drawer is open.
  const [inspect, setInspect] = useState(null)
  const marked = onPick ? selected : inspect
  const clickTimer = useRef(null)
  // Keyed by root: collapsing a branch of the fleet graph should not silently
  // collapse the same node inside a project's own view, where it may be the root.
  const storeKey = root ? `${COLLAPSE_KEY}.${root}` : COLLAPSE_KEY
  /* Fold state, host-owned when there is a host.
   *
   * `useStored` is a useState per component, so the graph and the outline held two
   * copies of one key and only agreed at mount. That was invisible while the graph
   * deferred to whatever it found; the moment it started seeding, it wrote 22 folds,
   * redrew itself, and left the outline rendering the set it had computed earlier —
   * the two views disagreeing about what is open, which is the exact confusion the
   * shared key exists to prevent.
   *
   * So a host that owns the state passes it in and there is one. Same seam as
   * `selected`/`onPick`. A project's scoped graph owns no host and keeps its own.
   */
  const ownStore = useStored(storeKey, [])
  const collapsed = hostCollapsed ?? ownStore[0]
  const setCollapsed = onCollapsed ?? ownStore[1]
  const [seeded, setSeeded] = useState(false)
  /* Has the user ever folded anything here?
   *
   * A host that wrote the key before this mounted must say so — on the Chart the
   * outline's `useStored` has already persisted it, so asking localStorage here
   * would call every visit a return visit. Where nothing else owns the key (a
   * project's scoped graph) this reads it itself, in an initialiser that runs
   * before useStored's own effect writes.
   */
  const [ownFirstVisit] = useState(() => {
    try { return localStorage.getItem(storeKey) === null } catch { return false }
  })
  const isFirstVisit = firstVisit ?? ownFirstVisit
  // Sticky, because whether you need the instructions is a fact about you, not
  // about this visit. Not `useStored` — that hook stores Sets, and would turn
  // `false` into an empty Set, which is truthy.
  const [legend, setLegend] = useState(() => {
    try { return localStorage.getItem(LEGEND_KEY) === '1' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem(LEGEND_KEY, legend ? '1' : '0') } catch { /* private mode */ }
  }, [legend])
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  /* Fullscreen is a CSS layer, not the Fullscreen API.
   *
   * `requestFullscreen` promotes ONE element, and the drawer this canvas opens is a
   * sibling rendered by the host — on the goals page it is not inside this subtree
   * at all — so the browser's own fullscreen would black out the panel that clicking
   * a node exists to open. A fixed layer under the Inspector's z-40 keeps both.
   * Deliberately not persisted: it is a posture for the next few minutes, not a
   * preference, and a page that reopens pinned over everything is a page you have
   * to escape before you can read anything else. */
  const [full, setFull] = useState(false)
  /* { parent, parentTitle } while a new problem is being typed. Null when not
     composing. `parentTitle` is carried rather than looked up because descending —
     adding beneath the node you just added — re-aims at an id the canvas has not
     refetched yet, and "Beneath undefined" for half a second is worse than passing
     one string. */
  const [composing, setComposing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [createErr, setCreateErr] = useState(null)
  // What this composing session has made, in order. Without it "add and keep going"
  // is a form that clears itself and gives no sign anything happened.
  const [made, setMade] = useState([])
  /* The keyboard's position in the tree, deliberately NOT the selection.
   *
   * Moving the selection with the arrow keys would open the drawer on every press —
   * on the project page that is a fetch per keystroke, and on both it means the panel
   * you are trying to navigate around is permanently in the way. So the cursor is its
   * own ring: arrows move it, Enter is what commits to reading a node. Clicking sets
   * it too, so the keyboard picks up wherever the mouse left off. */
  const [cursor, setCursor] = useState(null)
  const drag = useRef(null)
  const frame = useRef(null)

  // Same missing `.catch` the project page had: without it a failed load sits on
  // "loading graph…" forever, which reads as a slow layout rather than a dead one.
  const load = useCallback(() => {
    setErr(null)
    fetch(root ? `/api/graph?root=${encodeURIComponent(root)}` : '/api/graph')
      .then(r => {
        // A scoped graph 404s when the project has no chart node — which is not a
        // failure, it is the ordinary state of most repos here. Reading it as an
        // error put "could not read the chart" on every uncharted project the
        // moment this view replaced the outline that used to say so plainly.
        if (r.status === 404 && root) return { nodes: [], edges: [] }
        return r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))
      })
      .then(setData)
      .catch(e => setErr(e.message))
  }, [root])
  /* `nonce` is how a host says the chart changed under us.
   *
   * /api/graph is fetched once, which was fine while the graph was a read-only
   * second view — the outline owned authoring and re-rendered from its own data.
   * With the outline gone, adding or deleting a problem happens beside a canvas
   * that had no idea, so the node you just made was not drawn until a reload. Same
   * idiom FocusStrip already uses. */
  useEffect(load, [load, nonce])

  /* Escape unwinds one layer at a time, innermost first.
   *
   * `marked` is deliberately a bail-out rather than a case: the drawer runs its own
   * Escape listener on the same window, so handling it here too would close the panel
   * AND drop out of fullscreen on one keypress — two layers for one press, which is
   * the thing this ordering exists to prevent. With a node open, the first press is
   * the drawer's and the second is ours. */
  useEffect(() => {
    const onKey = e => {
      if (e.key !== 'Escape') return
      if (composing) { setComposing(null); return }
      if (marked) return
      if (full) { setFull(false); return }
      if (focus) { setFocus(null); return }
      onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, focus, full, composing, marked])


  // A page that scrolls behind a layer covering it is a scrollbar that moves nothing
  // you can see, and a wheel event the canvas never receives.
  useEffect(() => {
    if (!full) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [full])

  /* Open as deep as stays readable — on a first visit, and only then.
   *
   * The test used to be `collapsed.size > 0`, meaning "someone already has an
   * opinion, defer to it". On the Chart that someone was always the outline: it
   * folds every branch once the list passes 20 rows, writes the key both views
   * share, and does it before you can click through to the graph. So this never
   * ran on the surface it was written for, and the opening view was chosen by a
   * row count that knows nothing about whether the result is legible on a canvas.
   *
   * `isFirstVisit` asks the question that was meant: has the USER folded anything.
   * If they have, their choice stands — that has not changed. If they have not,
   * the view that can measure the frame decides, and writes it to the shared key
   * so the outline agrees. That write is the point rather than a side effect: one
   * chart, one fold state, and the decision made by whichever view can justify it.
   */
  useEffect(() => {
    if (!data || seeded) return
    setSeeded(true)
    if (!isFirstVisit) return
    // Fall back to the old fixed depth if the frame has not been measured yet —
    // a guess is still better than opening every node of a large chart.
    const box = frame.current?.getBoundingClientRect()
    setCollapsed(box
      ? seedCollapse(data.nodes, data.edges, box, MAX_OPEN_DEPTH)
      : collapseToDepth(data.nodes, data.edges, OPEN_TO_DEPTH))
  }, [data, seeded, isFirstVisit, setCollapsed])

  /* What the query hits. Null — not an empty set — when there is no query, so
     "searching and finding nothing" stays distinguishable from "not searching",
     which is the difference between dimming the whole chart and dimming none of
     it. Same fields the outline searches, so one box cannot mean two things. */
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q && data) {
      return new Set(data.nodes
        .filter(n => n.title.toLowerCase().includes(q) ||
                     (n.waypoint || '').toLowerCase().includes(q))
        .map(n => n.id))
    }
    // A facet — "13 without a waypoint" — is the same question asked from a chip
    // instead of a box, so it gets the same answer: ring the set, recede the rest,
    // unfold the path to each. Typing outranks a chip because it is the more
    // specific act, and the two are never usefully combined.
    return highlight ?? null
  }, [query, data, highlight])

  /* Search unfolds the path to each hit, but does NOT write the collapse set.
     A search is a question you are asking now; a fold is a decision you made
     about how you want the chart to sit. Writing one into the other would mean
     clearing the box left the tree splayed open, and — because the key is shared
     — rearranged the outline too, as a side effect of typing. */
  const shown = useMemo(() => {
    if (!matches?.size || !data) return collapsed
    const { parents } = relations(data.nodes, data.edges)
    const open = new Set()
    for (const m of matches) {
      for (let id = parents.get(m)?.[0]; id; id = parents.get(id)?.[0]) {
        if (open.has(id)) break
        open.add(id)
      }
    }
    const next = new Set(collapsed)
    open.forEach(id => next.delete(id))
    return next
  }, [matches, collapsed, data])

  const tree = useMemo(
    () => (data ? layout(data.nodes, data.edges, { focus, collapsed: shown }) : null),
    [data, focus, shown])

  const fit = useCallback(() => {
    const box = frame.current?.getBoundingClientRect()
    if (!box || !tree) return
    setView({ x: 12, y: 12, k: fitK(tree, box) })
  }, [tree])

  useEffect(() => { if (tree) fit() }, [tree?.width, tree?.height, fit])

  /* Refit when the frame itself changes size. Going fullscreen roughly doubles the
     height available and the zoom is derived from that height — without this, filling
     the window left the chart at the zoom it had picked for an 82vh box, which is the
     one thing fullscreen was asked for and the one thing it would not have done. */
  useEffect(() => { if (tree) fit() }, [full])

  /* Declared up here, above the early returns, because the keyboard effect names it
     in a dependency array — and a deps array is evaluated during render, so a `const`
     further down the body is still in its temporal dead zone when React reads it. */
  const toggle = useCallback(id => setCollapsed(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n
  }), [setCollapsed])

  const openNode = useCallback(id => { if (onPick) onPick(id); else setInspect(id) }, [onPick])

  /* Create, then keep going.
   *
   * Three things have to happen in order or the node you just made is invisible:
   * unfold the parent (the canvas opens folded, so a child born inside a fold is
   * never drawn), refetch the graph (/api/graph is fetched once — the same reason
   * `nonce` exists), and put the cursor on it. `onCreated` is the host's copy of the
   * chart, which knows nothing about any of this.
   *
   * `after` is what the outline had and a dialog does not. Breaking a problem into
   * five subproblems was five trips through the toolbar, because a form that closes
   * on submit assumes you came to make one thing — and nobody decomposes one thing.
   *
   *   'stay'    — same parent, ready for the next sibling. Enter.
   *   'descend' — re-aim at what was just made. Shift-Enter.
   *   'close'   — the old behaviour, and the only one that opens the drawer: with the
   *               composer still up, opening a panel over the canvas on every add
   *               would bury the thing you are building.
   *
   * Resolves true/false so the composer knows whether to clear its fields — clearing
   * on a rejected create would throw away the title you now have to retype. */
  const create = useCallback(({ title, waypoint, after = 'close' }) => {
    const parent = composing?.parent ?? null
    setCreating(true)
    setCreateErr(null)
    return fetch('/api/problems', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, waypoint, draft: !waypoint, parent_id: parent }),
    })
      .then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })
      .then(d => {
        if (parent) {
          setCollapsed(prev => { const n = new Set(prev); n.delete(parent); return n })
        }
        load()
        onCreated?.(d.id)
        setCursor(d.id)
        setMade(m => [...m, { id: d.id, title }])
        if (after === 'descend') setComposing({ parent: d.id, parentTitle: title })
        else if (after === 'close') { setComposing(null); openNode(d.id) }
        return true
      })
      .catch(e => { setCreateErr(e.message); return false })
      .finally(() => setCreating(false))
  }, [composing, setCollapsed, load, onCreated, openNode])

  /* Where a new problem lands, most specific first: the node you have open, then the
     one you have focused, then the subtree you are scoped to, then nothing — a new
     bearing. Anything else would mean reading the chart to find out where the button
     put it. */
  const openComposer = () => {
    setCreateErr(null)
    setMade([])
    setComposing({ parent: marked ?? cursor ?? focus ?? root ?? null })
  }

  /* The same composer, aimed at one node instead of at whatever is open. Used by the
     ＋ on a node and by the drawer's "add a problem beneath" — one control on the
     canvas and one in the panel, both landing in the same place, because two ways to
     add a child that behave differently is worse than one. */
  const addBeneath = id => {
    setCreateErr(null)
    setMade([])
    setComposing({ parent: id })
  }

  /* Unfold whatever the drawer is describing.
   *
   * The canvas folds by default and the selection comes from outside it — the URL
   * carries a node id, and the outline's search picks nodes several levels below
   * what the graph has open. Without this you could read a panel about a node
   * while the chart behind it did not contain it, and nothing on screen said
   * where it lived. Unfolding the ancestors rather than the whole tree keeps the
   * reveal as small as the question.
   *
   * This writes the shared collapse set on purpose: revealing a node here reveals
   * it in the outline too, which is the same "two views cannot disagree about
   * what is open" rule the collapse key already exists to enforce. */
  useEffect(() => {
    if (!marked || !data) return
    const { parents } = relations(data.nodes, data.edges)
    const chain = []
    for (let id = parents.get(marked)?.[0]; id; id = parents.get(id)?.[0]) {
      if (chain.includes(id)) break        // a shared node's bearings can cycle
      chain.push(id)
    }
    if (!chain.some(id => collapsed.has(id))) return
    setCollapsed(prev => {
      const n = new Set(prev)
      chain.forEach(id => n.delete(id))
      return n
    })
  }, [marked, data, collapsed, setCollapsed])

  /* ...and bring it into view, but only when it is not already there. Recentring
     on every selection would yank the canvas out from under someone clicking
     their way across a branch they can already see. Declared after `fit` so that
     on the relayout an unfold causes, this is what lands last.

     Shared with the keyboard cursor, which needs exactly the same thing and needs it
     on every press: arrowing off the bottom of the frame with no scroll is the
     failure mode that makes keyboard navigation useless on a 90-node chart. */
  const reveal = useCallback(id => {
    if (!id || !tree) return
    const p = tree.placed.get(id)
    const box = frame.current?.getBoundingClientRect()
    if (!p || !box) return
    const t = tier(p.depth)
    setView(v => {
      const x1 = p.x * v.k + v.x, y1 = p.y * v.k + v.y
      if (x1 >= 0 && y1 >= 0 && x1 + t.w * v.k <= box.width && y1 + t.h * v.k <= box.height) {
        return v
      }
      return { ...v,
        x: box.width / 2 - (p.x + t.w / 2) * v.k,
        y: box.height / 2 - (p.y + t.h / 2) * v.k }
    })
  }, [tree])

  useEffect(() => { reveal(marked) }, [marked, reveal])
  useEffect(() => { reveal(cursor) }, [cursor, reveal])

  /* Moving through the chart without the mouse.
   *
   * A canvas is the one shape that loses this for free: an outline gave you arrow
   * keys because rows ARE a list, and a diagram has to be told what "next" means. So
   * the two axes are answered separately, and each takes its meaning from the layout
   * rather than from the data:
   *
   *   ↑ / ↓  the flattened visible order, which for a tidy tree is exactly its
   *          vertical order — sort what is drawn by y. That crosses branch boundaries
   *          the way scrolling an outline does, which is the behaviour being missed.
   *   → / ←  structure. Right unfolds a folded branch, else steps to the first child;
   *          left folds an open branch, else steps to the parent. The file-tree idiom,
   *          because it is the one people already have.
   *
   * Enter opens the node — the cursor deliberately does not, see `cursor`. Space
   * folds. `/` puts the caret in the search box, so finding a node is also reachable
   * without leaving the keyboard.
   *
   * Guarded on INPUT/TEXTAREA: the drawer, the composer and the search box are all
   * full of fields, and an arrow key inside one of them is a caret movement, not a
   * navigation. This is why the guard tests the event target rather than asking
   * whether some panel happens to be open. */
  useEffect(() => {
    if (!tree || !data) return
    const onKey = e => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) {
        return
      }
      const KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', ' ', '/']
      if (!KEYS.includes(e.key)) return

      if (e.key === '/') {
        e.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
        return
      }

      // Everything drawn, in reading order. `placed` is filled by a post-order walk,
      // so its insertion order is NOT the vertical order — sorting by y is what makes
      // ↑/↓ mean what the eye expects.
      const order = [...tree.placed.entries()].sort((a, b) => a[1].y - b[1].y).map(([id]) => id)
      if (!order.length) return
      // First press with no cursor lands on whatever is already in play, so the
      // keyboard continues the mouse's thought instead of jumping to the top.
      const at = cursor && tree.placed.has(cursor) ? cursor
        : (marked && tree.placed.has(marked) ? marked : order[0])
      e.preventDefault()
      if (!cursor || !tree.placed.has(cursor)) { setCursor(at); return }

      const i = order.indexOf(at)
      const { parents, kids } = relations(data.nodes, data.edges)
      const childrenOf = id => kids.get(id)?.filter(k => tree.placed.has(k)) ?? []
      const isFolded = collapsed.has(at) && (tree.owned.get(at) || 0) > 0

      if (e.key === 'ArrowDown') setCursor(order[Math.min(i + 1, order.length - 1)])
      else if (e.key === 'ArrowUp') setCursor(order[Math.max(i - 1, 0)])
      else if (e.key === 'Enter') openNode(at)
      else if (e.key === ' ') { if ((tree.owned.get(at) || 0) > 0) toggle(at) }
      else if (e.key === 'ArrowRight') {
        if (isFolded) toggle(at)
        else {
          const kid = childrenOf(at)[0]
          if (kid) setCursor(kid)
        }
      } else if (e.key === 'ArrowLeft') {
        if (!isFolded && (tree.owned.get(at) || 0) > 0) toggle(at)
        else {
          const up = parents.get(at)?.[0]
          if (up && tree.placed.has(up)) setCursor(up)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tree, data, cursor, marked, collapsed, openNode, toggle])

  /* Same courtesy for a search: if the query hits something but every hit is off
     screen, go to the shallowest one. Highlighting a node you cannot see is the
     same failure as ringing a node that is folded away — the answer exists and
     the screen does not show it. Shallowest, because it is the hit nearest the
     bearing the others hang off, so it orients rather than teleports. */
  useEffect(() => {
    if (!matches?.size || !tree) return
    const box = frame.current?.getBoundingClientRect()
    if (!box) return
    const placed = [...matches].map(id => [id, tree.placed.get(id)]).filter(([, p]) => p)
    if (!placed.length) return
    setView(v => {
      const visible = placed.some(([, p]) => {
        const t = tier(p.depth)
        const x1 = p.x * v.k + v.x, y1 = p.y * v.k + v.y
        return x1 >= 0 && y1 >= 0 && x1 + t.w * v.k <= box.width && y1 + t.h * v.k <= box.height
      })
      if (visible) return v
      const [, p] = placed.reduce((a, b) => (b[1].depth < a[1].depth ? b : a))
      const t = tier(p.depth)
      return { ...v,
        x: box.width / 2 - (p.x + t.w / 2) * v.k,
        y: box.height / 2 - (p.y + t.h / 2) * v.k }
    })
  }, [matches, tree])

  const onWheel = e => {
    if (!e.ctrlKey && !e.metaKey && Math.abs(e.deltaX) > Math.abs(e.deltaY)) return
    e.preventDefault()
    // Guarded like `fit()` above. One of these two had `?.` and the other did
    // not, which is how a ref-is-null crash survives in a file that already
    // knows the ref can be null.
    const box = frame.current?.getBoundingClientRect()
    if (!box) return
    const mx = e.clientX - box.left, my = e.clientY - box.top
    setView(v => {
      const k = Math.min(2.5, Math.max(0.2, v.k * (e.deltaY < 0 ? 1.12 : 0.89)))
      // Keep the point under the cursor fixed, or zooming walks away from you.
      return { k, x: mx - (mx - v.x) * (k / v.k), y: my - (my - v.y) * (k / v.k) }
    })
  }

  // Chart supplies the page container when embedded; a second one double-pads.
  const wrap = embedded ? '' : 'mx-auto max-w-6xl px-6 py-6'
  const wrapTall = embedded ? '' : 'mx-auto max-w-6xl px-6 py-8'

  const back = embedded ? null : (
    <button onClick={onClose}
      className="mb-4 text-meta text-faint transition hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
      ← goals
    </button>
  )

  if (err) {
    return (
      <div className={wrapTall}>
        {back}
        <ErrorState title="Could not read the chart" detail={err} onRetry={load} />
      </div>
    )
  }

  if (!data) {
    return <div className={wrapTall}>{back}<Loading label="Laying out the chart" /></div>
  }

  /* An empty chart is where the missing "new node" hurt most: the view that draws
     the chart told you to go and build one somewhere else. A scoped graph still
     does — a project's node is how a repo enters the chart at all, and that is the
     adopt flow, not a bare problem — so `emptyDetail` lets the host say why. */
  if (data.nodes.length === 0) {
    return (
      <div className={wrapTall}>
        {back}
        {composing ? (
          <Composer parentTitle={null} canTopLevel={false}
            onCreate={create} onCancel={() => setComposing(null)} onOpen={openNode}
            busy={creating} error={createErr} made={made} />
        ) : (
          <EmptyState
            glyph="◇"
            title="Nothing charted yet"
            detail={emptyDetail
              || 'The graph draws the problem chart. Every goal starts as one problem with something observable beneath it.'}
            actions={root
              ? <Button onClick={() => { window.location.hash = '#/goals' }}>Go to Goals</Button>
              : <Button tone="primary" onClick={openComposer}>＋ Add the first problem</Button>}
          />
        )}
      </div>
    )
  }

  const { byId, parents } = relations(data.nodes, data.edges)
  const trail = []
  for (let id = focus; id; id = parents.get(id)?.[0]) {
    trail.unshift(byId.get(id))
    if (trail.length > 12) break
  }

  const near = id => hover && (hover === id ||
    data.edges.some(e => (e.child === hover && e.parent === id) ||
                         (e.parent === hover && e.child === id)))

  /* Which nodes an extra bearing touches, so the mark can be permanent even
     though the line is not. Without this, hiding the dashed edges would quietly
     turn a shared goal into one that looks like it serves a single bearing —
     hiding a *fact* rather than a bit of clutter, which is the opposite of the
     point. `shares` counts a node's extra parents; `lends` marks the goal on the
     other end, whose child sits somewhere else on the canvas. */
  const shares = new Map()
  const lends = new Set()
  for (const e of tree.edges) {
    if (!e.secondary) continue
    shares.set(e.child, (shares.get(e.child) || 0) + 1)
    lends.add(e.parent)
  }

  /* One control, rendered into both headers, because there are two of them and a
     button that exists in only one is a feature that depends on which page you
     opened. `Fit` and the zoom readout already had to be written twice; these join
     them rather than being duplicated a third time by hand. */
  const controls = (
    <>
      {/* Wired to `/` in the key handler, so finding a node never needs the mouse. */}
      <input
        ref={searchRef} value={query} onChange={e => setQuery(e.target.value)}
        onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setQuery(''); e.currentTarget.blur() } }}
        placeholder="search titles and waypoints…  /"
        aria-label="search the chart"
        className="w-56 rounded-lg border bg-transparent px-2 py-1 text-meta 
           focus:border-accent border-border"
      />
      <Button onClick={openComposer} disabled={!!composing}
        className="disabled:opacity-40"
        title="add a problem — beneath whatever is open or focused">
        ＋ New problem
      </Button>
      {/* One control, both directions. The page used to carry its own
          collapse-all beside the outline, so removing the outline left two
          buttons reading "expand all" that did different things. */}
      <Button onClick={() => setCollapsed(collapsed.size
        ? new Set()
        : collapseToDepth(data.nodes, data.edges, 1))}>
        {collapsed.size ? 'Expand all' : 'Collapse all'}
      </Button>
      <Button onClick={fit}>Fit</Button>
      <Button onClick={() => setFull(v => !v)}
        title={full ? 'back to the page — or press Escape' : 'fill the window'}
        aria-pressed={full}>
        {full ? '⤡ Exit fullscreen' : '⤢ Fullscreen'}
      </Button>
      <span className="self-center font-mono text-micro tabular-nums text-faint">{Math.round(view.k * 100)}%</span>
    </>
  )

  return (
    <div className={full
      ? 'fixed inset-0 z-30 flex flex-col px-5 py-4 bg-bg'
      : wrap}>
      {!full && back}

      {embedded ? (
        <div className="mb-3 flex flex-wrap items-center gap-3 shrink-0">
          {/* Fullscreen hides the page that was carrying the title, so the canvas
              has to say what it is drawing while it covers everything else. */}
          {full && (
            <span className="text-meta font-medium">
              {root ? 'Problem chart' : 'Long Term Goal Chart'}
              <span className="ml-2 font-normal text-faint">
                {data.nodes.length} problems
              </span>
            </span>
          )}
          {matches ? (
            // Zero is the answer worth stating plainly. Without it a query that
            // hits nothing looks identical to a chart that has simply dimmed.
            <span className={`text-meta ${matches.size ? 'text-accent' : 'text-warn'}`}>
              {matches.size
                ? `${matches.size} node${matches.size === 1 ? '' : 's'} ${
                    highlightLabel && !query.trim() ? highlightLabel : 'match'}`
                : 'nothing matches — the chart is unchanged'}
              {query.trim() && (
                <button onClick={() => setQuery('')} className="ml-2 text-accent hover:underline">
                  clear
                </button>
              )}
            </span>
          ) : (
            <span className="text-meta text-faint">
              Arrow keys to move, Enter to open, Space to fold.
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">{controls}</div>
        </div>
      ) : (
        <PageHeader title="Graph" actions={controls}>
          {data.nodes.length} problems · {data.edges.length} connections. Drag to pan,
          scroll to zoom, click a node to open it.
        </PageHeader>
      )}

      {composing && (
        <Composer
          // `parentTitle` first: descending re-aims at a node the canvas has not
          // refetched yet, so byId cannot name it for another moment.
          parentTitle={composing.parent
            ? (composing.parentTitle ?? byId.get(composing.parent)?.title)
            : null}
          canTopLevel={!root}
          onTopLevel={() => setComposing({ parent: null })}
          onCreate={create} onCancel={() => setComposing(null)} onOpen={openNode}
          busy={creating} error={createErr} made={made} />
      )}

      {trail.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1 text-micro">
          <button onClick={() => setFocus(null)} className="text-accent hover:underline">
            whole chart
          </button>
          {trail.map((n, i) => (
            <span key={n.id} className="flex items-center gap-1">
              <span className="text-faint">/</span>
              {i === trail.length - 1 ? (
                <span className="text-dim">{n.title}</span>
              ) : (
                <button onClick={() => setFocus(n.id)}
                  className="text-accent hover:underline">{n.title}</button>
              )}
            </span>
          ))}
        </div>
      )}

      <div
        ref={frame}
        onWheel={onWheel}
        onPointerDown={e => {
          if (e.target.closest('g[data-node]')) return
          drag.current = { x: e.clientX - view.x, y: e.clientY - view.y }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={e => {
          // Read the ref ONCE into a local. The guard below used to protect a
          // functional updater that dereferenced `drag.current` a second time —
          // and React runs that updater after this handler returns, so a
          // pointerup landing in between nulled the ref and threw
          // "can't access property 'x', drag.current is null" mid-drag.
          const from = drag.current
          if (!from) return
          setView(v => ({ ...v, x: e.clientX - from.x, y: e.clientY - from.y }))
        }}
        onPointerUp={() => { drag.current = null }}
        // Without this a browser-initiated cancel (scroll takeover, focus loss)
        // leaves a stale drag origin, and the next move jumps the canvas.
        onPointerCancel={() => { drag.current = null }}
        // Height, not width, is what this chart runs out of — a 64-node tree is
        // ~1700px tall and ~1960 wide, so the frame's height sets the zoom and every
        // reclaimed pixel converts directly into legibility. Which is the whole case
        // for fullscreen: `min-h-0` is load-bearing there, because a flex child
        // defaults to min-height:auto and would refuse to shrink to its share, pushing
        // the legend off the bottom of a layer that cannot scroll.
        className={`cursor-grab overflow-hidden rounded-card border active:cursor-grabbing border-border ${full ? 'min-h-0 flex-1' : 'h-[82vh]'}`}
      >
        <svg width="100%" height="100%" role="img"
          aria-label={`${data.nodes.length} goals and their connections`}>
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            {tree.edges.map((e, i) => {
              const c = tree.placed.get(e.child), p = tree.placed.get(e.parent)
              const pt = tier(p.depth), ct = tier(c.depth)
              const x1 = p.x + pt.w, y1 = p.y + pt.h / 2
              const x2 = c.x, y2 = c.y + ct.h / 2
              const mid = (x1 + x2) / 2
              const on = hover && (e.child === hover || e.parent === hover)
              // An extra bearing is drawn only while one of its two ends is
              // hovered. These are the crossing lines — they ignore the layout and
              // cut across it, so at rest they read as noise over the tree the eye
              // is trying to follow. The fact that a goal is shared does not
              // disappear with them: the node keeps a permanent mark (below), so
              // this hides the *line*, never the information.
              if (e.secondary && !on) return null
              return (
                <path key={i}
                  d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
                  fill="none" strokeWidth={on ? 1.6 : 1}
                  strokeDasharray={e.secondary ? '4 3' : undefined}
                  className={on ? 'stroke-accent' : 'stroke-zinc-700'} />
              )
            })}

            {[...tree.placed].map(([id, p]) => {
              const n = byId.get(id)
              if (!n) return null
              const t = tier(p.depth)
              const folded = tree.hidden.get(id)
              // How many children the tree gives it — the test for "is this a branch",
              // which `folded` cannot answer for anything currently open.
              const branch = tree.owned.get(id) || 0
              // The node the drawer is showing stays lit while you hover elsewhere:
              // it is the one you are reading, and dimming it would break the only
              // thing tying the canvas to the panel beside it.
              // A miss recedes; it never disappears. Dropping non-matches from the
              // canvas would change the shape of the tree under you and hide the
              // structure that says where a hit sits — the thing you came to the
              // graph for. The selected node is exempt: it is what the drawer is
              // showing, and a search should not blank the node you are reading.
              // `matches?.size`, not `matches` — an empty Set is truthy, so testing
              // the object dimmed all 64 nodes the moment a query stopped matching
              // and left you rereading a greyed-out chart while you retyped. A
              // search with no hits changes nothing on the canvas.
              const missed = !!matches?.size && !matches.has(id) && id !== marked
              const dim = missed || (hover && !near(id) && id !== marked)
              return (
                <g key={id} data-node transform={`translate(${p.x},${p.y})`}
                  onMouseEnter={() => setHover(id)}
                  onMouseLeave={() => setHover(null)}
                  onClick={e => {
                    // A plain click opens the node beside the canvas when there is
                    // a drawer to open, and its page when there is not. Folding
                    // keeps the same click behind a modifier rather than losing it
                    // — the badge is only drawn once something is already folded,
                    // so it cannot be the way in.
                    if (e.altKey || e.metaKey || e.ctrlKey) { toggle(id); return }
                    // Deferred, because a double-click fires onClick TWICE before
                    // onDoubleClick lands: acting immediately meant the documented
                    // "double-click to focus" gesture could never run — it always
                    // left the page first. Still deferred with a drawer, where the
                    // cost is smaller but the same: the first click would open a
                    // node you only meant to zoom into. Cancelled below if a second
                    // click arrives inside the double-click window.
                    clearTimeout(clickTimer.current)
                    clickTimer.current = setTimeout(() => {
                      if (onPick) onPick(id)
                      else setInspect(id)
                    }, 220)
                  }}
                  onDoubleClick={() => { clearTimeout(clickTimer.current); setFocus(id) }}
                  className={`cursor-pointer transition-opacity ${
                    // A search miss recedes less far than a hover dim. Hover is a
                    // momentary "not this one"; a search can sit on screen for as
                    // long as you are reading, and the desaturated-palette verdict
                    // on this app was "hard to see".
                    missed ? 'opacity-40' : dim ? 'opacity-30' : ''}`}>
                  <title>{n.waypoint || 'no waypoint yet'}
                    {shares.get(id) > 0 && ` — also serves ${shares.get(id)} more`}
                    {lends.has(id) && ' — one of its subproblems is placed elsewhere'}
                    {' — click to read it beside the chart, ＋ to add a subproblem, '
                     + 'double-click to focus'}</title>
                  {/* Selection outranks hover: hover is where the pointer happens to
                      be, selection is what you are actually reading. A heavier ring
                      of the same colour rather than a second colour — these are the
                      same relationship at two strengths, not two different facts. */}
                  <rect width={t.w} height={t.h} rx="9"
                    className={`${STANDING[n.standing]?.fill ?? 'fill-surface'}
                      ${id === marked || hover === id || (matches?.size && matches.has(id))
                        ? 'stroke-accent'
                        : STANDING[n.standing]?.stroke ?? 'stroke-zinc-700'}`}
                    strokeWidth={id === marked ? 2.25
                      : matches?.has(id) ? 1.75 : hover === id ? 1.5 : 1} />

                  {/* Where the keyboard is. A dashed ring OUTSIDE the node's own
                      border rather than a heavier version of it: the cursor and the
                      selection are different facts and are routinely on different
                      nodes — you arrow past four problems while still reading the
                      fifth — so one must not read as a weaker grade of the other. */}
                  {id === cursor && (
                    <rect x="-3.5" y="-3.5" width={t.w + 7} height={t.h + 7} rx="12"
                      fill="none" strokeWidth="1.5" strokeDasharray="5 3"
                      className="stroke-accent/70" />
                  )}

                  {/* Running now. Drawn as a bar down the leading edge rather than
                      another corner glyph: at a glance you are looking for the few
                      nodes that are live, and an edge marker survives being read at
                      the zoom where titles have already stopped being legible. */}
                  {n.active && (
                    <rect x="2" y={t.h / 2 - 9} width="3" height="18" rx="1.5"
                      className="fill-accent" />
                  )}
                  {n.standing === 'done' && (
                    <path d={`M${t.w - 20},${t.h / 2} l3,3.5 l6,-7.5`} fill="none"
                      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
                      className="stroke-ok" />
                  )}

                  <text x="11" y={t.showWaypoint ? 22 : t.h / 2 + 4}
                    style={{ fontSize: t.title }}
                    className="fill-zinc-50">
                    {clip(n.title, Math.floor(t.w / (t.title * 0.55)))}
                  </text>

                  {t.showWaypoint && (
                    <text x="11" y={38} style={{ fontSize: t.sub }}
                      className={n.draft ? 'fill-warn' : 'fill-zinc-500'}>
                      {clip(n.draft ? 'no waypoint yet' : (n.waypoint || ''),
                            Math.floor(t.w / (t.sub * 0.54)))}
                    </text>
                  )}

                  {!t.showWaypoint && n.draft && (
                    <circle cx={t.w - 11} cy={t.h / 2} r="2.5" className="fill-warn" />
                  )}
                  {/* A sounding dot used to sit here. With soundings undrawn it
                      would have been a grey circle meaning nothing, so it went
                      rather than becoming decoration. The draft marker above and
                      the anchor bar below still carry real state. */}
                  {n.anchored && (
                    <rect x={t.w - 6} y={t.h / 2 - 7} width="3" height="14" rx="1.5"
                      className="fill-accent" />
                  )}

                  {/* The permanent half of the hover trade. The dashed lines are
                      gone at rest, so this is what says "there is more here than
                      the tree shows" — and it is what makes hovering discoverable
                      rather than something you had to be told about. */}
                  {(shares.has(id) || lends.has(id)) && (
                    /* r=2 at h-6, not 2.5 at h-7: on the 34px tier the title's
                       descenders end at 24.4 and the larger dot started at 24.5 —
                       clearance measured in hundredths of a pixel is not clearance. */
                    <g transform={`translate(6,${t.h - 6})`}>
                      <circle r="2" className={hover === id ? 'fill-accent' : 'fill-zinc-400'} />
                      {shares.get(id) > 0 && (
                        <circle cx="5.5" r="2"
                          className={hover === id ? 'fill-accent' : 'fill-zinc-400'} />
                      )}
                    </g>
                  )}

                  {/* Folding, as a thing you click.
                   *
                   * It was ⌥click and a count badge that only appeared once a branch
                   * was already folded — so the affordance for unfolding existed and
                   * the affordance for folding did not, and neither was discoverable
                   * without reading the legend. Now every branch carries the control
                   * in both states: a chevron pointing at the children it would hide,
                   * or the count of what it is hiding. ⌥click still works.
                   *
                   * `stopPropagation` on pointerdown as well as click: the frame
                   * starts a pan on pointerdown, so without it a click here dragged
                   * the canvas a pixel before folding. */}
                  {branch > 0 && (
                    <g transform={`translate(${t.w + 6},${t.h / 2 - 9})`}
                      onPointerDown={e => e.stopPropagation()}
                      onClick={e => { e.stopPropagation(); toggle(id) }}
                      onDoubleClick={e => e.stopPropagation()}
                      className="cursor-pointer">
                      <title>{folded > 0
                        ? `unfold — ${folded} hidden beneath`
                        : `fold ${branch} subproblem${branch === 1 ? '' : 's'} away`}</title>
                      <rect width="30" height="18" rx="9"
                        className={`stroke-zinc-700 ${hover === id
                          ? 'fill-accent/10 stroke-accent/40'
                          : 'fill-surface-2'}`} strokeWidth="1" />
                      {folded > 0 ? (
                        <text x="15" y="12.5" textAnchor="middle" style={{ fontSize: 10 }}
                          className="fill-zinc-400">{folded}</text>
                      ) : (
                        // Points at the children, i.e. at what clicking would fold away.
                        <path d="M12 5.5 L17 9 L12 12.5" fill="none" strokeWidth="1.6"
                          strokeLinecap="round" strokeLinejoin="round"
                          className="stroke-zinc-500" />
                      )}
                    </g>
                  )}

                  {/* Add a subproblem to THIS node, wherever the pointer already is.
                      The toolbar's ＋ has to guess a parent from what is open or
                      focused; this one cannot be wrong about it. Hover-only, because
                      a permanent ＋ on ninety nodes is ninety invitations, and the
                      selected node keeps it so the drawer you are reading still has
                      one. */}
                  {(hover === id || marked === id) && (
                    <g transform={`translate(${t.w + (branch > 0 ? 40 : 6)},${t.h / 2 - 9})`}
                      onPointerDown={e => e.stopPropagation()}
                      onClick={e => { e.stopPropagation(); addBeneath(id) }}
                      onDoubleClick={e => e.stopPropagation()}
                      className="cursor-pointer">
                      <title>add a problem beneath {n.title}</title>
                      <rect width="18" height="18" rx="9"
                        className="fill-accent/10 stroke-accent/40" strokeWidth="1" />
                      <path d="M9 5 L9 13 M5 9 L13 9" strokeWidth="1.6" strokeLinecap="round"
                        className="stroke-accent" />
                    </g>
                  )}
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      {/* Two paragraphs of instructions sat permanently under the canvas, which is
          the wrong trade on a height-bound diagram: you read them once and pay for
          them on every visit after. Folded, they cost one line and the space goes
          back to the chart. */}
      <button onClick={() => setLegend(v => !v)}
        className="mt-2.5 shrink-0 text-micro text-faint transition hover:text-accent focus-visible:outline-none focus-visible:ring-2
           focus-visible:ring-accent/60">
        {legend ? '▾' : '▸'} how to read this
        {full && <span className="ml-2 text-faint">· Escape leaves fullscreen</span>}
      </button>

      {legend && (<>
      <p className="mt-1.5 text-micro text-faint">
        Left to right: a problem sits to the right of what it serves. Click a node to open it
        beside the chart. On its trailing edge, a <strong className="font-medium">chevron</strong>
        folds that branch away and a <strong className="font-medium">number</strong> unfolds it,
        counting what is hidden; <strong className="font-medium">＋</strong> adds a subproblem
        under that exact node. ⌥click still folds, double-click makes a node the root, scroll to
        zoom, drag to pan. A node marked with dots serves — or is served by — something the tree
        cannot place beside it; <strong className="font-medium">hover it</strong> to draw those
        extra bearings as dashed lines.
      </p>
      <p className="mt-1.5 text-micro text-faint">
        <strong className="font-medium">Keyboard.</strong> <kbd>↑</kbd>/<kbd>↓</kbd> move through
        the chart in the order it is drawn; <kbd>→</kbd> unfolds a branch, then steps into it, and
        <kbd>←</kbd> folds one, then steps back out to what it serves. <kbd>Enter</kbd> opens the
        node the dashed ring is on, <kbd>Space</kbd> folds it, <kbd>/</kbd> jumps to the search
        box. Inside the composer, <kbd>Enter</kbd> adds another problem in the same place and
        <kbd>Shift-Enter</kbd> adds one and descends into it.
      </p>
      <p className="mt-1.5 text-micro text-faint">
        <strong className="font-medium text-accent">Open</strong> — nothing beneath it is
        outstanding, so it can be worked now. <strong className="font-medium">Blocked</strong> —
        waiting on a subproblem. <strong className="font-medium text-ok">Done</strong> — marked
        solved by hand; a parent is never solved just because its children are.
      </p>
      </>)}

      {/* Only when no host owns the selection. With `onPick` the Chart renders its
          own, and two drawers over one canvas would be the same node twice. */}
      {!onPick && inspect && (
        <FetchedDrawer id={inspect} title={byId.get(inspect)?.title || ''}
          base={byId.get(inspect)} rail={rail}
          onAddChild={row => addBeneath(row.id)}
          onReload={() => { load(); onCreated?.(inspect) }}
          onClose={() => setInspect(null)} />
      )}
    </div>
  )
}
