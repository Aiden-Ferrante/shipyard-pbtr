"""The frontend dependency rule, asserted from the test suite.

`make check` runs check-ui.mjs, but agents and humans run pytest reflexively and
read CI rarely — so the contract fails here too.

The second test is the important one. A checker that never fires is
indistinguishable from a checker that cannot fire, so we plant a violation and
assert it is caught. Without this, rule drift looks identical to compliance.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "frontend" / "scripts" / "check-ui.mjs"
SRC = ROOT / "frontend" / "src"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not CHECKER.exists(),
    reason="node or check-ui.mjs unavailable",
)


def _run(target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(CHECKER), str(target)],
        capture_output=True, text=True, timeout=60,
    )


def test_frontend_honours_the_ui_contract():
    r = _run(SRC)
    assert r.returncode == 0, f"check-ui failed:\n{r.stdout}\n{r.stderr}"


def test_checker_catches_a_planted_violation(tmp_path):
    """A checker with no negative test is decoration."""
    shutil.copy(SRC / "ui.jsx", tmp_path / "ui.jsx")
    (tmp_path / "bad.jsx").write_text(
        'export function Chip() { return null }\n'          # redefines a primitive
        'const a = <p className="text-sm">loading…</p>\n'    # hand-rolled loading
        "const b = <div style={{ color: '#ff0000' }} />\n"   # raw colour literal
    )
    r = _run(tmp_path)
    assert r.returncode == 1, "checker passed a file that violates three rules"
    for rule in ("redefines-primitive", "hand-rolled-loading", "raw-colour"):
        assert rule in r.stderr, f"{rule} not reported:\n{r.stderr}"
