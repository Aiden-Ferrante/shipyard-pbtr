"""Open work, read from a repo's Backlog.md files and hung off the chart.

Shipyard owns none of this. Tasks live in `backlog/tasks/*.md` inside the project,
and which problem a task serves is recorded **in the task** as a label — the same
reasoning that kept group membership in PROJECT.yaml. Shipyard matches label slug to
problem title slug at read time and stores nothing.

The consequence is deliberate: an unlabelled task is an **orphan**, and says so. A
flat list makes every task look equally justified; nesting under the problem it
serves is what makes work with no stated reason visible.
"""

import re
from pathlib import Path

import yaml

OPEN_STATUSES = {"to do", "todo", "in progress", "wip", "blocked"}
_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    return _SLUG.sub("-", (text or "").strip().lower()).strip("-")


def _frontmatter(text: str) -> dict | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def read_tasks(repo: Path) -> list[dict]:
    """Every task in a repo's backlog. A repo with no `backlog/` is normal, not an
    error — most of the fleet has none."""
    tasks_dir = Path(repo) / "backlog" / "tasks"
    if not tasks_dir.is_dir():
        return []
    out = []
    for f in sorted(tasks_dir.glob("*.md")):
        try:
            fm = _frontmatter(f.read_text(errors="replace"))
        except OSError:
            continue
        if not fm:
            continue
        labels = fm.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        status = str(fm.get("status") or "").strip()
        out.append({
            "id": str(fm.get("id") or f.stem),
            "title": str(fm.get("title") or f.stem),
            "status": status,
            "open": status.lower() in OPEN_STATUSES,
            "labels": [str(x) for x in labels],
            "priority": fm.get("priority"),
            "type": fm.get("type"),
        })
    return out


def attach(tasks: list[dict], problems: list[dict]) -> dict:
    """Hang each task off the problem whose title its label matches.

    Never guesses: a task with no matching label is an orphan, full stop. Inventing
    an attachment would defeat the point of the section that shows them.
    """
    by_slug: dict[str, dict] = {}
    for p in problems:
        by_slug.setdefault(slug(p["title"]), p)

    nested: dict[str, list[dict]] = {p["id"]: [] for p in problems}
    orphans: list[dict] = []

    for t in tasks:
        hit = next((by_slug[slug(l)] for l in t["labels"] if slug(l) in by_slug), None)
        if hit:
            nested[hit["id"]].append(t)
        else:
            orphans.append(t)

    return {"nested": nested, "orphans": orphans}


# The write-back that used to live here (attach/detach a task by writing its label
# through the `backlog` CLI) was removed 2026-09-04 — see CHANGELOG. Its one rule is
# worth keeping even without the code: when shipyard writes into a repo, it follows
# that repo's conventions. A front end over other people's tools does not get to
# impose its own file format on them.


def subtree(problems_of: callable, root_id: str) -> list[dict]:
    """Every problem at or below a root, breadth-first, deduped."""
    seen: dict[str, dict] = {}
    queue = [root_id]
    while queue:
        pid = queue.pop(0)
        for kid in problems_of(pid):
            if kid["id"] in seen:
                continue
            seen[kid["id"]] = kid
            queue.append(kid["id"])
    return list(seen.values())
