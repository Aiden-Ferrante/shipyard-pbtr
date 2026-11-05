"""shipyard — project-lifecycle manager for the code/ fleet.

Scans $SHIPYARD_CODE_ROOT/*/PROJECT.yaml manifests (default ~/code) and joins each project to the chart
(why it exists), the open work in its backlog, its git history, and Mission Control
for live runtime status.

Keyless, local. Config via env with sane defaults (fleet convention).
"""

import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import (arguments as args_mod, chart, ledger, repo as repo_mod, tokens,
               shelved as shelved_mod, conventions as conv_mod,
               survey as survey_mod, templates as tpl_mod, work as work_mod)

ROOT = Path(__file__).resolve().parent.parent.parent  # shipyard/

# Where the repos live. Every path below is overridable by env; the defaults are
# neutral so a fresh clone runs without the author's directory layout.
CODE_ROOT = Path(os.environ.get("SHIPYARD_CODE_ROOT", "~/code")).expanduser()
MC_URL = os.environ.get("SHIPYARD_MC_URL", "http://localhost:9090")
MC_APPS_YAML = Path(os.environ.get(
    "SHIPYARD_MC_APPS_YAML", CODE_ROOT / "mission-control" / "apps.yaml")).expanduser()
DB_PATH = Path(os.environ.get("SHIPYARD_DB", ROOT / "data" / "shipyard.sqlite"))
# The chart's one-way markdown mirror, written on every chart write. Defaults to a
# gitignored path; point SHIPYARD_CHART_EXPORT at a versioned file to keep its history.
CHART_EXPORT = Path(os.environ.get("SHIPYARD_CHART_EXPORT", ROOT / "data" / "chart.md"))
ACTIVITY_WEEKS = 26
# Arguments are plain markdown in the repo, beside docs/chart.md, so the reasoning is
# versioned with the code. Point this elsewhere (a vault) and nothing else changes.
ARGUMENTS_DIR = Path(os.environ.get("SHIPYARD_ARGUMENTS_DIR", ROOT / "docs" / "arguments"))
# One config line makes any editor the "open in" target:
#   obsidian://open?vault=Obsidian&file={path}   vscode://file/{abspath}   file://{abspath}
EDITOR_URI = os.environ.get("SHIPYARD_EDITOR_URI") or None
# Templates are portable definitions, not a record of your reasoning, so they live as
# hand-editable YAML rather than in the chart's sqlite.
TEMPLATES_DIR = Path(os.environ.get("SHIPYARD_TEMPLATES_DIR", ROOT / "templates"))
# Where a template's document scaffold lands. Point it at a vault folder and cycle
# notes go there instead — the app does not care which, only that it is one place.
DOCUMENTS_DIR = Path(os.environ.get("SHIPYARD_DOCUMENTS_DIR", ROOT / "docs" / "cycles"))
# Fallback home for cycle records kept outside a repo, laid out as
# <root>/<Project>/Cycles/ (e.g. a notes vault). A repo's own docs/cycles/ wins.
CYCLES_ROOT = Path(os.environ.get(
    "SHIPYARD_CYCLES_ROOT", ROOT / "data" / "cycles")).expanduser()

SCAN_SKIP = {".git", "node_modules", ".venv", ".micromamba", "__pycache__",
             "site-packages", ".next", "dist", "build", "media", "data", "lake",
             # Retired projects keep their manifest, so without this the archived
             # copy of a project competes with the live one for the same id.
             "_archive"}
SCAN_DEPTH = 4  # PROJECT.yaml may sit a few levels below the code root
# How long a cached scan may keep serving page loads before disk and git are
# asked again. Short on purpose: the TTL exists to collapse one Fleet load —
# four endpoints, each of which used to pay the full per-repo git sweep — into
# one sweep, not to make an idle app cheap to poll. It is the honesty bound for
# out-of-band changes only (a commit from a terminal); our own write routes
# invalidate explicitly instead of waiting it out.
SCAN_TTL = float(os.environ.get("SHIPYARD_SCAN_TTL", "5"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("shipyard")

app = FastAPI(title="shipyard")
# Who is writing: X-Actor → a contextvar the write routes record (ledger.py).
app.add_middleware(ledger.ActorMiddleware)


# ---------- storage ----------

def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    chart.init(con)
    shelved_mod.init(con)
    ledger.init(con)
    return con


# ---------- request-time cache ----------

class _TTLCache:
    """Short-TTL, single-flight cache for the reads that shell out to git.

    Request-time rather than a background refresher: shipyard is page-load-
    driven, so a refresh loop would run git a few hundred times a minute on an
    idle machine to keep answers nobody asked for warm. A miss computes once,
    and concurrent requests during that miss wait for the same result — the
    Fleet page fires four endpoints at once, and without the single-flight each
    would pay the whole per-repo sweep separately.

    Values are shared between requests, so callers must treat them as
    read-only. Composition lives here in main.py on purpose: the domain
    modules stay unaware that anything above them caches.
    """

    def __init__(self, ttl: float):
        self.ttl = ttl
        self.stamp: str | None = None   # wall clock of the last store, for /health
        self._lock = threading.Lock()
        self._values: dict = {}         # key -> (monotonic deadline, value)
        self._flights: dict = {}        # key -> Event the computing thread will set

    def get(self, key, compute):
        while True:
            with self._lock:
                hit = self._values.get(key)
                if hit and hit[0] > time.monotonic():
                    return hit[1]
                flight = self._flights.get(key)
                if flight is None:
                    flight = self._flights[key] = threading.Event()
                    break
            # Another thread is computing this key. Wait, then re-check the
            # store rather than trusting the event alone: if the computer
            # failed, its flight is gone and the loop makes this thread the
            # next to try instead of caching the failure.
            flight.wait(timeout=30)
        try:
            value = compute()
        except BaseException:
            with self._lock:
                self._flights.pop(key, None)
            flight.set()
            raise
        with self._lock:
            now = time.monotonic()
            # Sweep expired entries while we hold the lock anyway — tests point
            # CODE_ROOT at a fresh tmp dir per module, and without this every
            # one of those would stay in the map for the life of the process.
            self._values = {k: v for k, v in self._values.items() if v[0] > now}
            self._values[key] = (now + self.ttl, value)
            self._flights.pop(key, None)
            # Aware, via isoformat() rather than a strftime string. The old
            # `time.strftime("%Y-%m-%dT%H:%M:%S")` emitted a NAIVE timestamp,
            # which is the one non-conformance that produces a confidently
            # wrong number: MC renders freshness as an age, and an age off a
            # naive stamp is wrong by the reader's UTC offset with nothing on
            # screen to say so. See mission-control/backend/app/freshness.py.
            self.stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        flight.set()
        return value

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def forget_under(self, path: Path) -> None:
        """Drop entries keyed by a directory that contains `path`.

        Facts are keyed by repo path, and a handler that writes any file into a
        repo's working tree has changed that repo's dirty count at minimum —
        the entry is wrong the moment the write lands, not five seconds later.
        """
        with self._lock:
            for key in [k for k in self._values
                        if isinstance(k, str) and path.is_relative_to(k)]:
                del self._values[key]


# Two caches because the two reads go stale independently: adopting a repo
# changes what the next scan finds but not every other repo's git state, and a
# write landing in one repo's tree invalidates that repo alone.
_scan_cache = _TTLCache(SCAN_TTL)
_facts_cache = _TTLCache(SCAN_TTL)


# ---------- standard + manifests ----------

def scan_manifests() -> dict[str, dict]:
    """Find PROJECT.yaml files under CODE_ROOT (bounded depth, pruned).

    Served through the cache: nearly every route starts with this walk and the
    Fleet page fires four of those routes per load. The key carries CODE_ROOT —
    tests rebind `main.CODE_ROOT` per module, and a key without it would hand
    one module's fleet to the next — plus the root's mtime, so a repo appearing
    or vanishing at top level reads as a new key rather than a five-second lie.
    Deeper changes (an edited manifest, a nested adoption) ride out the TTL or
    are invalidated by the write route that made them.
    """
    try:
        root_stamp = os.stat(CODE_ROOT).st_mtime_ns
    except OSError:
        root_stamp = 0  # a missing root scans to {}, which is fine to serve cached
    return _scan_cache.get((str(CODE_ROOT), root_stamp), _scan_uncached)


def _scan_uncached() -> dict[str, dict]:
    found = {}
    root_depth = len(CODE_ROOT.parts)
    for dirpath, dirnames, filenames in os.walk(CODE_ROOT):
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= SCAN_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP and not d.startswith(".")]
        if "PROJECT.yaml" not in filenames:
            continue
        path = Path(dirpath)
        try:
            with open(path / "PROJECT.yaml") as f:
                m = yaml.safe_load(f) or {}
        except Exception as e:  # malformed manifest: surface, don't crash the board
            log.warning("bad manifest %s: %s", path, e)
            continue
        pid = m.get("id") or path.name
        m["id"] = pid
        m["path"] = str(path)
        # Two manifests claiming one id silently shadowed each other, and which one
        # won came down to walk order — an archived copy and its successor shared an
        # id, so every reading of that project was a coin flip. Say so.
        if pid in found:
            log.warning("duplicate project id %r: %s shadows %s",
                        pid, found[pid]["path"], path)
            continue
        found[pid] = m
    return found


# ---------- mission control bridge (read-only, degrade gracefully) ----------

def mc_registry() -> dict:
    try:
        with open(MC_APPS_YAML) as f:
            reg = yaml.safe_load(f) or {}
        return {k: v for k, v in reg.items() if isinstance(v, dict)}
    except Exception:
        return {}


def mc_by_cwd(registry: dict) -> dict[str, list[str]]:
    """Which MC apps run out of which directory.

    `PROJECT.yaml` has an `mc:` field for naming the apps a repo ships, and it is
    a foreign key nothing enforces: 3 repos of 21 declare it while 8 more are
    managed by Mission Control without saying so. So the fleet view read
    "not managed" for most of a fleet that was demonstrably running.

    apps.yaml already carries `cwd` per app, which is the same fact from the side
    that cannot drift — MC could not start the app without it. Deriving the link
    from there means one source and no upkeep; the declared `mc:` field still
    wins where it exists, because a repo naming a subset of its apps on purpose
    is a judgement this should not overrule.
    """
    out: dict[str, list[str]] = {}
    for app_id, spec in registry.items():
        cwd = spec.get("cwd")
        if not cwd:
            continue
        try:
            key = str(Path(cwd).expanduser().resolve())
        except OSError:
            continue
        out.setdefault(key, []).append(app_id)
    return out


def mc_alive() -> bool:
    """Cheap MC liveness ping for /health. Deliberately hits /api/system (host
    stats), NOT /api/apps: /api/apps re-probes every registered app — including
    shipyard's own /health — so calling it from our health handler creates a
    probe feedback loop once shipyard is in MC's registry."""
    try:
        with urllib.request.urlopen(f"{MC_URL}/api/system", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def mc_status() -> dict:
    """Live status by app id from MC's API; {} when MC is down."""
    try:
        with urllib.request.urlopen(f"{MC_URL}/api/apps", timeout=3) as r:
            data = json.load(r)
    except Exception:
        return {}
    apps = data if isinstance(data, list) else data.get("apps", [])
    if isinstance(apps, dict):
        apps = list(apps.values())
    out = {}
    for a in apps:
        if isinstance(a, dict):
            aid = a.get("id") or a.get("name")
            if aid:
                out[aid] = a
    return out


# ---------- git ----------

def git_activity(path: Path, weeks: int = ACTIVITY_WEEKS) -> dict[str, int]:
    """Commits per day, for the heatmap. Free history — nothing to type into."""
    if not (path / ".git").exists():
        return {}
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "log", f"--since={weeks} weeks ago",
             "--format=%cd", "--date=format:%Y-%m-%d"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    days: dict[str, int] = {}
    for line in out.stdout.splitlines():
        day = line.strip()
        if day:
            days[day] = days.get(day, 0) + 1
    return days


def git_last_activity(path: Path) -> str | None:
    """ISO date of the last commit — the delta the board was missing."""
    if not (path / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%cI"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _cycle_counts(path: Path, manifest: dict) -> dict:
    """Closed cycles, and whether one is in flight — the same two facts
    `_open_gate` refuses on, so the chip and the 422 can never disagree.

    `planned` and not `open`: `open` is commits since the last tag, the normal
    state of every repo between releases. A record with no tag is the cycle
    somebody left running.
    """
    state = repo_mod.cycles(path, _records_dir(manifest))
    return {"closed": state["counts"]["cut"] if state.get("counts") else 0,
            "open": bool(state.get("planned"))}


def _repo_facts(manifest: dict) -> dict:
    """Everything project_view reads out of a repo's working tree, in one bundle.

    These are the expensive reads — several git processes per repo, run
    serially across the whole fleet, which is what made a Fleet load take
    seconds. They derive from the tree alone, so one entry per repo path can
    serve /api/projects, /api/owed and /api/board together without ever holding
    chart, shelf or MC state — those change through other doors and stay live.
    `documents` also reads the manifest's links; a links edit rides the TTL,
    since the only thing that writes links is an editor, not a route.
    """
    path = Path(manifest.get("path", ""))
    last_activity = git_last_activity(path)
    ver = repo_mod.version(path)
    return {"last_activity": last_activity,
            "version": ver,
            "changelog": repo_mod.changelog(path, ver["tag"] if ver else None),
            "documents": repo_mod.documents(path, manifest.get("links") or {}),
            "open_tasks": sum(1 for t in work_mod.read_tasks(path) if t["open"]),
            # What the strip's third column asks: may I start work here. Cheap
            # only because it rides this bundle — `repo.cycles` shells git per
            # repo, and calling it uncached from the board would run it serially
            # across every manifest, which is what made Fleet loads take seconds.
            "cycles": _cycle_counts(path, manifest)}


def _chart_expected(view: dict) -> bool:
    """Whether this repo is meant to answer to a problem at all.

    `chart: none` in PROJECT.yaml declares that it is not — a tool, a fork, a
    scratch collection, where the manifest's own description is the whole of why it
    exists. Anything else, including silence, still expects a node: the exemption is
    claimed, never acquired by neglect, exactly as `release: scheme: none` is.
    """
    return str(view.get("chart") or "").strip().lower() != "none"


def project_view(manifest: dict, con: sqlite3.Connection,
                 registry: dict, status: dict,
                 by_cwd: dict[str, list[str]] | None = None) -> dict:
    path = Path(manifest.get("path", ""))
    # Declared wins; derived fills the gap. See `mc_by_cwd` for why both exist.
    mc_ids = manifest.get("mc") or []
    if not mc_ids and by_cwd:
        try:
            mc_ids = by_cwd.get(str(path.resolve()), [])
        except OSError:
            mc_ids = []
    mc_info = []
    uptime = None
    for mid in mc_ids:
        entry = registry.get(mid, {})
        live = status.get(mid) or status.get(entry.get("name", ""), {})
        up = live.get("uptime_s")
        # The oldest running process is the one that decides staleness: if any part
        # of the app started before the newest commit, the app is running old code.
        if isinstance(up, (int, float)) and (uptime is None or up > uptime):
            uptime = up
        mc_info.append({"id": mid, "name": entry.get("name", mid),
                        "ports": entry.get("ports", []),
                        "open_url": entry.get("open_url"),
                        "status": live.get("status") or live.get("state"),
                        "uptime_s": up,
                        "health": live.get("health")})
    # What a card says now: is it charted, how well evidenced, how much is open, and
    # when it last moved. Conformance to a standard was never the point.
    root = chart.resolve(con, manifest["id"])
    facts = _facts_cache.get(str(path), lambda: _repo_facts(manifest))
    return {**manifest, "mc_info": mc_info,
            "last_activity": facts["last_activity"],
            "charted": bool(root),
            "sounding": chart.effective_sounding(con, root["id"]) if root else None,
            # Why this repo exists, carried on the project itself. The root node was
            # already loaded to compute the sounding, so this costs nothing — and
            # without it a fleet row has to fetch the chart per project to answer the
            # one question the row exists to answer.
            "why": root["title"] if root else None,
            "waypoint": root.get("waypoint") if root else None,
            "open_tasks": facts["open_tasks"],
            "cycles": facts["cycles"],
            "version": facts["version"],
            "changelog": facts["changelog"],
            "documents": facts["documents"],
            "running_behind": repo_mod.running_behind(facts["last_activity"], uptime)}


# ---------- api ----------

@app.get("/api/projects")
def api_projects():
    """Every repo on disk — shelved ones included, and flagged rather than dropped.

    Shelving is a decision about the *board*. Fleet is the page that catches a repo
    with unpushed work rotting for a month, and letting one opt out of that would
    turn a view preference into a way to stop being told. So it is marked here, not
    hidden: a project absent from the board but present in Fleet is explained on
    sight instead of reading as a bug.
    """
    registry, status = mc_registry(), mc_status()
    by_cwd = mc_by_cwd(registry)
    con = db()
    try:
        shelf = shelved_mod.ids(con)
        views = [{**project_view(m, con, registry, status, by_cwd),
                  "shelved": m["id"] in shelf}
                 for m in scan_manifests().values()]
    finally:
        con.close()
    views.sort(key=lambda v: v["id"])
    return {"projects": views}


@app.get("/api/memory")
def api_memory():
    """What each project remembers about itself, and what it has never written down.

    Four kinds of durable memory, read where they already live — no new store, and
    nothing here is a shipyard convention:

      why       a chart node. Recorded reasoning: the problem this repo attacks.
      rules     a CHARTER: what is fenced off, and the order things get cut.
      shape     ARCHITECTURE.md: boundaries, dependency direction, state ownership.
      choices   ADRs: what was decided, and against what alternative.

    Grouped by what is MISSING rather than ranked by how complete a project is.
    A score would answer "which repo is worst"; the real question is "what has this
    project never written down" — and the same guardrail that shaped Owed applies,
    since Road to 1.0 prunes anything that scores a project.

    Absence is not automatically debt. A three-file spike needs no charter, so this
    reports coverage and lets the reader judge; it does not nag.
    """
    manifests = scan_manifests()
    con = db()
    try:
        charted = {p["repo"] for p in chart.all_problems(con) if p.get("repo")}
        shelf = shelved_mod.ids(con)
        projects = []
        for pid, m in sorted(manifests.items()):
            if pid in shelf:
                continue
            path = Path(m["path"])
            docs = repo_mod.documents(path, m.get("links") or {})
            by_label = {d["label"]: d for d in docs if d.get("kind") == "file"}
            adrs = repo_mod.decisions(path)
            projects.append({
                "id": pid, "name": m.get("name") or pid,
                "why": pid in charted,
                "rules": by_label.get("charter", {}).get("path"),
                "shape": by_label.get("architecture", {}).get("path"),
                "choices": len(adrs),
            })
    finally:
        con.close()

    kinds = [
        ("why", "no chart node — nothing records why this repo exists",
         lambda p: not p["why"]),
        ("rules", "no charter — nothing states what this project has ruled out",
         lambda p: not p["rules"]),
        ("shape", "no ARCHITECTURE.md — the boundaries live only in someone's head",
         lambda p: not p["shape"]),
        ("choices", "no ADRs — decisions were made and the reasoning was not kept",
         lambda p: p["choices"] == 0),
    ]
    missing = [{"kind": k, "why": why,
                "projects": [{"id": p["id"], "name": p["name"]} for p in projects if pred(p)]}
               for k, why, pred in kinds]
    complete = [p for p in projects
                if p["why"] and p["rules"] and p["shape"] and p["choices"]]
    return {"missing": missing, "complete": complete,
            "projects": projects, "scanned": len(projects)}


@app.get("/api/owed")
def api_owed():
    """What the fleet owes, grouped by kind rather than ranked by project.

    Every number here was already computed per project; the only thing that was
    missing was somewhere to see all of them at once. Shipyard sat 48 commits
    past its own tag for five days with its own header reporting it, because
    reading that header meant opening the one page that shows it.

    Built on `project_view` rather than beside it, so the two surfaces cannot
    disagree — and serially, like `/api/projects`, because the board already
    pays exactly this cost for the same repos.
    """
    registry, status = mc_registry(), mc_status()
    by_cwd = mc_by_cwd(registry)
    con = db()
    try:
        views = [project_view(m, con, registry, status, by_cwd)
                 for m in scan_manifests().values()]
    finally:
        con.close()

    buckets: dict[str, list] = {k: [] for k, _ in repo_mod.OWED_KINDS}
    clear = []
    for v in views:
        items = repo_mod.owed(v.get("version"), v.get("changelog"),
                              v.get("running_behind"), bool(v.get("charted")),
                              _chart_expected(v))
        if not items:
            clear.append({"id": v["id"], "name": v.get("name") or v["id"]})
            continue
        for it in items:
            buckets[it["kind"]].append(
                {"id": v["id"], "name": v.get("name") or v["id"],
                 "n": it["n"], "detail": it["detail"],
                 "last_activity": v.get("last_activity")})

    # Within a kind, loudest first; ties by name so the order is stable between
    # loads rather than following whatever order the scan happened to return.
    for rows in buckets.values():
        rows.sort(key=lambda r: (-(r["n"] or 0), r["name"].lower()))

    return {"kinds": [{"kind": k, "why": why, "projects": buckets[k]}
                      for k, why in repo_mod.OWED_KINDS],
            "clear": sorted(clear, key=lambda r: r["name"].lower()),
            "scanned": len(views)}


# ---------- the yard (v0.28.0) ----------

# Display order — the mockup's console order, clear first. Assignment precedence
# runs the OTHER way (shelved > owes > uncharted > no-waypoint > clear): a repo
# lands under the strongest reason it cannot start, and appears exactly once.
_YARD_BAYS = [
    ("clear", "Cleared to enter",
     "owing nothing, charted, waypointed — a cycle can open whenever you choose"),
    ("owes", "Owes work",
     "the gate would refuse these today — the debt is the blocker, named per strip"),
    ("uncharted", "Uncharted",
     "nothing records why these exist — a repo with no problem node cannot enter the line"),
    ("no-waypoint", "No waypoint",
     "charted, but nothing records what entering the line would even mean"),
    ("shelved", "Shelved",
     "the one deliberate hide — grey means out of service, not unimportant"),
]

# The kinds that read red: work that is *lost* if this machine dies, plus a
# process serving code older than the tree. The rest of `owed` is amber — real,
# but merely undescribed rather than unrecoverable.
_DANGER_KINDS = {"uncommitted", "unpushed", "no-remote", "running-old-code"}


def _bay_of(shelved: bool, blockers: list[dict], root: dict | None) -> str:
    """Which bay holds this repo — the reason it cannot start (D5), first match wins.

    `uncharted` is an owed kind *and* a bay, and the kind is excluded from the
    owes test on purpose: owed's uncharted item rides along as a blocker chip,
    but a clean-git uncharted repo belongs in the bay that names its actual
    problem — were it "owes", the uncharted bay could never hold anything.
    """
    if shelved:
        return "shelved"
    if any(b["kind"] != "uncharted" for b in blockers):
        return "owes"
    if root is None:
        return "uncharted"
    if root.get("draft"):        # charted, waypoint since blanked — still no observable
        return "no-waypoint"
    return "clear"


def _lamp(bay: str, blockers: list[dict]) -> str:
    """Colour doctrine, pinned once: red = would-be-lost debt, amber = owed or
    unexplained, zinc = inert (shelved — never de-emphasis), green = flowing."""
    if bay == "shelved":
        return "off"
    if bay == "clear":
        return "ok"
    if any(b["kind"] in _DANGER_KINDS for b in blockers):
        return "danger"
    return "warn"


def _runtime_of(mc_info: list[dict]) -> dict | None:
    """One runtime reading per strip, folded from the repo's MC apps.

    None when there is no MC entry at all — a library was never something you
    start, and "stopped" about it is a small lie the eye has to correct. The
    state derivation is the old Fleet's `runtimeState`, moved server-side so
    the strip, the inspector and any future band read one derivation.
    """
    if not mc_info:
        return None
    up = any("run" in str(e.get("status") or "").lower() or e.get("health") is True
             for e in mc_info)
    if not up:
        state = "stopped"
    elif any(e.get("health") is False for e in mc_info):
        state = "unhealthy"
    else:
        state = "running"
    ports: list = []
    for e in mc_info:
        for p in e.get("ports") or []:
            if p not in ports:
                ports.append(p)
    uptimes = [e["uptime_s"] for e in mc_info
               if isinstance(e.get("uptime_s"), (int, float))]
    # The oldest process is the honest uptime — same call `project_view` makes
    # for staleness: if any part started before the newest commit, the app is
    # running old code, so the max is the number that matters.
    return {"state": state, "ports": ports,
            "uptime_s": max(uptimes) if uptimes else None}


@app.get("/api/yard")
def api_yard():
    """The yard — everything not on the line, grouped by what blocks entry (D5).

    Fleet's four groupings collapsed into one question with named answers. A repo
    appears under the reason it cannot start, and appears once; within a bay the
    order is the roster's id order — admission, never merit (guardrail 2: this
    page never ranks repos). Empty bays are omitted: nothing renders empty
    scaffolding.

    Composed here from reads that already exist — `project_view` for the facts,
    `repo.owed` re-read as an intake predicate (D3, same computation, new
    sentence), the chart for why/goal/manned, shelved for the one deliberate
    hide. No new module, no new storage, and it rides the same cached scan and
    git facts the rest of the Fleet load pays for once.

    Shelved strips keep their REAL owed blockers: the bay says "deliberately out
    of service", and hiding the debt too would let the inspector overstate how
    clean the shelf is.
    """
    registry, status = mc_registry(), mc_status()
    by_cwd = mc_by_cwd(registry)
    con = db()
    try:
        shelf = shelved_mod.ids(con)
        standings = shelved_mod.standing(con)
        views = [project_view(m, con, registry, status, by_cwd)
                 for m in scan_manifests().values()]
        views.sort(key=lambda v: v["id"])
        bays: dict[str, list] = {key: [] for key, _, _ in _YARD_BAYS}
        for v in views:
            blockers = repo_mod.owed(v.get("version"), v.get("changelog"),
                                     v.get("running_behind"), bool(v.get("charted")),
                                     _chart_expected(v))
            root = chart.resolve(con, v["id"])
            goal = None
            if root:
                pin = chart.nearest_pinned(con, root["id"])
                if pin:
                    goal = (chart.get(con, pin) or {}).get("title")
            bay = _bay_of(v["id"] in shelf, blockers, root)
            bays[bay].append({
                "id": v["id"],
                "name": v.get("name") or v["id"],
                "cycles": v.get("cycles"),
                "lamp": _lamp(bay, blockers),
                "blockers": blockers,
                "why": v.get("why"),
                "goal": goal,
                "runtime": _runtime_of(v.get("mc_info") or []),
                "version": (v.get("version") or {}).get("tag"),
                "last_activity": v.get("last_activity"),
                # Holds a focus slot — the same `active` flag `focus_slots`
                # derives from, read off the repo's own problem node.
                "manned": bool(root and root.get("active")),
                # Declared standing, or None for a repo nobody has ruled on. Three
                # states and one of them is silence: "not yet considered" is a real
                # answer and must not collapse into "not carried".
                "standing": standings.get(v["id"], {}).get("state"),
            })
        queue = _queue(con)
    finally:
        con.close()
    return {"bays": [{"key": key, "title": title, "why": why, "strips": bays[key]}
                     for key, title, why in _YARD_BAYS if bays[key]],
            "queue": queue,
            "scanned": len(views)}


def _queue(con: sqlite3.Connection) -> list[dict]:
    """The queue: problems captured without an observable, waiting to become work.

    Not a new store and not a second list. `create_problem(draft=True)` has always
    been the fast-capture opt-out from the waypoint requirement — *"you cannot demand
    an observable between pressing Enter and having the next thought"* — and a draft
    is already flagged, already counted as debt on the goals page, and already
    refused a repo link. What it never had was a surface that asks you to finish it.

    **Promotion is writing the waypoint.** There is no promote verb, because there is
    nothing else to do: the moment a draft has an observable it stops being a draft,
    `_open_gate` stops refusing it, and a cycle can open against it. That is why the
    queue empties only one way, and why nothing here writes.

    References are excluded, matching `/api/goals`: a node shown twice is one node,
    and a queue that listed it twice would ask you to finish it twice.

    **A draft with children is not in the queue.** Measured on the real chart before
    this filter existed: the queue opened with `<root goal>`
    and its five `<domain>` groupings — the skeleton the whole chart
    hangs from, waypointless because a grouping has no observable of its own and
    never will. Six of the twelve rows were things you can never start, at the top of
    a band whose entire question is what to start next. The same discriminator
    `_open_gate` uses: a node with problems beneath it composes work rather than
    being work. Their draft debt is still counted on the goals page, which is where
    a question about the chart's shape belongs.
    """
    drafts = [r for r in chart.outline(con) if not r["reference"] and r["draft"]]
    out = []
    for r in drafts:
        if chart.children(con, r["id"]):
            continue
        parent = chart.parents(con, r["id"])
        out.append({
            "id": r["id"],
            "title": r["title"],
            # The problem it would serve, which is the whole of why it is worth
            # finishing. A draft with no parent is a loose thought and says so.
            "parent": parent[0]["title"] if parent else None,
            "created_at": r.get("created_at"),
        })
    # Oldest first: the one that has been waiting longest is the one the queue is
    # asking about. Never ranked by anything else — guardrail 2 holds here too.
    out.sort(key=lambda r: r.get("created_at") or "")
    return out


# ---------- the ledger (v0.29.0): motion, reach, position, appetite ----------

@app.get("/api/projects/{pid}")
def api_project(pid: str):
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    con = db()
    try:
        return project_view(manifests[pid], con, mc_registry(), mc_status())
    finally:
        con.close()


class PinIn(BaseModel):
    pinned: bool


class ImportIn(BaseModel):
    path: str
    name: str | None = None
    description: str = ""


@app.put("/api/problems/{pid}/pin")
def api_pin(pid: str, body: PinIn):
    """Make a goal a board heading, or stop it being one. Structure is untouched."""
    con = db()
    try:
        chart.set_pinned(con, pid, body.pinned)
        con.commit()
        return chart.get(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/api/importable")
def api_importable():
    """Git repos on disk that shipyard cannot see, because they carry no manifest.

    Reported, never adopted: which of nineteen repos is *relevant* is a judgment
    the tool does not get to make.
    """
    known = {m["path"] for m in scan_manifests().values()}
    return {"repos": repo_mod.discover(CODE_ROOT, known, skip=SCAN_SKIP)}


@app.post("/api/importable")
def api_import(body: ImportIn):
    """Adopt one repo by writing a manifest into it."""
    # Resolve before comparing, the same shape as repo.read_document: a prefix
    # check on the unresolved string accepts `code/../elsewhere` and siblings
    # like `code-evil`, and the manifest then lands outside the fleet root.
    path = Path(body.path).expanduser().resolve()
    if not path.is_relative_to(CODE_ROOT.resolve()):
        raise HTTPException(422, "that path is outside the code root")
    try:
        out = repo_mod.write_manifest(
            path, name=body.name or path.name,
            description=body.description)
    except repo_mod.RepoError as e:
        raise HTTPException(422, str(e))
    # Adoption changes what the next scan finds, and the manifest write dirtied
    # the repo's tree — served cached, both would still show the pre-adoption
    # world to the request the UI fires immediately after this one.
    _scan_cache.clear()
    _facts_cache.forget_under(path)
    return out


class GroupBody(BaseModel):
    title: str
    bearing_ids: list[str]
    child_ids: list[str]
    waypoint: str = ""


@app.get("/api/chart-groupings")
def api_groupings():
    """Where the chart repeats a bearing set often enough that naming it would pay."""
    con = db()
    try:
        return {"groupings": chart.repeated_bearings(con)}
    finally:
        con.close()


@app.post("/api/chart-groupings")
def api_group(body: GroupBody):
    con = db()
    try:
        out = chart.group_under(con, title=body.title, bearing_ids=body.bearing_ids,
                                child_ids=body.child_ids, waypoint=body.waypoint)
        con.commit()
        _export_chart(con)
        return out
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/api/projects/{pid}/survey")
def api_survey(pid: str):
    """What the code shows about itself: shape, layout, how to start it, what it
    leans on. Derived, so it is never empty for a repo that exists."""
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    path = Path(manifests[pid]["path"])
    out = survey_mod.survey(path) or {}
    # Layout says where the weight sits, churn says where the attention went. They
    # come from different places — the tree and git — so they are composed here
    # rather than letting either module reach into the other's domain.
    out["churn"] = repo_mod.churn(path)
    return out


@app.get("/api/projects/{pid}/recent")
def api_recent(pid: str):
    """Commits since the last release and the state of the working tree."""
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    path = Path(manifests[pid]["path"])
    ver = repo_mod.version(path)
    return repo_mod.recent_work(path, ver["tag"] if ver else None)


def _project_path(repo_id: str | None) -> str | None:
    """Where a linked repo lives, so the tree can offer its own cut versions."""
    if not repo_id:
        return None
    m = scan_manifests().get(repo_id)
    return m["path"] if m else None


def _records_dir(manifest: dict) -> Path | None:
    """Where this project's cycle records live.

    Vault folders are named by hand, so they do not always match the manifest —
    "My App" may live in `MyApp`. Try the plausible spellings rather than demand
    a convention nobody agreed to.

    Prefer the repo's own `docs/cycles/`: it is under git, it travels with the code,
    and `mirror_records` has been copying the vault into it all along. The vault is
    the fallback, not the source — authoring may happen there, but a record that only
    exists in the vault is one reorganisation away from being unreachable, which is
    exactly what happened when `Projects/` was archived on 2026-08-14.
    """
    path = manifest.get("path")
    if path:
        d = Path(path) / "docs" / "cycles"
        if d.is_dir():
            return d

    name = manifest.get("name") or manifest["id"]
    for candidate in (name, name.replace(" ", ""), name.replace(" ", "-"),
                      manifest["id"], manifest["id"].replace("-", "")):
        d = CYCLES_ROOT / candidate / "Cycles"
        if d.is_dir():
            return d
    return None


@app.get("/api/projects/{pid}/cycles")
def api_cycles(pid: str):
    """Every cut version as a plan-build-test-review cycle.

    The tags already are the history — "the git tags are the only durable record of
    finished work" — so this joins them to what each produced and what was learned.
    """
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    path = Path(manifests[pid]["path"])
    return repo_mod.cycles(path, _records_dir(manifests[pid]))


@app.post("/api/projects/{pid}/cycles/mirror")
def api_mirror_cycles(pid: str):
    """Copy the vault's cycle records into the repo.

    Explicit rather than a side effect of reading: a GET that writes files is the
    kind of hidden behaviour this app exists to argue against.
    """
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    try:
        out = repo_mod.mirror_records(_records_dir(manifests[pid]),
                                      Path(manifests[pid]["path"]))
    except repo_mod.RepoError as e:
        raise HTTPException(422, str(e))
    # Mirrored records land in the repo's tree: its dirty count just moved.
    _facts_cache.forget_under(Path(manifests[pid]["path"]))
    return out


@app.get("/api/projects/{pid}/decisions")
def api_decisions(pid: str):
    """The ADRs this repo keeps. Empty is a normal answer, not an error."""
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    return {"decisions": repo_mod.decisions(Path(manifests[pid]["path"]))}


@app.get("/api/projects/{pid}/doc")
def api_document(pid: str, path: str):
    """Read one document out of a project, for the in-app reader.

    A repo-relative path off the query string is untrusted input; `repo.read_document`
    resolves it and refuses anything landing outside the project.
    """
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    try:
        return repo_mod.read_document(Path(manifests[pid]["path"]), path)
    except repo_mod.RepoError as e:
        raise HTTPException(404, str(e))


@app.get("/api/board")
def api_board():
    """The board, rendered from the chart.

    Sections are root problems. Under each sits every problem in its subtree: those
    with a repo are projects (full cards), those without are **ghosts** — decomposed
    but not yet attacked, which is exactly the gap worth seeing.

    A project whose repo has no problem node lands in `uncharted`, and one no heading
    claims lands in `ungrouped`. Nothing on disk is ever silently absent from this
    board — the single exception is a **shelved** repo, and it is not silent: the
    count rides on every response so the way back is always on screen.
    """
    manifests = scan_manifests()
    registry, status = mc_registry(), mc_status()
    by_cwd = mc_by_cwd(registry)
    con = db()
    try:
        # Shelving is deliberate invisibility, so it is applied at the source: drop
        # the manifest and every downstream pile — sections, ghosts, ungrouped,
        # uncharted — is filtered by construction rather than by four filters that
        # can disagree. A problem whose repo is shelved keeps its chart node; what
        # it loses is a card.
        shelf = shelved_mod.ids(con)
        manifests = {k: v for k, v in manifests.items() if k not in shelf}
        def card(problem: dict) -> dict:
            repo = problem.get("repo")
            m = manifests.get(repo) if repo else None
            base = {
                "problem_id": problem["id"],
                "title": problem["title"],
                "waypoint": problem["waypoint"],
                "sounding": chart.effective_sounding(con, problem["id"]),
                "anchored": problem.get("anchored"),
                "ghost": m is None,
            }
            if m is None:
                # A ghost must never wear a project's clothes: no status, no activity.
                return base
            view = project_view(m, con, registry, status, by_cwd)
            return {**base, "ghost": False, "id": view["id"], "name": view.get("name"),
                    "description": view.get("description"), "tags": view.get("tags"),
                    "cycles": view.get("cycles"), "mc_info": view["mc_info"],
                    "last_activity": view["last_activity"], "open_tasks": view["open_tasks"],
                    "path": view.get("path")}

        sections = []
        charted_repos = set()
        # A card appears ONCE, under the first bearing that claims it. A problem can
        # serve several, and rendering its whole subtree under each turns the board
        # into a hall of mirrors — one project appeared twice with ten ghosts each.
        placed: set[str] = set()
        # Headings are pinned goals, falling back to roots when nothing is pinned.
        # A chart deep enough to be useful has one root and fifty descendants, so
        # sectioning by root collapses the whole board into a single column.
        heads = chart.pinned_problems(con) or chart.roots(con)
        pinned_mode = bool(chart.pinned_problems(con))
        for root in heads:
            cards = []
            # With pins, a project can sit four levels below its heading, so the
            # section gathers every attacked problem whose nearest pin is this one.
            # Without pins the old rule stands: direct children only, or the board
            # buries the projects under their own sub-sub-problems.
            if pinned_mode:
                members = [p for p in chart.descendants(con, root["id"])
                           if p.get("repo") and chart.nearest_pinned(con, p["id"]) == root["id"]]
                members += [p for p in chart.children(con, root["id"]) if not p.get("repo")]
            else:
                members = chart.children(con, root["id"])
            for p in members:
                if p.get("repo"):
                    charted_repos.add(p["repo"])
                    # Without this a shelved project would come back as a *ghost* —
                    # its manifest is filtered out above, and `card()` reads a
                    # missing manifest as "decomposed but never attacked". That is
                    # a different claim about the work, and a false one.
                    if p["repo"] in shelf:
                        continue
                if p["id"] in placed:
                    continue
                placed.add(p["id"])
                c = card(p)
                others = [q["title"] for q in chart.parents(con, p["id"])
                          if q["id"] != root["id"]]
                if others:
                    c["also_serves"] = others
                kids = chart.children(con, p["id"])
                c["child_count"] = len(kids)
                # v0.20.0 rollup: solved beneath, so the board answers "how far in"
                # without opening the problem. Direct children only — a recursive
                # count would let a deep subtree read as progress on a shallow one.
                c["solved"] = bool(p.get("solved"))
                c["solved_below"] = sum(1 for k in kids if k.get("solved"))
                cards.append(c)
            sections.append({
                "id": root["id"], "title": root["title"], "waypoint": root["waypoint"],
                "sounding": chart.effective_sounding(con, root["id"]),
                "anchored": root.get("anchored"),
                "pinned": root.get("pinned", False),
                "cards": cards,
            })
            if root.get("repo"):
                charted_repos.add(root["repo"])

        # A charted project with no pinned ancestor belongs to no section, and
        # before this it was simply dropped: removing a heading made its projects
        # disappear from the board while their edges sat untouched in the chart.
        # That is the one thing this board promises never to do. They gather here
        # instead — still draggable, so the way back is to drop one into a group.
        #
        # Not `uncharted`: these have a problem node. What they lack is a heading.
        ungrouped = []
        head_ids = {h["id"] for h in heads}
        for p in chart.all_problems(con):
            if not p.get("repo") or p["id"] in placed or p["id"] in head_ids:
                continue
            charted_repos.add(p["repo"])
            if p["repo"] in shelf:
                continue
            placed.add(p["id"])
            ungrouped.append(card(p))

        charted_repos |= {p["repo"] for p in chart.all_problems(con) if p.get("repo")}
        uncharted = [project_view(m, con, registry, status, by_cwd)
                     for pid, m in sorted(manifests.items()) if pid not in charted_repos]
        # Always, even when empty. A count the UI can render unconditionally is what
        # keeps deliberate invisibility from becoming the silent kind.
        shelf_listing = shelved_mod.listing(con)
    finally:
        con.close()
    return {"sections": sections, "ungrouped": ungrouped, "uncharted": uncharted,
            "shelved": shelf_listing}


class ShelveIn(BaseModel):
    repo: str
    note: str = ""


@app.get("/api/shelved")
def api_shelved():
    con = db()
    try:
        return {"shelved": shelved_mod.listing(con)}
    finally:
        con.close()


@app.post("/api/shelved")
def api_shelve(body: ShelveIn):
    """Take a project off the board without touching a single file.

    Refuses a repo it cannot see, so a typo cannot shelve nothing and read as
    success — and so the restore list can never fill with names that mean nothing.
    """
    if body.repo not in scan_manifests():
        raise HTTPException(404, f"no PROJECT.yaml found for '{body.repo}'")
    con = db()
    try:
        out = shelved_mod.shelve(con, body.repo, body.note)
        con.commit()
        return out
    finally:
        con.close()


@app.delete("/api/shelved/{repo}")
def api_restore(repo: str):
    """Put it back. Deliberately idempotent and deliberately not validated against
    disk: the way back must work even for a repo that has since been moved away,
    or the row would be unremovable."""
    con = db()
    try:
        out = shelved_mod.restore(con, repo)
        con.commit()
        return out
    finally:
        con.close()


@app.get("/api/conventions")
def api_conventions():
    """The conventions this fleet runs on, and which of them have teeth.

    Reads no repo and scores nothing — see `standards.py` for why that boundary is
    the whole design, and why `standards.yaml` being deleted in v0.5.0 does not
    make this a revival of it.
    """
    return conv_mod.read(ROOT)


class CarryIn(BaseModel):
    repo: str
    note: str = ""


@app.post("/api/carried")
def api_carry(body: CarryIn):
    """Declare a repo as work you are carrying — the membership the ledger reads.

    Validated against disk for the same reason shelving is: a typo must not carry
    nothing and read as success. Carrying a shelved repo moves it rather than
    erroring — the table holds one state per repo, and saying "I am working on this
    again" is a perfectly ordinary thing to do to something you had set down.
    """
    if body.repo not in scan_manifests():
        raise HTTPException(404, f"no PROJECT.yaml found for '{body.repo}'")
    con = db()
    try:
        out = shelved_mod.carry(con, body.repo, body.note)
        con.commit()
        return out
    finally:
        con.close()


@app.delete("/api/carried/{repo}")
def api_uncarry(repo: str):
    """Stop carrying, without shelving. Idempotent and unvalidated, like `restore`:
    the way back must work for a repo that has since moved away, or the row would be
    unremovable. Dropping the row is not the same as shelving — that would claim a
    decision ("I looked and set this down") the caller never made."""
    con = db()
    try:
        out = shelved_mod.uncarry(con, repo)
        con.commit()
        return out
    finally:
        con.close()


class ParentIn(BaseModel):
    parent_id: str | None = None


class LinkIn(BaseModel):
    repo: str | None = None


@app.put("/api/problems/{pid}/parent")
def api_set_parent(pid: str, body: ParentIn):
    """Drag a card to another section: what this work is *for* changes."""
    con = db()
    try:
        chart.set_parent(con, child_id=pid, parent_id=body.parent_id)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.put("/api/problems/{pid}/repo")
def api_link_repo(pid: str, body: LinkIn):
    """Promote a problem to a project — the moment reasoning becomes work."""
    if body.repo and body.repo not in scan_manifests():
        raise HTTPException(404, f"no PROJECT.yaml found for '{body.repo}'")
    con = db()
    try:
        chart.link_repo(con, pid, body.repo)
        con.commit()
        _export_chart(con)
        return chart.get(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/api/unlinked")
def api_unlinked():
    """Repos not yet attached to any problem — the promote picker's options."""
    con = db()
    try:
        taken = {p["repo"] for p in chart.all_problems(con) if p.get("repo")}
    finally:
        con.close()
    return {"repos": [{"id": pid, "name": m.get("name", pid)}
                      for pid, m in sorted(scan_manifests().items()) if pid not in taken]}


@app.get("/api/projects/{pid}/activity")
def api_activity(pid: str):
    manifests = scan_manifests()
    if pid not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml found for '{pid}'")
    return {"days": git_activity(Path(manifests[pid]["path"])), "weeks": ACTIVITY_WEEKS}


# ---------- chart ----------

class ProblemIn(BaseModel):
    title: str
    waypoint: str
    sounding: str = "assumed"
    repo: str | None = None
    anchored_at: str | None = None
    anchor_basis: str | None = None
    falsifier: str | None = None
    # Accepted on create, not only on PATCH. Pydantic drops unknown fields
    # silently, so a caller that posted a description got a 200 and lost the text
    # with nothing to indicate it — the failure this codebase refuses everywhere
    # else, arriving through the one door that had not been checked.
    description: str | None = None
    notes: str | None = None
    parent_id: str | None = None   # ↑ this problem serves that one
    child_id: str | None = None    # ↓ that problem serves this one
    draft: bool = False            # outline capture: waypoint deferred


class EdgeIn(BaseModel):
    parent_id: str


class CycleLink(BaseModel):
    version: str


@app.get("/api/problems/{pid}/cycle-options")
def api_cycle_options(pid: str):
    """Cycles this problem could be addressed by, and which are already linked.

    Offered from real tags rather than typed: `chart.address` validates the *shape*
    of a version, not that anything ever cut it, so a free-text field would happily
    record a phantom cycle that no repo can corroborate.
    """
    con = db()
    try:
        if not chart.get(con, pid):
            raise HTTPException(404, f"no problem '{pid}'")
        linked = chart.addressed_by(con, pid)
        repos = chart.nearest_repos(con, pid)
    finally:
        con.close()

    manifests = scan_manifests()
    options = []
    for r in repos:
        m = manifests.get(r)
        if not m:
            continue
        for c in repo_mod.cycles(Path(m["path"]))["cycles"]:
            v = c.get("version")
            if v:
                options.append({"version": v, "repo": r, "weight": c.get("weight"),
                                "date": c.get("date"), "linked": v in linked})
    # Newest first: the cycle you just cut is the one you are most likely attaching.
    options.sort(key=lambda o: (o.get("date") or "", o["version"]), reverse=True)

    # A linked version with no tag behind it is a cycle in flight, not a mistake.
    # The tag is what closes it, so there is no state here to keep up to date.
    cut = {o["version"].lstrip("v") for o in options}
    open_cycles = [v for v in linked if v.lstrip("v") not in cut]

    con = db()
    try:
        r = chart.role(con, pid)
        composition = chart.cycle_composition(con, pid)
        # Everything already spoken for in this repo's line — cut or merely planned
        # — so the proposal steps past open cycles instead of colliding with them.
        claimed = chart.versions_claimed_in(con, repos[0]) if repos else []
    finally:
        con.close()
    latest = None
    if repos:
        m = manifests.get(repos[0])
        ver = repo_mod.version(Path(m["path"])) if m else None
        latest = (ver or {}).get("tag")
    bump = chart.ROLE_BUMP[r]

    return {"id": pid, "repos": repos, "linked": linked, "options": options,
            "open": open_cycles, "role": r, "bump": bump,
            "proposed": repo_mod.next_version(latest, bump, claimed),
            "latest_tag": latest, "claimed": claimed, "composition": composition}


class CycleOpen(BaseModel):
    version: str
    title: str
    # Which repo's version line this cuts. Optional only when there is one
    # candidate; with several, picking silently would cut a tag in a repo the
    # caller never named.
    repo: str | None = None


@app.post("/api/problems/{pid}/cycles/open")
def api_open_cycle(pid: str, body: CycleOpen):
    """Start a PBTR cycle against this problem, before anything is cut.

    Shipyard only ever learned about a cycle at the end, because a tag is the last
    event in P→B→T→R. This is the first: it writes the plan where Development
    Protocol 1.0 already puts cycle records — the vault — and links the problem to a
    version that does not exist yet.

    Nothing marks it done. A record with no tag is open, a record with a tag is
    closed, and cutting the tag is what moves it: the state is read off disk rather
    than typed into.
    """
    con = db()
    try:
        problem = chart.get(con, pid)
        if not problem:
            raise HTTPException(404, f"no problem '{pid}'")
        r = chart.role(con, pid)
        repos = chart.nearest_repos(con, pid)
    finally:
        con.close()

    if not repos:
        raise HTTPException(422, "no repo beneath this problem — a cycle cuts a version "
                                 "in a repo, and there is none to cut")
    if body.repo and body.repo not in repos:
        raise HTTPException(422, f"'{body.repo}' is not beneath this problem "
                                 f"(candidates: {', '.join(repos)})")
    if not body.repo and len(repos) > 1:
        raise HTTPException(422, "several repos sit beneath this problem — name which one "
                                 f"this cycle cuts in ({', '.join(repos)})")
    target = body.repo or repos[0]

    manifests = scan_manifests()
    m = manifests.get(target)
    if not m:
        raise HTTPException(404, f"no PROJECT.yaml for '{target}'")

    con = db()
    try:
        _open_gate(con, pid, target)
    finally:
        con.close()

    # `_records_dir` answers where records ARE; opening one needs where they GO.
    records = _records_dir(m) or (CYCLES_ROOT / (m.get("name") or m["id"]) / "Cycles")
    weight = {"bearing": "Super-cycle", "branch": "Sub-cycle", "leaf": "Light cycle"}[r]
    try:
        rec = repo_mod.scaffold_record(
            records, version=body.version, title=body.title,
            problem=problem["title"], waypoint=problem.get("waypoint"),
            weight=weight, opened=time.strftime("%Y-%m-%d"))
    except repo_mod.RepoError as e:
        raise HTTPException(409, str(e))
    # `records` is the repo's own docs/cycles/ when that exists, and the scaffold
    # just dirtied it; when it is the vault this forgets nothing, correctly.
    _facts_cache.forget_under(records)

    con = db()
    try:
        chart.address(con, pid, body.version)
        ledger.record(con, 'cycle_open', body.version, f"{body.title} · {body.repo or ''}".rstrip(' ·'), pid=pid)
        con.commit()
        _export_chart(con)
        linked = chart.addressed_by(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()
    return {"id": pid, "record": rec, "linked": linked, "repo": target}


@app.post("/api/problems/{pid}/cycles")
def api_address(pid: str, body: CycleLink):
    """Record that a cut cycle ran against this problem.

    "Addressed by", never "solved by": whether the work landed is what the sounding
    says, so a problem with three cycles and an `assumed` sounding stays legible as
    effort spent with no evidence to show for it.
    """
    con = db()
    try:
        chart.address(con, pid, body.version)
        ledger.record(con, 'cycle_link', body.version, None, pid=pid)
        con.commit()
        _export_chart(con)
        return {"id": pid, "addressed_by": chart.addressed_by(con, pid)}
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.delete("/api/problems/{pid}/cycles/{version}")
def api_unaddress(pid: str, version: str):
    con = db()
    try:
        chart.unaddress(con, pid, version)
        con.commit()
        _export_chart(con)
        return {"id": pid, "addressed_by": chart.addressed_by(con, pid)}
    finally:
        con.close()


@app.get("/api/chart/{ref}/tree")
def api_chart_tree(ref: str):
    """One problem's subtree, flat and depth-tagged.

    The same shape the goals outline renders, so a project draws its own chart with
    the tree affordances that already work rather than inventing a second diagram.
    A project's master problem is the one its repo attacks; everything under it is
    local to that project, which is the asymmetry the vocabulary already names —
    above a project is shared, below is its own.
    """
    con = db()
    try:
        node = chart.resolve(con, ref)
        if not node:
            raise HTTPException(404, f"nothing charted for '{ref}'")
        rows = chart.outline(con, node["id"])
        return {"root": node["id"], "outline": rows,
                "cut": [c["version"] for c in
                        repo_mod.cycles(Path(_project_path(node.get("repo")) or "."))["cycles"]]
                       if node.get("repo") else [],
                "total": len(rows),
                "drafts": sum(1 for r in rows if r.get("draft") and not r.get("reference"))}
    finally:
        con.close()


@app.get("/api/chart/{ref}")
def api_chart(ref: str):
    """Spine for one node. `ref` is a problem id or a project id."""
    con = db()
    try:
        view = chart.spine(con, ref)
        if not view:
            raise HTTPException(404, f"no chart node for '{ref}'")
        # The loop rides on the node: three manual marks are columns, Build is
        # derived here so a tick can never disagree with git.
        manifests = scan_manifests()
        view["node"]["build"] = _build_state(view["node"], manifests)
        view["node"]["approaches"] = chart.approaches(con, view["node"]["id"])
        for kid in view["children"]:
            kid["build"] = _build_state(kid, manifests)
        return view
    finally:
        con.close()


@app.get("/api/problems")
def api_problems():
    con = db()
    try:
        return {"problems": chart.all_problems(con)}
    finally:
        con.close()


@app.get("/api/goals")
def api_goals():
    """The goals page: the whole chart as an outline, plus how much draft debt it carries."""
    con = db()
    try:
        rows = chart.outline(con)
        # Whether an argument exists is a state worth managing by — nine of
        # fifty-three carry one — and a stat per row is cheaper than a request per row.
        standing = chart.standings(con)
        for r in rows:
            r["has_argument"] = args_mod.path_for(ARGUMENTS_DIR, r).is_file()
            r["standing"] = standing.get(r["id"], "open")
            r["active"] = bool(r.get("active"))
        drafts = sum(1 for r in rows if not r["reference"] and r["draft"])
        return {"outline": rows, "drafts": drafts,
                "total": sum(1 for r in rows if not r["reference"])}
    finally:
        con.close()


class TemplateIn(BaseModel):
    name: str
    description: str = ""
    from_problem: str | None = None      # save an existing subtree
    problems: list | None = None          # or post a shape directly
    document: dict | None = None          # {filename, body} — a page to fill in


class ApplyIn(BaseModel):
    slug: str


@app.get("/api/templates")
def api_templates():
    return {"templates": tpl_mod.listing(TEMPLATES_DIR)}


@app.get("/api/templates/{slug}")
def api_template(slug: str):
    t = tpl_mod.load(TEMPLATES_DIR, slug)
    if not t:
        raise HTTPException(404, f"no template '{slug}'")
    return t


@app.post("/api/templates")
def api_save_template(body: TemplateIn):
    """Save a shape — usually one lifted straight off a subtree you already built."""
    problems = body.problems
    if body.from_problem:
        con = db()
        try:
            if not chart.get(con, body.from_problem):
                raise HTTPException(404, f"no problem '{body.from_problem}'")
            problems = tpl_mod.from_subtree(
                lambda i: chart.children(con, i), body.from_problem)
        finally:
            con.close()
    try:
        out = tpl_mod.save(TEMPLATES_DIR, name=body.name,
                           problems=problems or [], description=body.description,
                           document=body.document)
    except tpl_mod.TemplateError as e:
        raise HTTPException(422, str(e))
    # templates/ sits inside a fleet repo's tree, like docs/arguments/.
    _facts_cache.forget_under(TEMPLATES_DIR)
    return out


@app.delete("/api/templates/{slug}")
def api_delete_template(slug: str):
    try:
        tpl_mod.delete(TEMPLATES_DIR, slug)
    except tpl_mod.TemplateError as e:
        raise HTTPException(404, str(e))
    _facts_cache.forget_under(TEMPLATES_DIR)
    return {"deleted": slug}


@app.post("/api/problems/{pid}/template")
def api_apply_template(pid: str, body: ApplyIn):
    """Stamp a template under a problem. Nothing is linked afterwards — the copy is
    yours, and shipyard will never tell you it has drifted from its template."""
    t = tpl_mod.load(TEMPLATES_DIR, body.slug)
    if not t:
        raise HTTPException(404, f"no template '{body.slug}'")
    con = db()
    try:
        if not chart.get(con, pid):
            raise HTTPException(404, f"no problem '{pid}'")

        def create(title, waypoint, parent_id):
            return chart.create_problem(con, title=title, waypoint=waypoint,
                                        parent_id=parent_id, draft=not waypoint)

        made = tpl_mod.instantiate(create, pid, t["problems"])
        con.commit()
        _export_chart(con)

        document = None
        if t["document"]:
            problem = chart.get(con, pid)
            fname, text = tpl_mod.render_document(
                t["document"], title=problem["title"],
                slug_of=args_mod.slug(problem["title"]))
            out = DOCUMENTS_DIR / fname
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                # Create-only, like every other scaffold here: a template hands you a
                # page to fill in and must never write over one you already filled.
                if out.exists():
                    document = {"path": str(out), "created": False}
                else:
                    out.write_text(text)
                    document = {"path": str(out), "created": True}
                    _facts_cache.forget_under(out)
            except OSError as e:
                log.warning("document scaffold failed: %s", e)
                document = {"error": str(e)}

        return {"applied": t["name"], "created": len(made),
                "document": document, "chart": chart.spine(con, pid)}
    finally:
        con.close()


@app.get("/api/graph")
def api_graph(root: str | None = None):
    """The chart as nodes and edges — no duplication, no reference rows.

    The outline has to render a two-parent node twice; a graph does not, which is
    the whole reason this view exists. Layout is the client's problem.

    `root` scopes it to one problem's subtree, exactly as `root_id` does for
    `chart.outline` — so a project draws its own graph from the problem its repo
    attacks. It takes a problem id or a project id, the same as every other `ref`
    on this API.

    Edges are filtered to pairs where BOTH ends are in scope. A descendant that
    also serves a bearing outside the subtree keeps that edge in the unscoped
    graph and loses it here, which is correct: an edge to a node that is not
    drawn is a line to nowhere.
    """
    con = db()
    try:
        if root is not None:
            node = chart.resolve(con, root)
            if not node:
                raise HTTPException(404, f"nothing charted for '{root}'")
            problems = [node] + chart.descendants(con, node["id"])
        else:
            problems = chart.all_problems(con)
        ids = {p["id"] for p in problems}
        # Computed over the WHOLE chart, then read per node: a scoped graph must not
        # report a problem as open just because the subproblem blocking it was left
        # outside the requested subtree.
        standing = chart.standings(con)
        nodes = []
        for p in problems:
            nodes.append({
                "id": p["id"], "title": p["title"], "waypoint": p["waypoint"],
                "draft": p["draft"], "repo": p.get("repo"), "anchored": p.get("anchored"),
                "sounding": chart.effective_sounding(con, p["id"]),
                "solved": bool(p.get("solved")),
                "standing": standing.get(p["id"], "open"),
                "active": bool(p.get("active")),
            })
        edges = [{"child": r[0], "parent": r[1]} for r in
                 con.execute("SELECT child_id, parent_id FROM problem_edges")
                 if r[0] in ids and r[1] in ids]
    finally:
        con.close()
    return {"nodes": nodes, "edges": edges}


@app.get("/api/drift")
def api_drift():
    """Drift = charted problems serving no bearing, plus projects with no chart at all.

    The second half matters more: a repo that was never charted is the loudest
    possible case of "nothing records why this exists", and it is invisible to a
    query that only looks inside the chart.
    """
    con = db()
    try:
        items = chart.drift(con)
        charted = {p["repo"] for p in chart.all_problems(con) if p.get("repo")}
        uncharted = [
            {"id": None, "title": m.get("name", pid), "repo": pid,
             "waypoint": None, "uncharted": True}
            for pid, m in sorted(scan_manifests().items()) if pid not in charted
        ]
        return {"drift": items + uncharted}
    finally:
        con.close()


# Every problem title this process has seen in its OWN store. It is the whole
# answer to a question the export cannot otherwise settle: a node the file names
# and the store lacks is either something you just deleted or something nobody
# ever seeded here, and those need opposite treatment. If we have held it, losing
# it is your edit; if we have never held it, losing it is the bug that ate 14
# nodes. Grows only — a title never leaves once seen, which is what makes the
# delete-then-export sequence work.
_SEEN_TITLES: set[str] | None = None


def _remember_titles(con) -> None:
    global _SEEN_TITLES
    try:
        titles = {p["title"] for p in chart.all_problems(con)}
    except sqlite3.Error as e:            # a broken read must not break the write
        log.warning("could not read chart titles: %s", e)
        return
    _SEEN_TITLES = titles if _SEEN_TITLES is None else _SEEN_TITLES | titles


def _boot_export_guard() -> None:
    """Snapshot the store before anything can edit it.

    It has to happen at boot rather than lazily: if the first chart action of the
    process is a delete, a snapshot taken afterwards would not contain the deleted
    node, and the export would defend a title the user had just removed on purpose
    — and keep defending it for the life of the process.
    """
    try:
        con = db()
    except sqlite3.Error as e:
        log.warning("chart export guard disabled — cannot open the store: %s", e)
        return
    try:
        _remember_titles(con)
    finally:
        con.close()
    try:
        unseeded = chart.exported_titles(CHART_EXPORT.read_text()) - (_SEEN_TITLES or set())
    except OSError:
        return
    if unseeded:
        log.warning(
            "%s names %d node(s) this store has never held — %s. They are protected "
            "from export until seeded (make chart-seed); the chart mirror will not "
            "be rewritten while they are missing.",
            CHART_EXPORT, len(unseeded), ", ".join(sorted(unseeded)[:5]))


_boot_export_guard()


def _export_chart(con) -> None:
    """Best-effort mirror. A failed export must never fail the write.

    Only the titles this store has never held are protected, so deleting a problem
    through the app still shrinks the file — that removal is the point — while a
    node the seeds put in the file and nobody put in this database cannot be
    erased by an unrelated edit.

    If the boot snapshot never ran we fall back to the old permissive behaviour
    rather than protecting everything: an empty set of seen titles would make the
    guard treat every node in the file as unseeded and refuse every export, which
    turns a data-loss bug into a mirror that silently stops updating.
    """
    try:
        if _SEEN_TITLES is None:
            chart.export(con, CHART_EXPORT, allow_removals=True)
        else:
            try:
                unseeded = chart.exported_titles(CHART_EXPORT.read_text()) - _SEEN_TITLES
            except OSError:
                unseeded = set()
            chart.export(con, CHART_EXPORT, protected=unseeded)
    except (OSError, chart.ChartError) as e:
        log.warning("chart export skipped: %s", e)
        return
    # Only after a successful write: a node created in this session becomes
    # deletable in this session, without the guard mistaking it for unseeded.
    _remember_titles(con)
    # Every chart write funnels through this mirror, and the mirror lands in
    # this repo's own tree — one line here keeps shipyard's own card honest
    # about its dirty count instead of one line in a dozen routes.
    _facts_cache.forget_under(CHART_EXPORT)


@app.post("/api/problems")
def api_create_problem(body: ProblemIn):
    con = db()
    try:
        pid = chart.create_problem(con, **body.model_dump())
        ledger.record(con, 'problem', pid, body.title[:120], pid=pid)
        con.commit()
        _export_chart(con)
        return {"id": pid, "chart": chart.spine(con, pid)}
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


class ProblemPatch(BaseModel):
    title: str | None = None
    waypoint: str | None = None
    sounding: str | None = None
    falsifier: str | None = None
    reasoning: str | None = None
    description: str | None = None
    notes: str | None = None


class ArgumentIn(BaseModel):
    body: str
    mtime: float | None = None


def _argument_payload(problem: dict) -> dict:
    """The essay for a problem, plus how it squares with the chart.

    A verdict that disagrees with the sounding is reported, never applied — changing
    a grade because prose changed would be exactly the invisible mutation this app
    exists to prevent.
    """
    doc = args_mod.read(ARGUMENTS_DIR, problem)
    if not doc:
        return {"exists": False, "sounding": problem["sounding"]}
    return {
        "exists": True, "name": doc["name"], "body": doc["body"], "mtime": doc["mtime"],
        "verdict": doc["verdict"], "sounding": problem["sounding"],
        "mismatch": bool(doc["verdict"] and doc["verdict"] != problem["sounding"]),
        "editor_url": args_mod.editor_link(EDITOR_URI, Path(doc["path"])),
        # The essay is where reasoning is worked out; the rail is where it has to be
        # recallable without rereading 1,500 words.
        **args_mod.summarise(doc["body"]),
    }


@app.get("/api/problems/{pid}/argument")
def api_get_argument(pid: str):
    con = db()
    try:
        problem = chart.get(con, pid)
    finally:
        con.close()
    if not problem:
        raise HTTPException(404, f"no problem '{pid}'")
    return _argument_payload(problem)


@app.post("/api/problems/{pid}/argument")
def api_create_argument(pid: str):
    """Scaffold an essay whose thesis is the waypoint. Create-only."""
    con = db()
    try:
        problem = chart.get(con, pid)
    finally:
        con.close()
    if not problem:
        raise HTTPException(404, f"no problem '{pid}'")
    try:
        args_mod.create(ARGUMENTS_DIR, problem)
    except args_mod.ArgumentError as e:
        raise HTTPException(422, str(e))
    # Arguments default to this repo's own docs/arguments/ — the scaffold just
    # dirtied whichever fleet repo contains that directory.
    _facts_cache.forget_under(ARGUMENTS_DIR)
    return _argument_payload(problem)


@app.put("/api/problems/{pid}/argument")
def api_write_argument(pid: str, body: ArgumentIn):
    con = db()
    try:
        problem = chart.get(con, pid)
    finally:
        con.close()
    if not problem:
        raise HTTPException(404, f"no problem '{pid}'")
    try:
        args_mod.write(ARGUMENTS_DIR, problem, body.body, body.mtime)
    except args_mod.ArgumentError as e:
        raise HTTPException(409, str(e))
    _facts_cache.forget_under(ARGUMENTS_DIR)
    return _argument_payload(problem)


class AnchorIn(BaseModel):
    basis: str
    falsifier: str | None = None
    when: str | None = None


@app.patch("/api/problems/{pid}")
def api_update_problem(pid: str, body: ProblemPatch):
    con = db()
    try:
        chart.update_problem(con, pid, **body.model_dump())
        ledger.record(con, 'problem', pid, "edit", pid=pid)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


def _build_state(problem: dict, manifests: dict | None = None) -> dict:
    """Build, derived from the repo rather than clicked (goal-prompt D2).

    The protocol says the tag is the transaction commit, so "building" is exactly
    "there is work since the last cut version" — commits past the tag, or a dirty
    tree.

    `known` is the load-bearing field. A problem with no repo, or a repo with no
    git, is not *un*built — git was never asked. Collapsing that into ticked=False
    would make "we didn't ask" indistinguishable from "not done", which is the
    failure this cycle's guardrail names. The UI must render the two differently.
    """
    repo = problem.get("repo")
    if not repo:
        return {"known": False, "ticked": False, "why": "no repo linked"}
    manifests = manifests if manifests is not None else scan_manifests()
    m = manifests.get(repo)
    if not m:
        return {"known": False, "ticked": False, "why": f"no PROJECT.yaml for {repo!r}"}
    v = repo_mod.version(Path(m["path"]))
    if not v:
        return {"known": False, "ticked": False, "why": f"{repo} is not a git repo"}

    ahead, dirty, tag = v.get("ahead") or 0, v.get("dirty") or 0, v.get("tag")
    ticked = bool(ahead or dirty)
    if ahead and dirty:
        why = f"{ahead} commit{'s' if ahead != 1 else ''} since {tag}, {dirty} uncommitted"
    elif ahead:
        why = f"{ahead} commit{'s' if ahead != 1 else ''} since {tag}"
    elif dirty:
        why = f"{dirty} uncommitted change{'s' if dirty != 1 else ''}"
    else:
        why = f"nothing since {tag}" if tag else "no commits yet"
    return {"known": True, "ticked": ticked, "repo": repo, "tag": tag,
            "commits": ahead, "dirty": dirty, "why": why}


# ---------- the loop, per problem (v0.20.0) ----------

class PhasesIn(BaseModel):
    """Only the manual phases. `build` is derived from commits and is not accepted —
    the chart layer rejects it rather than silently dropping it, because a dropped
    tick would look like the derived value disagreeing with the click."""
    model_config = ConfigDict(extra="forbid")   # a dropped `build` would return 200 and lie
    plan: bool | None = None
    test: bool | None = None
    review: bool | None = None


def _review_gate_reason(con: sqlite3.Connection, pid: str) -> str | None:
    """D4 — the gate gets teeth: review cannot be ticked while the repo owes
    uncommitted or unpushed work.

    Enforced here at the API boundary, the same place the chart already refuses
    a waypointless problem and for the same reason: a refusal a UI can skip is
    a suggestion. Composed in main.py because it takes two domains — the chart
    names the repos, git names the debt — and no domain module may import the
    other.

    Deliberately narrow, per the plan's wording: only `review`, and only the
    two kinds of owed that mean work would be *lost* — uncommitted and
    unpushed. `no-remote`, `untagged` and the rest stay yard-visible debts,
    not line-stopping ones; and unticking is always allowed, because backing a
    mark out is not passing the gate.

    Git is read fresh rather than through the facts cache: a gate serving a
    five-second-old answer would refuse a repo you just cleaned, and worse,
    pass one you just dirtied. One repo, a handful of subprocesses, on a write
    route — exactness is worth it here.
    """
    manifests = scan_manifests()
    for repo in chart.nearest_repos(con, pid):
        m = manifests.get(repo)
        if not m:
            continue          # a repo gone from disk cannot be measured, or refused
        v = repo_mod.version(Path(m["path"]))
        if not v:
            continue
        debts = []
        if v.get("dirty"):
            debts.append(f"{v['dirty']} uncommitted")
        if v.get("unpushed"):
            debts.append(f"{v['unpushed']} unpushed")
        if debts:
            return f"review refused: {repo} owes {', '.join(debts)}"
    return None


def _review_gate(con: sqlite3.Connection, pid: str) -> None:
    """Raise what `_review_gate_reason` computes. The reason exists on its own so
    `/api/direction` can say what WOULD be refused without refusing (2026-09-04)."""
    reason = _review_gate_reason(con, pid)
    if reason:
        raise HTTPException(422, reason)


def _open_gate_reason(con: sqlite3.Connection, pid: str, repo: str, *, as_leaf: bool = False) -> str | None:
    """The other gate: a cycle cannot OPEN on work nothing directs.

    `_review_gate` guards the end of a cycle and refuses the two debts that mean
    work would be *lost*. This guards the start, and refuses the two conditions
    that mean the work has no direction: a problem with no observable, and a
    repo already running a cycle nobody closed.

    Same boundary and the same reason: a refusal a UI can skip is a suggestion.
    Composed in main.py because it needs two domains — the chart names the
    problem and its role, git and the records directory name what is in flight —
    and no domain module may import another.

    **The third refusal the plan asked for is an invariant, not a branch.** A
    repo the chart does not claim cannot reach here: `chart.nearest_repos()`
    derives the candidates *from chart nodes*, and `body.repo` must be one of
    them. `test_every_offered_repo_is_charted` asserts that at its source, which
    is the only place it can actually be observed.

    Git is read fresh rather than through `_facts_cache`, exactly as
    `_review_gate` argues: a five-second-old answer would refuse a repo you just
    closed out, and worse, admit one you just opened.
    """
    problem = chart.get(con, pid)
    if problem and problem.get("draft"):
        return (f"open refused: '{problem['title']}' has no waypoint. A problem with "
                "no observable is a category, and a cycle cannot attack one — give it "
                "a waypoint first")

    # Only cycles that compose nothing contend for the one-open slot. A cycle with
    # problems beneath it is *meant* to stay open while theirs run; counting it
    # would deadlock every child, which is the composition read backwards.
    #
    # The test is "has children", not `role() != "leaf"`. `role` calls a parentless
    # node a bearing whether or not anything hangs off it, so keying on it would
    # exempt every top-level problem — including a lone one that composes nothing
    # and is exactly the single unit of work this gate is for.
    # `as_leaf` (v0.36.1) is direction's view: it resolves a repo to its OWNING problem,
    # which for every board repo composes and so would always pass here — while the
    # leaf an agent actually opens on would be refused by the in-flight check below.
    # Direction asks the question the leaf will be asked.
    if chart.children(con, pid) and not as_leaf:
        return None

    m = scan_manifests().get(repo)
    if not m:
        return None           # a repo gone from disk cannot be measured, or refused
    # `planned`, deliberately, and not `open`. `cycles()` reports both, and they
    # mean different things: `open` is commits since the last tag, which is the
    # normal state of every repo between releases and would refuse nearly all of
    # them. `planned` is a cycle *record* whose version no tag has cut — the exact
    # state this gate exists to catch, and the one v0.29.0 closed two of at once.
    state = repo_mod.cycles(Path(m["path"]), _records_dir(m))
    # A composing cycle's own record sits in the same repo its children cut in, so
    # filtering only the *caller* is not enough: without this, opening the branch
    # cycle first would block every leaf beneath it — the deadlock from the other
    # side. A planned version claimed by a problem with children is that problem's
    # umbrella and does not contend. An unclaimed record does contend: nothing on
    # the chart accounts for it, which is the stray-open-cycle case exactly.
    composing = {v for owner, versions in chart.all_addressed(con).items()
                 if chart.children(con, owner) for v in versions}
    in_flight = [r for r in (state.get("planned") or [])
                 if r["version"] not in composing]
    if in_flight:
        names = ", ".join(f"v{r['version']}" for r in in_flight)
        return (f"open refused: {repo} already has a cycle open ({names}). A record "
                "with no tag is open — close it by cutting its version, or abort it "
                "to the backlog and delete the record")
    return None


def _open_gate(con: sqlite3.Connection, pid: str, repo: str) -> None:
    reason = _open_gate_reason(con, pid, repo)
    if reason:
        raise HTTPException(422, reason)


@app.patch("/api/problems/{pid}/phases")
def api_set_phases(pid: str, body: PhasesIn):
    marks = {k: v for k, v in body.model_dump().items() if v is not None}
    con = db()
    try:
        if marks.get("review"):
            _review_gate(con, pid)
        row = chart.set_phases(con, pid, **marks)
        ledger.record(con, 'phase', pid, ", ".join(k for k, v in marks.items() if v) or "untick", pid=pid)
        con.commit()
        _export_chart(con)
        return row
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


class SolvedIn(BaseModel):
    solved: bool


@app.patch("/api/problems/{pid}/solved")
def api_set_solved(pid: str, body: SolvedIn):
    con = db()
    try:
        row = chart.set_solved(con, pid, body.solved)
        con.commit()
        _export_chart(con)
        return row
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


class ActiveIn(BaseModel):
    active: bool


@app.get("/api/focus")
def api_focus():
    """The focus slots — one per pinned domain, and what is running in each."""
    con = db()
    try:
        return {"slots": chart.focus_slots(con)}
    finally:
        con.close()


class SessionStart(BaseModel):
    id: str
    tool: str = "claude-code"
    cwd: str | None = None
    repo: str | None = None


class SessionEnd(BaseModel):
    reason: str | None = None
    summary: str | None = None


class SessionEvent(BaseModel):
    kind: str
    ref: str | None = None
    detail: str | None = None
    cwd: str | None = None
    repo: str | None = None


@app.post("/api/sessions")
def api_session_start(body: SessionStart):
    """A session opened (Claude Code's SessionStart hook). Upsert by id."""
    con = db()
    try:
        out = ledger.start(con, body.id, tool=body.tool, cwd=body.cwd, repo=body.repo)
        con.commit()
        return out
    finally:
        con.close()


@app.patch("/api/sessions/{sid}")
def api_session_end(sid: str, body: SessionEnd):
    """A session closed (SessionEnd hook): the reason, and a summary if any."""
    con = db()
    try:
        out = ledger.end(con, sid, reason=body.reason, summary=body.summary)
        con.commit()
        return out
    finally:
        con.close()


@app.post("/api/sessions/{sid}/events")
def api_session_event(sid: str, body: SessionEvent):
    """Something the session did outside the chart — a commit, a tag, a push —
    posted by the PostToolUse hook. Chart writes record themselves."""
    con = db()
    try:
        out = ledger.event(con, sid, body.kind, body.ref, body.detail, cwd=body.cwd, repo=body.repo)
        con.commit()
        return out
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/api/sessions")
def api_sessions(repo: str | None = None, since: str | None = None, limit: int = 50):
    """Sessions newest first, each with its events. `repo` and `since` (ISO) filter."""
    con = db()
    try:
        return {"sessions": ledger.listing(con, repo=repo, since=since, limit=limit)}
    finally:
        con.close()


@app.get("/api/sessions/{sid}")
def api_session(sid: str):
    con = db()
    try:
        out = ledger.get(con, sid)
        if not out:
            raise HTTPException(404, f"no session {sid}")
        return out
    finally:
        con.close()


@app.get("/api/direction")
def api_direction(repo: str):
    """What this repo is directed to do — and what would be refused if it tried.

    The agent-facing question before any work: which problem claims the repo, which
    bearing that hangs from, whether it is the bearing's active problem, whether a
    cycle is already open, and what each gate would say. Composed here because it
    joins three domains — the chart names the problem, git and the records dir name
    what is in flight, the manifest names the repo — and no domain module imports
    another. Reads the same `_open_gate_reason` / `_review_gate_reason` the write
    routes raise, so "would be refused" and "was refused" cannot drift apart.

    `next` is one sentence a session can act on. "clear" means: open a cycle.
    Unknown repo → 404 naming the manifest ids, so a typo cannot read as "uncharted".
    """
    manifests = scan_manifests()
    if repo not in manifests:
        raise HTTPException(404, f"no PROJECT.yaml is known as '{repo}'. Known: "
                                 f"{', '.join(sorted(manifests))}")
    m = manifests[repo]
    con = db()
    try:
        problem = chart.resolve(con, repo)
        state = repo_mod.cycles(Path(m["path"]), _records_dir(m))
        planned = state.get("planned") or []
        open_cycle = ({"version": planned[0]["version"], "record": planned[0].get("name")}
                      if planned else None)
        if not problem:
            return {
                "repo": repo, "problem": None, "bearing": None,
                "active": {"is_active": False, "occupant": None},
                "open_cycle": open_cycle,
                "gates": {"open": {"ok": False, "reason": "uncharted: no problem claims this repo"},
                          "review": {"ok": False, "reason": "uncharted: no problem claims this repo"}},
                "would_refuse": ["open: uncharted — no problem claims this repo"],
                "next": "chart it: create a problem with a waypoint and PUT /api/problems/{pid}/repo",
            }
        pid = problem["id"]
        pin_id = chart.nearest_pinned(con, pid)
        bearing = None
        occupant = None
        if pin_id:
            pin = chart.get(con, pin_id)
            bearing = {"id": pin_id, "title": pin["title"]} if pin else None
            for slot in chart.focus_slots(con):
                if slot["domain_id"] == pin_id and slot.get("problem"):
                    occupant = {"id": slot["problem"]["id"], "title": slot["problem"]["title"]}
        is_active = bool(problem.get("active"))
        open_reason = _open_gate_reason(con, pid, repo, as_leaf=True)
        review_reason = _review_gate_reason(con, pid)
        # `would_refuse` names only the NEXT step's gate (v0.36.0). With no cycle open the
        # next step is *open*; with one open it is *review*. Both gates stay under `gates`.
        # The fleet bench (fleet v0.4.0) showed why: a repo mid-work always "owes" something,
        # and an agent about to open a cycle stopped because *closing* would have been refused.
        would = []
        if open_cycle:
            if review_reason:
                would.append(f"review: {review_reason}")
        elif open_reason:
            would.append(f"open: {open_reason}")
        if open_cycle:
            nxt = (f"cycle v{open_cycle['version']} is open on {repo} — cut its tag (and tick review) "
                   f"or abort it to the backlog and delete the record")
            if review_reason:
                nxt += f"; review would be refused today: {review_reason}"
        elif problem.get("draft"):
            nxt = f"'{problem['title']}' has no waypoint — give it an observable before any cycle"
        elif bearing and not occupant:
            nxt = (f"no active problem under '{bearing['title']}' — the human picks one with "
                   f"PATCH /api/problems/{{pid}}/active")
        elif bearing and occupant and occupant["id"] != pid and not is_active:
            nxt = (f"'{occupant['title']}' holds the focus under '{bearing['title']}'; "
                   f"'{problem['title']}' is not the active problem — check with the human before opening")
        else:
            nxt = "clear"      # owed work only matters at review; it is under gates.review
        return {
            "repo": repo,
            "problem": {"id": pid, "title": problem["title"], "waypoint": problem.get("waypoint"),
                        "sounding": problem.get("sounding"), "anchored": bool(problem.get("anchored_at")),
                        "role": chart.role(con, pid)},
            "bearing": bearing,
            "active": {"is_active": is_active, "occupant": occupant},
            "open_cycle": open_cycle,
            "gates": {"open": {"ok": open_reason is None, "reason": open_reason},
                      "review": {"ok": review_reason is None, "reason": review_reason}},
            "would_refuse": would,
            "next": nxt,
        }
    finally:
        con.close()


@app.patch("/api/problems/{pid}/active")
def api_set_active(pid: str, body: ActiveIn):
    """Take or release a focus slot. Refuses a blocked problem, and refuses a second
    one in a domain that already has one — naming the occupant so the message is
    something you can act on rather than a rule you have to remember."""
    con = db()
    try:
        row = chart.set_active(con, pid, body.active)
        con.commit()
        return row
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


class ApproachIn(BaseModel):
    name: str
    rationale: str | None = None


class ApproachPatch(BaseModel):
    """`verdict` uses a sentinel rather than None-means-absent: clearing a verdict
    back to "untested" is a real edit, and None is the value that expresses it."""
    name: str | None = None
    rationale: str | None = None
    chosen: bool | None = None
    verdict: str | None = None
    set_verdict: bool = False


@app.post("/api/problems/{pid}/approaches")
def api_add_approach(pid: str, body: ApproachIn):
    con = db()
    try:
        chart.add_approach(con, pid, name=body.name, rationale=body.rationale)
        con.commit()
        return {"approaches": chart.approaches(con, pid)}
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.patch("/api/approaches/{aid}")
def api_update_approach(aid: str, body: ApproachPatch):
    con = db()
    try:
        rows = chart.update_approach(
            con, aid,
            name=body.name, rationale=body.rationale, chosen=body.chosen,
            verdict=body.verdict if body.set_verdict else ...,
        )
        con.commit()
        return {"approaches": rows}
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.delete("/api/approaches/{aid}")
def api_delete_approach(aid: str):
    con = db()
    try:
        rows = chart.delete_approach(con, aid)
        con.commit()
        return {"approaches": rows}
    except chart.ChartError as e:
        raise HTTPException(404, str(e))
    finally:
        con.close()


class DuplicateIn(BaseModel):
    parent_id: str | None = None


@app.post("/api/problems/{pid}/duplicate")
def api_duplicate(pid: str, body: DuplicateIn):
    """Copy a subtree as independent nodes — the opposite of sharing it."""
    con = db()
    try:
        new_id = chart.duplicate_subtree(con, pid, body.parent_id)
        con.commit()
        _export_chart(con)
        return {"id": new_id, "chart": chart.spine(con, new_id)}
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/api/problems/{pid}/deletion")
def api_deletion_impact(pid: str):
    """What deleting would do. Read before the button, never after — and since
    v0.35.0, the button needs the `token` this returns (tokens.py)."""
    con = db()
    try:
        impact = chart.deletion_impact(con, pid)
        return {**impact, "token": tokens.issue("delete", pid, impact)}
    except chart.ChartError as e:
        raise HTTPException(404, str(e))
    finally:
        con.close()


@app.delete("/api/problems/{pid}")
def api_delete_problem(pid: str, cascade: bool = False, token: str | None = None):
    """Delete one problem, or the whole branch it holds up.

    Without cascade, children are promoted; with it, everything whose only route to
    a bearing ran through this problem goes too. Anything with another parent is
    spared either way. Refused without the token `GET …/deletion` issued for the
    impact as it stands now — a deletion that did not read its consequences is
    the failure this gate exists to make impossible (2026-09-04).
    """
    con = db()
    try:
        current = chart.deletion_impact(con, pid)
        reason = tokens.check("delete", pid, token, current, f"GET /api/problems/{pid}/deletion")
        if reason:
            raise HTTPException(422, reason)
        result = (chart.delete_subtree(con, pid) if cascade
                  else chart.delete_problem(con, pid))
        con.commit()
        _export_chart(con)
        return result
    except chart.ChartError as e:
        raise HTTPException(404, str(e))
    finally:
        con.close()


@app.get("/api/problems/{pid}/impact")
def api_impact(pid: str):
    """What rests on this — read before thawing, never after; thaw needs the `token`."""
    con = db()
    try:
        impact = chart.impact(con, pid)
        return {**impact, "token": tokens.issue("thaw", pid, impact)}
    except chart.ChartError as e:
        raise HTTPException(404, str(e))
    finally:
        con.close()


@app.post("/api/problems/{pid}/anchor")
def api_freeze(pid: str, body: AnchorIn):
    con = db()
    try:
        chart.freeze(con, pid, basis=body.basis, falsifier=body.falsifier, when=body.when)
        ledger.record(con, 'anchor', pid, body.basis[:200], pid=pid)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.delete("/api/problems/{pid}/anchor")
def api_thaw(pid: str, token: str | None = None):
    """Lift an anchor. Refused without the token `GET …/impact` issued — everything
    that rests on the anchor is back in question, and the read is what you agree to."""
    con = db()
    try:
        reason = tokens.check("thaw", pid, token, chart.impact(con, pid), f"GET /api/problems/{pid}/impact")
        if reason:
            raise HTTPException(422, reason)
        chart.thaw(con, pid)
        ledger.record(con, 'thaw', pid, None, pid=pid)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(404, str(e))
    finally:
        con.close()


@app.delete("/api/problems/{pid}/parents/{parent_id}")
def api_remove_parent(pid: str, parent_id: str):
    """Detach one bearing while keeping the others."""
    con = db()
    try:
        chart.remove_parent(con, child_id=pid, parent_id=parent_id)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.post("/api/problems/{pid}/parents")
def api_attach_parent(pid: str, body: EdgeIn):
    """Attach an existing bearing — how a project gains a second parent."""
    con = db()
    try:
        chart.add_edge(con, child_id=pid, parent_id=body.parent_id)
        con.commit()
        _export_chart(con)
        return chart.spine(con, pid)
    except chart.ChartError as e:
        raise HTTPException(422, str(e))
    finally:
        con.close()


@app.get("/health")
def health():
    checks = {}
    try:
        con = db(); con.execute("SELECT 1"); con.close()
        checks["db"] = True
    except Exception:
        checks["db"] = False
    checks["code_root"] = CODE_ROOT.is_dir()
    checks["mc"] = mc_alive()  # informational: shipyard works without MC
    ok = checks["db"] and checks["code_root"]
    # A dict, per the fleet convention — MC drops any other shape on the floor,
    # which is why the old serve-time string never showed up anywhere. Stamps
    # are when each cached read last actually ran, not when this response went
    # out: a request answered wholly from cache moves neither.
    return {"ok": ok, "checks": checks,
            "freshness": {k: v for k, v in (("scan", _scan_cache.stamp),
                                            ("git", _facts_cache.stamp))
                          if v is not None}}


# ---------- static frontend (built by `make prod`) ----------

DIST = ROOT / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    # HEAD as well as GET. A GET-only root answers a HEAD probe with 405, which is
    # what uptime monitors and reverse proxies send — and it also makes `curl -I`
    # report the 405's headers rather than the page's, so hand-checking the caching
    # of this very route silently reads the wrong response.
    @app.api_route("/", methods=["GET", "HEAD"])
    def index():
        # Everything under /assets is content-hashed and safe to cache forever, but
        # index.html is what points at those hashes. It carries an ETag and a
        # Last-Modified, so a browser will revalidate if asked to — without a
        # Cache-Control it is free not to ask, and heuristic freshness off the
        # Last-Modified can pin the page to a bundle we no longer build.
        return FileResponse(DIST / "index.html",
                            headers={"Cache-Control": "no-cache, must-revalidate"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("SHIPYARD_HOST", "127.0.0.1"),
                port=int(os.environ.get("SHIPYARD_PORT", 8845)))
