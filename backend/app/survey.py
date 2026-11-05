"""A survey of the vessel — what the code shows about itself, with nothing written down.

The project page used to depend entirely on artifacts a human maintains: an
architecture note, a changelog, a decision record, a task list. Across nineteen
projects those exist 3, 4, 3 and 1 times, so the page was empty for almost every
repo and adding more of that kind of panel would only have added obligations.

Everything here is computed from the tree instead. It answers the question you
actually have when you open something four months later — what is this, what is it
made of, and how do I start it — for every repo on day one, and asks nothing of
you. Declared artifacts stay welcome where they exist; they are a bonus rather
than a prerequisite.
"""

import json
import re
import tomllib
from pathlib import Path

SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
        ".pytest_cache", ".next", "dist", "build", "site-packages", ".ruff_cache",
        "media", "out", ".micromamba", "target", ".gradle", "coverage"}

LANGUAGES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".rs": "Rust", ".go": "Go", ".c": "C", ".h": "C",
    ".cpp": "C++", ".hpp": "C++", ".java": "Java", ".rb": "Ruby", ".sh": "Shell",
    ".sql": "SQL", ".css": "CSS", ".scss": "CSS", ".html": "HTML", ".gd": "GDScript",
    ".md": "Markdown", ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
    ".toml": "TOML", ".ipynb": "Notebook",
}
# Prose and config are real files but they are not what a codebase *is*, so they are
# counted and then kept out of the "mostly X" verdict.
NOT_CODE = {"Markdown", "YAML", "JSON", "TOML"}
TEST_HINT = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)(test_|conftest)|_test\.|\.test\.|\.spec\.")

MAX_FILES = 20_000   # a runaway tree should degrade, not hang the page


def _manifests(root: Path, name: str) -> list[Path]:
    """`name` at the root and one level under it.

    A repo that splits backend from frontend keeps its dependencies and its run
    scripts one directory down — shipyard itself does — so a root-only look reports
    "no dependencies" for exactly the projects most worth describing.
    """
    out = [root / name] if (root / name).is_file() else []
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if child.is_dir() and child.name not in SKIP and not child.name.startswith("."):
            f = child / name
            if f.is_file():
                out.append(f)
    return out


def survey(path: Path) -> dict | None:
    """Shape, layout, entry points and dependencies — all read off the tree."""
    path = Path(path)
    if not path.is_dir():
        return None
    files = _walk(path)
    shape = _shape(path, files)
    return {
        "shape": shape,
        "layout": _layout(path, files),
        "start_here": entry_files(path, files),
        "path": str(path),
        "entries": entry_points(path),
        "dependencies": dependencies(path, primary=shape["primary"]),
    }


def _walk(root: Path) -> list[tuple[Path, int]]:
    """Every interesting file with its line count, bounded."""
    out: list[tuple[Path, int]] = []
    stack = [root]
    while stack and len(out) < MAX_FILES:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.name in SKIP or e.name.startswith("."):
                continue
            if e.is_symlink():
                continue
            if e.is_dir():
                stack.append(e)
            elif e.is_file():
                out.append((e, _lines(e)))
                if len(out) >= MAX_FILES:
                    return out
    return out


def _lines(f: Path) -> int:
    if f.suffix.lower() not in LANGUAGES:
        return 0
    try:
        if f.stat().st_size > 2_000_000:
            return 0
        with open(f, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _shape(root: Path, files: list[tuple[Path, int]]) -> dict:
    langs: dict[str, int] = {}
    tests = test_lines = 0
    total = 0
    for f, n in files:
        lang = LANGUAGES.get(f.suffix.lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + n
            total += n
        # Relative to the repo, never absolute: a project living in a directory
        # whose *path* contains "test" would otherwise report every file as a test.
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            rel = f.name
        if TEST_HINT.search(rel):
            tests += 1
            test_lines += n
    code = {k: v for k, v in langs.items() if k not in NOT_CODE}
    ranked = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "files": len(files),
        "lines": total,
        "languages": [{"name": k, "lines": v} for k, v in ranked[:6]],
        "primary": max(code, key=code.get) if code else None,
        "test_files": tests,
        # The ratio says more than either number: 14 test files means nothing until
        # you know whether they cover 500 lines or 50,000.
        "test_ratio": round(test_lines / total, 3) if total else 0.0,
    }


def _layout(root: Path, files: list[tuple[Path, int]]) -> list[dict]:
    """Top-level directories, largest first — the map you want before the detail."""
    groups: dict[str, dict] = {}
    for f, n in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            continue
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        g = groups.setdefault(top, {"name": top, "files": 0, "lines": 0, "langs": {}})
        g["files"] += 1
        g["lines"] += n
        lang = LANGUAGES.get(f.suffix.lower())
        if lang:
            g["langs"][lang] = g["langs"].get(lang, 0) + n
    out = []
    for g in groups.values():
        code = {k: v for k, v in g["langs"].items() if k not in NOT_CODE} or g["langs"]
        out.append({"name": g["name"], "files": g["files"], "lines": g["lines"],
                    "primary": max(code, key=code.get) if code else None})
    # A directory of assets with no countable lines tells you nothing about the
    # shape of the code, and pads the map with rows that are all zero.
    out = [g for g in out if g["lines"] > 0]
    return sorted(out, key=lambda g: g["lines"], reverse=True)[:12]


# Import lines, both dialects. Only the target matters, so the capture is the last
# path-ish token: `from app.chart import x`, `import chart`, `from './chart'`.
_IMPORT = re.compile(
    r"""^\s*(?:from\s+([.\w/]+)\s+import\b       # python: from a.b import c
        |import\s+([.\w]+)                        # python: import a.b
        |.*\bfrom\s+['"]([^'"]+)['"]              # js:     … from './a/b'
        |.*\brequire\(\s*['"]([^'"]+)['"])""",
    re.X)
# A file named for what it is rather than what it does tells you nothing about where
# to start, and every package has one, so they would top every list.
_ANONYMOUS = {"index", "__init__", "main", "app", "utils", "types", "const",
              "constants", "helpers", "setup", "conftest"}
# `from . import chart, repo as repo_mod` — the modules are named after `import`,
# not in the path, so the path-based match misses them entirely. shipyard's own
# package uses this form, which is how the gap showed up.
_FROM_PACKAGE = re.compile(r"^\s*from\s+\.+\s+import\s+\(?([^#]+)")


PY_SUFFIX = {".py"}
JS_SUFFIX = {".js", ".jsx", ".ts", ".tsx"}


def _keys(fam: str, leaf: str, near: str | None, wanted: set) -> list[tuple]:
    """Which candidate files an import line refers to.

    When the import names a directory — `from '../gateways/api/progress'` — only the
    file in that directory is meant. Without it, `api/progress.ts` and
    `ui/progress.tsx` were both credited for every mention of either.
    """
    exact = [k for k in wanted if k[0] == fam and k[1] == leaf and k[2] == near]
    if exact:
        return exact
    return [k for k in wanted if k[0] == fam and k[1] == leaf]


def entry_files(root: Path, files: list[tuple[Path, int]], limit: int = 6) -> list[dict]:
    """The modules everything else imports — where reading should start.

    Deliberately a text scan rather than a parser: resolving imports properly means
    a per-language dependency, and this only has to be directionally right. It
    counts *how many other files name you*, which is "what is load bearing here" in
    its cheapest honest form.

    Matching is per language family. shipyard has `chart.py`, `chart.jsx` and
    `chart.md`, and a stem match alone credited all three for every mention of
    either — including the markdown, which is never where you start reading code.
    """
    candidates = [(f, f.stem) for f, _ in files
                  if LANGUAGES.get(f.suffix.lower()) not in NOT_CODE
                  and f.suffix.lower() in LANGUAGES
                  and f.stem not in _ANONYMOUS]
    if not candidates:
        return []

    def family(suffix: str) -> str | None:
        if suffix in PY_SUFFIX:
            return "py"
        return "js" if suffix in JS_SUFFIX else None

    wanted = {(family(f.suffix.lower()), stem, f.parent.name) for f, stem in candidates}
    referenced: dict[tuple, set[str]] = {}
    for f, _ in files:
        if f.suffix.lower() not in LANGUAGES:
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if "import" not in line and "require" not in line:
                continue
            m = _IMPORT.match(line)
            if not m:
                continue
            # Groups 1-2 are python syntax, 3-4 javascript. Which one matched tells
            # us which family the author meant, so a python import cannot credit a
            # same-named .jsx and vice versa.
            fam = "py" if (m.group(1) or m.group(2)) else "js"
            target = next((g for g in m.groups() if g), "")
            parts = [p for p in target.replace("\\", "/").rstrip("/").split("/") if p]
            leaf = parts[-1].split(".")[-1] if parts else ""
            near = parts[-2] if len(parts) > 1 else None
            for key in _keys(fam, leaf, near, wanted):
                referenced.setdefault(key, set()).add(str(f))

            rel_import = _FROM_PACKAGE.match(line)
            if rel_import:
                for token in rel_import.group(1).split(","):
                    name = token.strip().split(" as ")[0].strip(" ()")
                    if ("py", name, None) in wanted or any(
                            k[1] == name for k in wanted if k[0] == "py"):
                        for key in _keys("py", name, None, wanted):
                            referenced.setdefault(key, set()).add(str(f))

    out = []
    for f, stem in candidates:
        key = (family(f.suffix.lower()), stem, f.parent.name)
        # A file importing itself is not a reference.
        callers = referenced.get(key, set()) - {str(f)}
        if callers:
            try:
                rel = f.relative_to(root).as_posix()
            except ValueError:
                rel = f.name
            out.append({"file": rel, "imported_by": len(callers)})
    out.sort(key=lambda e: (-e["imported_by"], e["file"]))
    return out[:limit]


def entry_points(path: Path) -> list[dict]:
    """How to start it — the question a README usually answers badly, if at all."""
    path = Path(path)
    out: list[dict] = []

    mk = path / "Makefile"
    if mk.is_file():
        try:
            for line in mk.read_text(errors="replace").splitlines():
                m = re.match(r"^([a-zA-Z][\w-]*)\s*:(?!=)", line)
                if m and m.group(1) not in {"PHONY"}:
                    out.append({"kind": "make", "name": m.group(1)})
        except OSError:
            pass

    for pkg in _manifests(path, "package.json"):
        where = "" if pkg.parent == path else f"{pkg.parent.name}/"
        try:
            scripts = (json.loads(pkg.read_text(errors="replace")) or {}).get("scripts") or {}
            out += [{"kind": "npm", "name": f"{where}{k}"} for k in scripts]
        except (OSError, ValueError):
            pass

    for name in ("docker-compose.yml", "docker-compose.yaml",
                 "deploy/compose/docker-compose.yml"):
        f = path / name
        if f.is_file():
            try:
                services = re.findall(r"^  ([a-zA-Z][\w-]*):\s*$",
                                      f.read_text(errors="replace"), re.M)
                out += [{"kind": "compose", "name": s} for s in services]
            except OSError:
                pass
            break

    for pyproj in _manifests(path, "pyproject.toml"):
        try:
            data = tomllib.loads(pyproj.read_text(errors="replace"))
            out += [{"kind": "script", "name": k}
                    for k in (data.get("project", {}).get("scripts") or {})]
        except (OSError, ValueError):
            pass

    seen, unique = set(), []
    for e in out:
        key = (e["kind"], e["name"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique[:24]


def dependencies(path: Path, primary: str | None = None) -> dict:
    """What it leans on. Names only — versions rot faster than they inform.

    Node packages are reported only for projects that *are* JavaScript. Everywhere
    else they belong to a frontend bolted onto something else, and listing react,
    react-dom and marked next to five real Python runtime deps buries the answer
    under things you already know.
    """
    path = Path(path)
    found: dict[str, list[str]] = {}

    py: set[str] = set()
    for pyproj in _manifests(path, "pyproject.toml"):
        try:
            data = tomllib.loads(pyproj.read_text(errors="replace"))
            for d in data.get("project", {}).get("dependencies") or []:
                py.add(re.split(r"[<>=!\[ ;]", d, 1)[0].strip())
            # Poetry keeps them somewhere else entirely, and a project that
            # declares them there is not a project with no dependencies.
            poetry = (data.get("tool", {}).get("poetry", {}).get("dependencies") or {})
            py |= {k for k in poetry if k.lower() != "python"}
        except (OSError, ValueError):
            pass
    for req in _manifests(path, "requirements.txt"):
        try:
            for line in req.read_text(errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    py.add(re.split(r"[<>=!\[ ;]", line, 1)[0].strip())
        except OSError:
            pass
    if py:
        found["python"] = sorted(n for n in py if n)

    # A project with a Python runtime keeps its node packages in a frontend, and
    # listing react next to five real runtime deps buries the answer. Primary
    # language is the wrong test — a Python app's TypeScript frontend can simply
    # be bigger. The presence of Python deps is the right one.
    node: set[str] = set()
    for pkg in ([] if py else _manifests(path, "package.json")):
        try:
            data = json.loads(pkg.read_text(errors="replace")) or {}
            node |= set(data.get("dependencies") or {})
        except (OSError, ValueError):
            pass
    if node:
        found["node"] = sorted(node)

    return {k: {"count": len(v), "names": v[:40]} for k, v in found.items()}
