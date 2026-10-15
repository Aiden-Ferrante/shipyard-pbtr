# ADR 0004: carried repos, targets, and where each new fact lives

Date: 2026-08-18
Status: **superseded in part by v0.29.3** — see the note below

## Superseded, 2026-08-26 (v0.29.3)

Two of the four facts this ADR routed have been **withdrawn**, and the decision that
routed them is the reason the withdrawal was cheap rather than painful.

- **Hill position** — the `hill_snapshots` table held **0 rows** on the day it was
  deleted. It was the one value the ADR argued git could not supply, and it was never
  supplied by hand either.
- **Targets** — **0 problems** ever carried a `due` date.

Both were built and neither was used, so the Yard was rendering two measures of
nothing. They went with the ledger in v0.29.3, along with `line.py`, `cadence.py` and
`hill.py`.

**Membership (`repo_standing`) and the release scheme survive**, and the routing test
this ADR established survives with them: *a fact the repo declares about itself goes
in its manifest and survives a clone; an opinion about my attention goes in
shipyard's sqlite and never touches the repo's filesystem.* That sentence is the
durable part of this document.

One further correction: the argument above uses `stage: spike` as its precedent for
declaring what a repo does not owe. **`stage` was itself removed in v0.29.3** — its
meaning left with `standards.yaml` in v0.5.0 and the field outlived it by
twenty-four versions. `release: scheme: none` still makes the move the ADR describes;
it just no longer has a sibling to point at.

## Context

The Yard is being reframed from a **gate** — what can enter the line, right now — to
a **trajectory**: how each repo is moving, toward what, by when. The shape is drawn in
`docs/mockups/yard-trajectory.html` and measured against live fleet data.

That reframe needs four facts the app does not currently hold:

| Fact | Example |
|---|---|
| **membership** | this repo is one I am carrying, not merely one on disk |
| **release scheme** | this repo versions with semver tags — or never versions at all |
| **target** | this repo should be public by 2026-09-30, inside a 6-week budget |
| **hill position** | where the work feels like it sits, and whether that has moved |

The measurement that forced this: the yard scans 22 repos and `_bay_of` puts **17 of
them in one bay**, which paints 68% of the page red. Grouping is not the defect —
membership is. A repo nobody intends to open a cycle on is not *blocked*; it is **not
in the queue**, and no threshold change fixes a population problem.

The naive move is to put all four in `PROJECT.yaml`, since it is already per-repo and
already read. That is wrong for three of them, and the rule that says so is already
written in this codebase — `shelved.py`:

> Every other absence in this app is derived: a project is uncharted because nothing
> claims it, ungrouped because no heading does. This is the exception, and it is the
> only place where shipyard holds an opinion that disk cannot justify. So it is stored
> rather than inferred.

That is the test. **A fact the repo declares about itself goes in its manifest and
survives a clone. An opinion about my attention goes in shipyard's sqlite and never
touches the repo's filesystem.**

## Decision

Route each fact by that test rather than by which store is convenient.

### 1. `PROJECT.yaml` gains exactly one block

```yaml
release:
  scheme: semver-tags        # semver-tags | date-tags | changelog | none
  changelog: CHANGELOG.md    # optional — only when a file also claims a version
```

`scheme: none` is the load-bearing value. Today `untagged` is reported as debt for
every repo, but `manim` is a scratch collection that will never cut a version and
`nn-zero-to-hero` is a code-along. Declaring that is how the yard stops rendering a
**choice** as a **defect** — the same move `stage: spike` already makes.

`changelog:` present means *these two must agree*. That check is not hypothetical:
shipyard's own `CHANGELOG.md` records `[0.27.0] — 2026-08-16` while its newest git tag
is `v0.26.0`, and because `line.measure` reads tags alone, the throughput figure on the
Yard is **silently two cycles stale today**. A `version-drift` blocker kind would have
caught it the day it happened.

**Why this is safe to hand-write, and the constraint that keeps it safe.**
`repo._dump()` emits only `id`, `name`, `stage`, `description` and `links`, and does
not round-trip unknown keys — so a `release:` block would not survive a rewrite. It
survives anyway, because **shipyard never rewrites a manifest**: `write_manifest()` is
the only writer, and it refuses outright when the file already exists
(`"{name} already has a PROJECT.yaml"`). Adoption creates; nothing edits.

That is not incidental, it is the module's stated position — *"the project's identity
belongs to the project: a manifest in the repo survives shipyard being deleted, travels
with a clone."* A create-only writer is what makes the manifest safe to extend by hand,
which is the property this ADR depends on.

**The forward constraint:** if an edit path is ever added — changing `stage` from the
UI is the obvious candidate — it must read, merge and re-emit unknown keys rather than
regenerate from a fixed field list. A writer that silently drops what it does not
recognise would take `release:` with it, and would do so quietly.

### 2. Targets sit beside their waypoint, not beside their repo

```sql
ALTER TABLE problems ADD COLUMN due      TEXT;   -- ISO date, nullable
ALTER TABLE problems ADD COLUMN appetite TEXT;   -- '2w' | '6w' — a budget, not an estimate
```

`problems.waypoint` **already** records what finishing means, and `problems.repo`
already attaches it to a repo. What is missing is only *by when*. Adding a `target:`
to `PROJECT.yaml` would build a second answer to a question the chart already answers,
and `PLATFORM.md` names two-registries-describing-one-repo as the thing to unify — not
to extend. A date without its observable is a deadline with no definition of done.

`appetite` is a **budget the work must fit inside**, never a predicted finish. A repo
that overruns is rendered as over its box, and the prescribed response is to cut scope,
not to extend the bar. This is deliberate: the alternative — a percent-complete — was
rejected because a to-do list grows as work is discovered, so the number can move
backwards, and 80% of tasks done while stuck on the one hard unknown reads as nearly
shipped.

**A repo heading several problems shows the nearest `due`.** `problem_edges` is
many-to-many, so *"the repo's target"* is genuinely ambiguous — and the resolution is to
render the earliest unmet one, because the date you would miss first is the one actually
constraining you. The others are not hidden: they are listed in the repo's inspector,
where a repo's several problems already appear. **The Yard never sums or averages
them** — that would invent a portfolio-level date nobody committed to, which is the same
mistake as a percent-complete wearing a calendar.

### 3. The hill is a trail, not a position

```sql
CREATE TABLE hill_snapshots (
    repo     TEXT NOT NULL,
    at       TEXT NOT NULL,
    position REAL NOT NULL CHECK (position BETWEEN 0 AND 1),
    note     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (repo, at)
);
```

Append-only, because **the value is in the movement, not the position**. A dot that has
not moved across successive snapshots is the signal worth rendering — it means the work
is stuck and probably needs splitting — and that is a query over history, not a field.

`position` is **set by hand and never computed from commits.** It records a person's
felt sense of where the work sits: the left slope is figuring out what to do, the summit
is the moment the unknowns are resolved, the right slope is execution. Deriving it from
activity would destroy the only thing it knows that git does not.

This is the one genuinely un-derived value on the page, and it goes stale silently.
That cost is accepted; it is not hidden.

### 4. Membership subsumes shelving

```sql
CREATE TABLE repo_standing (
    repo  TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('carried', 'shelved')),
    since TEXT NOT NULL,
    note  TEXT NOT NULL DEFAULT ''
);
-- absent = never considered → Receiving
```

Carrying a repo and shelving one are the same kind of judgement pointed in opposite
directions, and both are opinions disk cannot justify. Two tables expressing membership
are two things that can disagree, so `shelved_repos` folds into this one.

Three states, one row each: **carried** (in the ledger), **shelved** (looked at,
deliberately set down), **absent** (never considered, shown in Receiving).

`shelved.py`'s invariant survives the migration unchanged: shelving is **never silent**,
and `/api/board` keeps reporting the count, because the promise it bends is that nothing
on disk is quietly missing from the board.

**The migration**, one-way and total — `shelved_repos` has live rows (2 today) and is
not left behind as a second answer:

```sql
INSERT INTO repo_standing (repo, state, since, note)
     SELECT repo, 'shelved', shelved_at, note FROM shelved_repos;
DROP TABLE shelved_repos;
```

`shelved.py` keeps its name and its docstring — it is still the module that owns the
one opinion disk cannot justify, and that opinion has simply gained a second value.
Its existing tests assert the board's count invariant and must pass unchanged; if they
need editing to survive the migration, the migration is wrong.

## Rejected

- **`target:` in `PROJECT.yaml`** — duplicates `problems.waypoint`. See §2.
- **`tier:` in `PROJECT.yaml`** — proposed early in the design and withdrawn. The chart's
  pinned sections (the `<domain>` groupings and a `<personal goal>`) already
  group repos through `problems.repo`. A tier field would be a fourth grouping invented
  beside a real one, which is the exact failure v0.28.0's D1 collapsed.
- **Hill position as a column on `problems`** — loses the trail, and the trail is the
  point.
- **Membership by manifest presence** — 22 repos already have one. Deriving membership
  from file presence would mean deleting manifests to un-carry a repo, destroying its
  description and links to express a change of attention.

## Consequences

- **`write_manifest()` stays create-only, and that is now load-bearing.** Hand-written
  `release:` blocks are safe precisely because nothing rewrites a manifest. Any future
  manifest editor must merge unknown keys rather than regenerate from a field list.
- Shipyard owns two more pieces of state that exist nowhere else (`hill_snapshots`,
  `repo_standing`). Both are covered by the existing sqlite → markdown export
  obligation; neither is a third exception to "owns no complex logic", because both are
  opinions rather than logic — the same category `shelved_repos` already occupies.
- `repo_standing` is a migration of a live table. `shelved_repos` has rows today, and
  the board's count invariant is asserted by tests that must keep passing.
- The bay distribution stops being a UI problem. With membership declared, the 77%-in-one-bay
  collapse and the all-red andon board resolve without touching `_bay_of` or `_DANGER_KINDS`.
- `scheme: none` narrows what `owed` may report, which will **reduce** the fleet's owed
  count. That is the intended effect and should be visible when it happens, not quiet.

## Settled 2026-08-18

Both open calls were made, and each closes a door worth naming.

**1. `shelved_repos` folds into `repo_standing`.** The alternative — a carried table
beside the shelved one — was cheaper to build and would have left two tables able to
claim the same repo, with nothing to stop a row appearing in both. Membership is one
question with three answers, so it gets one table and a `CHECK` constraint. The cost is
real and accepted: this migrates a live table with rows in it, so the migration ships in
the same change as the schema, never after.

**2. `due` lives on the problem.** Targets stay attached to the observable that defines
them; there is no per-repo date. This rules out the shape where a repo carries a
deadline that no waypoint explains — a date with no definition of done, which is the
failure ADR 0003 already guarded against by making `waypoint` `NOT NULL`. The
many-to-many ambiguity is answered by rendering rather than by storage: nearest unmet
`due` on the strip, all of them in the inspector, never a sum.

Both choices point the same way — **one place per fact, ambiguity resolved at read
time.** That is the same instinct as `repo.owed()` being pure over already-computed
values: two surfaces computing one number is how they come to disagree.
