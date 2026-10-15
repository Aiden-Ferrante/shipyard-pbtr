# Plan — v0.28.0, the yard

Sub-cycle plan under [[0.) Development Protocol 1.0]]. Follows **v0.27.0 — The measured line**,
and like it attacks **Software Factory** (repo `shipyard`) — this time the *intake* clauses:
**work enters in one shape** and **a gate can stop the line**.

Appetite: **not set here.** Same reason as v0.27.0 — the duration is the user's to write. The cut
order, which is the part that binds: drop the gate's UI before its enforcement, drop the yard's
grouping controls before its content, and do not drop the planted-violation test.

## Problem

Fleet is a **roster**. Four groupings — repo, goal, debt, memory — over the same 21 nouns, each
answering *how are my repos doing*. That is a question about **inventory**, and the factory
question is about **flow**: what is moving, where is it stuck, what cannot get in.

This is the same state-versus-transition split that made `line.py` necessary in v0.27.0, and Fleet
is the largest surface built on the losing side. Its failure mode is already recorded in this
repo's own history: shipyard sat 48 commits past its tag for five days while its header faithfully
reported `48 ahead · 37 unpushed`. **The instrument existing is not the loop closing.** Fleet is
that lesson at page scale — it reports accurately, then requires you to go looking, and not one of
its four groupings ends in an action.

**Measured before planning, and it changes the plan.** There is exactly **one** open cycle
(v0.27.0, opened today), and of five repos sampled — shipyard, manalab, stocklake, fleet-ui,
glm-harness — only glm-harness has any Backlog tasks at all, nine of them. So a work-in-flight
board drawn today is one row over four empty columns. The half of this page that has content is
the half about work that has **not** entered the line.

## Vision + measuring stick

**North star:** open Fleet and know, without opening another page, what can enter the line, what is
blocked from entering, and why.

**Guardrail 1 — no band that is only a re-sort.** Fleet's existing problem is four views of one
snapshot; adding a fifth is the same mistake with a factory vocabulary. A band ships only if it
changes what you would *do*, not what you would *see*.

**Guardrail 2 — the page never ranks repos.** Same call as `/api/owed`: grouped, never scored. A
rank answers "which repo is worst"; the question here is "what is blocked, and on what".

**Guardrail 3 — a gate that has never refused anything has not shipped.** `test_ui_contract.py`
is the pattern: assert the checker, then plant a violation and assert it is caught. Rule drift and
compliance look identical from outside.

## Decisions

**D1 — Fleet's unit becomes work, not repo.** A repo stops being the row and becomes an attribute
of the row.
*Rejected:* a fifth grouping, `By line`. That is Fleet's existing failure performed once more —
the roster is not short of ways to sort itself, it is short of a question worth asking.

**D2 — Two bands, and only the yard ships in v0.28.0.** *The line* (open cycles as rows, P·B·T·R
as columns, position read off disk) is designed here and **deferred** until there are cycles to
draw. *The yard* — everything not on the line yet — ships now, because that is where the content
is.
*Rejected:* shipping both. An empty WIP board on day one teaches you to ignore the page, which is
the exact habit that made the current Fleet useless.

**D3 — `owed` is re-read as an intake predicate, not repo health.** Same computation, new
sentence: not *"this repo is untidy"* but **"this repo cannot enter the line"**. No new endpoint,
no new storage — `repo.owed()` stays pure over already-computed values and the star holds.
*Rejected:* a new intake-readiness score. See Guardrail 2.

**D4 — The gate gets teeth in this cycle.** A cycle cannot tick `review` while its repo owes
uncommitted or unpushed work, enforced at the API boundary as a 422 — the same place the chart
already refuses a waypointless problem, and for the same reason: a refusal a UI can skip is a
suggestion.
*Rejected:* an advisory banner. A gate nothing has died on is indistinguishable from a gate that
cannot fail, which is this node's own falsifier.

**D5 — The yard is grouped by what blocks entry, not by repo.** The four existing groupings
collapse into one question with named answers: owes work · no waypoint · uncharted · shelved. A
repo appears under the reason it cannot start, and appears once.

**D6 — The page composes as six bands in console order** (folded in 2026-08-16, validated
against a mockup before build — `docs/mockups/fleet-factory-floor.html` — the same test the
Fleet row itself passed): **andon** · **the measured line** · **the line** · **the gate** ·
**the yard** · **receiving**. Only the yard, the gate and the head pair are this cycle's;
andon and the track are the next one's, behind the same honesty condition as D2. What each
band is bound to:

- *Andon* renders only when lit and names the station — running-old-code is the red. Green is
  silence; an empty andon band draws nothing at all.
- *The measured line* is the v0.27.0 pair at the head, windowed; below n=5 it shows the count,
  never a rate.
- *The line* is P·B·T·R as a track schematic. The stations are always drawn because they are
  the factory, not a hope that work will fill them — which is how a track dodges the empty-board
  failure D2 names while a kanban board cannot. Occupancy sits inline at the station; seam
  markers appear only where finished work actually waits; **awaiting delivery** (review done,
  tag owed) is a real git state, not a column.
- *The gate* is the rule as a chip and refusals as a log of named events — never a gauge, never
  a score. Signals default restrictive: unknown renders as not-cleared, not as green.
- *The yard* is D5's bays as **strip bays**: the bay a strip sits in IS its blocker, within-bay
  order is admission time only, and attention is the cocked strip — offset plus a heavy left
  rule, no extra hue spent.
- *Receiving* is the importables section, unchanged.

**Colour is doctrine, pinned once and spent nowhere else:** green = flowing · amber = owed ·
red = refused / line stopped · blue = on the line · zinc = inert (shelved, stopped) and never
de-emphasis.
*Rejected:* a kanban column board (see the track, above) and per-station hues — a station is
named by its letter; colour is reserved for state.

**D7 — One strip, one vocabulary, three densities.** The strip is D1's row unit: one fixed
field order (lamp · repo · stage · position-or-blocker · evidence · age) carrying what the four
retired groupings each showed. The same words appear at three zoom levels — the bay's name, the
strip's chips, the inspector's met/missing gate checklist — so the 422 body, the yard grouping
and the drawer read as one sentence. New primitives land in `ui.jsx` (Strip, Bay, StationTrack,
Lamp, SeamMark, GateBadge, Spark), token-only, under the existing check-ui rules; `kit.jsx`
stays product-blind.

## Open, and deliberately not scoped here

**Chart writes are unbacked, and it has now cost real work.** During the v0.27.0 planning session a
repo link and a cycle address were both lost from `data/shipyard.sqlite` while a second window
worked the same repo; root cause was not determined. `data/` is gitignored, `docs/chart.md` is
one-way by ADR 0003, and `seed_chart.py` rebuilds only what was hand-authored into seed JSON — so
nothing written through the UI has a recovery path. This is durability, not a gate, and forcing it
into this cycle would blur D4. **Named here so it is not lost; it wants its own cycle.**

## Commit ladder

1. `/api/board` or a new `/api/yard` returns entries grouped by blocking reason (D5), composed in
   `main.py` from `owed` + chart state. No new module unless composition alone cannot do it.
2. Fleet's four groupings replaced by the yard band — strip bays per D6/D7, primitives first.
   `RepoInspector` survives (it is the one part of the page that already answers a question) and
   gains the gate's met/missing checklist.
3. The gate: 422 on ticking `review` against an owing repo, plus the planted-violation test; the
   refusal surfaces in the gate band as a logged event.
4. v0.27.0's throughput and rework pair mounted at the head of the page — the big board.
5. The line band — the track — **behind whatever makes it honest**: draw cycles on it only when
   open cycles exist. The stations themselves may ship drawn and empty, per D6.

## Definition of done

- [ ] Fleet answers "what can enter the line, what cannot, and why" without navigation
- [ ] Every yard entry carries the reason it is blocked; nothing is listed without one
- [ ] The gate has refused a real tick, and a planted violation proves it still can
- [ ] Throughput and rework appear together at the head, and cannot be read apart
- [ ] No score, no ranking, no repo listed twice
- [ ] Colour doctrine holds with zero exceptions — green flowing · amber owed · red refused ·
      blue on the line · zinc inert only, never de-emphasis
- [ ] Nothing renders empty scaffolding: andon silent when clear, a bay absent when empty; the
      four stations are the one committed exception
- [ ] No new storage; `repo.owed()` unchanged and still pure
- [ ] The line band ships empty-by-design or not at all — never as a fake WIP board
- [ ] `make check` clean, tests green, CHANGELOG + tag, `main` fast-forwarded
