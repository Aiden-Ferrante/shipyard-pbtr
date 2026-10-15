# ADR 0001: shipyard architecture

Date: 2026-07-09
Status: accepted

## Context

The fleet (17 codebases in `~/Desktop/code/`) has strong runtime conventions
(Mission Control, `{ok,checks,freshness}` health, vaultwriter write contract) but
no lifecycle layer: no shared answer to "what stage is this project at, what does
the standard require of it next, and where do its artifacts live". Three
architecture decisions were made before building.

## Decisions

1. **Data home: per-repo manifest + central state DB.**
   Each repo carries a `PROJECT.yaml` (identity, stage, links) that is versioned
   with the code and visible on GitHub. Checklist *state* (done/notes/timestamps)
   lives in shipyard's sqlite. Rationale: the standard travels with the code;
   the app stays a thin aggregator; repos never get written to by the app.
   Rejected: fully-central sqlite (standard invisible at the repo), fully
   git-native markdown (app would need write access to every repo).

2. **Stack: FastAPI + React (vite).**
   Matches the maintained patterns in mission-control and vault-dashboard; the
   UI (stage board, checklists) will grow. Rejected: zero-dep stdlib (UI would
   strain it), server-rendered (no strong reason to diverge from fleet pattern).

3. **Mission Control integration: read-only bridge.**
   Shipyard reads MC's `apps.yaml` (single registry of runnable things stays MC's)
   and proxies MC's status API for live health chips. No write coupling; shipyard
   degrades gracefully when MC is down. Two-way integration (MC showing stage) is
   deferred until the manifest format has settled.

## Consequences

- A new fleet-wide contract: `PROJECT.yaml` at repo roots (kept minimal).
- The checklist standard is code (`standards.yaml`, versioned) — evolving it is
  a normal commit, and unmet items surface per-project automatically.
- Shipyard itself is the first repo born fully under the standard it manages.
