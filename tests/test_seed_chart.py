"""The seeder: markdown-authored nodes put into the store, idempotently.

`docs/chart.md` is export-only (ADR 0003), so a charting session done as markdown —
the only form available on a machine without the sqlite — leaves the app blind to it.
`scripts/seed_chart.py` closes that gap by calling the same write API the UI calls.

What is worth protecting here is not the prose but the three properties that make it
safe to run against a real chart: it creates exactly what is missing, it refuses to
invent a bearing it cannot find, and running it twice changes nothing.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Nothing is exported to the environment here, deliberately — ARCHITECTURE.md:
# config binds to module constants at import, and patching the env has twice caused
# a run to scan or overwrite real data. It would also leak: pytest imports every
# test module before running any, so this file's paths would be inherited by the
# modules that `os.environ.setdefault` theirs later in the alphabet.
#
# The seeder is a separate process, where the environment IS the interface, so
# `run()` passes SHIPYARD_DB and SHIPYARD_CHART_EXPORT explicitly on every call —
# one place, never inherited, and never pointed at the real store.

import app.chart as chart  # noqa: E402

SCRIPT = ROOT / "scripts" / "seed_chart.py"
SEED = ROOT / "scripts" / "demo-chart.json"
BEARINGS = ("Ship a CLI tool", "Write docs people use")


def run(db, export, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(ROOT),
        env={**os.environ, "SHIPYARD_DB": str(db), "SHIPYARD_CHART_EXPORT": str(export)})


def store(tmp_path, bearings=BEARINGS):
    """A chart holding just the bearings the seed hangs from."""
    db = tmp_path / "chart.sqlite"
    con = sqlite3.connect(db)
    chart.init(con)
    for title in bearings:
        chart.create_problem(con, title=title, waypoint="placeholder")
    con.commit()
    con.close()
    return db, tmp_path / "chart.md"


def seeded_titles():
    spec = json.loads(SEED.read_text())
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n["title"])
            walk(n.get("kids") or [])

    walk(spec["nodes"])
    return out


def test_creates_every_node_then_becomes_a_no_op(tmp_path):
    db, export = store(tmp_path)
    titles = seeded_titles()

    first = run(db, export)
    assert first.returncode == 0, first.stderr
    assert f"{len(titles)} to create" in first.stdout

    con = sqlite3.connect(db)
    have = {p["title"] for p in chart.all_problems(con)}
    con.close()
    assert set(titles) <= have

    again = run(db, export)
    assert again.returncode == 0, again.stderr
    assert "0 to create" in again.stdout


def test_the_quickstart_node_serves_both_bearings(tmp_path):
    """The dual parent is the point of charting it at all — the node serves both
    bearings at once. A project with a single parent goes straight
    to drift the moment that parent is thawed (ADR 0003)."""
    db, export = store(tmp_path)
    run(db, export)

    con = sqlite3.connect(db)
    node = next(p for p in chart.all_problems(con)
                if p["title"].startswith("The quickstart runs exactly as written"))
    parents = {p["title"] for p in chart.parents(con, node["id"])}
    con.close()
    assert parents == set(BEARINGS)
    assert node["repo"] == "demo-cli"
    # Rendered in full under one bearing, referenced under the other — never twice.
    text = export.read_text()
    assert text.count(f"**{node['title']}**") == 2
    assert "*shown in full above*" in text


def test_refuses_when_a_bearing_is_missing(tmp_path):
    """Creating the missing bearing would invent the top of someone's chart from a
    data file. Refusing is the whole safety property when this runs against a real
    store."""
    db, export = store(tmp_path, bearings=("Ship a CLI tool",))
    r = run(db, export)
    assert r.returncode == 2
    assert "Write docs people use" in r.stderr
    con = sqlite3.connect(db)
    assert len(chart.all_problems(con)) == 1
    con.close()


def test_refuses_a_seed_that_hands_one_repo_to_several_nodes(tmp_path):
    """A repo is attacked by exactly one problem. `chart.link_repo` has always said so,
    but the seeder writes through `create_problem`, which did not — and on 2026-08-25 a
    branch seeded with `repo` on all seven of its nodes drew the same project card seven
    times on the board. Caught in the pre-flight, so --dry-run reports it too."""
    db, export = store(tmp_path, bearings=("Agentic AI",))
    seed = tmp_path / "collides.json"
    seed.write_text(json.dumps({"nodes": [
        {"title": "Parent that attacks the repo", "waypoint": "observable",
         "repo": "la4ml", "parents": ["Agentic AI"],
         "kids": [{"title": "A step under it", "waypoint": "also observable",
                   "repo": "la4ml"}]}]}))

    dry = run(db, export, str(seed), "--dry-run")
    assert dry.returncode == 2
    assert "la4ml" in dry.stderr
    assert "A step under it" in dry.stderr

    r = run(db, export, str(seed))
    assert r.returncode == 2
    con = sqlite3.connect(db)
    assert {p["title"] for p in chart.all_problems(con)} == {"Agentic AI"}
    con.close()
    assert not export.exists()


def test_a_repo_already_in_the_chart_is_not_handed_to_a_new_node(tmp_path):
    """The same invariant across the boundary between the store and the seed file:
    the collision is with a node that is already there, not with a sibling in the seed."""
    db, export = store(tmp_path, bearings=("Agentic AI",))
    con = sqlite3.connect(db)
    chart.create_problem(con, title="Already attacking it", waypoint="observable",
                         repo="la4ml")
    con.commit()
    con.close()

    seed = tmp_path / "steals.json"
    seed.write_text(json.dumps({"nodes": [
        {"title": "Wants the same repo", "waypoint": "observable", "repo": "la4ml",
         "parents": ["Agentic AI"]}]}))

    r = run(db, export, str(seed))
    assert r.returncode == 2
    assert "Already attacking it" in r.stderr
    con = sqlite3.connect(db)
    assert not [p for p in chart.all_problems(con) if p["title"] == "Wants the same repo"]
    con.close()


def test_dry_run_writes_nothing(tmp_path):
    db, export = store(tmp_path)
    r = run(db, export, "--dry-run")
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    assert {p["title"] for p in chart.all_problems(con)} == set(BEARINGS)
    con.close()
    assert not export.exists()


def test_siblings_keep_the_order_they_were_authored_in(tmp_path):
    """chart._now() is second-resolution and every view orders siblings by created_at,
    so a batch insert would tie and leave the order to sqlite. The seeder stamps each
    node a second apart; without that the export scrambles."""
    db, export = store(tmp_path)
    run(db, export)

    con = sqlite3.connect(db)
    aware = next(p for p in chart.all_problems(con)
                 if p["title"] == "Write docs people use")
    kids = [k["title"] for k in chart.children(con, aware["id"])]
    con.close()

    spec = json.loads(SEED.read_text())
    expected = [n["title"] for n in spec["nodes"]
                if "Write docs people use" in (n.get("parents") or [])]
    assert kids == expected
