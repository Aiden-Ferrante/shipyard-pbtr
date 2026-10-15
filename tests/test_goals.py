"""The goals page: drafts, and the outline that renders one node once."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "goals.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def rm(pid, **params):
    """Delete through the sanctioned path: read the impact, pass its token (v0.35.0)."""
    imp = client.get(f"/api/problems/{pid}/deletion")
    if imp.status_code != 200:
        return client.delete(f"/api/problems/{pid}", params=params)
    return client.delete(f"/api/problems/{pid}", params={**params, "token": imp.json()["token"]})


def mk(title, waypoint="observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_draft_may_be_created_without_a_waypoint():
    """You cannot demand an observable between Enter and the next thought."""
    r = client.post("/api/problems",
                    json={"title": "Captured fast", "waypoint": "", "draft": True})
    assert r.status_code == 200
    node = client.get(f"/api/chart/{r.json()['id']}").json()["node"]
    assert node["draft"] is True


def test_waypoint_still_required_without_the_draft_flag():
    """The composer keeps its guarantee — drafts are an explicit opt-in."""
    r = client.post("/api/problems", json={"title": "No opt-out", "waypoint": ""})
    assert r.status_code == 422


def test_a_problem_with_a_waypoint_is_not_a_draft():
    node = client.get(f"/api/chart/{mk('Proper problem')}").json()["node"]
    assert node["draft"] is False


def test_a_draft_cannot_be_linked_to_a_repo():
    """No unfalsifiable problem becomes real work."""
    r = client.post("/api/problems",
                    json={"title": "Unfalsifiable", "waypoint": "", "draft": True})
    pid = r.json()["id"]
    bad = client.put(f"/api/problems/{pid}/repo", json={"repo": "shipyard"})
    assert bad.status_code == 422
    assert "waypoint first" in bad.json()["detail"]


def test_a_draft_graduates_once_given_a_waypoint():
    r = client.post("/api/problems", json={"title": "Grows up", "waypoint": "", "draft": True})
    pid = r.json()["id"]
    client.patch(f"/api/problems/{pid}", json={"waypoint": "something I can see"})
    assert client.get(f"/api/chart/{pid}").json()["node"]["draft"] is False


def test_having_no_repo_is_not_draft_debt():
    """Most problems should never have a repo — decomposition comes first."""
    node = client.get(f"/api/chart/{mk('Never attacked')}").json()["node"]
    assert node["draft"] is False and node["repo"] is None


def test_outline_is_depth_tagged():
    root = mk("Outline root")
    kid = mk("Outline child", parent_id=root)
    mk("Outline grandchild", parent_id=kid)
    rows = client.get("/api/goals").json()["outline"]
    by_title = {r["title"]: r for r in rows}
    assert by_title["Outline root"]["depth"] == 0
    assert by_title["Outline child"]["depth"] == 1
    assert by_title["Outline grandchild"]["depth"] == 2


def test_shared_node_is_expandable_once_and_a_reference_after():
    a, b = mk("Left bearing"), mk("Right bearing")
    shared = mk("Serves both", parent_id=a)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": b})
    mk("Only child", parent_id=shared)

    rows = [r for r in client.get("/api/goals").json()["outline"] if r["id"] == shared]
    assert len(rows) == 2
    assert [r["reference"] for r in rows] == [False, True]
    # the subtree is walked once, not once per bearing
    kids = [r for r in client.get("/api/goals").json()["outline"]
            if r["title"] == "Only child"]
    assert len(kids) == 1


def test_draft_count_is_surfaced():
    client.post("/api/problems", json={"title": "Debt", "waypoint": "", "draft": True})
    body = client.get("/api/goals").json()
    assert body["drafts"] >= 1
    assert body["total"] >= body["drafts"]


# ---------- delete ----------

def test_delete_promotes_children_rather_than_destroying_them():
    """Deleting a rung must not silently take a whole branch of reasoning with it."""
    root = mk("Delete root")
    mid = mk("Doomed middle", parent_id=root)
    kid = mk("Survivor", parent_id=mid)

    r = rm(mid)
    assert r.status_code == 200
    assert r.json()["promoted"] == ["Survivor"]

    spine = client.get(f"/api/chart/{kid}").json()
    assert [p["title"] for p in spine["parents"]] == ["Delete root"]
    assert client.get(f"/api/chart/{mid}").status_code == 404


def test_deleting_a_root_makes_its_children_roots():
    root = mk("Root to remove")
    kid = mk("Orphaned upward", parent_id=root)
    rm(root)
    assert kid in [s["id"] for s in client.get("/api/board").json()["sections"]]


def test_deletion_impact_is_readable_before_deleting():
    root = mk("Impact root")
    mid = mk("Impact middle", parent_id=root)
    mk("Impact child", parent_id=mid)

    imp = client.get(f"/api/problems/{mid}/deletion").json()
    assert imp["children"] == ["Impact child"]
    assert imp["new_parents"] == ["Impact root"]
    assert imp["becomes_root"] is False
    assert client.get(f"/api/chart/{mid}").status_code == 200, "impact must not delete"


def test_deleting_frees_the_repo_without_touching_it():
    p = mk("Holds a repo")
    client.put(f"/api/problems/{p}/repo", json={"repo": "shipyard"})
    r = rm(p)
    assert r.json()["freed_repo"] == "shipyard"
    # the project is still on disk, now uncharted
    assert any(x["id"] == "shipyard" for x in client.get("/api/board").json()["uncharted"])


def test_deleting_a_leaf_is_clean():
    root = mk("Leaf parent")
    leaf = mk("Just a leaf", parent_id=root)
    r = rm(leaf)
    assert r.json()["promoted"] == []
    assert client.get(f"/api/chart/{leaf}").status_code == 404


def test_deleting_something_that_is_gone_is_404():
    assert client.delete("/api/problems/never-existed").status_code == 404


def test_cascade_deletes_the_branch():
    """Starting over should not mean clicking delete forty times."""
    root = mk("Cascade root")
    mid = mk("Cascade middle", parent_id=root)
    mk("Cascade leaf", parent_id=mid)

    r = rm(root, cascade="true")
    assert r.status_code == 200
    assert r.json()["count"] == 3
    titles = [x["title"] for x in client.get("/api/goals").json()["outline"]]
    for t in ("Cascade root", "Cascade middle", "Cascade leaf"):
        assert t not in titles


def test_cascade_spares_anything_with_another_bearing():
    """A branch delete removes the branch, not work that merely hung off it."""
    doomed, rescue = mk("Cascade doomed"), mk("Cascade rescue")
    shared = mk("Serves two", parent_id=doomed)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": rescue})
    only = mk("Serves one", parent_id=doomed)

    r = rm(doomed, cascade="true")
    titles = [x["title"] for x in client.get("/api/goals").json()["outline"]]
    assert "Serves two" in titles, "a second bearing must spare it"
    assert "Serves one" not in titles
    assert r.json()["spared"] == ["Serves two"]
    assert only


def test_deletion_impact_reports_the_cascade_cost():
    root = mk("Impact cascade root")
    mk("Impact cascade child", parent_id=root)
    imp = client.get(f"/api/problems/{root}/deletion").json()
    assert imp["cascade_count"] == 2


def test_plain_delete_still_promotes():
    root = mk("Still promotes")
    mid = mk("Middle promotes", parent_id=root)
    kid = mk("Promoted kid", parent_id=mid)
    rm(mid)
    spine = client.get(f"/api/chart/{kid}").json()
    assert [p["title"] for p in spine["parents"]] == ["Still promotes"]


def test_a_problem_can_serve_several_goals_without_duplication():
    """Several domains may all serve one economic goal — attaching
    must add a bearing, not move the node."""
    a, b, c = mk("Bearing one"), mk("Bearing two"), mk("Bearing three")
    shared = mk("Serves all three", parent_id=a)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": b})
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": c})

    parents = [p["title"] for p in client.get(f"/api/chart/{shared}").json()["parents"]]
    assert sorted(parents) == ["Bearing one", "Bearing three", "Bearing two"]
    # and it is still one node, rendered once
    rows = [r for r in client.get("/api/goals").json()["outline"]
            if r["id"] == shared and not r["reference"]]
    assert len(rows) == 1


def test_detaching_one_bearing_keeps_the_others():
    a, b = mk("Keeps this one"), mk("Loses this one")
    kid = mk("Two bearings", parent_id=a)
    client.post(f"/api/problems/{kid}/parents", json={"parent_id": b})

    r = client.delete(f"/api/problems/{kid}/parents/{b}")
    assert r.status_code == 200
    assert [p["title"] for p in r.json()["parents"]] == ["Keeps this one"]


def test_detaching_the_last_bearing_makes_it_a_goal():
    a = mk("Only bearing")
    kid = mk("Set adrift", parent_id=a)
    client.delete(f"/api/problems/{kid}/parents/{a}")
    assert kid in [s["id"] for s in client.get("/api/board").json()["sections"]]


def test_graph_renders_a_shared_node_once():
    """The outline must duplicate a two-parent node; the graph must not — that is
    the entire reason the view exists."""
    a, b = mk("Graph bearing A"), mk("Graph bearing B")
    shared = mk("Graph shared", parent_id=a)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": b})

    g = client.get("/api/graph").json()
    assert len([n for n in g["nodes"] if n["id"] == shared]) == 1
    edges = [(e["child"], e["parent"]) for e in g["edges"]]
    assert (shared, a) in edges and (shared, b) in edges


def test_graph_carries_what_a_node_needs_to_be_drawn():
    p = mk("Graph node", waypoint="visible thing")
    n = next(n for n in client.get("/api/graph").json()["nodes"] if n["id"] == p)
    assert set(n) >= {"id", "title", "waypoint", "draft", "repo", "anchored", "sounding"}


def test_description_and_notes_round_trip():
    p = mk("Prose holder")
    client.patch(f"/api/problems/{p}", json={"description": "what it is",
                                             "notes": "line one\nline two"})
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["description"] == "what it is"
    assert node["notes"] == "line one\nline two"


def test_create_accepts_prose_rather_than_dropping_it():
    """Pydantic ignores unknown fields, so a POST carrying a description used to
    return 200 and lose the text with nothing to say so."""
    r = client.post("/api/problems", json={"title": "Born with prose",
                                           "waypoint": "observable",
                                           "description": "what it is",
                                           "notes": "what I learned"})
    assert r.status_code == 200, r.text
    node = client.get(f"/api/chart/{r.json()['id']}").json()["node"]
    assert node["description"] == "what it is"
    assert node["notes"] == "what I learned"


def test_writing_prose_does_not_touch_the_sounding():
    """The recurring hazard: a PATCH that posts back a field it does not display
    silently rewrites evidence. Prose must leave the sounding exactly alone."""
    p = mk("Prose vs sounding")
    client.patch(f"/api/problems/{p}", json={"sounding": "observed"})
    client.patch(f"/api/problems/{p}", json={"description": "d", "notes": "n"})
    assert client.get(f"/api/chart/{p}").json()["node"]["sounding"] == "observed"


def test_multiline_notes_do_not_break_the_export_list():
    """chart.md is a nested markdown list. A raw newline in a note would end the
    list and reflow everything under it, so continuations are indented."""
    from app import chart
    from app import main as app_main
    # Under a bearing on purpose: a parentless leaf is bare drift, and the export
    # renders drift as a one-line summary that carries no prose at all.
    bearing = mk("Export bearing", waypoint="observable")
    p = mk("Export prose", waypoint="observable", parent_id=bearing)
    client.patch(f"/api/problems/{p}", json={"notes": "first\nsecond"})
    con = app_main.db()
    try:
        md = chart.render_markdown(con)
    finally:
        con.close()
    assert "- Notes — first" in md
    # the continuation is indented past the bullet, never flush at column zero
    line = next(l for l in md.splitlines() if l.strip() == "second")
    assert line.startswith("    "), f"continuation not indented: {line!r}"


def test_graph_scopes_to_a_subtree():
    """A project draws its own canvas, so the graph takes the same `root` scoping
    the outline already had — and an edge is only drawn when both ends are."""
    above = mk("Graph bearing above")
    root = mk("Graph scoped root", parent_id=above)
    kid = mk("Graph scoped child", parent_id=root)
    mk("Graph unrelated")

    g = client.get(f"/api/graph?root={root}").json()
    ids = {n["id"] for n in g["nodes"]}
    assert ids == {root, kid}, "the subtree and nothing else — not the bearing above it"
    edges = [(e["child"], e["parent"]) for e in g["edges"]]
    assert edges == [(kid, root)], "the edge up to the out-of-scope bearing is a line to nowhere"


def test_graph_scopes_by_project_id_too():
    """`root` takes a repo id like every other ref on this API."""
    p = mk("Graph by repo", repo="some-repo")
    g = client.get("/api/graph?root=some-repo").json()
    assert [n["id"] for n in g["nodes"]] == [p]


def test_graph_rejects_an_unknown_root():
    assert client.get("/api/graph?root=nothing-here").status_code == 404


def test_unscoped_graph_is_unchanged_by_scoping():
    """The Chart tab still gets the whole chart when it asks for no root."""
    a = mk("Graph whole A")
    mk("Graph whole B", parent_id=a)
    g = client.get("/api/graph").json()
    assert len(g["nodes"]) >= 2 and any(n["id"] == a for n in g["nodes"])


# ---------- shared vs copied ----------

def test_outline_counts_occurrences_of_a_shared_goal():
    """One goal in three places should read as 1/3, not as three goals."""
    a, b, c = mk("Occ one"), mk("Occ two"), mk("Occ three")
    shared = mk("Health", parent_id=a)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": b})
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": c})

    rows = [r for r in client.get("/api/goals").json()["outline"] if r["id"] == shared]
    assert len(rows) == 3
    assert [r["occurrence"] for r in rows] == [1, 2, 3]
    assert all(r["occurrences"] == 3 for r in rows)
    assert [r["reference"] for r in rows] == [False, True, True]


def test_a_single_placement_is_one_of_one():
    p = mk("Only here")
    row = next(r for r in client.get("/api/goals").json()["outline"] if r["id"] == p)
    assert row["occurrence"] == 1 and row["occurrences"] == 1


def test_duplicate_makes_independent_nodes():
    """Sharing says 'the same goal'; copying says 'two goals that will diverge'."""
    src_parent = mk("Copy source parent")
    src = mk("Copy me", parent_id=src_parent)
    mk("Copied child", parent_id=src)
    dest = mk("Copy destination")

    r = client.post(f"/api/problems/{src}/duplicate", json={"parent_id": dest})
    assert r.status_code == 200
    copy_id = r.json()["id"]
    assert copy_id != src

    kids = client.get(f"/api/chart/{copy_id}").json()["children"]
    assert [k["title"] for k in kids] == ["Copied child"]

    # editing the copy must not touch the original
    client.patch(f"/api/problems/{copy_id}", json={"title": "Diverged"})
    assert client.get(f"/api/chart/{src}").json()["node"]["title"] == "Copy me"


def test_a_copy_does_not_take_the_repo_or_the_anchor():
    """A project is attacked by one problem, and a copy has decided nothing yet."""
    p = mk("Has both")
    client.put(f"/api/problems/{p}/repo", json={"repo": "shipyard"})
    client.post(f"/api/problems/{p}/anchor", json={"basis": "held up for years"})

    copy_id = client.post(f"/api/problems/{p}/duplicate", json={}).json()["id"]
    node = client.get(f"/api/chart/{copy_id}").json()["node"]
    assert node["repo"] is None
    assert node["anchored"] is False
    assert client.get(f"/api/chart/{p}").json()["node"]["repo"] == "shipyard"
    client.put(f"/api/problems/{p}/repo", json={"repo": None})


def test_a_copy_keeps_the_shape():
    p = mk("Shapely", waypoint="a thing I could see")
    client.patch(f"/api/problems/{p}", json={"sounding": "proxy", "reasoning": "because"})
    copy_id = client.post(f"/api/problems/{p}/duplicate", json={}).json()["id"]
    node = client.get(f"/api/chart/{copy_id}").json()["node"]
    assert node["waypoint"] == "a thing I could see"
    assert node["sounding"] == "proxy" and node["reasoning"] == "because"
