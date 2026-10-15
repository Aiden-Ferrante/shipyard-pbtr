"""Smoke tests: the seam works — health, project scan, groups, chart."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "test.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_convention():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"ok", "checks", "freshness"}
    assert body["checks"]["db"] is True


def test_health_no_longer_checks_standards():
    """standards.yaml was deleted in v0.5.0 — health must not still look for it."""
    assert "standards" not in client.get("/health").json()["checks"]


def test_projects_include_shipyard():
    r = client.get("/api/projects")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    assert "shipyard" in ids


def test_project_view_has_no_checklist():
    """The checklist is gone; a card carries chart + work + activity instead."""
    p = next(p for p in client.get("/api/projects").json()["projects"]
             if p["id"] == "shipyard")
    assert "checklist" not in p and "progress" not in p
    assert set(p) >= {"charted", "sounding", "open_tasks", "last_activity"}


def test_checklist_routes_are_gone():
    assert client.get("/api/standards").status_code == 404
    assert client.post("/api/projects/shipyard/checks/git-init",
                       json={"done": True}).status_code == 404


def test_unknown_project_is_404():
    assert client.get("/api/projects/not-a-real-project").status_code == 404
