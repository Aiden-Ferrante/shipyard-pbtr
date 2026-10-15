"""The session ledger: a session is a row, what it did is an append-only event
log, and chart writes made under an X-Actor session record themselves.

Own DB, like every module here; the client sends X-Actor on the calls that
should land in the ledger and nothing on the ones that should not."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "ledger.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
AGENT = {"X-Actor": "claude-code:sess-ledger-1"}


def test_start_is_an_upsert_and_end_records_the_reason():
    r = client.post("/api/sessions", json={"id": "s1", "cwd": "/x/helm", "repo": "helm"})
    assert r.status_code == 200 and r.json()["repo"] == "helm" and r.json()["ended_at"] is None
    r = client.post("/api/sessions", json={"id": "s1"})          # resume: same row
    assert r.json()["repo"] == "helm"
    r = client.patch("/api/sessions/s1", json={"reason": "prompt_input_exit"})
    assert r.json()["ended_at"] and r.json()["end_reason"] == "prompt_input_exit"


def test_a_git_event_lands_on_its_session_even_before_start():
    r = client.post("/api/sessions/s2/events", json={"kind": "commit", "ref": "abc1234", "detail": "feat: x", "repo": "helm"})
    assert r.status_code == 200
    s = client.get("/api/sessions/s2").json()
    assert s["repo"] == "helm" and [e["kind"] for e in s["events"]] == ["commit"]


def test_an_unknown_event_kind_is_refused_by_name():
    r = client.post("/api/sessions/s2/events", json={"kind": "dance"})
    assert r.status_code == 422 and "dance" in r.json()["detail"]


def test_chart_writes_under_a_session_record_themselves_and_stamp_updated_by():
    p = client.post("/api/problems", json={"title": "ledgered", "waypoint": "obs"}, headers=AGENT).json()["id"]
    client.post(f"/api/problems/{p}/anchor", json={"basis": "decided"}, headers=AGENT)
    client.patch(f"/api/problems/{p}/phases", json={"plan": True}, headers=AGENT)
    s = client.get("/api/sessions/sess-ledger-1").json()
    kinds = [e["kind"] for e in s["events"]]
    assert kinds == ["problem", "anchor", "phase"], kinds
    assert s["events"][1]["ref"] == p and s["events"][1]["detail"] == "decided"
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["updated_by"] == "claude-code:sess-ledger-1"


def test_a_human_write_stamps_the_actor_but_creates_no_session():
    before = len(client.get("/api/sessions").json()["sessions"])
    p = client.post("/api/problems", json={"title": "by hand", "waypoint": "obs"}).json()["id"]
    after = len(client.get("/api/sessions").json()["sessions"])
    assert after == before
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["updated_by"] in ("unknown", "human:ui")


def test_listing_filters_by_repo_and_is_newest_first():
    client.post("/api/sessions", json={"id": "s3", "repo": "shipyard"})
    out = client.get("/api/sessions", params={"repo": "helm"}).json()["sessions"]
    assert {s["id"] for s in out} == {"s1", "s2"}
    allof = client.get("/api/sessions").json()["sessions"]
    assert allof[0]["started_at"] >= allof[-1]["started_at"]
    assert client.get("/api/sessions/nope").status_code == 404
