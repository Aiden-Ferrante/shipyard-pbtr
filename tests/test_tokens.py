"""Impact tokens: a destructive write proves it read its impact. Planted first —
a bare DELETE is refused with the read named — then the sanctioned flow, then
every way a token can be wrong (foreign, stale, reused)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "tokens.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app import tokens  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def mk(title, **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": "obs", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_a_bare_delete_is_refused_and_names_the_read():
    p = mk("tok-bare")
    r = client.delete(f"/api/problems/{p}")
    assert r.status_code == 422
    assert f"GET /api/problems/{p}/deletion" in r.json()["detail"]
    assert client.get(f"/api/chart/{p}").status_code == 200        # still there


def test_the_read_issues_a_token_the_delete_accepts_once():
    p = mk("tok-ok")
    imp = client.get(f"/api/problems/{p}/deletion").json()
    assert imp["token"]
    assert client.delete(f"/api/problems/{p}", params={"token": imp["token"]}).status_code == 200
    # reuse on another problem: the token is spent
    q = mk("tok-reuse")
    r = client.delete(f"/api/problems/{q}", params={"token": imp["token"]})
    assert r.status_code == 422 and "unknown or expired" in r.json()["detail"]


def test_a_token_for_another_problem_is_refused_by_name():
    a, b = mk("tok-a"), mk("tok-b")
    ta = client.get(f"/api/problems/{a}/deletion").json()["token"]
    r = client.delete(f"/api/problems/{b}", params={"token": ta})
    assert r.status_code == 422 and "different" in r.json()["detail"]


def test_a_changed_impact_invalidates_the_token():
    parent = mk("tok-parent")
    tok = client.get(f"/api/problems/{parent}/deletion").json()["token"]
    mk("tok-child", parent_id=parent)             # the world moved: deleting now promotes a child
    r = client.delete(f"/api/problems/{parent}", params={"token": tok})
    assert r.status_code == 422 and "has changed" in r.json()["detail"]
    fresh = client.get(f"/api/problems/{parent}/deletion").json()["token"]
    assert client.delete(f"/api/problems/{parent}", params={"token": fresh}).status_code == 200


def test_thaw_needs_the_impact_token():
    p = mk("tok-anchor")
    client.post(f"/api/problems/{p}/anchor", json={"basis": "decided"})
    r = client.delete(f"/api/problems/{p}/anchor")
    assert r.status_code == 422 and f"GET /api/problems/{p}/impact" in r.json()["detail"]
    assert client.get(f"/api/chart/{p}").json()["node"]["anchored"] is True
    tok = client.get(f"/api/problems/{p}/impact").json()["token"]
    assert client.delete(f"/api/problems/{p}/anchor", params={"token": tok}).status_code == 200
    assert client.get(f"/api/chart/{p}").json()["node"]["anchored"] is False


def test_an_expired_token_is_refused(monkeypatch):
    p = mk("tok-expired")
    tok = client.get(f"/api/problems/{p}/deletion").json()["token"]
    monkeypatch.setattr(tokens, "TTL", 0.0)
    k, t, d, _ = tokens._ISSUED[tok]
    tokens._ISSUED[tok] = (k, t, d, 0.0)
    r = client.delete(f"/api/problems/{p}", params={"token": tok})
    assert r.status_code == 422 and "expired" in r.json()["detail"]
