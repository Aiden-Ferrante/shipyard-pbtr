"""The standards surface — what the conventions are, and which have teeth.

The point of this file is narrow and worth stating: the band's whole value is the
**enforcer column**, and an enforcer column that lies is worse than no column at
all, because it reads as coverage. So these tests assert the two ways it could lie
— claiming a file that is not there, and claiming an enforcer that is not there.

The second test is the one that matters, and it is the same shape as
`test_fleet_drift.py`'s: a checker that never fires is indistinguishable from a
checker that cannot fire. Here, a `present` flag that never goes False is
indistinguishable from one that cannot.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import conventions as standards  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_it_describes_standards_and_never_a_repo():
    """The v0.5.0 line, asserted rather than remembered.

    `standards.yaml` was deleted for scoring repos against a checklist. If a repo id,
    a per-repo verdict or a score ever appears in this payload, that decision has
    been quietly reversed — so the shape is pinned.
    """
    d = standards.read(ROOT)
    assert set(d) == {"standards", "enforced", "prose"}
    for s in d["standards"]:
        assert set(s) == {"id", "title", "what", "where", "enforcer",
                          "enforcer_where", "note", "present", "enforcer_present",
                          "items"}
        assert "repo" not in s, "a standard must not name a repo"
        assert "score" not in s and "compliant" not in s


def test_the_counts_agree_with_the_rows():
    d = standards.read(ROOT)
    assert d["enforced"] == sum(1 for s in d["standards"] if s["enforcer"])
    assert d["enforced"] + d["prose"] == len(d["standards"])


def test_every_declared_path_exists_in_this_repo():
    """The list is hand-written, so it can rot. This is what stops it.

    Cross-repo paths are exempt: a clone of shipyard alone must still answer, the
    same allowance `test_fleet_drift.py` makes for the checker it runs.
    """
    d = standards.read(ROOT)
    missing = [s["id"] for s in d["standards"]
               if s["present"] is False and not (s["where"] or "").startswith("..")]
    assert not missing, f"declared paths that no longer exist: {missing}"


def test_a_missing_file_is_reported_missing(tmp_path):
    """The negative half. Pointed at an empty root, the flags must go False — a
    `present` that cannot fail is decoration, and the drift this surface exists to
    catch is exactly a standard whose file moved."""
    d = standards.read(tmp_path)
    withpath = [s for s in d["standards"] if s["where"]]
    assert withpath, "no standard declares a path, so nothing here is testable"
    assert all(s["present"] is False for s in withpath), \
        "a standard's file was reported present against an empty directory"
    claimed = [s for s in d["standards"] if s["enforcer_where"]]
    assert claimed and all(s["enforcer_present"] is False for s in claimed), \
        "an enforcer was reported present when it does not exist"


def test_counted_standards_are_counted_from_disk():
    """Templates and ADRs report what is on disk, not a number typed here — the one
    part of the list that must never need editing when a file is added."""
    d = {s["id"]: s for s in standards.read(ROOT)["standards"]}
    assert d["templates"]["items"] == sorted(
        p.stem for p in (ROOT / "templates").glob("*.yaml"))
    assert d["decisions"]["items"] == sorted(
        p.stem for p in (ROOT / "docs" / "adr").glob("*.md"))
    assert d["templates"]["items"], "the templates directory read as empty"
