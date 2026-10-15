"""The chart never opens at a size you cannot read.

The rule is one line: **fitting the whole tree must never win over legibility.**

It needs a browser because it is a claim about rendered pixels. The zoom is chosen
from a measured frame, the type sizes come from the tier table, and the thing that
matters is their product — so every cheaper check passes while the chart is a grey
texture. Measured before the floor existed, a 64-node chart fitted at k=0.27 and
drew every label between 2.7 and 3.8 real pixels.

The regression is a one-line edit that looks like a simplification:

    setView({ x: 12, y: 12, k: fitK(tree, box) })      # now
    setView({ x: 12, y: 12, k: Math.max(0.25, k) })    # what it replaced

Nothing else in the repo would notice. The nodes are all still drawn, the DOM is
identical, the API tests pass, and the screenshot looks like a chart.

Asserted as rendered pixels rather than against MIN_LEGIBLE_K. The constant is a
design choice and may move; "a label you can read" is the behaviour, and a test
that imports the constant would pass just as happily if someone set it to 0.05.

WHICH TEST GUARDS WHAT, established by planting each regression and watching:

  Expand all / Fit    guard the floor. Restoring `Math.max(0.25, raw)` in fitK
                      fails both, at 2.5px labels and 25% zoom.
  the opening view    guards the OUTLINE's seeding, not the graph's. On the Chart,
                      goals.jsx folds every branch on a first visit above
                      COLLAPSE_ABOVE=20 rows, writing the collapse key both views
                      share — so GraphPage's own `seedCollapse` sees a non-empty
                      set and returns early. It never runs here. Breaking it
                      changes nothing on this page, which is why planting that
                      regression failed no test.

That last line is a finding, not a caveat: `seedCollapse` is reachable only where
no outline has seeded first — a project page's scoped graph, or a chart under the
outline's threshold. The opening view of the Chart is the outline's decision.

**This skips unless it can really run** — playwright installed, a browser present,
and a frontend build on disk. A skip is not a pass:

    make setup                                     # installs playwright the package
    backend/.venv/bin/playwright install chromium  # the browser itself, once
    make prod                                      # or any build, to create frontend/dist
    make test-ui                                   # does all three, then runs the ui tests
"""

from __future__ import annotations

import contextlib
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_TMP = Path(tempfile.mkdtemp())
DB = _TMP / "chart.sqlite"
# Never let a test write the repo's real chart export — on 2026-08-06 they
# overwrote docs/chart.md with test fixtures.
EXPORT = _TMP / "chart.md"
FLEET = Path(tempfile.mkdtemp())

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

# Big enough that fitting it all would have to go under the floor, which is the
# only condition under which this test can fail. Three bearings of sixteen leaves
# is ~48 rows at 34px plus gaps — over 2000px of tree in a frame of roughly 590,
# so an unclamped fit lands near k=0.25. A shallow fixture would pass no matter
# what the code did.
BEARINGS = 3
LEAVES_EACH = 16
TOTAL = 1 + BEARINGS + BEARINGS * LEAVES_EACH

# What the floor is for. At k=0.70 the smallest type in the tier table — 10px on a
# depth-1 subtitle — renders at 7px, and the deepest titles at 8. Six is under both
# and far above the 2.7 an unclamped fit produced, so this separates the two states
# without pinning either number.
READABLE_PX = 6.0


def _isolate():
    """Point the *app* at this module's fixtures, whatever imported it first.

    `app.main` binds DB_PATH, CHART_EXPORT and CODE_ROOT once at import and several
    test modules set those names, so patching the environment does nothing and
    silently scans real data. ARCHITECTURE.md states this as a load-bearing
    boundary; `db()` reads the global at call time, so rebinding is what takes
    effect. Restored by the fixture afterwards.
    """
    import app.main as main_mod
    before = (main_mod.DB_PATH, main_mod.CHART_EXPORT, main_mod.CODE_ROOT)
    main_mod.DB_PATH, main_mod.CHART_EXPORT, main_mod.CODE_ROOT = DB, EXPORT, FLEET
    return main_mod, before


def _seed():
    import app.chart as chart
    con = sqlite3.connect(DB)
    chart.init(con)
    root = chart.create_problem(con, title="A tall fixture bearing",
                                waypoint="the bearing is observable")
    for b in range(BEARINGS):
        branch = chart.create_problem(con, title=f"Branch {b}",
                                      waypoint=f"branch {b} is observable",
                                      parent_id=root)
        for leaf in range(LEAVES_EACH):
            chart.create_problem(con, title=f"Leaf {b}-{leaf}",
                                 waypoint=f"leaf {b}-{leaf} is observable",
                                 parent_id=branch)
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


@contextlib.contextmanager
def _open(base_url, viewport=None):
    """A fresh browser on the graph view, with the console watched.

    Fresh matters more here than elsewhere: the fold state lives in localStorage
    and is shared with the outline, so a reused profile would skip the seeding
    this file is partly about. A new context each test starts with none — and the
    viewport has to be set at creation for the same reason, since resizing after
    the seeding has already run would prove nothing about what it chose.
    """
    with sync_playwright() as p:
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM")
        try:
            browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:  # pragma: no cover — environment, not behaviour
            pytest.skip(f"no chromium available ({e}) — `playwright install chromium`, "
                        f"or set PLAYWRIGHT_CHROMIUM to a chrome binary")
        pg = browser.new_page(viewport=viewport) if viewport else browser.new_page()
        errors: list[str] = []

        def on_console(m):
            url = (m.location or {}).get("url", "")
            if m.type == "error" and "favicon" not in url:
                errors.append(f"{m.text} @ {url}")

        pg.on("console", on_console)
        pg.on("pageerror", lambda e: errors.append(str(e)))

        # No tab to click: the Chart is the graph now. The outline was removed, and
        # with it the view switcher these tests used to drive.
        pg.goto(f"{base_url}/#/goals")
        pg.wait_for_selector("g[data-node]", timeout=15_000)
        yield pg
        assert not errors, f"console errors: {errors}"
        browser.close()


@pytest.fixture
def page(base_url):
    with _open(base_url) as pg:
        yield pg


@pytest.fixture
def tall_page(base_url):
    """A viewport deep enough that the whole fixture fits above the floor.

    This is the only condition under which the two seedings visibly disagree, and
    therefore the only way to assert which one is in charge.
    """
    with _open(base_url, {"width": 1400, "height": 2000}) as pg:
        yield pg


_MEASURE = """() => {
  const svg = document.querySelector('svg[aria-label*="goals"]');
  const g = svg.querySelector('g');
  const k = parseFloat((/scale\\(([\\d.]+)\\)/.exec(g.getAttribute('transform')) || [0, 1])[1]);
  const texts = [...svg.querySelectorAll('text')];
  const sizes = texts.map(t => parseFloat(getComputedStyle(t).fontSize) * k);
  return {
    zoom: k,
    nodes: svg.querySelectorAll('g[data-node]').length,
    smallest: sizes.length ? Math.min(...sizes) : null,
    labels: sizes.length,
  };
}"""


def measure(pg):
    """Zoom, node count and the smallest label as it actually lands on screen.

    The product is the point. Either number alone is satisfiable while the chart is
    unreadable — a large zoom on tiny type, or big type at 27%.
    """
    return pg.evaluate(_MEASURE)


def test_the_chart_opens_at_a_readable_size(page):
    m = measure(page)
    assert m["labels"] > 0, "no text drawn at all, so nothing was measured"
    assert m["smallest"] >= READABLE_PX, (
        f"opened with {m['smallest']:.1f}px labels at {m['zoom'] * 100:.0f}% zoom — "
        f"fitting the tree won over reading it")


def test_a_tall_chart_opens_folded_rather_than_shrunk(page):
    """The choice the app makes on arrival, stated as a claim.

    Legible-because-small is not the property; this fixture is deliberately too
    tall to show at once, so the only way to open readable is to fold. Without this
    the test above would pass on a chart that simply fits.

    Deliberately silent about WHICH seeding folded it. On the Chart that is
    goals.jsx (see the module docstring); on a graph with no outline beside it, it
    is seedCollapse. The property the user has is the same either way, and pinning
    the mechanism would make this fail on a refactor that kept the behaviour.
    """
    m = measure(page)
    assert m["nodes"] < TOTAL, (
        f"all {TOTAL} nodes were drawn at once — nothing was folded, so the opening "
        f"view was sized to the whole tree")
    assert m["smallest"] >= READABLE_PX


def test_expanding_everything_still_will_not_go_below_reading_size(page):
    """The floor's real job, and the half a default-depth change cannot cover.

    Asking for the whole chart is a legitimate thing to want; silently answering it
    at 27% is not. The zoom stops, the canvas keeps panning.
    """
    before = measure(page)
    page.get_by_role("button", name="Expand all", exact=True).click()
    page.wait_for_function(
        f"() => document.querySelectorAll('svg[aria-label*=\"goals\"] g[data-node]').length"
        f" > {before['nodes']}", timeout=10_000)

    after = measure(page)
    assert after["nodes"] == TOTAL, (
        f"expected the whole fixture drawn, got {after['nodes']} of {TOTAL}")
    assert after["smallest"] >= READABLE_PX, (
        f"expanded to {after['nodes']} nodes and shrank to {after['smallest']:.1f}px "
        f"labels at {after['zoom'] * 100:.0f}% zoom")


def test_the_graph_decides_the_opening_view_not_the_outlines_row_count(tall_page):
    """Which seeding is in charge, asserted where the two disagree.

    The outline folds every branch once its list passes 20 rows, and this fixture
    is 52. That rule is blind to the canvas: given a viewport with room for the
    whole tree above the legibility floor, it would still hand you four nodes and
    a set of badges.

    seedCollapse asks the layout instead, so here it opens everything — 52 nodes
    at roughly 73%, which is over the floor and therefore readable. If this fails
    with a handful of nodes, the graph has gone back to inheriting a decision made
    by counting rows.
    """
    m = measure(tall_page)
    assert m["nodes"] == TOTAL, (
        f"opened {m['nodes']} of {TOTAL} nodes in a viewport with room for all of "
        f"them — the row-count rule is choosing the view again")
    assert m["smallest"] >= READABLE_PX, (
        f"opened everything at {m['smallest']:.1f}px labels — legible was supposed "
        f"to be the constraint that allowed it")


def test_a_users_own_folds_still_win(page):
    """The half the change could have broken. Seeding on a first visit is one
    thing; overriding a fold someone made by hand would be another, and the old
    `collapsed.size > 0` test was what used to prevent it."""
    nodes = page.locator("g[data-node]")
    before = nodes.count()

    # Open a branch by hand, then come back to the graph fresh.
    page.get_by_role("button", name="Expand all", exact=True).click()
    page.wait_for_function(
        f"() => document.querySelectorAll('svg[aria-label*=\"goals\"] g[data-node]').length"
        f" > {before}", timeout=10_000)
    page.reload()
    page.wait_for_selector("g[data-node]", timeout=15_000)

    assert measure(page)["nodes"] == TOTAL, (
        "the seeding re-folded a chart the user had expanded — a stored choice "
        "must outrank the default")


def test_fit_respects_the_floor_too(page):
    """`Fit` is the other way to ask for the whole tree, and it calls the same
    clamp. It had its own unclamped `Math.max(0.25, k)` before, so a fix applied
    only to the opening path would leave one button that still ruins the chart."""
    page.get_by_role("button", name="Expand all", exact=True).click()
    page.wait_for_timeout(200)
    page.get_by_role("button", name="Fit", exact=True).click()
    page.wait_for_timeout(300)

    m = measure(page)
    assert m["nodes"] == TOTAL
    assert m["smallest"] >= READABLE_PX, (
        f"Fit shrank the chart to {m['smallest']:.1f}px labels at "
        f"{m['zoom'] * 100:.0f}% zoom")
