# Backlog

The queue Development Protocol 1.0 assumes and this repo has never had. Three
things land here and nothing else:

- **Pruned children** — scope cut out of a cycle, written down at the moment it
  was cut. A pruned list assembled afterwards is a description of what you
  happened not to do.
- **ADR seeds** — a decision that wanted an ADR and didn't get one yet.
- **Retro items** — "what carries forward" from a closed cycle.

An item here is not scheduled. The next light plan pulls from this file; it does
not add to it mid-build.

## Pruned

- **`work.attach()` and `work.subtree()` are stranded too, and were left.** The
  2026-09-04 removal of the task write-back took only the write half of `work.py`;
  these two read-side functions lost their last route in `fea68d0` and are kept
  alive by `tests/test_work.py` alone. Sweep B1 planned to collapse the module to
  `read_tasks` + `_frontmatter`. Left because they write nothing and the ask was
  the write; take them when the orphan-under-problem view is either rebuilt or
  declared gone.

- ~~Repo inheritance upward, so a sub-problem can open a cycle.~~ **Done in
  v0.31.1.** The stated blocker — sibling version collisions — had already been
  retired by `_open_gate` one cycle before this entry was written. Re-read a
  deferred item's reason before deferring it again.

## ADR seeds

- **What a project's problem chart is allowed to look like.** ADR 0005 settled what
  an open cycle is; the shape question is still open — does the repo sit on the node
  that gets worked, or the node that names the project, and what happens to the other
  one. The backlog item above cannot be designed without answering it.

## Carries forward

- **The Directed work arc routed around its own rule on its first run** — the three
  leaf tags were cut at the shell and linked afterwards, because the API would have
  refused them for the reason above. The falsifier is not satisfied (the work was
  directed and nothing sat untagged) but the mechanism was bypassed, which is the
  distinction the falsifier exists to make visible.
- **A plan is a hypothesis.** Three of this arc's decisions were wrong on paper and
  right only after building — an unreachable refusal, the wrong field for "open",
  and an exemption written twice. Build earlier, plan less confidently.
