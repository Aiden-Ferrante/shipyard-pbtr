"""The fixture fleet: every run scans a code root built here, never the machine's.

A dozen route tests used to assert against the real ~/Desktop/code — they passed
only on a machine with a tagged shipyard clone in exactly that place, and `make
test` was red everywhere else: fresh clones, containers, CI.

Env, not the module attribute, and only here: conftest imports before every test
module, so these lines deterministically precede the first `app.main` import.
That is the ordering guarantee the test modules themselves never had — setting
env *there* raced module collection order and silently scanned the real fleet
(see test_owed.fleet and test_board.fake_code_root, which patch the attribute
for exactly that reason). Per-test overrides must still patch `main.CODE_ROOT`.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         *args],
        cwd=cwd, check=True, capture_output=True)


def _build_fleet() -> Path:
    """One adopted repo named shipyard: manifest, one commit, a version tag.

    The tag matters — Build is derived from `git describe`, and test_loop
    asserts the derived `why` names a version or says "nothing since".
    """
    fleet = Path(tempfile.mkdtemp(prefix="shipyard-fleet-"))
    repo = fleet / "shipyard"
    repo.mkdir()
    (repo / "PROJECT.yaml").write_text("id: shipyard\nname: Shipyard\nstage: tool\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    _git(repo, "tag", "v0.1.0")
    return fleet


os.environ["SHIPYARD_CODE_ROOT"] = str(_build_fleet())

# Safety nets, not policy: each module still pins its own DB and export (and
# must — see the 2026-08-06 incident notes), but a module that forgets should
# land in a tempdir, never in the repo's data/ or docs/. MC gets an address
# that refuses instantly, so a live Mission Control on :9090 can't leak real
# fleet status into a run.
os.environ.setdefault("SHIPYARD_DB", os.path.join(tempfile.mkdtemp(), "conftest.sqlite"))
os.environ.setdefault("SHIPYARD_CHART_EXPORT", os.path.join(tempfile.mkdtemp(), "chart.md"))
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())
os.environ.setdefault("SHIPYARD_CYCLES_ROOT", tempfile.mkdtemp())
os.environ.setdefault("SHIPYARD_MC_URL", "http://127.0.0.1:9")
