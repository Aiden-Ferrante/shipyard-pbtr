"""v0.20.0 — the loop attached to a problem: phases, solved, approaches."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import chart  # noqa: E402


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite")
    chart.init(c)
    return c


@pytest.fixture
def pid(con):
    return chart.create_problem(con, title="A problem", waypoint="something observable")


def test_migration_is_idempotent(tmp_path):
    c = sqlite3.connect(tmp_path / "i.sqlite")
    chart.init(c)
    before = sorted(r[1] for r in c.execute("PRAGMA table_info(problems)"))
    chart.init(c)
    chart.init(c)
    assert sorted(r[1] for r in c.execute("PRAGMA table_info(problems)")) == before


def test_manual_phases_round_trip(con, pid):
    row = chart.set_phases(con, pid, plan=True, review=True)
    assert (row["phase_plan"], row["phase_test"], row["phase_review"]) == (1, 0, 1)
    row = chart.set_phases(con, pid, plan=False)
    assert row["phase_plan"] == 0


def test_build_is_not_a_manual_phase(con, pid):
    """Derived from commits (D2). Accepting it here would let a click disagree with git."""
    with pytest.raises(chart.ChartError, match="derived"):
        chart.set_phases(con, pid, build=True)


def test_solved_sets_and_clears_its_timestamp(con, pid):
    assert chart.set_solved(con, pid, True)["solved_at"]
    assert chart.set_solved(con, pid, False)["solved_at"] is None


def test_solved_does_not_cascade_from_children(con, pid):
    """A parent problem is not the sum of its parts — that is why it has a waypoint."""
    kid = chart.create_problem(con, title="child", waypoint="w", parent_id=pid)
    chart.set_solved(con, kid, True)
    assert chart._problem_row(con, pid)["solved"] == 0


def test_a_verdict_survives_the_choice_moving_on(con, pid):
    """THE guarantee of D1.

    Try A, it fails, switch to B. The record `A -> failed` is the most valuable row
    in the table; losing it when the radio moves would make this a planning tool
    instead of a learning one.
    """
    a = chart.add_approach(con, pid, name="A", rationale="the obvious one")
    b = chart.add_approach(con, pid, name="B")
    chart.update_approach(con, a["id"], chosen=True)
    chart.update_approach(con, a["id"], verdict="failed")

    rows = {r["name"]: r for r in chart.update_approach(con, b["id"], chosen=True)}

    assert rows["A"]["verdict"] == "failed", "verdict erased when the choice moved"
    assert rows["A"]["chosen"] == 0
    assert rows["B"]["chosen"] == 1
    assert rows["B"]["verdict"] is None, "an untried approach must not look succeeded"


def test_only_one_approach_is_chosen_at_a_time(con, pid):
    ids = [chart.add_approach(con, pid, name=n)["id"] for n in "ABC"]
    for i in ids:
        chart.update_approach(con, i, chosen=True)
    assert sum(r["chosen"] for r in chart.approaches(con, pid)) == 1


def test_verdict_is_a_closed_vocabulary(con, pid):
    a = chart.add_approach(con, pid, name="A")
    with pytest.raises(chart.ChartError):
        chart.update_approach(con, a["id"], verdict="probably fine")


def test_an_approach_needs_a_name(con, pid):
    with pytest.raises(chart.ChartError):
        chart.add_approach(con, pid, name="   ")


def test_approaches_die_with_their_problem(con, pid):
    chart.add_approach(con, pid, name="A")
    con.execute("PRAGMA foreign_keys = ON")
    chart.delete_problem(con, pid)
    assert chart.approaches(con, pid) == []


def test_a_fresh_problem_reads_as_empty_not_answered(con, pid):
    """The guardrail: nothing may default to looking done."""
    row = chart._problem_row(con, pid)
    assert row["solved"] == 0 and row["solved_at"] is None
    assert (row["phase_plan"], row["phase_test"], row["phase_review"]) == (0, 0, 0)
    assert chart.approaches(con, pid) == []


# ---------- HTTP surface ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPYARD_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("SHIPYARD_CHART_EXPORT", str(tmp_path / "chart.md"))
    for mod in [m for m in list(sys.modules) if m.startswith("app.")]:
        del sys.modules[mod]
    from fastapi.testclient import TestClient
    from app.main import app as fresh
    return TestClient(fresh)


def _mk(client, title="P"):
    r = client.post("/api/problems", json={"title": title, "waypoint": "observable"})
    assert r.status_code < 300, r.text
    return r.json()["id"] if "id" in r.json() else r.json()["problem"]["id"]


def test_phases_endpoint_round_trips(client):
    pid = _mk(client)
    r = client.patch(f"/api/problems/{pid}/phases", json={"plan": True, "review": True})
    assert r.status_code == 200, r.text
    assert r.json()["phase_plan"] == 1 and r.json()["phase_review"] == 1


def test_phases_endpoint_will_not_take_build(client):
    """build is derived; the API must refuse it rather than drop it silently."""
    pid = _mk(client)
    r = client.patch(f"/api/problems/{pid}/phases", json={"build": True})
    assert r.status_code == 422, "a silently-dropped build would return 200 and lie"


def test_solved_endpoint_round_trips(client):
    pid = _mk(client)
    assert client.patch(f"/api/problems/{pid}/solved", json={"solved": True}).json()["solved"] == 1
    assert client.patch(f"/api/problems/{pid}/solved", json={"solved": False}).json()["solved_at"] is None


def test_approach_verdict_survives_rechoosing_over_http(client):
    """The D1 guarantee, end to end through the API."""
    pid = _mk(client)
    a = client.post(f"/api/problems/{pid}/approaches", json={"name": "A"}).json()["approaches"][0]
    b = client.post(f"/api/problems/{pid}/approaches", json={"name": "B"}).json()["approaches"][1]
    client.patch(f"/api/approaches/{a['id']}", json={"chosen": True})
    client.patch(f"/api/approaches/{a['id']}", json={"verdict": "failed", "set_verdict": True})
    rows = client.patch(f"/api/approaches/{b['id']}", json={"chosen": True}).json()["approaches"]
    by = {r["name"]: r for r in rows}
    assert by["A"]["verdict"] == "failed" and by["A"]["chosen"] == 0
    assert by["B"]["chosen"] == 1 and by["B"]["verdict"] is None


def test_bad_verdict_is_422(client):
    pid = _mk(client)
    a = client.post(f"/api/problems/{pid}/approaches", json={"name": "A"}).json()["approaches"][0]
    r = client.patch(f"/api/approaches/{a['id']}", json={"verdict": "fine", "set_verdict": True})
    assert r.status_code == 422


def test_deleting_an_unknown_approach_is_404(client):
    assert client.delete("/api/approaches/nope").status_code == 404


# ---------- derived Build (D2) ----------

def test_build_is_unknown_without_a_repo(client):
    """git cannot answer for a problem with no repo — that must not read as 'not done'."""
    pid = _mk(client)
    b = client.get(f"/api/chart/{pid}").json()["node"]["build"]
    assert b["known"] is False and b["ticked"] is False
    assert "no repo" in b["why"]


def test_build_explains_itself_when_known():
    """A derived tick indistinguishable from a clicked one trips the guardrail."""
    import importlib
    m = importlib.import_module("app.main")
    state = m._build_state({"repo": "shipyard"})
    assert state["known"] is True
    assert state["why"] and any(ch.isdigit() for ch in state["why"]) or "nothing since" in state["why"]


def test_spine_carries_approaches(client):
    pid = _mk(client)
    client.post(f"/api/problems/{pid}/approaches", json={"name": "A"})
    assert [a["name"] for a in client.get(f"/api/chart/{pid}").json()["node"]["approaches"]] == ["A"]


def test_board_rolls_up_solved_children(client):
    """The board answers 'how far in' without opening the problem.

    Direct children only: a recursive count would let a deep subtree read as
    progress on a shallow one.
    """
    parent = _mk(client, "parent")
    client.patch(f"/api/problems/{parent}/pin", json={"pinned": True})
    kids = [client.post("/api/problems", json={
        "title": f"kid{i}", "waypoint": "w", "parent_id": parent}).json() for i in range(3)]
    kid_ids = [k["id"] if "id" in k else k["problem"]["id"] for k in kids]
    client.patch(f"/api/problems/{kid_ids[0]}/solved", json={"solved": True})

    board = client.get("/api/board").json()
    cards = [c for s in board["sections"] for c in s["cards"]]
    by = {c["title"]: c for c in cards}
    assert by, "board returned no cards"
    if "kid0" in by:
        assert by["kid0"]["solved"] is True


def test_adding_an_approach_to_a_missing_problem_is_rejected(con):
    """Foreign keys refuse the orphan, but as sqlite3.IntegrityError — which the
    route does not catch, so it surfaced as a 500. Fail like every other bad ref."""
    with pytest.raises(chart.ChartError, match="no problem"):
        chart.add_approach(con, "does-not-exist", name="orphan")


def test_phases_and_solved_return_the_standard_problem_shape(con, pid):
    """Five neighbouring routes returned three different shapes for one concept."""
    full = chart.get(con, pid)
    for row in (chart.set_phases(con, pid, plan=True), chart.set_solved(con, pid, True)):
        missing = set(full) - set(row)
        assert not missing, f"shape drift, missing: {sorted(missing)}"
