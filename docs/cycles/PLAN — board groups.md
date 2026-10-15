# Plan — board groups

Light cycle. Appetite: **one evening.** PATCH-level: no new concept, one missing affordance.

## Problem

Three asks — delete a group without deleting its projects, add a group from the goal chart, drag
projects between groups — read as three features. Measured, they are **one**.

A board section already *is* a chart node: a section is a **pinned** problem. And the board already
reparents on drop (`board.jsx:134` `reparent()`, `:204` `onDrop`, `PUT /api/problems/{id}/parent`).

So the backend needs **nothing new**. What is missing is that the control lives on the wrong page:
`PUT /api/problems/{pid}/pin` is called only from `goals.jsx:650`, so managing the board means
leaving the board, finding the node in a 56-row outline, pinning it, and coming back.

## Vision + measuring stick

**North star:** add a group, remove a group, and move three projects between groups without leaving
the board.

**Guardrail:** removing a group must never touch its projects. Unpinning changes no edges — the
children keep their bearings and simply stop having a heading. If a "delete group" ever removes a
problem, that is the failure; the word *delete* should not appear in the UI at all. Use **remove**.

## Decisions

**D1 — A group is a pinned chart node. Do not introduce a group entity.** Two registries for one
concept is the drift this repo keeps finding (`sounding` vs `why` for "uncharted", four `slug`s).
*Rejected:* a `board_groups` table — it would need syncing with the chart forever.

**D2 — Add-group is a picker over unpinned chart nodes**, modelled on `Bearings`
(`goals.jsx:480-513`): filter input + ancestor path per row. That component exists **because**
forty-five bare pills is not a chooser (`goals.jsx:477`).
*Rejected:* copying `Copy`'s picker (`goals.jsx:370-381`) — still 45 bare pills; it is the
abandoned version, not the good one.

**D3 — Remove-group is unpin, worded as "remove".** Show what survives: *"Remove this heading? Its
N projects keep their place in the chart."* No confirm modal — unpin is one click to undo, and the
board already has three delete confirmations with three different phrasings (sweep, Consistency).

**D4 — Drag gets a visible handle and a drop-target highlight.** The mechanism works today; the
affordance does not exist, which is why it does not feel built. `board.jsx:205` already styles
`dragOver` — it just fires late, once you are over the target.

## Commit ladder

1. Group header gains a **remove** action → `PUT /api/problems/{pid}/pin {pinned:false}`, optimistic.
2. **Add group** button → picker over unpinned nodes (D2), pin on select.
3. Drag handle on the card + drop-target highlight on every section while a drag is in flight.
4. Empty-group state: a pinned node with no projects should say so and offer the picker.

## Definition of done

- [x] Add, remove and re-home without leaving the board
- [x] Removing a group leaves every project on the chart — assert edge count unchanged in a test
- [x] The picker filters and shows ancestor paths (not bare pills)
- [x] Every section highlights as a drop target while dragging, not only on hover
- [x] No new table, no new endpoint
- [x] `make check` clean, tests green, CHANGELOG + tag

Ladder step 4 (empty-group state) was **not** built: an empty group already says
"nothing serves this yet", and the picker it wanted is a *project* picker, not the
group picker this cycle added. Different widget, not in the measuring stick.

## What the measuring stick got wrong

"Assert edge count unchanged" was the wrong test, and it passed while the feature
was broken. Removing a `<domain>` group cost zero edges **and** dropped its four projects off
the board — because a card was only ever placed under its nearest *pinned* ancestor,
and unpinning left them with none. The guardrail was written about the chart when
what it needed to protect was the board.

The board's own docstring already had the right words — *"nothing on disk is ever
silently absent from this board"* — and the fix is `ungrouped`, the bucket that
sentence implied. A test asserting a **project stays visible** replaces the one
asserting an integer did not move. Both are kept; only the second has teeth.

## Watch for

`board.jsx` load has no `.catch` (`:130`) — the sweep's P0 pattern, not fixed there. Do not add
optimistic writes on top of a fetch that cannot report failure; fix the load first or the board
will silently show a stale group after a failed pin.
