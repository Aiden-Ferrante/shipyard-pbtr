"""The export refuses to delete reasoning it did not write.

`docs/chart.md` is a one-way export (ADR 0003), which means every write rewrites
the whole file from the store. The failure that follows is quiet: a store that is
merely INCOMPLETE — seeds pulled but never run — drops every node it has not heard
of, and the only signal is a diff with more deletions than insertions.

That happened. Fourteen world-awareness nodes lived in the committed markdown and
in no local database; the next seed run removed all fourteen.

The second test is the important one, for the same reason it is in
test_ui_contract.py: a guard that never fires is indistinguishable from a guard
that cannot fire. So one test plants the exact situation — a file naming a node
the store has never held — and asserts the export refuses rather than proceeding.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest  # noqa: E402

from app import chart  # noqa: E402


def _store(tmp_path, children, *, drift=()):
    """A bearing with `children` beneath it, plus any `drift` nodes serving nothing.

    Both shapes on purpose: render_markdown writes a charted node as
    `- **Title** — …` and a drift node as `- Title — waypoint: …`, and a guard that
    only recognised the first would let the second be deleted without a word.
    """
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(Path(tmp_path) / "t.sqlite")
    chart.init(con)
    root = chart.create_problem(con, title="Bearing", waypoint="the bearing is observable")
    for t in children:
        chart.create_problem(con, title=t, waypoint=f"{t} is observable", parent_id=root)
    for t in drift:
        chart.create_problem(con, title=t, waypoint=f"{t} is observable")
    con.commit()
    return con


def test_export_writes_when_nothing_would_be_lost(tmp_path):
    con = _store(tmp_path, ["Alpha", "Beta"], drift=["Loose"])
    out = tmp_path / "chart.md"

    chart.export(con, out)
    assert "Alpha" in out.read_text()

    # Re-exporting the same store is a no-op, not a refusal: every title in the
    # file is still in the store.
    chart.export(con, out)
    assert "Beta" in out.read_text()


def test_prose_bullets_inside_a_description_are_not_titles(tmp_path):
    """The false positive that showed up the first time this ran for real.

    A description can contain hand-written markdown, and a bolded bullet inside one
    looks exactly like a node line if you only match the bold. This repo had three,
    from the manalab audit. Defending them would have been permanent: they are
    prose, so no seed can ever put them in the store, and the mirror would have
    stopped updating with a warning nobody could act on.
    """
    con = _store(tmp_path, ["Alpha"])
    chart.create_problem(
        con, title="Findings", waypoint="the findings are written down",
        description=(
            "Two things were wrong:\n"
            "- **746 cards have the wrong cmc.** 494 have NULL mana_cost.\n"
            "- **46 faced lands are modelled as untapped** (Kabira Takedown...).\n"
        ))
    con.commit()
    out = tmp_path / "chart.md"
    chart.export(con, out)

    found = chart.exported_titles(out.read_text())
    assert "Findings" in found
    assert not [t for t in found if "cards have the wrong cmc" in t]
    assert not [t for t in found if "faced lands" in t]

    # And the round trip is exact: what the file names is what the store holds.
    assert found == {p["title"] for p in chart.all_problems(con)}


@pytest.mark.parametrize("missing, kind", [("Gamma", "charted"), ("Loose", "drift")])
def test_export_refuses_to_drop_a_node_the_store_never_had(tmp_path, missing, kind):
    """The planted violation. Without this the guard above proves nothing.

    Run for both render shapes: the real incident dropped charted nodes, but a
    drift node is if anything MORE likely to be the one a store has not caught up
    with, since drift is where a partially-seeded chart accumulates.
    """
    out = tmp_path / "chart.md"
    rich = _store(tmp_path, ["Alpha", "Beta", "Gamma"], drift=["Loose"])
    chart.export(rich, out)
    assert missing in out.read_text()
    before = out.read_text()

    # A second machine, whose store never received it — exactly the shape of the
    # real incident, where the seed had been pulled but not run.
    kids = [t for t in ("Alpha", "Beta", "Gamma") if t != missing]
    drift = [t for t in ("Loose",) if t != missing]
    poor = _store(tmp_path / "other", kids, drift=drift)

    with pytest.raises(chart.ChartError) as e:
        chart.export(poor, out)

    assert missing in str(e.value)
    assert "store is incomplete" in str(e.value).lower()
    # And it refused before writing, not after.
    assert out.read_text() == before


def test_protected_narrows_the_guard_to_named_titles(tmp_path):
    """`protected` is what lets one caller distinguish its own deletions from a
    store that never caught up. Only the named titles are defended."""
    out = tmp_path / "chart.md"
    chart.export(_store(tmp_path, ["Alpha", "Beta", "Gamma"]), out)
    poor = _store(tmp_path / "other", ["Alpha"])       # lost both Beta and Gamma

    # Guarding only Gamma: losing Beta is fine, losing Gamma is not.
    with pytest.raises(chart.ChartError) as e:
        chart.export(poor, out, protected={"Gamma"})
    assert "Gamma" in str(e.value)
    assert "Beta" not in str(e.value)

    # Guard something neither store ever had and nothing is defended.
    chart.export(poor, out, protected={"Nonexistent"})
    assert "Gamma" not in out.read_text()


class TestAppPath:
    """The app's half of the rule, exercised through main._export_chart.

    The app cannot use the strict guard — deleting a problem through the UI is
    supposed to shrink the file. So it protects exactly the titles this store has
    never held, and these two tests are the same call with the same store landing
    on opposite answers depending on that one set.
    """

    def _main(self):
        import app.main as main_mod
        return main_mod

    def test_a_node_this_store_never_held_survives_an_unrelated_edit(
            self, tmp_path, monkeypatch):
        main_mod = self._main()
        out = tmp_path / "chart.md"
        chart.export(_store(tmp_path, ["Alpha", "Beta"]), out)
        poor = _store(tmp_path / "other", ["Alpha"])    # Beta was never seeded here

        monkeypatch.setattr(main_mod, "CHART_EXPORT", out)
        monkeypatch.setattr(main_mod, "_SEEN_TITLES", {"Bearing", "Alpha"})
        main_mod._export_chart(poor)

        assert "Beta" in out.read_text(), "the mirror erased a node nobody deleted"

    def test_a_node_this_store_did_hold_is_allowed_to_go(self, tmp_path, monkeypatch):
        main_mod = self._main()
        out = tmp_path / "chart.md"
        chart.export(_store(tmp_path, ["Alpha", "Beta"]), out)
        poor = _store(tmp_path / "other", ["Alpha"])    # same store as above

        monkeypatch.setattr(main_mod, "CHART_EXPORT", out)
        monkeypatch.setattr(main_mod, "_SEEN_TITLES", {"Bearing", "Alpha", "Beta"})
        main_mod._export_chart(poor)

        assert "Beta" not in out.read_text(), "a deliberate delete was refused"

    def test_no_snapshot_falls_back_to_permissive(self, tmp_path, monkeypatch):
        """A guard that cannot tell the cases apart must not freeze the mirror.
        With no boot snapshot the old behaviour is correct: export anyway."""
        main_mod = self._main()
        out = tmp_path / "chart.md"
        chart.export(_store(tmp_path, ["Alpha", "Beta"]), out)
        poor = _store(tmp_path / "other", ["Alpha"])

        monkeypatch.setattr(main_mod, "CHART_EXPORT", out)
        monkeypatch.setattr(main_mod, "_SEEN_TITLES", None)
        main_mod._export_chart(poor)

        assert "Beta" not in out.read_text()


def test_allow_removals_is_how_a_real_delete_gets_through(tmp_path):
    """Deleting a problem through the app is supposed to shrink the file, so the
    escape hatch has to work — otherwise the guard would make deletion impossible
    and someone would remove the guard instead of using it."""
    out = tmp_path / "chart.md"
    chart.export(_store(tmp_path, ["Alpha", "Beta", "Gamma"]), out)

    poor = _store(tmp_path / "other", ["Alpha", "Beta"])
    chart.export(poor, out, allow_removals=True)

    assert "Gamma" not in out.read_text()
    assert "Alpha" in out.read_text()
