"""`PROJECT.yaml`'s `mc:` field is a foreign key into `mission-control/apps.yaml`.

Nothing enforced it. `PLATFORM.md §2` names it directly — *"a foreign key across
two files that nothing enforces"* — and lists unifying the two registries as the
merge's main functional payoff. This is the half of that payoff available without
the merge: assert the key resolves.

## WHY THE TEST IS HERE AND NOT IN MISSION CONTROL

MC does not know `PROJECT.yaml` exists, and must not learn. `PLATFORM.md §1`
puts the supervisor in its own tier precisely because it has to outlive the
things that read it; teaching it about the project-management plane above it is
an upward dependency in the one place the platform design forbids one.

Shipyard is the repo that DEREFERENCES the key, so shipyard is the repo that
breaks when it dangles. It already reads `apps.yaml` from disk (`mc_registry()`),
so the join costs nothing and needs no running MC.

## THE FAILURE THIS CATCHES, WHICH IS SILENT

`project_view()` does `entry = registry.get(mid, {})` and then builds a card from
the empty dict — id, `name=mid`, `ports=[]`, `status=None`. A `mc:` entry naming
an app that no longer exists therefore renders as a **real-looking app card that
is simply never running**, which is indistinguishable from a stopped app. The
fleet row says the repo ships an app; the app does not exist; nothing anywhere
says so.

That is not hypothetical for this fleet. `mission-control` commit `c0c74eb`
purged the dead `rf-*` entries when the research-firm repo was deleted, and
`apps.yaml` entries have been renamed in place (`feedwall` became the FreshRSS
firehose while the wall moved to `feedwall-wall`). Either move leaves any `mc:`
that pointed at the old id dangling and rendering.

## WHY A MISSING `mc:` IS NOT A VIOLATION

`mc_by_cwd()` derives the link from `apps.yaml`'s `cwd`, which is the same fact
from the side that cannot drift — MC could not start the app without it. Its
docstring records that only 3 of 21 repos declared `mc:` while 8 more were
managed, so requiring the field would fail most of a fleet that works. Declared
wins where present; derived fills the gap. Only a declaration that points at
NOTHING is a bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

REPO = Path(__file__).resolve().parents[1]
CODE_ROOT = REPO.parent
APPS_YAML = CODE_ROOT / "mission-control" / "apps.yaml"

# apps.yaml top-level keys that are not app ids.
RESERVED = {"capabilities"}

# MC refuses to appear in its own registry (`registry.py:104-105` raises), so a
# repo naming it is declaring a true fact that apps.yaml structurally cannot
# carry. Not a dangling key.
SELF_ID = "mission-control"


def _declared_keys() -> list[tuple[Path, str]]:
    """(manifest path, mc id) for every declaration under the real code root."""
    out = []
    for manifest in sorted(CODE_ROOT.glob("*/PROJECT.yaml")):
        try:
            m = yaml.safe_load(manifest.read_text()) or {}
        except yaml.YAMLError:
            continue  # a malformed manifest is a different test's problem
        ids = m.get("mc") or []
        if isinstance(ids, str):
            ids = [ids]
        out.extend((manifest, str(i)) for i in ids)
    return out


def _app_ids(apps_yaml: Path) -> set[str]:
    raw = yaml.safe_load(apps_yaml.read_text()) or {}
    return {k for k, v in raw.items() if isinstance(v, dict) and k not in RESERVED}


# ---------------------------------------------------------------------------
# The real fleet
# ---------------------------------------------------------------------------

pytestmark_reason = (
    f"the real fleet is not beside this repo — no {APPS_YAML}. The suite is "
    f"hermetic by design (see tests/conftest.py), so this file is the one place "
    f"that reads the machine, and it skips rather than failing a clone."
)


@pytest.mark.skipif(not APPS_YAML.exists(), reason=pytestmark_reason)
def test_every_declared_mc_id_resolves():
    """The join, over the fleet as it is on disk."""
    known = _app_ids(APPS_YAML)
    dangling = [
        f"{manifest.parent.name}/PROJECT.yaml declares mc: [{mid}] — no such app "
        f"in apps.yaml"
        for manifest, mid in _declared_keys()
        if mid != SELF_ID and mid not in known
    ]
    assert not dangling, (
        "dangling mc: foreign key — the fleet row will render a card for an app "
        "that does not exist, indistinguishable from a stopped one:\n  "
        + "\n  ".join(dangling))


@pytest.mark.skipif(not APPS_YAML.exists(), reason=pytestmark_reason)
def test_the_join_is_not_vacuous():
    """A test over an empty set passes for the wrong reason.

    If `mc:` fell out of use entirely, or the glob stopped matching, the test
    above would go green while enforcing nothing — the same shape as
    `check_hubs.py:56`, which walks a list a package can simply be missing from.
    """
    declared = _declared_keys()
    assert declared, "no mc: declarations found at all — the join reads nothing"
    assert _app_ids(APPS_YAML), "apps.yaml parsed to no app ids"


# ---------------------------------------------------------------------------
# The negative test — hermetic, always runs
# ---------------------------------------------------------------------------

def _fixture(tmp_path: Path, manifest: str, apps_yaml: str) -> tuple[Path, Path]:
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "PROJECT.yaml").write_text(manifest)
    (tmp_path / "mission-control").mkdir()
    p = tmp_path / "mission-control" / "apps.yaml"
    p.write_text(apps_yaml)
    return tmp_path, p


def _dangling(root: Path, apps_yaml: Path) -> list[str]:
    """The rule under test, parameterised on a root so it can be pointed at a
    fixture. Kept in step with the module-level version by
    `test_the_rule_and_its_fixture_agree`."""
    known = _app_ids(apps_yaml)
    out = []
    for manifest in sorted(root.glob("*/PROJECT.yaml")):
        m = yaml.safe_load(manifest.read_text()) or {}
        ids = m.get("mc") or []
        if isinstance(ids, str):
            ids = [ids]
        out += [f"{manifest.parent.name}: {i}" for i in ids
                if str(i) != SELF_ID and str(i) not in known]
    return out


def test_a_dangling_key_is_caught(tmp_path):
    """The `rf-*` shape: a manifest still naming an app that was purged."""
    root, apps = _fixture(
        tmp_path,
        "id: demo\nmc: [rf-api]\n",
        "something-else:\n  cwd: /tmp\n  start: echo hi\n")
    assert _dangling(root, apps) == ["repo: rf-api"]


def test_a_renamed_app_is_caught(tmp_path):
    """The `feedwall` shape: the id still exists in apps.yaml but now means a
    different app, and the one this repo meant moved to a new id. Catching the
    rename requires only that the OLD id be gone — which is the case whenever the
    move was a rename rather than an addition."""
    root, apps = _fixture(
        tmp_path,
        "id: demo\nmc: [old-wall]\n",
        "feedwall:\n  cwd: /tmp\n  start: a\nfeedwall-wall:\n  cwd: /tmp\n  start: b\n")
    assert _dangling(root, apps) == ["repo: old-wall"]


def test_a_resolving_key_passes(tmp_path):
    """The other half. A rule that fails everything satisfies the tests above for
    entirely the wrong reason."""
    root, apps = _fixture(
        tmp_path, "id: demo\nmc: [demo]\n", "demo:\n  cwd: /tmp\n  start: echo hi\n")
    assert _dangling(root, apps) == []


def test_a_repo_with_no_mc_field_passes(tmp_path):
    """Absence is handled by `mc_by_cwd()` deriving the link from apps.yaml's
    `cwd`. Requiring the field would fail most of a fleet that demonstrably
    works — see this module's docstring."""
    root, apps = _fixture(
        tmp_path, "id: demo\nname: Demo\n", "demo:\n  cwd: /tmp\n  start: echo hi\n")
    assert _dangling(root, apps) == []


def test_naming_mission_control_passes(tmp_path):
    """`registry.py` RAISES if apps.yaml lists `mission-control`, so a repo naming
    it states a true fact the registry structurally cannot hold. Failing that
    would demand an edit that MC refuses to load."""
    root, apps = _fixture(
        tmp_path, "id: demo\nmc: [mission-control]\n",
        "other:\n  cwd: /tmp\n  start: echo hi\n")
    assert _dangling(root, apps) == []


def test_a_scalar_mc_field_is_read_as_one_id(tmp_path):
    """`mc: shipyard` instead of `mc: [shipyard]`. YAML accepts both and a reader
    that assumed a list would iterate the string's characters — eight dangling
    keys from one correct-looking manifest."""
    root, apps = _fixture(
        tmp_path, "id: demo\nmc: gone\n", "demo:\n  cwd: /tmp\n  start: echo hi\n")
    assert _dangling(root, apps) == ["repo: gone"]


@pytest.mark.skipif(not APPS_YAML.exists(), reason=pytestmark_reason)
def test_the_rule_and_its_fixture_agree():
    """The negative tests exercise `_dangling`, the live test exercises the
    module-level join. Two implementations of one rule drift, and the drift would
    be invisible: the negative tests keep passing while the live rule quietly
    stops matching. Assert they agree on the real fleet."""
    known = _app_ids(APPS_YAML)
    live = sorted(f"{m.parent.name}: {i}" for m, i in _declared_keys()
                  if i != SELF_ID and i not in known)
    assert sorted(_dangling(CODE_ROOT, APPS_YAML)) == live
