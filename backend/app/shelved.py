"""Where shipyard records what it is carrying, and what it has set down.

Every other absence in this app is derived: a project is uncharted because nothing
claims it, ungrouped because no heading does. This is the exception, and it is the
only place where shipyard holds an opinion that disk cannot justify. So it is stored
rather than inferred, and it is **never silent** — `/api/board` always reports the
shelved count, because the invariant this bends is the board's own promise that
nothing on disk is quietly missing from it.

Keyed by repo id (the `PROJECT.yaml` `id`), not by problem: standing is a decision
about a repo, and it must survive the chart node being deleted, re-linked, or never
having existed. Nothing here touches the filesystem.

**One table, three states (ADR 0004).** Carrying a repo and shelving one are the same
judgement pointed in opposite directions, so they share a row rather than two tables
that could both claim the same repo:

    carried   in the ledger — work you intend to open a cycle on
    shelved   looked at, deliberately set down
    absent    never considered — shown in Receiving

`shelved_repos` folded into this table; `init()` carries its rows over and drops it.
The shelving API below is unchanged in name, signature and return shape, because the
board's count invariant is asserted by tests that must keep passing — if they needed
editing to survive the migration, the migration would be wrong.
"""

import sqlite3
import time

STATES = ("carried", "shelved")


def init(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS repo_standing (
        repo  TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK (state IN ('carried', 'shelved')),
        since TEXT NOT NULL,
        note  TEXT NOT NULL DEFAULT ''
    )""")
    _migrate_shelved_repos(con)


def _migrate_shelved_repos(con: sqlite3.Connection) -> None:
    """Fold the v0.28.0-and-earlier table in, once, then drop it.

    Idempotent by construction: after the DROP there is nothing to find, and the
    INSERT is OR IGNORE so a half-applied migration cannot double-write. Runs inside
    `init()` rather than a separate migration step because there is exactly one
    deployment of this app and a table that still exists is the only signal needed.
    """
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shelved_repos'"
    ).fetchone()
    if not exists:
        return
    con.execute("""INSERT OR IGNORE INTO repo_standing (repo, state, since, note)
                        SELECT repo, 'shelved', shelved_at, note FROM shelved_repos""")
    con.execute("DROP TABLE shelved_repos")
    # Commit is load-bearing here and nowhere else in this module's schema work.
    # `CREATE TABLE` is DDL and autocommits, which is why every other `init()` in
    # this app persists without one — but this migration *copies rows*, and an
    # INSERT opens a transaction that the DROP then joins. Read routes close their
    # connection without committing (`api_yard` does), so without this the rows and
    # the drop both roll back and the migration silently re-runs on every request
    # against an empty table. Observed exactly that before it was added.
    con.commit()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _set(con: sqlite3.Connection, repo: str, state: str, note: str) -> None:
    con.execute(
        "INSERT INTO repo_standing (repo, state, since, note) VALUES (?,?,?,?) "
        "ON CONFLICT(repo) DO UPDATE SET state=excluded.state, note=excluded.note",
        (repo, state, _now(), note))


# ---------- shelving: unchanged API, so the board's tests are unchanged ----------

def shelve(con: sqlite3.Connection, repo: str, note: str = "") -> dict:
    _set(con, repo, "shelved", note)
    return {"repo": repo, "shelved": True}


def restore(con: sqlite3.Connection, repo: str) -> dict:
    """Idempotent on purpose: the way back must never be able to fail.

    Restoring drops the row entirely rather than moving the repo to `carried`.
    Un-shelving says "I will look at this again", which is not the same claim as
    "I am working on it" — inferring the stronger one would put a repo in the
    ledger that nobody chose to carry.
    """
    con.execute("DELETE FROM repo_standing WHERE repo=? AND state='shelved'", (repo,))
    return {"repo": repo, "shelved": False}


def ids(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in
            con.execute("SELECT repo FROM repo_standing WHERE state='shelved'")}


def listing(con: sqlite3.Connection) -> list[dict]:
    """`since` is aliased back to `shelved_at`: the column generalised, the wire
    format did not, and one endpoint's field name is not worth a breaking change."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT repo, since AS shelved_at, note FROM repo_standing "
        "WHERE state='shelved' ORDER BY repo")]


# ---------- carrying: the new half ----------

def carry(con: sqlite3.Connection, repo: str, note: str = "") -> dict:
    """Declare a repo as work you are carrying — the membership the ledger reads."""
    _set(con, repo, "carried", note)
    return {"repo": repo, "carried": True}


def uncarry(con: sqlite3.Connection, repo: str) -> dict:
    """Stop carrying without shelving. Idempotent, for the same reason `restore` is."""
    con.execute("DELETE FROM repo_standing WHERE repo=? AND state='carried'", (repo,))
    return {"repo": repo, "carried": False}


def carried_ids(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in
            con.execute("SELECT repo FROM repo_standing WHERE state='carried'")}


def standing(con: sqlite3.Connection) -> dict[str, dict]:
    """Every repo with a standing, keyed by repo id — one read for the whole page."""
    con.row_factory = sqlite3.Row
    return {r["repo"]: dict(r) for r in con.execute(
        "SELECT repo, state, since, note FROM repo_standing")}
