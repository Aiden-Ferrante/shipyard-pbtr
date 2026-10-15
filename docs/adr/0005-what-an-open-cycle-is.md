# ADR 0005: what records an open cycle, and which cycles contend

Date: 2026-08-26
Status: accepted

## Context

v0.29.1 added `_open_gate`: a cycle may not open against a problem with no
waypoint, or in a repo that already has one running. Two questions had to be
answered to write it, and both were answered wrongly on the first attempt. They are
recorded here rather than in a cycle record because they will be re-litigated the
first time a super-cycle blocks something and the answer looks like a bug.

## Decision 1 — an open cycle is a `planned` record, not `open` commits

`repo.cycles()` returns both, and the names invite the mistake:

- **`open`** — commits since the last tag. This is the normal state of every repo
  between releases. Gating on it would have refused most of the fleet on the first
  request.
- **`planned`** — a cycle *record* on disk whose version no tag has cut.

The gate reads `planned`. That is the state Development Protocol 1.0 means by an
open cycle — *"a record with no tag is open, a record with a tag is closed, and
cutting the tag is what moves it"* — and it is the state v0.29.0 closed two of in a
single tag with nothing that could have stopped the second.

The state stays on disk. **No `cycle_open` column**, for the same reason ADR 0003
keeps the chart out of the markdown and the Face cycle's D3 answered "count the
tags": a second store of a fact git already holds is a fact that will one day
disagree with git.

## Decision 2 — cycles that *compose* other cycles do not contend

A cycle with problems beneath it is meant to stay open while theirs run. Two
consequences, and the second was missed until a test caught it:

1. **A composing problem is exempt from the gate.** Otherwise its own open cycle
   blocks it from... nothing, but it would be refused the moment a child opened one.
2. **A composing cycle's record does not block anyone else.** Its record lands in the
   same repo its children cut in, so filtering only the caller is not enough:
   opening a branch cycle first refused every leaf beneath it. `planned` is filtered
   by whether the problem claiming that version has children.

An **unclaimed** record still contends. Nothing on the chart accounts for it, which
is the stray-open-cycle case exactly — the one this gate exists for.

### The discriminator is `chart.children()`, not `chart.role()`

`role()` returns `bearing` for any parentless node, whether or not anything hangs off
it. Keying the exemption on `role() != "leaf"` therefore exempted **every top-level
problem**, including a lone one that composes nothing and is precisely the single
unit of work the gate is for.

`children()` says what was actually meant: **composes work** versus **is work**.

That seam has now answered two unrelated questions in two consecutive cycles — which
cycles contend for the one-open slot (v0.29.1), and which drafts belong in the Yard's
queue (v0.29.2, where the unfiltered version opened with `<root goal>`
and its `<domain>` groupings, six of twelve rows being things that can never be started).
It is a real distinction in the chart and should be reached for by name, not
re-derived a third time.

## Consequences

- `role()` keeps its job — naming a cycle's *weight* for the record scaffold, where
  the bearing/branch/leaf vocabulary is correct — and loses the job it was briefly
  given, deciding what the gate refuses.
- A problem gains children and its cycle silently stops contending. That is intended:
  decomposing work is exactly the moment its cycle becomes an umbrella.
- The gate reads git fresh, outside `_facts_cache`, matching `_review_gate`. A
  five-second-old answer would refuse a repo you just closed out.

## Alternatives rejected

- **A `cycle_open` column.** Duplicates disk state; drifts.
- **Scoping the one-open rule per problem rather than per repo.** Two sibling
  problems would each see the same latest tag and propose the same version — the
  collision `chart.versions_claimed_in()` was written for.
- **Gating documentation at the same door.** Wanted, and deferred: `standards.yaml`
  is being rewritten, and gating on a definition about to change would bake in the
  old one.
