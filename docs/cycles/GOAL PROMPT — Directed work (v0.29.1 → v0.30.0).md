# Goal Prompt — Directed work

Sub-cycle · shipyard `v0.29.1 → v0.30.0`
Drafted 2026-08-26. Fossilised on Build gate — corrections go to ADRs, never back-edits.

---

## 0. The protocol, inlined

*Restated rather than linked: the vault's `Projects/` tree was archived 2026-08-14, and a prompt
that depends on an archived note is not self-contained.*

A cycle is **atomic**: it passes P→B→T→R and cuts a version, or it cuts nothing. There is no
version for "got through build and testing." If the re-plan valve fires mid-cycle, the cycle
aborts — learnings go to `Backlog.md` and a retro, no version is cut.

**The version bump is the transaction commit.** `CHANGELOG.md` is the write-ahead log; git tags
are the only durable record. *"Did I finish anything?"* → count the tags.

| Unit | Version move | Ends with |
|---|---|---|
| Light cycle (this arc's children) | **PATCH** `v0.29.0 → v0.29.1` | CHANGELOG entry + tag + cycle record |
| **Sub-cycle** (this whole arc) | **MINOR** `→ v0.30.0` | the three below, closed |
| Super-cycle | MAJOR | not this arc |

`repo._weight()` reads that table off the version number, and `chart.role()` arrives at the same
vocabulary from tree position — parentless = bearing = super, has-children = branch = sub, leaf =
light. **The two must agree.** This arc's branch problem is a `branch`, so it cuts MINOR; its three
leaves cut PATCH. That is why `v0.30.0` lands *last* and the numbering stays honest.

**The loop attaches to a problem, never to a project.** Several problems may share one repo.

---

## 1. Problem

Shipyard has exactly one rule with teeth, and it guards the **end** of a cycle: `_review_gate`
refuses to tick `review` while a repo owes uncommitted or unpushed work — the two debts that mean
work would be *destroyed*.

Nothing guards the **start**. `api_open_cycle` checks only that a repo exists beneath the problem
and that an ambiguous repo was named. It does not check that the problem has an observable, that
anything on the chart claims the repo, or that a cycle is already running there.

Three measured consequences:

- **Two cycles ran open at once and nobody noticed until the tag.** v0.29.0's changelog says it
  out loud: *"the conventions band and the `chart: none` / adoption work below sat under Unreleased
  with no tag — an open cycle by the protocol's own definition."* One tag closed two cycles because
  no mechanism could have prevented the second from opening.
- **The chart claims 10 repos out of 33 manifested.** If work can start without a node, the chart
  is a description written afterwards — and a description nothing consults rots.
- **The Yard is not opened.** It carries eight bands, of which five measure the operator rather
  than the fleet, and two of those measure nothing at all: `hill_snapshots` holds **0 rows** and
  **0 problems carry a due date**. The page that should start work is instead a telemetry page
  whose telemetry was never recorded.

## 2. Vision + measuring stick

**Vision.** The chart is upstream of the work. Nothing starts that isn't directed, nothing starts
while something else is unfinished, and the Yard is where you go to *begin*.

**North star.** From the Yard, cold, the time to answer *"what may I start right now"* is zero
clicks and no reading of prose.

**Guardrail.** *A refusal must name the condition it refuses on.* No 422 in this arc may say only
"not allowed" — each states which fact is missing, in the same vocabulary the strip and the bay
already use. **The failure mode worse than a missing gate is a gate whose message sends you
hunting.**

**Second guardrail, carried forward.** *Grouped, never ranked.* Nothing added here computes a score
for a repo or a problem. This has twice produced a better design than the thing it blocked.

## 3. Constraints / appetite

**Appetite: three evenings, one per light cycle.** Where a choice is between correct-but-large and
boring-but-adequate, appetite picks boring.

- No new runtime dependency, backend or frontend.
- No domain module may import another. Anything needing two is composed in `main.py`.
- Each light cycle is atomic: it cuts a PATCH or it cuts nothing.
- Every cycle ends green on `make test` (430 backend + 5 frontend) and `make check`.
- `check-ui.mjs`'s raw-font-size ratchet is at **43**: it may fall, never rise.

## 4. Landscape

- **Buy:** nothing to buy. Every mechanism this arc needs already exists in the repo; the work is
  wiring and deletion, not construction. See §6 D2 and D4 — both decisions are "use the thing that
  is already there."
- **Standards:** Shape Up's appetite (already in the protocol). Nothing else applies — a gate over
  a personal project chart is not a domain with off-the-shelf parts.
- **The gap = the build:** three refusals, one band, and a deletion pass.

## 5. Decomposition

**AND-children** (all three required for `v0.30.0` to close):

1. `v0.29.1` **No cycle opens on undirected work** — three refusals at `api_open_cycle`.
2. `v0.29.2` **The draft queue** — the Yard surfaces waypointless problems; promotion is the exit.
3. `v0.29.3` **The Yard answers one question** — delete the self-measurement half, remove `stage`,
   add the cycle chip.

Order is free — the three touch mostly disjoint code. Only `v0.30.0` depends on all of them.

**Prerequisites, not cycles** (Step 0 and Step 1 of the plan; no version is cut for either):
branch hygiene (merge the stranded chart-invariant fix, promote `main`, which is 9 behind `dev`
while the ADR claims it is prod), then create this arc's four chart nodes.

**Pruned children** — the v2 list, written down at the moment it was cut:

| Pruned | Why |
|---|---|
| Rewriting `standards.yaml` | Deliberately deleted; will be rewritten from scratch, and will not reuse `stage`. Gating on a definition about to change would bake in the old one. |
| Gating documentation at the open gate | Same reason. The requirement is real; the definition isn't ready. |
| Joining `backlog/tasks` orphans into the queue | Two stores feeding one surface is the divergence risk this codebase avoids everywhere else. See D4. |
| Sweeping `stage:` from the fleet's 33 manifests | A key nothing reads is inert. A sweep dirties 33 working trees at once and trips the review gate fleet-wide for a cosmetic change. |
| Fixing the README's `standards.yaml` seam section | It is stale and should go, but it belongs with the rewrite that replaces it. |
| Enforcing view→view imports as `check-ui.mjs` rule 7 | ARCHITECTURE.md names this gap honestly. Its own cycle. |

## 6. Decision points

**D1 — Where does the refusal live?** → **`_open_gate(con, pid, repo)` in `main.py`, beside
`_review_gate`.**
*Rejected:* a domain module (it needs two — the chart names the repos, git names the state — and no
domain module may import another); a check in the UI (*a refusal a UI can skip is a suggestion* —
the same sentence that put `_review_gate` at the API boundary).
**Consequence:** the two gates sit adjacent and read as a pair, which is the point: one guards the
start, one the end, and they deliberately refuse different things.

**D2 — What counts as "a cycle is open"?** → **`repo.cycles(path)["open"]` — a record with no tag.**
*Rejected:* a `cycle_open` column or table. Duplicates state that already lives on disk and will
drift from it — the same reasoning that made "count the tags" the answer in the Face cycle's D3.
**Basis:** `cycles()` already reports `open` and `planned` separately, and its docstring already
says why: *"No version, no credit. Abort → backlog + retro, not a partial bump."*

**D3 — Which cycles contend for the one-open slot?** → **Leaf cycles only, scoped per repo.**
*Rejected:* per problem (two sibling problems each see the same latest tag and propose the same
version — the collision `versions_claimed_in` was written for); counting branch and bearing cycles
(a super-cycle is *supposed* to stay open while its children run; counting it deadlocks everything
beneath it).
**Consequence:** `chart.role()` is the discriminator, and this arc is its own first test — the
branch stays open across all three leaves.

**D4 — What is the queue?** → **Chart drafts.**
*Rejected:* `backlog/tasks/*.md` orphans (richer items, but requires the `backlog` CLI on PATH and
a `backlog/` directory — most of the fleet has neither); both joined (D4's rejection above).
**Basis:** `create_problem(draft=True)` already captures a waypointless problem, flags it, counts
it as debt on the goals page, and **refuses to let it link to a repo**. The filter this arc wants
is already written and already refuses. The work is surfacing, not mechanism.
**Consequence:** promotion is writing the waypoint. There is no separate promote verb, no second
store, and `problem.jsx` already carries the copy: *"nothing can be attacked until it has one."*

**D5 — Delete the self-measurement bands, or hide them?** → **Delete outright.**
*Rejected:* collapsing them (dead code wearing a UI); a second page (a page already not opened).
**Basis:** measured, not assumed — `hill_snapshots` has **0 rows**, `problems` has **0** non-null
`due`. The hill and target features were built and never used. Deletion costs no data.
**Boring-option clause:** if removing the ledger destabilises `/api/yard`'s `bays` half, ship the
band removal and defer the module deletion — `bays` is the gate's data and must not regress.

**D6 — What replaces `stage` on the strip?** → **A `CycleChip`: `29 cycles` idle, `cycle open` in
flight.**
*Rejected:* count only (the gate state is the question the page exists to answer); state only (the
strip loses any sense of a repo's history).
**Consequence:** `cycles: {closed, open}` joins `_repo_facts()` — the TTL-cached bundle — because
`repo.cycles()` shells git per repo and an uncached call runs serially across 33 of them, which is
what made Fleet loads take seconds before.

**D7 — Is `stage` deprecated or removed?** → **Removed, field and all.**
*Rejected:* leaving the field and dropping only the chip. Standards is being rewritten from
scratch and will not reuse it; a field kept "for later" against a spec that doesn't exist yet is
how the last one rotted.
**Consequence:** ADR 0004 leans on `stage: spike` as its precedent for declaring what a repo does
not owe. It gets a superseding note, not a back-edit.

## 7. Architecture style + dependency rule

Unchanged. This arc adds no module and no directory; it deletes three.

> **Backend — a star, not a chain.** No domain module imports another. `main.py` imports all of
> them and is the only composer. After this arc there are **eight** domain modules, not eleven:
> `line`, `cadence` and `hill` are deleted.

> **Frontend — `ui.jsx` ← `kit.jsx` ← views.** `ui.jsx` imports nothing but React. `kit.jsx` is
> product-blind. `outline.jsx` is deliberately product-aware.

**Mechanically checked** by `frontend/scripts/check-ui.mjs` in `make check`, with
`tests/test_ui_contract.py` asserting the checker catches a planted violation. The new `CycleChip`
is a **domain** chip: it goes in `kit.jsx`, not `ui.jsx`, exactly where `StageChip` was.

## 8. Docs set

**Written:** a `CHANGELOG.md` entry per light cycle · one cycle record per version in
`docs/cycles/` · a superseding note on `docs/adr/0004-carried-repos-and-targets.md` (D7) ·
one new ADR for **D2 + D3** — *what records an open cycle, and which cycles contend* — because it
is the decision most likely to be re-litigated when a super-cycle first blocks something.

**Deliberately absent:** no ADR for D1 (it restates a boundary ADR 0001 already holds) · no ADR
for D5 (a deletion justified by two row counts belongs in the cycle record, not a decision log) ·
no `ARCHITECTURE.md` rewrite beyond the module count and the eleven→eight correction.

## 9. Test fixtures

- **Backend:** the 430 existing tests stay green at every commit.
- **`tests/test_gate.py` gains three planted conditions**, each of which must fail if its check is
  deleted — the negative-test discipline `test_ui_contract.py` already models:
  (a) a draft problem → 422; (b) a problem whose repo no node claims → 422, *and* a repo declaring
  `chart: none` → **allowed** (the exemption is claimed, never acquired by neglect);
  (c) a repo with an untagged record → 422, *and* the same repo with a branch cycle open →
  **allowed** (D3).
- **Queue round-trip:** a draft appears in `/api/yard`'s queue; a `PATCH` adding its waypoint
  removes it *and* makes it cycle-openable. Both transitions asserted, not just the first.
- **Deletion:** `test_line.py` and `test_line_band.py` are removed with their subjects;
  `test_yard.py` loses its ledger assertions and **keeps every `bays` assertion** — that half is
  the gate's data and is the regression this cycle is most likely to cause.
- **Browser verification per light cycle:** load the served app, exercise the surface, read the
  console, screenshot. *v0.29.0's anchor-routing bug was found by driving the app and not by the
  suite* — that is the standing reason this line is here.

## 10. Commit ladder

**Step 0 — hygiene, no tag.** (1) merge `claude/objective-hellman-37a2ca` (`b59c46e`) into `dev` ·
(2) inspect and drop `wip/local-2026-08-16` · (3) push `dev`, promote `main`.

**Step 1 — chart, no tag.** Four nodes under **`<domain>`**, sibling of *"A place to try the method
without touching real work"*: the branch (`repo: shipyard`) and its three leaves, each with the
waypoint and falsifier fixed in the plan. Clears shipyard's own `uncharted` debt.

**v0.29.1 Gate** — (1) `_open_gate()` beside `_review_gate`, git read fresh, not through
`_facts_cache` · (2) wire into `api_open_cycle` after the repo checks and **before**
`scaffold_record` writes anything · (3) the three planted tests · (4) CHANGELOG + record + tag.

**v0.29.2 Queue** — (1) `/api/yard` gains the draft queue from rows it already reads · (2) Queue
band at the top of the Yard, `kit.jsx` primitives only · (3) queue depth becomes `MapBand`'s first
stage · (4) round-trip test · (5) CHANGELOG + record + tag.

**v0.29.3 Cut** — (1) delete `line.py`, `cadence.py`, `hill.py`, their endpoints, `hill_mod.init`,
and the `groups`/`heat`/`targets` keys; drop `hill_snapshots` · (2) delete `LedgerBand`,
`PortfolioBand`, `RhythmBand`, `LineBand`, `Reach`, `Appetite` · (3) `MapBand` becomes queue →
gate → receiving · (4) remove `stage` end to end; `StageChip` and `MaturityChip` collapse into
`CycleChip` · (5) `cycles: {closed, open}` into `_repo_facts()` · (6) ADR 0004 superseding note ·
(7) CHANGELOG + record + tag.

**v0.30.0 Close** — cut only when all three tags exist. The record is a real retro across the
three: what the gate refused in practice, whether the queue drained, whether the Yard got opened.

## 11. Definition of done

The sub-cycle closes when **all three PATCH tags exist**, `v0.30.0` is cut, and:

- [ ] opening a cycle is refused on a draft problem, on an unclaimed repo, and on a repo with a
      cycle already open — each 422 naming its condition
- [ ] a repo declaring `chart: none` is **not** refused; the exemption is claimed, never acquired
- [ ] a branch cycle open does **not** block a leaf cycle beneath it
- [ ] each refusal has a test that fails when its check is deleted
- [ ] a waypointless problem appears in the Yard queue and leaves it by gaining a waypoint
- [ ] the Yard renders queue, gate and receiving — and nothing else
- [ ] `line.py`, `cadence.py`, `hill.py` are gone; eight domain modules remain; the star rule holds
- [ ] `/api/projects/{pid}/line` returns 404
- [ ] no surface renders `stage`; `StageChip` and `MaturityChip` no longer exist
- [ ] strips show `n cycles` or `cycle open`, served from the cached facts bundle
- [ ] `make test` and `make check` green; the font-size ratchet has not risen
- [ ] `GET /health` still returns `{ok, checks:{db, code_root, mc}, freshness}`
- [ ] each version has a CHANGELOG entry, a cycle record, and a tag
- [ ] ARCHITECTURE.md says eight modules, and ADR 0004 carries its superseding note

**Gate to Build:** this prompt is fossilised, and it would build the same thing in anyone's hands.
