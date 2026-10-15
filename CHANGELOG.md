# Changelog

All notable changes to shipyard are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions are cut per completed
P→B→T→R cycle (see the vault's Development Protocol) — the tag is the transaction
commit.

## [Unreleased]

## [0.36.1] — 2026-09-05 — gates.open answers for the leaf

### Fixed
- `GET /api/direction` evaluated the open gate on the repo's *owning* problem, which for every board repo composes — so the gate's umbrella exemption made `gates.open.ok` true even with a leaf's cycle in flight. Direction now asks the gate as a leaf would (`_open_gate_reason(..., as_leaf=True)`); the gate itself is unchanged, and a composing problem still opens its umbrella cycle freely.
- `tests/test_direction.py` cleanup deletes the record file, not just the version link — an unlinked record still counts as planned, which polluted the module-scoped world.

## [0.36.0] — 2026-09-05 — would_refuse names only the next step

### Changed
- `GET /api/direction` scopes `would_refuse` to the gate the caller is about to hit: with no cycle open, the open gate; with one open, the review gate. Both gates stay under `gates`. Owed work with no cycle open no longer turns `next` away from "clear" — it is the review gate's business, later. From the fleet bench (fleet v0.4.0): an agent about to open a cycle stopped because *closing* would have been refused.

### Removed

- **The task write-back helper, and the `backlog` CLI shell-out under it.**
  `_task_write()` in `main.py` attached or detached a task from a problem by writing
  a label into another repo's `backlog/` through `work.set_label()`. Its two routes
  (`POST`/`DELETE /api/projects/{pid}/tasks/{tid}/problem`) were pruned on 2026-08-14
  (`fea68d0`, sweep step B1) after their UI went in `c1f2405`; the helper survived
  that prune because its message counted `set_label` as "still called from main.py"
  — the caller it counted was `_task_write` itself, already stranded. Dead since
  8/14, gone now, with `WriteError`, `cli_available`, `_run`, `set_label`, their
  four tests, and the `shutil`/`subprocess` imports in `work.py`. The read side
  (`read_tasks`, `attach`, `subtree`, `slug`) is untouched.

  **This is a decision, not cleanup.** Fleet `CONVENTIONS.md` §3 holds that
  shipyard's cross-repo writes are legitimate, and this was one of them. It is
  removed because it had no caller for three weeks and no target: no repo under
  `code/` has a `backlog/` directory today (glm-harness, the one that did, was
  deleted 2026-09-04). §3 stands — `PROJECT.yaml` on adoption and the vault paths
  are unchanged. If task-labelling from the dashboard comes back, it comes back
  through the CLI, per the rule kept as a comment in `work.py`.

## [0.35.0] — 2026-09-05 — a destructive write proves it read its impact

### Added
- **Impact tokens** (`tokens.py`): `GET /api/problems/{pid}/deletion` and `GET /api/problems/{pid}/impact` return a `token`; `DELETE /api/problems/{pid}` and `DELETE /api/problems/{pid}/anchor` refuse 422 without it, naming the read to make. Single use, ten minutes, invalidated when the impact changes between the read and the write. The same module is copied verbatim into mission-control (stop app, delete model) and learnhub-core (delete course).

### Changed
- The goals board and the problem page pass the token from the impact they already fetched; a failed read is now a refusal with its reason, never a blind delete.

## [0.34.0] — 2026-09-04 — an agent's session is a record

### Added
- **The session ledger** (`ledger.py`, ADR 0006): `sessions` and append-only `session_events`, `problems.updated_by`; `X-Actor` read by middleware; anchor, thaw, cycle open/link, phase ticks and problem writes record themselves under a `claude-code:<session>` actor. Routes: `POST /api/sessions`, `PATCH /api/sessions/{sid}`, `POST /api/sessions/{sid}/events`, `GET /api/sessions[?repo&since&limit]`, `GET /api/sessions/{sid}`.

## [0.33.0] — 2026-09-04 — a repo can ask what it is directed to do

### Added
- **`GET /api/direction?repo=`** — the read an agent makes before any work: the problem that claims the repo, its bearing, the focus occupant, any open cycle, what `open` and `review` would refuse today, one `next` sentence. Computed by the same functions the write routes raise from, so "would be refused" is "is refused".

### Changed
- `_open_gate` / `_review_gate` are thin wrappers over `_open_gate_reason` / `_review_gate_reason`.

## [0.31.1] — 2026-08-26 — A sub-problem can cut its own version

The first cycle in this repo opened against a sub-problem rather than a project
node — which is the fix, demonstrating itself.

### Fixed

- **`nearest_repos()` looks up when nothing is below it.** It searched downward
  only: a problem carrying a repo answered for itself, a goal inherited from the
  nearest repo beneath it, and nothing looked up. Since one repo belongs to exactly
  one problem, the repo sits on the project node and every sub-problem under it was
  refused with *"no repo beneath this problem"*.

  The refusal was not the cost — the workaround was. Four cycles were opened against
  the project node instead, and by v0.31.0 that had begun moving version numbers: a
  light cycle's work cut as a MINOR because only a branch could hold a cycle. The
  chart's shape was choosing the weight, which is backwards.

  Downward still wins whenever it finds anything, so composition is untouched — a
  goal offers what it decomposes into and never a bearing's own tag. Upward walks
  **only your own ancestry**, breadth-first, stopping at the first generation that
  carries a repo: a sibling of a project is not part of it.

  **It was blocked on a precondition that had already shipped.** `Backlog.md` said
  inheritance was unsafe because two siblings would propose the same next version;
  `_open_gate` (v0.29.1) refuses a second open cycle per repo, so the collision
  cannot happen — and `versions_claimed_in()` now resolves more problems per repo,
  so the proposal gets more careful rather than less. The blocker had been retired
  one cycle before the entry recording it was written.

### Added

- **Seven tests.** Five on the chart: inheritance, that downward still wins, that it
  stops at the nearest ancestor, that a sibling inherits nothing, and that an
  abstract leaf still offers nothing. Two end to end: a leaf reports `role=leaf`,
  `bump=patch`, opens, and writes a record saying `Light cycle`; and two
  sub-problems sharing an inherited repo — the second refused, which is the
  collision the backlog worried about, asserted rather than argued.

  Verified by removing the fallback: exactly the two inheritance tests go red. The
  other three pass either way, correctly — they assert what must **not** change.

## [0.31.0] — 2026-08-26 — Standards and docs, on their own pages

### Added

- **A tab strip at the top of the Yard: the yard · standards · what this is.** Two
  new pages behind it, both reads of endpoints that already existed — nothing here
  was built so much as given a door.

- **Standards, on its own page** (`#/standards`). What this fleet runs on and which
  rules have teeth, from `/api/conventions`. It had been a collapsed section at the
  very bottom of the Yard, which is where a convention goes to be indistinguishable
  from one that does not exist.

- **A manual** (`#/docs`). What shipyard is for as four questions and four
  refusals, plus shipyard's own README, ARCHITECTURE, CHANGELOG and ADRs — the same
  list the project card renders, opened through the same `DocPage` reader, so there
  is one rendering of a document rather than two that can disagree.

### Changed

- **`StandardsBand` is gone from the Yard.** v0.29.3 gave that page the waypoint
  *"shows the queue, the gate, and receiving, and nothing else"* and left the
  standards band underneath all three. The waypoint decided this, not a preference.

- **A document closes with `history.back()`.** It now has two entrances — the
  project card and the manual — and a fixed destination stranded whoever came from
  the other. Same call `ProblemPage` already makes.

- **Receiving renders at zero.** `Importable` returned `null` when nothing was
  waiting, so the map's Receiving tile scrolled to an element that did not exist.
  Harmless when receiving was one of five stages; it is now one of three, and a dead
  tile in a three-stage map is the map lying. Deliberately unlike an empty bay, which
  stays hidden because nothing points at it.

### Known limitation — the same one, and now it moved a version number

`Backlog.md`'s first entry is that a sub-problem beneath a repo node cannot open a
cycle. This cycle hit it on the first try: **Shipyard explains itself** was created
as a leaf, and opening a cycle against it was refused with *"no repo beneath this
problem"*. The cycle was opened against the branch instead — which is why this is a
MINOR sub-cycle and not the PATCH light cycle the work actually was.

The chart's shape is now choosing the version number, which is backwards. Repo
inheritance should come before any further feature.

## [0.30.0] — 2026-08-26 — Directed work

The sub-cycle that composes v0.29.1, v0.29.2 and v0.29.3. Shipyard now refuses a
cycle that starts undirected as firmly as it refuses one that closes sloppily, the
Yard asks one question, and shipyard is on its own chart.

### Changed

- **`main` is prod again.** It had been nine commits behind `dev`, including the
  v0.29.0 tag, while `docs/adr/0002-branching-model.md` and the README both said it
  was what Mission Control runs. Promoted before the arc began, along with a merge
  of the stranded one-repo-one-problem fix.

- **shipyard's manifest** no longer advertises "stages, checklists, links" — two of
  those three are gone. It describes what the app now is: the chart that says why
  each repo exists, the gate that says what may start, and the cycles that close.

### Known limitation, recorded rather than papered over

**A sub-problem beneath a repo node cannot open a cycle.** `chart.nearest_repos()`
searches downward only — a problem carrying a repo answers for itself, and one above
the project layer inherits from the nearest repo below it. Nothing looks up. Since
one repo belongs to one problem, the repo sits on the project node and every
sub-problem under it is refused with *"no repo beneath this problem"*.

This arc's own three leaf tags were therefore cut at the shell and linked afterwards
through `POST /api/problems/{id}/cycles`, which does not check repos — the arc
routing around its own rule on its first run, which is close to what this problem's
falsifier predicted. Repo inheritance changes what `versions_claimed_in()` has to
prevent, so it is not being fixed inside a closing cycle. See `Backlog.md`, whose
first three entries this arc wrote.

## [0.29.3] — 2026-08-26 — The Yard answers one question

Third light cycle of the **Directed work** arc. Mostly deletion.

### Removed

- **The half of the Yard that measured the operator.** The line, the portfolio, the
  rhythm heatmap and the hill are gone, with `line.py`, `cadence.py` and `hill.py`,
  `GET /api/projects/{pid}/line`, `POST /api/hill`, `GET /api/hill/{repo}`, the
  `groups`/`heat`/`targets` keys, and the `hill_snapshots` table. **Eleven domain
  modules became eight**; the star rule still holds over all of them.

  Deleted rather than hidden because the measurement was honest about itself:
  `hill_snapshots` held **0 rows** and **0 problems** ever carried a `due` date. The
  page was rendering two instruments that had never taken a reading.

- **`stage`, field and all.** It was the dial `standards.yaml` used to decide which
  bands of requirement a repo owed; that file went in v0.5.0 and the field outlived
  its meaning by twenty-four versions, rendering as a coloured word nothing read.
  Gone from `write_manifest`, the adopt route, every payload, the palette's search,
  and the `stage-spike/tool/product` colour tokens. `StageChip` and `MaturityChip`
  collapse into one component — they had been the same thing twice, fed by `main.py`
  aliasing `stage` to `maturity`.

  **The fleet's 33 manifests keep their `stage:` lines.** A key nothing reads is
  inert; a sweep would dirty thirty-three working trees at once and trip the review
  gate fleet-wide for a cosmetic change.

### Added

- **A cycle chip in the slot `stage` left**, with the gate's two answers: `43
  cycles` when nothing is running, `cycle open` when a record is in flight — which
  is exactly when `_open_gate` refuses a second. It reads `planned`, the same field
  the gate does, so the chip and the 422 cannot disagree. `_cycle_counts` rides
  `_repo_facts`, the TTL-cached bundle, because `repo.cycles()` shells git per repo.

- **`docs/adr/0005-what-an-open-cycle-is.md`** — what records an open cycle
  (`planned`, on disk, never a column) and which cycles contend (those that compose
  nothing, by `chart.children()` rather than `chart.role()`). ADR 0004 gains a
  superseding note: two of its four facts are withdrawn, and its routing test — a
  declaration goes in the manifest, an opinion about attention goes in sqlite —
  survives them.

### Changed

- **The bays came back, under the gate.** v0.29.0's ledger had displaced them,
  grouping the same repos by motion instead of by what blocks entry — a different
  question wearing the same heading. Deleting the ledger would have deleted the only
  place any repo strip rendered, so `YardBand` is restored from `6641975~1` beneath
  the gate band, where the 422 can be read row by row.

- **The map is queue → gate → receiving**, and the page header no longer claims
  membership, hill and targets are stored. Both were found by loading the page, not
  by the suite: `yard.carried` was a ledger key and the header opened with a blank
  where a number belonged.

- **README's third seam is corrected.** It still advertised `standards.yaml` as a
  live seam with a mermaid edge feeding it into the app, four versions after the
  file was deleted, and never mentioned the chart — the one thing shipyard owns.

## [0.29.2] — 2026-08-26 — The draft queue

Second light cycle of the **Directed work** arc.

### Added

- **The queue: what is captured but not yet startable.** `/api/yard` gains `queue`
  and the Yard gains a band, ahead of the gate on the map. It is not a new store and
  not a second list — `create_problem(draft=true)` has always allowed capturing a
  problem before its observable exists, on the grounds that you cannot demand a
  waypoint between pressing Enter and having the next thought. What a draft never
  had was a surface asking you to finish it.

  **There is no promote button.** Promotion *is* writing the waypoint: the moment a
  draft has one it stops being a draft, `_open_gate` stops refusing it, and a cycle
  can be cut against it. The row links to the problem and the chart's editor does
  the rest. A second verb would be a second way to do the one thing.

  **A grouping is not in the queue.** Found by rendering it against the real store,
  not by a test: the first version opened with `<root goal>`
  and its five `<domain>` groupings — six of twelve rows were the chart's
  own skeleton, waypointless because a grouping has no observable of its own and
  never will. A band asking *what may I start next* would have opened with six
  things that can never be started. The filter is `chart.children()`, the same
  discriminator `_open_gate` settled on in v0.29.1: a node with problems beneath it
  composes work rather than being work. Their draft debt is still counted on the
  goals page, where a question about the chart's shape belongs.

  Deliberately **not** `work.py`'s `backlog/tasks` orphans: that needs the `backlog`
  CLI and a `backlog/` directory most of the fleet lacks, and joining two stores
  behind one surface is the divergence this codebase avoids elsewhere.

- **Three tests, each with a negative** — the round-trip in both directions (a draft
  appears, and writing its waypoint removes it *and* makes it cycle-openable), the
  grouping exclusion, and no-duplicate-rows for a node `outline` emits twice.

## [0.29.1] — 2026-08-26 — No cycle opens on undirected work

First light cycle of the **Directed work** arc
(`docs/cycles/GOAL PROMPT — Directed work (v0.29.1 → v0.30.0).md`), and the first
version cut against shipyard's own chart node.

### Added

- **The other gate: a cycle cannot open on work nothing directs.** `_review_gate`
  guards the end of a cycle and refuses the two debts that mean work would be
  *lost*; `_open_gate` guards the start and refuses the two that mean work has no
  *direction* — a problem with no waypoint, and a repo already running a cycle
  nobody closed. Same boundary, same reason: a refusal a UI can skip is a
  suggestion. Composed in `main.py` because it needs two domains and no domain
  module may import another.

  The waypoint refusal is reachable by a route that is not the obvious one. A draft
  cannot *carry* a repo — `link_repo` already refuses that — but it can **inherit**
  one, and a waypointless parent whose child carries a repo could open a cycle
  against an observable it does not have.

  The open-cycle refusal reads `planned`, not `open`. `cycles()` reports both and
  they mean different things: `open` is commits since the last tag, which is the
  normal state of every repo between releases and would have refused most of the
  fleet. `planned` is a record whose version no tag has cut — the state v0.29.0
  closed two of at once, with nothing that could have stopped the second.

  **Only cycles that compose nothing contend**, and the filter runs on both sides.
  `chart.children()` is the test rather than `chart.role()`, which calls any
  parentless node a bearing and would have exempted every top-level problem — a lone
  one included, which is exactly what the gate is for. And because a composing
  cycle's record lands in the same repo its children cut in, the planned list drops
  versions claimed by a problem with children; otherwise opening a branch cycle
  blocks every leaf beneath it, which is the deadlock the rule exists to prevent.
  An *unclaimed* record still contends — nothing on the chart accounts for it.

- **Five tests, each of which fails when its check is removed** (`tests/test_gate.py`),
  verified by neutering the gate and re-running rather than by assertion. Includes
  `test_every_offered_repo_is_charted`: the plan's third refusal turned out to be
  unreachable — `nearest_repos()` derives candidates from chart nodes, so a repo the
  chart does not claim cannot arrive here — and the invariant is asserted at its
  source instead of enforced by a branch that could never fire.

### Changed

- **shipyard is on its own chart.** Four nodes under `<domain>`: the branch *Work is
  directed before it starts, and closed when it ends* carrying `repo: shipyard`, and
  the three leaves this arc cuts. It had been one of 23 manifested repos the chart
  did not claim, while being the app that reports the debt.

## [0.29.0] — 2026-08-24 — The legible yard

Closes two cycles in one tag, said out loud rather than papered over: the
conventions band and the `chart: none` / adoption work below sat under Unreleased
with no tag — an open cycle by the protocol's own definition — and this release
carries them out together with the legibility cycle
(`docs/cycles/PLAN — v0.29.0 the legible yard.md`).

### Added

- **The map** — the factory story, drawn instead of narrated. Receiving → the yard
  → the gate → the line, one stage box each with a live count, at the top of the
  Yard page. The flow had lived only in a source comment since v0.28.0, and the
  page read as seven unrelated lists without it. Counts come from reads the page
  already makes: the importable fetch lifted into `FleetPage`, and the gate count
  extracted into `gateRefusals()`, one derivation shared with the gate band so the
  two can never disagree. Stages scroll by element id through a button, not an
  `<a href="#…">` — the app routes on the hash, and an anchor would rewrite the
  route instead of moving the page (found by driving the served app, not by the
  suite).

### Changed

- **Band order became flow order.** The page told its own story backwards — the
  line first, receiving last. Now: map, the yard, the gate, the line, then the
  measures (portfolio, rhythm), then the standards, with receiving as the
  collapsed intake at the bottom where the map's first stage jumps.
- **"The ledger" is retitled "The yard".** The band replaced `YardBand` in
  `6641975` and the heading never followed the page's own tab name.
- **Every aside now states the question its band answers** — "what stops a sloppy
  cycle from closing", "did I show up" — with the doctrine demoted behind the
  question rather than deleted. The old asides defended design decisions to the
  person who made them; a reader needs orientation before doctrine.

### Removed

- **Dead `YardBand`** and its private helpers (`subOf`, `evidenceOf`, `BAY_META`),
  unrendered since `6641975`. Same call as `outline.jsx`: row geometry goes with
  its last caller rather than remaining shared with nothing to share.


### Added

- **The conventions this fleet runs on, and which of them have teeth** —
  `GET /api/conventions` and a collapsed band in the Yard: eight standards, what each
  one is, where it lives, and what enforces it. Templates and ADRs are counted from
  disk, so adding one needs no edit here.

  **Not `standards.yaml`.** That was deleted in v0.5.0 for scoring repos against a
  checklist when conformance was never the point, and
  `test_checklist_routes_are_gone` still asserts `GET /api/standards` returns 404 —
  which caught the first draft of this claiming the name. The guard held and the
  route moved rather than the other way round. Nothing here reads a repo, ranks one,
  or reports whether one complies; a test pins that no repo id, score or verdict can
  appear in the payload.

  The enforcement column is the point, from the rule `docs/census/DECISIONS.md`
  already states: *anything a linter can enforce becomes a checker rule and leaves
  the prose, because a convention stated in prose **and** enforced in code trains
  everyone to read the prose as advisory.* **2 of 8 enforced is not a number to drive
  to zero** — the templates declare in their own first line that they are a starting
  shape and never a standard. It is a list of where a convention could drift with
  nothing to say so, which this fleet has done twice: the palette was hand-converged
  and drifted back within days, and `check.sh` sat passing for weeks because nothing
  ran it.

### Changed

- **A repo can declare it is not goal-bearing.** `chart: none` in `PROJECT.yaml`, and
  `owed()` takes the declaration rather than inferring it. `uncharted` had been firing
  for thirteen of twenty-two repos — correct when the chart was a registry of what is
  on disk, wrong from 2026-08-18, when the capability spine was pruned and the chart
  became a map of goals under four life domains. Eight repos hang off those; the rest
  are tools, forks and scratch collections, and a tool having no problem node is its
  resting state rather than a debt.

  Fixing the predicate was chosen over restoring the deleted Software Factory node —
  the alternative was editing the map to match the instrument. Claimed, never
  inherited: silence still owes a node, and so does any value but `none`, on the same
  reasoning as `release: scheme: none`. An exemption acquired by neglect protects
  nothing and would let a manifest edit silence real debt.

### Fixed

- **Adoption reads the README instead of writing an empty description.**
  `write_manifest` fell back to `""`, and the Receiving form never asked — so every
  adopted repo got a blank field, and the field was then filled in by hand. Four were
  filled in wrong the same way: `mission-control` stops at "…every custom app on",
  `stocklake` at "…money-flow tracking, and", `benjamin` at "…driven by a DGX". Each
  ends exactly at its README's line wrap, because on screen a wrapped line looks like
  a whole one.

  `readme_summary()` takes the first real paragraph and joins it *before* taking it,
  so the wrap cannot become the ending. **Deliberately no character cap** — a cap is
  the same defect, committed by the tool rather than by a person. Furniture is
  skipped rather than guessed at: headings, wrapper `<div>`s, badge rows, rules, list
  markers, fenced blocks, and link-only lines. Fences are tracked because one repo
  opens with an ASCII-art logo inside ```` ```text ````, which reads as a paragraph
  of punctuation to anything that only inspects line shape. An explicit description
  still wins; the README is the fallback, not the authority.

  Validated against all thirty READMEs on disk, not just fixtures — the first pass
  looked right on twenty-eight and returned ASCII art for `godot-mcp` and a bare URL
  for `postiz-docker-compose`. The four already-truncated manifests are **not**
  rewritten; this changes what the next adoption writes.
- **One repo, one problem — enforced where the data is written, not at one door.**
  `link_repo` has refused a repo another problem already carries since the link
  existed, but `create_problem` did not, and it is the path both POST /api/problems
  and `scripts/seed_chart.py` take. So a seed file could write state the API would
  reject. On 2026-08-25 `scripts/la4ml-branch.json` put `repo: la4ml` on all seven
  nodes of a branch and every one of them drew *the same project card* — not an
  ambiguity on the board, seven copies of one project — cleared by hand through
  `PUT /api/problems/{id}/repo` with `null`.

  Both checks now call one `_repo_owner()` helper, so the invariant has a single
  statement. The seeder additionally validates repos in its pre-flight, beside the
  existing missing-bearing and duplicate-title refusals: a collision is reported by
  `--dry-run` and nothing is written, rather than failing partway through the batch.
  Two fixtures in the suite had been quietly relying on the gap and were given repo
  names of their own — the test modules share one database, so repo names are now
  unique suite-wide.

## [0.28.0] — 2026-08-18 — The yard

Named for the cycle it closes (`docs/cycles/PLAN — v0.28.0 the yard.md`), which
attacked Software Factory's *intake* clauses: work enters in one shape, and a gate
can stop the line. The cycle grew a second half in the same version — the yard was
built as a **gate**, then reframed as a **trajectory** once its own numbers showed
the gate was not discriminating (`_bay_of` put 17 of 22 repos in one bay, painting
68% of the page red). Both halves ship here because they are one argument about the
same page, and splitting them would have dated a design critique after the design it
replaced.

**⚠ The test and review phases did not run, and could not.** This version is cut
against a protocol it cannot satisfy, which is recorded here rather than papered
over. `PHASES = ("plan", "test", "review")` are columns on `problems`, so ticking
them needs a chart node — and the **Software Factory** node was deleted on
2026-08-18 in the intentional prune of the capability spine (commit `4454eb0`, which
names shipyard among the twelve repos whose nodes went). The cycle record's other
home is the vault under `Projects/<Project>/Cycles/`, now
`Archived/Projects (retired 2026-08-14)/`. So the machinery for recording a
transition is gone at both ends. What *was* verified is stated per entry below and
in each commit; what was not is this: no phase transition was recorded, and the
line's rework figure will score this cycle with that caveat unstated. Restoring the
node is the fix and is deliberately left as a decision rather than taken here.

### Added

- **`GET /api/yard`** — every repo in exactly one bay, named by what blocks entry
  (shelved > owes > uncharted > no-waypoint > clear); empty bays omitted; composed
  in `main.py` from existing reads, no new storage, nothing ranked.
- **The gate** — ticking `review` 422s while the cycle's repo owes uncommitted or
  unpushed work, checked fresh, refusal naming the debt. Planted-violation test
  proves it can still refuse.
- **Fleet's yard band** — the four groupings replaced by strip bays per the plan's
  D6/D7; gate band names exactly what the 422 would refuse today; `Strip` and
  `Bay` join `ui.jsx`; RepoInspector gains the met/missing gate checklist;
  Importable retitled Receiving.

- **The chart can be grown from the chart** — `＋ New problem` on the canvas, on
  both surfaces that draw it. The new problem lands beneath whatever is open, then
  focused, then the subtree in scope, then nothing; the parent is unfolded first, so
  a node made in a folded branch is drawn rather than born invisible. The empty chart
  offers it too, instead of pointing at a page you were already on.
- **The chart is navigable from the keyboard** — ↑/↓ walk the order the chart is
  drawn in, → unfolds a branch then steps into it, ← folds one then climbs back out
  to what it serves, Enter opens the node, Space folds it, `/` jumps to search. The
  ring the arrows move is deliberately *not* the selection — moving the selection
  would open the drawer on every press, which on the project page is a fetch per
  keystroke and on both is a panel permanently over the thing you are navigating.
- **The composer stays open** — Enter adds another problem in the same place,
  Shift-Enter adds one and descends into it, and what the session has made is listed
  and clickable. Decomposing a problem into five subproblems was five trips through
  the toolbar; a form that closes on submit assumes you came to make one thing.
- **Fold and add, on the node itself** — every branch carries a control on its
  trailing edge: a chevron that folds it away, or the count of what it is hiding,
  which unfolds. Folding was ⌥click and a badge that only existed once something was
  already folded — an affordance for one direction and none for the other. Hovering
  a node also reveals a ＋ that adds a subproblem under that exact node, so the
  parent is never inferred. ⌥click still works.
- **Fullscreen for the chart** — a `fixed` layer rather than the Fullscreen API,
  because the drawer is a sibling the browser's own fullscreen would black out. The
  zoom refits to the taller frame; Escape unwinds one layer at a time (composer,
  drawer, focus, page) so one press never closes two things.

### Changed

- **The project's Problem Chart is the graph, and only the graph** — the
  Outline/Graph switch and `tree.jsx` (492 lines) are gone. Two renderings of one
  subtree meant every per-node action had to be written twice or exist on one
  surface: adding a problem from the project page worked, renaming it did not. The
  canvas keeps the structure and `GraphPage` gained a `rail` seam, so the drawer
  carries `GoalRail` — the same authoring component the goals page uses, not a second
  one. `outline.jsx`'s row geometry went with its last caller.
- **Cycle linking moved into the drawer** — starting a cycle and recording which one
  addressed a problem lived only on the deleted outline. It is now a section of the
  project chart's rail, built entirely from `/api/problems/<id>/cycle-options`, with
  the same role-derived proposal (leaf PATCH, branch MINOR, bearing MAJOR).
- **Search moved onto the canvas** — out of the goals page header and into the
  graph's own toolbar. It was on one surface only, so the project's chart had no way
  to find anything; and once the canvas could fill the window the box went *behind*
  it, making fullscreen the one state where nothing could be found. The graph is what
  derives the hit set and unfolds the path to each, so the box belongs beside those
  controls. Regression-tested with `elementFromPoint`, since the input stayed
  "visible" by every ordinary measure while sitting underneath the layer.
- **An uncharted project says so** — a scoped `/api/graph` 404 is the ordinary state
  of most repos here, not a failure, so it renders the empty state the outline used
  to show instead of "could not read the chart".
- **The Fleet hot path is cached** — `scan_manifests` + per-repo git facts behind
  a 5s-TTL single-flight cache in `main.py` (11 invalidation sites, `/health`
  freshness stamps). Four-endpoint Fleet burst: 1.05s → ~0.10s warm.

### Added — the trajectory half (2026-08-18)

- **ADR 0004 and its schema.** `shelved_repos` folds into **`repo_standing`**
  (`carried` / `shelved`, absent = never considered): carrying and shelving are one
  judgement pointed two ways, and two tables could both claim a repo where a primary
  key cannot. **`hill_snapshots`** is append-only because the value is in the
  movement — a dot that has not moved is a raised hand, which is a query over
  history, not a field. **`due`** and **`appetite`** land on `problems`, beside the
  waypoint that already says what finishing *means*; a date on a repo would be a
  deadline with no definition of done. Migration verified against a copy of the live
  database before it ran on the real one: both shelved rows round-trip with notes and
  original timestamps, the CHECK refuses an unknown state, and the primary key
  refuses a repo claimed as both.
- **`cadence.py`** — commit time series, one git call per repo bucketed in memory
  rather than twelve subprocesses per repo per page load. Merge commits excluded, so
  a promotion day does not read as twice the work. Imports nothing from `app`.
- **The ledger** — one row per repo: motion, reach, position, appetite, grouped by
  **momentum** rather than by blocker. Same repos, a distribution that discriminates:
  12 moving · 4 slowing · 4 dormant · 2 shelved, against 17-in-one-bay. Blockers
  survive as chips, where they answer a different question about the same row.
- **The rhythm panel** — every carried repo summed by day. One shared scale with a
  clamped top bin, and zero rendered achromatic rather than as the palest ramp step,
  so "nothing happened" cannot be read as "a little". Measured both schemes:
  zinc-200 light, zinc-800 dark, chroma ≈0.005 either way. No streak counter,
  deliberately — GitHub removed theirs in 2016 after conceding streaks punish rest,
  and that objection is intrinsic rather than about being observed.
- **Carry and hill controls** — `POST/DELETE /api/carried`, `POST/GET /api/hill`,
  surfaced as Standing and Hill facets in the repo inspector. The hill is five named
  stops, not a slider: a raw 0–1 input invites precision the reading does not have,
  and naming the summit *"the unknowns are resolved"* is what stops it being read as
  percent-complete. Verified by driving the UI — readings went 1→2 with the trail
  growing rather than overwriting.
- **`docs/mockups/yard-trajectory.html`** — the design this half was built from,
  drawn on real fleet data and citing its prior art per band.

### Changed — the trajectory half

- **The Fleet tab is the Yard.** The header carried two things labelled "Fleet"
  stacked — the six-app switcher and this tab over ~22 repos. The rename was already
  three-quarters done underneath (`/api/yard`, `test_yard.py`, the page's own copy)
  and had stalled at the UI. `#/fleet` forwards rather than falling through to the
  board, with `replace()` so the dead route leaves no history entry.
- **`/api/yard` grew additively.** `bays` stays as the gate's source and all twenty
  of `test_yard.py`'s bay assertions pass untouched — they encode this cycle's own D5
  and precedence decisions, and discarding them to reshape a page would have been the
  wrong trade. Only the exact-shape contract test changed, to declare the new keys.

### Fixed

- **v0.27.0 was never tagged.** Its CHANGELOG entry existed; the tag did not, and
  `line.measure` reads tags alone — so throughput under-reported its own factory by
  two cycles. Cut retroactively at `dfb1747` with the tagger date set to the commit's
  own, since every prior tag here has `taggerdate == committerdate` and a tag dated
  today would have compressed the span. Exactly the failure this cycle's plan
  predicted: *the instrument existing is not the loop closing.*
- **The fleet-drift negative test was red for a rule that went quiet on purpose** —
  it planted `rgba(0,0,0,.5)`, which the achromatic carve-out deliberately exempts.
  Now plants the old palette's green tint, the literal the rule exists for.
- **`.gitignore` missed hand-made sqlite copies** — `data/*.sqlite-*` catches
  sqlite's own sidecars but not `shipyard.sqlite.bak-<stamp>`; the dot breaks the
  match. One was staged during this cycle's migration, which is precisely when a
  snapshot exists.

## [0.27.0] — 2026-08-16 — The measured line

Named for the cycle it closes (`docs/cycles/v0.27.0 — The measured line.md`), which
attacks one clause of **Software Factory** — the node this repo is now linked to. The
graph-drawer work below was already on `dev` and ships under the same tag.

### Fixed

- **The project page's Problem Chart → Outline opens a node beside the tree too.** Its
  row title was a bare `<a href="#/problem/…">`, so the third and last surface that
  draws the chart still left the page. Two of three working is how the previous bug
  looked, so the drawer now has a test on every surface that can open it.
  - `ProblemDrawer` moved to **`outline.jsx`** with the three views that use it —
    goals, graph, tree. It was in `graph.jsx` because there were only two callers, and
    a third made that the wrong home: `tree → graph` would have added a view→view
    import to a convention ARCHITECTURE.md already records as drifted.
  - It stays **layout-only**, which is that file's charter: it takes a node, never an
    id. Goals and the tree already hold the whole row (`/api/chart/{ref}/tree` returns
    the outline's shape), and the graph — which holds only an id — does its own fetch
    and passes the result down.

- **Every graph opens a node beside the canvas, not just the Chart's.** The project
  page's **Problem Chart → Graph** still navigated to `#/problem/<id>` on a click,
  because only the Chart passed `onPick` and the fallback was to leave the page. One
  gesture meant two different things depending on which page you were on — the
  fallback looked like a safe default and was really a second behaviour.
  - `GraphPage` now draws its own drawer when no host owns the selection. The Chart
    still passes `onPick`, because its selection lives in the URL and is shared with
    the outline; nothing else has to.
  - The facets are now **one component** (`ProblemDrawer`), used by both, so the two
    cannot drift. It takes a node already in hand — the Chart has the outline row, and
    re-fetching would add a loading flash where there is none — or an id to read,
    which is all a graph has, since `/api/graph` is a layout payload carrying no prose.
  - The regression test was planted and **fails on the old code**: only the new
    project-page test goes red while all six Chart tests pass, which is exactly why
    the original file could not have caught this.

### Added

- **The line — the first surface here that measures flow rather than state.** Every
  other reading in this app is a snapshot: `owed` says what is untidy now, `activity`
  says what moved lately, `standings` says where the frontier is. None of them could
  answer how long anything took, because nothing recorded a *transition*.
  - **`line.py`** (`GET /api/projects/{pid}/line`), a new point on the backend star
    that imports nothing from `app` — asserted by a test, not by discipline.
    Throughput comes from tag dates, which every repo already has; the alternative
    unit, a Backlog task, would have needed a convention adopted across a fleet where
    most repos have none.
  - **Three `phase_*_at` columns.** `set_phases` writes the timestamp and the flag in
    one statement and clears the timestamp on untick — a time left behind by an untick
    claims a transition that was taken back. `build` stays derived from commits and is
    still refused as a manual phase.
  - **Rework is `escaped defect`**: a fix or revert landing between a tag and its
    successor that touches code that tag shipped, bookkeeping files excluded, and the
    **head tag never scored**. Narrower than the obvious definition on all three
    counts because the obvious one was run first and failed — it flagged 27 of 27
    fix commits, made the newest tag permanently the worst, and let `CHANGELOG.md`
    attribute unrelated fixes to whatever shipped last. The refutation is recorded in
    `docs/cycles/v0.27.0 — The measured line.md`, and the tests are written against
    those three failure modes rather than a happy path.
  - **Fleet gains the band, and keeps its name.** Throughput is never rendered without
    rework beside it: a tag is a number you mint yourself — seven of shipyard's were
    cut in one afternoon — so versions-per-week read alone is the vendor-reported
    speedup figure, self-inflicted. `tests/test_line_band.py` plants the violation and
    catches it. The leaked figure is deliberately **uncoloured**: grading five-of-ten
    is a score, and this cycle exists to establish the baseline that would justify one.
  - Known gap: the line is measured for **one repo**, named in `fleet.jsx`. A
    fleet-wide roll-up shells git per tag and per fix commit, so it is a page-load cost
    that has not been paid for yet.

- **The graph opens a node in the drawer instead of leaving the page.** A plain click
  on a node in the Chart's graph view now opens the same `Inspector` the outline
  opens — title, waypoint, description, falsifier, what is beneath it — beside the
  canvas, with the node's ring left lit so the canvas and the panel visibly agree
  about what is open. The outline got this in the goal-inspector cycle and the graph
  did not, so the same friction that cycle names — *reading a node costs you the tree
  you were reading it in* — was still there in the other half of one view.
  - The drawer moved **out of the outline branch** to get it. It was rendered inside
    the outline's own grid, so the graph could not have shown it at all; it is
    `fixed`-positioned, so the move costs nothing visually and ends the state where
    one drawing of the chart had a capability the other could not have.
  - `#/problem/<id>` **stays the full page** and stays linked from inside the drawer,
    which is the goal-inspector plan's guardrail: a drawer that swallows the URL makes
    a node unshareable. A graph drawn without a drawer to open (`onPick` unset) still
    navigates there, so the gesture never dead-ends.
  - Selection stays in the URL as `#/goals?node=<id>` — reload reopens on the same
    node, Back closes it — and ⌥click-to-fold and double-click-to-focus are unchanged.

- **`tests/test_graph_drawer.py` and `make test-ui`** — the first browser test in the
  repo, driving a real Chromium against the built app on a real port. It is here
  because every cheaper check passes while this feature is broken: the drawer is a
  `fixed` overlay whose absence is invisible to `make check`, to the production build,
  and to every API test in the suite.
  - **Both regressions it guards were planted and caught**, in the spirit of
    `test_ui_contract.py`'s planted violation — dropping `onPick` from the graph, and
    moving the `Inspector` back inside the outline's branch. Each turned 5 of the 6
    tests red, and the sixth is the outline path that genuinely is unaffected.
  - It **skips** without playwright, a browser or a build, and says which is missing.
    A skip is not a pass, so `make test-ui` supplies all three in one command;
    `PLAYWRIGHT_CHROMIUM` points it at a browser you already have.
  - Found while writing it, and worth knowing beyond this file: the tests passed alone
    and failed in the suite. `app.main` binds `DB_PATH`, `CHART_EXPORT` and `CODE_ROOT`
    **once at import**, so setting the env vars in a test module does nothing when
    another module imported first — the trap `test_chart.py::db_conn` documents and
    ARCHITECTURE.md states as load-bearing. Both new test files patch the module
    attributes and set **no** environment variables: pytest imports every test module
    before running any, so an env var set in one is inherited by the modules that
    `os.environ.setdefault` theirs later in the alphabet.

- **`scripts/seed_chart.py` and `make chart-seed`.** Puts chart nodes authored as
  markdown into the store, which is the only place the app reads from. `docs/chart.md`
  is a one-way export (ADR 0003), so a charting session done anywhere without the
  sqlite produces reasoning that is versioned, reviewable and **invisible in the app** —
  fifteen nodes were in exactly that state. Deliberately a client of `chart.py`'s write
  API and **not** a parser of `docs/chart.md`: a parser would make the markdown a second
  writable source and bring back the merge problem export-only was chosen to avoid.
  - Idempotent on exact title; refuses (exit 2) to invent a bearing it cannot find;
    stamps `created_at` a second apart because `_now()` is second-resolution and every
    view orders siblings by it, so a batch insert would otherwise let sqlite pick the
    order. Found by rendering the export, not by reading the code.

## [0.26.0] — 2026-08-15 — Durable memory

### Added

- **`By memory` on Fleet, and `GET /api/memory`.** Four kinds of durable memory read
  where they already live — `why` (a chart node), `rules` (a CHARTER), `shape`
  (ARCHITECTURE.md), `choices` (ADRs). **No new store**: charters stay markdown in
  their repos, versioned with the code and readable when shipyard is down, which is
  what "one pleasant front end over the tools that already hold the truth" means.
  - **Grouped by what is MISSING, never scored** — the same call Owed made. A score
    answers "which repo is worst"; the useful question is "what has this project never
    written down". Road to 1.0 prunes anything that scores a project.
  - It **does not nag**: a three-file spike needs no charter. It reports coverage and
    lets the reader judge.
  - First reading, and the reason the view is worth more than a reader would be: of 21
    projects, **20 have no charter, 17 no architecture, 17 no ADRs, 13 no chart node —
    and none carry all four.** The empty case says so out loud, because an empty list
    otherwise reads as "not scanned yet".

### Fixed

- **A manifest that named its own documents was ignored.** `repo.documents()` consulted
  only `links.docs` (an external URL) and otherwise matched a hardcoded three-file list,
  so glm-harness declared `charter: docs/CHARTER.md` in its PROJECT.yaml for weeks and
  its project page offered a README. Any `links.*` entry now resolves: a repo-relative
  path becomes a readable document, an `http(s)` value stays a link, a declared file
  that does not exist is not offered, and a path that is both declared and conventional
  appears once. `CHARTER.md` and `docs/CHARTER.md` also join discovery by convention,
  since most repos will never declare one.


## [0.25.0] — 2026-08-14 — Focus slots

The second borrowed idea from HOI4's focus tree, and the last one planned: mutual
exclusivity was considered and **declined**, so this closes the thread.

### Added

- **One focus slot per domain.** A goal chart lists everything that matters and so
  says nothing about what is being worked on *now*. A focus tree is legible partly
  because exactly one focus runs and the rest visibly do not — scarcity is the
  mechanic. `GET /api/focus` returns one slot per pinned goal;
  `PATCH /api/problems/{pid}/active` takes or releases one.
  - **A domain is a pinned goal** — the same `nearest_pinned` the board sections by.
    No second notion of "domain" was invented. A problem under no pin falls into a
    single `__unassigned__` slot, which is also what the whole chart collapses to
    when nothing is pinned: one focus, globally, which is HOI4 exactly.
  - **Two refusals, never a silent correction.** A **blocked** problem cannot be
    started — starting something a subproblem is still holding up is the thing the
    state model exists to make visible, so the app must not do it for you. And a
    second focus in one domain is **refused by name** (*"<domain> is already focused
    on <problem> — release that first"*) rather than swapped in, because the moment you
    switch what you are working on is exactly the moment worth noticing.
  - **Solving releases the slot.** A slot is only scarce if finishing gives it back;
    otherwise every domain silently fills with completed work.
  - **Empty slots are drawn as loudly as full ones** and never summarised into a
    count — "this domain has nothing going" is the reading worth having, and a
    filled-slot tally is exactly what would hide it.
  - Shown in three places from one field: the focus strip above the chart, a ring on
    the outline's standing dot, and a bar down the leading edge of the graph node —
    an edge marker survives the zoom at which titles stop being legible.

## [0.24.0] — 2026-08-14 — Hover-only cross-links, and three states

Two changes to the goal chart, the second one the first borrowed idea from HOI4's
focus tree.

### Changed

- **Extra bearings are drawn on hover, marked always.** The dashed links are the
  ones that ignore the layout and cut across it, so at rest they read as noise over
  the tree the eye is following — and they scale badly, since every new cross-link
  is a chord across the whole canvas. They now render only while one of their two
  ends is hovered. What does *not* depend on hover is the fact: a node an extra
  bearing touches carries a permanent pair of dots and names the relationship in its
  tooltip. Hiding a line is a density decision; hiding a fact would be a lie.

### Added

- **Three standings — `open` / `blocked` / `done`.** A subproblem serves its parent,
  so children are this chart's prerequisites: a problem is **open** when nothing
  beneath it is outstanding (every leaf, so the frontier starts at the bottom),
  **blocked** while any subproblem is unsolved, and **done** when marked solved by
  hand. On the live chart that reads 35 open, 22 blocked.
  - **Derived, never stored.** `solved` stays the only fact a person sets; a second
    column agreeing with it is a column that will one day disagree with it.
  - **One rule, both views.** `chart.standings()` is computed once and read by the
    outline *and* the graph, with a test asserting they agree — the same reason
    those two already share a collapse key.
  - **It does not overrule you.** A problem you marked solved reads `done` even if
    the chart beneath it was never finished, because a parent is not the sum of its
    parts — which is exactly why `set_solved` is explicit.
  - Standings are computed over the whole chart and then read per node, so a scoped
    graph cannot report a problem as open because the subproblem blocking it sat
    outside the requested subtree.
  - Carried by **hue and shape, never by dimming** — `blocked` is a hollow ring, not
    a faded dot. A desaturated pass over this app was rejected on sight in August,
    and a state marker that recedes is one nobody reads.

## [0.23.0] — 2026-08-14 — Shelving

Taking a project off the board without touching a file, and proving that losing a
parent can never lose a project.

### Added

- **Shelving — the one thing shipyard chooses not to show.** A `×` on any project
  card (grouped, ungrouped or uncharted) takes it off the board; `shelved_repos`
  stores the decision, keyed by **repo id** so it survives the chart node being
  deleted, re-linked, or never existing. Nothing on disk is touched and the chart
  node keeps its repo — what it loses is a card, not its reasoning.
  `GET/POST /api/shelved`, `DELETE /api/shelved/{repo}`.
- **It is never silent.** `/api/board` returns `shelved` on every response, so the
  board renders an `N shelved` control unconditionally with a dated list and a
  one-click `restore`. Deliberate invisibility a user cannot find again is
  indistinguishable from data loss, and this is the one place the board's
  "nothing on disk is ever silently absent" rule bends — the count is what keeps
  it honest. Restore is idempotent and is **not** validated against disk, so a
  repo that has since moved away can still be un-shelved.

### Changed

- **Fleet lists shelved projects rather than hiding them**, with a `shelved` flag on
  `/api/projects`. Shelving is a decision about the *board*; Fleet is the page that
  catches a repo rotting with unpushed work, and letting one opt out of that would
  turn a view preference into a way to stop being told.

### Tests

- **A project can never end up nowhere** — pinned down on all three routes: its
  parent deleted (promoted to the grandparent, keeps its group), its *last* parent
  deleted (falls to `ungrouped`), and detached outright (falls to `ungrouped`). No
  code change was needed; v0.22.0's `ungrouped` already covered it, and now it
  stays covered.
- **Shelving does not make a project a ghost.** The subtle failure this guards:
  filtering the manifest alone leaves the problem node behind, and a missing
  manifest reads as `ghost` — *"decomposed but never attacked"* — which is a
  different claim about the work, and a false one.

## [0.22.0] — 2026-08-14 — Board groups

Managing the board from the board. Three asks — remove a group without losing its
projects, add one from the goal chart, drag projects between groups — measured down
to **one missing affordance**: a section already *is* a pinned chart node, and the
pin control lived only on the Chart page. No new table, no new endpoint.
See `docs/cycles/PLAN — board groups.md`.

### Fixed

- **Removing a group made its projects vanish from the board.** The guardrail this
  cycle was built around, and it failed the first time it was tried: unpinning
  a `<domain>` group left its four cards with no pinned ancestor, and the section rule placed
  a card only under its *nearest* pin — so they were dropped. On the chart, off the
  board, no message. Edges were untouched the whole time, which is exactly why an
  edge-count assertion passed while the board silently lost four projects. `/api/board`
  now returns `ungrouped`: every charted project that no heading claims, rendered as
  its own section and still draggable, so the way back is to drop one onto a group.
  This also closes a pre-existing gap in fallback mode, where a project more than one
  level below a root was never shown either.

### Added

- **A group header removes itself** — one click, worded *remove*, never *delete*,
  because unpinning changes no edges. The tooltip says what survives.
- **`+ group` on the board** opens a filterable picker over every unpinned chart
  node, each with its ancestor path. Adding a group is pinning a goal; it was
  always one `PUT` away, just on the wrong page.
- **The drag affordance the mechanism never had.** Re-homing a project by dragging
  has worked since the board was rebuilt, and nothing said so: no handle, no cursor,
  and a drop target that lit only once you were already over it. Cards now show a
  grip and a grab cursor, and **every** section lights the moment a drag begins.

### Changed

- **One goal picker, not two.** `GoalPicker` moves to `kit.jsx` and is now shared by
  the chart's *also serve another goal* and the board's *add group*. Two choosers
  over one chart is how they drift apart — and the abandoned one was still 45 bare
  pills.
- **`/api/board` reports its own failure.** The load had no `.catch`, so a dropped
  request left the board rendering a skeleton forever; every write here confirms
  itself by re-reading, which would have made a failed pin show stale groups.

## [0.21.0] — 2026-08-14 — The sweep, first pass

Not a planned sub-cycle: a pass driven by two audits of shipyard's own surface
(`docs/cycles/SWEEP — prune, keep, enhance.md`). Correctness first, then dead code.
**The sweep is partial** — ladder steps C–F are untouched and step B is half done.

### Fixed

- **A failed fetch no longer asserts the opposite.** Four project panels turned a
  network failure into confident prose: *"Nothing since the last release — the tag
  and the code agree"*, *"No versions cut yet"*, *"No ADRs yet"*, and a silently
  emptied Orient. A missing state is a blank; this was a lie, and the worst kind —
  the app claimed the tag and the code agreed when it had no idea. Each handler now
  records the failure and each panel renders `ErrorState` before it can reach its
  empty copy. The empty strings stay: they are correct when the fetch *succeeded*.
- **Three v0.20.0 defects**, found by the audit and verified before acting: a dead
  `GET /api/problems/{pid}/approaches` born unused one commit earlier, `phases` and
  `solved` returning a different shape from every neighbouring route, and
  `add_approach` turning a bogus id into a 500 rather than a clean rejection.
- **The graph's double-click could never reach focus.** `onClick` fires twice before
  `onDoubleClick`, and it navigated immediately — so the gesture the node's own
  tooltip documents always left the page first. Navigation is deferred and cancelled
  by a second click.

### Added

- **`<Boundary>`** — an error boundary around the graph. The render-time twin of the
  `.catch` fix above: a throw unmounts the subtree and leaves a blank pane that only
  a full reload recovers, which is indistinguishable from an empty chart and is why
  the vanishing graph has resisted diagnosis. It now renders `ErrorState` and logs
  the component stack, which is the only place that stack exists post-unmount.
  **This does not fix the crash** — it makes the next one legible.

### Removed

- **`chart.jsx`, 387 lines** — 6% of the frontend, five exports, zero consumers.
  `AnchorControl` inside it was the only UI able to set `anchored`, a state shown in
  five places and settable in none; rehomed onto the problem page first, which also
  makes the `/anchor` endpoints reachable for the first time.
- **The work/task write-back routes** (42 lines). Their UI went in `c1f2405`, whose
  message left the endpoints standing as a deferred decision. This is that decision.
- Phantom imports, dead `outline`/`query` state in `Copy`, and four `kit.jsx` exports
  with no external consumer (un-exported, not deleted — they have internal callers,
  which the audit's "dead" label missed).

### Notes

- **Eight claims acted on today did not survive verification** — six from the audits,
  two from my own diagnosis of the graph bug. The sweep plan carries ~40 more findings
  in the same format; none should be actioned without checking it first.
- `/api/drift` and the two `templates/{slug}` routes are equally dead but pruning them
  reds 9 tests that exercise real logic through those routes. Reverted rather than
  leave the suite failing.


## [0.20.0] — 2026-08-14 — The Hub

Second sub-cycle of **The Face**. The loop now lives on a problem, which is the
prerequisite for shipyard running a cycle instead of being the thing a cycle
happens to.

### Added

- **The loop, per problem.** `phase_plan` / `phase_test` / `phase_review` are
  ticked by hand; `solved` + `solved_at` record whether the problem is closed.
  Solved does not cascade from children — a parent problem is not the sum of its
  parts, which is why it carries its own waypoint.
- **`problem_approaches`** — the options considered, which one is being taken, and
  a **verdict** on it. The verdict outlives the choice moving on: try A, it fails,
  switch to B, and `A — failed` remains. That row is the most useful thing on the
  page, and erasing it would make this a planning tool rather than a learning one.
  Locked by a test at both the chart and HTTP layers.
- **Build is derived, not clicked.** Read off the repo as work since the last cut
  version, because the protocol makes the tag the transaction commit. Never stored,
  never clickable, and always labelled with its reason — "7 commits since v0.2.0,
  1 uncommitted". A derived tick indistinguishable from a clicked one would fail
  the same way a silent default does.
- **`known` on the derived state.** A problem with no repo is not *un*built; git was
  never asked. It renders a dash rather than an empty box.
- **Board rollup** — `n/m solved` on cards with subproblems.
- Six endpoints: phases, solved, and approach CRUD.

### Fixed

- **`ON DELETE CASCADE` was decorative.** SQLite ships with foreign keys off, so
  deleting a problem orphaned its `problem_edges` rows. Pre-existing; surfaced by
  the approaches cascade test. Enabled per-connection in `chart.init()`.
- **Cycle records were unreachable.** `_records_dir` looked only under the vault's
  `Projects/` tree; when that was archived, all 31 of shipyard's cycles reported no
  record while nine sat in `docs/cycles/`. Now prefers the repo, which is the copy
  under git.
- **`python -m app.main` ignored `SHIPYARD_HOST`** and bound `0.0.0.0`, colliding
  with `tailscale serve` so the old process survived and the new one died quietly.
  Now matches the Makefile's loopback default.

### Notes

- `PhasesIn` forbids extra fields: `{"build": true}` returned 200 with nothing set,
  which would have told a client Build was ticked. Now 422.
- 305 tests green; `make check` clean.


## [0.19.0] — 2026-08-14 — Consolidation

First sub-cycle of **The Face** super-cycle (`docs/cycles/GOAL PROMPT — The Face`).
No feature moved; the app stopped disagreeing with itself about what things look like.

### Changed

- **One `Chip`, one status renderer, one `Skeleton`.** `kit.jsx` defined a second
  `Chip` (rounded-md, raw `text-[11px]`) beside `ui.jsx`'s pill, and owned
  `StatusDot` and `Skeleton`. The same concept rendered differently depending on
  which file imported it. `ui.jsx` wins — it carries the accessibility work and
  uses the scale token. `kit.jsx` keeps domain helpers and the stage-aware chips.
- **Every loading state comes from `<Loading>`.** Nine call sites across six views
  hand-rolled their own — five spellings of `text-sm text-zinc-400`, one raw
  `text-[11px]`, three different labels — while the primitive sat unused. One site
  is inline inside a row, so `<Loading>` gained an `inline` variant rather than
  leaving a straggler.
- **126 × `text-[11px]` → `text-micro`.** `--text-micro` is exactly `0.6875rem`,
  so this is byte-identical output. 43 raw sizes remain (`10px` below the scale,
  `13px` between two steps); converting those is a visual decision, not a
  mechanical one.
- **The accent means interaction, and nothing else.** Versions, repo names, cycle
  weight, `anchored`/`open` and a progress fill were rendered in the same blue as
  buttons and links, so affordance and fact read identically. Data moved to mono +
  neutral or to its semantic hue.

### Added

- **`make check` — the dependency rule, mechanically.** `frontend/scripts/check-ui.mjs`
  enforces `ui.jsx ← kit.jsx ← views` plus five more rules, wired into a pytest case
  so it fails the suite rather than a lint nobody runs.
- **A negative test for the checker.** It plants three violations and asserts all
  three are caught. This immediately earned its place: the first draft of the
  raw-colour rule exempted any line containing `//`, so a colour literal with a
  trailing comment passed clean — visible only because the fixture expected three
  failures and got two.

### Notes

- Rule 5 is a **ratchet**, not a gate: baseline 43 raw font sizes, may fall, never rise.
- 285 tests green (283 + two contract tests).


### Added

- **Habits** (`#/habits`) and a **Vault ↗ link in the header** — the first two
  doors in what is meant to become one front end you move between tools inside,
  rather than a bookmark bar of ports.

  **Shipyard renders no habits.** It briefly did: this tab shipped as a native
  view over a `/api/habits` bridge, and both are now gone. vault-dashboard owns
  the daily notes, so it owns the habit record *and how that record looks*; a
  second renderer here would have been a second thing to keep in step, which is
  the exact failure `kit.jsx` names when it says two surfaces disagreeing about
  what something looks like is how a reading stops being trusted. The view moved
  to vault-dashboard, where it belonged, and the tab became a door to it.

  What the removed bridge was careful about went with it rather than being lost:
  a missed day and a day with no note are different things, and vault-dashboard
  now draws them differently (it had been colouring both the same). On the real
  vault that is most of the window — <n> of the last 90 days carry the
  section.

  Cross-links are built from the browser's current hostname, not a literal
  `localhost`. Both apps bind `0.0.0.0` and get opened over the tailnet, where a
  hardcoded localhost points at whichever machine is *reading* the page — the
  same reason Mission Control templates its `open_url` with `{host}`.

- **Owed** (`#/owed`) — what the whole fleet owes, grouped by kind: uncommitted,
  unpushed, no remote, untagged work, unlogged, uncharted, running old code. Every
  number was already computed and already on a project page; the only thing missing
  was somewhere to see all nineteen at once. The motivating case is this repo — it
  sat 48 commits past its own tag for five days with its own header faithfully
  reporting `48 ahead · 37 unpushed`, because reading that meant opening the one
  page that shows it.

  **Grouped, never ranked.** Road to 1.0 prunes "anything that computes a score for
  a project", and the guardrail turns out to be the better design: a score answers
  "which repo is worst", while the question on returning to a fleet is "what do I
  owe" — one is a number to argue with, the other is a list to work through. The
  kind order is editorial and fixed (what you lose if the disk dies tonight, first);
  magnitude only sorts *within* a kind, because thirteen uncommitted files and
  thirteen unlogged commits are not the same debt.

  Built on `project_view` rather than beside it, so the two surfaces cannot
  disagree — verified on manalab, which reads `56 uncommitted · no remote` on both.
  `repo.owed()` is pure over already-computed values, so the module stays ignorant
  of charts and manifests. No new storage, no new object, nothing to keep up to
  date: it is read out of git and the chart on every load.

  **First reading, and it is not flattering.** 18 of 19 projects owe something;
  `csv-profiler` alone is clear. Nine repos have no remote at all — half the fleet
  exists only on this machine. manalab has **56 uncommitted files, edited today,
  with nowhere to push them**. mission-control — the fleet's own control plane —
  has 23 uncommitted sitting 19 days. codebase-memory-mcp is 165 commits past
  `v0.9.0` with 75 of them unlogged. And 16 of 19 are uncharted, including shipyard.

### Changed

- `Chip` moved from `project.jsx` into `kit.jsx`. Two surfaces disagreeing about
  what "unpushed" looks like is how a reading stops being trusted.

### Removed

- **Soundings are no longer drawn.** The chips, the three-button pickers, the
  `SoundingTrack` bar, the graph's sounding dot, the header's `N/M above
  assumed`, and the verdict-vs-sounding mismatch banner on both the goals rail
  and the argument page are all gone.

  **The data was kept, deliberately.** `assumed`/`proxy`/`observed` still ride on
  every problem, `effective_sounding()` still caps a parent by its children, the
  API still returns both, and `docs/chart.md` still exports them. Thirty-one
  problems carry a recorded sounding and three carry written reasoning; none of
  it was touched. This is a change of what is on screen, not of what is believed,
  and it is one revert away.

  The one hazard is the edit form, which now PATCHes `{title, waypoint}` and
  never mentions sounding. That is only safe while a missing field means "leave
  it alone" — if PATCH ever coerced absent to `assumed`, every edit would quietly
  erase evidence with nothing on screen to show it. Two tests in
  `test_chart.py` pin it.

  Where a sounding was carrying something else, that something else came back:
  bearing headers get their card count returned (`SoundingTrack` had been
  carrying it), and project cards keep a plain `uncharted` marker, so charted is
  now a binary rather than a grade.

### Fixed

- Counts of one read as `1 file`, not `1 files` — the kind of seam that makes a
  reading feel machine-generated and therefore ignorable.

## [0.17.0] — 2026-08-12

Five days and 48 commits that ran without a tag. Under Development Protocol 1.0 the tag
is the transaction commit, so by the protocol's own accounting none of this existed —
the same exception `v0.1.0` logged, and worth saying out loud rather than quietly
backfilling. Cut as one MINOR rather than reconstructed into the five-or-so cycles it
actually was: retroactive tags would be archaeology, and per-cycle detail belongs in
`docs/cycles/` anyway. The drift was visible the whole time — shipyard's own header
reported `48 ahead · 37 unpushed · 29 unreleased entries` — which is the argument for
the next cycle, not this one.

### Added

- **Documents read like documents.** The reader gained the structure prose needs and
  the styles it never had: tables (16 of 48 project documents use them and none of it
  was styled, so comparison tables rendered as run-together text), code blocks with a
  frame and their language named, a real heading hierarchy, linkable heading anchors,
  and an on-this-page nav built from the document's own sections. The page title now
  comes from the document's H1 rather than its filename — "Development Protocol 1.0"
  reads better than `0001-development-protocol.md`.

- **Shape panel on the goals page** — counts per top-level domain with leaf counts,
  and state chips that filter the outline flat: nothing-to-observe, no-waypoint,
  leaves, argued. Answers "what does my chart look like" without traversing it,
  which is what you need when managing rather than authoring. Its first reading:
  one `<domain>` holds 38 of 52 rows against 4, 4, 4 and 2 for the others — five pinned
  domains, one real branch.
- **A quiet domain tint** on each row, so a long outline says where you are while
  scrolling. It yields the whole edge to the selection bar rather than sharing it,
  and stays washed out on purpose: soundings own the loud colour channel, and with
  73% of the chart in one domain a saturated rail would be a wall of one colour
  claiming to be information.

- **Four template shapes** — Instrument, Habit surface, Infrastructure, Production
  pipeline. A project chart's children are claims about *why this would work*, and
  those claims rhyme by what kind of bet a project is, not by what it is built with.

- **Cycle records mirrored into the repo.** The vault stays the source — a record
  is a hand-written retro — but the copies live in `docs/cycles/` so the history of
  finished work survives a fresh clone, the same reason `docs/chart.md` mirrors a
  chart that lives in gitignored sqlite. Copied verbatim, so "is this current" is a
  byte comparison rather than a judgement; provenance lives in a README beside them
  rather than a header that would make every copy differ from its source. One
  direction only, and triggered explicitly: a GET that writes files is the hidden
  behaviour this app exists to argue against.
- **Cycles tab** — every cut version as a plan-build-test-review cycle. Under
  Development Protocol 1.0 the git tags already *are* the history of finished work,
  so this joins them to what each produced (the changelog entry) and what was
  learned (the vault's cycle record), classifying each version move as a
  super-cycle, sub-cycle or light cycle from the number alone. Work since the last
  tag is shown apart and explicitly not counted: no version, no credit.
  It reports that shipyard has cut 28 versions and kept 8 retros.
- Tests for `survey.py`, which had none and had been wrong twice — 25 covering line
  and language counting, the primary-language verdict, the empty-repo and no-tests
  cases, layout ordering, skipped vendor directories, Poetry and PEP 621
  dependencies, and the rule suppressing node packages where a Python runtime exists.
- **Project state in the header** — the released tag, the commits stacked on top
  of it, the uncommitted and unpushed counts. One number would be a lie of
  omission: a repo thirteen commits past its tag is not that tag. `no remote` gets
  its own flag, because having no upstream is a different problem from having
  nothing to push — it is what stops a repo being demonstrable to anyone else.
- **Changelog drift** — commits since the last tag that changed what the software
  does, with nothing under `Unreleased` to show for them, surface as one chip that
  opens the changelog. An audit surface, not a history: a commit feed would be
  GitHub's rebuilt worse, and would not reduce reading. Only `feat/fix/perf/
  refactor` count, since a flag that fires on index syncs gets ignored — which is
  the failure it exists to prevent.
- **Documentation, split from links** — `ARCHITECTURE.md`, `CHANGELOG.md`,
  `README.md` and `docs/adr/` are discovered on disk rather than declared, and open
  in an in-app reader. They were previously rendered as inert `<code>`: a path you
  could read but not follow. ADRs get their own tab.
- **Running old code** — compares the newest commit against how long the process
  has been up, which needs nothing from the app itself. Reports *unknown* rather
  than *false* when it cannot tell, which is the honest answer for compose apps.
- **Moving lately** on orient — commits touching each top-level directory in the
  last 90 days. Layout says where the weight sits; this says where the attention
  went, and telling a large untouched directory from a small rewritten one is most
  of what you want on returning. Counted in commits rather than files, so one mass
  rename cannot outrank three months of steady work.
- **Start reading here** — the modules other files import most, as a cheap stand-in
  for what is load bearing. stocklake reports `config.py` at 35 and `lake.py` at 29;
  shipyard reports `kit.jsx` at 7.

### Changed

- **The bearing picker is a filtered list, not a wall of pills.** It rendered every
  candidate as a bare pill with no hierarchy — 51 of them on the live chart — so
  attaching one goal to another meant scanning an unordered wall where two goals
  sharing a title were indistinguishable. Now: type to narrow, and every candidate
  carries the path it sits on.
- **Search over the outline.** Titles and waypoints, with each hit's ancestors
  carried along so a match is never an orphaned line. Searching overrides collapse,
  since a match hidden inside a closed branch is the one case where the browser's
  saved state is actively wrong.

- **The draft prompt fires where the rule was skipped, not on every draft.** The
  stopping rule is "descend until the waypoint is cheap to observe", so a problem
  with children and no waypoint was broken down before anyone knew what they were
  looking for — that is the rule being skipped, and the only draft worth
  interrupting for. A childless draft is just a name, and gets a quiet line. The old
  prompt fired on 48 of 53 rows, which made it wallpaper; the live chart has 10 that
  actually break the rule, and they are the entire spine — the root, all five
  domains, and one `<personal goal>` chain, with 43 leaves hanging beneath them.

- The nine argument essays use one tag convention. Two of the corrections were not
  cosmetic: five tags sat alone on a line and produced no bullet at all, and one
  essay used its tags to close the claim before them while the rest introduced the
  claim after — so two confidence chips were attached to the wrong claims.
- A statistic cited in two `<personal>` essays now cites its primary source
  consistently, with its caveats.

### Fixed
- **The uncommitted count was counting directories, not files.** `git status
  --porcelain` collapses an untracked directory to one line, so manalab reported
  "13 uncommitted" against 71 real files. Every never-committed repo read that way
  — which is exactly when the number matters most, because nothing there is
  recoverable. Both call sites now pass `-uall`; the working-tree listing was
  showing one row per directory for the same reason.

- **Every file counted as a test** for any project whose *path* contained "test" or
  "spec". The survey matched its test-file pattern against the absolute path rather
  than the repo-relative one, so a repo in a directory named `my-test-thing` reported
  a 100% test ratio. Found by the first tests written for that module.
- The survey's file bound was checked once per directory, so a single folder of forty
  files walked straight past a limit of five. It now bounds files, as intended.
- Evidence in the goals rail was read line by line, so a bullet was whatever fitted
  on one physical line — some essays wrap at ~95 columns and some keep a paragraph
  on one line, making bullet quality an accident of formatting. Paragraphs are now
  joined first, and each tag is resolved by shape: a **label** introduces the claim
  after it, a **stamp** grades the claim before it, a **predicate** sits inside the
  claim. Reading a stamp forwards had been returning the caveat and dropping the
  finding.
- Thesis claims were cut at the wrap column, so every one ended on a conjunction.
- Rail bullets could end on a dangling word (`…too thin and`), which read as a
  truncation bug rather than a summary.
- The import scan credited every file sharing a name, so `chart.md` ranked as
  somewhere to start reading code; `from . import chart` was missed entirely,
  hiding shipyard's own backend from its own list and reading stocklake's
  `lake.py` at 4 instead of 29; and two files with one name in the same language
  were both credited for either mention.

### Removed

- The "no waypoint" line under every leaf. Forty-two rows repeating what the header
  already counts, at a line each.
- **web-service.yaml.** Its five children — does the thing, someone else can run it,
  survives being left alone, shape is stated, anyone uses it — were completeness
  gates identical for every web service, which is a checklist wearing a template's
  clothes. `main.py` still says "conformance to a standard was never the point", and
  v0.5.0 deleted the last one. Maturity lives in the stage field and on orient.
- The `Dashboard` and `TaskRow` components, dead since the work tab was rebuilt on
  git, along with a stale comment block describing the goals page that the file
  split had left stranded above them. 137 lines. The backend `work` routes stay —
  `glm-harness` has a real backlog and that API still answers.

## [0.16.0] — 2026-08-07

Duplicates in the tree were two different things wearing one face.

### Added
- **Occurrence counters** — every placement of a shared goal reads `1/3`, on the
  real row as well as the references, so a goal in three places reads as one goal
  in three places rather than as three goals. Previously the extra placements were
  a mute "shown above" with no sense of how many.
- **Copy a block** — duplicates a subtree as independent nodes, for two similar
  goals that then diverge. The panel says plainly that *also serve another goal* is
  the other thing, so the choice is made on purpose rather than by whichever
  control was nearer. A copy drops the repo and the anchor — a project is attacked
  by one problem and the copy has not earned it; an anchor is a dated decision and
  the copy has decided nothing.

## [0.15.1] — 2026-08-07

### Changed
- **Templates belong to projects.** They were offered on every problem including
  pure goals, which was wrong in a way worth naming: a template describes how a
  *project* is attacked, and only work has recurring shapes. A goal's shape comes
  from thinking about that goal — offering to stamp one invites skipping the only
  step that matters. The panel now appears only when a problem has a repo.
- The header gains **Projects · Goals · Graph**. The board was reachable only by
  browser back or by clearing the hash by hand, making it the one view you could
  get stuck away from.

## [0.15.0] — 2026-08-07

### Added
- **Document scaffolds.** A template may now carry a shape, a document, or both.
  The kind you most wanted could not previously exist: a development cycle
  instantiates once per *cycle* rather than per project — thirteen ran in a single
  day of building shipyard — so putting its steps in the chart would bury the
  reasoning under process bookkeeping. It needs a page, not a subtree.
- **A development-cycle template**, document-only, written from Development
  Protocol 1.0. Its prompts are opinionated about the parts that actually slip: the
  problem must name a failure that already happened rather than a missing feature;
  the pruned list is written before the first commit, since added afterwards it is
  just a description of what you happened not to do; guardrails are derived from
  the problem rather than invented; done means observed output, never "tests pass".

## [0.14.0] — 2026-08-07

### Added
- **Templates** — a saved subtree of problems and their waypoints, stamped under
  anything. You do not author one in a separate editor: you build a chart you like
  and save that subtree, which is what keeps it general — the same machinery serves
  a web service, a grow cycle and a training block, because a template is only ever
  problems. The rule that keeps this from being `standards.yaml` under a new name:
  **a standard says what you must have; a template says where to start.** So
  templates are never checked, nothing is ever "missing" from one, a stamped copy
  carries no link back, and shipyard can never say a project has drifted from its
  template — there is a test pinning that. Soundings, repos and anchors are
  stripped on save, since they describe the chart the shape came from rather than
  the shape. They live as YAML in `templates/` rather than in sqlite: unlike the
  chart they are portable definitions, not a record of reasoning.

## [0.13.0] — 2026-08-07

### Added
- **A graph view of the goal web** at `#/graph`. It buys the one thing an outline
  structurally cannot show: a problem serving two goals appears once with two
  edges, instead of twice with a "shown above" apology. That case is the whole
  reason the chart is a DAG, and until now it was only visible as a footnote.
  Layered rather than force-directed, because *serves* has a direction and letting
  nodes float would discard the only meaning the layout could carry. Read-only on
  purpose — editing lives in the outline, and a canvas you can also rearrange is a
  different product. No layout dependency; about eighty lines, rendered as SVG.

## [0.12.0] — 2026-08-07

### Added
- **Choose which board sections to show, and collapse the rest.** The board grows
  with the chart, and a chart is meant to grow. Filter chips toggle each top-level
  goal plus Uncharted, with counts, persisted per browser rather than in the data
  because it is about looking rather than about the chart. Collapsing and hiding
  are deliberately different: a collapsed section stays on screen as a header so
  you know it exists, a hidden one is gone. When anything is hidden the board says
  *showing 3 of 4* — a filtered board that looks like a complete board is how you
  forget a whole branch exists.

## [0.11.5] — 2026-08-07

Two things that surfaced the moment the chart got real content.

### Added
- **Rename in place** — a pencil on hover, and clicking the title of an already
  selected row starts editing. Renaming had been hidden behind a double-click
  nobody would guess at.
- **Serve several goals at once.** Multi-parent existed in the model since 0.2.0
  and was unreachable from the outline: dragging could only ever *move* a node, so
  saying three goals all serve one problem meant writing that problem three times.
  Now a *Serves* panel in the rail listing current bearings, each removable, plus
  ⌥drag to attach instead of move. Dropping the last bearing is allowed — that
  makes it a top-level goal, which is a legitimate place to be.

## [0.11.4] — 2026-08-06

### Changed
- **The waypoint shows under each title.** The outline was a list of labels; the
  claim that makes a goal falsifiable lived in the rail one goal at a time, so the
  page could not be scanned for the weak ones — the entire reason waypoints are
  insisted on, invisible. A goal without one gets a clickable prompt, *no waypoint
  yet — what would you observe?*, which selects the row with the rail open on the
  field that answers it. Drafts stop being a chip you have to notice and become a
  question you are looking at.

## [0.11.3] — 2026-08-06

### Added
- **Drag a goal out to top level.** Drag could only ever nest something deeper —
  every drop target was another goal — so there was no mouse route back out. A
  dashed strip appears beneath the outline *while a nested goal is in flight*, and
  stays hidden when the goal is already at the top, because offering an action that
  would do nothing is just noise.

## [0.11.2] — 2026-08-06

### Added
- **Add a problem directly under another.** Enter made a sibling and Tab indented
  it, so decomposing — the motion the page exists for — took two actions and a
  mental step. A `+` on hover creates a child in place, expanding the parent first
  so the new row is visible rather than created into a collapsed branch.
  Shift-Enter is the keyboard twin.

## [0.11.1] — 2026-08-06

### Added
- **Drag a goal into another**, the same operation as Tab reached by mouse. A drop
  that would close a loop is refused by the API and surfaced rather than silently
  ignored.
- **Delete from the row** — a trash button on hover opens a confirm inline beneath
  that row rather than sending you to the rail, stating the same consequences and
  offering both *delete only this* and *delete the branch*.

### Changed
- Child counts stop hiding on hover now that the trash occupies that spot; a count
  is information, not a control.

## [0.11.0] — 2026-08-06

The two things missing before a chart can be built from scratch and taken seriously.

### Added
- **Assign a repo from the goals rail** — an *Attacked by* section that links or unlinks a
  project without leaving the page you're reasoning on. Previously only the board could do
  this, so deciding to attack a problem meant navigating away from it. Drafts are refused
  with a pointer at the waypoint.
- **Delete the branch.** Alongside "delete only this" (which promotes children), the confirm
  now offers *Delete the branch (N)* — everything whose only route to a bearing ran through
  this problem. Starting a chart over should not mean clicking delete forty times.
  **Anything with a second bearing is spared either way**, and named in the confirmation.

### Changed
- The rail reads **Waypoint · Why · Sounding · Attacked by · Argument** — the order you
  actually think in: what would I see, why do I believe it, how sure am I, who is working on
  it, and where is the case written down.

## [0.10.3] — 2026-08-06

### Fixed
- **Tests were not isolated from the repo.** `CHART_EXPORT` was never overridden, so every
  `make test` rewrote the real `docs/chart.md` with test fixtures — and it was committed
  that way several times, because a generated file nobody reads in a diff is where silent
  damage hides. Tests now hard-set `SHIPYARD_DB` (`setdefault` let a leaked env var win) and
  point the export and arguments directories at temp dirs.
- **Restored two lost bearings** — "Learning faster compounds everything else" (with its
  2026-08-05 anchor and basis) and "<personal goal>" — plus all
  three edges. The live chart had been reduced to 12 problems with both projects orphaned.

### Added
- A guard in `arguments.write`: a body with a closing `---` near the top and no opening one
  is refused. That is the exact shape of a corruption seen earlier that no write path could
  be made to reproduce. Deleting the whole frontmatter block deliberately stays legal.

## [0.10.2] — 2026-08-06

### Changed
- **Split `App.jsx`** (1855 lines) into surface modules: `kit` (product-blind primitives),
  `board`, `chart`, `project`, `goals`, `argument`, `palette`, leaving `App.jsx` at 113 lines
  of routing and chrome. Dependencies run one way and there are no cycles.

  It had already caused two self-inflicted bugs in a day. Note for next time: Vite builds
  JSX without checking that identifiers resolve, so a hand-written import list produced a
  green build and a blank page. The cross-module imports were computed from actual usage.

## [0.10.1] — 2026-08-06

### Changed
- **The argument editor is a writing surface, not a config box.** It is typeset like the
  document it produces — same face, size, line-height and 68ch measure as the reading view —
  so toggling between `write` and `read` barely moves the text. Writing prose into a
  monospace box is the fastest way to stop writing prose.
- **Autosave on a pause** (1.2s), with `saving… / saved` status and a word count. Writing
  should never involve remembering to save. The mtime guard still protects a file edited
  elsewhere, and each save carries the new mtime forward so autosave never trips its own guard.
- The box grows to fit its content — the page scrolls, not a small inner pane.
- `⌘S` save · `⌘B` bold · `⌘I` italic, wrapping the selection. No toolbar.

## [0.10.0] — 2026-08-06

### Added
- **An argument gets its own page** at `#/argument/<id>`, with the markdown **rendered** rather
  than shown as source. Hand-styled at a ~68ch measure with quiet uppercase section headings,
  because an essay is the one screen where the reading experience *is* the feature. Frontmatter
  is hidden, the thesis and short reasoning sit in a card above the prose, and an edit toggle
  swaps to the raw source. `marked` added for rendering.
- The rail now links to that page instead of holding an editor — an essay written in a 300px
  column is an essay nobody writes.

### Removed
- **"What would make this false"** from the rail. It belongs in the argument, where there is
  already an *evidence against, and what would falsify this* section, and having it in both
  places invited two answers to one question. The `falsifier` column is untouched on disk.

## [0.9.0] — 2026-08-06

**Arguments.** A waypoint was asserted, never argued — you picked one of three chips and
nothing anywhere said why that grade was deserved. Now every waypoint can be the **thesis of
a short argumentative essay with evidence**, and the sounding can be its conclusion.

### Added
- **Argument files** — plain markdown, scaffolded from the rail with the waypoint pre-filled
  as the thesis, and sections for *why this follows*, *evidence for*, *evidence against and
  what would falsify this*, and a **Verdict**.
- **`reasoning`** — a short field on every problem, one or two sentences, visible in the rail
  without opening anything. The compressed why, distinct from the essay.
- **Verdict mismatch.** Shipyard reads the essay's verdict and reports disagreement — *"the
  argument concludes observed; the chart says assumed"* — with one-click reconcile.
- Editing inline, or in your own editor via `SHIPYARD_EDITOR_URI`.

### Decisions
- **Plain markdown, nothing tool-specific.** Obsidian is one way to open a file, not a
  dependency. One config line — `obsidian://open?vault=…&file={path}`, `vscode://file/{abspath}`,
  `file://{abspath}` — makes any editor the "open in" target, and shipyard can always edit
  inline so the app is never broken for someone who configured nothing.
- **They live in the repo**, `docs/arguments/`, beside `docs/chart.md`: versioned with the code,
  works on a fresh clone, no external path assumptions. `SHIPYARD_ARGUMENTS_DIR` relocates them.
- **The verdict is read, never enforced.** A mismatch is surfaced for a human to reconcile.
  Silently changing a grade because prose changed is the invisible mutation this app exists to
  prevent — and tightening the rule later is easy, while loosening it after trust is lost is not.
- **Writes are mtime-guarded**; a file changed elsewhere is refused rather than clobbered, and
  scaffolds are create-only.

### Fixed
- The argument panel only reloaded on selection change, so reconciling a mismatch left it
  claiming a disagreement that no longer existed. It now reloads when the sounding changes too.

## [0.8.2] — 2026-08-06

### Changed
- **Goals outline polish.** It read as a flat list past two levels: text arrows replaced with
  rotating SVG chevrons, every row a uniform 32px, hairline **depth guides** so nesting is
  countable, selection as a left accent bar rather than a full-width wash, and chips moved to
  the right edge and quietened to rings.

## [0.8.1] — 2026-08-06

### Added
- **Delete a problem**, from the goals rail. Until now the outline could only grow —
  removing anything meant reaching into sqlite by hand.
- **Children are promoted, never destroyed.** Deleting a rung re-attaches everything
  beneath it to that rung's parents, or makes them goals in their own right if it had
  none. A whole branch of recorded reasoning must not vanish behind one click; to remove
  a subtree, delete bottom-up, which forces you to see each part.
- **The consequences are shown before the button**, not after: how many problems move,
  where they move to, and that a linked repo stays on disk and simply becomes uncharted.
- `GET /api/problems/{id}/deletion` and `DELETE /api/problems/{id}`.

### Fixed
- "1 problems beneath" — pluralisation in the rail and the delete confirmation.

## [0.8.0] — 2026-08-06

**The goals page.** The board shows goals; nothing let you build them. The chart was
project-scoped and composer-driven — one dialog per problem, reached by first opening a
project. Fine for adding a rung while thinking about one thing, hopeless for sitting down
and decomposing a goal in one pass.

### Added
- **`#/goals`** — an indented, collapsible outline of the whole chart, with a detail rail.
  Chosen over Finder-style columns (navigates well, cannot be authored) and over the
  spine-as-page, which turned out to *be* the rail with the outline removed.
- **Keyboard authoring** — `Enter` new sibling, `Tab` indent, `Shift-Tab` outdent, `↑`/`↓`
  move, double-click to rename. Indent and outdent re-parent chart edges.
- **Undo for structural moves.** `Tab` silently rewires your reasoning; every move now shows
  *moved "X" under "Y"* with an undo that restores the previous parent.
- **Detail rail** — waypoint, falsifier and sounding, edited in place, plus what sits beneath.
- **Duplicate handling** — a problem with two bearings is expandable at its first occurrence
  and an inert *shown above* reference at the second. Never two editable copies, and a shared
  subtree is walked once rather than once per bearing.

### Changed
- **Drafts.** A problem created in the outline may have no waypoint yet — you cannot demand an
  observable between pressing `Enter` and having the next thought. A draft is flagged, counted
  in the page header, and **cannot be linked to a repo**: *"give it a waypoint first — you
  cannot attack a problem you can't tell you've solved."*

  The rule from v0.2.0 survives where it matters. The composer still requires a waypoint;
  drafts are an explicit opt-in for fast capture.
- Blanking a waypoint now **demotes to draft** rather than erroring.
- **Having no repo is not debt.** Most problems should never have one — decomposition comes
  first and a repo is what you add once you decide to attack. Only a missing *waypoint* is
  flagged.

## [0.7.0] — 2026-08-06

**The chart is the board.** The app was backwards: projects were the primary object and the
chart was bolted on. But the reasoning comes first — a project is what you create once a
subproblem is concrete enough to attack. So the model inverts.

### Changed
- **Sections are root problems**, not lifecycle buckets. The board is organised by *purpose*.
  Self-organising: add a parent above two roots and they merge into one section, so the board
  always shows the highest level you're currently organising by.
- **Maturity survives as a field**, not the grouping — `spike / tool / product` is now a chip on
  the card, read from `PROJECT.yaml` `stage:`.
- **Dragging a card re-parents it on the chart.** It changes what the work is *for*, which is a
  far more meaningful action than moving it between maturity buckets. Loops are refused.

### Added
- **Ghost cards** — a problem with no repo, in a dashed, unfilled style. Deliberately wears none
  of a project's clothes: no status, no activity, no task count. The gap between *decomposed*
  and *being worked on* is exactly what should be visible.
- **Promote a problem to a project** by linking an existing repo, from a picker of unlinked
  manifests. This is the moment reasoning becomes work.
- **`Uncharted` section** — projects with no problem node. Nothing on disk is ever silently
  absent from the board.
- `GET /api/board`, `GET /api/unlinked`, `PUT /api/problems/{id}/parent`, `PUT /api/problems/{id}/repo`.

### Removed
- **`groups.yaml`**, `groups.py` and the group CRUD API. Groups were a separate concept for
  three versions; they were always the chart wearing a disguise. `PROJECT.yaml` `stage:` values
  are untouched by the removal — they simply mean maturity now.

### Fixed
- **Loop detection on re-parent was backwards** — it asked whether the child sat below the
  proposed parent, when the cycle condition is the reverse. Caught by a test that expected a
  refusal and got a 200.
- **A card with two bearings rendered under both sections**, dragging its whole subtree along —
  the board became a hall of mirrors. Cards now appear once, under the first bearing that claims
  them, with `also serves N other bearings` on the card.
- **Every problem at every depth became a card.** Ten ghosts per section buried the projects
  under their own sub-sub-problems. The board shows a root's **direct children** only, with
  `{n} below` pointing into the project's own chart.

## [0.6.1] — 2026-08-06

### Changed
- **A project is now a page, not a drawer.** Clicking a project navigates to
  `#/project/<id>` and replaces the board, instead of sliding a 2xl panel over it.
  Browser back returns to the board, a project can be linked to directly, and the chart
  and its context get the full width they were always cramped for. The scrim and the
  modal semantics are gone with it.

## [0.6.0] — 2026-08-05

**Write-back.** v0.5.0 made unjustified work visible but not fixable — the orphan section
showed you the problem and left you to open a terminal. This closes the loop, and makes the
"reads *and writes*" half of shipyard's one-liner true for work as well as for groups.

### Added
- **Attach and detach a task from the dashboard.** Orphans get an `attach…` control listing the
  project's problems; attached tasks get `detach` on hover. Both write the label for real.
- `POST` / `DELETE /api/projects/{id}/tasks/{tid}/problem`.

### Decisions
- **The write goes through the `backlog` CLI, not a file edit.** v0.4.0 wrote `PROJECT.yaml`
  with a surgical line edit; that would have been easy here too, and it would have been wrong.
  Repos using Backlog.md state the rule in their own `CLAUDE.md`: *do not edit task markdown
  directly, use the CLI so metadata, relationships and history stay consistent.*

  The general principle, now proven twice: **when shipyard writes into a repo, it follows that
  repo's conventions.** A front end over other people's tools does not get to impose its own
  file format on them. Confirmed in practice — the CLI stamped `updated_date` on its own, which
  a hand-written frontmatter edit would have silently skipped.
- **A missing CLI is a visible error**, surfaced with the CLI's own message. A write-back that
  silently fails is worse than one never offered. Projects without a `backlog/` are refused
  outright rather than shown a control that cannot work.

### Verified
Attached `TASK-7` to *Quality* from the UI — orphans went 2 → 1, the label landed on disk, and
`backlog task view` agreed. Detached it again; labels round-tripped exactly, leaving only the
CLI's own `updated_date` stamp.

### Known gaps
- One task, one problem — a task matching several problems still attaches to the first.
- No bulk attach.
- The drift inbox still can't resolve anything; only the dashboard can.

## [0.5.0] — 2026-08-05

**The dashboard, and the end of the checklists.** Conformance to a standard was never the
point, and the Floor/Run/See/Decide boxes were cluttering the thing you actually open.

### Added
- **Work nested under the problem it serves.** A project's open Backlog tasks hang off the
  chart problems they belong to, with a **serves no waypoint** section for everything else.
  That section is the reason for the layout: a flat task list makes all work look equally
  justified, and nesting is what makes unjustified work visible.
- `GET /api/projects/{id}/work`, and a Backlog reader that tolerates a repo with no `backlog/`
  (most of the fleet has none).
- Project cards now carry **sounding**, **open task count** and an **uncharted** marker in place
  of the checklist ring.

### Removed
- **`standards.yaml`**, the derived checks, `/api/standards`, the check-toggle route, the
  `standards` health check, and the whole checklist UI. Shipyard no longer owns an opinion
  about what a good repo looks like.
- The `checks` table is **left on disk with its rows** — only the code paths are gone, so
  reversing this costs a revert rather than a loss.

### Decisions
- **A task says which problem it serves via a Backlog label**, matched to the problem's title
  slug. That fact belongs in the task, not in shipyard — the same reasoning that kept group
  membership in `PROJECT.yaml`. Shipyard resolves at read time and stores nothing.
- **Never invent an attachment.** An unmatched or unlabelled task is an orphan and says so.
  The honest consequence is that unlabelled work all lands in the orphan bin at first.

### Observed
Learn Hub, after labelling: **Habit** holds 2 tasks, **Engagement** holds 6, and 2 serve no
waypoint — `TASK-27` (1.0 packaging, which serves the *`<personal goal>`* bearing rather than
anything under learning-efficiency) and `TASK-7`. The effort concentration the mock predicted
is real: the lens with the least evidence holds the fewest tasks, and the one whose waypoint
isn't even instrumented holds the most.

## [0.4.0] — 2026-08-05

**Board rework.** The board still looked the way it did before any of this started: three
hardcoded sections from a fixed vocabulary, and a single "16d ago" stamp where the shape of
the work over time was wanted.

### Added
- **User-owned groups.** Create, rename, delete and drag between them. Deleting a group that
  still holds projects is refused by name rather than silently stranding them off the board,
  and the last group can't be deleted.
- **Drag-and-drop** project cards between groups, with a drop-target highlight.
- **Per-project activity heatmap** — 26 weeks of real commit history, GitHub-shaped, in the
  project panel. Nothing to type into: it reads `git log`.
- `GET /api/projects/{id}/activity`, and group CRUD under `/api/groups`.

### Changed
- **The board renders from `groups.yaml`, not from a hardcoded array.** `standards.yaml`'s
  stage vocabulary no longer decides what sections exist.
- **Shipyard now writes into repos it doesn't own** — the first real write-back, pulled forward
  from v0.6.0. Which group a project is in is a fact about the project, so it lives in that
  project's `PROJECT.yaml`; only the group *definitions* live in shipyard's `groups.yaml`.

### Decisions
- **Membership does not go in sqlite.** v0.2.0 recorded that a third "shipyard owns truth"
  exception would mean the definition was wrong. It held: membership went to the manifest,
  definitions to a committed config file, and neither is a database.
- **The write-back is a surgical line edit, not a YAML round-trip.** These manifests carry
  hand-written comments and `yaml.safe_dump` would have silently deleted every one. Verified
  on shipyard's own manifest: header comment, flow-style lists and key order all survived, and
  `git diff` showed exactly one changed line.

### Known gaps
- Group reorder exists in the API but has no UI.
- Group colour is fixed at creation; new groups all get blue.
- The heatmap lives in the project panel, not on the card.

## [0.3.0] — 2026-08-05

**Anchors & drift.** v0.2.0 could write a chart but not maintain one — no editing, no way to
upgrade a sounding when evidence arrived, no record that a belief had been frozen and when.
A structure you can only add to is a document, and documents rot.

### Added
- **Edit a problem** — `PATCH /api/problems/{id}` for title, waypoint, sounding, falsifier.
  Waypoint stays required; blanking it is a 422.
- **Anchors** — freeze a problem with a **basis** (rejected if blank: *why* are you willing to
  stop questioning it?) and a date. Thawing clears only the frozen state and **deliberately
  keeps the basis and falsifier** — the record of what you believed and when is the point.
- **Thaw impact, shown before the action.** `GET /api/problems/{id}/impact` reports what rests
  on a problem, split into what **survives** (and which bearing keeps it) and what **falls to
  drift**. The UI refuses to offer thaw without showing this first.
- **Drift inbox** on the board — including **projects with no chart at all**, which is the
  loudest form of "nothing records why this exists" and is invisible to any query that only
  looks inside the chart.
- Export marks anchors, their basis, and **thawed** state — a thawed belief otherwise reads
  identically to one never examined.

### Fixed
- **Survival is transitive.** Impact checked only direct parents, so thawing a bearing reported
  a healthy project's entire subtree as orphaned even though the project itself survived via a
  second bearing. Now a node survives if *any* upward path reaches a bearing outside the blast
  radius. On real data this moved learn-hub's subtree from 11 false orphans to 11 survivors.
- **A bearing is not drift.** Drift listed every parentless problem, which meant your two
  top-level bearings were reported as orphans and the inbox was useless. Drift is now a
  parentless problem that *should* serve something: a project, or a floating leaf.

### Learned
- `effective = min(declared, best child)` cuts **both** ways: a strong child cannot lift a weak
  parent. Learn Hub's audiobook problem earned `proxy` and Quality stayed `assumed` — verifying
  that audio generates says nothing about whether retention improved. The vault vocabulary note
  said otherwise and was corrected.

### Known gaps
- No re-parenting, detaching, or deleting.
- Drift can be seen but not resolved from the inbox — no attach action yet.
- Cycles remain possible in principle.

## [0.2.0] — 2026-08-05

**Chart core.** Shipyard could show what a project is and whether it moved, but nothing
about *why it exists* — that reasoning lived in prose and never got checked. The chart
makes it inspectable.

### Added
- **The chart** — a DAG of problems. One node type: what used to be called a rung, a lens
  or a subproblem are all `problems`, with direction carried by an edge. A problem with a
  `repo` is a project.
- **Waypoints are mandatory.** Every problem must say what you'd observe if it were
  working; blank is rejected with a 422. A problem without an observable is a category,
  and admitting one lets the chart fill with unfalsifiable prose.
- **Soundings** (`assumed` / `proxy` / `observed`) with an **effective** grade computed at
  read time: a parent is capped at the best of its children, so if every child is
  `assumed` the parent is `assumed` regardless of what it declares. The UI shows the cap
  with a `↓` and explains it on hover.
- **Spine view** in the project panel — bearings above, the project centred, children
  below. Click any node to re-centre; "back to the project" returns.
- **Composers on `↑` and `↓`** — literally the two questions the method asks: *why does
  this matter?* and *how do I attack it?* The `↑` composer also lists existing bearings to
  attach to, which is how a project gains a second parent.
- **Many-to-many bearings.** A project serving two bearings survives one of them being
  thawed; a project with one parent goes straight to drift.
- **`GET /api/drift`** — problems serving no bearing.
- **Markdown export** to `docs/chart.md`, rewritten on every chart write. `data/*.sqlite`
  is gitignored, so this is what gives months of recorded reasoning a history and a backup.
  One-way by design: no parser, no merge conflicts.

### Decisions
- **ADR 0003** — the chart lives in shipyard's sqlite, making shipyard an owner of truth
  for the first time. Accepted as the *second* deliberate exception to "owns no complex
  logic of its own", conditional on the export above. A third exception is not available:
  if one is proposed, the definition is wrong and gets rewritten instead.

### Seeded
- Learn Hub's real chart, created through the UI: 2 bearings, 3 children, 7 grandchildren.
  `csv-profiler` attached to the shared `<personal goal>` bearing, which now carries 2 projects.

### Known gaps
- Everything is `assumed`. No sounding has been earned yet.
- No thaw, no drift inbox, no re-parenting, no editing an existing problem.
- Cycles are possible in principle; the composer makes them hard, nothing forbids them.

## [0.1.0] — 2026-08-05

Baseline. Records everything shipyard already was, plus the work of 2026-08-05.

> **Ran out of protocol.** This work had no Plan phase — it was requested and built
> directly. Logged here per the protocol's rule that skipped cycles must be said out
> loud. `0.1.0` is therefore a *baseline tag*, not a completed P→B→T→R cycle; the first
> real cycle starts after this.

### Added
- **Checklist items derived from disk.** Seven standard items are now computed rather than
  hand-ticked: `git-init`, `gitignore`, `readme`, `project-manifest`, and
  `make-dev`/`make-prod`/`make-test` (parsed from Makefile targets). Items carry a
  `derived` flag; `POST /api/projects/{id}/checks/{item}` returns **409** for them, so
  stored state cannot drift from what is actually on disk.
- **`last_activity`** per project, from `git log -1` — the time axis the board never had.
- **Command palette** on `Cmd/Ctrl-K` and `/`, with arrow-key navigation.
- **Staleness signalling** — relative "16d ago" on every card, amber past 14 days, red past 30.

### Changed
- **Frontend rebuilt on Tailwind v4** (first Tailwind adopter in the fleet; CSS-first, so
  configuration is an `@theme` block, not a `tailwind.config.js`). Light *and* dark via
  `prefers-color-scheme` — previously dark-only. SVG progress rings replace flat bars; a
  responsive grid replaces three hardcoded columns; skeleton loaders replace a text
  "loading…"; `prefers-reduced-motion` is respected.
- **Project detail is now a slide-over** rather than a full-board replacement — opening a
  project no longer unmounts the board and blanks the surrounding context.
- **Season plan moved** from `docs/wiki/` to `docs/` — it is hand-written, and `docs/wiki/`
  is the machine-owned DeepWiki floor that is regenerated rather than edited.

### Fixed
- **`make setup` is self-healing.** `dev`/`prod`/`test` now depend on `setup`, and `setup`
  is keyed off marker files instead of directories. Previously `prod` had no `setup`
  dependency (a missing venv failed forever) and an *empty* `node_modules` counted as
  satisfied — together these left the app unable to start at all.

### Known gaps
- Tracks **5 of ~35** repos; only those carry a `PROJECT.yaml`.
- No git remote — fails its own `github-remote` standard item.
- Nine checklist items are still hand-ticked state owned by shipyard's sqlite.
