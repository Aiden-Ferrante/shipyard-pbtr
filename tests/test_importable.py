"""POST /api/importable — containment must hold against path-resolution tricks.

The guard used to be `str(path).startswith(str(CODE_ROOT))` on the *unresolved*
path, which accepted `code/../elsewhere` and prefix-siblings like `code-evil`,
then wrote a PROJECT.yaml outside the fleet root. `read_document` already did
this correctly (resolve, then compare) — these tests hold the import endpoint
to the same standard.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "importable.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture
def code_root(tmp_path, monkeypatch):
    """Patch the module attribute, never the env var: config binds at import,
    so the env version silently scans the real ~/Desktop/code (same trap as
    test_board.fake_code_root)."""
    root = tmp_path / "code"
    root.mkdir()
    monkeypatch.setattr(main, "CODE_ROOT", root)
    return root


def mkrepo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_a_repo_inside_the_root_is_adopted(code_root):
    repo = mkrepo(code_root / "adoptme")
    r = client.post("/api/importable", json={"path": str(repo)})
    assert r.status_code == 200, r.text
    assert (repo / "PROJECT.yaml").exists()


def test_dotdot_cannot_escape_the_root(code_root):
    """`code/../outside` starts with the root as a string but resolves past it."""
    outside = mkrepo(code_root.parent / "outside")
    sneaky = str(code_root / ".." / "outside")
    r = client.post("/api/importable", json={"path": sneaky})
    assert r.status_code == 422
    assert "outside the code root" in r.json()["detail"]
    assert not (outside / "PROJECT.yaml").exists()


def test_a_prefix_sibling_is_not_inside(code_root):
    """`code-evil` shares the root's string prefix without being under it."""
    sibling = mkrepo(code_root.parent / (code_root.name + "-evil"))
    r = client.post("/api/importable", json={"path": str(sibling)})
    assert r.status_code == 422
    assert not (sibling / "PROJECT.yaml").exists()


def test_the_root_itself_still_counts_as_inside(code_root):
    """Resolution must not tighten the boundary: the root was importable before."""
    subprocess.run(["git", "init", "-q", str(code_root)], check=True)
    r = client.post("/api/importable", json={"path": str(code_root)})
    assert r.status_code == 200, r.text
    assert (code_root / "PROJECT.yaml").exists()
