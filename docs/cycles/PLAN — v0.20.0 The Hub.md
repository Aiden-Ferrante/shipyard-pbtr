# Plan — v0.20.0 "The Hub"

Sub-cycle 2 of 5 under `GOAL PROMPT — The Face`. Appetite: **one evening.**
Human leads Plan; agent leads Build; both Test; human leads Review.

## Problem

A problem records *what it is* and *what would count as progress*. It does not record the
approaches considered, the one chosen, whether that approach worked, or how far round the loop it
is. So the loop is run from memory and written up in markdown afterwards — which is exactly what
happened for v0.19.0: a markdown goal prompt, a markdown record, and shipyard participating in
none of it.

This blocks the 1.0 criterion that has been open since 2026-08-05: *"runs a real cycle end to end,
through shipyard rather than a markdown file."*

## Vision + measuring stick

**North star:** v0.21.0's plan is written *in shipyard*, on a problem node, and its four phases
are ticked there as they complete.

**Guardrail:** *confidently wrong is worse than unsure.* An unticked phase must mean "not done",
never "we didn't ask". A `verdict` of `null` must render as untested, never as success. **The
failure worse than absence is a hub that looks filled in because the schema defaulted.**

## Constraints

- One evening. Migration + endpoints + one view.
- No new dependency.
- `make check` clean and 285+ tests green at every commit.
- **Derived beats entered** (goal prompt §0, and the archived Road-to-1.0 guardrail: *anything
  needing manual upkeep to stay true violates the July lesson*). Four of the five new fields are
  necessarily manual; **Build is not** — see D2.

## Decomposition

**AND-children:**
1. Schema — five booleans, `solved_at`, and `problem_approaches`.
2. API — phase toggle, solved toggle, approach CRUD + choose + verdict.
3. Hub view — the five sections, in the order the user named them.
4. Chart/board rollup — `n/m solved` where problems already render.

**Pruned:**
| Pruned | Why |
|---|---|
| Appetite + elapsed on a problem | Needs cycle timestamps that do not exist. v0.22.0 at the earliest. |
| Auto-closing a cycle when all four tick | Cycle close cuts a tag; that stays a human act (protocol: the version bump is the transaction commit). |
| Approach ordering / drag | Radio + add is enough for one evening. |
| Rich text in approaches | Plain text. The argument essays already exist for prose. |
| A "score" for a problem | Explicitly pruned in Road to 1.0. Still pruned. |

## Decision points

**D1 — Where do approaches live?** → new table `problem_approaches`
`(id TEXT PK, problem_id TEXT FK ON DELETE CASCADE, name TEXT, rationale TEXT,
chosen INTEGER DEFAULT 0, verdict TEXT NULL, created_at, updated_at)`
*Rejected:* a JSON column (unqueryable — *"show me every approach that failed"* is the entire
point); markdown files (the argument essays own prose already).
**`verdict ∈ {null, worked, failed, abandoned}` and it survives `chosen` moving.** Deleting the
record of a failed approach when you pick a different one is the single worst thing this feature
could do — that record is the most valuable row in the table.

**D2 — Are the PBTR marks manual?** → **Plan, Test, Review are manual. Build is derived.**
Build ticks when the problem's repo has commits after the phase was opened; it is not clickable.
*Rejected:* all four manual (violates derived-beats-entered, and Build is the one phase git can
answer honestly); all four derived (git cannot know whether you planned, and several problems
share one repo, so the other three are genuinely per-problem).
**Consequence:** the hub must show *why* Build is ticked — "3 commits since" — or a derived tick
is indistinguishable from a clicked one, which trips the guardrail.

**D3 — Does `solved` cascade from children?** → **No. It is set by hand and shows children's counts
beside it.**
*Rejected:* auto-solve when all children solve (a parent problem is not the sum of its parts —
that is the whole reason the chart has waypoints).

**D4 — Where does the hub live?** → extend `problem.jsx` (405 lines, already the problem view).
*Rejected:* a new file (a second problem surface is how the two-Chip problem started).

## Commit ladder

1. **Migration + chart.py accessors.** Idempotent: apply twice, same schema. Tests first.
2. **Endpoints.** `PATCH /api/problems/{id}/phases`, `PATCH /api/problems/{id}/solved`,
   `GET|POST|PATCH|DELETE /api/problems/{id}/approaches`. Each with a test.
3. **Derived Build.** `phase_build` computed from `git log --since` against the problem's repo,
   with the commit count returned so the UI can explain itself.
4. **Hub view** in `problem.jsx`: what it's about · possible approaches (radio + verdict) · why
   this one · the four marks · subproblems with checkboxes.
5. **Rollup.** `n/m solved` on the board row and the chart node.

## Test fixtures

- migration applied twice → identical schema
- `verdict='failed'` survives `chosen` moving to another approach ← **the D1 guarantee**
- deleting a problem cascades its approaches
- phases and solved round-trip through the API
- a problem with no repo returns `phase_build=false` and does not raise
- `make check` stays clean; the planted-violation test still fires

## Definition of done

- [ ] A problem can hold ≥2 approaches, one chosen, one with a verdict, and the verdict survives re-choosing
- [ ] Four marks persist across reload; Build is derived and says why
- [ ] An empty hub reads as empty — no field defaults to looking answered
- [ ] Board and chart show `n/m solved`
- [ ] Migration idempotent; tests green; `make check` clean
- [ ] CHANGELOG entry + cycle record + `v0.20.0` tag

## Gate to Build

This plan is fossilised. Corrections go to ADRs.
