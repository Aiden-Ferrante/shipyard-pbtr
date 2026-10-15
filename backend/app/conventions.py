"""The conventions this fleet actually runs on, and which of them have teeth.

**This is not `standards.yaml`, and the difference is the whole design.** That file
was deleted in v0.5.0 because it scored repos against a checklist, and conformance
was never the point — `ARCHITECTURE.md` still says shipyard is not a compliance
enforcer, and that stands. Nothing here reads a repo, ranks one, or reports whether
one complies. It describes the *standards themselves*: what each one is, where it
lives, and what — if anything — makes it more than prose.

The column that earns the surface is **enforcement**, and the rule it comes from is
already written in `docs/census/DECISIONS.md`:

    Anything a linter can enforce becomes a checker rule and is deleted from
    CONVENTIONS.md. A convention stated in prose *and* enforced in code trains
    everyone to read the prose as advisory.

So a standard with no enforcer is not a failure — some should never have one, and
the templates say so themselves. It is a *fact worth seeing*, because a convention
you believe is holding and nothing checks is the one that has already drifted. The
fleet learned that twice: the palette was converged by hand and drifted back within
days, and `check.sh` sat passing for weeks because nothing ran it.

**Declared, plus derived where derivation is honest.** The list of standards is
written here, because no file on disk enumerates "the fleet has a health convention"
— that is a fact about a practice, not about a path. But every path is *checked*, so
a standard whose file has moved reads as missing rather than silently fine, and the
counted ones (templates, ADRs) are counted from disk rather than from memory.

Cross-repo paths are allowed to be absent: a clone of shipyard alone must still
answer, the same rule `test_fleet_drift.py` applies to the checker it runs.
"""

from pathlib import Path

# `enforcer` is the name of the thing that would fail, or None for prose. `derive`
# names an optional callback key resolved in `read()` — kept out of the table so the
# table stays a readable declaration rather than a pile of lambdas.
_STANDARDS = [
    {
        "id": "fleet-visual",
        "title": "One visual contract",
        "what": "Colour tokens, the six-step type scale and the header shell, shared "
                "by every admin surface so moving between them reads as one site.",
        "where": "../fleet-ui/fleet.css",
        "enforcer": "check.sh",
        "enforcer_where": "../fleet-ui/check.sh",
        "note": "Adopted by aliasing, never renaming: an app points its own token "
                "names at fleet's, so existing rules keep working and the source of "
                "truth moves in one edit.",
    },
    {
        "id": "fleet-registry",
        "title": "One app registry",
        "what": "Who exists and on what port, as ports rather than URLs, resolved "
                "against whoever is reading the page.",
        "where": "../fleet-ui/apps.js",
        "enforcer": "check.sh",
        "enforcer_where": "../fleet-ui/check.sh",
        "note": "Duplicated into three hand-maintained copies on purpose — a header "
                "must render before any fetch resolves. The checker is what keeps "
                "the copies honest, and it derives its expectation from apps.js at "
                "run time, so a seventh app demands itself with no edit.",
    },
    {
        "id": "manifest",
        "title": "A repo describes itself",
        "what": "PROJECT.yaml carries id, name, description and links — plus "
                "release: and chart: to declare what a repo does not owe.",
        "where": "PROJECT.yaml",
        "enforcer": None,
        "note": "Partly specified by ADR 0004. Nothing validates the schema; a "
                "malformed manifest is logged and skipped rather than refused, so a "
                "typo removes a repo from the board silently.",
    },
    {
        "id": "architecture",
        "title": "Boundaries, on one page",
        "what": "One ARCHITECTURE.md per repo, boundaries first, derived from the "
                "code rather than remembered.",
        "where": "ARCHITECTURE.md",
        "enforcer": None,
        "note": "The backend's star rule — no domain module imports another — holds "
                "by discipline. The doc itself names that as unenforced and says "
                "what the test would look like.",
    },
    {
        "id": "health",
        "title": "One health shape",
        "what": "{ok, checks, freshness} from every service that answers /health, so "
                "one renderer can draw any of them.",
        "where": None,
        "enforcer": None,
        "note": "Five adopters across the fleet, drawn differently in each. The "
                "convention is real and nothing checks it.",
    },
    {
        "id": "branching",
        "title": "main is prod, dev is the workbench",
        "what": "Two long-lived branches. Promotion is a merge, gated on the suite "
                "passing and the app booting.",
        "where": "docs/adr/0002-branching-model.md",
        "enforcer": None,
        "note": "Named in ADR 0002 as a candidate fleet default once proven on a "
                "second repo.",
    },
    {
        "id": "templates",
        "title": "Starting shapes",
        "what": "Chart shapes to instantiate a project from — problems, a document, "
                "or both.",
        "where": "templates/",
        "enforcer": None,
        "note": "Unenforced BY DESIGN, and they say so in their own first line: a "
                "starting shape, never a standard, and an instantiated copy forgets "
                "it. This row is the one where 'no enforcer' is the correct state.",
        "derive": "templates",
    },
    {
        "id": "decisions",
        "title": "Decisions are written down",
        "what": "An ADR per architectural decision, with the rejected alternative "
                "and its reason kept.",
        "where": "docs/adr/",
        "enforcer": None,
        "note": "The rule that governs the set: anything a linter can enforce "
                "becomes a checker rule and leaves the prose.",
        "derive": "adrs",
    },
]


def _items(root: Path, rel: str, suffix: str) -> list[str]:
    d = root / rel
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob(f"*{suffix}"))


def read(root: Path) -> dict:
    """Every standard, with its paths resolved against `root`.

    `present` is the derived half and the reason this is not a static document: a
    standard whose file has been moved or deleted reads as missing here, which is
    the one way this surface can catch drift without ever looking at a repo.
    """
    root = Path(root)
    out = []
    for s in _STANDARDS:
        # Every key on every row, defaulted rather than omitted. A row missing
        # `enforcer_where` because it never claimed one, and a row missing it
        # because the declaration is malformed, are indistinguishable to a caller —
        # and the second is exactly the rot this surface exists to expose.
        row = {"id": s["id"], "title": s["title"], "what": s["what"],
               "where": s.get("where"), "enforcer": s.get("enforcer"),
               "enforcer_where": s.get("enforcer_where"), "note": s.get("note")}
        where = s.get("where")
        row["present"] = None if where is None else (root / where).exists()
        ew = s.get("enforcer_where")
        # An enforcer named but missing is worse than one never claimed: the rule
        # reads as covered while nothing runs. Reported separately from `present`.
        row["enforcer_present"] = None if ew is None else (root / ew).exists()
        if s.get("derive") == "templates":
            row["items"] = _items(root, "templates", ".yaml")
        elif s.get("derive") == "adrs":
            row["items"] = _items(root, "docs/adr", ".md")
        else:
            row["items"] = None
        out.append(row)
    enforced = sum(1 for r in out if r["enforcer"])
    return {
        "standards": out,
        "enforced": enforced,
        "prose": len(out) - enforced,
    }
