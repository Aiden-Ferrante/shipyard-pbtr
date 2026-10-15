"""The chart: one node type, required waypoints, evidence capped by children."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "chart.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.chart as chart_mod  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def rm(pid, **params):
    """Delete through the sanctioned path: read the impact, pass its token (v0.35.0)."""
    imp = client.get(f"/api/problems/{pid}/deletion")
    if imp.status_code != 200:
        return client.delete(f"/api/problems/{pid}", params=params)
    return client.delete(f"/api/problems/{pid}", params={**params, "token": imp.json()["token"]})


def db_conn():
    """The database the *app* is using.

    Not `os.environ["SHIPYARD_DB"]` — several test modules set that name, the app
    binds DB_PATH once at import, and whichever module imported first wins. Reading
    the env at call time opened a different, empty file and every assertion about
    written rows came back empty."""
    import sqlite3
    import app.main as main_mod
    con = sqlite3.connect(main_mod.DB_PATH)
    chart_mod.init(con)
    return con


def mk(title, waypoint="something observable", **kw):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_waypoint_is_required():
    """A problem with no observable is a category — the chart must refuse it."""
    r = client.post("/api/problems", json={"title": "Be better", "waypoint": ""})
    assert r.status_code == 422
    assert "waypoint" in r.json()["detail"]


def test_title_is_required():
    r = client.post("/api/problems", json={"title": "  ", "waypoint": "x"})
    assert r.status_code == 422


def test_bad_sounding_rejected():
    r = client.post("/api/problems",
                    json={"title": "t", "waypoint": "w", "sounding": "vibes"})
    assert r.status_code == 422


def test_spine_has_parents_and_children():
    bearing = mk("A bearing")
    project = mk("Learn Hub", repo="learn-hub", parent_id=bearing)
    mk("Habit", parent_id=project)

    view = client.get(f"/api/chart/{project}").json()
    assert view["node"]["title"] == "Learn Hub"
    assert [p["title"] for p in view["parents"]] == ["A bearing"]
    assert [c["title"] for c in view["children"]] == ["Habit"]


def test_resolves_by_project_id_too():
    """The board hands shipyard a project id, not a problem id."""
    bearing = mk("Ship things")
    mk("csv-profiler", repo="csv-profiler", parent_id=bearing)
    view = client.get("/api/chart/csv-profiler").json()
    assert view["node"]["repo"] == "csv-profiler"


def test_second_parent_can_be_attached():
    """Many-to-many is the point: a second bearing is insurance against a thaw."""
    a, b = mk("Bearing A"), mk("Bearing B")
    proj = mk("Two-parent project", repo="tpp", parent_id=a)
    r = client.post(f"/api/problems/{proj}/parents", json={"parent_id": b})
    assert r.status_code == 200
    assert sorted(p["title"] for p in r.json()["parents"]) == ["Bearing A", "Bearing B"]


def test_self_edge_rejected():
    p = mk("Loner")
    r = client.post(f"/api/problems/{p}/parents", json={"parent_id": p})
    assert r.status_code == 422


def test_unknown_parent_rejected():
    p = mk("Orphan")
    r = client.post(f"/api/problems/{p}/parents", json={"parent_id": "nope"})
    assert r.status_code == 422


def test_sounding_is_capped_by_children():
    """A claim is only as good as what supports it."""
    parent = mk("Confident parent", sounding="observed")
    mk("Weak child", parent_id=parent, sounding="assumed")

    view = client.get(f"/api/chart/{parent}").json()
    assert view["node"]["sounding"] == "observed"          # what was declared
    assert view["node"]["effective_sounding"] == "assumed"  # what it's worth


def test_leaf_keeps_its_own_sounding():
    leaf = mk("Measured leaf", sounding="observed")
    assert client.get(f"/api/chart/{leaf}").json()["node"]["effective_sounding"] == "observed"


def test_best_child_carries_the_parent():
    parent = mk("Parent", sounding="observed")
    mk("Weak", parent_id=parent, sounding="assumed")
    mk("Strong", parent_id=parent, sounding="observed")
    view = client.get(f"/api/chart/{parent}").json()
    assert view["node"]["effective_sounding"] == "observed"


def test_drift_lists_problems_with_no_bearing():
    loose = mk("Serves nothing in particular")
    ids = [d["id"] for d in client.get("/api/drift").json()["drift"]]
    assert loose in ids


def test_missing_node_is_404():
    assert client.get("/api/chart/does-not-exist").status_code == 404


def test_export_renders_the_chart(tmp_path):
    """data/*.sqlite is gitignored — the export is what gives the chart a history."""
    from app import chart as chart_mod
    from app.main import db

    con = db()
    try:
        out = tmp_path / "chart.md"
        chart_mod.export(con, out)
        body = out.read_text()
        assert "# Chart" in body
        assert "Do not edit by hand" in body
        assert "Waypoint —" in body
    finally:
        con.close()


def test_export_marks_capped_soundings(tmp_path):
    from app import chart as chart_mod
    from app.main import db

    parent = mk("Export parent", sounding="observed")
    mk("Export child", parent_id=parent, sounding="assumed")
    con = db()
    try:
        out = tmp_path / "c.md"
        chart_mod.export(con, out)
        assert "capped by its children" in out.read_text()
    finally:
        con.close()


def test_shared_node_is_not_rendered_twice(tmp_path):
    """A project with two bearings is one node — not two subtrees."""
    from app import chart as chart_mod
    from app.main import db

    a, b = mk("Dedup bearing A"), mk("Dedup bearing B")
    proj = mk("Shared project", repo="shared-proj", parent_id=a)
    client.post(f"/api/problems/{proj}/parents", json={"parent_id": b})
    mk("Only child of shared", parent_id=proj)

    con = db()
    try:
        out = tmp_path / "d.md"
        chart_mod.export(con, out)
        body = out.read_text()
        assert body.count("Only child of shared") == 1
        assert "shown in full above" in body
    finally:
        con.close()


def test_a_repo_cannot_be_created_onto_a_second_problem():
    """`link_repo` has always refused a repo another problem holds, but *create* is a
    second door onto the same column and did not check — so POST /api/problems and
    `scripts/seed_chart.py` could both write the state the API would reject. Two
    nodes carrying one repo render as the same project card twice."""
    bearing = mk("Repo clash bearing")
    first = mk("First owner", repo="clash-fixture", parent_id=bearing)

    r = client.post("/api/problems", json={"title": "Second owner",
                                           "waypoint": "also observable",
                                           "repo": "clash-fixture"})
    assert r.status_code == 422
    assert "already linked to another problem" in r.json()["detail"]
    assert client.get(f"/api/chart/{first}").json()["node"]["repo"] == "clash-fixture"


# ---------- v0.3.0: editing, anchors, thaw impact ----------

def test_sounding_can_be_upgraded_and_parent_follows():
    """Evidence arriving is the whole reason edit exists."""
    parent = mk("Upgrade parent", sounding="observed")
    child = mk("Upgrade child", parent_id=parent, sounding="assumed")
    assert client.get(f"/api/chart/{parent}").json()["node"]["effective_sounding"] == "assumed"

    r = client.patch(f"/api/problems/{child}", json={"sounding": "observed"})
    assert r.status_code == 200
    assert client.get(f"/api/chart/{parent}").json()["node"]["effective_sounding"] == "observed"


def test_blanking_a_waypoint_demotes_to_draft():
    """Since v0.8.0 a blank waypoint is not an error — it means "not falsifiable yet".
    The rule that matters moved to the repo link: a draft can't become work."""
    p = mk("Loses its waypoint")
    assert client.patch(f"/api/problems/{p}", json={"waypoint": "  "}).status_code == 200
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["draft"] is True
    assert client.put(f"/api/problems/{p}/repo",
                      json={"repo": "shipyard"}).status_code == 422


def test_edit_unknown_problem_is_422():
    assert client.patch("/api/problems/nope", json={"title": "x"}).status_code == 422


def test_freeze_requires_a_basis():
    p = mk("Needs a reason")
    assert client.post(f"/api/problems/{p}/anchor", json={"basis": " "}).status_code == 422


def test_freeze_then_thaw_keeps_the_record():
    """Thawing clears the frozen state, never the history of what was believed."""
    p = mk("Belief")
    client.post(f"/api/problems/{p}/anchor",
                json={"basis": "held up for two years", "falsifier": "a month that contradicts it"})
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["anchored"] is True and node["anchor_basis"] == "held up for two years"

    client.delete(f"/api/problems/{p}/anchor", params={"token": client.get(f"/api/problems/{p}/impact").json()["token"]})
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["anchored"] is False
    assert node["anchor_basis"] == "held up for two years"   # kept on purpose
    assert node["falsifier"] == "a month that contradicts it"


def test_impact_separates_survivors_from_orphans():
    """A second bearing is insurance — that is the number worth seeing before a thaw."""
    doomed = mk("Doomed bearing")
    rescue = mk("Rescue bearing")
    safe = mk("Has two parents", parent_id=doomed)
    client.post(f"/api/problems/{safe}/parents", json={"parent_id": rescue})
    lost = mk("Only one parent", parent_id=doomed)
    assert lost

    imp = client.get(f"/api/problems/{doomed}/impact").json()
    assert imp["affected"] == 2
    assert [n["title"] for n in imp["survives"]] == ["Has two parents"]
    assert imp["survives"][0]["kept_by"] == ["Rescue bearing"]
    assert [n["title"] for n in imp["orphaned"]] == ["Only one parent"]


def test_impact_counts_projects():
    b = mk("Bearing with a project")
    mk("A project", repo="impact-proj", parent_id=b)
    imp = client.get(f"/api/problems/{b}/impact").json()
    assert [p["repo"] for p in imp["projects"]] == ["impact-proj"]


def test_impact_of_missing_problem_is_404():
    assert client.get("/api/problems/nope/impact").status_code == 404


def test_survival_is_transitive():
    """A child of a surviving project survives too — the rescue propagates down."""
    doomed = mk("Transitive doomed")
    rescue = mk("Transitive rescue")
    proj = mk("Rescued project", repo="rescued", parent_id=doomed)
    client.post(f"/api/problems/{proj}/parents", json={"parent_id": rescue})
    grandchild = mk("Child of a rescued project", parent_id=proj)

    imp = client.get(f"/api/problems/{doomed}/impact").json()
    titles = {n["title"] for n in imp["survives"]}
    assert "Rescued project" in titles
    assert "Child of a rescued project" in titles, "survival must propagate downward"
    assert grandchild
    assert imp["orphaned"] == []


def test_a_bearing_is_not_drift():
    """A parentless problem with children is a top-level aim, not an orphan."""
    bearing = mk("A real bearing")
    mk("Something it carries", parent_id=bearing)
    ids = [d["id"] for d in client.get("/api/drift").json()["drift"]]
    assert bearing not in ids


def test_a_parentless_project_is_drift():
    """A project with nothing above it has no stated reason to exist."""
    p = mk("Unmoored project", repo="unmoored")
    ids = [d["id"] for d in client.get("/api/drift").json()["drift"]]
    assert p in ids


def test_uncharted_projects_show_as_drift():
    """The loudest 'nothing records why this exists' is a repo never charted."""
    items = client.get("/api/drift").json()["drift"]
    assert any(d.get("uncharted") for d in items)


# ---------- repeated bearings ----------

def serves(child, parent):
    r = client.post(f"/api/problems/{child}/parents", json={"parent_id": parent})
    assert r.status_code == 200, r.text


def test_a_repeated_bearing_set_is_a_missing_node():
    """Ten problems each serving the same two goals assert one fact twenty times
    and state it zero times — the thing they share has no name."""
    a, b = mk("Finance Undergraduate"), mk("Data Science Masters")
    kids = [mk(f"role {i}") for i in range(10)]
    for k in kids:
        serves(k, a)
        serves(k, b)

    found = client.get("/api/chart-groupings").json()["groupings"]
    mine = [g for g in found if len(g["children"]) == 10]
    assert len(mine) == 1
    assert {b_["title"] for b_ in mine[0]["bearings"]} == {"Finance Undergraduate",
                                                           "Data Science Masters"}
    assert (mine[0]["edges_now"], mine[0]["edges_after"]) == (20, 12)


def test_a_grouping_that_would_not_pay_stays_quiet():
    """Two problems sharing two bearings costs four edges either way. The rule is
    the break-even itself, not a tuned threshold, so this is silent."""
    a, b = mk("bearing one"), mk("bearing two")
    for i in range(2):
        k = mk(f"pair {i}")
        serves(k, a)
        serves(k, b)
    found = client.get("/api/chart-groupings").json()["groupings"]
    assert not [g for g in found
                if {x["title"] for x in g["bearings"]} == {"bearing one", "bearing two"}]


def test_grouping_rewires_children_onto_the_new_node():
    a, b = mk("route A"), mk("route B")
    kids = [mk(f"shared {i}") for i in range(3)]
    for k in kids:
        serves(k, a)
        serves(k, b)

    r = client.post("/api/chart-groupings", json={
        "title": "What they have in common",
        "bearing_ids": [a, b], "child_ids": kids})
    assert r.status_code == 200, r.text
    gid = r.json()["id"]

    group = client.get(f"/api/chart/{gid}").json()
    assert {p["title"] for p in group["parents"]} == {"route A", "route B"}
    # each child now serves only the group — the repetition is gone, not duplicated
    for k in kids:
        assert [p["id"] for p in client.get(f"/api/chart/{k}").json()["parents"]] == [gid]


def test_the_group_is_a_draft_until_it_earns_a_waypoint():
    """It is a problem like any other: named, but not yet falsifiable."""
    a, b = mk("bearing X"), mk("bearing Y")
    kids = [mk(f"kid {i}") for i in range(3)]
    for k in kids:
        serves(k, a)
        serves(k, b)
    gid = client.post("/api/chart-groupings", json={
        "title": "Unnamed commonality", "bearing_ids": [a, b], "child_ids": kids}).json()["id"]
    assert client.get(f"/api/chart/{gid}").json()["node"]["draft"] is True


def test_a_stale_grouping_is_refused():
    """This rewires many edges off a suggestion that may have been on screen a
    while. Regrouping something that no longer matches would be exactly the
    invisible mutation this app exists to prevent."""
    a, b = mk("old A"), mk("old B")
    kids = [mk(f"drifting {i}") for i in range(3)]
    for k in kids:
        serves(k, a)
        serves(k, b)
    client.delete(f"/api/problems/{kids[0]}/parents/{b}")   # the chart moved

    r = client.post("/api/chart-groupings", json={
        "title": "Too late", "bearing_ids": [a, b], "child_ids": kids})
    assert r.status_code == 422
    assert "no longer serves" in r.json()["detail"]


def test_a_group_needs_a_name():
    a, b = mk("nameless A"), mk("nameless B")
    kids = [mk(f"n {i}") for i in range(3)]
    for k in kids:
        serves(k, a)
        serves(k, b)
    r = client.post("/api/chart-groupings", json={
        "title": "   ", "bearing_ids": [a, b], "child_ids": kids})
    assert r.status_code == 422


# ---------- a project's own tree ----------

def test_a_project_tree_is_rooted_at_the_problem_its_repo_attacks():
    """Above a project is shared, below is local — so a project draws the same tree
    the goals page does, rooted at its own master problem rather than the fleet's."""
    top = mk("tree-fleet bearing")
    master = mk("tree-master", repo="tree-fixture-repo")
    serves(master, top)
    kid = mk("tree-child")
    serves(kid, master)

    body = client.get("/api/chart/tree-fixture-repo/tree").json()
    assert body["root"] == master
    titles = [r["title"] for r in body["outline"]]
    assert titles == ["tree-master", "tree-child"]
    assert "tree-fleet bearing" not in titles, "the bearing above is not part of this chart"
    assert [r["depth"] for r in body["outline"]] == [0, 1], "the master problem is depth 0"


def test_the_tree_counts_what_cannot_be_observed():
    master = mk("tree-counts", repo="tree-fixture-two")
    a = client.post("/api/problems", json={"title": "tree-vague", "waypoint": "",
                                           "draft": True, "parent_id": master})
    assert a.status_code == 200, a.text
    body = client.get("/api/chart/tree-fixture-two/tree").json()
    assert body["total"] == 2 and body["drafts"] == 1


def test_a_tree_for_something_uncharted_is_a_404():
    assert client.get("/api/chart/no-such-repo-at-all/tree").status_code == 404


def test_the_whole_outline_is_unchanged_by_rooting():
    """The rooted call is the same walk with a different start, so the unrooted one
    must keep behaving exactly as the goals page depends on."""
    con = db_conn()
    try:
        assert chart_mod.outline(con) == chart_mod.outline(con, None)
    finally:
        con.close()


# ---------- cycles that addressed a problem ----------

def test_a_cycle_can_be_recorded_against_a_problem():
    p = mk("addressed-problem")
    r = client.post(f"/api/problems/{p}/cycles", json={"version": "0.4.0"})
    assert r.status_code == 200
    assert r.json()["addressed_by"] == ["0.4.0"]


def test_addressing_says_nothing_about_whether_it_worked():
    """The whole point of "addressed by" over "solved by": three cycles beside an
    `assumed` sounding is effort with nothing to show for it, and that state has to
    stay visible rather than being collapsed into a tick."""
    p = mk("still-assumed")
    for v in ("0.1.0", "0.2.0", "0.3.0"):
        client.post(f"/api/problems/{p}/cycles", json={"version": v})
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["sounding"] == "assumed", "linking work does not move the evidence"


def test_a_problem_can_take_several_cycles_and_a_cycle_several_problems():
    a, b = mk("many-a"), mk("many-b")
    client.post(f"/api/problems/{a}/cycles", json={"version": "0.5.0"})
    client.post(f"/api/problems/{a}/cycles", json={"version": "0.6.0"})
    client.post(f"/api/problems/{b}/cycles", json={"version": "0.5.0"})
    assert client.get(f"/api/chart/{a}").json()["node"]["id"] == a
    con = db_conn()
    try:
        assert chart_mod.addressed_by(con, a) == ["0.5.0", "0.6.0"]
        assert chart_mod.addressed_by(con, b) == ["0.5.0"]
    finally:
        con.close()


def test_linking_the_same_cycle_twice_is_idempotent():
    p = mk("twice-linked")
    for _ in range(2):
        client.post(f"/api/problems/{p}/cycles", json={"version": "0.7.0"})
    con = db_conn()
    try:
        assert chart_mod.addressed_by(con, p) == ["0.7.0"]
    finally:
        con.close()


def test_a_cycle_is_named_by_the_tag_it_cut():
    """Anything that is not a version is not a cycle — the protocol is explicit that
    the version bump is the transaction commit."""
    p = mk("bad-version")
    for bad in ("latest", "nightly", "", "v1"):
        r = client.post(f"/api/problems/{p}/cycles", json={"version": bad})
        assert r.status_code == 422, bad


def test_a_link_can_be_removed():
    p = mk("unlinkable")
    client.post(f"/api/problems/{p}/cycles", json={"version": "0.8.0"})
    r = client.delete(f"/api/problems/{p}/cycles/0.8.0")
    assert r.status_code == 200 and r.json()["addressed_by"] == []


def test_the_tree_carries_the_links():
    master = mk("linked-master", repo="link-fixture-repo")
    client.post(f"/api/problems/{master}/cycles", json={"version": "0.9.0"})
    row = client.get("/api/chart/link-fixture-repo/tree").json()["outline"][0]
    assert row["addressed_by"] == ["0.9.0"]


def test_deleting_a_problem_takes_its_links_with_it():
    p = mk("doomed-link")
    client.post(f"/api/problems/{p}/cycles", json={"version": "0.9.1"})
    rm(p)
    con = db_conn()
    try:
        left = con.execute("SELECT COUNT(*) FROM problem_cycles WHERE problem_id=?",
                           (p,)).fetchone()[0]
        assert left == 0, "a deleted problem must not leave links behind"
    finally:
        con.close()


def test_editing_without_a_sounding_leaves_it_alone():
    """The sounding pickers were removed from the UI but the data was kept, so
    the edit form now PATCHes `{title, waypoint}` and never mentions sounding.
    That is only safe while a missing field means "leave it alone" — if PATCH
    ever coerced absent to `assumed`, every edit would silently erase evidence
    with nothing on screen to show it had happened.
    """
    p = mk("evidence I want to keep", sounding="observed")
    r = client.patch(f"/api/problems/{p}", json={"title": "renamed", "waypoint": "moved"})
    assert r.status_code == 200
    node = client.get(f"/api/chart/{p}").json()["node"]
    assert node["sounding"] == "observed"
    assert node["title"] == "renamed" and node["waypoint"] == "moved"


def test_a_new_problem_starts_assumed_without_being_told():
    """The composer no longer sends a sounding either — a fresh claim takes the
    server default rather than whatever the removed picker last had selected."""
    body = client.post("/api/problems", json={"title": "fresh", "waypoint": "w"}).json()
    assert client.get(f"/api/chart/{body['id']}").json()["node"]["sounding"] == "assumed"


"""nearest_repos — which cycles may address a problem.

The rule that matters is *nearest*, not transitive: a big PBTR cycle is made of the
small ones directly beneath it, so a bearing must not be offered a leaf's patch tag.
"""


def test_a_problem_with_a_repo_answers_for_itself():
    pid = mk("has a repo", repo="alpha")
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, pid) == ["alpha"]
    finally:
        con.close()


def test_a_goal_inherits_the_repo_below_it():
    goal = mk("goal above")
    mk("kid with repo", repo="beta", parent_id=goal)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, goal) == ["beta"]
    finally:
        con.close()


def test_it_stops_at_the_nearest_repo_rather_than_collecting_the_subtree():
    """Collecting the transitive set would put a leaf's patch release in the picker
    for the root bearing — the composition read backwards."""
    goal = mk("stops here goal")
    mid = mk("mid", repo="gamma", parent_id=goal)
    deep = mk("deep", repo="delta", parent_id=mid)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, goal) == ["gamma"], "delta is below gamma, not beside it"
        assert chart_mod.nearest_repos(con, deep) == ["delta"]
    finally:
        con.close()


def test_a_goal_over_several_projects_offers_each_branch():
    goal = mk("two projects")
    mk("p one", repo="eps", parent_id=goal)
    mk("p two", repo="zeta", parent_id=goal)
    con = db_conn()
    try:
        assert sorted(chart_mod.nearest_repos(con, goal)) == ["eps", "zeta"]
    finally:
        con.close()


def test_a_branch_with_no_repo_anywhere_below_offers_nothing():
    goal = mk("all abstract")
    mk("also abstract", parent_id=goal)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, goal) == []
    finally:
        con.close()


def test_cycle_options_reports_the_repos_it_resolved():
    goal = mk("options goal")
    mk("options kid", repo="project-problem", parent_id=goal)
    r = client.get(f"/api/problems/{goal}/cycle-options")
    assert r.status_code == 200, r.text
    assert r.json()["repos"] == ["project-problem"]


def test_cycle_options_404s_for_a_problem_that_does_not_exist():
    assert client.get("/api/problems/nope/cycle-options").status_code == 404


def test_a_version_no_repo_cut_is_still_only_shape_checked():
    """Documents the gap the picker exists to close: address() validates the shape
    of a version, never that anything ever cut it."""
    pid = mk("shape only", repo="eta")
    assert client.post(f"/api/problems/{pid}/cycles", json={"version": "v9.9.9"}).status_code == 200
    bad = client.post(f"/api/problems/{pid}/cycles", json={"version": "not-a-version"})
    assert bad.status_code == 422


"""Opening a cycle — the Plan step shipyard never had.

A tag is the LAST event in P→B→T→R, so a chart that only knew about cut versions
only ever learned a cycle existed once it was over.
"""


def test_role_reads_scope_off_the_tree():
    """The shape of the tree is already a claim about how big a cycle is."""
    bearing = mk("a bearing")
    branch = mk("a branch", parent_id=bearing)
    leaf = mk("a leaf", parent_id=branch)
    con = db_conn()
    try:
        assert chart_mod.role(con, bearing) == "bearing"
        assert chart_mod.role(con, branch) == "branch"
        assert chart_mod.role(con, leaf) == "leaf"
        assert chart_mod.ROLE_BUMP["bearing"] == "major"
        assert chart_mod.ROLE_BUMP["branch"] == "minor"
        assert chart_mod.ROLE_BUMP["leaf"] == "patch"
    finally:
        con.close()


def test_composition_counts_children_that_have_cycles():
    """Reported, never enforced — a parent cycle over children with none is a
    legible state, sometimes correct, and always worth seeing."""
    parent = mk("parent w/ kids")
    a = mk("kid a", parent_id=parent)
    mk("kid b", parent_id=parent)
    client.post(f"/api/problems/{a}/cycles", json={"version": "v1.0.0"})
    con = db_conn()
    try:
        c = chart_mod.cycle_composition(con, parent)
        assert c["children"] == 2 and c["with_cycles"] == 1
        assert c["missing"] == ["kid b"]
    finally:
        con.close()


def test_next_version_bumps_the_right_component():
    from app import repo as repo_mod
    assert repo_mod.next_version("v1.2.3", "major") == "v2.0.0"
    assert repo_mod.next_version("v1.2.3", "minor") == "v1.3.0"
    assert repo_mod.next_version("v1.2.3", "patch") == "v1.2.4"
    assert repo_mod.next_version(None, "minor") == "v0.1.0", "an untagged repo starts somewhere"


def test_opening_a_cycle_needs_a_repo_to_cut_in():
    pid = mk("pure reasoning")
    r = client.post(f"/api/problems/{pid}/cycles/open",
                    json={"version": "v0.1.0", "title": "nope"})
    assert r.status_code == 422
    assert "no repo beneath" in r.json()["detail"]


def test_a_problem_over_two_repos_refuses_to_guess_which_one_it_cuts():
    goal = mk("over two")
    mk("one", repo="over-two-alpha", parent_id=goal)
    mk("two", repo="over-two-beta", parent_id=goal)
    r = client.post(f"/api/problems/{goal}/cycles/open",
                    json={"version": "v0.1.0", "title": "ambiguous"})
    assert r.status_code == 422
    assert "name which one" in r.json()["detail"]


def test_an_open_cycle_is_a_linked_version_with_no_tag_behind_it():
    """The tag is what closes it, so there is no 'done' flag to forget to set."""
    pid = mk("in flight", repo="in-flight-repo")
    client.post(f"/api/problems/{pid}/cycles", json={"version": "v99.0.0"})
    d = client.get(f"/api/problems/{pid}/cycle-options").json()
    assert "99.0.0" in d["open"], "no tag cut it, so it is still open"
    assert all(o["version"].lstrip("v") != "99.0.0" for o in d["options"])


def test_versions_are_stored_without_the_v_whichever_spelling_arrives():
    """`v0.1.0` beside git's `0.18.0` in one list rendered as "vv0.1.0"."""
    pid = mk("spelling", repo="theta")
    client.post(f"/api/problems/{pid}/cycles", json={"version": "v1.2.3"})
    client.post(f"/api/problems/{pid}/cycles", json={"version": "4.5.6"})
    con = db_conn()
    try:
        assert chart_mod.addressed_by(con, pid) == ["1.2.3", "4.5.6"]
    finally:
        con.close()
    # and unlinking works from either spelling
    client.delete(f"/api/problems/{pid}/cycles/v1.2.3")
    con = db_conn()
    try:
        assert chart_mod.addressed_by(con, pid) == ["4.5.6"]
    finally:
        con.close()


def test_the_proposal_steps_past_an_open_cycle():
    """Reading only the latest tag proposed a version an open cycle had already
    claimed, so the second cycle collided with the first."""
    from app import repo as repo_mod
    assert repo_mod.next_version("v0.18.0", "minor") == "v0.19.0"
    assert repo_mod.next_version("v0.18.0", "minor", ["0.19.0"]) == "v0.20.0"
    assert repo_mod.next_version("v0.18.0", "patch", ["0.19.0"]) == "v0.19.1"


def test_versions_compare_as_numbers_not_strings():
    """`0.9.0` sorts above `0.10.0` lexically — the classic way this goes wrong."""
    from app import repo as repo_mod
    assert repo_mod.next_version("v0.9.0", "minor", ["0.10.0"]) == "v0.11.0"


def test_a_claimed_version_is_scoped_to_the_repo_not_the_problem():
    """A goal and the project beneath it cut the same version line, so a cycle
    opened on either must be visible to the other. Scoping the claim to the problem
    would let them each propose the same number and collide only when the second
    tried to write its record."""
    goal = mk("goal over one repo")
    proj = mk("the project", repo="iota", parent_id=goal)
    client.post(f"/api/problems/{proj}/cycles", json={"version": "v2.5.0"})

    con = db_conn()
    try:
        assert "2.5.0" in chart_mod.versions_claimed_in(con, "iota")
        assert chart_mod.nearest_repos(con, goal) == ["iota"], "the goal shares the line"
    finally:
        con.close()

    d = client.get(f"/api/problems/{goal}/cycle-options").json()
    assert "2.5.0" in d["claimed"], "the goal must see what its project already claimed"
    assert d["proposed"] != "v2.5.0"


# ---------- standings: done / open / blocked ----------
#
# The focus-tree primitive. One derived rule, read by both the outline and the
# graph, because two views of one chart disagreeing about it is its own confusion.

def standing_of(pid):
    return {n["id"]: n["standing"] for n in client.get("/api/graph").json()["nodes"]}[pid]


def test_a_leaf_is_open():
    """The frontier starts at the bottom: nothing is beneath a leaf, so nothing
    blocks it."""
    assert standing_of(mk("stand-leaf")) == "open"


def test_a_parent_with_an_unsolved_child_is_blocked():
    parent = mk("stand-parent")
    child = mk("stand-child")
    client.post(f"/api/problems/{child}/parents", json={"parent_id": parent})
    assert standing_of(parent) == "blocked"
    assert standing_of(child) == "open"


def test_solving_the_last_child_opens_the_parent():
    """This is the whole mechanic — the frontier moves up as work lands."""
    parent = mk("stand-move-parent")
    a, b = mk("stand-move-a"), mk("stand-move-b")
    for k in (a, b):
        client.post(f"/api/problems/{k}/parents", json={"parent_id": parent})
    assert standing_of(parent) == "blocked"

    client.patch(f"/api/problems/{a}/solved", json={"solved": True})
    assert standing_of(parent) == "blocked", "one of two is not enough"

    client.patch(f"/api/problems/{b}/solved", json={"solved": True})
    assert standing_of(parent) == "open", "nothing outstanding beneath it now"


def test_solved_wins_over_everything():
    """A problem you have declared solved reads as done even if the chart beneath it
    was never finished — `solved` is set by hand and a parent is not the sum of its
    parts, so the rule must not quietly overrule the person."""
    parent = mk("stand-declared")
    child = mk("stand-declared-child")
    client.post(f"/api/problems/{child}/parents", json={"parent_id": parent})
    client.patch(f"/api/problems/{parent}/solved", json={"solved": True})
    assert standing_of(parent) == "done"
    assert standing_of(child) == "open", "the child is untouched by the parent's verdict"


def test_the_outline_and_the_graph_agree():
    """Two views, one rule. They already share a collapse key for this reason."""
    parent = mk("stand-agree")
    child = mk("stand-agree-child")
    client.post(f"/api/problems/{child}/parents", json={"parent_id": parent})
    outline = {r["id"]: r["standing"] for r in client.get("/api/goals").json()["outline"]}
    graph = {n["id"]: n["standing"] for n in client.get("/api/graph").json()["nodes"]}
    for pid in (parent, child):
        assert outline[pid] == graph[pid] == standing_of(pid)


def test_a_scoped_graph_still_sees_what_blocks_a_node():
    """Standings are computed over the whole chart, then read per node. Computing
    them inside the requested subtree would report a problem as open because the
    subproblem blocking it happened to sit outside the scope."""
    top = mk("stand-scope-top")
    inner = mk("stand-scope-inner")
    client.post(f"/api/problems/{inner}/parents", json={"parent_id": top})
    scoped = {n["id"]: n["standing"]
              for n in client.get(f"/api/graph?root={top}").json()["nodes"]}
    assert scoped[top] == "blocked"


# ---------- focus slots ----------
#
# Scarcity is the mechanic. One slot per pinned domain, keyed by the same
# nearest_pinned the board sections by, so "domain" means one thing in this app.

def slots():
    return {s["domain"]: s for s in client.get("/api/focus").json()["slots"]}


def activate(pid, on=True):
    return client.patch(f"/api/problems/{pid}/active", json={"active": on})


@pytest.fixture(autouse=True)
def _slots_released():
    yield
    for s in client.get("/api/focus").json()["slots"]:
        if s["problem"]:
            client.patch(f"/api/problems/{s['problem']['id']}/active", json={"active": False})
    for n in client.get("/api/graph").json()["nodes"]:
        if n.get("active"):
            client.patch(f"/api/problems/{n['id']}/active", json={"active": False})


def test_an_open_problem_can_take_its_domains_slot():
    dom = mk("slot-domain")
    leaf = mk("slot-leaf")
    client.post(f"/api/problems/{leaf}/parents", json={"parent_id": dom})
    client.put(f"/api/problems/{dom}/pin", json={"pinned": True})
    assert activate(leaf).status_code == 200
    assert slots()["slot-domain"]["problem"]["id"] == leaf
    client.put(f"/api/problems/{dom}/pin", json={"pinned": False})


def test_a_blocked_problem_cannot_be_started():
    """The point of the state model: you do not start something a subproblem is
    still holding up, and the app must not be the one to do it."""
    parent = mk("slot-blocked")
    client.post(f"/api/problems/{mk('slot-blocker')}/parents", json={"parent_id": parent})
    r = activate(parent)
    assert r.status_code == 422
    assert "blocked" in r.json()["detail"]


def test_a_second_focus_in_one_domain_is_refused_by_name():
    """Refused, not swapped — switching what you are working on is exactly the
    moment worth noticing, and the message has to be actionable."""
    dom = mk("slot-one-at-a-time")
    a, b = mk("slot-first"), mk("slot-second")
    for k in (a, b):
        client.post(f"/api/problems/{k}/parents", json={"parent_id": dom})
    client.put(f"/api/problems/{dom}/pin", json={"pinned": True})
    assert activate(a).status_code == 200
    r = activate(b)
    assert r.status_code == 422
    assert "slot-first" in r.json()["detail"], "the occupant must be named"
    client.put(f"/api/problems/{dom}/pin", json={"pinned": False})


def test_releasing_frees_the_slot():
    dom = mk("slot-free")
    a, b = mk("slot-free-a"), mk("slot-free-b")
    for k in (a, b):
        client.post(f"/api/problems/{k}/parents", json={"parent_id": dom})
    client.put(f"/api/problems/{dom}/pin", json={"pinned": True})
    activate(a)
    assert activate(a, False).status_code == 200
    assert activate(b).status_code == 200, "the slot is free once its occupant steps out"
    client.put(f"/api/problems/{dom}/pin", json={"pinned": False})


def test_two_domains_each_get_their_own_slot():
    d1, d2 = mk("slot-dom-1"), mk("slot-dom-2")
    a, b = mk("slot-in-1"), mk("slot-in-2")
    client.post(f"/api/problems/{a}/parents", json={"parent_id": d1})
    client.post(f"/api/problems/{b}/parents", json={"parent_id": d2})
    for d in (d1, d2):
        client.put(f"/api/problems/{d}/pin", json={"pinned": True})
    assert activate(a).status_code == 200
    assert activate(b).status_code == 200, "domains do not contend with each other"
    for d in (d1, d2):
        client.put(f"/api/problems/{d}/pin", json={"pinned": False})


def test_solving_releases_the_slot():
    """A slot is only scarce if finishing gives it back."""
    dom = mk("slot-solve")
    a, b = mk("slot-solve-a"), mk("slot-solve-b")
    for k in (a, b):
        client.post(f"/api/problems/{k}/parents", json={"parent_id": dom})
    client.put(f"/api/problems/{dom}/pin", json={"pinned": True})
    activate(a)
    client.patch(f"/api/problems/{a}/solved", json={"solved": True})
    assert slots()["slot-solve"]["problem"] is None, "a finished focus does not hold a slot"
    assert activate(b).status_code == 200
    client.patch(f"/api/problems/{a}/solved", json={"solved": False})
    client.put(f"/api/problems/{dom}/pin", json={"pinned": False})


def test_solving_something_unrelated_does_not_clear_its_active_flag():
    """`set_solved` writes `active` too, so the un-solve path must preserve it
    rather than blanking a flag it never meant to touch."""
    leaf = mk("slot-preserve")
    activate(leaf)
    client.patch(f"/api/problems/{leaf}/solved", json={"solved": False})
    assert {n["id"]: n["active"] for n in client.get("/api/graph").json()["nodes"]}[leaf] is True


# ---------- upward inheritance (v0.31.1) ----------
#
# Downward answers "what does this goal decompose into". Upward answers "which
# project is this sub-problem part of". Both are `nearest`; only the direction
# differs, and downward wins whenever it finds anything.


def test_a_sub_problem_inherits_the_project_above_it():
    """The bug this cycle fixes. A leaf beneath a project node had no repo below it
    and could not have one of its own — `_repo_owner` gives a repo to exactly one
    problem, and that problem is the project."""
    project = mk("a project", repo="inh-parent")
    leaf = mk("one of its sub-problems", parent_id=project)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, leaf) == ["inh-parent"]
    finally:
        con.close()


def test_downward_still_wins_when_there_is_anything_below():
    """Composition is untouched: a goal offers what it decomposes into, never the
    repo of a bearing above it. If upward ever outranked downward, a bearing's own
    tag would appear in the picker for the projects beneath it."""
    top = mk("bearing with a repo", repo="inh-bearing")
    goal = mk("goal between", parent_id=top)
    mk("project below", repo="inh-below", parent_id=goal)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, goal) == ["inh-below"]
    finally:
        con.close()


def test_inheritance_stops_at_the_nearest_ancestor():
    project = mk("near project", repo="inh-near")
    mid = mk("mid, no repo", parent_id=project)
    leaf = mk("deep leaf", parent_id=mid)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, leaf) == ["inh-near"]
    finally:
        con.close()


def test_a_sibling_of_a_project_inherits_nothing_from_it():
    """Only your own ancestry. A leaf beside a project is not part of it, and
    offering that repo would let abstract work cut a tag in someone else's line."""
    goal = mk("goal over two")
    mk("the project", repo="inh-sibling-proj", parent_id=goal)
    sibling = mk("abstract sibling", parent_id=goal)
    con = db_conn()
    try:
        # The sibling looks up to `goal`, which has no repo of its own; `goal`'s repo
        # comes from looking DOWN at its other child, and that is not inherited across.
        assert chart_mod.nearest_repos(con, sibling) == []
    finally:
        con.close()


def test_a_leaf_with_no_project_anywhere_above_still_offers_nothing():
    goal = mk("abstract all the way up")
    leaf = mk("abstract leaf", parent_id=goal)
    con = db_conn()
    try:
        assert chart_mod.nearest_repos(con, leaf) == []
    finally:
        con.close()
