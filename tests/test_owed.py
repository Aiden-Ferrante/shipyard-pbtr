"""The fleet-wide owed view.

Grouped by kind, never ranked by project: Road to 1.0 prunes "anything that
computes a score for a project", and the question this answers is "what do I owe",
not "which repo is worst".

This file owns its own CODE_ROOT. Every other route test scans the real
`~/Desktop/code`, which is read-only and therefore safe but makes any assertion
about *counts* a hostage to whatever the fleet happens to look like today.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

_ROOT = tempfile.mkdtemp()
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "owed.sqlite")
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main, repo  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def git(path, *argv):
    subprocess.run(["git", "-C", str(path), *argv], check=True,
                   capture_output=True, text=True)


def mkrepo(name, *, dirty=0, commits=1, tag="v1.0.0", manifest_extra=""):
    path = Path(_ROOT) / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "PROJECT.yaml").write_text(
        f"id: {name}\nname: {name.title()}\nstage: tool\n{manifest_extra}")
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "first")
    if tag:
        git(path, "tag", tag)
    for i in range(commits - 1):
        (path / f"f{i}.txt").write_text("x\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", f"feat: thing {i}")
    for i in range(dirty):
        (path / f"loose{i}.txt").write_text("y\n")
    return path


@pytest.fixture(scope="module", autouse=True)
def fleet():
    """Patch the module attribute, not the environment.

    `main.CODE_ROOT` is read once at import. Setting `SHIPYARD_CODE_ROOT` here
    only works if this file is imported before every other test module — which it
    is not, alphabetically or otherwise — so the env-var version of this fixture
    silently scanned the real `~/Desktop/code` and passed in isolation while
    failing in the suite. Same shape as the 2026-08-06 export incident: config
    bound at import is not overridable by a test that loads later.
    """
    previous = main.CODE_ROOT
    main.CODE_ROOT = Path(_ROOT)
    mkrepo("tidy")
    mkrepo("messy", dirty=3, commits=4)
    yield
    main.CODE_ROOT = previous


def kinds():
    r = client.get("/api/owed")
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {k["kind"]: k["projects"] for k in body["kinds"]}


def test_it_scans_the_fleet_and_groups_by_kind():
    body, by = kinds()
    assert body["scanned"] == 2
    assert [k["kind"] for k in body["kinds"]] == [k for k, _ in repo.OWED_KINDS], \
        "kind order is editorial and fixed — the frontend renders it as given"


def test_uncommitted_work_is_counted_by_file_and_named():
    _, by = kinds()
    messy = [p for p in by["uncommitted"] if p["id"] == "messy"]
    assert len(messy) == 1
    assert messy[0]["n"] == 3
    assert messy[0]["detail"] == "3 files"


def test_a_repo_past_its_tag_is_owed_regardless_of_how_clean_it_is():
    _, by = kinds()
    assert [p["id"] for p in by["untagged"]] == ["messy"]
    assert by["untagged"][0]["detail"] == "3 commits since v1.0.0"


def test_a_project_with_no_chart_node_owes_the_reason_it_exists():
    """The loudest debt, and the one invisible to a chart-only query: a project
    nobody has said why they are building."""
    _, by = kinds()
    assert sorted(p["id"] for p in by["uncharted"]) == ["messy", "tidy"]


@contextlib.contextmanager
def temp_repos(*specs):
    """Build repos, then remove them again.

    Every other test here asserts on the exact fixture set, so a repo left behind
    turns three unrelated assertions red — which is exactly what happened when these
    two tests were first written without it. The module's root is shared on purpose
    (see the docstring); the cleanup is what makes adding a case to it safe.
    """
    made = []
    try:
        for name, kw in specs:
            mkrepo(name, **kw)
            made.append(Path(_ROOT) / name)
        yield
    finally:
        for path in made:
            shutil.rmtree(path, ignore_errors=True)


def test_chart_none_clears_the_uncharted_debt_and_nothing_else():
    """A repo can declare it is not goal-bearing, and then not owe a reason.

    After the chart became a map of goals under four life domains rather than a
    registry of everything on disk, `uncharted` fired for thirteen repos that were
    never meant to carry a node. This is the declared exemption — and it must clear
    exactly one kind, or it becomes a way to silence real debt by editing a manifest.
    """
    with temp_repos(("exempt", {"dirty": 2, "manifest_extra": "chart: none\n"})):
        _, by = kinds()
        assert "exempt" not in [p["id"] for p in by["uncharted"]], \
            "a repo declaring chart: none still owed the reason it exists"
        assert "exempt" in [p["id"] for p in by["uncommitted"]], \
            "the exemption silenced a debt that has nothing to do with the chart"


def test_the_uncharted_exemption_must_be_claimed_not_inherited():
    """Silence is not an exemption. A repo that says nothing still owes a node —
    the same rule as `release: scheme: none`, and the reason both are declarations
    rather than defaults: an exemption acquired by neglect protects nothing."""
    with temp_repos(("silent", {}), ("wrong-value", {"manifest_extra": "chart: someday\n"})):
        _, by = kinds()
        owing = [p["id"] for p in by["uncharted"]]
        assert "silent" in owing, "a manifest saying nothing was treated as exempt"
        assert "wrong-value" in owing, "any value but 'none' must still expect a node"


def test_a_repo_with_no_upstream_reports_that_and_not_a_push_count():
    _, by = kinds()
    assert sorted(p["id"] for p in by["no-remote"]) == ["messy", "tidy"]
    assert by["unpushed"] == [], "there is no count of unpushed without an upstream"


def test_a_project_owing_nothing_is_listed_apart_rather_than_omitted():
    """Absence from every bucket is indistinguishable from not being scanned;
    `clear` is what makes "I owe nothing here" a readable answer."""
    body, _ = kinds()
    assert body["clear"] == [], "both fixtures are uncharted, so neither is clear"
    assert body["scanned"] == 2


def test_loudest_first_within_a_kind():
    mkrepo("loudest", dirty=9)
    _, by = kinds()
    assert [p["n"] for p in by["uncommitted"]] == [9, 3]


# ---------- durable memory ----------
#
# Four kinds, read where they already live. The point of the view is the ABSENCE:
# grouped by what is missing, never scored, for the same reason Owed is.

def test_a_manifest_declared_document_is_surfaced(tmp_path, monkeypatch):
    """The bug this fixes: glm-harness declared `charter: docs/CHARTER.md` in its
    PROJECT.yaml for weeks and the documents list showed it a README, because only
    `links.docs` was ever read."""
    import app.repo as repo_mod
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CHARTER.md").write_text("# Charter\n")
    (tmp_path / "README.md").write_text("# Readme\n")
    docs = repo_mod.documents(tmp_path, {"charter": "docs/CHARTER.md", "readme": "README.md"})
    by = {d["label"]: d for d in docs}
    assert by["charter"]["path"] == "docs/CHARTER.md"
    assert by["charter"]["declared"] is True


def test_a_declared_document_that_does_not_exist_is_not_offered(tmp_path):
    """A manifest naming a file that is gone must not produce a link that 404s."""
    import app.repo as repo_mod
    docs = repo_mod.documents(tmp_path, {"charter": "docs/CHARTER.md"})
    assert not [d for d in docs if d["label"] == "charter"]


def test_a_charter_is_found_by_convention_without_a_manifest_entry(tmp_path):
    """Discovery must not require the manifest — most repos will never declare one."""
    import app.repo as repo_mod
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CHARTER.md").write_text("# Charter\n")
    assert [d for d in repo_mod.documents(tmp_path, {}) if d["label"] == "charter"]


def test_a_declared_document_is_not_listed_twice(tmp_path):
    """`docs/CHARTER.md` is both a declared link and a convention path — it must
    appear once, or the rail grows a duplicate row per repo that does both."""
    import app.repo as repo_mod
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CHARTER.md").write_text("# Charter\n")
    docs = repo_mod.documents(tmp_path, {"charter": "docs/CHARTER.md"})
    assert len([d for d in docs if d.get("path") == "docs/CHARTER.md"]) == 1


def test_an_external_link_stays_a_url_not_a_file(tmp_path):
    import app.repo as repo_mod
    docs = repo_mod.documents(tmp_path, {"vision": "https://example.com/vision"})
    v = next(d for d in docs if d["label"] == "vision")
    assert v["kind"] == "url" and "path" not in v


def test_memory_groups_by_what_is_missing():
    body = client.get("/api/memory").json()
    kinds = {k["kind"] for k in body["missing"]}
    assert kinds == {"why", "rules", "shape", "choices"}
    # Grouped, never ranked — no per-project score anywhere in the payload.
    assert all("score" not in p for p in body["projects"])
    for k in body["missing"]:
        assert k["why"], "every kind states what its absence means"
