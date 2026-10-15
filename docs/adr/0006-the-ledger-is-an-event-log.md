# ADR 0006: the session ledger is an event log, and that is why it may be stored

**Status:** accepted 2026-09-04 · **Cycle:** v0.34.0 · **Problem:** `cb7a672f083a` "An agent's session is a record"

## Context

Every other fact in shipyard is derived at read time from the rows that already exist — standings,
focus slots, the Yard, cycle counts. ADR 0004 argued against a second table when one column will
do, and `chart.py` repeats "derive, never store" because a stored count is a number that will one
day disagree with the rows it claims to describe.

The fleet's 2026-09-04 agent survey found no column anywhere that says *who* made a change, and no
way to answer "what did the agent do while I was away" except by reading git logs in eight repos and
guessing which anchors landed in the same hour.

## Decision

Two stored tables — `sessions` and `session_events` — plus `problems.updated_by`, written by
`backend/app/ledger.py`. Chart write routes append their own event when the request carried
`X-Actor: claude-code:<session_id>`; Claude Code hooks post the session's open, close, and git events.

## Why this does not break the rule

"Derive, never store" is about **state**: a fact that can be recomputed from other rows and will
drift if cached. A session is **history**: the fact that a commit, a tag and an anchor happened in
the same session exists at one moment and nowhere afterwards — not in git (a commit does not know
which agent process made it), not in the chart (an anchor knows its basis, not its author). It can
only be recorded when it happens. An append-only log is the one shape of stored fact that has no
derived twin to disagree with.

So the ledger is deliberately nothing but events: no status column, no rollup, no cached count.
Anything that looks like a summary (sessions per repo, events per kind) is computed on read.

## Consequences

- `X-Actor` is a record, not authentication. Nothing verifies it; shipyard binds loopback and has
  no auth (the loopback bind is the boundary, as it is for every other write).
- A ledger failure never undoes a chart write (`ledger.record` swallows sqlite errors).
- The fleet MCP sets the header from the session file the SessionStart hook writes; a session with
  no hook reads as `claude-code:unknown` and records no events — visible, not fatal.
- helm shows sessions beside decisions; it stores nothing (rule 3, "a reflector is wrong only by
  being stale").
