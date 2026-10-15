# ADR 0003: the chart lives in sqlite, with a committed markdown export

Date: 2026-08-05
Status: accepted

## Context

Shipyard is gaining a **chart**: a DAG of problems, where a project is a problem
that happens to have a repo attached. Each problem carries a waypoint (the
observable that says it is moving), a sounding (`assumed` / `proxy` / `observed`),
and optionally an anchor — a date and basis recording that the belief has been
deliberately frozen. Vocabulary is fixed in the vault's `7.) Chart Vocabulary`.

This collides with shipyard's own definition: *"one pleasant front end over the
tools that already hold the truth — it reads and writes them, and owns no complex
logic of its own."* Everything shipyard renders today is read from somewhere else:
manifests from repos, checklist facts from disk, activity from git, runtime status
from Mission Control. The chart is different. **No existing tool holds it.**

Two candidates were weighed:

- **Markdown in the Obsidian vault.** Truth stays in a tool already in daily use,
  edits work from both sides, no new store, Obsidian's graph view for free. Costs a
  parser and a concurrent-edit story.
- **Shipyard's sqlite.** Simple, transactional, fast graph queries, no parser.
  Costs: shipyard becomes an owner of truth.

## Decision

**The chart lives in shipyard's sqlite**, in two tables (`problems`,
`problem_edges`), alongside the existing `checks` table.

This is a **deliberate exception** to the "owns no complex logic" rule — the second
one, after `standards.yaml`. It is accepted knowingly, on two conditions:

1. **A one-way markdown export, committed to the repo.** `data/*.sqlite` is
   gitignored, so without this the highest-value artifact shipyard holds — months of
   recorded reasoning and dated decisions — would sit in an untracked file with no
   history and no backup. Export only: no parser, no merge conflicts, no
   concurrent-edit problem.
2. **The vault-as-truth option stays reversible.** The export is the migration path
   if that reversal is ever wanted.

A third exception is not available. If one is ever proposed, the definition is wrong
and gets rewritten rather than exempted again.

## Schema

```sql
CREATE TABLE problems (
  id            TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  waypoint      TEXT NOT NULL,          -- required: no waypoint, no problem
  sounding      TEXT NOT NULL DEFAULT 'assumed',
  repo          TEXT,                   -- set => this problem is a project
  anchored_at   TEXT,                   -- set => frozen prior
  anchor_basis  TEXT,
  falsifier     TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE problem_edges (
  child_id  TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  parent_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  PRIMARY KEY (child_id, parent_id)
);
```

**One node type.** `rung`, `lens` and `subproblem` all collapse into `problems`;
direction is an edge, not a type. A row with a non-null `repo` is a project.

`waypoint` is `NOT NULL` and rejected when blank at the API boundary: a problem
without an observable is a category, not a problem, and admitting one would let the
chart fill with unfalsifiable prose — the exact failure the chart exists to prevent.

`problem_edges` is many-to-many because a project can serve several bearings. That
is not incidental: a project with a second parent survives one of its parents being
thawed, and a project with a single parent goes straight to drift.

## Consequences

- Shipyard now owns state that exists nowhere else. The export is what makes that
  survivable, so **the export is not optional and ships in the same cycle**.
- Graph queries stay in SQL — cheap, no new dependency.
- Sounding propagation (a parent can be no better-evidenced than its children) is a
  read-time computation over the edges, not stored. Aggregators are derived.
- Cycles are possible in principle. Not guarded in v0.2.0; the composer only creates
  a node with one edge at a time, so a cycle needs deliberate effort. Revisit if
  re-parenting ever lands.
