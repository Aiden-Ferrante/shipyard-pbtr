<!-- fleet:begin -->
# Working in the fleet — what every agent session needs to know

This block is rendered from `fleet/agents/common.md` + `fleet/agents/shipyard.md` by
`fleet/render_agent_docs.py`; a checker fails when a copy drifts. Edit the source, not this file.

## The system you are inside

Eight repos, three tiers, one protocol. **Libraries** (fleet-ui: tokens + header + the class kit;
vaultwriter :8799: the only process that writes the Obsidian vault) → **Daemon** (mission-control
:9090: starts, stops and probes every app) → **Surfaces** (shipyard :8845 owns the chart; helm :8990
is the task scheduler; learnhub :3001/:8010; feedwall :8975; content-manager :8955). Edges point up:
a lower tier never imports, reads or learns about a higher one. `fleet/` holds the checkers and the
agent tool layer.

## How to reach the apps

Use the **fleet MCP** (`fleet` server, registered by this repo's `.mcp.json`; ~50 tools named
`shipyard_*`, `helm_*`, `mc_*`, `learnhub_*`). Reads are marked read-only. Writes change state.
Destructive tools (`shipyard_thaw`, `shipyard_delete_problem`, `mc_stop_app`) need the
`impact_token` their impact read returned **and a human's yes**. A refusal from any tool carries the
app's own sentence — it names the missing fact. Fix the fact; never route around a gate with curl.

## The protocol: a cycle, or nothing

Work is a **PBTR cycle** (Plan → Build → Test → Review) on a chart **problem** that has a
**waypoint** (an observable). Open it with `shipyard_open_cycle` — refused when the problem has no
waypoint or the repo already has an untagged record. Build in one Conventional Commit per rung. Test
means observed output on real data, pasted into the record in `docs/cycles/`, never "tests pass".
Close by moving CHANGELOG's Unreleased under the version, `git tag -a vX.Y.Z`, push, and
`shipyard_tick_phases review` — refused while the repo owes uncommitted or unpushed work. **The tag
is the transaction commit; a record with no tag is an open cycle.** Full protocol: the `pbtr` skill.

**Decisions are anchors.** A scope cut, a "not before X", a "never Y" — record it with
`shipyard_anchor` (or `helm_record_decision`) on the problem it decides. Not in a plan file, a memory
note or a daily note. Lifting an anchor (`shipyard_thaw`) puts everything above it back in question;
read its impact first and ask.

**Roles.** The human owns why and what — the problem, the waypoint, every decision point,
acceptance. You own how. Where the spec is silent, take the boring option. Where reality contradicts
the spec, flag and stop; the fork becomes an ADR seed. Never "improve" something silently.

## Chart words (never invent a ninth)

Problem · Bearing (a top-level problem a domain hangs from) · Waypoint (the observable) · Sounding
(evidence grade: assumed / proxy / observed; a strong child cannot lift a weak parent) · Anchor (a
dated decision, frozen) · Drift (work serving no bearing — information, not failure) · Ground ·
Chart. A project is a problem with a repo attached; one repo, one problem.

## What holds the fleet together (run before you close)

- `bash fleet-ui/check.sh` — visual: every colour, type size and face from fleet.css; no `dark:`;
  no `outline: none`; registry copies and built bundles know every app.
- `python3 fleet/check_fleet.py` — structural: Makefile test targets resolve, streams have onerror,
  apps.js ⨝ apps.yaml, AI 101 section keys, agent docs current.
- `python3 mission-control/scripts/check_freshness.py` — runtime: every `/health` conforms to
  `{ok, checks, freshness}`; `ok` covers only what the app owns.
- The repo's own `make test`. A green suite over fixtures never closes a phase — open the real page.

## Never

Write the vault by any path but vaultwriter · `git push --force` (a hook refuses it) · `rm -rf` a
checkout · `git checkout --` / `reset --hard` / `clean` without `git status` first (uncommitted work
is not in git) · print, commit or type a secret · restyle onto `--fleet-*` names (alias instead) ·
grow one app into another's tier (helm is the scheduler; shipyard owns the chart; MC owns processes).

## Ports (rendered from fleet-ui/apps.js)

| tab | app | port | what |
|---|---|---|---|
| Shipyard | `shipyard` | `:8845` | projects, goals, what the fleet owes |
| Control | `mission-control` | `:9090` | what is running |
| Learn | `learnhub` | `:3001` | courses, study queue, uploads |
| Feed | `feedwall` | `:8975` | what the frontier said this week |
| Content | `content-manager` | `:8955` | channels, productions, scripts |
| Helm | `helm` | `:8990` | what needs me now, agenda, decisions |
| — | `vaultwriter` | `:8799` | the one vault writer (library tier) |
| — | `learnhub` API | `:8010` | Learn Hub's FastAPI behind the :3001 UI |

## shipyard — owns the chart

The chart (problems, edges, anchors, cycles, focus) lives in `data/shipyard.sqlite` and is exported
one-way to `docs/chart.md` on every write (ADR 0003) — review that diff before you commit. The two
hard gates are here: `_open_gate` (no waypoint / open record) and `_review_gate` (owed work).
Templates in `templates/*.yaml` are starting shapes, never standards. The Yard is derived from git
and MC on every load; nothing there is stored.

**Correction to ADR 0001** (recorded in `fleet/CONVENTIONS.md §3`): the ADR says "repos never get
written to by the app". That is false in three places by design — `POST /api/importable` writes a
`PROJECT.yaml`, and the arguments/documents/templates dirs are vault paths. Do not resolve the
contradiction by deleting the writes.

`make test` runs pytest (`tests/`, tmp fleet fixture) then vitest; `make check` runs the UI check
and fleet-ui's check.sh. main is prod, dev is the workbench (ADR 0002). Another session may be
committing here — `git pull --rebase` and `git status` before you add.
<!-- fleet:end -->
