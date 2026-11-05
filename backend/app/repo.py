"""What a repo already says about itself — version, documents, decisions.

Nothing here is a shipyard convention. Every value is read back out of things the
repo keeps anyway: git tags, the working tree, `README.md`, `ARCHITECTURE.md`,
`CHANGELOG.md`, `docs/adr/`. A project that never opens shipyard still answers all
of these, which is the point — shipyard reads the tools that hold the truth.

The one derived value is `running_behind`, and it is derived rather than declared
on purpose. Asking every app to report its own version would be a new convention
for seven repos to implement and drift out of. Comparing the newest commit against
how long the process has been up needs nothing from the app at all.
"""

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Read-only, and small: a document rail is for orienting, not for serving a wiki.
MAX_DOC_BYTES = 400_000
READABLE_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".yaml", ".yml", ".toml",
                     # Source too, so a flow step's code reference can be followed.
                     # Deliberately a list rather than "anything not secret": .env,
                     # keys and dumps stay unreadable by not being on it.
                     ".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".sh", ".css"}

# Ordered: this is the order they appear in the rail, most-orienting first.
# A charter leads because it is the one that says what the project has *ruled out* —
# the rest describe what it is.
KNOWN_DOCS = [
    ("charter", "docs/CHARTER.md"),
    ("charter", "CHARTER.md"),
    ("architecture", "ARCHITECTURE.md"),
    ("changelog", "CHANGELOG.md"),
    ("readme", "README.md"),
]
ADR_DIRS = ("docs/adr", "docs/decisions", "adr")


class RepoError(RuntimeError):
    """A read was refused, always for a stated reason."""


def _git(path: Path, *argv: str) -> str | None:
    """A git read. None means the command failed — which is information, not an
    error: `log @{u}..HEAD` failing is how we learn there is no upstream."""
    try:
        out = subprocess.run(["git", "-C", str(path), *argv],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def version(path: Path) -> dict | None:
    """Released tag, work since it, and whether the tree and remote agree.

    One number would be a lie of omission: a repo sitting 13 commits past its last
    tag is not "v0.14.0", it is v0.14.0 plus thirteen commits nobody has named.
    """
    path = Path(path)
    if not (path / ".git").exists():
        return None

    tag = _git(path, "describe", "--tags", "--abbrev=0")
    ahead = None
    if tag:
        count = _git(path, "rev-list", f"{tag}..HEAD", "--count")
        ahead = int(count) if count and count.isdigit() else None

    # `-uall` because git collapses an untracked *directory* to a single porcelain
    # line. manalab reported "13 uncommitted" against 71 real files — the count was
    # of directories, and every never-committed repo reads that way, which is
    # exactly when the number matters most.
    status = _git(path, "status", "--porcelain", "-uall")
    dirty = len([ln for ln in (status or "").splitlines() if ln.strip()])

    # No upstream is a distinct state from "nothing to push", and worth seeing:
    # it is what blocks a repo from being demonstrable to anyone else.
    unpushed, has_remote = None, True
    ahead_of_remote = _git(path, "log", "@{u}..HEAD", "--oneline")
    if ahead_of_remote is None:
        has_remote = False
    else:
        unpushed = len([ln for ln in ahead_of_remote.splitlines() if ln.strip()])

    return {"tag": tag or None, "ahead": ahead, "dirty": dirty,
            "unpushed": unpushed, "has_remote": has_remote,
            "branch": _git(path, "rev-parse", "--abbrev-ref", "HEAD")}


def running_behind(last_commit: str | None, uptime_s: float | None) -> bool | None:
    """Is the running process older than the newest commit?

    None when it cannot be known (no commit, or nothing running). Deliberately a
    comparison of two facts already on hand rather than a version handshake: on
    2026-08-07 shipyard served an hour of stale code while the fix sat committed
    and green, and nothing on the page could have said so.
    """
    if not last_commit or not uptime_s:
        return None
    try:
        committed = datetime.fromisoformat(last_commit)
    except ValueError:
        return None
    if committed.tzinfo is None:
        committed = committed.replace(tzinfo=timezone.utc)
    started = datetime.now(timezone.utc).timestamp() - float(uptime_s)
    return committed.timestamp() > started


CHANGELOG_NAMES = ("CHANGELOG.md", "CHANGELOG.markdown", "CHANGELOG")
# Only commits that change what the software does belong in a changelog. Without
# this filter the check fires on `chore: sync MAP.md file index [skip ci]`, and a
# flag that cries wolf gets ignored — which is the failure it exists to prevent.
_NOTABLE = re.compile(r"^(feat|fix|perf|refactor)(\([^)]*\))?!?:\s*(.+)$", re.I)
_VERSION_HEADING = re.compile(r"^##\s*\[?v?(\d+\.\d+\.\d+)\]?", re.M)
_UNRELEASED_HEADING = re.compile(r"^##\s*\[?unreleased\]?", re.I | re.M)


def changelog(path: Path, tag: str | None) -> dict | None:
    """Has anything landed since the last release that nobody wrote down?

    An audit surface, not a history: the point is to read one curated summary
    instead of every commit. So the question is not "what changed" — git answers
    that better — but "is the summary keeping up with the code".
    """
    path = Path(path)
    if not (path / ".git").exists():
        return None

    found = next((path / n for n in CHANGELOG_NAMES if (path / n).is_file()), None)
    body = ""
    if found:
        try:
            body = found.read_text(errors="replace")
        except OSError:
            found = None

    unreleased = _unreleased_entries(body)
    documented = _VERSION_HEADING.search(body)
    latest_documented = documented.group(1) if documented else None

    # Anchor to when the summary was last written, not to the last release.
    # Anchoring on the tag broke on the first repo it met that documents a version
    # without tagging it: csv-profiler wrote `## [0.1.0]` covering nine features
    # already committed, and with no tag to bound the window its whole history read
    # as unlogged. The changelog's own last commit answers the question being asked
    # — has the summary kept up with the code — in both directions: a release tagged
    # without an entry still drifts, and an entry written after the fact still
    # clears. It is fooled by an unrelated edit to the file, which is the price of
    # not trying to match entries to commits.
    anchor = _git(path, "log", "-1", "--format=%H", "--", found.name) if found else None
    span = f"{anchor or tag}..HEAD" if (anchor or tag) else "HEAD"
    log = _git(path, "log", span, "--format=%h\x1f%s") or ""
    unlogged = []
    for line in log.splitlines():
        sha, _, subject = line.partition("\x1f")
        m = _NOTABLE.match(subject.strip())
        if m:
            unlogged.append({"sha": sha, "subject": subject.strip()})

    # Entries under Unreleased mean somebody is keeping up; we deliberately do not
    # try to match entry-to-commit, which would be guesswork dressed as precision.
    drift = bool(unlogged) and unreleased == 0
    behind = bool(tag and latest_documented
                  and latest_documented != tag.lstrip("v"))

    return {"path": found.name if found else None,
            "latest_documented": latest_documented,
            "unreleased_entries": unreleased,
            "unlogged": unlogged,
            "drift": drift,
            "release_behind": behind}


# Kinds of owed, ordered by what you lose if the disk dies tonight — uncommitted
# work is gone, unpushed work is gone, and everything below is merely undescribed.
# This is a fixed editorial order over *kinds*, deliberately not a score over
# projects: Road to 1.0 prunes "anything that computes a score for a project", and
# a score would answer "which repo is worst" when the real question is "what do I
# owe". A project appears under every kind it satisfies.
OWED_KINDS = [
    ("uncommitted", "not in git at all — lost if the disk dies"),
    ("unpushed", "committed, but exists only on this machine"),
    ("no-remote", "no upstream — nothing here can be shown to anyone else"),
    ("untagged", "commits past the last tag, with no version cut"),
    ("unlogged", "behaviour changed, with nothing written down"),
    ("uncharted", "nothing records why this exists"),
    ("running-old-code", "the deployed process is older than the newest commit"),
]


def owed(version: dict | None, changelog: dict | None,
         behind: bool | None, charted: bool,
         chart_expected: bool = True) -> list[dict]:
    """Which kinds of owed a project is in, and by how much.

    Pure: it reads already-computed values rather than the disk, so this module
    stays ignorant of charts and manifests and the caller keeps the fan-out.
    `n` is a magnitude for sorting within a kind, never across kinds — thirteen
    uncommitted files and thirteen unlogged commits are not the same debt.

    `chart_expected=False` means the manifest declared `chart: none` — this repo is
    not goal-bearing, and its description is the whole of why it exists. Without
    that, `uncharted` fires for every repo the chart does not claim, which after the
    2026-08-18 prune is thirteen of them: the chart became a map of goals under four
    life domains rather than a registry of everything on disk, so a tool having no
    node is the correct resting state and reporting it as debt is the stale
    assumption. Declared, never inferred — silence still reads as owed, exactly like
    `release: scheme: none`, so the exemption has to be claimed and cannot be
    acquired by neglect.
    """
    out = []

    def add(kind: str, n: int | None = None, detail: str | None = None):
        out.append({"kind": kind, "n": n, "detail": detail})

    def plural(n: int, noun: str) -> str:
        return f"{n} {noun}{'' if n == 1 else 's'}"

    if version:
        if version.get("dirty"):
            add("uncommitted", version["dirty"], plural(version["dirty"], "file"))
        if not version.get("has_remote"):
            add("no-remote")
        elif version.get("unpushed"):
            add("unpushed", version["unpushed"], plural(version["unpushed"], "commit"))
        if version.get("ahead"):
            tag = version.get("tag") or "the beginning"
            add("untagged", version["ahead"],
                f"{plural(version['ahead'], 'commit')} since {tag}")

    # Drift already means "notable commits AND nothing under Unreleased", so an
    # unreleased count is somebody keeping up, not a second debt. Only the drift
    # flag is owed; the entries are what clears it.
    if changelog and changelog.get("drift"):
        n = len(changelog.get("unlogged") or [])
        add("unlogged", n, plural(n, "commit"))

    if not charted and chart_expected:
        add("uncharted")

    # None means "cannot tell" — reported as unknown rather than owed, the same
    # honesty `running_behind` already applies for compose apps.
    if behind is True:
        add("running-old-code")

    return out


def _unreleased_entries(body: str) -> int:
    """Bullet count under an `## Unreleased` heading, up to the next `## `."""
    m = _UNRELEASED_HEADING.search(body or "")
    if not m:
        return 0
    rest = body[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    block = rest[:nxt.start()] if nxt else rest
    return len([ln for ln in block.splitlines() if ln.lstrip().startswith(("-", "*"))])


def recent_work(path: Path, tag: str | None, limit: int = 12) -> dict:
    """What has actually happened lately, read from git rather than a task list.

    The work tab used to read a per-repo backlog. One of nineteen repos had one,
    so the tab read zero almost everywhere and would have kept doing so. Git knows what happened without being told.
    """
    path = Path(path)
    if not (path / ".git").exists():
        return {"commits": [], "dirty": [], "span": None}

    span = f"{tag}..HEAD" if tag else "HEAD"
    log = _git(path, "log", span, f"-{limit}", "--format=%h\x1f%cI\x1f%s") or ""
    commits = []
    for line in log.splitlines():
        sha, _, rest = line.partition("\x1f")
        when, _, subject = rest.partition("\x1f")
        commits.append({"sha": sha, "date": when[:10], "subject": subject})

    dirty = []
    for line in (_git(path, "status", "--porcelain", "-uall") or "").splitlines():
        if line.strip():
            dirty.append({"state": line[:2].strip() or "?", "file": line[3:]})

    return {"commits": commits, "dirty": dirty[:40], "span": tag}


# ---------- cycles ----------
#
# Under Development Protocol 1.0 a cycle is atomic: it passes plan-build-test-review
# and cuts a version, or it cuts nothing. "The version bump is the transaction
# commit… the git tags are the only durable record of finished work" — so the tags
# already *are* the history, and this only has to join them to what each one
# produced (the changelog entry) and what was learned (the vault's cycle record).
#
# Nothing here grades or enforces. The protocol is the owner's, and a tool that
# started failing cycles would be inventing authority it was never given.

_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# Written by hand in the vault as `v0.4.0 — Board rework.md`.
_RECORD = re.compile(r"^(v?\d+\.\d+\.\d+)\s*[—–-]\s*(.+)\.md$")


def _semver(tag: str) -> tuple[int, int, int] | None:
    m = _SEMVER.match(tag.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _weight(prev: tuple | None, cur: tuple) -> str:
    """Which unit of the protocol's nesting this version move represents.

    sub-cycle = MINOR, light cycle = PATCH, super-cycle = MAJOR. The number carries
    the meaning, so the weight is read off it rather than recorded anywhere.
    """
    if prev is None:
        return "first"
    if cur[0] != prev[0]:
        return "super"
    if cur[1] != prev[1]:
        return "sub"
    return "light"


def cycle_records(records_dir: Path | None) -> dict[str, dict]:
    """Cycle notes on disk, keyed by version. Absent is a normal answer."""
    if not records_dir:
        return {}
    d = Path(records_dir)
    if not d.is_dir():
        return {}
    out = {}
    for f in sorted(d.glob("*.md")):
        m = _RECORD.match(f.name)
        if m:
            version = m.group(1).lstrip("v")
            out[version] = {"title": m.group(2).strip(), "path": str(f), "name": f.name}
    return out


def next_version(tag: str | None, bump: str, taken=()) -> str:
    """The version a new cycle would cut.

    Proposed, never imposed: the caller can name any version. The proposal exists
    because the bump *is* the claim about scope — a leaf problem cutting a MAJOR is
    a mismatch worth seeing before it becomes a tag nobody can move.

    `taken` is every version already spoken for in this repo's line, cut or merely
    planned. Reading only the latest *tag* proposed a version that an open cycle had
    already claimed, so the second cycle you opened collided with the first — caught
    by the create-only guard, but only after you had typed a name for it.

    Compared as tuples, never as strings: `0.9.0` sorts above `0.10.0` lexically.
    """
    versions = [v for v in (_semver(t) for t in (tag or "v0.0.0", *taken)) if v]
    major, minor, patch = max(versions) if versions else (0, 0, 0)
    if bump == "major":
        return f"v{major + 1}.0.0"
    if bump == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


RECORD_SCAFFOLD = """# {version} — {title}

{weight} plan under [[0.) Development Protocol 1.0]]
Opened {opened}

Addresses **{problem}**
{waypoint_line}

## Problem

_What is actually wrong, and what is at stake in getting it wrong. This is the rung
of the chart being attacked, restated in enough detail to build against._

## Appetite

_How long this is worth. Scope bends, the timebox does not._

## Plan

_What will be built, and deliberately what will not._

**Non-goals.**

## Exit criteria

_What has to be true to cut {version}. The waypoint above is the honest version of
this — everything else is a task list._

## Build

_Filled in as it happens: decisions taken, and why._

## Test

_What was actually run, and what it said._

## Review

_What was learned, including what went wrong. A cycle with no surprises was either
too small or not honestly recorded._
"""


def scaffold_record(records_dir: Path, *, version: str, title: str,
                    problem: str, waypoint: str | None = None,
                    weight: str = "Sub-cycle", opened: str) -> dict:
    """Write a cycle record for a version that has not been cut.

    Create-only, like an argument: a cycle note is prose you wrote, and the one
    unforgivable behaviour for a tool that writes into a vault is clobbering it.
    """
    d = Path(records_dir)
    d.mkdir(parents=True, exist_ok=True)
    v = version if version.startswith("v") else f"v{version}"
    path = d / f"{v} — {title}.md"
    if path.exists():
        raise RepoError(f"{path.name} already exists — open it rather than overwrite it")
    body = RECORD_SCAFFOLD.format(
        version=v, title=title, weight=weight, opened=opened, problem=problem,
        waypoint_line=f"\n> {waypoint}" if waypoint else "")
    path.write_text(body)
    return {"path": str(path), "name": path.name, "version": v.lstrip("v")}


MIRROR_DIR = "docs/cycles"
MIRROR_README = """# Cycle records — mirrored

These are copies. The originals are hand-written in the vault under
`Projects/<Project>/Cycles/`, which is where Development Protocol 1.0 puts them.

They are mirrored here so the record of finished work survives a fresh clone — the
same reason `docs/chart.md` mirrors a chart that lives in gitignored sqlite. Edit
the vault; anything changed here is overwritten on the next mirror.
"""


def mirror_state(records_dir: Path | None, repo_path: Path) -> dict:
    """How the repo's copies compare to the vault's originals.

    Byte equality, deliberately: the copy is written verbatim so "is this current"
    stays a comparison rather than a judgement. Provenance lives in a README beside
    them instead of in a header on each file, which would make every copy differ
    from its source by construction.
    """
    records = cycle_records(records_dir)
    target = Path(repo_path) / MIRROR_DIR
    fresh, stale, missing = [], [], []
    for version, rec in sorted(records.items()):
        copy = target / rec["name"]
        if not copy.is_file():
            missing.append(version)
            continue
        try:
            same = copy.read_bytes() == Path(rec["path"]).read_bytes()
        except OSError:
            same = False
        (fresh if same else stale).append(version)
    return {"dir": MIRROR_DIR, "total": len(records), "fresh": fresh,
            "stale": stale, "missing": missing,
            "behind": len(stale) + len(missing)}


def mirror_records(records_dir: Path | None, repo_path: Path) -> dict:
    """Copy the vault's cycle records into the repo, verbatim.

    One direction only. The vault is the source: a record is a hand-written retro,
    and letting the copy write back would put two editable versions of the same
    thought in play with nothing to say which won.
    """
    records = cycle_records(records_dir)
    if not records:
        raise RepoError("no cycle records to mirror — the vault folder is empty or absent")
    target = Path(repo_path) / MIRROR_DIR
    try:
        target.mkdir(parents=True, exist_ok=True)
        (target / "README.md").write_text(MIRROR_README)
    except OSError as e:
        raise RepoError(f"could not prepare {target}: {e}")

    copied = []
    for version, rec in sorted(records.items()):
        src, dst = Path(rec["path"]), target / rec["name"]
        try:
            data = src.read_bytes()
            if not dst.is_file() or dst.read_bytes() != data:
                dst.write_bytes(data)
                copied.append(version)
        except OSError as e:
            raise RepoError(f"could not mirror {rec['name']}: {e}")
    return {"copied": copied, "total": len(records), "dir": MIRROR_DIR}


def cycles(path: Path, records_dir: Path | None = None, limit: int = 40) -> dict:
    """Every cut version as a cycle, plus whatever is in flight without one.

    The open cycle is reported separately and deliberately not counted: "No version,
    no credit. Abort → backlog + retro, not a partial bump."

    `planned` is the other half of that: a cycle record whose version no tag has cut.
    This list built from tags alone, so a cycle that had been opened but not yet cut
    was invisible here — which is precisely the state the Plan step creates, and the
    one you most need to see while you are in it.
    """
    path = Path(path)
    if not (path / ".git").exists():
        return {"cycles": [], "open": None, "records_dir": None}

    raw = _git(path, "tag", "--sort=creatordate", "--format=%(refname:short)\x1f%(creatordate:short)")
    tagged = []
    for line in (raw or "").splitlines():
        tag, _, when = line.partition("\x1f")
        v = _semver(tag)
        if v:
            tagged.append((tag, v, when))

    documented = set()
    for name in CHANGELOG_NAMES:
        f = path / name
        if f.is_file():
            try:
                documented = set(_VERSION_HEADING.findall(f.read_text(errors="replace")))
            except OSError:
                pass
            break

    records = cycle_records(records_dir)

    out = []
    prev = None
    for tag, v, when in tagged:
        version = ".".join(str(p) for p in v)
        rec = records.get(version)
        out.append({
            "tag": tag, "version": version, "date": when,
            "weight": _weight(prev, v),
            "logged": version in documented,
            "record": rec,
        })
        prev = v
    out.reverse()

    last = tagged[-1][0] if tagged else None
    span = f"{last}..HEAD" if last else "HEAD"
    ahead = [ln for ln in (_git(path, "log", span, "--format=%h") or "").splitlines() if ln]

    # A record with no tag behind it is a cycle in flight. Ordered newest-version
    # first to match `cycles`, so the two lists read the same way.
    cut_versions = {c["version"] for c in out}
    planned = [{"version": v, **rec} for v, rec in records.items() if v not in cut_versions]
    planned.sort(key=lambda r: _semver(r["version"]) or (0, 0, 0), reverse=True)

    return {
        "cycles": out[:limit],
        "planned": planned,
        "open": {"since": last, "commits": len(ahead)} if ahead else None,
        "records_dir": str(records_dir) if records_dir else None,
        "mirror": mirror_state(records_dir, path),
        "counts": {
            "cut": len(tagged),
            "recorded": sum(1 for c in out if c["record"]),
            "logged": sum(1 for c in out if c["logged"]),
        },
    }


def churn(path: Path, days: int = 90) -> list[dict]:
    """Which parts of the tree have actually been moving.

    Counted in *commits* touching a directory, not files changed: one commit that
    rewrites forty files is one act of work, and counting files would let a single
    mass rename outrank three months of steady effort.

    Layout says where the weight sits; this says where the attention went. A large
    directory nobody has touched in a quarter and a small one rewritten last week
    are the two things you most want to tell apart when you come back to a project.
    """
    path = Path(path)
    if not (path / ".git").exists():
        return []
    log = _git(path, "log", f"--since={days} days ago", "--name-only",
               "--format=%x00%h") or ""

    counts: dict[str, int] = {}
    touched: set[str] = set()
    for line in log.split("\n"):
        if line.startswith("\x00"):
            for d in touched:
                counts[d] = counts.get(d, 0) + 1
            touched = set()
            continue
        name = line.strip()
        if name:
            head, _, rest = name.partition("/")
            touched.add(head if rest else "(root)")
    for d in touched:                       # the final commit has no sentinel after it
        counts[d] = counts.get(d, 0) + 1

    return sorted(({"name": k, "commits": v} for k, v in counts.items()),
                  key=lambda c: c["commits"], reverse=True)[:12]


def documents(path: Path, links: dict | None = None) -> list[dict]:
    """The reading material this repo actually has.

    `kind` is what the frontend needs to decide behaviour: `url` opens out to the
    published docs, `file` opens the in-app reader, `dir` is a set of decisions.
    """
    path = Path(path)
    out: list[dict] = []

    links = links or {}
    published = links.get("docs")
    if published:
        out.append({"label": "docs", "kind": "url", "href": str(published)})

    # A manifest that names its own documents is the repo telling you where its
    # truth lives — reading only `docs` threw the rest away. glm-harness declared
    # `charter: docs/CHARTER.md` for weeks and this list showed it a README.
    seen: set[str] = set()
    for label, value in links.items():
        if label in ("docs", "github", "repo", "app") or not isinstance(value, str):
            continue
        if value.startswith(("http://", "https://")):
            out.append({"label": label, "kind": "url", "href": value})
            continue
        if (path / value).is_file():
            out.append({"label": label, "kind": "file", "path": value, "declared": True})
            seen.add(value)

    for label, rel in KNOWN_DOCS:
        if rel not in seen and (path / rel).is_file():
            out.append({"label": label, "kind": "file", "path": rel})
            seen.add(rel)

    adrs = decisions(path)
    if adrs:
        out.append({"label": "decisions", "kind": "dir", "count": len(adrs)})
    return out


def decisions(path: Path) -> list[dict]:
    """ADRs, newest first — the record of what was decided and why."""
    path = Path(path)
    for rel in ADR_DIRS:
        d = path / rel
        if not d.is_dir():
            continue
        found = []
        for f in sorted(d.glob("*.md")):
            if f.name.lower() in {"readme.md", "template.md", "index.md"}:
                continue
            found.append({"name": f.name, "path": f"{rel}/{f.name}",
                          "title": _first_heading(f) or f.stem})
        return list(reversed(found))
    return []


def _first_heading(f: Path) -> str | None:
    try:
        with open(f, errors="replace") as fh:
            for _ in range(40):
                line = fh.readline()
                if not line:
                    break
                if line.startswith("#"):
                    return line.lstrip("#").strip() or None
    except OSError:
        return None
    return None


def discover(code_root: Path, known: set[str], *, depth: int = 3,
             skip: set[str] | None = None) -> list[dict]:
    """Git repos under `code_root` that shipyard cannot see, because they carry no
    manifest.

    Nothing on disk should be silently absent — a project you forgot you had is
    exactly the thing a board is supposed to surface. But discovery is not import:
    these are reported, never adopted, because which of nineteen repos is *relevant*
    is a judgment the tool does not get to make.
    """
    code_root = Path(code_root).expanduser()
    skip = skip or set()
    found, seen = [], set()
    candidates = []
    for level in range(depth):
        candidates += sorted(code_root.glob("*/" * level + ".git"))
    for git_dir in candidates:
        path = git_dir.parent
        if str(path) in seen:
            continue
        seen.add(str(path))
        if str(path) in known or any(part in skip for part in path.parts):
            continue
        if (path / "PROJECT.yaml").is_file():
            continue
        found.append({
            "id": _slug(path.name),
            "name": path.name,
            "path": str(path),
            "last_activity": _git(path, "log", "-1", "--format=%cI"),
            "remote": _git(path, "remote", "get-url", "origin"),
            "archived": "_archive" in path.parts,
        })
    return found


def _slug(name: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name.strip().lower())
    return "-".join(p for p in out.split("-") if p) or "project"


# Lines a README opens with that are not prose: headings, raw HTML wrappers,
# horizontal rules, blockquotes, and list markers. Badge lines are caught
# separately, by having nothing left once the links come out.
_FURNITURE = re.compile(r'^(#|<|>|-{3,}|={3,}|\*{3,}|([-*+]|\d+\.)\s)')
_FENCE = re.compile(r'^(```|~~~)')
_BARE_URL = re.compile(r'^https?://\S+$')
_IMAGE = re.compile(r'!\[[^\]]*\]\([^)]*\)')
_LINK = re.compile(r'\[([^\]]*)\]\([^)]*\)')
_EMPHASIS = re.compile(r'(\*\*|__|\*|_|`)')


def readme_summary(root: Path) -> str:
    """The README's first real paragraph, unwrapped into one line.

    This exists because the description a human copies by hand is the one that
    comes out wrong. Four manifests in this fleet carry a description cut
    mid-sentence, each stopping
    exactly at the README's line wrap, because on screen a wrapped line looks
    like a whole one.

    So the paragraph is joined *before* it is taken, and there is deliberately
    no character cap: a cap is the very defect this removes, only committed by
    the tool instead of by a person.
    """
    try:
        text = (Path(root) / "README.md").read_text(errors="replace")
    except OSError:
        return ""

    paragraph: list[str] = []
    fenced = False
    for raw in text.splitlines():
        line = raw.strip()
        if _FENCE.match(line):
            # A fenced block is never prose, and one repo here opens with an
            # ASCII-art logo inside ```text — which reads as a paragraph of
            # punctuation to anything that only looks at line shape.
            fenced = not fenced
            if paragraph:
                break
            continue
        if fenced:
            continue
        stripped = _strip_markdown(line)
        if not line or _FURNITURE.match(line) or not stripped or _BARE_URL.match(stripped):
            # Furniture before any prose is skipped; after it, the paragraph
            # has ended — a badge row under the opening line is not more of it.
            if paragraph:
                break
            continue
        paragraph.append(line)
    return _strip_markdown(" ".join(paragraph))


def _strip_markdown(line: str) -> str:
    """Inline markup off, text kept. Images vanish, links keep their label."""
    out = _IMAGE.sub("", line)
    out = _LINK.sub(r"\1", out)
    out = _EMPHASIS.sub("", out)
    return " ".join(out.split())


def write_manifest(path: Path, *, name: str, description: str = "") -> dict:
    """Adopt a repo by writing the manifest into the repo itself.

    The project's identity belongs to the project: a manifest in the repo survives
    shipyard being deleted, travels with a clone, and keeps one source of truth
    rather than a registry that drifts from the five that already do it this way.

    An absent description falls back to the README rather than to `""`, because
    an empty field is what invites the hand-copied, half-a-sentence version.
    """
    path = Path(path)
    if not (path / ".git").is_dir():
        raise RepoError(f"{path.name} is not a git repository")
    target = path / "PROJECT.yaml"
    if target.exists():
        raise RepoError(f"{path.name} already has a PROJECT.yaml")

    manifest = {"id": _slug(name), "name": name,
                "description": description or readme_summary(path)}
    remote = _git(path, "remote", "get-url", "origin")
    if remote:
        manifest["links"] = {"github": _https(remote)}
    try:
        target.write_text(_dump(manifest))
    except OSError as e:
        raise RepoError(f"could not write {target}: {e}")
    return {**manifest, "path": str(path)}


def _https(remote: str) -> str:
    """git@github.com:user/repo.git → https://github.com/user/repo — a link the
    browser can open, since that is what the card does with it."""
    r = remote.strip()
    if r.startswith("git@"):
        host, _, rest = r[4:].partition(":")
        r = f"https://{host}/{rest}"
    return r[:-4] if r.endswith(".git") else r


def _dump(manifest: dict) -> str:
    """Hand-written rather than yaml.dump so the file reads like the five a human
    already wrote — key order preserved, no anchors, no sorted keys."""
    lines = ["# Imported by shipyard.",
             f"id: {_scalar(manifest['id'])}",
             f"name: {_scalar(manifest['name'])}",
             f"description: {_scalar(manifest.get('description') or '')}"]
    if manifest.get("links"):
        lines.append("links:")
        for k, v in manifest["links"].items():
            lines.append(f"  {k}: {_scalar(v)}")
    return "\n".join(lines) + "\n"


def _scalar(value: str) -> str:
    """Quote anything YAML would otherwise misread.

    Written unquoted, a description like "Search over Example: the
    Demo" is a mapping inside a mapping, and the whole manifest fails to
    parse — so the project silently disappears from the board. Four did.
    """
    s = str(value)
    if s == "":
        return '""'
    if re.search(r':\s|\s#|^[\s>|&*!%@`\[\]{},]|[:#]$|^-\s', s) or s.strip() != s:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def read_document(root: Path, rel: str) -> dict:
    """Read a document from inside the repo, and only from inside the repo.

    `rel` arrives from a URL, so it is treated as hostile: resolved against the
    repo and rejected unless it lands underneath it. `resolve()` collapses `..`
    and follows symlinks before the check, so neither escapes.
    """
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise RepoError("that path is outside the project")
    if not target.is_file():
        raise RepoError(f"no such document: {rel}")
    if target.suffix.lower() not in READABLE_SUFFIXES:
        raise RepoError(f"{target.suffix or 'that file type'} is not readable here")
    if target.stat().st_size > MAX_DOC_BYTES:
        raise RepoError("that document is too large to display")
    try:
        body = target.read_text(errors="replace")
    except OSError as e:
        raise RepoError(f"could not read {target.name}: {e}")
    return {"name": target.name, "path": rel, "body": body}
