import React from 'react'
import { Chip, Facet, Inspector, Loading } from './ui'

/* The shape of one problem's DETAIL, shared by every surface that draws the chart.
 *
 * This file used to hold two things: the geometry of an outline ROW, and the panel
 * that opens beside a node. The rows are gone — the goals page dropped its outline
 * first, the project page followed, and both now draw the chart once, as a canvas.
 * `DepthGuides`, `RowIndent`, `Twisty`, `TitleCell`, `titleType`, `WaypointCell`,
 * `StandingDot`, `TITLE_COL` and `INDENT` went with their last caller rather than
 * staying behind as a layout nobody lays out, which would have left the next reader
 * believing two surfaces still shared a row shape.
 *
 * What is left is the half that turned out to be the durable one. The drawer arrived
 * late and in the wrong place — written inline on the goals page, then copied into
 * the graph — and each surface that missed it was a surface where reading a node cost
 * you the diagram you were reading it in. Layout only: fetching is the caller's,
 * which is why it takes a node rather than an id.
 *
 * Imported by pages; imports only React and `ui` primitives. Not in `kit` — kit is
 * product-blind primitives, and a panel that knows what a waypoint is has an opinion.
 */

/* One problem, read beside whatever drew it — outline row, graph node, project tree.
 *
 * ONE definition for all three: these were the same five facets written twice
 * already, which is how the two-Chip problem started. It takes a node in hand, never
 * an id, so this file stays layout-only — a caller holding just an id (a graph, whose
 * /api/graph payload is layout and carries no prose) does its own fetch and passes
 * the result down. `title` covers that caller's gap while its fetch is in flight,
 * since the panel was opened by clicking a title already on screen. */
/* `children` is where a host puts what only it can offer. The Chart hangs a
   node's whole authoring surface there — rename, add, delete, bearings, repo,
   templates — because with the outline gone the drawer is the only per-node
   place left, and a second panel beside the canvas would rebuild the clutter
   removing the outline was meant to end. A project's tree passes nothing and
   keeps a read-only drawer. */
export function ProblemDrawer({ node, title = '', pending = null, onClose, children = null }) {
  const n = node
  return (
    <Inspector title={n?.title || title} onClose={onClose}
      badge={n?.repo ? <Chip mono>{n.repo}</Chip> : null}>
      {/* A caller that had to fetch says so here; one holding the row already
          never renders this branch at all. */}
      {!n && (pending || <Loading />)}
      {n && (
        <>
          <Facet label="Waypoint">
            {n.waypoint
              ? <p className="text-meta">{n.waypoint}</p>
              : <p className="text-meta text-warn">
                  Nothing here says what progress would look like.
                </p>}
          </Facet>
          <Facet label="Description">
            <p className="whitespace-pre-wrap text-meta text-dim">
              {n.description || <span className="text-faint">Nothing written yet.</span>}
            </p>
          </Facet>
          {n.falsifier && (
            <Facet label="Falsified by">
              <p className="text-meta text-dim">{n.falsifier}</p>
            </Facet>
          )}
          <Facet label="Beneath">
            <p className="text-meta text-faint">
              {n.child_count || 0} problem{n.child_count === 1 ? '' : 's'}
            </p>
          </Facet>
          <a href={`#/problem/${encodeURIComponent(n.id)}`}
            className="text-meta text-accent hover:underline">
            Open the full page →
          </a>
          {children}
        </>
      )}
    </Inspector>
  )
}
