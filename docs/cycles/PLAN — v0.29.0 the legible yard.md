---
cycle: legible-yard
project: shipyard
opened: 2026-08-24
version: v0.29.0
---

# The legible yard — v0.29.0

Light plan under Development Protocol 1.0. A cycle is **atomic**: it passes all four
phases and cuts a version, or it cuts nothing.

## Problem

The Yard cannot be understood by looking at it — its owner said so out loud
("I just don't exactly understand what yard is"). Three causes, all presentation:

1. **The story lives in a code comment.** `fleet.jsx:11` states the factory flow
   (work enters at receiving, waits in the yard, passes the gate, runs the line);
   the page renders no trace of it, and the band order tells it backwards — the
   line first, receiving last.
2. **The asides defend instead of orienting.** Every `SectionHeading aside` is an
   ADR sentence ("counts, never averages"). None state the question the band
   answers.
3. **The page's main band is mislabelled.** "The ledger" is the yard — v0.28.0's
   `YardBand` was replaced by it in `6641975` — but the heading never followed,
   and the dead `YardBand` (plus `subOf`, `evidenceOf`, `BAY_META`, its only
   callers' helpers) is still in the file.

## Appetite

One sitting, 2026-08-24. Cut order if it runs long: drop the map's click-to-scroll
before the map, drop the dead-code removal before the aside rewrite, never drop
`make check`.

## In scope

- **The map** — one band at the top drawing the flow with live counts:
  Receiving (n) → The yard (n carried · momentum split) → The gate (refuses n) →
  The line (throughput, or "no cycles open"). Composed from reads the page already
  makes — the importable fetch lifts from `Importable` into `FleetPage`; the gate
  count extracts into one helper both the map and `GateBand` call, so the two can
  never disagree.
- **Band order becomes flow order** — yard → gate → line, then the measures
  (portfolio, rhythm), then standards, then receiving (collapsed intake, reachable
  from the map).
- **Asides become the question the band answers**; the doctrine lines survive where
  they fit, demoted behind the question.
- **"The ledger" retitles to "The yard"**; dead `YardBand` + its private helpers
  removed with it, per the outline.jsx precedent (row geometry goes with its last
  caller).

## Out of scope — pruned

- Any `/api` change; the payloads already carry everything the map needs.
- Next-action-per-strip, lamp semantics, bay redesign — separate cycles if wanted.
- The line's fleet-wide roll-up (still cut, per the v0.28.0 plan).

## Guardrails

- `check-ui.mjs` green — no new primitives in views, tokens only, ratchet holds.
- Grouped, never ranked — the map shows counts, no ordering among repos changes.
- The doctrine text is demoted, never deleted — legibility over restraint cuts
  both ways.

## Commit ladder

1. Map band + lifted importable fetch + shared gate helper, `make check` green.
2. Reorder + retitle + asides, `make check` green.
3. Dead code out, full `make test` green, verified in the served app.

## Definition of done

- [ ] The page opens with the flow drawn and each stage's count live.
- [ ] `make test` green — observed output, not asserted.
- [ ] The served app on :8845 shows the new page (prod build, not the dev server).
- [ ] CHANGELOG entry + tag `v0.29.0`.

## Retro

*(after review)*

---

## Retro — 2026-08-24

**What went right?** The map's counts came entirely from reads the page already
made — no API change, exactly as planned. The rewrite surfaced and removed a dead
band (`YardBand`) the plan had only suspected.

**What bit?** The anchor links: `<a href="#gate">` silently rewrites a
hash-routed app's route. The suite could not catch it — it was found only by
driving the served app, which is the second time this project's history has
taught that lesson (the changelog's own "render the real artifact" entries).
Also: the browser held the old bundle through a normal reload; verification
needed a cache-busted load before it was measuring the new code.

**Was the appetite honest?** Yes — one sitting, all three rungs, no cuts taken.

**What carries forward?** The map hard-codes nothing but stage order; when the
line gains a fleet-wide roll-up (still pruned), its stage box is the place the
number lands. Next legibility candidates, deliberately not taken here: per-strip
next actions, and grouping the yard's rows by blocker kind within a momentum
group.
