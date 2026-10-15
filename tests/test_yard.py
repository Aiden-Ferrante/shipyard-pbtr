"""The yard — everything not on the line, grouped by what blocks entry (D5).

One repo, exactly one bay, under the strongest reason it cannot start:
shelved > owes > uncharted > no-waypoint > clear. Grouped, never ranked
(guardrail 2), and an empty bay is omitted rather than rendered as scaffolding.

This file owns its own CODE_ROOT, like test_owed: assertions about *which* bay
holds *which* repo are hostage to the real fleet otherwise.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

_ROOT = tempfile.mkdtemp()
_REMOTES = tempfile.mkdtemp()   # bare upstreams live OUTSIDE the scanned root
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "yard.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

STRIP_KEYS = {"id", "name", "cycles", "lamp", "blockers", "why", "goal",
              "runtime", "version", "last_activity", "manned", "standing"}
BAY_KEYS = {"key", "title", "why", "strips"}


def git(path, *argv):
    subprocess.run(["git", "-C", str(path), *argv], check=True,
                   capture_output=True, text=True)


def mkrepo(name, *, dirty=0, tag="v1.0.0", remote=True, after_tag=0):
    """A fixture repo whose owed state is exact by construction.

    Commit subjects are deliberately non-notable (`chore:`) so the changelog
    drift check never fires — each fixture owes precisely what its arguments
    say, and nothing the test did not ask for.
    """
    path = Path(_ROOT) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "PROJECT.yaml").write_text(
        f"id: {name}\nname: {name.title()}\nstage: tool\n")
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "first")
    if tag:
        git(path, "tag", tag)
    for i in range(after_tag):
        (path / f"past{i}.txt").write_text("x\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", f"chore: past the tag {i}")
    if remote:
        bare = Path(_REMOTES) / f"{name}.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True,
                       capture_output=True, text=True)
        git(path, "remote", "add", "origin", str(bare))
        git(path, "push", "-qu", "origin", "main")
    for i in range(dirty):
        (path / f"loose{i}.txt").write_text("y\n")
    return path


def mk(title, waypoint="something observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module", autouse=True)
def fleet():
    """Patch the module attribute, not the environment (see test_owed for why).

    Six repos, one per readable state — including the compound ones, because the
    compounds are where precedence either holds or does not:

      yard-clear      clean, pushed, tagged, charted w/ waypoint  → clear
      yard-owes       dirty, charted                              → owes (danger)
      yard-messy      dirty AND uncharted                         → owes, not uncharted
      yard-untagged   commits past its tag, uncharted             → owes (warn, no red kind)
      yard-uncharted  clean, no chart node                        → uncharted
      yard-shelved    dirty AND uncharted AND shelved             → shelved, debts kept
    """
    previous = main.CODE_ROOT
    main.CODE_ROOT = Path(_ROOT)
    mkrepo("yard-clear")
    mkrepo("yard-owes", dirty=3)
    mkrepo("yard-messy", dirty=1)
    mkrepo("yard-untagged", after_tag=1)
    mkrepo("yard-uncharted")
    mkrepo("yard-shelved", dirty=2)
    mk("Attack yard-clear", repo="yard-clear")
    mk("Attack yard-owes", repo="yard-owes")
    r = client.post("/api/shelved", json={"repo": "yard-shelved", "note": "resting"})
    assert r.status_code == 200, r.text
    yield
    main.CODE_ROOT = previous


def yard():
    r = client.get("/api/yard")
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {b["key"]: b for b in body["bays"]}


def strips_of(bay):
    return [s["id"] for s in bay["strips"]]


def test_shape_is_exactly_the_contract():
    """The frontend was built against this shape first; the backend conforms.

    Asserting the exact set rather than a subset keeps this test able to catch a
    key nobody meant to ship — which is the only reason it exists.

    `queue` joined them in v0.29.2. The ledger keys left again in v0.29.3 with the
    bands that read them: bays say what blocks entry, the queue says what is not
    yet startable, and nothing here measures the operator any more.
    """
    body, by = yard()
    assert set(body) == {"bays", "scanned", "queue"}
    assert body["scanned"] == 6
    for bay in body["bays"]:
        assert set(bay) == BAY_KEYS
        assert bay["title"] and bay["why"], "a bay names itself and its reason"
        for s in bay["strips"]:
            assert set(s) == STRIP_KEYS, s["id"]
            assert isinstance(s["manned"], bool)
            assert s["lamp"] in ("ok", "warn", "danger", "off")
            for b in s["blockers"]:
                assert set(b) == {"kind", "n", "detail"}
            # No fixture is registered with Mission Control, and a repo that is
            # not something you start reads null — never "stopped".
            assert s["runtime"] is None


def test_one_repo_exactly_one_bay():
    body, by = yard()
    ids = [s for b in body["bays"] for s in strips_of(b)]
    assert len(ids) == len(set(ids)) == body["scanned"], \
        "every scanned repo appears, and none twice — no score, no rank, no double listing"


def test_bays_hold_the_reason_a_repo_cannot_start():
    _, by = yard()
    assert strips_of(by["clear"]) == ["yard-clear"]
    assert strips_of(by["owes"]) == ["yard-messy", "yard-owes", "yard-untagged"]
    assert strips_of(by["uncharted"]) == ["yard-uncharted"]
    assert strips_of(by["shelved"]) == ["yard-shelved"]


def test_precedence_owes_beats_uncharted_and_shelved_beats_both():
    """yard-messy is dirty AND uncharted — the debt is the stronger reason.
    yard-shelved is dirty AND uncharted AND shelved — the hide wins over both."""
    _, by = yard()
    assert "yard-messy" in strips_of(by["owes"])
    assert "yard-messy" not in strips_of(by["uncharted"])
    assert strips_of(by["shelved"]) == ["yard-shelved"]
    assert "yard-shelved" not in strips_of(by["owes"])


def test_empty_bays_are_omitted():
    """Nothing renders empty scaffolding: no repo is charted-without-waypoint yet,
    so the no-waypoint bay does not arrive at all."""
    body, by = yard()
    assert set(by) == {"clear", "owes", "uncharted", "shelved"}
    assert [b["key"] for b in body["bays"]] == ["clear", "owes", "uncharted", "shelved"], \
        "display order is the mockup's console order, clear first"


def test_within_a_bay_the_order_is_the_roster_not_a_rank():
    """id order — the same stable order every other roster read uses. Sorting by
    last_activity descending would be a rank, and the page never ranks repos."""
    _, by = yard()
    owes = strips_of(by["owes"])
    assert owes == sorted(owes)


def test_lamps_follow_the_colour_doctrine():
    _, by = yard()
    lamp = {s["id"]: s["lamp"] for b in by.values() for s in b["strips"]}
    assert lamp["yard-clear"] == "ok"
    assert lamp["yard-owes"] == "danger", "uncommitted work is would-be-lost — red"
    assert lamp["yard-untagged"] == "warn", "untagged is owed, not lost — amber"
    assert lamp["yard-uncharted"] == "warn"
    assert lamp["yard-shelved"] == "off", "zinc means inert, and shelved is the inert state"


def test_blockers_are_owed_items_verbatim():
    _, by = yard()
    owes = {s["id"]: s for s in by["owes"]["strips"]}
    assert owes["yard-owes"]["blockers"] == [
        {"kind": "uncommitted", "n": 3, "detail": "3 files"}]
    clear = by["clear"]["strips"][0]
    assert clear["blockers"] == []


def test_shelved_strips_keep_their_real_debts():
    """The bay says deliberately-out-of-service; the blockers still say what is
    owed — otherwise the inspector overstates how clean the shelf is."""
    _, by = yard()
    shelved = by["shelved"]["strips"][0]
    kinds = {b["kind"]: b for b in shelved["blockers"]}
    assert kinds["uncommitted"]["n"] == 2
    assert "uncharted" in kinds


def test_why_goal_and_manned_read_from_the_chart():
    _, by = yard()
    clear = by["clear"]["strips"][0]
    assert clear["why"] == "Attack yard-clear"
    assert clear["goal"] is None and clear["manned"] is False

    pid = client.get("/api/chart/yard-clear").json()["node"]["id"]
    bearing = mk("Yard bearing")
    assert client.put(f"/api/problems/{bearing}/pin",
                      json={"pinned": True}).status_code == 200
    assert client.post(f"/api/problems/{pid}/parents",
                       json={"parent_id": bearing}).status_code == 200
    assert client.patch(f"/api/problems/{pid}/active",
                        json={"active": True}).status_code == 200
    try:
        _, by = yard()
        clear = by["clear"]["strips"][0]
        assert clear["goal"] == "Yard bearing", "the nearest pinned goal, as the board groups"
        assert clear["manned"] is True, "holds a focus slot"
    finally:
        client.patch(f"/api/problems/{pid}/active", json={"active": False})
        client.put(f"/api/problems/{bearing}/pin", json={"pinned": False})


def test_a_blanked_waypoint_lands_in_the_no_waypoint_bay():
    """Charted-without-waypoint IS representable: creation requires a waypoint,
    but an edit may blank one (a draft is allowed to stay a draft), and a linked
    repo keeps its link. The bay exists for exactly that state."""
    mkrepo("yard-drafted")
    pid = mk("Attack yard-drafted", repo="yard-drafted")
    r = client.patch(f"/api/problems/{pid}", json={"waypoint": ""})
    assert r.status_code == 200, r.text

    body, by = yard()
    assert body["scanned"] == 7
    assert strips_of(by["no-waypoint"]) == ["yard-drafted"]
    strip = by["no-waypoint"]["strips"][0]
    assert strip["lamp"] == "warn"
    assert strip["blockers"] == [], "charted and owing nothing — the waypoint is the blocker"
    assert strip["why"] == "Attack yard-drafted"


# ---------- runtime folding ----------
#
# The strip's runtime mirrors the old Fleet's client-side `runtimeState`, moved
# server-side: null when MC never knew it, stopped/unhealthy/running otherwise.

def test_runtime_none_when_mission_control_never_knew_it():
    assert main._runtime_of([]) is None


def test_runtime_running_and_the_oldest_uptime_wins():
    rt = main._runtime_of([
        {"status": "running", "ports": [8001], "uptime_s": 60},
        {"status": "stopped", "ports": [8002, 8001], "uptime_s": 9000},
    ])
    assert rt == {"state": "running", "ports": [8001, 8002], "uptime_s": 9000}


def test_runtime_unhealthy_when_up_but_failing_health():
    rt = main._runtime_of([{"status": "running", "health": False, "ports": []}])
    assert rt["state"] == "unhealthy"


def test_runtime_stopped_when_nothing_is_up():
    rt = main._runtime_of([{"status": "exited", "ports": [80]}])
    assert rt == {"state": "stopped", "ports": [80], "uptime_s": None}


def test_runtime_health_alone_counts_as_up():
    rt = main._runtime_of([{"health": True}])
    assert rt["state"] == "running"


# ---------- the queue (v0.29.2) ----------


def _queue_titles():
    return [q["title"] for q in client.get("/api/yard").json()["queue"]]


def test_a_draft_waits_in_the_queue_and_leaves_by_gaining_a_waypoint():
    """Both transitions, not just the first. A queue that fills and never
    visibly drains is the failure this leaf is falsified by."""
    r = client.post("/api/problems", json={"title": "Queued thought",
                                           "waypoint": "", "draft": True})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert "Queued thought" in _queue_titles()

    r = client.patch(f"/api/problems/{pid}",
                     json={"waypoint": "something I could actually observe"})
    assert r.status_code == 200, r.text
    assert "Queued thought" not in _queue_titles(), \
        "writing the waypoint is the only exit, and it must actually be one"


def test_a_grouping_is_not_in_the_queue():
    """A problem with others beneath it has no observable of its own and never
    will. Before this filter the real chart's queue opened with five bearings —
    `<root goal>` and its `<domain>` groupings — half the rows being
    things that can never be started, on the band that asks what to start."""
    r = client.post("/api/problems", json={"title": "A grouping, not a task",
                                           "waypoint": "", "draft": True})
    parent = r.json()["id"]
    client.post("/api/problems", json={"title": "Real work beneath it",
                                       "waypoint": "observable", "parent_id": parent})

    titles = _queue_titles()
    assert "A grouping, not a task" not in titles
    assert "Real work beneath it" not in titles, "a waypointed problem is not queued"


def test_the_queue_never_lists_a_problem_twice():
    """`outline` emits a shared node once expandable and once as an inert
    reference; a queue that listed both would ask you to finish it twice."""
    titles = _queue_titles()
    assert len(titles) == len(set(titles))
