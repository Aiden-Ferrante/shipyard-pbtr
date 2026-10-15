"""`GET /api/direction?repo=` — what a repo is directed to do, and what would be
refused. Built like test_gate.py: its own code root, fixture repos with a
docs/cycles/, so an opened cycle's record lands in the fixture.

The point of the endpoint is that "would be refused" is computed by the same
functions that refuse, so the last test opens a cycle the endpoint said would be
refused and asserts the refusal matches word for word.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

_ROOT = tempfile.mkdtemp()
_CYCLES = tempfile.mkdtemp()
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "direction.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def git(path, *argv):
    subprocess.run(["git", "-C", str(path), *argv], check=True, capture_output=True, text=True)


def mkrepo(name, *, dirty=0):
    path = Path(_ROOT) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "PROJECT.yaml").write_text(f"id: {name}\nname: {name}\nstage: tool\n")
    (path / "docs" / "cycles").mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "first")
    git(path, "tag", "v0.1.0")
    for i in range(dirty):
        (path / f"loose{i}.txt").write_text("y\n")
    return path


def mk(title, waypoint="observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def world():
    # Own the code root the way test_gate does: main.CODE_ROOT binds at import and
    # whichever module imported first wins, so an env var set here is too late —
    # and setting SHIPYARD_CODE_ROOT at import broke two later modules that read it.
    prev_code, prev_cycles = main.CODE_ROOT, main.CYCLES_ROOT
    main.CODE_ROOT, main.CYCLES_ROOT = Path(_ROOT), Path(_CYCLES)
    w = None
    try:
        w = _world()
        yield w
    finally:
        # Restore even when setup fails: a fixture that errored after rebinding
        # CODE_ROOT pointed every later module at an empty tmp root (2026-09-04).
        main.CODE_ROOT, main.CYCLES_ROOT = prev_code, prev_cycles
        # The suite shares one chart: a bearing left pinned changes what /api/goals
        # lists for every later module (test_goals asserts on unpinned roots).
        if w:
            client.put(f"/api/problems/{w['bearing']}/pin", json={"pinned": False})


def _world():
    # Repo names are prefixed: the suite shares one sqlite (DB_PATH binds at the
    # first import) and test_chart already claims a repo called "alpha".
    mkrepo("dir-alpha")
    mkrepo("dir-beta", dirty=2)
    mkrepo("dir-gamma")
    bearing = mk("Be somewhere by 2028")
    client.put(f"/api/problems/{bearing}/pin", json={"pinned": True})
    alpha = mk("dir-alpha's problem", parent_id=bearing, repo="dir-alpha")
    beta = mk("dir-beta's problem", parent_id=bearing, repo="dir-beta")
    # A draft is a problem whose waypoint was blanked (the outline's opt-out); the
    # create route requires one, so make it and take it away.
    gamma = mk("a category", parent_id=bearing, repo="dir-gamma")
    r = client.patch(f"/api/problems/{gamma}", json={"waypoint": ""})
    assert r.status_code == 200, r.text
    return {"bearing": bearing, "alpha": alpha, "beta": beta, "gamma": gamma}


def direction(repo):
    r = client.get("/api/direction", params={"repo": repo})
    assert r.status_code == 200, r.text
    return r.json()


def test_unknown_repo_is_a_404_naming_the_known_ids(world):
    r = client.get("/api/direction", params={"repo": "nope"})
    assert r.status_code == 404
    assert "dir-alpha" in r.json()["detail"] and "nope" in r.json()["detail"]


def test_a_charted_repo_with_no_active_problem_says_so(world):
    d = direction("dir-alpha")
    assert d["problem"]["title"] == "dir-alpha's problem" and d["problem"]["role"] == "leaf"
    assert d["bearing"]["title"] == "Be somewhere by 2028"
    assert d["active"] == {"is_active": False, "occupant": None}
    assert d["gates"]["open"]["ok"] and d["gates"]["review"]["ok"]
    assert d["would_refuse"] == []
    assert "no active problem under 'Be somewhere by 2028'" in d["next"]


def test_the_occupant_is_named_when_another_problem_holds_the_focus(world):
    client.patch(f"/api/problems/{world['beta']}/active", json={"active": True})
    d = direction("dir-alpha")
    assert d["active"]["occupant"]["title"] == "dir-beta's problem"
    assert "holds the focus" in d["next"]
    d2 = direction("dir-beta")
    assert d2["active"]["is_active"] is True


def test_owed_work_is_visible_under_gates_but_does_not_refuse_an_open(world):
    """v0.36.0: with no cycle open the next step is *open*, so owed work — which only the
    review gate cares about — must not appear in would_refuse or turn `next` away from clear."""
    d = direction("dir-beta")
    assert d["gates"]["open"]["ok"]
    assert not d["gates"]["review"]["ok"] and "owes 2 uncommitted" in d["gates"]["review"]["reason"]
    assert d["would_refuse"] == []
    assert d["next"] == "clear"


def test_with_a_cycle_open_would_refuse_names_only_the_review_gate(world):
    """The next step is review, so the review gate is the one that counts — and the open gate
    (which would now say 'open record') stays out of would_refuse."""
    pid = world["beta"]
    r = client.post(f"/api/problems/{pid}/cycles/open", json={"version": "v0.2.0", "title": "scoped"})
    assert r.status_code == 200, r.text
    d = direction("dir-beta")
    assert d["open_cycle"]["version"] == "0.2.0"
    assert not d["gates"]["open"]["ok"]                      # an open record refuses a second open
    assert d["would_refuse"] == [f"review: {d['gates']['review']['reason']}"]
    assert "cycle v0.2.0 is open" in d["next"] and "review would be refused today" in d["next"]
    client.delete(f"/api/problems/{pid}/cycles/v0.2.0")
    Path(r.json()["record"]["path"]).unlink()                # the file, not just the link, is what "planned" sees


def test_a_draft_problem_would_refuse_open_and_next_says_waypoint(world):
    d = direction("dir-gamma")
    assert not d["gates"]["open"]["ok"] and "has no waypoint" in d["gates"]["open"]["reason"]
    assert "give it an observable" in d["next"]


def test_an_open_cycle_is_reported_and_the_refusal_matches_word_for_word(world):
    client.patch(f"/api/problems/{world['beta']}/active", json={"active": False})
    r = client.post(f"/api/problems/{world['alpha']}/cycles/open",
                    json={"version": "v0.2.0", "title": "first", "repo": "dir-alpha"})
    assert r.status_code == 200, r.text
    d = direction("dir-alpha")
    assert d["open_cycle"]["version"] == "0.2.0"
    assert "cycle v0.2.0 is open on dir-alpha" in d["next"]
    assert not d["gates"]["open"]["ok"]
    # what it says would be refused IS what is refused
    r2 = client.post(f"/api/problems/{world['alpha']}/cycles/open",
                     json={"version": "v0.3.0", "title": "second", "repo": "dir-alpha"})
    assert r2.status_code == 422
    assert r2.json()["detail"] == d["gates"]["open"]["reason"]


def test_an_uncharted_repo_is_directed_to_the_chart(world):
    mkrepo("dir-delta")
    d = direction("dir-delta")
    assert d["problem"] is None
    assert "chart it" in d["next"] and d["would_refuse"]


def test_gates_open_answers_for_the_leaf_when_the_owning_problem_composes(world):
    """v0.36.1: live, every board repo's owning problem has children, so the open gate's
    composition exemption made gates.open always ok — even with a leaf's cycle in flight.
    Direction must report what a leaf would be told."""
    beta = world["beta"]
    kid = mk("dir-beta leaf", parent_id=beta)                 # beta now composes
    r = client.post(f"/api/problems/{kid}/cycles/open", json={"version": "v0.2.0", "title": "leaf work"})
    assert r.status_code == 200, r.text
    d = direction("dir-beta")
    assert d["problem"]["id"] == beta and d["problem"]["role"] == "branch"
    assert d["open_cycle"]["version"] == "0.2.0"
    assert not d["gates"]["open"]["ok"] and "already has a cycle open (v0.2.0)" in d["gates"]["open"]["reason"]
    # the gate itself still exempts the composing problem — that is the umbrella rule, unchanged
    r2 = client.post(f"/api/problems/{beta}/cycles/open", json={"version": "v0.3.0", "title": "umbrella"})
    assert r2.status_code == 200, r2.text
    for pid_, v, rr in ((beta, "v0.3.0", r2), (kid, "v0.2.0", r)):
        client.delete(f"/api/problems/{pid_}/cycles/{v}")
        Path(rr.json()["record"]["path"]).unlink()

