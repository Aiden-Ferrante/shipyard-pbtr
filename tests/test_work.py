"""Work read from Backlog.md, hung off the chart by label.

The orphan behaviour is the interesting part: shipyard must never guess an
attachment, because the whole value of the layout is that unjustified work shows up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import work  # noqa: E402

TASK = """\
---
id: TASK-9
title: Engagement heartbeat
status: To Do
labels:
  - habit
  - activity
priority: high
type: feature
---

## Description
Body text.
"""

DONE_TASK = """\
---
id: TASK-1
title: Already finished
status: Done
labels: [habit]
---
"""

NO_LABELS = """\
---
id: TASK-5
title: Unlabelled work
status: In Progress
---
"""


def _repo(tmp_path, files: dict[str, str]) -> Path:
    d = tmp_path / "backlog" / "tasks"
    d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(body)
    return tmp_path


def test_repo_without_backlog_is_not_an_error(tmp_path):
    """Most of the fleet has no backlog/ — that is normal."""
    assert work.read_tasks(tmp_path) == []


def test_reads_frontmatter(tmp_path):
    repo = _repo(tmp_path, {"a.md": TASK})
    t = work.read_tasks(repo)[0]
    assert t["id"] == "TASK-9"
    assert t["title"] == "Engagement heartbeat"
    assert t["labels"] == ["habit", "activity"]
    assert t["priority"] == "high"
    assert t["open"] is True


def test_done_tasks_are_marked_closed(tmp_path):
    repo = _repo(tmp_path, {"a.md": DONE_TASK})
    assert work.read_tasks(repo)[0]["open"] is False


def test_scalar_label_is_tolerated(tmp_path):
    repo = _repo(tmp_path, {"a.md": "---\nid: T\ntitle: t\nstatus: To Do\nlabels: habit\n---\n"})
    assert work.read_tasks(repo)[0]["labels"] == ["habit"]


def test_garbage_file_is_skipped(tmp_path):
    repo = _repo(tmp_path, {"a.md": "no frontmatter here", "b.md": TASK})
    assert [t["id"] for t in work.read_tasks(repo)] == ["TASK-9"]


PROBLEMS = [
    {"id": "p1", "title": "Habit"},
    {"id": "p2", "title": "Engagement"},
]


def test_label_matches_problem_title():
    tasks = [{"id": "T1", "title": "x", "labels": ["habit"], "open": True}]
    out = work.attach(tasks, PROBLEMS)
    assert [t["id"] for t in out["nested"]["p1"]] == ["T1"]
    assert out["orphans"] == []


def test_match_is_slug_insensitive():
    tasks = [{"id": "T1", "title": "x", "labels": ["Engagement"], "open": True}]
    assert work.attach(tasks, PROBLEMS)["nested"]["p2"][0]["id"] == "T1"


def test_unmatched_label_is_an_orphan_not_a_guess():
    """Never invent an attachment — an orphan is the honest answer."""
    tasks = [{"id": "T1", "title": "x", "labels": ["release"], "open": True}]
    out = work.attach(tasks, PROBLEMS)
    assert [t["id"] for t in out["orphans"]] == ["T1"]
    assert all(v == [] for v in out["nested"].values())


def test_unlabelled_task_is_an_orphan():
    tasks = [{"id": "T1", "title": "x", "labels": [], "open": True}]
    assert work.attach(tasks, PROBLEMS)["orphans"][0]["id"] == "T1"


def test_first_matching_label_wins():
    tasks = [{"id": "T1", "title": "x", "labels": ["nope", "habit"], "open": True}]
    out = work.attach(tasks, PROBLEMS)
    assert out["nested"]["p1"][0]["id"] == "T1"


def test_no_problems_means_everything_is_an_orphan():
    tasks = [{"id": "T1", "title": "x", "labels": ["habit"], "open": True}]
    out = work.attach(tasks, [])
    assert len(out["orphans"]) == 1
