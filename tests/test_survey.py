"""The survey: what the code shows about itself, read off a real tree.

This module had no tests and was wrong twice in one evening — node packages keyed
off the wrong signal, and Poetry-declared dependencies invisible, so deepwiki-open
reported none at all. Both were caught by a human reading four repos by hand. These
are the checks that should have caught them instead.

Fixtures are real directories, not mocks: the whole module's job is to walk a tree,
so faking the tree would test nothing.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("SHIPYARD_DB", os.path.join(tempfile.mkdtemp(), "survey.sqlite"))
os.environ.setdefault("SHIPYARD_CHART_EXPORT", os.path.join(tempfile.mkdtemp(), "chart.md"))
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402

from app import survey  # noqa: E402


def write(root: Path, rel: str, lines: int = 1, text: str | None = None) -> Path:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text if text is not None else "\n".join("x" for _ in range(lines)) + "\n")
    return f


# ---------- shape ----------

def test_lines_and_languages_are_counted(tmp_path):
    write(tmp_path, "a.py", 10)
    write(tmp_path, "b.py", 5)
    write(tmp_path, "c.ts", 3)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["files"] == 3
    assert shape["lines"] == 18
    assert {l["name"]: l["lines"] for l in shape["languages"]} == {"Python": 15, "TypeScript": 3}


def test_prose_and_config_do_not_win_the_primary_verdict(tmp_path):
    """A repo is not "mostly Markdown" because it is well documented."""
    write(tmp_path, "README.md", 500)
    write(tmp_path, "config.yaml", 200)
    write(tmp_path, "app.py", 20)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["primary"] == "Python"
    # ...but the prose is still counted, because it is still there.
    assert shape["lines"] == 720


def test_a_tree_with_no_code_has_no_primary(tmp_path):
    write(tmp_path, "notes.md", 5)
    assert survey.survey(tmp_path)["shape"]["primary"] is None


def test_unknown_extensions_are_counted_as_files_but_not_lines(tmp_path):
    write(tmp_path, "data.parquet", 40)
    write(tmp_path, "app.py", 4)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["files"] == 2, "it is still a file on disk"
    assert shape["lines"] == 4, "but only languages we recognise contribute lines"


# ---------- tests, and the empty case ----------

def test_test_files_are_recognised_by_several_conventions(tmp_path):
    write(tmp_path, "tests/test_thing.py", 10)
    write(tmp_path, "src/widget.spec.ts", 5)
    write(tmp_path, "src/widget.ts", 5)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["test_files"] == 2
    assert shape["test_ratio"] == round(15 / 20, 3)


def test_a_repo_with_no_tests_does_not_divide_by_zero(tmp_path):
    """feedwall has no tests at all, and the page has to say so rather than crash."""
    write(tmp_path, "app.py", 12)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["test_files"] == 0
    assert shape["test_ratio"] == 0.0


def test_an_entirely_empty_directory_is_survivable(tmp_path):
    shape = survey.survey(tmp_path)["shape"]
    assert shape == {"files": 0, "lines": 0, "languages": [], "primary": None,
                     "test_files": 0, "test_ratio": 0.0}


def test_a_path_that_is_not_a_directory_returns_nothing(tmp_path):
    f = write(tmp_path, "lonely.py", 1)
    assert survey.survey(f) is None


# ---------- layout ----------

def test_layout_is_ordered_by_weight_and_names_the_root(tmp_path):
    write(tmp_path, "big/one.py", 100)
    write(tmp_path, "small/two.py", 5)
    write(tmp_path, "setup.py", 20)
    layout = survey.survey(tmp_path)["layout"]
    assert [g["name"] for g in layout] == ["big", "(root)", "small"], \
        "heaviest first, with loose files at the root gathered under one name"
    assert layout[0]["lines"] == 100
    assert next(g for g in layout if g["name"] == "(root)")["lines"] == 20


def test_directories_with_no_countable_lines_are_dropped(tmp_path):
    """An assets folder pads the map with rows that are all zero and say nothing."""
    write(tmp_path, "code/app.py", 10)
    write(tmp_path, "assets/pic.png", 3)
    layout = survey.survey(tmp_path)["layout"]
    assert [g["name"] for g in layout] == ["code"]


def test_layout_reports_a_primary_language_per_directory(tmp_path):
    write(tmp_path, "frontend/app.tsx", 40)
    write(tmp_path, "backend/api.py", 30)
    layout = {g["name"]: g["primary"] for g in survey.survey(tmp_path)["layout"]}
    assert layout == {"frontend": "TypeScript", "backend": "Python"}


# ---------- what is skipped ----------

def test_vendored_and_build_directories_are_skipped(tmp_path):
    write(tmp_path, "app.py", 5)
    write(tmp_path, "node_modules/left-pad/index.js", 9999)
    write(tmp_path, ".venv/lib/thing.py", 9999)
    write(tmp_path, "dist/bundle.js", 9999)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["files"] == 1 and shape["lines"] == 5


def test_hidden_directories_are_skipped(tmp_path):
    write(tmp_path, "app.py", 5)
    write(tmp_path, ".github/workflows/ci.yml", 40)
    assert survey.survey(tmp_path)["shape"]["files"] == 1


def test_a_runaway_tree_degrades_rather_than_hanging(tmp_path, monkeypatch):
    monkeypatch.setattr(survey, "MAX_FILES", 5)
    for i in range(40):
        write(tmp_path, f"pkg/mod{i}.py", 1)
    shape = survey.survey(tmp_path)["shape"]
    assert shape["files"] <= 5, "the walk stops rather than reading forty files"


# ---------- entry points ----------

def test_make_targets_and_npm_scripts_are_found(tmp_path):
    write(tmp_path, "Makefile", text="setup: deps\n\tpip install\n\ntest:\n\tpytest\n"
                                     "VAR := value\n")
    write(tmp_path, "package.json", text=json.dumps({"scripts": {"dev": "vite"}}))
    names = {(e["kind"], e["name"]) for e in survey.entry_points(tmp_path)}
    assert ("make", "setup") in names and ("make", "test") in names
    assert ("npm", "dev") in names
    assert not any(n == "VAR" for _, n in names), "a variable assignment is not a target"


def test_scripts_one_level_down_are_labelled_with_their_directory(tmp_path):
    """shipyard keeps its npm scripts in frontend/, and `npm run dev` from the root
    would be the wrong instruction."""
    write(tmp_path, "frontend/package.json", text=json.dumps({"scripts": {"dev": "vite"}}))
    names = [e["name"] for e in survey.entry_points(tmp_path) if e["kind"] == "npm"]
    assert names == ["frontend/dev"]


# ---------- dependencies ----------

def test_pep621_dependencies_are_read_without_their_version_pins(tmp_path):
    write(tmp_path, "pyproject.toml", text=(
        '[project]\nname = "x"\ndependencies = ["fastapi>=0.1", "uvicorn[standard]", "pyyaml"]\n'))
    deps = survey.dependencies(tmp_path)
    assert deps["python"]["names"] == ["fastapi", "pyyaml", "uvicorn"]
    assert deps["python"]["count"] == 3


def test_poetry_dependencies_are_read_too(tmp_path):
    """deepwiki-open declares everything under [tool.poetry.dependencies] and so
    reported no Python dependencies at all — then fell through to listing its
    frontend's instead."""
    write(tmp_path, "pyproject.toml", text=(
        '[project]\nname = "x"\n\n[tool.poetry.dependencies]\n'
        'python = "^3.11"\nfastapi = ">=0.95"\nadalflow = ">=0.1"\n'))
    deps = survey.dependencies(tmp_path)
    assert deps["python"]["names"] == ["adalflow", "fastapi"]
    assert "python" not in deps["python"]["names"], "the interpreter is not a dependency"


def test_requirements_and_pyproject_are_merged_not_chosen_between(tmp_path):
    write(tmp_path, "pyproject.toml", text='[project]\nname = "x"\ndependencies = ["fastapi"]\n')
    write(tmp_path, "api/requirements.txt", text="# comment\n-r other.txt\nboto3==1.0\n\n")
    assert survey.dependencies(tmp_path)["python"]["names"] == ["boto3", "fastapi"]


def test_node_packages_are_suppressed_when_there_is_a_python_runtime(tmp_path):
    """Learn Hub is a Python app whose TypeScript frontend is simply larger, and
    listing react beside eleven real runtime deps buries the answer."""
    write(tmp_path, "pyproject.toml", text='[project]\nname = "x"\ndependencies = ["fastapi"]\n')
    write(tmp_path, "frontend/package.json",
          text=json.dumps({"dependencies": {"react": "^18", "marked": "^12"}}))
    deps = survey.dependencies(tmp_path)
    assert set(deps) == {"python"}


def test_node_packages_are_kept_for_a_project_that_is_actually_node(tmp_path):
    """godot-mcp has no Python at all — reporting nothing would be a lie."""
    write(tmp_path, "package.json",
          text=json.dumps({"dependencies": {"zod": "^3", "express": "^4"}}))
    deps = survey.dependencies(tmp_path)
    assert deps["node"]["names"] == ["express", "zod"]


def test_a_project_with_no_manifests_reports_nothing_rather_than_failing(tmp_path):
    write(tmp_path, "app.py", 3)
    assert survey.dependencies(tmp_path) == {}


def test_malformed_manifests_do_not_take_the_page_down(tmp_path):
    write(tmp_path, "pyproject.toml", text="this is not : valid toml [[[\n")
    write(tmp_path, "package.json", text="{not json")
    assert survey.dependencies(tmp_path) == {}
    assert survey.entry_points(tmp_path) == []


# ---------- the whole payload ----------

def test_survey_reports_where_it_read_from(tmp_path):
    write(tmp_path, "app.py", 2)
    assert survey.survey(tmp_path)["path"] == str(tmp_path)


def test_survey_carries_every_section(tmp_path):
    write(tmp_path, "app.py", 2)
    assert set(survey.survey(tmp_path)) == {
        "shape", "layout", "start_here", "path", "entries", "dependencies"}


# ---------- start here ----------

def test_the_most_imported_module_comes_first(tmp_path):
    write(tmp_path, "core.py", text="VALUE = 1\n")
    for i in range(3):
        write(tmp_path, f"user{i}.py", text="from core import VALUE\n")
    write(tmp_path, "lonely.py", text="x = 1\n")
    start = survey.survey(tmp_path)["start_here"]
    assert start[0] == {"file": "core.py", "imported_by": 3}
    assert "lonely.py" not in [e["file"] for e in start], "nothing imports it"


def test_a_file_importing_itself_is_not_a_reference(tmp_path):
    write(tmp_path, "solo.py", text="from solo import thing\n")
    assert survey.survey(tmp_path)["start_here"] == []


def test_from_package_imports_are_counted(tmp_path):
    """`from . import chart` names the module after the import, not in the path —
    shipyard's own package uses this form and was missing from its own list."""
    write(tmp_path, "chart.py", text="def draw(): pass\n")
    write(tmp_path, "main.py", text="from . import chart, repo as repo_mod\n")
    write(tmp_path, "other.py", text="from . import (chart,\n    survey)\n")
    start = {e["file"]: e["imported_by"] for e in survey.survey(tmp_path)["start_here"]}
    assert start.get("chart.py") == 2


def test_an_import_cannot_credit_the_other_language(tmp_path):
    """shipyard has chart.py and chart.jsx; a python import means the python one."""
    write(tmp_path, "chart.py", text="x = 1\n")
    write(tmp_path, "chart.jsx", text="export const x = 1\n")
    write(tmp_path, "backend.py", text="from chart import x\n")
    start = {e["file"]: e["imported_by"] for e in survey.survey(tmp_path)["start_here"]}
    assert start == {"chart.py": 1}


def test_a_named_directory_disambiguates_two_files_with_one_name(tmp_path):
    """api/progress.ts and ui/progress.tsx were both credited for either mention."""
    write(tmp_path, "api/progress.ts", text="export const p = 1\n")
    write(tmp_path, "ui/progress.tsx", text="export const P = 2\n")
    write(tmp_path, "page.tsx", text="import { p } from '../api/progress'\n")
    start = {e["file"]: e["imported_by"] for e in survey.survey(tmp_path)["start_here"]}
    assert start == {"api/progress.ts": 1}


def test_documents_are_never_where_to_start_reading_code(tmp_path):
    """chart.md shares a stem with chart.py and was being credited alongside it."""
    write(tmp_path, "chart.md", text="# notes\n")
    write(tmp_path, "chart.py", text="x = 1\n")
    write(tmp_path, "user.py", text="from chart import x\n")
    assert [e["file"] for e in survey.survey(tmp_path)["start_here"]] == ["chart.py"]


def test_files_named_for_what_they_are_are_ignored(tmp_path):
    """Every package has an index and a utils; topping the list with them tells you
    nothing about where this particular project begins."""
    write(tmp_path, "utils.py", text="def f(): pass\n")
    write(tmp_path, "a.py", text="from utils import f\n")
    write(tmp_path, "b.py", text="from utils import f\n")
    assert survey.survey(tmp_path)["start_here"] == []
