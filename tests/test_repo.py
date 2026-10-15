"""What a repo says about itself: version, documents, decisions — and containment.

Nothing here invents a shipyard convention. Each test asserts we read back what the
repo already keeps, and that a path arriving off a URL cannot escape it.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("SHIPYARD_DB", os.path.join(tempfile.mkdtemp(), "repo.sqlite"))
os.environ.setdefault("SHIPYARD_CHART_EXPORT", os.path.join(tempfile.mkdtemp(), "chart.md"))
os.environ.setdefault("SHIPYARD_ARGUMENTS_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402

from app import repo  # noqa: E402


def git(path, *argv):
    subprocess.run(["git", "-C", str(path), *argv], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def sample(tmp_path):
    """A small repo with one tag and one commit on top of it."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("# Sample\n")
    (tmp_path / "ARCHITECTURE.md").write_text("# Boundaries\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "first")
    git(tmp_path, "tag", "v1.0.0")
    (tmp_path / "CHANGELOG.md").write_text("# Changes\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "second")
    return tmp_path


def test_version_separates_released_from_unreleased(sample):
    """One number would be a lie of omission: a repo past its tag is not the tag."""
    v = repo.version(sample)
    assert v["tag"] == "v1.0.0"
    assert v["ahead"] == 1, "the commit on top of the tag has to be visible"
    assert v["dirty"] == 0
    assert v["branch"] == "main"


def test_no_upstream_is_its_own_state(sample):
    """Distinct from 'nothing to push' — it is what stops a repo being demonstrable."""
    v = repo.version(sample)
    assert v["has_remote"] is False
    assert v["unpushed"] is None


def test_dirty_tree_is_counted(sample):
    (sample / "README.md").write_text("# Sample edited\n")
    assert repo.version(sample)["dirty"] == 1


def test_a_directory_without_git_has_no_version(tmp_path):
    assert repo.version(tmp_path) is None


def test_documents_are_discovered_not_declared(sample):
    labels = [d["label"] for d in repo.documents(sample)]
    assert labels == ["architecture", "changelog", "readme"], \
        "ordered most-orienting first, and found on disk without a manifest"


def test_published_docs_url_comes_from_the_manifest(sample):
    docs = repo.documents(sample, {"docs": "https://example.com/wiki"})
    assert docs[0] == {"label": "docs", "kind": "url", "href": "https://example.com/wiki"}


def test_decisions_are_newest_first_with_titles(sample):
    adr = sample / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-first.md").write_text("# ADR 0001: Use sqlite\n")
    (adr / "0002-second.md").write_text("# ADR 0002: Keep TypeScript\n")
    (adr / "README.md").write_text("# index, not a decision\n")
    got = repo.decisions(sample)
    assert [d["title"] for d in got] == ["ADR 0002: Keep TypeScript", "ADR 0001: Use sqlite"]
    assert all("README" not in d["name"] for d in got), "the index is not a decision"


def test_decisions_appear_in_documents_as_a_count(sample):
    adr = sample / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-x.md").write_text("# One\n")
    entry = [d for d in repo.documents(sample) if d["kind"] == "dir"][0]
    assert entry == {"label": "decisions", "kind": "dir", "count": 1}


# ---------- containment ----------

@pytest.mark.parametrize("bad", [
    "../outside.md",
    "../../etc/passwd",
    "/etc/passwd",
    "docs/../../outside.md",
    "README.md/../../outside.md",
])
def test_a_path_from_a_url_cannot_escape_the_project(sample, bad):
    """`rel` arrives off a query string, so it is treated as hostile."""
    (sample.parent / "outside.md").write_text("secret\n")
    with pytest.raises(repo.RepoError):
        repo.read_document(sample, bad)


def test_a_symlink_out_of_the_project_is_refused(sample):
    """resolve() follows the link before the check, so the target is what counts."""
    (sample.parent / "outside.md").write_text("secret\n")
    (sample / "sneaky.md").symlink_to(sample.parent / "outside.md")
    with pytest.raises(repo.RepoError):
        repo.read_document(sample, "sneaky.md")


def test_readable_types_are_a_list_not_an_exclusion(sample):
    """Source became readable so a flow step's code reference can be followed.
    The guard is still an allow-list: .env, keys and dumps stay out by not being
    on it, rather than by being guessed at."""
    (sample / "run.py").write_text("print('x')\n")
    assert repo.read_document(sample, "run.py")["name"] == "run.py"

    for name, body in (("secrets.env", "TOKEN=abc\n"),
                       ("id_rsa", "-----BEGIN-----\n"),
                       ("dump.sqlite", "binary\n")):
        (sample / name).write_text(body)
        with pytest.raises(repo.RepoError):
            repo.read_document(sample, name)


def test_a_normal_document_reads(sample):
    got = repo.read_document(sample, "ARCHITECTURE.md")
    assert got["name"] == "ARCHITECTURE.md" and "Boundaries" in got["body"]


def test_an_oversized_document_is_refused(sample):
    (sample / "huge.md").write_text("x" * (repo.MAX_DOC_BYTES + 1))
    with pytest.raises(repo.RepoError):
        repo.read_document(sample, "huge.md")


# ---------- changelog drift ----------

def test_features_landing_with_no_changelog_entry_are_drift(sample):
    """The live case: Learn Hub sat 13 commits past its tag with five features
    shipped and a changelog whose newest entry was the tag itself."""
    (sample / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0] — 2026-01-01\n\n- shipped\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "docs: changelog for 1.0.0")
    (sample / "feature.py").write_text("x = 1\n")     # lands *after* the summary
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "feat: something a user can see")

    c = repo.changelog(sample, "v1.0.0")
    assert c["drift"] is True
    assert [u["subject"] for u in c["unlogged"]] == ["feat: something a user can see"]
    assert c["latest_documented"] == "1.0.0"


def test_housekeeping_commits_do_not_raise_the_flag(sample):
    """`chore: sync MAP.md file index [skip ci]` must not cry wolf — a flag that
    fires on noise gets ignored, which is the failure it exists to prevent."""
    (sample / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0]\n\n- shipped\n")
    for msg in ("chore: sync MAP.md file index [skip ci]", "docs: fix a typo",
                "backlog: track TASK-19"):
        (sample / "noise.txt").write_text(msg)
        git(sample, "add", "-A")
        git(sample, "commit", "-qm", msg)
    c = repo.changelog(sample, "v1.0.0")
    assert c["unlogged"] == [] and c["drift"] is False


def test_an_unreleased_section_clears_the_flag(sample):
    """Somebody is keeping up. We do not try to match entry-to-commit — that would
    be guesswork dressed as precision."""
    (sample / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- the new thing\n\n## [1.0.0]\n\n- shipped\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "docs: note the new thing")
    (sample / "feature.py").write_text("x = 1\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "feat: the new thing")
    c = repo.changelog(sample, "v1.0.0")
    assert c["unreleased_entries"] == 1
    assert c["drift"] is False, "an entry exists, so the summary is keeping up"


def test_a_changelog_written_after_the_work_is_not_drift(sample):
    """csv-profiler's shape, and the false positive that produced this rule.

    Nine features landed, then a `## [0.1.0]` section was written covering all of
    them, and the repo was never tagged. Anchoring on the tag meant no boundary at
    all, so a changelog that was entirely up to date read as nine unlogged
    features. A flag that cries wolf gets ignored.
    """
    (sample / "feature.py").write_text("x = 1\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "feat: the classifier")
    (sample / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0]\n\n- the classifier\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "docs: CHANGELOG 0.1.0")

    c = repo.changelog(sample, None)     # never tagged
    assert c["unlogged"] == []
    assert c["drift"] is False, "the summary was written after the work, and covers it"


def test_a_changelog_behind_the_tags_is_reported(sample):
    """shipyard's own case: tagged v0.16.0 with a changelog stopping at 0.11.0."""
    (sample / "CHANGELOG.md").write_text("# Changelog\n\n## [0.11.0]\n\n- old\n")
    c = repo.changelog(sample, "v1.0.0")
    assert c["release_behind"] is True
    assert c["latest_documented"] == "0.11.0"


def test_a_missing_changelog_still_reports_what_is_unlogged(sample):
    (sample / "CHANGELOG.md").unlink()   # the fixture ships one; this repo has none
    (sample / "feature.py").write_text("x = 1\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "feat: no changelog exists here")
    c = repo.changelog(sample, "v1.0.0")
    assert c["path"] is None and c["drift"] is True


# ---------- staleness ----------

def test_running_behind_when_the_process_predates_the_commit():
    """The 2026-08-07 case: an hour of stale code served while the fix sat committed."""
    from datetime import datetime, timedelta, timezone
    just_now = datetime.now(timezone.utc).isoformat()
    assert repo.running_behind(just_now, uptime_s=3600) is True

    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    assert repo.running_behind(old, uptime_s=3600) is False


def test_staleness_is_unknown_rather_than_false_when_nothing_runs():
    """Nothing running is not the same as running current code."""
    assert repo.running_behind("2026-08-07T10:00:00+00:00", None) is None
    assert repo.running_behind(None, 3600) is None
    assert repo.running_behind("not-a-date", 3600) is None


def test_a_description_with_a_colon_survives_the_round_trip(tmp_path):
    """Written unquoted, "Example: the Demo" is a mapping inside a mapping and
    the whole manifest fails to parse — so the project silently disappears from the
    board. Four did before this was quoted."""
    import yaml
    (tmp_path / ".git").mkdir()
    got = repo.write_manifest(tmp_path, name="manalab",
                              description="Search over Example: the Demo")
    parsed = yaml.safe_load((tmp_path / "PROJECT.yaml").read_text())
    assert parsed["description"] == "Search over Example: the Demo"
    assert parsed["id"] == got["id"]


def test_awkward_manifest_values_are_quoted(tmp_path):
    import yaml
    (tmp_path / ".git").mkdir()
    repo.write_manifest(tmp_path, name="edge",
                        description="# not a comment: and *not an alias")
    parsed = yaml.safe_load((tmp_path / "PROJECT.yaml").read_text())
    assert parsed["description"] == "# not a comment: and *not an alias"


# ---------- the description the README already holds ----------

def test_an_absent_description_takes_the_whole_readme_paragraph(tmp_path):
    """The defect this replaces, verbatim: four manifests in the fleet stop at the
    README's line wrap — "…every custom app on", "…driven by a DGX" — because a
    wrapped line looks whole on screen. The paragraph must be joined before it is
    taken, so the wrap cannot become the ending."""
    import yaml
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text(
        "# Mission Control\n\n"
        "A single dashboard to start, stop, and watch\n"
        "every custom app on the Spark.\n\n"
        "## Run\n")
    repo.write_manifest(tmp_path, name="mission-control")
    parsed = yaml.safe_load((tmp_path / "PROJECT.yaml").read_text())
    assert parsed["description"] == (
        "A single dashboard to start, stop, and watch every custom app on the Spark.")


def test_an_explicit_description_still_wins(tmp_path):
    """The README is the fallback, not the authority — adopting with a description
    typed on purpose must not be overwritten by whatever the README opens with."""
    import yaml
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# thing\n\nWhat the readme says.\n")
    repo.write_manifest(tmp_path, name="thing", description="What I meant.")
    parsed = yaml.safe_load((tmp_path / "PROJECT.yaml").read_text())
    assert parsed["description"] == "What I meant."


def test_badges_html_and_headings_are_not_the_description(tmp_path):
    """Every fork in this fleet opens with a wrapper div and a wall of shields.io
    badges. Taking "the first non-empty line" would adopt the badge row."""
    (tmp_path / "README.md").write_text(
        '<div align="center">\n\n'
        "# whichllm\n\n"
        "[![PyPI](https://img.shields.io/pypi/v/x)](https://pypi.org/project/x/)\n"
        "[![License](https://img.shields.io/badge/L-MIT-y.svg)](https://opensource.org/l)\n\n"
        "**Find the best local LLM** that actually runs on your `hardware`.\n")
    assert repo.readme_summary(tmp_path) == (
        "Find the best local LLM that actually runs on your hardware.")


def test_fenced_ascii_art_is_not_a_paragraph(tmp_path):
    """A real repo here opens with an ASCII-art logo inside ```text. To anything
    that only looks at line shape, that is a paragraph of punctuation — it produced
    "text ((((((( (((((((" as a description before fences were tracked."""
    (tmp_path / "README.md").write_text(
        "# Godot MCP\n\n"
        "```text\n"
        "   (((((((     (((((((\n"
        "  (((((((((   (((((((((\n"
        "```\n\n"
        "A Model Context Protocol server for the Godot game engine.\n")
    assert repo.readme_summary(tmp_path) == (
        "A Model Context Protocol server for the Godot game engine.")


def test_a_link_only_line_is_not_a_description(tmp_path):
    """One README leads with a bare tutorial link. Keeping the link text would put
    a raw URL on the project card, which describes nothing."""
    (tmp_path / "README.md").write_text(
        "## Watch the tutorial:\n"
        "[https://example.com/v?a=1](https://example.com/v?a=1)\n\n"
        "Upgrading from an old version means updating your compose file.\n")
    assert repo.readme_summary(tmp_path) == (
        "Upgrading from an old version means updating your compose file.")


def test_no_readme_is_not_an_error(tmp_path):
    """Adoption must not depend on a README existing — an empty description is a
    thin manifest, but a raised exception is a repo that cannot be adopted."""
    import yaml
    (tmp_path / ".git").mkdir()
    repo.write_manifest(tmp_path, name="bare")
    parsed = yaml.safe_load((tmp_path / "PROJECT.yaml").read_text())
    assert parsed["description"] == ""


# ---------- churn ----------

def test_churn_counts_commits_not_files(sample):
    """One commit rewriting forty files is one act of work; counting files would let
    a single mass rename outrank three months of steady effort."""
    (sample / "src").mkdir()
    for i in range(5):
        (sample / "src" / f"m{i}.py").write_text("x\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "five files, one commit")

    (sample / "docs").mkdir()
    (sample / "docs" / "a.md").write_text("a\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "docs one")
    (sample / "docs" / "b.md").write_text("b\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "docs two")

    by = {c["name"]: c["commits"] for c in repo.churn(sample)}
    assert by["src"] == 1, "five files in one commit is one commit"
    assert by["docs"] == 2


def test_churn_gathers_loose_files_under_the_root(sample):
    (sample / "README.md").write_text("changed\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "touch the readme")
    assert "(root)" in {c["name"] for c in repo.churn(sample)}


def test_churn_is_ordered_by_attention(sample):
    for i in range(3):
        d = sample / "hot"
        d.mkdir(exist_ok=True)
        (d / f"f{i}.py").write_text("x\n")
        git(sample, "add", "-A")
        git(sample, "commit", "-qm", f"hot {i}")
    (sample / "cold").mkdir()
    (sample / "cold" / "f.py").write_text("x\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "cold once")
    names = [c["name"] for c in repo.churn(sample)]
    assert names.index("hot") < names.index("cold")


def test_churn_respects_the_window(sample):
    """A window is only useful if it excludes. Backdated so this asserts something."""
    old_dir = sample / "ancient"
    old_dir.mkdir()
    (old_dir / "f.py").write_text("x\n")
    git(sample, "add", "-A")
    env = {**os.environ, "GIT_AUTHOR_DATE": "2024-01-01T00:00:00",
           "GIT_COMMITTER_DATE": "2024-01-01T00:00:00"}
    subprocess.run(["git", "-C", str(sample), "commit", "-qm", "long ago"],
                   check=True, capture_output=True, text=True, env=env)

    (sample / "recent").mkdir()
    (sample / "recent" / "f.py").write_text("x\n")
    git(sample, "add", "-A")
    git(sample, "commit", "-qm", "recent work")

    names = {c["name"] for c in repo.churn(sample, days=90)}
    assert "recent" in names
    assert "ancient" not in names, "a 90-day window must not reach back to 2024"


def test_a_directory_without_git_has_no_churn(tmp_path):
    assert repo.churn(tmp_path) == []


# ---------- cycles ----------

@pytest.fixture
def plain(tmp_path):
    """A repo with one commit and no tags.

    The `sample` fixture ships a v1.0.0, and backdated tags sort before it — so
    cycle tests need a repo whose whole tag history they own.
    """
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "seed.txt").write_text("seed\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def tag_at(path, name, when):
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    (path / f"{name}.txt").write_text(name)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", name],
                   check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(path), "tag", name], check=True, capture_output=True)


def test_the_version_move_says_which_unit_of_the_protocol_it_was(plain):
    """sub-cycle = MINOR, light = PATCH, super = MAJOR. The number carries the
    meaning, so nothing has to be recorded anywhere."""
    tag_at(plain, "v0.1.0", "2026-01-01T00:00:00")
    tag_at(plain, "v0.2.0", "2026-01-02T00:00:00")
    tag_at(plain, "v0.2.1", "2026-01-03T00:00:00")
    tag_at(plain, "v1.0.0", "2026-01-04T00:00:00")
    by = {c["tag"]: c["weight"] for c in repo.cycles(plain)["cycles"]}
    assert by["v0.1.0"] == "first", "nothing to compare the opening version against"
    assert by["v0.2.0"] == "sub"
    assert by["v0.2.1"] == "light"
    assert by["v1.0.0"] == "super"


def test_cycles_are_newest_first(plain):
    tag_at(plain, "v0.2.0", "2026-01-02T00:00:00")
    tag_at(plain, "v0.3.0", "2026-01-03T00:00:00")
    assert [c["tag"] for c in repo.cycles(plain)["cycles"]][:2] == ["v0.3.0", "v0.2.0"]


def test_work_since_the_last_tag_is_open_not_finished(plain):
    """"No version, no credit." Commits in flight are reported apart from the cut
    cycles and never counted among them."""
    tag_at(plain, "v0.2.0", "2026-01-02T00:00:00")
    (plain / "wip.py").write_text("x = 1\n")
    git(plain, "add", "-A")
    git(plain, "commit", "-qm", "half a cycle")
    c = repo.cycles(plain)
    assert c["open"] == {"since": "v0.2.0", "commits": 1}
    assert "wip" not in str(c["cycles"])
    assert c["counts"]["cut"] == 1, "the open work is not a cut version"


def test_a_tag_with_no_cycle_record_says_so(plain, tmp_path):
    """Twenty of shipyard's twenty-eight tags have no retro, and a surface that
    hid that would be worse than no surface."""
    tag_at(plain, "v0.2.0", "2026-01-02T00:00:00")
    tag_at(plain, "v0.3.0", "2026-01-03T00:00:00")
    records = tmp_path / "Cycles"
    records.mkdir()
    (records / "v0.2.0 — Chart core.md").write_text("# retro\n")

    by = {c["tag"]: c["record"] for c in repo.cycles(plain, records)["cycles"]}
    assert by["v0.2.0"]["title"] == "Chart core"
    assert by["v0.3.0"] is None
    assert repo.cycles(plain, records)["counts"]["recorded"] == 1


def test_non_semver_tags_are_not_cycles(plain):
    """A release tag is the transaction commit; `nightly` is not a finished cycle."""
    tag_at(plain, "v0.2.0", "2026-01-02T00:00:00")
    subprocess.run(["git", "-C", str(plain), "tag", "nightly"], check=True, capture_output=True)
    assert [c["tag"] for c in repo.cycles(plain)["cycles"]] == ["v0.2.0"]


def test_a_repo_with_no_tags_has_no_cycles(plain):
    c = repo.cycles(plain)
    assert c["cycles"] == []
    assert c["open"] == {"since": None, "commits": 1}, "everything is still in flight"


def test_missing_records_directory_is_not_an_error(plain, tmp_path):
    assert repo.cycles(plain, tmp_path / "nope")["counts"]["recorded"] == 0


# ---------- mirroring cycle records ----------

def test_records_absent_from_the_repo_are_reported_as_behind(plain, tmp_path):
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v0.2.0 — Chart core.md").write_text("# retro\n")
    state = repo.mirror_state(records, plain)
    assert state["missing"] == ["0.2.0"] and state["behind"] == 1


def test_mirroring_copies_verbatim(plain, tmp_path):
    """Byte equality is what makes "is this current" a comparison rather than a
    judgement, so nothing is stamped onto the copy."""
    records = tmp_path / "Cycles"; records.mkdir()
    body = "# v0.2.0 — Chart core\n\nretro text\n"
    (records / "v0.2.0 — Chart core.md").write_text(body)

    out = repo.mirror_records(records, plain)
    assert out["copied"] == ["0.2.0"]
    copy = plain / repo.MIRROR_DIR / "v0.2.0 — Chart core.md"
    assert copy.read_text() == body
    assert repo.mirror_state(records, plain)["behind"] == 0


def test_a_second_mirror_copies_nothing(plain, tmp_path):
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v0.2.0 — x.md").write_text("a\n")
    repo.mirror_records(records, plain)
    assert repo.mirror_records(records, plain)["copied"] == []


def test_an_edited_copy_is_stale_and_gets_overwritten(plain, tmp_path):
    """One direction only. A record is a hand-written retro, and two editable
    versions of the same thought with nothing to say which wins is the drift this
    mirror exists to avoid."""
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v0.2.0 — x.md").write_text("original\n")
    repo.mirror_records(records, plain)
    copy = plain / repo.MIRROR_DIR / "v0.2.0 — x.md"
    copy.write_text("edited in the repo\n")

    assert repo.mirror_state(records, plain)["stale"] == ["0.2.0"]
    repo.mirror_records(records, plain)
    assert copy.read_text() == "original\n"


def test_the_mirror_explains_itself(plain, tmp_path):
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v0.2.0 — x.md").write_text("a\n")
    repo.mirror_records(records, plain)
    readme = (plain / repo.MIRROR_DIR / "README.md").read_text()
    assert "copies" in readme and "vault" in readme


def test_mirroring_nothing_is_refused_rather_than_silent(plain, tmp_path):
    empty = tmp_path / "Cycles"; empty.mkdir()
    with pytest.raises(repo.RepoError):
        repo.mirror_records(empty, plain)
    with pytest.raises(repo.RepoError):
        repo.mirror_records(None, plain)


def test_untracked_directories_are_counted_by_file(plain):
    """git collapses an untracked directory to one porcelain line. manalab reported
    "13 uncommitted" against 71 real files, and every never-committed repo reads
    that way — which is exactly when the number matters most."""
    (plain / "pkg").mkdir()
    for i in range(5):
        (plain / "pkg" / f"m{i}.py").write_text("x\n")
    (plain / "loose.txt").write_text("y\n")

    assert repo.version(plain)["dirty"] == 6, "five files in a directory, plus one loose"


def test_the_working_tree_listing_shows_each_untracked_file(plain):
    (plain / "pkg").mkdir()
    for i in range(3):
        (plain / "pkg" / f"m{i}.py").write_text("x\n")
    files = [d["file"] for d in repo.recent_work(plain, None)["dirty"]]
    assert sorted(files) == ["pkg/m0.py", "pkg/m1.py", "pkg/m2.py"]


"""Owed — which kinds of debt a project is in.

Pure over already-computed values, so these need no git fixture. The cases that
matter are the ones where *not* reporting is correct: unknown is not owed, and a
changelog somebody is keeping up with is not drift.
"""


def _v(**kw):
    base = {"tag": "v1.0.0", "ahead": 0, "dirty": 0, "unpushed": 0,
            "has_remote": True, "branch": "main"}
    return {**base, **kw}


def test_a_clean_charted_project_owes_nothing():
    assert repo.owed(_v(), {"drift": False, "unlogged": []}, False, True) == []


def test_the_five_day_drift_that_motivated_this():
    """Shipyard's own reading on 2026-08-12: 48 past the tag, 37 unpushed, 1 dirty.
    Every number was already on its project page; none of them was anywhere you
    would pass without going to look."""
    kinds = {o["kind"]: o for o in repo.owed(
        _v(ahead=48, dirty=1, unpushed=37), {"drift": False, "unlogged": []}, False, True)}

    assert set(kinds) == {"uncommitted", "unpushed", "untagged"}
    assert kinds["untagged"]["detail"] == "48 commits since v1.0.0"
    assert kinds["unpushed"]["n"] == 37


def test_no_remote_replaces_unpushed_rather_than_joining_it():
    """Without an upstream there is no count of what is unpushed — everything is.
    Reporting both would be one debt wearing two hats."""
    kinds = [o["kind"] for o in repo.owed(
        _v(unpushed=0, has_remote=False), None, False, True)]
    assert "no-remote" in kinds and "unpushed" not in kinds


def test_a_changelog_somebody_keeps_up_with_is_not_owed():
    """drift already means notable commits AND nothing under Unreleased, so
    entries are what clears the debt, not a second one."""
    owed = repo.owed(_v(), {"drift": False, "unlogged": [{"sha": "a", "subject": "feat: x"}],
                            "unreleased_entries": 4}, False, True)
    assert [o["kind"] for o in owed] == []


def test_drift_is_owed_and_counts_its_commits():
    owed = repo.owed(_v(), {"drift": True, "unlogged": [{"sha": "a", "subject": "feat: x"},
                                                        {"sha": "b", "subject": "fix: y"}]},
                     False, True)
    assert owed == [{"kind": "unlogged", "n": 2, "detail": "2 commits"}]


def test_unknown_is_not_owed():
    """`running_behind` returns None when it cannot tell — the honest answer for
    compose apps. Treating that as debt would put every unknowable app in the
    inbox permanently, which is how an inbox becomes wallpaper."""
    assert [o["kind"] for o in repo.owed(_v(), None, None, True)] == []
    assert [o["kind"] for o in repo.owed(_v(), None, True, True)] == ["running-old-code"]


def test_an_uncharted_project_owes_the_reason_it_exists():
    assert [o["kind"] for o in repo.owed(_v(), None, False, False)] == ["uncharted"]


def test_every_kind_emitted_is_declared_in_the_order():
    """The frontend renders OWED_KINDS in order; a kind emitted but not declared
    would be computed and never shown."""
    every = repo.owed(_v(ahead=1, dirty=1, unpushed=1, has_remote=True),
                      {"drift": True, "unlogged": [{"sha": "a", "subject": "feat: x"}]},
                      True, False)
    declared = {k for k, _ in repo.OWED_KINDS}
    assert {o["kind"] for o in every} <= declared
    assert {o["kind"] for o in every} == declared - {"no-remote"}


def test_counts_of_one_read_as_one():
    """"1 files" is the kind of seam that makes a reading feel machine-generated
    and therefore ignorable."""
    one = {o["kind"]: o["detail"] for o in repo.owed(
        _v(dirty=1, unpushed=1, ahead=1), {"drift": True, "unlogged": [{"sha": "a", "subject": "feat: x"}]},
        False, True)}
    assert one["uncommitted"] == "1 file"
    assert one["unpushed"] == "1 commit"
    assert one["untagged"] == "1 commit since v1.0.0"
    assert one["unlogged"] == "1 commit"


def test_a_cycle_record_with_no_tag_is_planned_not_invisible(plain, tmp_path):
    """`cycles` built from tags alone, so a cycle opened but not yet cut did not
    appear anywhere — which is exactly the state the Plan step creates."""
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v0.1.0 — Count the words.md").write_text("# v0.1.0\n")
    (records / "v0.2.0 — Not yet either.md").write_text("# v0.2.0\n")

    c = repo.cycles(plain, records)
    assert [p["version"] for p in c["planned"]] == ["0.2.0", "0.1.0"], "newest first"
    assert c["planned"][0]["title"] == "Not yet either"
    assert c["cycles"] == [], "nothing has been tagged"


def test_a_record_stops_being_planned_once_its_tag_exists(sample, tmp_path):
    """The tag is what closes a cycle, so this needs nothing marked done."""
    records = tmp_path / "Cycles"; records.mkdir()
    (records / "v1.0.0 — Already cut.md").write_text("# v1.0.0\n")
    (records / "v2.0.0 — Still open.md").write_text("# v2.0.0\n")

    c = repo.cycles(sample, records)
    assert [p["version"] for p in c["planned"]] == ["2.0.0"]
    assert any(x["version"] == "1.0.0" and x["record"] for x in c["cycles"]), \
        "the cut one moved over to cycles, carrying its record"
