# Plan — the goal inspector

Next sub-cycle. Appetite: **two evenings** — see D6; the original one-evening estimate
predates the rail decision.

## Problem

Writing a goal's description costs you your place in the chart. Three surfaces do the same job in
three ways, and all three navigate away from the tree you are editing:

- `#/problem/<id>` — a full page
- `#/argument/<id>` — another full page
- `goals.jsx:1458` — a modal rendering the *same* `ArgumentPage` as the route above

For a 56-node tree being filled in node by node, losing your position on every write is the whole
friction.

## Vision + measuring stick

**North star:** describe five nodes in a row without the chart leaving the screen.

**Guardrail:** the drawer must never be the *only* way to reach a problem. `#/problem/<id>` stays
a working deep link — a drawer that swallows the URL makes a node unshareable and unbookmarkable.

## Decisions

**D1 — Drawer, not modal.** A centred popup blocks the tree you are navigating, which defeats the
point. A right-hand drawer keeps the outline readable and lets you compare — reading a parent's
waypoint while writing a child's is when descriptions actually get written well.
*Rejected:* modal (blocks the tree), inline expand (reflows every row below).

**D2 — Reuse `ui.jsx`'s `Inspector`.** It already does `role="dialog"`, focus-on-mount and
Escape-to-close, and it is the only drawer in the app that handles all three. `fleet.jsx:386`
already uses it for repos, so this is a port, not a design.
*Rejected:* a new component (this is exactly how the two-Chip problem started).

**D3 — Selection lives in the URL as a query, not a route.** `#/goals?node=<id>`. Reload keeps the
drawer open on the same node; back closes it. Keeps `#/problem/<id>` untouched as the full page.

**D4 — Fields: description, waypoint, falsifier.** The three that make a node real. Save on blur,
optimistic. **Not** the argument essay — that stays its own page; it is prose, not a field.

**D5 — Retire the goal-window modal** (`goals.jsx:1458`) in the same cycle. Leaving it means two
ways to open the same content, which is the drift this replaces.

**D6 — The rail is retired; its controls move into the drawer as facets.**

`goals.jsx`'s rail holds `LinkRepo`, `Templates`, `Copy`, `Bearings` (structural — where the node
sits and what is attached) and `ArgumentPanel` (content — waypoint + argument précis). It already
mixes the two. A drawer that takes only the content half leaves the structural half behind, which
is not a boundary but a split down the middle of one job — and it is exactly the fourth editing
surface this cycle exists to prevent.

*Rejected: drawer owns content, rail keeps structure.* It sounds principled and is not. Both
surfaces attach to the same selected row and both sit beside the outline, so you would be asking
"is this a content edit or a structural one" on every change — a question with no stable answer.
Linking a repo is structural, and also the single most descriptive fact about a problem.

`Inspector` already exports `Facet` and `KeyValues` for this. One drawer, several facets, which is
also what the definition of done requires.

**Cost, stated rather than discovered later:**
- This is **two evenings, not one**. The appetite above is wrong and should be re-set at Plan.
- `Bearings` (`goals.jsx:480–513`) has the filter-and-ancestor-path chooser that `Copy` never got.
  Moving it must not lose that — `Copy` is still 45 bare pills and must not become the template.
- Commit 4 changes from "delete the modal" to "move five controls, then delete the rail".

## Commit ladder

1. `Inspector` opens from a goals row; renders title, waypoint, description read-only. No writes.
2. `#/goals?node=<id>` — open, close, reload, back.
3. Editable fields, save on blur, optimistic with rollback on failure.
4. Move the rail's five controls into the drawer as facets (D6), then delete the rail
   and the goal-window modal.
5. Keyboard: `Esc` closes (free from `Inspector`), `j/k` moves selection with the drawer following.

## Definition of done

- [ ] Five nodes described without the chart leaving the screen
- [ ] `#/problem/<id>` still works as a full page and is still linked from the drawer
- [ ] Reload with the drawer open restores the same node
- [ ] Exactly one drawer implementation in the app (`ui.jsx` `Inspector`)
- [ ] `goals.jsx:1458`'s modal is gone
- [ ] A failed save shows the failure and restores the previous value — it must not
      silently keep the optimistic text (see `a4255e1`: a failure must not assert success)
- [ ] `make check` clean, tests green, CHANGELOG + cycle record + tag

## Watch for

`goals.jsx` is 1,468 lines and the largest file in the repo, and D6 puts the rail migration inside
it. That is the risk in this cycle — not the drawer, which is a port of `Inspector`.

Two edits in this file broke the build on 2026-08-14, both from brace-matching a function whose
parameters are destructured. Extract by line range or by hand; do not match braces from
`function NAME(`.
