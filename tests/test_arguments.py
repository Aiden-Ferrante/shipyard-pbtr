"""Arguments: plain markdown, create-only scaffolds, guarded writes, read verdicts."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
_dir = tempfile.mkdtemp()
os.environ["SHIPYARD_DB"] = os.path.join(tempfile.mkdtemp(), "args.sqlite")
# Never let a test write the repo's real chart export or arguments —
# on 2026-08-06 they overwrote docs/chart.md with test fixtures.
os.environ["SHIPYARD_CHART_EXPORT"] = os.path.join(tempfile.mkdtemp(), "chart.md")
os.environ["SHIPYARD_ARGUMENTS_DIR"] = _dir

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app import arguments  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(scope="module", autouse=True)
def arguments_dir():
    """Patch the attribute and put it back (test_owed.fleet's shape). The old
    import-time rebind leaked this module's tempdir into every module collected
    after it — order-dependent state the suite only survived by accident."""
    previous = main.ARGUMENTS_DIR
    main.ARGUMENTS_DIR = Path(_dir)
    yield
    main.ARGUMENTS_DIR = previous


def mk(title, waypoint="a thing I could observe"):
    r = client.post("/api/problems", json={"title": title, "waypoint": waypoint})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_no_argument_is_a_normal_state():
    body = client.get(f"/api/problems/{mk('Unargued')}/argument").json()
    assert body["exists"] is False


def test_scaffold_anchors_on_the_waypoint():
    """v0.14.0 replaced the report layout with an argumentative essay: the waypoint
    now anchors the introduction rather than standing alone as a thesis heading."""
    pid = mk("Needs defending", "retention holds at 30 days")
    body = client.post(f"/api/problems/{pid}/argument").json()
    assert body["exists"] is True
    assert "retention holds at 30 days" in body["body"]
    assert "## Introduction" in body["body"] and "**Thesis.**" in body["body"]


def test_scaffold_never_overwrites_an_existing_essay():
    pid = mk("Already written")
    client.post(f"/api/problems/{pid}/argument")
    client.put(f"/api/problems/{pid}/argument",
               json={"body": "MY PROSE", "mtime": None})
    again = client.post(f"/api/problems/{pid}/argument").json()
    assert again["body"] == "MY PROSE", "create must not stamp over writing"


def test_write_then_read_round_trips():
    pid = mk("Round trip")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    saved = client.put(f"/api/problems/{pid}/argument",
                       json={"body": "# New\n\n## Verdict\nproxy\n", "mtime": cur["mtime"]})
    assert saved.status_code == 200
    assert client.get(f"/api/problems/{pid}/argument").json()["verdict"] == "proxy"


def test_stale_write_is_refused():
    """Someone else's editor wins by default; shipyard says so rather than clobbering."""
    pid = mk("Contested")
    client.post(f"/api/problems/{pid}/argument")
    r = client.put(f"/api/problems/{pid}/argument",
                   json={"body": "clobber", "mtime": 1.0})
    assert r.status_code == 409
    assert "changed on disk" in r.json()["detail"]


def test_verdict_mismatch_is_reported_not_applied():
    pid = mk("Disagrees")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    client.put(f"/api/problems/{pid}/argument",
               json={"body": "## Verdict\nobserved\n", "mtime": cur["mtime"]})

    body = client.get(f"/api/problems/{pid}/argument").json()
    assert body["verdict"] == "observed"
    assert body["sounding"] == "assumed"
    assert body["mismatch"] is True
    # the chart must be untouched by prose
    assert client.get(f"/api/chart/{pid}").json()["node"]["sounding"] == "assumed"


def test_unknown_verdict_word_is_ignored():
    assert arguments.verdict_of("## Verdict\nmaybe\n") is None
    assert arguments.verdict_of("## Verdict\nobserved\n") == "observed"


def test_filename_survives_a_rename():
    pid = mk("Original name")
    client.post(f"/api/problems/{pid}/argument")
    first = client.get(f"/api/problems/{pid}/argument").json()["name"]
    assert pid[:8] in first, "the id keeps the essay findable after a retitle"


def test_editor_link_template_is_filled():
    url = arguments.editor_link("vscode://file/{abspath}", Path("/tmp/x.md"))
    assert url == "vscode://file//tmp/x.md"
    assert arguments.editor_link(None, Path("/tmp/x.md")) is None


def test_dangling_frontmatter_is_refused():
    """The exact damage seen on 2026-08-06: an essay lost only its opening `---`,
    leaving the closing one behind.

    No write path in the app could be made to reproduce it, so instead of shipping
    an unverified explanation, the shape of the damage is refused.
    """
    pid = mk("Keeps its frontmatter")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    assert cur["body"].startswith("---\n")

    bad = client.put(f"/api/problems/{pid}/argument",
                     json={"body": "\nproblem: x\n---\n\n# gone\n", "mtime": cur["mtime"]})
    assert bad.status_code == 409
    assert "frontmatter" in bad.json()["detail"]

    # and the file on disk is untouched
    assert client.get(f"/api/problems/{pid}/argument").json()["body"].startswith("---\n")


def test_a_normal_edit_still_saves():
    pid = mk("Edits fine")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    ok = client.put(f"/api/problems/{pid}/argument",
                    json={"body": cur["body"] + "\nreal writing\n", "mtime": cur["mtime"]})
    assert ok.status_code == 200
    assert "real writing" in client.get(f"/api/problems/{pid}/argument").json()["body"]


def test_deleting_the_whole_block_is_still_allowed():
    """The guard rejects half a frontmatter block, not the decision to drop it."""
    pid = mk("Drops it on purpose")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    ok = client.put(f"/api/problems/{pid}/argument",
                    json={"body": "# just prose\n\nno frontmatter at all\n",
                          "mtime": cur["mtime"]})
    assert ok.status_code == 200


def test_scaffold_is_an_argument_not_a_report():
    """A report lists evidence and commits to nothing; an essay states a thesis and
    defends it in parts."""
    pid = mk("Structured", "a thing I could observe")
    body = client.post(f"/api/problems/{pid}/argument").json()["body"]
    for section in ("## Introduction", "**Thesis.**", "## Conclusion", "## Verdict"):
        assert section in body, section
    assert body.index("## Introduction") < body.index("## Conclusion")
    assert "a thing I could observe" in body, "the waypoint anchors the introduction"


def test_scaffold_without_a_waypoint_asks_for_one():
    r = client.post("/api/problems", json={"title": "Undecided", "waypoint": "", "draft": True})
    body = client.post(f"/api/problems/{r.json()['id']}/argument").json()["body"]
    assert "No waypoint yet" in body


# ---------- at-a-glance summary ----------

ESSAY = """---
problem: x
title: Demo
---

# Demo

## Introduction

Some context here.

**Thesis.**

1. The first position, which is a claim not a topic.
2. The second position, with a [link](https://example.com/paper) inside it.
3. The third position.

## 1. The first position

**Robust.** A large replicated finding, n = 400,000.

## 2. The second position

**Weak/contested.** A popular claim resting on 47 couples.

## Conclusion

Wrapping up.
"""


def test_summary_extracts_the_thesis():
    from app import arguments as A
    out = A.summarise(ESSAY)
    assert len(out["thesis"]) == 3
    assert out["thesis"][0].startswith("The first position")
    assert "link" in out["thesis"][1] and "https://" not in out["thesis"][1], \
        "markdown links collapse to their words"


def test_summary_extracts_tagged_evidence():
    from app import arguments as A
    out = A.summarise(ESSAY)
    tags = [e["tag"] for e in out["evidence"]]
    assert tags == ["robust", "weak/contested"]
    assert "400,000" in out["evidence"][0]["text"]


def test_summary_ignores_scaffold_placeholders():
    """A scaffold's italic prompts are not claims. Showing them in the rail dressed
    as conclusions is worse than showing nothing."""
    from app import arguments as A
    pid = mk("Bare", "an observable")
    body = client.post(f"/api/problems/{pid}/argument").json()["body"]
    assert "_First claim._" in body, "the scaffold does still prompt"
    assert A.summarise(body)["thesis"] == []


def test_api_carries_the_summary():
    pid = mk("Summarised", "an observable")
    client.post(f"/api/problems/{pid}/argument")
    cur = client.get(f"/api/problems/{pid}/argument").json()
    client.put(f"/api/problems/{pid}/argument", json={"body": ESSAY, "mtime": cur["mtime"]})
    body = client.get(f"/api/problems/{pid}/argument").json()
    assert len(body["thesis"]) == 3
    assert body["evidence"][0]["tag"] == "robust"


def test_a_mid_sentence_tag_yields_a_whole_sentence():
    """A tag written inside a sentence must not produce a dangling fragment —
    a fragment in the rail is worse than no bullet at all."""
    from app import arguments as A
    body = ("**Thesis.**\n\n1. A claim.\n\n## 1. A claim\n\n"
            "Returns diminish with income; treat that as **robust** for planning.\n")
    ev = A.summarise(body)["evidence"]
    assert len(ev) == 1
    assert ev[0]["text"].startswith("Returns diminish")
    assert ev[0]["tag"] == "robust"


def test_tag_punctuation_is_normalised():
    from app import arguments as A
    body = "x\n\n**Weak/contested:** the three needs are not separable in the meta-analysis.\n"
    assert A.summarise(body)["evidence"][0]["tag"] == "weak/contested"


def test_leading_tags_are_preferred_over_incidental_ones():
    from app import arguments as A
    body = ("Some prose that mentions **mixed** evidence somewhere in the middle here.\n"
            "**Robust.** A deliberate annotation with a real finding behind it.\n")
    ev = A.summarise(body, max_evidence=1)
    assert ev["evidence"][0]["tag"] == "robust"


def test_the_tag_word_is_not_repeated_in_the_text():
    """The chip already says it; repeating it wastes the only line the rail has."""
    from app import arguments as A
    ev = A.summarise("**Robust.** A three-year RCT of 1,000 adults found no lasting effect.\n")
    assert ev["evidence"][0]["tag"] == "robust"
    assert ev["evidence"][0]["text"].startswith("A three-year RCT")


def test_a_dash_after_the_tag_is_stripped_too():
    """`**Mixed** — modest effect` must not surface as a bullet starting with a dash."""
    from app import arguments as A
    ev = A.summarise("**Mixed** — a modest effect from early-2010s social psychology work.\n")
    assert ev["evidence"][0]["text"].startswith("a modest effect")


def test_a_stamped_claim_reads_backwards_not_forwards():
    """The essays use three tag shapes and only one points forward.

    A *stamp* grades the sentence it closes — "…means. **Robust**, with the caveat…" —
    so reading forward returns the caveat and silently drops the claim it was grading.
    """
    from app import arguments as A
    body = ("A residual cannot attribute a share to a named person. **Robust**, with "
            "the standard objection that attribution was never the point.\n")
    text = A.summarise(body)["evidence"][0]["text"]
    assert text.startswith("A residual cannot attribute")
    assert "standard objection" in text, "the caveat rides along, it does not replace"


def test_a_predicate_tag_keeps_the_sentence_around_it():
    from app import arguments as A
    body = "Adaptation is asymmetric, and that is **robust** for direction and persistence.\n"
    assert A.summarise(body)["evidence"][0]["text"].startswith("Adaptation is asymmetric")


def test_hard_wrapping_does_not_truncate_a_bullet():
    """Where an essay wraps is an accident of whoever typed it — some of these files
    wrap at ~95 columns and some keep a paragraph on one line. A line-based reader
    turns that accident into bullet quality, ending them mid-phrase."""
    from app import arguments as A
    body = ("**Robust.** Modest effect, early-2010s social psychology — but a hazard\n"
            "specific to goals that are pursued explicitly rather than held loosely.\n")
    text = A.summarise(body)["evidence"][0]["text"]
    assert text.endswith("held loosely."), text
    assert "hazard specific to goals" in text, "the wrap must not survive into the bullet"


def test_a_wrapped_thesis_claim_is_joined():
    """Thesis claims wrap across lines in every real essay. Reading only the first
    line cut them mid-phrase — "…measured by an instrument too thin and"."""
    from app import arguments as A
    body = ("**Thesis.**\n\n"
            "1. The outcome is measured by an instrument too thin and\n"
            "   too noisy to steer by.\n"
            "2. The second claim.\n\n"
            "## 1. Something\n")
    t = A.summarise(body)["thesis"]
    assert t[0] == "The outcome is measured by an instrument too thin and too noisy to steer by."
    assert t[1] == "The second claim."


def test_two_labels_in_one_paragraph_yield_two_bullets():
    """A label stops at the next label, so they do not run together."""
    from app import arguments as A
    body = ("**Robust.** The first finding, replicated across four panels.\n"
            "**Mixed.** The second finding, resting on one small sample.\n")
    ev = A.summarise(body)["evidence"]
    assert [e["tag"] for e in ev] == ["robust", "mixed"]
    assert ev[0]["text"].startswith("The first finding")
    assert "second finding" not in ev[0]["text"]
