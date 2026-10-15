"""The gate (D4): ticking `review` against a repo that owes uncommitted or
unpushed work is refused at the API boundary with a 422 that names the debt.

Guardrail 3 — a gate that has never refused anything has not shipped. So the
core of this file is the planted violation: build a repo that owes, walk the
real flow (chart it, open a cycle, tick review), and assert the refusal fires
and says why. Rule drift and compliance look identical from outside.

This file owns its own CODE_ROOT and CYCLES_ROOT, and its fixture repos carry
a docs/cycles/ so an opened cycle's record lands inside the fixture, never in
the real vault.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

_ROOT = tempfile.mkdtemp()
_REMOTES = tempfile.mkdtemp()
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "gate.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def git(path, *argv):
    subprocess.run(["git", "-C", str(path), *argv], check=True,
                   capture_output=True, text=True)


def mkrepo(name, *, dirty=0, tag="v1.0.0", remote=True, unpushed=0, after_tag=0):
    """A repo whose debts are exact by construction: `dirty` uncommitted files,
    `unpushed` commits past the upstream, `after_tag` clean pushed commits past
    the tag (owed, but not a kind the gate refuses on)."""
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
    for i in range(unpushed):
        (path / f"local{i}.txt").write_text("z\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", f"chore: not pushed {i}")
    for i in range(dirty):
        (path / f"loose{i}.txt").write_text("y\n")
    # Untracked-and-empty is invisible to `git status`, so this costs no dirt;
    # it is where an opened cycle's record scaffold will land.
    (path / "docs" / "cycles").mkdir(parents=True, exist_ok=True)
    return path


def mk(title, waypoint="something observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def tick(pid, **phases):
    return client.patch(f"/api/problems/{pid}/phases", json=phases)


def phase_review(pid):
    return client.get(f"/api/chart/{pid}").json()["node"].get("phase_review")


@pytest.fixture(scope="module", autouse=True)
def roots():
    """Patch module attributes, never env vars (config binds at import).
    CYCLES_ROOT too: the open-cycle route falls back to the vault when a repo
    has no docs/cycles/, and a test must have no path to the real one."""
    prev_code, prev_cycles = main.CODE_ROOT, main.CYCLES_ROOT
    main.CODE_ROOT = Path(_ROOT)
    main.CYCLES_ROOT = Path(tempfile.mkdtemp())
    yield
    main.CODE_ROOT, main.CYCLES_ROOT = prev_code, prev_cycles


def test_planted_violation_review_is_refused_and_the_debt_is_named():
    """The whole flow, with the violation planted first: two files nobody
    committed, a cycle opened against the problem (whose record scaffold makes
    a third), then the tick the gate exists to stop."""
    mkrepo("gate-dirty", dirty=2)
    pid = mk("Gate dirty problem", repo="gate-dirty")
    r = client.post(f"/api/problems/{pid}/cycles/open",
                    json={"version": "v0.1.1", "title": "planted"})
    assert r.status_code == 200, r.text

    r = tick(pid, review=True)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "review refused: gate-dirty owes 3 uncommitted"
    assert not phase_review(pid), "a refused tick must not land"


def test_unpushed_work_refuses_review_too():
    mkrepo("gate-unpushed", unpushed=2)
    pid = mk("Gate unpushed problem", repo="gate-unpushed")
    r = tick(pid, review=True)
    assert r.status_code == 422
    assert r.json()["detail"] == "review refused: gate-unpushed owes 2 unpushed"


def test_both_debts_are_named_together():
    mkrepo("gate-both", dirty=1, unpushed=1)
    pid = mk("Gate both problem", repo="gate-both")
    r = tick(pid, review=True)
    assert r.status_code == 422
    assert r.json()["detail"] == "review refused: gate-both owes 1 uncommitted, 1 unpushed"


def test_a_clean_repo_ticks_review_fine():
    """The positive case: open a cycle, commit the record it scaffolds, push —
    owing nothing, the same tick passes and the phase lands."""
    path = mkrepo("gate-clean")
    pid = mk("Gate clean problem", repo="gate-clean")
    r = client.post(f"/api/problems/{pid}/cycles/open",
                    json={"version": "v0.1.1", "title": "clean run"})
    assert r.status_code == 200, r.text
    git(path, "add", "-A")
    git(path, "commit", "-qm", "chore: cycle record")
    git(path, "push", "-q")

    r = tick(pid, review=True)
    assert r.status_code == 200, r.text
    assert r.json()["phase_review"], "the tick landed"
    assert phase_review(pid)


def test_unticking_review_is_not_gated():
    """Backing a mark out is not passing the gate — an owing repo may always
    untick."""
    pid = client.get("/api/chart/gate-dirty").json()["node"]["id"]
    r = tick(pid, review=False)
    assert r.status_code == 200, r.text


def test_plan_and_test_ticks_pass_an_owing_repo():
    """Only `review` is gated — the plan's wording, exactly. Plan and test are
    marks about thinking, and thinking is allowed to happen on a dirty tree."""
    pid = client.get("/api/chart/gate-dirty").json()["node"]["id"]
    r = tick(pid, plan=True, test=True)
    assert r.status_code == 200, r.text


def test_only_lost_work_gates_not_every_debt():
    """no-remote and untagged are yard-visible debts, not line-stopping ones:
    a repo can be reviewed without an upstream, and past its tag — the plan
    names uncommitted and unpushed, and the gate must not grow teeth the plan
    never gave it."""
    mkrepo("gate-isolated", remote=False, after_tag=0)
    pid = mk("Gate isolated problem", repo="gate-isolated")
    r = tick(pid, review=True)
    assert r.status_code == 200, r.text

    mkrepo("gate-untagged", after_tag=2)
    pid = mk("Gate untagged problem", repo="gate-untagged")
    r = tick(pid, review=True)
    assert r.status_code == 200, r.text


def test_a_problem_with_no_repo_beneath_ticks_fine():
    """Nothing to measure is not a debt: pure reasoning has no working tree."""
    pid = mk("Gate pure reasoning")
    r = tick(pid, review=True)
    assert r.status_code == 200, r.text


# ---------- the other gate (v0.29.1): opening, not closing ----------
#
# `_review_gate` refuses the debts that mean work would be LOST. `_open_gate`
# refuses the conditions that mean work has no DIRECTION. Same boundary, same
# reason, opposite end of the cycle — so the planted-violation discipline above
# applies here too: each test builds the condition and asserts the refusal.


def test_a_draft_problem_cannot_open_a_cycle():
    """The reachable route to a waypointless cycle, which is not the obvious one.

    A draft cannot *carry* a repo — `link_repo` already refuses that. It can
    **inherit** one: a waypointless parent whose child carries a repo is offered
    that repo by `nearest_repos`, and without this gate could open a cycle
    against an observable it does not have.
    """
    mkrepo("gate-draft-kid")
    r = client.post("/api/problems", json={"title": "Undirected parent",
                                           "waypoint": "", "draft": True})
    assert r.status_code == 200, r.text
    parent = r.json()["id"]
    mk("Directed child", repo="gate-draft-kid", parent_id=parent)

    r = client.post(f"/api/problems/{parent}/cycles/open",
                    json={"version": "v1.1.0", "title": "should not open"})
    assert r.status_code == 422, r.text
    assert "has no waypoint" in r.json()["detail"]
    assert not list((Path(_ROOT) / "gate-draft-kid" / "docs" / "cycles").iterdir()), \
        "a refused open must not have scaffolded a record"


def test_a_second_cycle_is_refused_while_one_is_open():
    mkrepo("gate-oneopen")
    pid = mk("One open at a time", repo="gate-oneopen")
    first = client.post(f"/api/problems/{pid}/cycles/open",
                        json={"version": "v1.0.1", "title": "the open one"})
    assert first.status_code == 200, first.text

    second = client.post(f"/api/problems/{pid}/cycles/open",
                         json={"version": "v1.0.2", "title": "the one too many"})
    assert second.status_code == 422, second.text
    detail = second.json()["detail"]
    assert "already has a cycle open" in detail and "v1.0.1" in detail


def test_cutting_the_version_closes_the_cycle_and_the_next_one_opens():
    """The gate is a queue, not a lock: closing is cutting the tag, and the
    state is read off disk rather than typed into."""
    path = mkrepo("gate-reopen")
    pid = mk("Reopenable", repo="gate-reopen")
    assert client.post(f"/api/problems/{pid}/cycles/open",
                       json={"version": "v1.0.1", "title": "first"}).status_code == 200
    assert client.post(f"/api/problems/{pid}/cycles/open",
                       json={"version": "v1.0.2", "title": "second"}).status_code == 422

    git(path, "add", "-A")
    git(path, "commit", "-qm", "docs: the cycle record")
    git(path, "tag", "v1.0.1")

    r = client.post(f"/api/problems/{pid}/cycles/open",
                    json={"version": "v1.0.2", "title": "second, properly"})
    assert r.status_code == 200, r.text


def test_a_branch_cycle_does_not_block_the_leaves_beneath_it():
    """A super- or sub-cycle is *meant* to stay open while its children run.
    Counting it would deadlock every leaf under it — the composition read
    backwards — so only a cycle that composes nothing contends for the slot.

    The repo hangs off the leaf and the branch inherits it through
    `nearest_repos`, which is the real shape: one repo, one problem.
    """
    mkrepo("gate-branch")
    branch = mk("A branch that stays open")
    leaf = mk("A leaf beneath it", repo="gate-branch", parent_id=branch)

    assert client.post(f"/api/problems/{branch}/cycles/open",
                       json={"version": "v1.1.0", "title": "the branch"}).status_code == 200
    r = client.post(f"/api/problems/{leaf}/cycles/open",
                    json={"version": "v1.0.1", "title": "a leaf under it"})
    assert r.status_code == 200, r.text


def test_every_offered_repo_is_charted():
    """The third refusal the v0.29.1 plan asked for, as the invariant it really is.

    A repo the chart does not claim cannot reach `_open_gate`: the candidates
    come from `nearest_repos`, which derives them from chart nodes, and
    `body.repo` must be one of them. A branch refusing that condition would be
    dead code, so the guarantee is asserted where it is actually made.
    """
    mkrepo("gate-charted")
    mkrepo("gate-uncharted")          # on disk, deliberately claimed by nobody
    pid = mk("Charted problem", repo="gate-charted")

    con = main.db()
    try:
        offered = main.chart.nearest_repos(con, pid)
        assert offered == ["gate-charted"]
        assert all(main.chart.resolve(con, r) for r in offered), \
            "nearest_repos may only offer repos a chart node claims"
    finally:
        con.close()

    r = client.post(f"/api/problems/{pid}/cycles/open",
                    json={"version": "v1.0.1", "title": "x", "repo": "gate-uncharted"})
    assert r.status_code == 422
    assert "is not beneath this problem" in r.json()["detail"]


def test_a_sub_problem_opens_its_own_light_cycle():
    """v0.31.1, end to end: the refusal this fix removes, and the weight it lets
    the tree decide.

    Before upward inheritance this returned 422 — "no repo beneath this problem" —
    and the workaround was to open the cycle against the project node instead,
    which made a light cycle's work cut a MINOR because only a branch could hold
    it. The chart's shape was choosing the version number.
    """
    mkrepo("gate-inherit", tag="v2.0.0")
    project = mk("Inheriting project", repo="gate-inherit")
    leaf = mk("A sub-problem of it", parent_id=project)

    opts = client.get(f"/api/problems/{leaf}/cycle-options").json()
    assert opts["role"] == "leaf"
    assert opts["bump"] == "patch", "a leaf cuts a PATCH — the tree decides, not the author"
    assert opts["proposed"] == "v2.0.1"

    r = client.post(f"/api/problems/{leaf}/cycles/open",
                    json={"version": "v2.0.1", "title": "its own cycle"})
    assert r.status_code == 200, r.text
    assert r.json()["repo"] == "gate-inherit"
    assert "Light cycle" in Path(r.json()["record"]["path"]).read_text()


def test_the_open_gate_still_counts_the_repo_not_the_problem():
    """Inheritance means several problems now resolve to one repo, which is exactly
    the collision the backlog entry worried about. The one-open-cycle rule is what
    makes it safe: a sibling cannot open a second cycle in the shared line."""
    mkrepo("gate-shared", tag="v3.0.0")
    project = mk("Shared line project", repo="gate-shared")
    one = mk("first sub-problem", parent_id=project)
    two = mk("second sub-problem", parent_id=project)

    assert client.post(f"/api/problems/{one}/cycles/open",
                       json={"version": "v3.0.1", "title": "first"}).status_code == 200
    r = client.post(f"/api/problems/{two}/cycles/open",
                    json={"version": "v3.0.2", "title": "second"})
    assert r.status_code == 422, r.text
    assert "already has a cycle open" in r.json()["detail"]
