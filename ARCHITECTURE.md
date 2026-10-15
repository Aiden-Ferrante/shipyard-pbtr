# Architecture

One page, boundaries first. Every claim here was derived from the code on
2026-08-26 (`ast` over the backend, import scan over the frontend), not from
memory — where a rule is enforced by a script, the script is named.

## What it is

> *One pleasant front end over the tools that already hold the truth — it reads
> and writes them, and owns no complex logic of its own.*

That sentence is the architecture. Mission Control answers "is it running?";
shipyard answers "where is this in its life?". It owns exactly one thing — the
chart — and reads everything else from wherever that thing already lives.

## Modules and dependency direction

### Backend — a star, not a chain

```
                    main.py  (HTTP, IO fan-out, the only composer)
                       │
 ┌──────┬──────┬───────┼────────┬───────────┬──────┬─────────┐
chart  repo  survey  arguments  conventions  work  shelved  templates
```

**Rule: no domain module imports another.** Verified — all eight import nothing
from the package; `main.py` imports all eight. It was eleven until v0.29.3, when
`line`, `cadence` and `hill` went with the bands that read them: they measured the
operator rather than the fleet, and two of them measured nothing at all — the hill
table held zero rows and no problem ever carried a due date. A domain module takes values and
returns values; anything needing two of them is composed in `main.py`.

That is why `repo.owed()` is pure over already-computed values rather than
reaching for the chart, and why `/api/owed` is built on `project_view` instead of
beside it — two surfaces computing the same number is how they come to disagree.

*Not enforced by a script.* It holds today by discipline; if it ever breaks, the
test to write is the one `check-ui.mjs` already models for the frontend.

### Frontend — three layers, one enforced mechanically

```
views (App, board, fleet, goals, graph, project, problem, argument, doc, palette)
   │            │
   ▼            ▼
kit.jsx     outline.jsx        domain helpers · the product-AWARE node drawer
   │            │
   ▼            ▼
        ui.jsx                 visual primitives; imports nothing but React
```

`ui.jsx` is pure: no `fetch`, no upward imports. `kit.jsx` is **product-blind** —
it knows a stage chip and a relative date, nothing about boards or charts.
`outline.jsx` is deliberately product-**aware**: `ProblemDrawer`, the panel that
opens beside whichever surface drew the node, so reading a problem never costs you
the diagram you were reading it in.

**The chart is now drawn once.** There were two renderings — a canvas and a row
outline — at two scopes, and keeping them in step was a standing tax: every per-node
action had to be written twice or exist on one surface only, which is how "you can
add a problem from the project page but not rename it" happened. The goals page
dropped its outline first and `tree.jsx` followed; `outline.jsx`'s row geometry
(`Twisty`, `TitleCell`, `WaypointCell`, `DepthGuides`, …) went with its last caller
rather than remaining as a shared layout with nothing to share.

What replaces "share the layout, never the behaviour" is narrower and mechanical:
**one canvas, and a rail the host supplies.** `GraphPage` owns structure — pan, fold,
focus, create — and takes a `rail` render-prop for everything only the host knows.
The goals page owns its own drawer and passes `onPick`; the project page has none and
lets the graph own it, hanging `GoalRail` plus its cycle section off `rail`. Authoring
lives in exactly one component either way.

**Enforced by `frontend/scripts/check-ui.mjs`** (`make check`, and
`tests/test_ui_contract.py` asserts the checker catches a planted violation — a
checker with no negative test is decoration):

1. a view may not redefine a `ui` primitive
2. `kit.jsx` may not export a visual primitive
3. no hand-rolled loading text outside the primitive
4. no colour literals in components — tokens only
5. raw font sizes are a **ratchet** at 43: the count may fall, never rise
6. `ui.jsx` stays pure — no `fetch`, no upward imports

**Known gap, stated rather than hidden:** view→view imports are *not* checked, and
the convention has drifted past what was written down. Actual today:
`goals → argument, graph`, `project → graph, goals`, and `manual → fleet`. The old note claimed one
exception (`project → chart`); `chart.jsx` no longer exists, and `tree.jsx` has since
gone the same way. The newest edge — `project → goals`, for `GoalRail` — is the
deliberate price of the paragraph above: a second rail written in `project.jsx` would
have been the divergence this whole change removes. Either enforce the list as rule 7
or stop calling it a rule.

## Information hiding

- **`repo.py` invents no conventions.** Every value is read back out of things a
  repo keeps anyway — git tags, `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
  `docs/adr/`. A project that never opens shipyard still answers all of them.
  The one derived value is `running_behind`, derived precisely so no app has to
  report its own version.
- **`chart.py` hides its storage.** Callers get dicts; sqlite, the edge table and
  the cycle guard never leak upward.
- **Derived, never stored.** `standings()` (open/blocked/done), `focus_slots()`
  and `effective_sounding()` are computed at read time. A second column agreeing
  with `solved` is a column that will one day disagree with it.

## State — who owns what

| State | Owner | Notes |
|---|---|---|
| The chart (problems, edges, pins, solved, active) | **shipyard**, `data/*.sqlite` | The only thing it owns. Gitignored; mirrored one-way to `SHIPYARD_CHART_EXPORT` (default `data/chart.md`, gitignored) on every write. |
| Shelved repos | **shipyard**, same sqlite | Deliberate invisibility — the one opinion disk cannot justify, so the count rides on every `/api/board`. |
| Description, links, release scheme | **each repo's `PROJECT.yaml`** | Manifests *enrich* a project, they do not *admit* it. `stage` lived here until v0.29.3. |
| Runtime, ports, health | **Mission Control** `apps.yaml` | Read-only bridge; degrades to `{}` when MC is down, never 5xx. |
| Version, commits, docs, ADRs | **git and the filesystem** | Nothing cached. |
| Study progress | **Learn Hub** | Never duplicated here. |
| Collapse/filter view state | **the browser**, `localStorage` | `shipyard.board.hidden`, `.board.collapsed`, `.goals.shape`. About looking, not about data. |

## Writing outside itself — the short list

Shipyard is write-capable, and every outward write is deliberate and small:
`PROJECT.yaml` on adopt (surgical, never a YAML round-trip — `safe_dump` would
delete hand-written comments), cycle records into a repo's `docs/cycles/`,
argument markdown into `docs/arguments/`, template scaffolds, and
`docs/chart.md`. **When shipyard writes into a repo it follows that repo's
conventions, not its own.**

Reads are guarded: `read_document` resolves and follows symlinks *before* the
containment check, so neither escapes the project root.

## Boundaries that are load-bearing

- **Config binds to module constants at import.** `CODE_ROOT`, `DB_PATH` and
  friends are read once. Tests must patch the module attribute
  (`main.CODE_ROOT`), never the env var — patching the env has twice caused a
  test run to scan or overwrite real data.
- **A waypoint is required at the API boundary** (422), not as a UI hint. A
  problem with no observable is a category, and the boundary is where that is
  refused.
- **Grouped, never ranked.** Owed and the durable-memory view both group by kind.
  Road to 1.0 prunes anything that computes a score for a project; the guardrail
  has twice produced a better design than the thing it blocked.

## What this is not

Not a compliance enforcer — `standards.yaml` was deleted and shipyard holds no
opinion about what a good repo looks like. Not a task tracker (Backlog.md), not a
study tracker (Learn Hub), not a process supervisor (Mission Control). When a
feature would duplicate one of those, the answer is a read, not a table.
