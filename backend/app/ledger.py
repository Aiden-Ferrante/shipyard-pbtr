"""The session ledger — who touched the chart, from which session, and what else
that session did (commits, tags, pushes) while it was open.

Two tables and one header. `sessions` is one row per agent session (Claude Code's
`session_id`, posted by the SessionStart hook in fleet/hooks). `session_events`
is an append-only log: chart writes made under that session (anchor, thaw, cycle
open/link, phase ticks) are appended here by the routes themselves, and git
events (commit, tag, push) are posted by the PostToolUse hook. `problems.updated_by`
records the actor of the last write on each problem.

WHY A STORED TABLE in a codebase whose rule is "derive, never store" (ADR 0006):
that rule is about STATE — a count that will one day disagree with the rows it
describes. A session is history: nothing on disk or in git says "this commit was
made by the session that also set this anchor", so it cannot be derived later;
it can only be recorded at the moment it happens. An append-only event log is
the one shape of stored fact the rule permits, and the ledger is deliberately
nothing else — no status, no rollup, no cached count.

THE ACTOR is read from the `X-Actor` request header by `ActorMiddleware` into a
contextvar, so routes call `actor()` without threading a Request through. The
fleet MCP sends `claude-code:<session_id>` (from the session file the SessionStart
hook writes); the SPA sends nothing and reads as `human:ui`. Any other client
that says nothing is `unknown`. Nothing is verified — this is a record, not auth.
"""
from __future__ import annotations

import contextvars
import sqlite3
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware

_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("actor", default="unknown")
EVENT_KINDS = ("commit", "tag", "push", "anchor", "thaw", "cycle_open", "cycle_link", "phase",
               "problem", "note")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def actor() -> str:
    return _ACTOR.get()


def session_of(act: str | None = None) -> str | None:
    """The session id inside `claude-code:<sid>`, or None for a human/unknown actor."""
    a = act or actor()
    if a.startswith("claude-code:") and a != "claude-code:unknown":
        return a.split(":", 1)[1]
    return None


class ActorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        hdr = request.headers.get("x-actor")
        # The SPA never sets the header; a browser is the human.
        val = hdr.strip() if hdr else ("human:ui" if "text/html" in request.headers.get("accept", "") or request.headers.get("sec-fetch-mode") else "unknown")
        token = _ACTOR.set(val)
        try:
            return await call_next(request)
        finally:
            _ACTOR.reset(token)


def init(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id          TEXT PRIMARY KEY,
        tool        TEXT NOT NULL DEFAULT 'claude-code',
        cwd         TEXT,
        repo        TEXT,
        started_at  TEXT NOT NULL,
        ended_at    TEXT,
        end_reason  TEXT,
        summary     TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS session_events (
        id          INTEGER PRIMARY KEY,
        session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        at          TEXT NOT NULL,
        kind        TEXT NOT NULL,
        ref         TEXT,
        detail      TEXT)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_session_events_sid ON session_events(session_id, id)")
    cols = {r[1] for r in con.execute("PRAGMA table_info(problems)")}
    if "updated_by" not in cols:
        con.execute("ALTER TABLE problems ADD COLUMN updated_by TEXT")


# --- sessions ---------------------------------------------------------------

def start(con: sqlite3.Connection, sid: str, *, tool: str = "claude-code", cwd: str | None = None,
          repo: str | None = None) -> dict:
    """Upsert. A hook may fire twice (resume, clear); the row is the same session."""
    row = con.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
    if row:
        con.execute("UPDATE sessions SET cwd=COALESCE(?, cwd), repo=COALESCE(?, repo), ended_at=NULL, end_reason=NULL WHERE id=?",
                    (cwd, repo, sid))
    else:
        con.execute("INSERT INTO sessions (id, tool, cwd, repo, started_at) VALUES (?,?,?,?,?)",
                    (sid, tool, cwd, repo, now()))
    return get(con, sid)


def end(con: sqlite3.Connection, sid: str, *, reason: str | None = None, summary: str | None = None) -> dict:
    if not con.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
        start(con, sid)
    con.execute("UPDATE sessions SET ended_at=?, end_reason=COALESCE(?, end_reason), summary=COALESCE(?, summary) WHERE id=?",
                (now(), reason, summary, sid))
    return get(con, sid)


def event(con: sqlite3.Connection, sid: str, kind: str, ref: str | None = None,
          detail: str | None = None, *, cwd: str | None = None, repo: str | None = None) -> dict:
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind {kind!r}; one of {', '.join(EVENT_KINDS)}")
    if not con.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
        # An event before its SessionStart (hook order, or a session that began
        # before the ledger existed) still gets recorded; the row is created bare.
        start(con, sid, cwd=cwd, repo=repo)
    cur = con.execute("INSERT INTO session_events (session_id, at, kind, ref, detail) VALUES (?,?,?,?,?)",
                      (sid, now(), kind, ref, detail))
    return {"id": cur.lastrowid, "session_id": sid, "at": now(), "kind": kind, "ref": ref, "detail": detail}


def record(con: sqlite3.Connection, kind: str, ref: str | None = None, detail: str | None = None,
           pid: str | None = None) -> None:
    """Called by chart write routes: stamp `updated_by` and, when the actor is a
    session, append the event. Never raises — a ledger failure must not undo a
    chart write that already happened."""
    try:
        a = actor()
        if pid:
            con.execute("UPDATE problems SET updated_by=? WHERE id=?", (a, pid))
        sid = session_of(a)
        if sid:
            event(con, sid, kind, ref, detail)
    except (sqlite3.Error, ValueError):
        pass


def get(con: sqlite3.Connection, sid: str) -> dict | None:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["events"] = [dict(e) for e in con.execute(
        "SELECT id, at, kind, ref, detail FROM session_events WHERE session_id=? ORDER BY id", (sid,))]
    return d


def listing(con: sqlite3.Connection, *, repo: str | None = None, since: str | None = None,
            limit: int = 50) -> list[dict]:
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM sessions WHERE 1=1"
    args: list = []
    if repo:
        q += " AND repo=?"; args.append(repo)
    if since:
        q += " AND started_at>=?"; args.append(since)
    q += " ORDER BY started_at DESC LIMIT ?"; args.append(max(1, min(int(limit), 500)))
    out = []
    for r in con.execute(q, args):
        d = dict(r)
        d["events"] = [dict(e) for e in con.execute(
            "SELECT id, at, kind, ref, detail FROM session_events WHERE session_id=? ORDER BY id", (d["id"],))]
        out.append(d)
    return out


def new_id() -> str:
    return uuid.uuid4().hex
