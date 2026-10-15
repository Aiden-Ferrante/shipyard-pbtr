#!/usr/bin/env python3
"""Put hand-authored chart nodes into the store, where the app can see them.

`docs/chart.md` is a ONE-WAY export (ADR 0003): the database is the store, and
nothing reads the markdown back. So a charting session done as markdown — which is
the only form available to an agent working on a machine that does not have the
sqlite — produces reasoning the app cannot render. This closes that gap.

It is a **client of chart.py's write API**, making the same calls the UI makes. It
is deliberately NOT a parser of `docs/chart.md`: ADR 0003 rules that out, and the
reason holds — a parser makes the markdown a second writable source and brings back
the merge problem the export-only decision was taken to avoid. The seed is its own
committed data file, and once it has run the store is truth and `docs/chart.md` is
regenerated from it.

Idempotent. Nodes are matched on exact title: missing ones are created, existing
ones are left alone, edges are INSERT OR IGNORE. Re-running is a no-op that prints
what it found.

    python3 scripts/seed_chart.py --dry-run          # show the plan, touch nothing
    python3 scripts/seed_chart.py                    # apply, then re-export chart.md
    python3 scripts/seed_chart.py path/to/seed.json  # some other seed

Seed format:

    {"edits": [{"title": "<existing node>", "description": "..."}],
     "nodes": [{"title": ..., "waypoint": ..., "falsifier": ..., "description": ...,
                "notes": ..., "repo": ..., "parents": ["<existing node title>", ...],
                "kids": [ ...same shape, parent implied... ]}]}
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import chart  # noqa: E402  — needs the path above

DB_PATH = Path(os.environ.get("SHIPYARD_DB", ROOT / "data" / "shipyard.sqlite"))
CHART_EXPORT = Path(os.environ.get("SHIPYARD_CHART_EXPORT", ROOT / "data" / "chart.md"))
DEFAULT_SEED = Path(__file__).resolve().parent / "demo-chart.json"

FIELDS = ("waypoint", "falsifier", "description", "notes", "repo")


def index_by_title(con) -> dict[str, str]:
    """title -> id. Duplicate titles are reported rather than silently picking one:
    the whole script keys on title, so a duplicate makes every decision ambiguous."""
    seen, dupes = {}, set()
    for p in chart.all_problems(con):
        if p["title"] in seen:
            dupes.add(p["title"])
        seen[p["title"]] = p["id"]
    if dupes:
        raise SystemExit(
            "duplicate titles in the chart, so matching on title is ambiguous:\n  "
            + "\n  ".join(sorted(dupes))
            + "\nRename or merge them, then re-run.")
    return seen


def plan(nodes, index, parent_title=None, depth=0, out=None):
    """Walk the seed, deciding create-vs-skip per node. No writes."""
    out = out if out is not None else []
    for n in nodes:
        title = n["title"]
        parents = list(n.get("parents") or ([parent_title] if parent_title else []))
        out.append({
            "title": title, "parents": parents, "depth": depth,
            "action": "skip" if title in index else "create",
            "fields": {k: n[k] for k in FIELDS if n.get(k)},
        })
        plan(n.get("kids") or [], index, title, depth + 1, out)
    return out


def stamped(base: float, i: int) -> str:
    """chart._now() is second-resolution, so a batch insert ties on created_at — and
    sibling order in every view, the export included, is ORDER BY created_at. Ties
    would leave the order to whatever sqlite returns, which is not the order these
    nodes were reasoned out in. So each node is stamped a second apart, deliberately."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(base + i))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("seed", nargs="?", default=str(DEFAULT_SEED))
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and exit without writing")
    args = ap.parse_args()

    seed = json.loads(Path(args.seed).read_text())
    if not DB_PATH.exists() and not args.dry_run:
        print(f"no store at {DB_PATH} — start shipyard once so it creates one, "
              f"or point SHIPYARD_DB at the right file.", file=sys.stderr)
        return 2

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        chart.init(con)
        index = index_by_title(con)

        steps = plan(seed.get("nodes") or [], index)
        edits = seed.get("edits") or []

        # Bearings the seed hangs things from must already exist. Creating them here
        # would invent the top of someone's chart from a data file, which is exactly
        # the kind of write that should be refused rather than guessed.
        wanted = {p for s in steps for p in s["parents"]}
        wanted |= {e["title"] for e in edits}
        missing = sorted(w for w in wanted
                         if w not in index and w not in {s["title"] for s in steps})
        if missing:
            print("these bearings are not in the chart, so there is nothing to hang "
                  "the seed from:", file=sys.stderr)
            for m in missing:
                print(f"  - {m}", file=sys.stderr)
            return 2

        # One repo, one problem. `chart.create_problem` refuses a repo another node
        # already holds, but a seed that trips it would fail partway through the
        # write, so the collision is found here instead — before anything is written,
        # and where --dry-run reports it. On 2026-08-25 a seed listed `la4ml` on all
        # seven nodes of a branch and every one of them rendered as the same project
        # card; only the node that actually attacks the repo should carry it.
        owner = {p["repo"]: p["title"] for p in chart.all_problems(con) if p["repo"]}
        clashes = []
        for s in steps:
            repo = s["fields"].get("repo")
            # A node already in the chart is skipped, repo included — nothing is written
            # for it, so it cannot collide with anything.
            if not repo or s["action"] != "create":
                continue
            if repo in owner:
                clashes.append(f"{s['title']} — '{repo}' is already carried by "
                               f"{owner[repo]}")
            else:
                owner[repo] = s["title"]
        if clashes:
            print("a repo is attacked by exactly one problem, and this seed hands the "
                  "same repo to more than one:", file=sys.stderr)
            for c in clashes:
                print(f"  - {c}", file=sys.stderr)
            print("Leave the repo on the node that attacks it and drop it from the "
                  "rest, then re-run.", file=sys.stderr)
            return 2

        for s in steps:
            mark = "+" if s["action"] == "create" else "="
            print(f"  {mark} {'  ' * s['depth']}{s['title']}"
                  + (f"   [{', '.join(s['parents'])}]" if s["parents"] else ""))
        for e in edits:
            changed = [k for k in FIELDS if e.get(k)]
            print(f"  ~ {e['title']}   (rewrites: {', '.join(changed) or 'nothing'})")

        creates = sum(1 for s in steps if s["action"] == "create")
        print(f"\n{creates} to create, {len(steps) - creates} already present, "
              f"{len(edits)} to rewrite.")
        if args.dry_run:
            print("dry run — nothing written.")
            return 0

        base = time.time()
        created = 0
        for i, s in enumerate(steps):
            if s["action"] == "create":
                pid = chart.create_problem(con, title=s["title"], **s["fields"])
                # See stamped(): deliberate, so the export order is the authored order.
                con.execute("UPDATE problems SET created_at=?, updated_at=? WHERE id=?",
                            (stamped(base, i), stamped(base, i), pid))
                index[s["title"]] = pid
                created += 1
            for parent in s["parents"]:
                chart.add_edge(con, child_id=index[s["title"]],
                               parent_id=index[parent])

        for e in edits:
            fields = {k: e[k] for k in FIELDS if e.get(k) and k != "repo"}
            if fields:
                chart.update_problem(con, index[e["title"]], **fields)

        con.commit()
        chart.export(con, CHART_EXPORT)
        print(f"\nwrote {created} problem(s) to {DB_PATH}")
        print(f"re-exported {CHART_EXPORT} from the store — if its order differs from "
              f"the hand-authored file, the store is right and the file now says so.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
