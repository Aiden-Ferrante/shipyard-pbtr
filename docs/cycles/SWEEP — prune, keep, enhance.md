# Sweep — prune / keep / enhance

Started 2026-08-14, after v0.20.0. A full pass over shipyard's function and layout to tag
everything as **PRUNE**, **KEEP** or **ENHANCE** before more is built on top.

Both audits complete. Backend: 58 routes — **7 PRUNE, 37 KEEP, 14 ENHANCE**.

**No 1.0 plan governs this sweep.** The old `Road to 1.0` was retired 2026-08-14 as outdated, so
nothing here defers to it — not its milestones, not its pruned list. Judge each item on the code in
front of you. **What 1.0 means is currently an open question**, and this sweep is deliberately not
the place it gets answered: prune what is dead and fix what lies, then decide what the thing is.

---

## P0 — a correctness bug, fix before anything cosmetic

**Four project panels turn a failed fetch into confident prose asserting the opposite.**

| site | on network failure it prints |
|---|---|
| `project.jsx:420` → `:444` | *"Nothing since the last release — the tag and the code agree."* |
| `project.jsx:489` → `:620` | *"No versions cut yet."* |
| `project.jsx:635` → `:642` | *"No ADRs yet."* |
| `project.jsx:284` | silently empties the Orient panel |
| `project.jsx:177,184` | Purpose vanishes with `.catch(() => {})` |

This is the exact failure mode the guardrail names: *confidently wrong is worse than unsure.* A
missing state is a blank; this is a **lie** — the app says the tag and the code agree when it does
not know. It is worse than the `{"build": true}` → 200 hole fixed in v0.20.0, because it is
already user-visible.

**Fix:** these five `.catch` handlers must set an error, not a plausible empty value.

---

## PRUNE

| # | What | Evidence |
|---|---|---|
| 1 | **`chart.jsx` — all 387 lines** (6% of the frontend) | All 5 exports have zero external uses; `project.jsx:2` imports `Chart` and never renders it |
| 2 | **`GraphPage`'s non-embedded branch** | `embedded=false` default at `:150`, dead `PageHeader` `:296–311`, back button `:227–236`, permanent no-op `onClose?.()` `:176`. Both call sites pass `embedded`; no `#/graph` route exists |
| 3 | **Duplicate delete confirmation** `goals.jsx:681–728` (48 lines) | Identical payload and copy to `:1389–1429` on the same page |
| 4 | **Four zero-use `ui.jsx` exports** | `TileRow` `:164`, `Tile` `:168`, `AttentionList` `:356`, `AttentionItem` `:363` |
| 5 | **Four `kit.jsx` exports with no external consumer** | `STAGE_STYLE`, `STALE_DAYS`, `COLD_DAYS`, `daysSince` |
| 6 | **Phantom imports** | `project.jsx:8` `StatusDot` unused · `fleet.jsx:2` `activityTone` unused · `project.jsx:32` re-exports `SideHeading` for nobody |
| 7 | **Dead state in `Copy`** `goals.jsx:342–343` | `outline`/`query` declared, never read — a fix started and abandoned |
| 8 | **Unused props** | `ui.jsx:147` `Chip mono` never passed · `ui.jsx:185` `Table empty` passed once, three call sites render `undefined` |
| 9 | **Goal-window modal** `goals.jsx:1458` | Renders the same `ArgumentPage` as `#/argument` |

**Open question on #1:** `AnchorControl` (`chart.jsx:74–161`) is the **only** UI that can set
`anchored`. Anchoring is *displayed* in five places (`board.jsx:227`, `graph.jsx:415`,
`problem.jsx:504`, `goals.jsx:663,1332`) and **settable in zero** — the control is already
unreachable. Either rehome it onto the problem page or accept that `anchored` becomes a
backend-only concept. **Decide before deleting the file.**

---

## ENHANCE

1. **Command palette** (`palette.jsx`, 68 lines) — indexes projects only; seven routes exist and
   it reaches one. Cannot find a problem, goal, argument or doc. Its own comment concedes it "runs
   no commands". It is the app's only global keyboard entry point.
2. **Problem page** — now the click target of every chart surface (`goals.jsx:1237,1299`,
   `graph.jsx:383`, `tree.jsx:198`) but a dead end back toward work: `node.repo` is a bare `<code>`
   at `:502`, not a link to `#/project/<repo>`. v0.20.0 gave it substance; navigation did not follow.
3. **Decisions tab** (`project.jsx:630–663`) — title + filename only, no count (`TABS` `:671` sets
   none although `ui.jsx:94` supports it), no error state.
4. **Purpose panel** (`project.jsx:160–272`) — renders `null` for 17 of 19 projects by design. The
   most valuable panel is invisible almost everywhere.

---

## Consistency debt

- **"no waypoint" has six spellings** across `board.jsx:100,241`, `outline.jsx:116`,
  `goals.jsx:631`, `project.jsx:237`, `problem.jsx:488` — three different tones for one state.
- **The waypoint label is hand-copied four times** (`board.jsx:97,237`, `problem.jsx:483`,
  `fleet.jsx:416`) while `outline.jsx:88` `WaypointCell` is the real component nobody uses.
- **"uncharted" is computed from two different fields** — `board.jsx:43` keys on `!p.sounding`,
  `fleet.jsx:366` on `!p.why`.
- **Three delete confirmations** with three different phrasings (`goals.jsx` ×2, `tree.jsx:323`).
- **Cycle linking has two UIs** — only `tree.jsx` can open a cycle, only `problem.jsx` shows open
  state.
- **Dates render four ways** — `relTime()`, an ISO slice (`fleet.jsx:205`), and two raw prints.

---

## v0.19.0 did not finish

The consolidation landed on the files it touched and never reached the rest:

| file | raw font sizes |
|---|---|
| `fleet.jsx`, `graph.jsx`, `ui.jsx`, `outline.jsx`, `kit.jsx` | **0** |
| `project.jsx` | 35 |
| `goals.jsx` | 34 |
| `tree.jsx` | 25 |
| `problem.jsx` | 20 |
| `chart.jsx` | 20 (moot if pruned) |

And `<Loading>` has already drifted — raw loaders at `project.jsx:287`, `problem.jsx:85`,
`goals.jsx:47,585`. The ratchet holds the total but not the distribution.

**Measured adherence: 4 of 17 surfaces use all three of Loading/ErrorState/EmptyState.**
`EmptyState` has **one** call site in ~6,300 lines.

---

## P0b — what v0.20.0 got wrong (mine, from today)

Four defects in code committed this session. Listed first because they are the newest and the
cheapest to fix while the reasoning is fresh.

| site | defect |
|---|---|
| `main.py:1416` `GET /api/problems/{pid}/approaches` | **Born dead one commit ago.** `problem.jsx:349` reads `node.approaches` off `/api/chart/{ref}`. A duplicate read path that never had a consumer. **PRUNE.** |
| `main.py:1376,1394` phases + solved | Return a raw `_problem_row` dict, not the `_row`-decorated shape every other problem route returns — missing `draft`, `anchored`, `pinned`. Three shapes for one concept across five neighbouring routes. |
| `chart.py:1058` `add_approach` | Never validates `pid`. POSTing to a nonexistent problem returns **200 and inserts an orphan row**. |
| `problem.jsx:383` | Never sends the `set_verdict` sentinel, so clearing a verdict back to *untested* is **unreachable from the UI** — the flag I added specifically to make that possible. |

---

## P1 — the triple scan

`fleet.jsx:282-285` fires `/api/projects`, `/api/owed` and `/api/board` in one `Promise.all`. All
three run the **same** full sweep: `main.py:274-282` and `:299-306` are byte-identical five-line
blocks, and the board does it a third time at `:558`.

Measured: 22 manifests × ~7 git subprocesses each ≈ **460+ `git` process spawns and 3 full
`os.walk` passes for one page load.** `scan_manifests()` appears at 23 call sites with no cache.

`/api/owed`'s own docstring claims it is "built on `project_view` rather than beside it". It is
beside it.

**Not a deletion** — all three have real consumers. It is the largest measured waste in the backend.

---

## PRUNE — backend

| # | What | Evidence |
|---|---|---|
| B1 | **work/task write-back** — routes `:689`, `:750`, `:755` + 6 of work.py's 8 functions (~150 lines) | Consumer deleted in `c1f2405`, whose message says the endpoints were left standing as a *deferred decision*. This is that decision. Strands `work.slug/attach/cli_available/_run/set_label/subtree`; collapses work.py to `read_tasks` + `_frontmatter`. Also removes the only shell-out to an external CLI. |
| B2 | **`GET /api/drift`** `:1174` | Consumer removed in `f73c244` — the `-fetch('/api/drift')` line is in that diff. Its second half re-derives `/api/board`'s uncharted list into a different shape. Only remaining callers are 4 test assertions. `chart.drift` survives — `render_markdown` uses it. |
| B3 | **`GET`/`DELETE /api/templates/{slug}`** `:1048,:1077` | `git log -S"api/templates/" -- frontend/` returns **no commits at all** — never wired, not un-wired. Strands `templates.delete`. |
| B4 | **`GET …/approaches`** `:1416` | See P0b. |

## Soundings — the biggest quiet cost

`c002e75 refactor(ui): stop drawing soundings` removed every rendering. The value is now displayed
**nowhere** — `p.sounding` survives only as a truthiness test for "charted". But the backend still
computes `effective_sounding` on **six read paths** (`main.py:256,569,621,707,1164`,
`chart.py:793,796`) via a recursive per-node subtree walk, for zero pixels. 5 of 56 problems carry
a non-`assumed` value.

The data was kept deliberately. The **computation** on every read was not a decision — it is
leftover.

## Inconsistency worth one pass

- **404 vs 422 for "no such problem"**: 8 routes 404, 7 routes 422, and 3 return **200** (`GET
  …/approaches` empty, `POST …/approaches` orphan insert, `DELETE …/cycles/{version}` silent success).
- **`GET /api/projects/{pid}` drops `by_cwd`** (`:340`) where `/api/projects` and `/api/board` pass
  it — so the same project reports different `mc_info` depending which endpoint you ask.
- **Four `slug` implementations**, three near-identical, `_SLUG` redeclared three times.
- **`SOUNDINGS` declared twice** — `chart.py:21` and `arguments.py:22`.
- **Route `:755` takes `problem_id` as a query param** while its POST twin takes a body.

---

## Proposed sequence

Not yet a cycle — a candidate ladder once the backend audit lands.

| | |
|---|---|
| **A** | The five lying `.catch` handlers (P0), then the four v0.20.0 defects (P0b). Correctness, not cleanup. |
| **B** | Prune 1–9 above, after deciding the `AnchorControl` question. |
| **C** | One "no waypoint" rendering, one waypoint label, one delete confirmation. |
| **D** | Finish v0.19.0 on the four untouched files; lower the ratchet baseline. |
| **E** | Palette over all seven routes; problem→project link. |
| **F** | Backend prunes B1–B4; stop computing soundings on read; one cache for the triple scan. |
