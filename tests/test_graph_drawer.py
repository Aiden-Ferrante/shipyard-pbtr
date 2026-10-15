"""Clicking a node in the graph opens it beside the chart, not instead of it.

The rule this protects is one line: **a plain click must never leave the chart.**
It is worth a browser test because every cheaper check passes while it is broken —
the drawer is a `fixed` overlay whose absence is invisible to the UI contract, the
production build, and every API test in this suite. The regression it guards is a
one-word edit in `graph.jsx` (`onPick` dropped) or a move of the `Inspector` back
inside the outline's branch in `goals.jsx`, and both look entirely reasonable in a
diff.

It also covers the guardrail from the goal-inspector plan, which is the half that
rots quietly: `#/problem/<id>` stays a working full page and stays linked from
inside the drawer. A drawer that swallows the URL makes a node unshareable, and
nothing else in the repo would notice.

**This skips unless it can really run** — playwright installed, a browser present,
and a frontend build on disk. A skip is not a pass, and the skip reasons say what
is missing:

    make setup                                   # installs playwright the package
    backend/.venv/bin/playwright install chromium  # the browser itself, once
    make prod                                    # or any build, to create frontend/dist
    make test-ui                                 # does all three, then runs this file
"""

from __future__ import annotations

import os
import socket
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "backend"))

_TMP = Path(tempfile.mkdtemp())
DB = _TMP / "chart.sqlite"
# Never let a test write the repo's real chart export —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
EXPORT = _TMP / "chart.md"
# An empty fleet: the scan must not wander into a real ~/Desktop/code and make the
# page's contents depend on whose machine is running the suite.
FLEET = Path(tempfile.mkdtemp())

# These are NOT exported to the environment, deliberately. ARCHITECTURE.md's
# load-bearing boundary: config binds to module constants at import, so tests patch
# the module attribute and never the env var — patching the env has twice caused a
# run to scan or overwrite real data. It is also not local: pytest imports every
# test module before running any of them, so an env var set here would be inherited
# by the modules that `os.environ.setdefault` theirs later in the alphabet, and this
# file's temp paths would quietly become test_repo's and test_survey's.

DIST = ROOT / "frontend" / "dist" / "index.html"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover — environment, not behaviour
    sync_playwright = None

pytestmark = [
    pytest.mark.skipif(sync_playwright is None,
                       reason="playwright not installed — `pip install playwright`"),
    pytest.mark.skipif(not DIST.exists(),
                       reason=f"no frontend build at {DIST} — run `make prod` first"),
]

# A shallow fixture on purpose: the graph opens two levels deep, so a target at
# depth 1 is on the canvas without unfolding anything. Testing the click should not
# require first testing the fold.
ROOT_GOAL = "A fixture bearing"
TARGET = "The node this test clicks"
PROJECT = "fixture-project"
DESCRIPTION = ("Prose long enough to be worth a drawer, and distinctive enough that "
               "finding it on the page proves the drawer rendered this node.")
WAYPOINT = "What would be observed if this fixture were working"
FALSIFIER = "The drawer opens empty"


def _isolate():
    """Point the *app* at this module's fixtures, whatever imported it first.

    Setting SHIPYARD_DB in the environment is not enough and silently was not:
    `app.main` binds DB_PATH, CHART_EXPORT and CODE_ROOT once at import, and
    several test modules set those names, so whichever imports first wins — the
    same trap `test_chart.py::db_conn` documents and ARCHITECTURE.md states as a
    load-bearing boundary. Run alone these tests passed; run in the suite they
    served another module's empty chart and every one of them failed. `db()` reads
    the global at call time, so rebinding here is what actually takes effect.
    Restored by the fixture afterwards.
    """
    import app.main as main_mod
    before = (main_mod.DB_PATH, main_mod.CHART_EXPORT, main_mod.CODE_ROOT)
    main_mod.DB_PATH, main_mod.CHART_EXPORT, main_mod.CODE_ROOT = DB, EXPORT, FLEET
    return main_mod, before


def _seed():
    import app.chart as chart
    con = sqlite3.connect(DB)
    chart.init(con)
    root = chart.create_problem(con, title=ROOT_GOAL, waypoint="a bearing's observable")
    target = chart.create_problem(con, title=TARGET, waypoint=WAYPOINT,
                                  description=DESCRIPTION, falsifier=FALSIFIER,
                                  parent_id=root)
    # A project whose repo attacks the target, so the project page's Problem Chart
    # has a graph to draw. That surface is the reason this fixture exists: it draws
    # the same component with no drawer of its own, and shipped still navigating
    # away while the Chart's copy was fixed.
    chart.link_repo(con, target, PROJECT)
    (FLEET / PROJECT).mkdir(parents=True, exist_ok=True)
    (FLEET / PROJECT / "PROJECT.yaml").write_text(
        f"id: {PROJECT}\nname: Fixture Project\nstage: tool\n"
        "description: A project that exists only for this test.\n")
    # A sibling, so "the drawer showed the node I clicked" is a real claim rather
    # than the only thing it could possibly have shown.
    chart.create_problem(con, title="A sibling nobody clicks",
                         waypoint="another observable", description="Not this one.",
                         parent_id=root)
    con.commit()
    con.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url():
    """The real app on a real port: a browser cannot drive TestClient."""
    main_mod, before = _isolate()
    _seed()
    import uvicorn
    from app.main import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("the app did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    main_mod.DB_PATH, main_mod.CHART_EXPORT, main_mod.CODE_ROOT = before


@pytest.fixture
def page(base_url):
    """A browser on the Chart, in the graph view, with the console watched.

    Console errors are collected and asserted at teardown: a React error boundary
    swallows the failure and leaves a plausible-looking page, so "it rendered" is
    not on its own evidence that it worked.
    """
    with sync_playwright() as p:
        # PLAYWRIGHT_CHROMIUM points at a chrome binary you already have, for
        # machines that will not download playwright's own — CI images that ship a
        # browser, and anyone unwilling to fetch a second copy of Chromium.
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM")
        try:
            browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:  # pragma: no cover — environment, not behaviour
            pytest.skip(f"no chromium available ({e}) — `playwright install chromium`, "
                        f"or set PLAYWRIGHT_CHROMIUM to a chrome binary")
        pg = browser.new_page()
        errors: list[str] = []

        def on_console(m):
            url = (m.location or {}).get("url", "")
            # This repo ships no favicon, and its 404 is not a finding.
            if m.type == "error" and "favicon" not in url:
                errors.append(f"{m.text} @ {url}")

        pg.on("console", on_console)
        pg.on("pageerror", lambda e: errors.append(str(e)))

        pg.goto(f"{base_url}/#/goals")
        # The canvas is the Chart's "ready". It used to be the view tabs, until the
        # outline was removed and the Chart became the graph outright.
        pg.wait_for_selector("g[data-node]", timeout=15_000)
        yield pg
        assert not errors, f"console errors: {errors}"
        browser.close()


def to_graph(pg):
    """On the Chart there is nothing to switch to any more — it is the graph."""
    pg.wait_for_selector("g[data-node]", timeout=15_000)
    return pg.locator("g[data-node]")


def node_index(nodes, text):
    return next((i for i in range(nodes.count())
                 if text[:24] in (nodes.nth(i).text_content() or "")), None)


def click_node(pg, nodes, i):
    nodes.nth(i).click()
    # The handler defers by 220ms so a double-click can still mean "focus".
    pg.wait_for_selector('[role="dialog"]', timeout=5_000)
    return pg.locator('[role="dialog"]')


def test_a_click_opens_the_node_beside_the_chart(page):
    nodes = to_graph(page)
    i = node_index(nodes, TARGET)
    assert i is not None, f"target not drawn; canvas holds {nodes.all_text_contents()}"

    drawer = click_node(page, nodes, i)
    body = drawer.inner_text()
    assert TARGET in body
    assert DESCRIPTION[:40] in body, body
    assert WAYPOINT in body
    assert FALSIFIER in body

    # The whole point: the chart is still there to be read alongside it.
    assert "#/problem/" not in page.url, page.url
    assert "node=" in page.url, page.url
    assert nodes.count() > 0


def test_the_full_page_stays_reachable(page):
    """The goal-inspector plan's guardrail. A drawer that becomes the only way to
    reach a problem makes the node unshareable, and no other check would notice."""
    nodes = to_graph(page)
    drawer = click_node(page, nodes, node_index(nodes, TARGET))
    link = drawer.locator('a[href^="#/problem/"]')
    assert link.count() == 1
    link.click()
    page.wait_for_timeout(400)
    assert "#/problem/" in page.url
    assert page.locator('[role="dialog"]').count() == 0


def test_the_clicked_node_is_marked_on_the_canvas(page):
    """Otherwise the panel and the canvas do not visibly agree about what is open.
    Asserted as a comparison, not a literal width — the number is a design choice
    and may move; "the selected one is drawn more heavily" is the behaviour."""
    nodes = to_graph(page)
    i = node_index(nodes, TARGET)
    other = node_index(nodes, "A sibling nobody clicks")
    click_node(page, nodes, i)

    width = lambda k: float(nodes.nth(k).locator("rect").first.get_attribute("stroke-width"))
    assert width(i) > width(other)


def test_escape_closes_it_and_the_url_follows(page):
    """Selection lives in the URL, so reload reopens the same node and Back closes
    it. State kept only in the component would pass every other assertion here."""
    nodes = to_graph(page)
    click_node(page, nodes, node_index(nodes, TARGET))
    assert "node=" in page.url

    page.keyboard.press("Escape")
    page.wait_for_selector('[role="dialog"]', state="detached", timeout=5_000)
    assert page.url.endswith("#/goals"), page.url


def test_reload_reopens_the_same_node(page):
    nodes = to_graph(page)
    click_node(page, nodes, node_index(nodes, TARGET))
    url = page.url

    page.reload()
    page.wait_for_selector('[role="dialog"]', timeout=15_000)
    assert TARGET in page.locator('[role="dialog"]').inner_text()
    assert page.url == url


def test_the_project_pages_graph_opens_it_too(page, base_url):
    """The bug this file did not catch the first time.

    The Chart passes `onPick` and owns a drawer; the project page's Problem Chart
    passes nothing, and the fallback was to navigate — so the same click meant two
    different things depending on which page you were on. Every assertion below
    passed on the Chart while this surface was still leaving the page.
    """
    page.goto(f"{base_url}/#/project/{PROJECT}")
    page.get_by_role("tab", name="Problem Chart").click()
    page.wait_for_selector("g[data-node]", timeout=15_000)

    nodes = page.locator("g[data-node]")
    i = node_index(nodes, TARGET)
    assert i is not None, f"target not drawn; canvas holds {nodes.all_text_contents()}"

    drawer = click_node(page, nodes, i)
    # Fetched, not handed over: /api/graph is a layout payload and carries no prose,
    # so an empty drawer here would mean the fetch never happened.
    page.wait_for_selector(f'[role="dialog"] :text("{DESCRIPTION[:40]}")', timeout=5_000)
    assert WAYPOINT in drawer.inner_text()
    assert "#/problem/" not in page.url, page.url
    assert f"#/project/{PROJECT}" in page.url, page.url


def test_the_project_chart_can_still_be_authored(page, base_url):
    """What the outline used to be for, after the outline was deleted.

    There were two drawings of this subtree — a canvas and a row list — and only the
    rows could be typed into. Deleting the outline is the right call exactly once the
    canvas can do what it did, so this asserts the three things that came across with
    it and would otherwise vanish in a diff that only *looks* like a layout change:
    rename, decompose, and the cycle link. The old version of this test opened a
    drawer from the outline; this one opens the same drawer from the canvas and
    checks it is not read-only.
    """
    page.goto(f"{base_url}/#/project/{PROJECT}")
    page.get_by_role("tab", name="Problem Chart").click()
    page.wait_for_selector("g[data-node]", timeout=15_000)

    nodes = page.locator("g[data-node]")
    drawer = click_node(page, nodes, node_index(nodes, TARGET))
    page.wait_for_selector(f'[role="dialog"] :text("{DESCRIPTION[:40]}")', timeout=5_000)

    # Rename — an input, because there is no row left to click into.
    assert drawer.get_by_label(f"rename {TARGET}").count() == 1
    text = drawer.inner_text()
    # Decomposition, the motion the chart tab exists for.
    assert "add a problem beneath" in text
    # And the one thing a graph cannot express, which is why it moved here rather
    # than going with the rows: which cycle ran against this problem.
    page.wait_for_selector('[role="dialog"] :text("Addressed by")', timeout=5_000)
    assert f"#/project/{PROJECT}" in page.url, page.url


def test_the_drawer_carries_the_authoring_surface(page):
    """Replaces `test_the_outline_still_opens_the_same_drawer`, whose subject is
    gone: the Chart's outline was removed, so there are no rows to click.

    What that test really protected was that a node stays reachable and editable
    without leaving the chart. With the rows gone the drawer is the ONLY place
    left to rename, decompose or delete a problem — so if it opens read-only, the
    Chart has quietly become unauthorable and nothing else in this suite notices.
    """
    nodes = to_graph(page)
    drawer = click_node(page, nodes, node_index(nodes, TARGET))

    assert drawer.locator('input[aria-label^="rename"]').count() == 1, "no rename field"
    body = drawer.inner_text()
    for control in ("add a problem beneath", "delete…", "Serves"):
        assert control in body, f"{control!r} missing from the drawer:\n{body}"
    assert "#/problem/" not in page.url, page.url


def test_folding_is_a_plain_click_on_the_node(page):
    """Folding used to be ⌥click and a badge that only appeared once something was
    already folded — an affordance for unfolding, none for folding, and neither
    findable without reading the legend.

    The regression this guards is subtle and would look fine in a screenshot: the
    control renders, and the click reaches the NODE instead of the control, so
    folding a branch also opens the drawer. That is why both halves are asserted.
    """
    nodes = to_graph(page)
    before = nodes.count()

    fold = page.locator("g[data-node] g").filter(
        has=page.locator("title", has_text="fold ")).first
    fold.wait_for(timeout=5_000)
    fold.click()

    page.wait_for_function(f"document.querySelectorAll('g[data-node]').length < {before}",
                           timeout=5_000)
    assert page.locator('[role="dialog"]').count() == 0, "folding opened the drawer"

    # And back: the badge counting what is hidden is the way in again.
    unfold = page.locator("g[data-node] g").filter(
        has=page.locator("title", has_text="unfold")).first
    unfold.click()
    page.wait_for_function(f"document.querySelectorAll('g[data-node]').length == {before}",
                           timeout=5_000)


def _cursor(pg):
    """Whichever node the dashed keyboard ring is on, by title."""
    ring = pg.locator("g[data-node]").filter(has=pg.locator("rect[stroke-dasharray]"))
    return ring.first.locator("text").first.text_content() if ring.count() else None


def test_the_chart_can_be_navigated_from_the_keyboard(page):
    """A canvas is the one shape that loses this for free.

    An outline gets arrow keys because rows ARE a list; a diagram has to be told what
    "next" means, and getting it wrong is invisible in a screenshot. So the two axes
    are asserted separately: ↑/↓ walk the drawn order, and →/← are structural —
    right unfolds then descends, left folds then climbs.

    Enter is asserted too, because the cursor deliberately does NOT open anything.
    That is the whole reason it is a separate ring from the selection, and a
    "simplification" that merged them would pass every other assertion here.
    """
    page.wait_for_selector("g[data-node]", timeout=15_000)

    # The first press only places the ring — it continues the mouse's thought rather
    # than teleporting to the top.
    page.keyboard.press("ArrowDown")
    first = _cursor(page)
    assert first is not None, "no cursor after the first arrow key"

    page.keyboard.press("ArrowDown")
    assert _cursor(page) != first, "↓ did not move the cursor"
    page.keyboard.press("ArrowUp")
    assert _cursor(page) == first, "↑ did not come back"

    # Walk to the one node with children. The fixture is deliberately shallow, so
    # nothing starts folded — ← has to create that state before → can undo it.
    for _ in range(6):
        if _cursor(page) == ROOT_GOAL:
            break
        page.keyboard.press("ArrowDown")
    assert _cursor(page) == ROOT_GOAL, "never reached the branch by arrowing"

    # Structural, both directions, with the node count as the proof.
    whole = page.locator("g[data-node]").count()
    page.keyboard.press("ArrowLeft")           # an open branch folds
    page.wait_for_function(
        f"document.querySelectorAll('g[data-node]').length < {whole}", timeout=5_000)
    assert _cursor(page) == ROOT_GOAL, "folding moved the cursor off the branch"

    page.keyboard.press("ArrowRight")          # ...and unfolds again
    page.wait_for_function(
        f"document.querySelectorAll('g[data-node]').length == {whole}", timeout=5_000)

    page.keyboard.press("ArrowRight")          # ...then steps into it
    child = _cursor(page)
    assert child != ROOT_GOAL, "→ did not descend into the branch it opened"

    page.keyboard.press("ArrowLeft")           # ...and back out to what it serves
    assert _cursor(page) == ROOT_GOAL, "← did not climb to the parent"
    parent = ROOT_GOAL

    # Arrowing across the chart must not have opened anything.
    assert page.locator('[role="dialog"]').count() == 0, "the cursor opened a drawer"
    page.keyboard.press("Enter")
    page.wait_for_selector('[role="dialog"]', timeout=5_000)
    assert parent[:20] in page.locator('[role="dialog"]').inner_text()


def test_search_is_reachable_while_the_chart_fills_the_window(page):
    """The regression that arrived WITH fullscreen.

    The query box lived in the goals page header, so the moment the canvas could
    cover the window it went behind the layer — fullscreen being exactly when finding
    a node matters most. `elementFromPoint` is the assertion rather than visibility,
    because the input was still 'visible' by every ordinary measure: correct size,
    on-screen coordinates, not display:none. It was simply underneath.
    """
    page.wait_for_selector("g[data-node]", timeout=15_000)
    page.get_by_role("button", name="⤢ Fullscreen").click()

    box = page.get_by_label("search the chart")
    box.wait_for(timeout=5_000)
    on_top = page.evaluate(
        """() => { const s = document.querySelector('input[aria-label="search the chart"]');
                   const r = s.getBoundingClientRect();
                   return document.elementFromPoint(r.left + 10, r.top + 8) === s }""")
    assert on_top, "the search box is covered by the fullscreen canvas"

    # And `/` reaches it without the mouse.
    box.blur()
    page.keyboard.press("/")
    assert page.evaluate(
        """() => document.activeElement?.getAttribute('aria-label')""") == "search the chart"


def test_a_node_can_be_created_from_the_canvas(page, base_url):
    """The canvas was read-only, so the chart could only grow from somewhere else.

    Guarded in the browser rather than by an API test because POST /api/problems was
    never the broken part: the failure was that nothing on the page called it, and
    then that the node it made was born inside a fold and never drawn. This clicks
    the control, types, and looks for the new node ON THE CANVAS.
    """
    made = "A node made from the canvas"
    to_graph(page)
    page.get_by_role("button", name="＋ New problem").click()
    page.get_by_placeholder("the problem").fill(made)
    page.get_by_placeholder("the problem").press("Enter")

    page.wait_for_selector(f'g[data-node] :text("{made}")', timeout=10_000)
    assert page.locator("g[data-node]").filter(has_text=made).count() >= 1


def test_the_composer_stays_open_so_a_branch_can_be_typed_in_one_pass(page):
    """The motion the outline did for free and its deletion cost.

    A form that closes on submit assumes you came to make one thing, and nobody
    decomposes one thing — breaking a problem into three subproblems was three trips
    through the toolbar. Enter adds another in the same place; Shift-Enter adds one
    and descends into it. Both are asserted because they differ only in which parent
    the next add lands under, which is exactly the kind of thing that silently
    regresses to "they both do the same".
    """
    to_graph(page)
    page.get_by_role("button", name="＋ New problem").click()
    field = page.get_by_placeholder("the problem")

    field.fill("Sibling one")
    field.press("Enter")
    # Still open, cleared, and saying what it made — the three halves of "keep going".
    page.wait_for_selector(':text("Sibling one")', timeout=10_000)
    assert field.input_value() == "", "the composer did not clear for the next one"

    field.fill("Sibling two")
    field.press("Enter")
    page.wait_for_selector(':text("Sibling two")', timeout=10_000)
    # Both siblings, so the second did not land under the first.
    assert page.get_by_placeholder("the problem").count() == 1, "composer closed"

    field.fill("A child of sibling two")
    field.press("Shift+Enter")
    # Descending re-aims the composer, and says so without waiting for a refetch.
    page.wait_for_selector(':text("Beneath A child of sibling two")', timeout=10_000)
