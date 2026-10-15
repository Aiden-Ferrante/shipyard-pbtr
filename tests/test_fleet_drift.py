"""The fleet's colour and type contract, asserted from this repo's test suite.

`fleet.css` is the shared visual contract and `fleet-ui/check.sh` is what stops it
decaying — the palette and scale were converged by hand twice and drifted back
within days the first time. But a checker only enforces anything if something runs
it, and until now nothing did: no CI, no hook, no make target. It found 127
violations in this repo the day it was given teeth, all of which had accumulated
while it sat there passing.

So it runs here, for the same reason check-ui.mjs does — agents and humans run
pytest reflexively and read CI rarely.

SCOPED TO THIS REPO, deliberately. Run bare, check.sh scans all four fleet apps,
and shipyard's suite going red because vault-dashboard drifted would make the
result something nobody here can act on. Each app asserts its own scope; a human
running check.sh by hand still gets the whole fleet.

It lives in a sibling repo, which is a real dependency and is allowed to be
absent — a clone of shipyard alone must still pass. Absent is a SKIP with a
reason, never a silent pass.

The second test is the important one, exactly as in test_ui_contract.py: a
checker that never fires is indistinguishable from a checker that cannot fire.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
CHECKER = ROOT.parent / "fleet-ui" / "check.sh"

pytestmark = pytest.mark.skipif(
    not CHECKER.exists() or shutil.which("bash") is None,
    reason=f"fleet-ui/check.sh not beside this repo at {CHECKER} — clone it to run "
           f"the drift check, or run `bash check.sh` from fleet-ui by hand",
)


def _run(*scopes: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(CHECKER), *(str(s) for s in scopes)],
        capture_output=True, text=True, timeout=120,
    )


def test_this_repo_holds_the_fleet_contract():
    r = _run(SRC)
    assert r.returncode == 0, f"fleet drift in {SRC}:\n{r.stdout}\n{r.stderr}"


def test_the_checker_catches_a_planted_violation(tmp_path):
    """A checker with no negative test is decoration.

    One planted file, one violation per rule the check knows about. If a rule is
    ever weakened into something that cannot match — which is how the Tailwind
    hole existed for months, catching nothing while reporting clean — this fails
    and names the rule that went quiet.
    """
    (tmp_path / "bad.jsx").write_text(
        'const a = <p className="text-sm">off the six steps</p>\n'      # tailwind scale
        'const b = <p className="text-[13px]">a raw pixel size</p>\n'   # bracketed px
        "const c = <div style={{ color: '#ff0000' }} />\n"              # hex literal
        # Chromatic on purpose. The achromatic carve-out exempts rgba(0,0,0,α)
        # and rgba(255,255,255,α) — with no hue they cannot encode a stale
        # palette — so planting black here would test the carve-out, not the
        # rule. This is the old palette's green tint, the literal the rule
        # exists for.
        "const d = <div style={{ background: 'rgba(63,185,80,.12)' }} />\n"  # rgba literal
    )
    r = _run(tmp_path)
    assert r.returncode == 1, (
        f"the checker passed a file that breaks four rules:\n{r.stdout}\n{r.stderr}")

    out = r.stdout + r.stderr
    for rule in ("hex in value position",
                 "rgb()/rgba() literal",
                 "raw pixel type size",
                 "Tailwind default type scale"):
        assert rule in out, f"{rule!r} did not fire:\n{out}"


def test_a_clean_directory_passes(tmp_path):
    """The other half of the negative test. A checker that fails everything is as
    useless as one that fails nothing, and would make the test above pass for the
    wrong reason."""
    (tmp_path / "fine.jsx").write_text(
        'const a = <p className="text-meta text-zinc-500">on the scale</p>\n'
        'const b = <p className="text-micro">and this one</p>\n'
    )
    r = _run(tmp_path)
    assert r.returncode == 0, f"a compliant file was reported as drift:\n{r.stdout}"
