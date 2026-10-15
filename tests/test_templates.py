"""Templates: a starting shape, never a standard.

The tests that matter most are the ones pinning what a template is *not* — it is
never checked, it carries no facts about your chart, and a stamped copy forgets it.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "tpl.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())
_tdir = tempfile.mkdtemp()
os.environ["SHIPYARD_TEMPLATES_DIR"] = _tdir

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app import templates as T  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(scope="module", autouse=True)
def templates_dir():
    """Patch the attribute and put it back (test_owed.fleet's shape). The old
    import-time rebind leaked this module's tempdir into every module collected
    after it — order-dependent state the suite only survived by accident."""
    previous = main.TEMPLATES_DIR
    main.TEMPLATES_DIR = Path(_tdir)
    yield
    main.TEMPLATES_DIR = previous

SHAPE = [
    {"title": "It does the thing", "waypoint": "core path works", "children": [
        {"title": "The hard part works", "waypoint": "the tricky case passes", "children": []},
    ]},
    {"title": "Someone else can run it", "waypoint": "README gets a stranger up", "children": []},
]


def mk(title, waypoint="observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_save_and_load_round_trip():
    r = client.post("/api/templates", json={"name": "Web service", "problems": SHAPE})
    assert r.status_code == 200
    t = client.get("/api/templates/web-service").json()
    assert t["name"] == "Web service"
    assert t["problems"][0]["children"][0]["title"] == "The hard part works"


def test_listing_counts_nested_problems():
    client.post("/api/templates", json={"name": "Counted", "problems": SHAPE})
    row = next(x for x in client.get("/api/templates").json()["templates"]
               if x["slug"] == "counted")
    assert row["count"] == 3


def test_a_template_carries_no_facts_about_your_chart():
    """Soundings, repos and anchors describe *your* chart, not the shape being reused."""
    dirty = [{"title": "Has baggage", "waypoint": "w", "sounding": "observed",
              "repo": "shipyard", "anchored_at": "2026-01-01", "children": []}]
    client.post("/api/templates", json={"name": "Clean", "problems": dirty})
    node = client.get("/api/templates/clean").json()["problems"][0]
    assert set(node) == {"title", "waypoint", "children"}


def test_empty_template_is_refused():
    assert client.post("/api/templates",
                       json={"name": "Nothing", "problems": []}).status_code == 422


def test_save_from_an_existing_subtree():
    """You author templates by building one good chart, not in a separate editor."""
    root = mk("Real project")
    kid = mk("Real child", parent_id=root)
    mk("Real grandchild", parent_id=kid)

    r = client.post("/api/templates", json={"name": "Lifted", "from_problem": root})
    assert r.status_code == 200
    t = client.get("/api/templates/lifted").json()
    assert [n["title"] for n in t["problems"]] == ["Real child"]
    assert t["problems"][0]["children"][0]["title"] == "Real grandchild"


def test_applying_stamps_the_shape_with_its_waypoints():
    """The waypoints are the payload — a copy without them is a list of categories."""
    client.post("/api/templates", json={"name": "Stamper", "problems": SHAPE})
    target = mk("Fresh project")

    r = client.post(f"/api/problems/{target}/template", json={"slug": "stamper"})
    assert r.status_code == 200
    assert r.json()["created"] == 3

    kids = client.get(f"/api/chart/{target}").json()["children"]
    assert sorted(k["title"] for k in kids) == ["It does the thing", "Someone else can run it"]
    hard = next(k for k in kids if k["title"] == "It does the thing")
    assert hard["waypoint"] == "core path works"
    assert hard["draft"] is False, "a stamped problem is falsifiable straight away"


def test_a_stamped_copy_forgets_its_template():
    """Never linked. Shipyard must never be able to say a project drifted."""
    client.post("/api/templates", json={"name": "Forgotten", "problems": SHAPE})
    target = mk("Forgets")
    client.post(f"/api/problems/{target}/template", json={"slug": "forgotten"})

    kid = client.get(f"/api/chart/{target}").json()["children"][0]
    node = client.get(f"/api/chart/{kid['id']}").json()["node"]
    assert "template" not in node and "template_slug" not in node


def test_deleting_a_template_leaves_stamped_copies_alone():
    client.post("/api/templates", json={"name": "Doomed", "problems": SHAPE})
    target = mk("Keeps its children")
    client.post(f"/api/problems/{target}/template", json={"slug": "doomed"})

    assert client.delete("/api/templates/doomed").status_code == 200
    assert len(client.get(f"/api/chart/{target}").json()["children"]) == 2


def test_unknown_template_is_404():
    t = mk("Nowhere")
    assert client.post(f"/api/problems/{t}/template",
                       json={"slug": "nope"}).status_code == 404
    assert client.get("/api/templates/nope").status_code == 404


def test_nesting_is_bounded():
    deep = {"title": "d0", "waypoint": "w", "children": []}
    cur = deep
    for i in range(1, 9):
        nxt = {"title": f"d{i}", "waypoint": "w", "children": []}
        cur["children"] = [nxt]
        cur = nxt
    with pytest.raises(T.TemplateError):
        T.save(Path(_tdir), name="Too deep", problems=[deep])


# ---------- document scaffolds ----------

def test_a_template_may_be_a_document_only():
    """The development cycle has no useful decomposition — it recurs per cycle, and
    its steps in the chart would bury the reasoning under process bookkeeping."""
    r = client.post("/api/templates", json={
        "name": "Doc only", "problems": [],
        "document": {"filename": "{slug}-cycle.md", "body": "# {title}\n\n## Problem\n"}})
    assert r.status_code == 200
    t = client.get("/api/templates/doc-only").json()
    assert t["problems"] == [] and t["document"]["body"].startswith("# {title}")


def test_a_template_with_neither_is_refused():
    assert client.post("/api/templates",
                       json={"name": "Empty", "problems": []}).status_code == 422


def test_applying_a_document_template_writes_the_page(tmp_path):
    main.DOCUMENTS_DIR = tmp_path
    client.post("/api/templates", json={
        "name": "Writes a page", "problems": [],
        "document": {"filename": "{slug}-cycle.md", "body": "# {title}\n\n## Problem\n"}})
    target = mk("Shipyard v0.15")

    r = client.post(f"/api/problems/{target}/template", json={"slug": "writes-a-page"})
    assert r.status_code == 200
    assert r.json()["created"] == 0, "a document template adds nothing to the chart"

    doc = r.json()["document"]
    assert doc["created"] is True
    body = Path(doc["path"]).read_text()
    assert "# Shipyard v0.15" in body, "the title placeholder is filled"
    assert Path(doc["path"]).name == "shipyard-v0-15-cycle.md"


def test_a_document_scaffold_never_overwrites(tmp_path):
    """Create-only, like every other scaffold: it hands you a page, it does not take
    one back."""
    main.DOCUMENTS_DIR = tmp_path
    client.post("/api/templates", json={
        "name": "Careful", "problems": [],
        "document": {"filename": "{slug}.md", "body": "scaffold\n"}})
    target = mk("Already written")
    first = client.post(f"/api/problems/{target}/template", json={"slug": "careful"}).json()
    Path(first["document"]["path"]).write_text("MY WRITING")

    again = client.post(f"/api/problems/{target}/template", json={"slug": "careful"}).json()
    assert again["document"]["created"] is False
    assert Path(again["document"]["path"]).read_text() == "MY WRITING"


def test_the_shipped_cycle_template_is_document_only():
    """Ships with shipyard; the decision that it stays out of the chart is load-bearing."""
    real = T.load(Path(__file__).resolve().parent.parent / "templates", "development-cycle")
    assert real is not None
    assert real["problems"] == []
    assert "Appetite" in real["document"]["body"]
    assert "Retro" in real["document"]["body"]
