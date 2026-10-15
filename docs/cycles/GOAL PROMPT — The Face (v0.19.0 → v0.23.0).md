# Goal Prompt — The Face

Super-cycle · shipyard `v0.19.0 → v0.23.0`
Drafted 2026-08-14. Fossilised on Build gate — corrections go to ADRs, never back-edits.

---

## 0. The protocol, inlined

*The vault's `Projects/` tree — including Development Protocol 1.0 — was archived 2026-08-14.
Rather than depend on an archived note, the mechanics this cycle actually uses are restated here.
This prompt is self-contained by its own spec; that now includes the protocol.*

**The atom — one cycle.**

```
   PLAN ────────► BUILD ────────► TEST ────────► REVIEW
   human          agent           both           human
   leads          leads                          leads
     ▲                                              │
     └────── retro → Backlog.md → next Plan ◄───────┘
```

A cycle is **atomic**: it passes all four phases and cuts a version, or it cuts nothing. There is
no version for "got through build and testing." If the re-plan valve fires mid-cycle, the cycle
aborts — learnings go to `Backlog.md` and a retro, no version is cut.

**The version bump is the transaction commit.** `CHANGELOG.md` is the write-ahead log; git tags
are the only durable record of finished work. *"Did I finish anything this month?"* → count the tags.

| Unit | Version move | Ends with |
|---|---|---|
| Commit | — | tests green |
| **Sub-cycle** (one atomic P→B→T→R) | **MINOR** `0.19.0 → 0.20.0` | CHANGELOG entry + tag + cycle record |
| Light cycle (fix / small addition) | PATCH | CHANGELOG line |
| **Super-cycle** (this whole arc) | MAJOR, eventually | the artifact made *visible* |

**Deliberately absent:** story points and velocity. Appetite replaces estimation; tags-per-month
is the only velocity. This binds §3 and forbids inventing a points system in §8's overview work.

**Where PBTR lives — settled in this cycle's planning conversation.** The loop attaches to a
**problem**, never to a project. A project has no status, no stage rollup and no super-cycle of
its own; it carries a **version number and nothing else**. Several problems may share one repo, so
a phase cannot be derived from that repo's git state — it is recorded per problem (D5).

**The navigation this implies:** board lists projects → click a project → that project's problem
chart → click a problem → the problem hub. Three levels, no fourth.

---

## 1. Problem

Shipyard holds the truth and renders it flatly. Eleven distinct facts — stage, version, decay,
owed work, runtime, coverage, waypoint-presence, subtree size — arrive in the same grey voice, so
none can be read at a glance. The predictable shape: every new fact makes the screen busier and
the signal weaker, and the cost of opening the app to answer *"what am I doing on this"* stays
high enough that the loop gets run from memory instead.

Concretely, three measured causes:

- **The design system exists and is 31% adopted.** `ui.jsx` exports 22 components; 5 of 16 view
  files import it. Eight views hardcode `<p className="text-sm text-zinc-400">loading…</p>` while
  `<Loading>` sits unused. `Chip` is defined twice (`ui.jsx`, `kit.jsx`) with different tone maps;
  status renders three ways (`StatusGlyph`, `Status`, `StatusDot`).
- **The chart carries almost no information per node.** `graph.jsx` is a good tidy-tree with
  pan/zoom that draws uniform boxes. 13 of 56 nodes have no waypoint and the chart does not show
  it; a 3-stub domain and a six-level curriculum render identically.
- **The problem page is missing the reasoning.** A problem records what it is and what would count
  as progress, but not the approaches considered, the one chosen, or whether it worked.

## 2. Vision + measuring stick

**Vision.** Shipyard is the surface where a problem's whole state — what it is, what you tried,
what you're trying, and how far round the loop it is — is legible without reading.

**North star.** From cold open, the time to answer *"what is the next action on problem X"* is one
click and no reading of prose.

**Guardrail.** *Confidently wrong is worse than unsure.* No visual encoding may imply evidence
that does not exist. A node with no waypoint must look empty, not neutral; a phase with no data
must look unknown, not incomplete. **The failure mode worse than absence is a chart that looks
complete because the renderer defaulted to solid.**

## 3. Constraints / appetite

**Appetite: five evenings, one per sub-cycle.** Appetite decides the D-points below — where a
choice is between a correct-but-large option and a boring-but-adequate one, appetite picks boring.

- No new runtime dependency. Tailwind v4 + React 18 as-is. No charting library.
- No backend rewrite. New columns and endpoints only.
- Every sub-cycle ends green on the existing 279 backend tests.
- Each sub-cycle is atomic: it cuts a MINOR or it cuts nothing.

## 4. Landscape

- **Buy:** charting libs (d3-hierarchy, visx, nivo) — **rejected**, see D2. `graph.jsx` already
  implements tidy-tree layout with pan/zoom/collapse; importing a library replaces working code
  with a dependency and a restyle.
- **Standards:** Shape Up (appetite — already in the protocol), View Transitions API (baseline in
  Chromium/WebKit; progressive enhancement, no polyfill).
- **Research:** icicle/sunburst for part-to-whole hierarchy; treemap rejected for deep shallow-leaf
  trees. Force-directed rejected on first principles — see D2.
- **The gap = the build:** nothing off the shelf knows about waypoints, soundings, PBTR or
  appetite. The encodings are domain-specific; only the layout math is generic, and that exists.

## 5. Decomposition

**AND-children** (all required for the super-cycle to close):

1. `v0.19.0` **Consolidation** — one design system, adopted everywhere.
2. `v0.20.0` **The problem hub** — approaches, chosen approach, verdict, PBTR, solved.
3. `v0.21.0` **Chart encodings** — fill/size/cross-link on both charts.
4. `v0.22.0` **Overview** — sunburst + growth-over-time.
5. `v0.23.0` **Craft** — transitions, keyboard model, motion, elevation, accent discipline.

**Pruned children** (not forgotten — this is the v2 list):

| Pruned | Why |
|---|---|
| Charting the other 16 projects | The user's own work, not the app's. Deliberately theirs. |
| A new `loop_closed` table | The protocol already says *count the tags*. Git tags are the durable record; a second store would drift from them. |
| Frontend test framework | Real, but its own cycle. Adding Vitest mid-face-lift blows the appetite. |
| Path routing / `{path:path}` SPA fix | Belongs to the platform merge, not here. Hash routing stays. |
| Splitting `goals.jsx` (1,468 lines) | Tempting during consolidation. Out — it is a refactor cycle with its own risk. |
| Appetite-vs-actual tracking | Wanted, but needs cycle timestamps that do not exist yet. v2. |
| Fleet-wide component sharing | `fleet-ui` is CSS-only by design (no build step). Components stay in shipyard. |

## 6. Decision points

**D1 — Where do shared components live?** → **`ui.jsx`, extended in place.**
*Rejected:* a new `components/` tree (churn without benefit this cycle); moving them to `fleet-ui`
(that repo is deliberately zero-build, zero-dependency — React would force a build step on a
library whose whole value is not having one).
**Consequence:** `kit.jsx` becomes domain-helpers-only. Its `Chip` and `StatusDot` are deleted;
callers move to `ui.jsx`. Where the two implementations disagree, **`ui.jsx` wins** — it has the
accessibility work (`role`, roving `tabIndex`, focus-visible).

**D2 — Chart layout.** → **Keep the existing tidy tree; add encodings.**
*Rejected:* force-directed (nodes move between renders, destroying spatial memory, and it discards
real hierarchy); radial tree as the primary view (labels collide past ~40 nodes); a charting
library (D2 landscape).
**Basis:** measured — 54 of 56 nodes have exactly one parent, 1 has two. The chart is a tree with a
single cross-link. Do not pay for DAG-general layout.

**D3 — What records a closed loop?** → **The git tag. Nothing new.**
*Rejected:* a `loop_closed` table (duplicates the tag and will drift from it).
**Consequence:** "loops closed" views read tags via the existing cycles endpoint.

**D4 — Where do approaches live?** → **A new `problem_approaches` table.**
`(id, problem_id, name, rationale, chosen INTEGER, verdict TEXT NULL, created_at, updated_at)`
*Rejected:* a JSON column on `problems` (unqueryable — "show me every approach that failed" is the
whole point of recording them); markdown in `docs/` (the argument essays already occupy that
niche and are prose, not enumerable).
**`verdict`** is the field that makes this a learning tool rather than a planning tool:
`null` (untested) · `worked` · `failed` · `abandoned`. A failed approach is a **result**, and must
survive the radio button being moved to another option.

**D5 — Solved and PBTR marks.** → **Five booleans on `problems`.**
`solved, phase_plan, phase_build, phase_test, phase_review` + `solved_at TEXT NULL`.
*Rejected:* a separate phase table (over-modelled for four booleans); deriving PBTR from git
(tried and rejected in mockup — git says what happened to a *repo*, and a phase belongs to a
*problem*; several problems share one repo).

**D6 — Overview shape.** → **Icicle, with a sunburst toggle.**
*Rejected:* treemap (bad for deep trees with small leaves); sunburst-only (labels illegible past
three rings — icicle keeps horizontal text at every depth).
**Boring-option clause applies:** if the icicle costs more than one evening, ship the growth
timeline alone and defer the icicle to v2. The timeline is the higher-value half — it uses
`created_at`/`updated_at`, which are already stored and entirely unused.

**D7 — Do project charts get the same treatment as the goal chart?** → **Yes, identical.**
*Basis:* the current project charts are small (manalab 8 nodes) **only because they are
partially charted**. They are expected to grow to the same scale. Build both to the goal chart's
scale from the start. **Do not special-case small charts.**

**D8 — Accent discipline.** → **`--color-accent` means interaction and nothing else.**
Sounding, stage, status and phase all move to their own hues. *Rejected:* keeping the current
overload (it is exactly why status and affordance blur today).

## 7. Architecture style + dependency rule

**Style:** a flat view layer over one component module. No new directories this cycle.

> **Dependency rule:** `ui.jsx` ← `kit.jsx` ← views. `ui.jsx` imports nothing from the app.
> `kit.jsx` holds domain helpers and **no visual primitives**. A view file may not define a
> component whose name is exported by `ui.jsx`.

**Mechanically checked** by `frontend/scripts/check-ui.mjs`, run in `make check` and as a pytest
case so it fails the suite, not just a lint someone forgets:

1. no `export function <Name>` in a view file where `<Name>` is exported by `ui.jsx`
2. no `import ... from './kit'` of a name in the ui-primitives list
3. zero occurrences of the string `loading…` outside `ui.jsx`
4. no raw hex or `oklch(` literal outside `styles.css`
5. `ui.jsx` contains no `fetch(` and no import from any view

**The checker owes a negative test** — a fixture with a deliberate violation that it must catch. A
checker with no negative test is decoration.

## 8. Docs set

**Written:** `CHANGELOG.md` entry per sub-cycle · one cycle record per version in `docs/cycles/`
(the protocol's Review gate) · ADRs for **D1, D2, D3, D4, D6, D8** via `codebase-memory-mcp`.

**Deliberately absent:** no `ARCHITECTURE.md` (the platform merge owns that) · no component
storybook (16 files, one reader) · no design-token doc (`fleet.css` is the token contract and
already documented in `fleet-ui/README.md`).

## 9. Test fixtures

- **Backend:** the 279 existing tests stay green at every commit. New: migration idempotency
  (apply twice, same schema); `problem_approaches` CRUD including *"a failed verdict survives
  `chosen` moving to another row"*; PBTR/solved round-trip.
- **Chart fixtures:** three hand-built trees — (a) a leaf with no waypoint, (b) a 6-deep chain,
  (c) the real cross-link (`Professional Networking` under two parents). Assert the encoder
  returns `empty` fill for (a) and one accent edge for (c).
- **Checker:** the negative fixture from §7.
- **Browser verification** per sub-cycle (there is no frontend test runner and adding one is
  pruned): load the app, exercise the surface, read the console, screenshot.

## 10. Commit ladder

**v0.19.0 Consolidation** — (1) delete `kit.Chip`/`kit.StatusDot`, repoint callers · (2) replace 8
hardcoded loading strings with `<Loading>` · (3) route the 11 non-adopting views through `ui.jsx`
· (4) add `check-ui.mjs` + negative fixture + wire into `make check` · (5) accent discipline (D8).

**v0.20.0 Hub** — (1) migration: 5 booleans + `solved_at` + `problem_approaches` · (2) endpoints:
`PATCH /api/problems/{id}/phases`, `PATCH .../solved`, CRUD `.../approaches` · (3) hub view:
what-it's-about, approaches with radio + verdict, why-this-one, PBTR checkmarks, subproblems ·
(4) board shows `n/m solved` + version only.

**v0.21.0 Encodings** — (1) `encode(node)` → `{fill, size, kind}` pure function + fixtures ·
(2) apply in `graph.jsx` · (3) cross-link edge styling · (4) same encoder in `tree.jsx` gutter.

**v0.22.0 Overview** — (1) growth timeline from `created_at` · (2) icicle behind a toggle
(boring-option clause per D6).

**v0.23.0 Craft** — (1) motion vocabulary (one easing, 120ms state / 180ms panel) · (2) View
Transitions on board→chart→problem · (3) keyboard model `j/k`, `space`, `Enter`, `Esc` ·
(4) optimistic writes on every toggle · (5) elevation pass.

## 11. Definition of done

The super-cycle closes when **all five tags exist** and:

- [ ] `ui.jsx` is imported by every view that renders a primitive; `check-ui.mjs` green, negative fixture caught
- [ ] one `Chip`, one status renderer, zero hardcoded `loading…`
- [ ] a problem records approaches, which one is chosen, and a **verdict** on it that survives re-selection
- [ ] PBTR marks and solved persist across reload
- [ ] a waypointless node is visually distinguishable from a waypointed one **without hovering**
- [ ] the cross-link renders as one accent edge; no node appears twice
- [ ] board rows show name, description, `n/m solved`, version — **no status**
- [ ] 279 backend tests green; new tests for approaches, phases, migration idempotency
- [ ] `--color-accent` appears only on interactive elements
- [ ] every toggle paints before the network returns
- [ ] each version has a CHANGELOG entry, a cycle record, and a tag

**Gate to Build:** this prompt is fossilised, and it would build the same thing in anyone's hands.
