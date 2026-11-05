"""The chart — a DAG of problems, and the spine view over it.

One node type. A `rung`, a `lens` and a `subproblem` are all just problems; what
distinguishes them is the direction of an edge, not a type. A problem with a `repo`
is a project.

Vocabulary (vault `7.) Chart Vocabulary`):
  bearing   a problem sitting above another — what that one serves
  anchor    a problem deliberately frozen; `anchored_at` + `anchor_basis` set
  waypoint  the observable that says a problem is moving — required
  sounding  evidence behind the waypoint: assumed | proxy | observed
  drift     a problem serving no bearing

Storage decision and its exception are recorded in docs/adr/0003-chart-storage.md.
"""

import re
import sqlite3
import time
import uuid
from typing import Any

SOUNDINGS = ("assumed", "proxy", "observed")
_RANK = {s: i for i, s in enumerate(SOUNDINGS)}


def init(con: sqlite3.Connection) -> None:
    # sqlite ships with foreign keys OFF, so every ON DELETE CASCADE in this
    # schema was decorative: deleting a problem orphaned its edges and (from
    # v0.20.0) its approaches. Per-connection, so it belongs here rather than
    # in the schema. Found by the approaches cascade test.
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("""CREATE TABLE IF NOT EXISTS problems (
        id           TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        waypoint     TEXT NOT NULL,
        sounding     TEXT NOT NULL DEFAULT 'assumed',
        repo         TEXT,
        anchored_at  TEXT,
        anchor_basis TEXT,
        falsifier    TEXT,
        reasoning    TEXT,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS problem_edges (
        child_id  TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
        parent_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
        PRIMARY KEY (child_id, parent_id))""")
    # Added in v0.9.0; existing databases predate the column.
    cols = {r[1] for r in con.execute("PRAGMA table_info(problems)")}
    if "reasoning" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN reasoning TEXT")
    # v0.17.0: which goals head the board. Deliberately separate from being a root —
    # a chart deep enough to be useful has one root and fifty descendants, so "root"
    # stopped being a useful heading the moment the chart got real.
    if "pinned" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    # The problem's own page needs somewhere to put prose. Columns rather than a
    # file per problem: they are edited in the same form as the waypoint, and the
    # existing one-way export carries them into docs/chart.md, so they are still
    # versioned in git without a second markdown system beside docs/arguments.
    #
    # Distinct from `reasoning`, which is the argument page's field for why the
    # problem is framed the way it is. `description` says what the problem IS;
    # `notes` is whatever you learn while working it.
    for col in ("description", "notes"):
        if col not in cols:
            con.execute(f"ALTER TABLE problems ADD COLUMN {col} TEXT")
    # v0.28.0 (ADR 0004): a target — when the waypoint should be met, and inside what
    # budget. Here rather than on the repo because the waypoint already says what
    # finishing *means*; a date parked on a repo would be a deadline with no
    # definition of done, which is the failure `waypoint NOT NULL` exists to prevent.
    #
    # `appetite` is a budget the work must fit inside, never a predicted finish —
    # a repo that overruns is shown over its box, and the response is to cut scope.
    # Both nullable: most problems never carry a date, and a default would invent one.
    for col in ("due", "appetite"):
        if col not in cols:
            con.execute(f"ALTER TABLE problems ADD COLUMN {col} TEXT")
    # v0.18.0: which finished cycles ran against a problem. Deliberately "addressed
    # by" and not "solved by" — whether the work landed is the sounding's job, so
    # "three cycles, still assumed" stays a visible and useful state rather than
    # being collapsed into a tick.
    con.execute("""CREATE TABLE IF NOT EXISTS problem_cycles (
        problem_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
        version    TEXT NOT NULL,
        PRIMARY KEY (problem_id, version))""")
    # Versions are canonically stored without the `v`, which is the form git tags
    # arrive in. Rows written before that was enforced are normalised in place;
    # idempotent, so it costs one cheap UPDATE on every open.
    con.execute("UPDATE OR IGNORE problem_cycles SET version = ltrim(version, 'v') "
                "WHERE version LIKE 'v%'")
    con.execute("DELETE FROM problem_cycles WHERE version LIKE 'v%'")
    # v0.20.0: the loop, attached to the problem rather than to the project.
    #
    # Note the tension with the v0.18.0 note above, which said "addressed by" and not
    # "solved by" on the grounds that whether the work landed is the sounding's job.
    # That held while the sounding was the surface you read. It is not any more — the
    # board and the hub show phases and a tick, not a grade — so `solved` now carries
    # that meaning explicitly. The sounding still exists and still means what it meant;
    # it just stopped being the thing asked to answer "is this done".
    #
    # Manual, except `phase_build`: that one is derived from the repo's commits and is
    # never written here (goal-prompt D2 — derived beats entered wherever git can
    # answer honestly). It is absent from this table on purpose.
    for col in ("phase_plan", "phase_test", "phase_review", "solved"):
        if col not in cols:
            con.execute(f"ALTER TABLE problems ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    if "solved_at" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN solved_at TEXT")

    # v0.27.0: WHEN a phase was ticked, not just whether. The booleans above answer
    # "where is this" and nothing answers "how long was it there" — every other
    # surface in this app is a state snapshot, so flow was not merely unmeasured, it
    # was unanswerable. `solved_at` and `active_at` were already timestamped; these
    # three close the gap for the stations themselves.
    #
    # Nullable and cleared on untick: a timestamp left behind by an untick would
    # claim a transition that was taken back, and a wrong date is worse than none.
    for col in ("phase_plan_at", "phase_test_at", "phase_review_at"):
        if col not in cols:
            con.execute(f"ALTER TABLE problems ADD COLUMN {col} TEXT")

    # The focus slot. A goal chart lists everything that matters and so says nothing
    # about what is being worked on now — HOI4's tree is legible partly because
    # exactly one focus is running and the rest visibly are not. Scarcity is the
    # whole mechanic, and it is enforced per pinned domain (see `focus_slots`)
    # rather than stored as a count that could drift from the rows it describes.
    if "active" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN active INTEGER NOT NULL DEFAULT 0")
    if "active_at" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN active_at TEXT")

    # Approaches considered, and which one is being taken. A verdict outlives the
    # choice moving on: an approach you tried and that failed is the most valuable
    # row here, so `chosen` flipping to another row must never erase it.
    con.execute("""CREATE TABLE IF NOT EXISTS problem_approaches (
        id         TEXT PRIMARY KEY,
        problem_id TEXT NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
        name       TEXT NOT NULL,
        rationale  TEXT,
        chosen     INTEGER NOT NULL DEFAULT 0,
        verdict    TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_approaches_problem "
                "ON problem_approaches(problem_id)")

    con.execute("CREATE INDEX IF NOT EXISTS ix_edges_parent ON problem_edges(parent_id)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_problems_repo ON problems(repo)")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ChartError(ValueError):
    """Rejected write — the caller sent something the chart won't hold."""


# ---------- writes ----------

def _repo_owner(con: sqlite3.Connection, repo: str | None,
                besides: str | None = None) -> str | None:
    """Who already holds this repo, if anyone. `besides` exempts the problem being
    written, so re-linking a repo to the problem that already carries it is a no-op
    rather than a clash.

    A repo is attacked by exactly one problem. Two nodes carrying the same repo do
    not read as an ambiguity — they render as the *same project card*, once per node,
    which is how seven copies of one project appeared on the board on 2026-08-25.
    """
    if not repo:
        return None
    row = con.execute("SELECT id FROM problems WHERE repo=? AND id<>?",
                      (repo, besides or "")).fetchone()
    return row[0] if row else None


def create_problem(con: sqlite3.Connection, *, title: str, waypoint: str,
                   sounding: str = "assumed", repo: str | None = None,
                   anchored_at: str | None = None, anchor_basis: str | None = None,
                   falsifier: str | None = None, reasoning: str | None = None,
                   description: str | None = None, notes: str | None = None,
                   parent_id: str | None = None, child_id: str | None = None,
                   draft: bool = False) -> str:
    """Create one problem, optionally wiring it straight to a neighbour.

    `parent_id` is the ↑ case (this problem serves that one); `child_id` is the ↓
    case (that problem serves this one).

    `draft=True` is the outline's opt-out from the waypoint requirement. You cannot
    demand an observable between pressing Enter and having the next thought, so fast
    capture is allowed to defer it — but a draft is visibly flagged and can never be
    linked to a repo. The rule survives where it matters: no unfalsifiable problem
    becomes real work.
    """
    title = (title or "").strip()
    waypoint = (waypoint or "").strip()
    if not title:
        raise ChartError("a problem needs a title")
    if not waypoint and not draft:
        # The whole point of the chart: a problem with no observable is a category.
        raise ChartError("a problem needs a waypoint — what would you observe if it were working?")
    if sounding not in SOUNDINGS:
        raise ChartError(f"sounding must be one of {', '.join(SOUNDINGS)}")
    # Checked here and not only in `link_repo`: creating with a repo is a second door
    # onto the same invariant, and both `scripts/seed_chart.py` and POST /api/problems
    # come through it.
    if _repo_owner(con, repo):
        raise ChartError(f"'{repo}' is already linked to another problem")

    pid = uuid.uuid4().hex[:12]
    now = _now()
    con.execute(
        """INSERT INTO problems (id, title, waypoint, sounding, repo,
                                 anchored_at, anchor_basis, falsifier, reasoning,
                                 description, notes, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, title, waypoint, sounding, repo, anchored_at, anchor_basis,
         falsifier, reasoning, description, notes, now, now))
    if parent_id:
        add_edge(con, child_id=pid, parent_id=parent_id)
    if child_id:
        add_edge(con, child_id=child_id, parent_id=pid)
    return pid


EDITABLE = ("title", "waypoint", "sounding", "falsifier", "reasoning",
            "description", "notes")


def update_problem(con: sqlite3.Connection, pid: str, **fields) -> None:
    """Edit a problem in place. A chart you can only add to is a document, and
    documents rot — the sounding in particular has to be able to move when evidence
    finally shows up."""
    if not get(con, pid):
        raise ChartError(f"no such problem '{pid}'")
    sets, vals = [], []
    for key in EDITABLE:
        if key not in fields or fields[key] is None:
            continue
        val = fields[key]
        if key == "title":
            val = str(val).strip()
            if not val:
                raise ChartError("title cannot be blank")
        if key == "waypoint":
            # Blank is allowed here so a draft can be edited without being forced to
            # graduate; it simply stays a draft.
            val = str(val).strip()
        if key == "sounding" and val not in SOUNDINGS:
            raise ChartError(f"sounding must be one of {', '.join(SOUNDINGS)}")
        sets.append(f"{key}=?")
        vals.append(val)
    if not sets:
        return
    sets.append("updated_at=?")
    vals += [_now(), pid]
    con.execute(f"UPDATE problems SET {', '.join(sets)} WHERE id=?", vals)


def freeze(con: sqlite3.Connection, pid: str, *, basis: str,
           falsifier: str | None = None, when: str | None = None) -> None:
    """Stop litigating this problem — deliberately, and on the record.

    An anchor is a *decision*, not a fact: it gets a date and a basis so that new
    evidence can thaw it later. The failure this prevents is an invisible belief
    (the lane-ladder's "I work best on one thing at a time") outliving its evidence.
    """
    if not get(con, pid):
        raise ChartError(f"no such problem '{pid}'")
    basis = (basis or "").strip()
    if not basis:
        raise ChartError("freezing needs a basis — why are you willing to stop questioning it?")
    con.execute(
        """UPDATE problems SET anchored_at=?, anchor_basis=?,
           falsifier=COALESCE(?, falsifier), updated_at=? WHERE id=?""",
        (when or time.strftime("%Y-%m-%d"), basis, falsifier, _now(), pid))


def thaw(con: sqlite3.Connection, pid: str) -> None:
    """Un-freeze. Deliberately keeps `anchor_basis` and `falsifier` — the record of
    what was believed and why is the whole point; only the frozen *state* clears."""
    if not get(con, pid):
        raise ChartError(f"no such problem '{pid}'")
    con.execute("UPDATE problems SET anchored_at=NULL, updated_at=? WHERE id=?",
                (_now(), pid))


def impact(con: sqlite3.Connection, pid: str) -> dict:
    """What rests on this problem, and what would survive it being thawed.

    A descendant with a bearing *outside* this subtree keeps its justification; one
    without falls to drift. That asymmetry is the argument for second parents, so it
    is the number worth showing before anyone clicks thaw.
    """
    node = get(con, pid)
    if not node:
        raise ChartError(f"no such problem '{pid}'")

    subtree: dict[str, dict] = {}

    def collect(nid: str) -> None:
        for kid in children(con, nid):
            if kid["id"] in subtree:
                continue
            subtree[kid["id"]] = kid
            collect(kid["id"])

    collect(pid)

    # Survival is transitive, not a one-level check: a node is still justified if ANY
    # path upward reaches a bearing without passing through the thawed problem. A
    # child of a surviving project survives too — getting this wrong reported a whole
    # healthy subtree as orphaned.
    verdict: dict[str, list[str]] = {}

    def kept_by(nid: str, path: frozenset[str]) -> list[str]:
        if nid in verdict:
            return verdict[nid]
        if nid in path:                    # cycle — no independent justification here
            return []
        holders: list[str] = []
        for p in parents(con, nid):
            if p["id"] == pid:
                continue
            if p["id"] not in subtree:
                holders.append(p["title"])          # a bearing outside the blast radius
            elif kept_by(p["id"], path | {nid}):
                holders.append(p["title"])          # held up by something that survives
        verdict[nid] = holders
        return holders

    survives, orphaned = [], []
    for nid, n in subtree.items():
        holders = kept_by(nid, frozenset())
        (survives if holders else orphaned).append({**n, "kept_by": holders})

    return {
        "node": node,
        "affected": len(subtree),
        "projects": [n for n in subtree.values() if n.get("repo")],
        "survives": survives,
        "orphaned": orphaned,
    }


def remove_parent(con: sqlite3.Connection, *, child_id: str, parent_id: str) -> None:
    """Detach one bearing, leaving any others. Dropping the last one is allowed —
    that makes it a top-level goal, which is a legitimate place to be."""
    if not get(con, child_id):
        raise ChartError(f"no such problem '{child_id}'")
    con.execute("DELETE FROM problem_edges WHERE child_id=? AND parent_id=?",
                (child_id, parent_id))


def set_parent(con: sqlite3.Connection, *, child_id: str, parent_id: str | None) -> None:
    """Re-parent: what this problem is *for* changes.

    Replaces every existing edge rather than adding one, because dragging a card
    between sections means "it serves this instead", not "it also serves this".
    Multi-parent is still reachable through `add_edge`; this is the board's verb.
    `parent_id=None` makes it a root — a top-level bearing, not an orphan.
    """
    if not get(con, child_id):
        raise ChartError(f"no such problem '{child_id}'")
    if parent_id is not None:
        if child_id == parent_id:
            raise ChartError("a problem cannot serve itself")
        if not get(con, parent_id):
            raise ChartError(f"no such problem '{parent_id}'")
        # A cycle means the proposed parent already sits *below* the child, so
        # attaching would close the loop. Walk down from the child, not the parent.
        if _reaches(con, child_id, parent_id):
            raise ChartError("that would make a loop — the parent already serves this problem")
    con.execute("DELETE FROM problem_edges WHERE child_id=?", (child_id,))
    if parent_id is not None:
        con.execute("INSERT INTO problem_edges (child_id, parent_id) VALUES (?,?)",
                    (child_id, parent_id))


def _reaches(con: sqlite3.Connection, start: str, target: str,
             _seen: set[str] | None = None) -> bool:
    """Is `target` at or below `start`?"""
    if start == target:
        return True
    _seen = _seen or set()
    if start in _seen:
        return False
    _seen.add(start)
    return any(_reaches(con, k["id"], target, _seen) for k in children(con, start))


def link_repo(con: sqlite3.Connection, pid: str, repo: str | None) -> None:
    """Promote a problem to a project by attaching a repo — or demote by clearing it.

    This is the moment a decomposition stops being reasoning and becomes work.
    """
    node = get(con, pid)
    if not node:
        raise ChartError(f"no such problem '{pid}'")
    if repo and node["draft"]:
        raise ChartError(
            "give it a waypoint first — you cannot attack a problem you can't tell you've solved")
    if _repo_owner(con, repo, besides=pid):
        raise ChartError(f"'{repo}' is already linked to another problem")
    con.execute("UPDATE problems SET repo=?, updated_at=? WHERE id=?",
                (repo or None, _now(), pid))


def delete_subtree(con: sqlite3.Connection, pid: str) -> dict:
    """Delete a problem and everything that only existed to serve it.

    Reuses `impact`: a descendant that still reaches a bearing outside this subtree
    keeps its justification and is spared, while one whose only path up went through
    here goes with it. So deleting a branch removes the branch, not other people's
    work that happened to hang off it.
    """
    view = impact(con, pid)
    doomed = [n["id"] for n in view["orphaned"]] + [pid]
    titles = [n["title"] for n in view["orphaned"]]
    for nid in doomed:
        con.execute("DELETE FROM problem_edges WHERE child_id=? OR parent_id=?", (nid, nid))
        con.execute("DELETE FROM problem_cycles WHERE problem_id=?", (nid,))
        con.execute("DELETE FROM problems WHERE id=?", (nid,))
    return {
        "deleted": view["node"]["title"],
        "also_deleted": titles,
        "spared": [n["title"] for n in view["survives"]],
        "count": len(doomed),
    }


def delete_problem(con: sqlite3.Connection, pid: str) -> dict:
    """Remove one problem. Its children are **promoted**, never destroyed.

    Deleting a rung should not silently take everything below it with it — that is
    a whole branch of recorded reasoning disappearing behind one click. So children
    re-attach to this problem's parents, or become roots if it had none. To remove a
    subtree, delete it from the bottom up, which forces you to see each part.

    A linked repo is untouched; the project simply becomes uncharted again.
    """
    node = get(con, pid)
    if not node:
        raise ChartError(f"no such problem '{pid}'")
    kids = children(con, pid)
    grandparents = parents(con, pid)

    for kid in kids:
        con.execute("DELETE FROM problem_edges WHERE child_id=? AND parent_id=?",
                    (kid["id"], pid))
        for gp in grandparents:
            con.execute(
                "INSERT OR IGNORE INTO problem_edges (child_id, parent_id) VALUES (?,?)",
                (kid["id"], gp["id"]))

    con.execute("DELETE FROM problem_edges WHERE child_id=? OR parent_id=?", (pid, pid))
    # sqlite does not enforce ON DELETE CASCADE unless foreign keys are switched
    # on, and this function has always cleared edges by hand for that reason. The
    # cycle links need the same treatment or a deleted problem leaves them behind.
    con.execute("DELETE FROM problem_cycles WHERE problem_id=?", (pid,))
    con.execute("DELETE FROM problems WHERE id=?", (pid,))
    return {
        "deleted": node["title"],
        "promoted": [k["title"] for k in kids],
        "promoted_to": [g["title"] for g in grandparents] or None,
        "freed_repo": node.get("repo"),
    }


def deletion_impact(con: sqlite3.Connection, pid: str) -> dict:
    """What deleting would do — shown before the button, never after."""
    node = get(con, pid)
    if not node:
        raise ChartError(f"no such problem '{pid}'")
    kids = children(con, pid)
    gps = parents(con, pid)
    view = impact(con, pid)
    return {
        "title": node["title"],
        "children": [k["title"] for k in kids],
        "new_parents": [g["title"] for g in gps],
        "becomes_root": bool(kids) and not gps,
        "repo": node.get("repo"),
        # what the cascade option would take, so both choices state their cost
        "cascade_count": len(view["orphaned"]) + 1,
        "cascade_spared": [n["title"] for n in view["survives"]],
    }


def roots(con: sqlite3.Connection) -> list[dict]:
    """Parentless problems — the board's sections.

    Self-organising on purpose: add a parent above two roots and they stop being
    sections, merging into the new one. The board always shows the highest level
    currently being organised by.
    """
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT * FROM problems
           WHERE id NOT IN (SELECT child_id FROM problem_edges)
           ORDER BY created_at""").fetchall()
    return [_row(r) for r in rows]


def descendants(con: sqlite3.Connection, pid: str,
                _seen: set[str] | None = None) -> list[dict]:
    """Everything below a problem, deduped, excluding itself."""
    _seen = _seen if _seen is not None else set()
    out = []
    for kid in children(con, pid):
        if kid["id"] in _seen:
            continue
        _seen.add(kid["id"])
        out.append(kid)
        out.extend(descendants(con, kid["id"], _seen))
    return out


ROLE_BUMP = {"bearing": "major", "branch": "minor", "leaf": "patch"}


def role(con: sqlite3.Connection, pid: str) -> str:
    """Where a problem sits, which is the claim its cycle makes about scope.

    Small cycles compose into big ones, so the shape of the tree already says which
    kind a problem's cycle is: a leaf is one run against one observable, a branch
    closes only when the things beneath it have, and a parentless bearing is the arc
    they all serve. That is the same super/sub/light vocabulary `repo.cycles` reads
    off a version number, arrived at from the other side.
    """
    if not parents(con, pid):
        return "bearing"
    return "branch" if children(con, pid) else "leaf"


def versions_claimed_in(con: sqlite3.Connection, repo: str) -> list[str]:
    """Every version spoken for in one repo's line, by any problem.

    Scoped to the repo rather than to the problem, because a version number is only
    unique within a repo: two sibling problems opening cycles would each see the
    same latest tag and propose the same next version, and the collision would only
    surface when the second one tried to write a record file.
    """
    out: set[str] = set()
    for pid, versions in all_addressed(con).items():
        if repo in nearest_repos(con, pid):
            out.update(versions)
    return sorted(out)


def cycle_composition(con: sqlite3.Connection, pid: str) -> dict:
    """How much of a problem's cycle its children already account for.

    Reported, never enforced. A parent cycle opened over children that have none is
    a legible state — sometimes the parent is the work — and the point is that you
    can see it rather than that shipyard can veto it.
    """
    kids = children(con, pid)
    with_cycles = [k for k in kids if addressed_by(con, k["id"])]
    return {"children": len(kids), "with_cycles": len(with_cycles),
            "missing": [k["title"] for k in kids if not addressed_by(con, k["id"])]}


def nearest_repos(con: sqlite3.Connection, pid: str,
                  _seen: set[str] | None = None) -> list[str]:
    """The repos whose cycles can address this problem.

    A problem carrying a repo answers for itself. One that does not — a goal above
    the project layer — inherits from the *nearest* repo down each branch, stopping
    at the first one found rather than collecting the whole subtree.

    That stop matters. A big PBTR cycle is made of the small ones directly beneath
    it, so "<personal goal>" should offer crossfolio's tags and not also every tag
    of everything crossfolio itself decomposes into; collecting the transitive set
    would put a leaf's patch release in the picker for the root bearing, which is
    the composition read backwards.

    **Nothing below, so look above (v0.31.1).** A problem *beneath* the project node
    — one of the sub-problems the project decomposes into — has no repo below it and
    had none of its own, because `_repo_owner` gives a repo to exactly one problem
    and that problem is the project. So it was refused, and four cycles in a row were
    opened against the project node instead. By v0.31.0 the workaround was moving
    version numbers: a light cycle's work cut as a MINOR because only a branch could
    hold the cycle. The chart's shape was choosing the weight, which is backwards.

    Downward wins when it finds anything, so composition is untouched: a goal still
    offers the repos it decomposes into and never its ancestors'. Upward is the
    fallback for the leaves, and it walks **only your own ancestry** — a sibling's
    repo is not yours, and a leaf beside a project is not part of it.

    Safe only because of the gate. The recorded risk was two siblings inheriting one
    repo and proposing the same next version; `_open_gate` refuses a second open
    cycle per repo, and `versions_claimed_in` now sees *more* problems per repo
    rather than fewer, so the proposal gets more careful, not less.
    """
    node = get(con, pid)
    if not node:
        return []
    if node.get("repo"):
        return [node["repo"]]
    _seen = _seen if _seen is not None else {pid}
    found: list[str] = []
    for kid in children(con, pid):
        if kid["id"] in _seen:
            continue
        _seen.add(kid["id"])
        for r in nearest_repos(con, kid["id"], _seen):
            if r not in found:
                found.append(r)
    return found or _repo_above(con, pid)


def _repo_above(con: sqlite3.Connection, pid: str) -> list[str]:
    """The nearest ancestor's repo, breadth-first so *nearest* means fewest hops.

    Stops at the first generation that carries one, for the same reason the downward
    walk stops: a problem inherits the project it is part of, not every project its
    bearings ever contained. A node with two parents at that distance carrying
    different repos returns both, and the open-cycle route already asks which — that
    ambiguity is real and guessing would cut a tag in a repo nobody named.
    """
    seen = {pid}
    level = [pid]
    while level:
        nxt, repos = [], []
        for nid in level:
            for parent in parents(con, nid):
                if parent["id"] in seen:
                    continue
                seen.add(parent["id"])
                if parent.get("repo"):
                    if parent["repo"] not in repos:
                        repos.append(parent["repo"])
                else:
                    nxt.append(parent["id"])
        if repos:
            return repos
        level = nxt
    return []


def add_edge(con: sqlite3.Connection, *, child_id: str, parent_id: str) -> None:
    """`child` serves `parent`. Many-to-many: a project may serve several bearings."""
    if child_id == parent_id:
        raise ChartError("a problem cannot serve itself")
    for node in (child_id, parent_id):
        if not con.execute("SELECT 1 FROM problems WHERE id=?", (node,)).fetchone():
            raise ChartError(f"no such problem '{node}'")
    con.execute("INSERT OR IGNORE INTO problem_edges (child_id, parent_id) VALUES (?,?)",
                (child_id, parent_id))


# ---------- repeated bearings ----------

def repeated_bearings(con: sqlite3.Connection) -> list[dict]:
    """Sets of problems whose bearings are *identical* — a missing node, said N times.

    When ten problems each serve the same two goals, the chart asserts one fact
    twenty times and states it zero times. The thing they have in common has no
    name, so it cannot carry a waypoint, cannot be argued for, and cannot be moved
    as a unit.

    Only reported when naming the set would cost fewer edges than repeating it —
    `children × bearings > children + bearings`. That is not a tuned threshold but
    the break-even itself, so two problems sharing two bearings (4 edges either
    way) stays quiet and nothing is suggested that would not pay for itself.
    """
    rows = con.execute("SELECT child_id, parent_id FROM problem_edges").fetchall()
    held: dict[str, set[str]] = {}
    for child_id, parent_id in rows:
        held.setdefault(child_id, set()).add(parent_id)

    grouped: dict[frozenset, list[str]] = {}
    for child_id, ps in held.items():
        if len(ps) > 1:
            grouped.setdefault(frozenset(ps), []).append(child_id)

    titles = dict(con.execute("SELECT id, title FROM problems").fetchall())
    out = []
    for ps, kids in grouped.items():
        c, p = len(kids), len(ps)
        if c * p <= c + p:
            continue
        out.append({
            "bearings": [{"id": i, "title": titles.get(i, i)} for i in sorted(ps)],
            "children": [{"id": i, "title": titles.get(i, i)}
                         for i in sorted(kids, key=lambda i: titles.get(i, ""))],
            "edges_now": c * p,
            "edges_after": c + p,
        })
    return sorted(out, key=lambda g: g["edges_now"] - g["edges_after"], reverse=True)


def group_under(con: sqlite3.Connection, *, title: str, bearing_ids: list[str],
                child_ids: list[str], waypoint: str = "") -> dict:
    """Insert one named problem between a set of bearings and the problems serving
    exactly them.

    Deliberately refuses if any child's bearings have changed since the grouping was
    offered. This rewires many edges at once off a suggestion the user may have been
    looking at for a while, and quietly regrouping something that no longer matches
    would be the invisible mutation this app exists to prevent.
    """
    title = (title or "").strip()
    if not title:
        raise ChartError("the group needs a name — it is a problem like any other")
    if len(bearing_ids) < 1 or len(child_ids) < 2:
        raise ChartError("a group needs at least one bearing and two problems")

    wanted = set(bearing_ids)
    for cid in child_ids:
        have = {p["id"] for p in parents(con, cid)}
        if have != wanted:
            node = get(con, cid)
            raise ChartError(
                f"'{node['title'] if node else cid}' no longer serves exactly those "
                "bearings — the chart changed since this was suggested. Reload and look again")

    group_id = create_problem(con, title=title, waypoint=waypoint,
                              draft=not waypoint.strip())
    for bid in bearing_ids:
        add_edge(con, child_id=group_id, parent_id=bid)
    for cid in child_ids:
        add_edge(con, child_id=cid, parent_id=group_id)
        for bid in bearing_ids:
            remove_parent(con, child_id=cid, parent_id=bid)
    return {"id": group_id, "title": title,
            "regrouped": len(child_ids), "bearings": len(bearing_ids)}


# ---------- reads ----------

def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["anchored"] = bool(d.get("anchored_at"))
    # No waypoint yet: captured fast, not yet made falsifiable. Debt, and said so.
    # Note this is NOT the same as having no repo — most problems should never have
    # one; decomposition comes first and a repo is what you add once you attack it.
    d["draft"] = not (d.get("waypoint") or "").strip()
    d["pinned"] = bool(d.get("pinned"))
    d["active"] = bool(d.get("active"))
    return d


def set_pinned(con: sqlite3.Connection, pid: str, on: bool) -> None:
    """Pin a goal as a board heading.

    Pinning is a decision about *looking*, held separately from decomposing: you
    add a sub-problem because the thinking demands it, not because you wanted
    another column. So a chart can grow to any depth while the board stays six
    headings wide.
    """
    if not get(con, pid):
        raise ChartError(f"no such problem '{pid}'")
    con.execute("UPDATE problems SET pinned=?, updated_at=? WHERE id=?",
                (1 if on else 0, _now(), pid))


_VERSION = None  # set below; kept near the functions that use it


def address(con: sqlite3.Connection, pid: str, version: str) -> None:
    """Record that a cut cycle ran against this problem."""
    import re as _re
    if not get(con, pid):
        raise ChartError(f"no such problem '{pid}'")
    version = (version or "").strip()
    if not _re.fullmatch(r"v?\d+\.\d+\.\d+", version):
        raise ChartError(f"'{version}' is not a version — a cycle is named by the tag it cut")
    # Stored without the `v`, because that is the form git tags arrive in via
    # `repo.cycles`. Accepting both spellings and storing whichever was typed put
    # `v0.1.0` beside `0.18.0` in one list and rendered as "vv0.1.0".
    version = version.lstrip("v")
    con.execute("INSERT OR IGNORE INTO problem_cycles (problem_id, version) VALUES (?,?)",
                (pid, version))


def unaddress(con: sqlite3.Connection, pid: str, version: str) -> None:
    # Accept either spelling on the way out too, so a chip rendered from stored
    # data unlinks whatever the caller round-trips back.
    v = (version or "").strip().lstrip("v")
    con.execute("DELETE FROM problem_cycles WHERE problem_id=? AND version IN (?,?)",
                (pid, v, f"v{v}"))


def addressed_by(con: sqlite3.Connection, pid: str) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT version FROM problem_cycles WHERE problem_id=? ORDER BY version", (pid,))]


def all_addressed(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Every link at once — the outline needs them per row and a query per row is
    the shape that made the argument summaries slow."""
    out: dict[str, list[str]] = {}
    for pid, version in con.execute(
            "SELECT problem_id, version FROM problem_cycles ORDER BY version"):
        out.setdefault(pid, []).append(version)
    return out


def pinned_problems(con: sqlite3.Connection) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [_row(r) for r in con.execute(
        "SELECT * FROM problems WHERE pinned=1 ORDER BY title").fetchall()]


def nearest_pinned(con: sqlite3.Connection, pid: str) -> str | None:
    """The pinned goal this problem belongs under — itself, or the closest above it.

    Breadth-first so the *nearest* pin wins when a problem serves several bearings;
    a project under two pinned goals lands under the one it is closest to rather
    than whichever the walk happened to reach first.
    """
    seen, frontier = {pid}, [pid]
    while frontier:
        nxt = []
        for node in frontier:
            row = get(con, node)
            if row and row["pinned"]:
                return node
        for node in frontier:
            for p in parents(con, node):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    nxt.append(p["id"])
        frontier = nxt
    return None


def get(con: sqlite3.Connection, pid: str) -> dict | None:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    return _row(r) if r else None


def resolve(con: sqlite3.Connection, ref: str) -> dict | None:
    """Accept either a problem id or a project id (the `repo` column)."""
    return get(con, ref) or _by_repo(con, ref)


def _by_repo(con: sqlite3.Connection, repo: str) -> dict | None:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM problems WHERE repo=? ORDER BY created_at LIMIT 1",
                    (repo,)).fetchone()
    return _row(r) if r else None


def parents(con: sqlite3.Connection, pid: str) -> list[dict]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT p.* FROM problems p JOIN problem_edges e ON e.parent_id = p.id
           WHERE e.child_id = ? ORDER BY p.created_at""", (pid,)).fetchall()
    return [_row(r) for r in rows]


def children(con: sqlite3.Connection, pid: str) -> list[dict]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT p.* FROM problems p JOIN problem_edges e ON e.child_id = p.id
           WHERE e.parent_id = ? ORDER BY p.created_at""", (pid,)).fetchall()
    return [_row(r) for r in rows]


def effective_sounding(con: sqlite3.Connection, pid: str,
                       _seen: set[str] | None = None) -> str:
    """Evidence is capped by the children — a claim is only as good as what supports it.

    A leaf reports what it declares. A parent reports the weaker of its own declared
    sounding and the *best* of its children: if every child is `assumed`, the parent
    is `assumed` no matter how confident it feels. So the grade at the top of a chart
    is computed, and the only place worth grading honestly is the bottom.
    """
    _seen = _seen or set()
    if pid in _seen:                      # cycles are possible; don't hang on them
        return "assumed"
    _seen.add(pid)
    own = (get(con, pid) or {}).get("sounding", "assumed")
    kids = children(con, pid)
    if not kids:
        return own
    best_child = max((effective_sounding(con, k["id"], _seen) for k in kids),
                     key=lambda s: _RANK[s])
    return min((own, best_child), key=lambda s: _RANK[s])


def spine(con: sqlite3.Connection, ref: str) -> dict | None:
    """The view the UI draws: bearings above, the node centred, children below."""
    node = resolve(con, ref)
    if not node:
        return None
    pid = node["id"]
    node["effective_sounding"] = effective_sounding(con, pid)

    def decorate(p: dict) -> dict:
        p["effective_sounding"] = effective_sounding(con, p["id"])
        p["child_count"] = len(children(con, p["id"]))
        p["project_count"] = _project_count(con, p["id"])
        return p

    return {
        "node": node,
        "parents": [decorate(p) for p in parents(con, pid)],
        "children": [decorate(c) for c in children(con, pid)],
    }


def _project_count(con: sqlite3.Connection, pid: str, _seen: set[str] | None = None) -> int:
    """How many projects hang off this problem, at any depth. A bearing's weight."""
    _seen = _seen or set()
    if pid in _seen:
        return 0
    _seen.add(pid)
    total = 0
    for kid in children(con, pid):
        if kid.get("repo"):
            total += 1
        total += _project_count(con, kid["id"], _seen)
    return total


def duplicate_subtree(con: sqlite3.Connection, pid: str, parent_id: str | None,
                      _depth: int = 0) -> str:
    """Copy a problem and everything beneath it as *new, independent* nodes.

    The opposite of attaching a second bearing: sharing says "this is the same goal";
    copying says "these are two similar goals that will diverge". Conflating them is
    how a chart quietly stops meaning anything.

    Deliberately not copied: the **repo** (a project is attacked by one problem, and
    the copy has not earned it) and the **anchor** (a dated decision about a specific
    belief; the copy has decided nothing yet). Title, waypoint, sounding, reasoning
    and falsifier all carry over, because those are the shape.
    """
    src = get(con, pid)
    if not src:
        raise ChartError(f"no such problem '{pid}'")
    if _depth > 8:
        raise ChartError("that subtree is too deep to copy")

    new_id = create_problem(
        con, title=src["title"], waypoint=src["waypoint"] or "",
        sounding=src["sounding"], reasoning=src.get("reasoning"),
        falsifier=src.get("falsifier"), parent_id=parent_id,
        draft=not (src["waypoint"] or "").strip())

    for kid in children(con, pid):
        duplicate_subtree(con, kid["id"], new_id, _depth + 1)
    return new_id


def outline(con: sqlite3.Connection, root_id: str | None = None) -> list[dict]:
    """The chart as a flat, ordered, depth-tagged list — the goals page.

    `root_id` scopes it to one problem's subtree, which is how a project draws its
    own chart: the same tree, the same depths, rooted at the problem the repo
    attacks rather than at the fleet's bearings.

    A problem with two bearings is emitted **expandable at its first occurrence and
    as an inert reference at the second**. Never two editable copies: the chart has
    one node, and rendering two would let you edit a thing twice and disagree with
    yourself. Also stops a shared subtree from being walked (and drawn) repeatedly.
    """
    rows: list[dict] = []
    emitted: set[str] = set()
    # How many places each node will appear: once per bearing, or once if it is a
    # root. Shown as "1/3" so a shared goal reads as one goal in three places
    # rather than as three goals.
    total = {n["id"]: max(1, len(parents(con, n["id"]))) for n in all_problems(con)}
    linked = all_addressed(con)
    seen_count: dict[str, int] = {}

    def walk(node: dict, depth: int, path: frozenset[str]) -> None:
        seen_count[node["id"]] = seen_count.get(node["id"], 0) + 1
        occ = {"occurrence": seen_count[node["id"]], "occurrences": total.get(node["id"], 1)}
        if node["id"] in emitted:
            rows.append({**node, **occ, "depth": depth, "reference": True, "child_count": 0})
            return
        if node["id"] in path:                      # cycle guard
            return
        emitted.add(node["id"])
        kids = children(con, node["id"])
        rows.append({**node, **occ, "depth": depth, "reference": False,
                     "child_count": len(kids),
                     "addressed_by": linked.get(node["id"], []),
                     "effective_sounding": effective_sounding(con, node["id"])})
        for kid in kids:
            walk(kid, depth + 1, path | {node["id"]})

    if root_id:
        start = get(con, root_id)
        if not start:
            raise ChartError(f"no such problem '{root_id}'")
        walk(start, 0, frozenset())
    else:
        for root in roots(con):
            walk(root, 0, frozenset())
    return rows


def drift(con: sqlite3.Connection) -> list[dict]:
    """Problems serving no bearing. Usually means the chart is incomplete.

    A parentless problem is not automatically drift — a **bearing** is parentless by
    definition, and reporting your top-level aims as orphans makes the inbox useless.
    Drift is a parentless problem that *should* serve something: a project (a project
    with nothing above it has no stated reason to exist), or a leaf floating with
    neither parent nor children.
    """
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT p.* FROM problems p
           WHERE p.id NOT IN (SELECT child_id FROM problem_edges)
             AND (p.repo IS NOT NULL
                  OR p.id NOT IN (SELECT parent_id FROM problem_edges))
           ORDER BY p.created_at""").fetchall()
    return [_row(r) for r in rows]


def all_problems(con: sqlite3.Connection) -> list[dict]:
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM problems ORDER BY created_at").fetchall()
    return [_row(r) for r in rows]


# ---------- export ----------
#
# data/*.sqlite is gitignored, so without this the chart — months of recorded
# reasoning and dated decisions — would live in an untracked file with no history
# and no backup. One-way on purpose: export only, so there is no parser to keep
# correct and no merge conflict to resolve. See docs/adr/0003-chart-storage.md.

def render_markdown(con: sqlite3.Connection) -> str:
    roots = [p for p in all_problems(con) if not parents(con, p["id"])]
    lines = [
        "# Chart",
        "",
        "Generated by shipyard from `data/shipyard.sqlite`. **Do not edit by hand** —",
        "edits here are not read back; the database is the store (ADR 0003).",
        "",
        "Read top-down: a bearing, then everything that serves it.",
        "",
    ]

    # One shared set across every root, not one per root: a node with two bearings
    # is the same node, and rendering its whole subtree under each would both double
    # the file and hide that they are the same problem.
    rendered: set[str] = set()

    def walk(node: dict, depth: int) -> None:
        if node["id"] in rendered:
            lines.append(f"{'  ' * depth}- **{node['title']}** — *shown in full above*")
            return
        rendered.add(node["id"])
        pad = "  " * depth
        eff = effective_sounding(con, node["id"])
        bits = [f"`{eff}`"]
        if eff != node["sounding"]:
            bits.append(f"declared `{node['sounding']}`, capped by its children")
        if node.get("repo"):
            bits.append(f"project `{node['repo']}`")
        if node.get("anchored_at"):
            bits.append(f"**anchored** {node['anchored_at']}")
        elif node.get("anchor_basis"):
            # Basis without a date means it was frozen once and thawed. Say so — a
            # thawed belief reads identically to one never examined otherwise.
            bits.append("**thawed**")
        lines.append(f"{pad}- **{node['title']}** — {' · '.join(bits)}")
        lines.append(f"{pad}  - Waypoint — {node['waypoint']}")
        ran = addressed_by(con, node["id"])
        if ran:
            # Which finished cycles ran against it — not which one solved it. The
            # sounding above already says whether anything was observed.
            lines.append(f"{pad}  - Addressed by — {', '.join('v' + v for v in ran)}")
        if node.get("anchor_basis"):
            lines.append(f"{pad}  - Basis — {node['anchor_basis']}")
        if node.get("falsifier"):
            lines.append(f"{pad}  - Falsified by — {node['falsifier']}")
        # Prose is free-form and therefore multi-line. Continuation lines are
        # indented to sit under the bullet's text, or a single newline in a note
        # would silently end the list and reflow everything below it.
        for label, key in (("Description", "description"), ("Notes", "notes")):
            text = (node.get(key) or "").strip()
            if not text:
                continue
            head, *rest = text.splitlines()
            lines.append(f"{pad}  - {label} — {head}")
            lines.extend(f"{pad}    {line}" if line.strip() else "" for line in rest)
        for kid in children(con, node["id"]):
            walk(kid, depth + 1)

    for root in roots:
        if not children(con, root["id"]) and not root.get("repo"):
            continue                       # bare drift; listed separately below
        walk(root, 0)
        lines.append("")

    loose = [p for p in drift(con) if not children(con, p["id"]) and not p.get("repo")]
    if loose:
        lines += ["## Drift", "", "Serving no bearing — usually the chart is incomplete,",
                  "not the work.", ""]
        lines += [f"- {p['title']} — waypoint: {p['waypoint']}" for p in loose]
        lines.append("")

    return "\n".join(lines)


# Both shapes render_markdown emits, because a guard that only knows one of them
# would let the other be deleted silently — and Drift is the section most likely to
# hold a node the store has not caught up with.
#
# The tail is not decoration. A node line is `- **Title** — ` followed by its
# backticked sounding, or by *shown in full above* for a second appearance. Matching
# on the bold alone also matches every bolded bullet a human wrote INSIDE a
# description, and this repo has three: the manalab audit's findings list rendered
# as `- **746 cards have the wrong cmc.** 494 …`. Those are prose, they will never be
# problem titles, and defending them would freeze the mirror permanently.
_EXPORTED_TITLE = re.compile(
    r'^(?:\s*[-*]\s+\*\*(?P<bold>.+?)\*\*\s+—\s+(?:`|\*shown in full above\*)'
    r'|[-*]\s+(?P<plain>[^*\n]+?)\s+—\s+waypoint:)',   # drift, column zero only
    re.M)


def exported_titles(text: str) -> set[str]:
    """Every problem title a rendered chart names. Public because the app needs to
    ask the same question the guard asks, to work out which removals are its own."""
    return {(m.group("bold") or m.group("plain")).strip()
            for m in _EXPORTED_TITLE.finditer(text)}


def export(con: sqlite3.Connection, path, *, allow_removals: bool = False,
           protected: set[str] | None = None) -> None:
    """Write the store to `path` as markdown.

    ADR 0003 makes this one-way: the store is truth and nothing reads the file
    back. The consequence is sharper than it sounds — every export rewrites the
    WHOLE file from whatever the store currently holds, so a store that is merely
    incomplete silently deletes reasoning that was only ever committed to the file.

    That is not hypothetical. A machine that pulled `scripts/world-awareness.json`
    but never ran it had 14 nodes in `docs/chart.md` and none of them in sqlite;
    the next seed run dropped all 14, and the only evidence was a diff with more
    deletions than insertions.

    So by default an export refuses to drop a node the file already names. Reading
    the file to decide whether to REFUSE is not the parser ADR 0003 rules out —
    nothing here is read back into the store, and the markdown does not become a
    second writable source. It only gets a veto over its own destruction.

    `allow_removals=True` drops the guard entirely, for callers where removal is
    the point.

    `protected` is the sharper form, and the one the app uses: guard only these
    titles. It lets a caller that knows which nodes it has actually held say so,
    so a deliberate delete goes through while a node this store never received
    still cannot be erased. Passing it overrides `allow_removals`.
    """
    from pathlib import Path
    p = Path(path)
    text = render_markdown(con)
    if p.exists() and (protected is not None or not allow_removals):
        try:
            before = exported_titles(p.read_text())
        except OSError:
            before = set()          # unreadable file is not evidence of anything
        if protected is not None:
            before &= protected
        gone = sorted(before - exported_titles(text))
        if gone:
            shown = ", ".join(repr(t) for t in gone[:5])
            more = f" (and {len(gone) - 5} more)" if len(gone) > 5 else ""
            raise ChartError(
                f"refusing to export: {len(gone)} node(s) in {p} are not in the "
                f"store — {shown}{more}. The store is incomplete, not the file. "
                f"Seed them first (scripts/seed_chart.py) or pass allow_removals."
            )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


# ---------- v0.20.0: the loop, per problem ----------

def _problem_row(con: sqlite3.Connection, pid: str) -> dict:
    r = con.execute("SELECT * FROM problems WHERE id = ?", (pid,))
    row = r.fetchone()
    if not row:
        raise ChartError(f"no problem {pid!r}")
    return dict(zip([c[0] for c in r.description], row))


PHASES = ("plan", "test", "review")   # `build` is derived from git, never stored
VERDICTS = (None, "worked", "failed", "abandoned")


def set_phases(con: sqlite3.Connection, pid: str, **marks: bool) -> dict:
    """Tick or untick manual phases. Unknown names are rejected rather than ignored —
    a silently-dropped `build=True` would look like the derived value disagreeing."""
    bad = set(marks) - set(PHASES)
    if bad:
        raise ChartError(f"not a manual phase: {', '.join(sorted(bad))} "
                         f"(build is derived from commits)")
    if not marks:
        return get(con, pid)
    now = _now()
    # Each tick writes its own timestamp and each untick clears it, in the same
    # statement as the flag. Two writes could half-fail and leave a phase that is on
    # with no time, or off with one — both of which read as data rather than as a bug.
    sets, params = [], []
    for k, v in marks.items():
        sets += [f"phase_{k} = ?", f"phase_{k}_at = ?"]
        params += [1 if v else 0, now if v else None]
    con.execute(f"UPDATE problems SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
                params + [now, pid])
    return get(con, pid)


def set_solved(con: sqlite3.Connection, pid: str, solved: bool) -> dict:
    """Solved is set by hand and does not cascade from children: a parent problem is
    not the sum of its parts, which is the whole reason it carries its own waypoint.

    Solving releases the focus slot. A slot is only scarce if finishing gives it
    back — otherwise every domain silently fills with completed work and the one
    number the focus strip exists to show stops meaning anything.
    """
    con.execute(
        "UPDATE problems SET solved = ?, solved_at = ?, active = ?, active_at = ?, "
        "updated_at = ? WHERE id = ?",
        (1 if solved else 0, _now() if solved else None,
         0 if solved else _bool_col(con, pid, "active"),
         None if solved else _col(con, pid, "active_at"),
         _now(), pid))
    return get(con, pid)


def _col(con: sqlite3.Connection, pid: str, name: str) -> Any:
    r = con.execute(f"SELECT {name} FROM problems WHERE id = ?", (pid,)).fetchone()
    return r[0] if r else None


def _bool_col(con: sqlite3.Connection, pid: str, name: str) -> int:
    return 1 if _col(con, pid, name) else 0


STANDINGS = ("done", "open", "blocked")


def standings(con: sqlite3.Connection) -> dict[str, str]:
    """Where every problem sits relative to the work beneath it. One query, one rule.

    A subproblem serves its parent, so children are this chart's prerequisites:

      done      solved by hand
      open      not solved, and nothing beneath it is outstanding — which includes
                every leaf, so the frontier starts at the bottom of the chart
      blocked   not solved, and at least one subproblem is still unsolved

    Derived, never stored: `solved` is the only fact a person sets, and a second
    column agreeing with it is a column that will one day disagree with it. Computed
    here rather than in each view because the outline and the graph drawing the same
    chart and disagreeing about it is its own confusion — the same reason they
    already share a collapse key.

    Note this does NOT make a parent solved when its children are: `set_solved` is
    explicit precisely because a parent problem is not the sum of its parts.
    """
    solved = {}
    for r in con.execute("SELECT id, solved FROM problems"):
        solved[r[0]] = bool(r[1])
    has_open_child = set()
    for child, parent in con.execute("SELECT child_id, parent_id FROM problem_edges"):
        if child in solved and not solved[child]:
            has_open_child.add(parent)
    return {pid: "done" if done else ("blocked" if pid in has_open_child else "open")
            for pid, done in solved.items()}


UNASSIGNED = "__unassigned__"


def focus_slots(con: sqlite3.Connection) -> list[dict]:
    """One slot per pinned domain, and what is running in it.

    A slot is keyed by the pinned goal a problem answers to — the same
    `nearest_pinned` the board sections by, so "domain" means one thing in this app
    and not two. A problem under no pin lands in a single `__unassigned__` slot,
    which is also what the whole chart collapses to when nothing is pinned at all.
    That degenerate case is HOI4 exactly: one focus, globally.

    Derived from the rows every time. A stored count of what is running is a number
    that will one day disagree with the rows it claims to describe.
    """
    con.row_factory = sqlite3.Row          # _row() needs mappings, not tuples
    active = [_row(r) for r in con.execute(
        "SELECT * FROM problems WHERE active = 1 ORDER BY active_at")]
    running = {}
    for p in active:
        running.setdefault(nearest_pinned(con, p["id"]) or UNASSIGNED, p)

    slots = []
    for pin in pinned_problems(con):
        p = running.pop(pin["id"], None)
        slots.append({"domain_id": pin["id"], "domain": pin["title"], "problem": p})
    # Only shown when something is actually in it: an empty "no domain" slot is an
    # invitation to use one, and the point of slots is that they are scarce.
    stray = running.pop(UNASSIGNED, None)
    if stray or running:
        slots.append({"domain_id": UNASSIGNED, "domain": "No domain",
                      "problem": stray or next(iter(running.values()))})
    return slots


def set_active(con: sqlite3.Connection, pid: str, on: bool) -> dict:
    """Take or release the focus slot for this problem's domain.

    Two rules, both refusals rather than silent corrections:

    * Only an **open** problem can be taken up. Starting something a subproblem is
      still holding up is the thing this whole state model exists to make visible,
      so the app must not be the one to do it.
    * One at a time per domain. A second is **refused, naming the occupant**, not
      swapped in — HOI4 makes you cancel a focus deliberately, and the moment you
      switch what you are working on is exactly the moment worth noticing. The UI
      turns that refusal into an explicit replace.
    """
    node = get(con, pid)
    if not node:
        raise ChartError(f"no such problem '{pid}'")
    if on:
        standing = standings(con).get(pid)
        if standing == "blocked":
            raise ChartError(
                f"'{node['title']}' is blocked — a subproblem beneath it is unsolved")
        if standing == "done":
            raise ChartError(f"'{node['title']}' is already solved")
        home = nearest_pinned(con, pid) or UNASSIGNED
        for slot in focus_slots(con):
            if slot["domain_id"] == home and slot["problem"] \
                    and slot["problem"]["id"] != pid:
                raise ChartError(
                    f"“{slot['domain']}” is already focused on "
                    f"“{slot['problem']['title']}” — release that first")
    con.execute("UPDATE problems SET active = ?, active_at = ?, updated_at = ? WHERE id = ?",
                (1 if on else 0, _now() if on else None, _now(), pid))
    return get(con, pid)


def approaches(con: sqlite3.Connection, pid: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM problem_approaches WHERE problem_id = ? ORDER BY created_at", (pid,))
    return [dict(zip([c[0] for c in rows.description], r)) for r in rows.fetchall()]


def add_approach(con: sqlite3.Connection, pid: str, *, name: str,
                 rationale: str | None = None) -> dict:
    if not (name or "").strip():
        raise ChartError("an approach needs a name")
    # Foreign keys already refuse an orphan, but they raise sqlite3.IntegrityError,
    # which the route does not catch — so a bogus pid became a 500. Check first and
    # fail the same way every other bad reference here does.
    if not con.execute("SELECT 1 FROM problems WHERE id = ?", (pid,)).fetchone():
        raise ChartError(f"no problem {pid!r}")
    aid = uuid.uuid4().hex[:12]
    now = _now()
    con.execute("INSERT INTO problem_approaches "
                "(id, problem_id, name, rationale, chosen, verdict, created_at, updated_at) "
                "VALUES (?,?,?,?,0,NULL,?,?)", (aid, pid, name.strip(), rationale, now, now))
    return {"id": aid, "problem_id": pid, "name": name.strip(), "rationale": rationale,
            "chosen": 0, "verdict": None, "created_at": now, "updated_at": now}


def update_approach(con: sqlite3.Connection, aid: str, *, name: str | None = None,
                    rationale: str | None = None, verdict: str | None = ...,
                    chosen: bool | None = None) -> list[dict]:
    """Edit one approach. Choosing this one un-chooses its siblings — but never
    touches their verdicts: an approach you tried and abandoned keeps saying so
    after you move on, which is the whole reason the verdict is recorded."""
    row = con.execute("SELECT problem_id FROM problem_approaches WHERE id = ?", (aid,)).fetchone()
    if not row:
        raise ChartError(f"no approach {aid!r}")
    pid = row[0]
    if verdict is not ... and verdict not in VERDICTS:
        raise ChartError(f"verdict must be one of {VERDICTS}")
    sets, vals = [], []
    if name is not None:
        if not name.strip():
            raise ChartError("an approach needs a name")
        sets.append("name = ?"); vals.append(name.strip())
    if rationale is not None:
        sets.append("rationale = ?"); vals.append(rationale)
    if verdict is not ...:
        sets.append("verdict = ?"); vals.append(verdict)
    if sets:
        con.execute(f"UPDATE problem_approaches SET {', '.join(sets)}, updated_at = ? WHERE id = ?",
                    vals + [_now(), aid])
    if chosen:
        con.execute("UPDATE problem_approaches SET chosen = 0, updated_at = ? WHERE problem_id = ?",
                    (_now(), pid))
        con.execute("UPDATE problem_approaches SET chosen = 1, updated_at = ? WHERE id = ?",
                    (_now(), aid))
    elif chosen is False:
        con.execute("UPDATE problem_approaches SET chosen = 0, updated_at = ? WHERE id = ?",
                    (_now(), aid))
    return approaches(con, pid)


def delete_approach(con: sqlite3.Connection, aid: str) -> list[dict]:
    row = con.execute("SELECT problem_id FROM problem_approaches WHERE id = ?", (aid,)).fetchone()
    if not row:
        raise ChartError(f"no approach {aid!r}")
    con.execute("DELETE FROM problem_approaches WHERE id = ?", (aid,))
    return approaches(con, row[0])
