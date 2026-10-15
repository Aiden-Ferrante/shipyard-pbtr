"""The board is the chart: roots are sections, projects and ghosts sit beneath.

The guardrail with the most teeth is that nothing on disk ever silently vanishes.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "board.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def rm(pid, **params):
    """Delete through the sanctioned path: read the impact, pass its token (v0.35.0)."""
    imp = client.get(f"/api/problems/{pid}/deletion")
    if imp.status_code != 200:
        return client.delete(f"/api/problems/{pid}", params=params)
    return client.delete(f"/api/problems/{pid}", params={**params, "token": imp.json()["token"]})


def mk(title, **kw):
    r = client.post("/api/problems",
                    json={"title": title, "waypoint": "observable", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_roots_become_sections():
    root = mk("Board root A")
    mk("Under A", parent_id=root)
    ids = [s["id"] for s in client.get("/api/board").json()["sections"]]
    assert root in ids


def test_a_problem_with_a_parent_is_not_a_section():
    root = mk("Board root B")
    child = mk("Child of B", parent_id=root)
    ids = [s["id"] for s in client.get("/api/board").json()["sections"]]
    assert child not in ids


def test_problem_without_a_repo_is_a_ghost():
    root = mk("Ghost root")
    mk("Never attacked", parent_id=root)
    sec = next(s for s in client.get("/api/board").json()["sections"] if s["id"] == root)
    ghost = next(c for c in sec["cards"] if c["title"] == "Never attacked")
    assert ghost["ghost"] is True
    # A ghost must not wear a project's clothes.
    assert "last_activity" not in ghost and "open_tasks" not in ghost


def test_linking_a_repo_promotes_a_ghost_to_a_project():
    root = mk("Promote root")
    p = mk("Becomes real", parent_id=root)
    r = client.put(f"/api/problems/{p}/repo", json={"repo": "shipyard"})
    assert r.status_code == 200

    sec = next(s for s in client.get("/api/board").json()["sections"] if s["id"] == root)
    card = next(c for c in sec["cards"] if c["problem_id"] == p)
    assert card["ghost"] is False
    assert card["id"] == "shipyard"
    assert "cycles" in card and "last_activity" in card

    client.put(f"/api/problems/{p}/repo", json={"repo": None})  # restore


def test_unknown_repo_cannot_be_linked():
    p = mk("Wants a fake repo")
    assert client.put(f"/api/problems/{p}/repo",
                      json={"repo": "no-such-repo"}).status_code == 404


def test_a_repo_cannot_be_linked_twice():
    a, b = mk("First claim"), mk("Second claim")
    assert client.put(f"/api/problems/{a}/repo", json={"repo": "shipyard"}).status_code == 200
    assert client.put(f"/api/problems/{b}/repo", json={"repo": "shipyard"}).status_code == 422
    client.put(f"/api/problems/{a}/repo", json={"repo": None})


def test_uncharted_projects_still_appear():
    """Nothing on disk may silently vanish from the board."""
    body = client.get("/api/board").json()
    assert any(p["id"] == "shipyard" for p in body["uncharted"])


def test_reparent_replaces_the_edge():
    a, b = mk("Bearing one"), mk("Bearing two")
    c = mk("Moves house", parent_id=a)
    assert client.put(f"/api/problems/{c}/parent",
                      json={"parent_id": b}).status_code == 200
    spine = client.get(f"/api/chart/{c}").json()
    assert [p["title"] for p in spine["parents"]] == ["Bearing two"]


def test_reparent_to_null_makes_a_root():
    a = mk("Temp bearing")
    c = mk("Set free", parent_id=a)
    client.put(f"/api/problems/{c}/parent", json={"parent_id": None})
    assert c in [s["id"] for s in client.get("/api/board").json()["sections"]]


def test_reparent_refuses_a_loop():
    a = mk("Loop top")
    b = mk("Loop middle", parent_id=a)
    r = client.put(f"/api/problems/{a}/parent", json={"parent_id": b})
    assert r.status_code == 422
    assert "loop" in r.json()["detail"]


def test_unlinked_lists_only_free_repos():
    p = mk("Claims csv-profiler")
    client.put(f"/api/problems/{p}/repo", json={"repo": "csv-profiler"})
    repos = [r["id"] for r in client.get("/api/unlinked").json()["repos"]]
    assert "csv-profiler" not in repos, "a linked repo is not on offer"
    assert "shipyard" in repos
    client.put(f"/api/problems/{p}/repo", json={"repo": None})


def test_board_shows_direct_children_only():
    """Deeper decomposition belongs in the project's chart, not on the board."""
    root = mk("Depth root")
    mid = mk("Direct child", parent_id=root)
    mk("Grandchild", parent_id=mid)
    sec = next(s for s in client.get("/api/board").json()["sections"] if s["id"] == root)
    titles = [c["title"] for c in sec["cards"]]
    assert titles == ["Direct child"]
    assert next(c for c in sec["cards"] if c["title"] == "Direct child")["child_count"] == 1


def test_a_card_appears_once_across_sections():
    """Two bearings, one card — otherwise the board is a hall of mirrors."""
    a, b = mk("Bearing left"), mk("Bearing right")
    shared = mk("Serves both", parent_id=a)
    client.post(f"/api/problems/{shared}/parents", json={"parent_id": b})

    secs = client.get("/api/board").json()["sections"]
    hits = [s["title"] for s in secs if any(c["problem_id"] == shared for c in s["cards"])]
    assert len(hits) == 1, f"card rendered in {hits}"

    card = next(c for s in secs for c in s["cards"] if c["problem_id"] == shared)
    assert card["also_serves"], "the other bearing must still be named on the card"


# ---------- pinned sections ----------
#
# These share one sqlite with every other test module (each sets SHIPYARD_DB at
# import time and the first import wins), so they use repo ids nothing else claims
# and hand every pin back afterwards. A leaked pin switches the whole board into
# pinned mode and takes unrelated tests down with it.

@pytest.fixture(autouse=True)
def _pins_returned():
    yield
    for s in client.get("/api/board").json()["sections"]:
        if s.get("pinned"):
            client.put(f"/api/problems/{s['id']}/pin", json={"pinned": False})


def pin(pid, on=True):
    assert client.put(f"/api/problems/{pid}/pin",
                      json={"pinned": on}).status_code == 200


def under(child, parent):
    assert client.post(f"/api/problems/{child}/parents",
                       json={"parent_id": parent}).status_code == 200


def sections_by_title():
    return {s["title"]: s for s in client.get("/api/board").json()["sections"]}


def test_without_pins_the_board_still_sections_by_root():
    """The fallback has to hold: a chart nobody has pinned is not a blank board."""
    root = mk("pin-fallback root")
    under(mk("pin-fallback child"), root)
    assert "pin-fallback root" in sections_by_title()


def test_a_pinned_goal_becomes_the_heading_instead_of_the_root():
    """One root and fifty descendants is what a useful chart looks like, and
    sectioning by root collapses that into a single column."""
    root, domain = mk("pin-life"), mk("pin-domain")
    under(domain, root)
    pin(domain)
    titles = sections_by_title()
    assert "pin-domain" in titles
    assert "pin-life" not in titles, "pins replace roots as headings, they do not add to them"


def test_a_project_lands_under_its_nearest_pinned_ancestor():
    """A pin can sit several levels above the work, so a section gathers its whole
    subtree rather than only direct children."""
    root, domain, mid = mk("pin-r2"), mk("pin-d2"), mk("pin-m2")
    deep = mk("pin-deep project", repo="pin-fixture-alpha")
    under(domain, root)
    under(mid, domain)
    under(deep, mid)
    pin(domain)
    cards = {c["title"]: c for c in sections_by_title()["pin-d2"]["cards"]}
    assert "pin-deep project" in cards, "a project three levels down still belongs here"
    # Direct children stay listed, so a section still shows what has been decomposed
    # but not yet attacked. Deeper undecomposed problems are the project's business.
    assert "pin-m2" in cards


def test_the_nearest_pin_wins_when_two_are_above():
    """A problem serving two pinned goals belongs to the closer one, not to
    whichever the walk happened to reach first."""
    far, near, mid = mk("pin-far"), mk("pin-near"), mk("pin-between")
    proj = mk("pin-shared project", repo="pin-fixture-beta")
    under(near, far)
    under(mid, near)
    under(proj, mid)      # two pins above it: near at distance 2, far at distance 3
    pin(far)
    pin(near)
    titles = sections_by_title()
    assert "pin-shared project" in [c["title"] for c in titles["pin-near"]["cards"]]
    assert "pin-shared project" not in [c["title"] for c in titles["pin-far"]["cards"]], \
        "a project belongs to the closer pin, and to exactly one section"


def test_pinning_changes_no_structure():
    """It is a decision about looking, so the chart must read identically after."""
    root = mk("pin-structural")
    under(mk("pin-structural child"), root)
    before = client.get(f"/api/chart/{root}").json()["children"]
    pin(root)
    pin(root, False)
    assert client.get(f"/api/chart/{root}").json()["children"] == before


def test_pinning_something_that_does_not_exist_is_refused():
    assert client.put("/api/problems/nope/pin", json={"pinned": True}).status_code == 422


def edge_count():
    """Edges, read straight from the table the app is actually bound to.

    Not via os.environ — several test modules set SHIPYARD_DB and the app binds
    DB_PATH once at import, so whichever imported first wins."""
    import sqlite3

    import app.main as main_mod
    con = sqlite3.connect(main_mod.DB_PATH)
    try:
        return con.execute("SELECT COUNT(*) FROM problem_edges").fetchone()[0]
    finally:
        con.close()


def test_removing_a_group_keeps_every_project():
    """The guardrail with teeth for board group management.

    "Remove this group" is unpinning, and unpinning is a decision about *looking*.
    If it ever costs an edge, a project has silently lost its place in the chart —
    which is the one failure this feature is not allowed to have.
    """
    domain = mk("ungroup-domain")
    proj = mk("ungroup-project", repo="ungroup-fixture")
    under(domain, mk("ungroup-root"))
    under(proj, domain)
    pin(domain)
    assert "ungroup-domain" in sections_by_title(), "precondition: it heads a group"

    before = edge_count()
    assert before > 0, "an edge count of zero would let this pass without checking anything"
    pin(domain, False)
    assert edge_count() == before, "removing a group must not cost a single edge"

    # And the project is still reachable: it kept its bearing, it merely lost a heading.
    assert domain in [p["id"] for p in client.get(f"/api/chart/{proj}").json()["parents"]]


def on_board(title):
    """Everywhere a project can legitimately appear. Sections, ungrouped, uncharted."""
    b = client.get("/api/board").json()
    return (title in [c["title"] for s in b["sections"] for c in s["cards"]]
            or title in [c["title"] for c in b["ungrouped"]]
            or title in [p.get("name") for p in b["uncharted"]])


def test_removing_a_group_does_not_hide_its_projects():
    """The edge count surviving is not enough — the *board* has to keep showing them.

    Unpinning a heading leaves its projects with no pinned ancestor, and the section
    rule placed a card only under its nearest pin. So they were dropped: on the chart,
    off the board, no message. Four vanished this way the first time it was tried.
    """
    other = mk("hide-other")
    domain = mk("hide-domain")
    proj = mk("hide-project", repo="hide-fixture")
    under(domain, mk("hide-root"))
    under(proj, domain)
    pin(domain)
    pin(other)                       # keeps the board in pinned mode after the removal
    assert on_board("hide-project")

    pin(domain, False)
    assert on_board("hide-project"), \
        "a project with no heading left must still appear — silently absent is the one failure"


def test_an_ungrouped_project_can_still_be_dragged_into_a_group():
    """Ungrouped is a way station, not a hole: the card carries the id the board
    reparents by, so dropping it on a section is the way back."""
    home = mk("way-home")
    proj = mk("way-project", repo="way-fixture")
    under(proj, mk("way-orphan-parent"))
    pin(home)
    card = next(c for c in client.get("/api/board").json()["ungrouped"]
                if c["title"] == "way-project")
    assert card["problem_id"] == proj

    assert client.put(f"/api/problems/{proj}/parent",
                      json={"parent_id": home}).status_code == 200
    assert "way-project" in [c["title"] for s in client.get("/api/board").json()["sections"]
                             if s["id"] == home for c in s["cards"]]


def test_deleting_a_middle_folder_keeps_the_project_in_its_group():
    """`delete_problem` promotes children to the grandparent, so a project whose
    immediate parent goes away keeps the heading above it. Better than falling to
    ungrouped, and the reason ungrouped stays small."""
    home = mk("orphan-home")
    folder = mk("orphan-folder")
    proj = mk("orphan-project", repo="orphan-fixture")
    under(folder, home)
    under(proj, folder)
    pin(home)

    assert rm(folder).status_code == 200
    assert "orphan-project" in [c["title"] for s in client.get("/api/board").json()["sections"]
                                if s["id"] == home for c in s["cards"]]


def test_a_project_whose_last_parent_is_deleted_falls_back_to_ungrouped():
    """And when there is no grandparent to be promoted to, it lands in ungrouped —
    never nowhere. This is the route that used to drop a card off the board."""
    keep = mk("lone-keeps-pinned-mode")
    folder = mk("lone-folder")
    proj = mk("lone-project", repo="lone-fixture")
    under(proj, folder)             # folder is a root: nothing above it to inherit
    pin(keep)

    assert rm(folder).status_code == 200
    assert "lone-project" in [c["title"] for c in client.get("/api/board").json()["ungrouped"]]


def test_a_project_detached_from_its_parent_falls_back_to_ungrouped():
    """The same thing by the other route: dragged out rather than orphaned."""
    home = mk("detach-home")
    proj = mk("detach-project", repo="detach-fixture")
    under(proj, home)
    pin(home)
    assert client.put(f"/api/problems/{proj}/parent", json={"parent_id": None}).status_code == 200
    assert "detach-project" in [c["title"] for c in client.get("/api/board").json()["ungrouped"]]


# ---------- shelving ----------
#
# A shelved repo is the ONE thing shipyard chooses not to show, so these tests
# guard the two halves of that bargain: it really disappears from the board, and
# it is never gone quietly.

@pytest.fixture
def fake_code_root(tmp_path, monkeypatch):
    """A code root of our own.

    Patches the module attribute, never the env var: config is bound to module
    constants at import and whichever test file imports `app.main` first wins, so
    setting SHIPYARD_CODE_ROOT here would silently scan the real ~/Desktop/code.
    That exact bug shipped twice.
    """
    import app.main as main_mod
    for name in ("shelf-one", "shelf-two"):
        d = tmp_path / name
        d.mkdir()
        (d / "PROJECT.yaml").write_text(f"id: {name}\nname: {name}\nstage: spike\n")
    monkeypatch.setattr(main_mod, "CODE_ROOT", tmp_path)
    yield tmp_path
    client.delete("/api/shelved/shelf-one")
    client.delete("/api/shelved/shelf-two")


def board_repo_ids():
    b = client.get("/api/board").json()
    return ({c.get("id") for s in b["sections"] for c in s["cards"]}
            | {c.get("id") for c in b["ungrouped"]}
            | {p["id"] for p in b["uncharted"]})


def test_shelving_takes_a_project_off_every_pile(fake_code_root):
    assert "shelf-one" in board_repo_ids()
    assert client.post("/api/shelved", json={"repo": "shelf-one"}).status_code == 200
    assert "shelf-one" not in board_repo_ids(), "shelved means off the board, everywhere"
    assert "shelf-two" in board_repo_ids(), "and only the one you shelved"


def test_a_shelved_project_is_never_silently_gone(fake_code_root):
    client.post("/api/shelved", json={"repo": "shelf-one"})
    b = client.get("/api/board").json()
    assert [s["repo"] for s in b["shelved"]] == ["shelf-one"], \
        "the count rides on every board response — that is what makes hiding honest"


def test_shelving_a_charted_project_does_not_make_it_a_ghost(fake_code_root):
    """The subtle failure: filtering the manifest alone leaves the problem node, and
    a missing manifest reads as `ghost` — 'decomposed but never attacked'. That is a
    different claim about the work, and a false one."""
    home = mk("shelf-home")
    proj = mk("shelf-charted", repo="shelf-one")
    under(proj, home)
    pin(home)
    client.post("/api/shelved", json={"repo": "shelf-one"})
    titles = [c["title"] for s in client.get("/api/board").json()["sections"] for c in s["cards"]]
    assert "shelf-charted" not in titles


def test_shelving_touches_no_files_and_no_chart(fake_code_root):
    # shelf-two, not shelf-one: the test above already charted shelf-one, and one repo
    # is attacked by exactly one problem. The chart is not reset between tests.
    proj = mk("shelf-keeps-node", repo="shelf-two")
    before = edge_count()
    client.post("/api/shelved", json={"repo": "shelf-two"})
    assert (fake_code_root / "shelf-two" / "PROJECT.yaml").is_file(), "files are never touched"
    assert client.get(f"/api/chart/{proj}").json()["node"]["repo"] == "shelf-two", \
        "the chart node keeps its repo — what it lost is a card, not its reasoning"
    assert edge_count() == before


def test_restoring_puts_it_back(fake_code_root):
    client.post("/api/shelved", json={"repo": "shelf-one"})
    assert "shelf-one" not in board_repo_ids()
    assert client.delete("/api/shelved/shelf-one").status_code == 200
    assert "shelf-one" in board_repo_ids()


def test_restore_is_idempotent(fake_code_root):
    """The way back must never be able to fail."""
    assert client.delete("/api/shelved/never-shelved").status_code == 200


def test_shelving_a_repo_that_does_not_exist_is_refused(fake_code_root):
    assert client.post("/api/shelved", json={"repo": "nope"}).status_code == 404


def test_fleet_still_lists_a_shelved_project(fake_code_root):
    """Shelving is about the board. Fleet is where a repo rotting with unpushed work
    gets caught, and opting out of that is not a view preference."""
    client.post("/api/shelved", json={"repo": "shelf-one"})
    projects = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert "shelf-one" in projects
    assert projects["shelf-one"]["shelved"] is True
    assert projects["shelf-two"]["shelved"] is False
