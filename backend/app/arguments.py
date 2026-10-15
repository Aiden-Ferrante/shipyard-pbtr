"""Arguments — a waypoint is a thesis, and this is the essay that defends it.

Plain markdown files, nothing tool-specific. Shipyard scaffolds them, reads them and
can edit them inline; any editor opens the same file. They live in the repo beside
`docs/chart.md` so the reasoning is versioned with the code and survives a fresh
clone, and `SHIPYARD_ARGUMENTS_DIR` moves them anywhere (a vault, say) without
touching the rest.

Two rules the writes obey:

  * **Never overwrite prose shipyard did not write.** Scaffolding is create-only and
    every save is mtime-guarded, so a file edited elsewhere is refused rather than
    clobbered.
  * **The verdict is read, never enforced.** An essay concluding `observed` while the
    chart says `assumed` produces a *mismatch to reconcile*, not a silent grade
    change. Invisible mutation is the thing this app exists to prevent.
"""

import re
from pathlib import Path

SOUNDINGS = ("assumed", "proxy", "observed")
_SLUG = re.compile(r"[^a-z0-9]+")
_VERDICT = re.compile(r"^\s*#*\s*verdict\s*[:—-]?\s*(\w+)", re.I | re.M)


class ArgumentError(RuntimeError):
    """A write was refused, always for a stated reason."""


def slug(text: str) -> str:
    return _SLUG.sub("-", (text or "").strip().lower()).strip("-")[:60] or "problem"


def path_for(root: Path, problem: dict) -> Path:
    """Stable filename: readable slug plus a short id, so renaming a problem does not
    orphan its essay and two problems can share a title."""
    return Path(root) / f"{slug(problem['title'])}-{problem['id'][:8]}.md"


def scaffold(problem: dict) -> str:
    """The shape of an argument: introduction, one section per claim, conclusion.

    Deliberately an *argumentative essay* rather than a report. A report can list
    evidence and commit to nothing; an essay has to state a thesis and defend it in
    parts, which is what makes a waypoint defensible rather than merely sourced.

    The thesis is broken into numbered claims and each gets its own section, so a
    reader — including you in six months — can see exactly which part of the argument
    a piece of evidence is doing work for, and which part is carrying nothing.
    """
    wp = (problem.get("waypoint") or "").strip()
    return f"""---
problem: {problem['id']}
title: {problem['title']}
---

# {problem['title']}

## Introduction

_The context: what this problem is, why it is worth attacking, and what is at stake
in getting it wrong. Ends by stating the thesis as numbered claims._

{'**Waypoint** — ' + wp if wp else '_No waypoint yet. The argument should end by proposing one._'}

**Thesis.**

1. _First claim._
2. _Second claim._
3. _Third claim._

## 1. _First claim_

_One part of the thesis, argued. Tag each substantive claim **robust**, **mixed** or
**weak/contested**, and cite what it rests on._

## 2. _Second claim_

## 3. _Third claim_

## Conclusion

_What the argument establishes taken together, and what to focus on as a result._

## Verdict

assumed

<!-- assumed = a belief · proxy = something adjacent measured · observed = seen directly.
     Shipyard reads this line and flags a mismatch with the chart; it never changes the
     chart on its own. -->
"""


def read(root: Path, problem: dict) -> dict | None:
    """The essay, or None when there isn't one — a normal state, not an error."""
    p = path_for(root, problem)
    if not p.is_file():
        return None
    try:
        body = p.read_text(errors="replace")
        mtime = p.stat().st_mtime
    except OSError as e:
        raise ArgumentError(f"could not read {p.name}: {e}")
    return {"path": str(p), "name": p.name, "body": body,
            "mtime": mtime, "verdict": verdict_of(body)}


def create(root: Path, problem: dict) -> dict:
    p = path_for(root, problem)
    if p.is_file():                       # create-only: never stamp over an essay
        return read(root, problem)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(scaffold(problem))
    except OSError as e:
        raise ArgumentError(f"could not create {p.name}: {e}")
    return read(root, problem)


def write(root: Path, problem: dict, body: str, expect_mtime: float | None) -> dict:
    """Save, refusing if the file moved under us.

    `expect_mtime` is what the client last saw. A mismatch means someone edited in
    another editor, and their words win by default — shipyard says so rather than
    quietly winning.
    """
    p = path_for(root, problem)
    if p.is_file():
        if expect_mtime is not None:
            current = p.stat().st_mtime
            if abs(current - expect_mtime) > 0.001:
                raise ArgumentError(
                    "this argument changed on disk since it was opened — reload before saving, "
                    "or your other editor's version will be lost")
        # Refuse *dangling* frontmatter: no opening `---`, but a closing one still
        # sitting in the first few lines. On 2026-08-06 one of these files lost only
        # its opening `---`, silently, and no write path in the app could be made to
        # reproduce it. Rather than ship an unverified explanation, the shape of the
        # damage is rejected — while deliberately deleting the whole block stays
        # legal, because that leaves no terminator behind.
        if _dangling_frontmatter(body):
            raise ArgumentError(
                "refusing to save: the frontmatter has no opening `---` but still has a "
                "closing one. That is the shape of a corruption, not an edit — reload "
                "and try again")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    except OSError as e:
        raise ArgumentError(f"could not write {p.name}: {e}")
    return read(root, problem)


def _dangling_frontmatter(body: str, window: int = 8) -> bool:
    """A closing `---` near the top with no opening one: half a frontmatter block."""
    if body.startswith("---\n"):
        return False
    head = body.split("\n")[:window]
    return any(line.strip() == "---" for line in head)


_THESIS_ITEM = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)\s*$")
_TAGGED = re.compile(r"\*\*(Robust|Mixed|Weak[^*]*?)[.:,]?\*\*", re.I)
_TAG_WORD = re.compile(r"[a-z/]+", re.I)


def summarise(body: str, *, max_evidence: int = 8) -> dict:
    """Pull the thesis and the tagged evidence out of an argument, for glancing at.

    The essay is where the reasoning is worked out; the rail is where you need to
    remember what you concluded without reading 1,500 words again. So this reads the
    structure the scaffold enforces — numbered claims under `**Thesis.**`, and any
    sentence carrying an evidence tag — rather than trying to summarise prose.
    """
    thesis: list[str] = []
    current: list[str] | None = None
    seen_thesis = False

    def flush() -> None:
        """Close the claim being collected, joining the lines it wrapped across."""
        nonlocal current
        if current:
            raw = " ".join(current).strip()
            # A scaffold's placeholders are italic — `_First claim._`. Reading those
            # back would show prompts in the rail dressed as conclusions, which is
            # worse than showing nothing.
            if not _is_placeholder(raw):
                thesis.append(_plain(raw))
        current = None

    for line in (body or "").splitlines():
        if "**Thesis.**" in line:
            seen_thesis = True
            continue
        if not seen_thesis:
            continue
        if line.startswith("#"):            # the first heading ends the list
            break
        m = _THESIS_ITEM.match(line)
        if m:
            flush()
            current = [m.group(2)]
        elif not line.strip():
            flush()                         # a blank line closes the current claim
        elif current is not None:
            # A wrapped continuation of the claim above. Without this the rail shows
            # a thesis cut at whatever column the file happens to wrap at, ending
            # mid-phrase on "…too thin and".
            current.append(line.strip())
    flush()

    # Work in paragraphs, not lines. Where an essay happens to wrap is an accident of
    # whoever typed it — some of these files wrap at ~95 columns and some keep a
    # paragraph on one long line — and a line-based reader turns that accident into
    # bullet quality, producing fragments that end mid-phrase ("...a hazard specific
    # to"). Joining the paragraph first makes the rail independent of formatting.
    tagged = []
    seen = set()
    for para in _paragraphs(body):
        hits = list(_TAGGED.finditer(para))
        for i, m in enumerate(hits):
            word = _TAG_WORD.search(m.group(1))
            if not word:
                continue
            tag = word.group(0).lower()
            if tag.startswith("weak"):
                tag = "weak/contested"

            # These essays use a tag in three shapes, and they need different readings.
            # Only the first points forward:
            #
            #   label      "**Robust.** A large RCT found…"      → the claim follows
            #   stamp      "…is what residual means. **Robust**, with the caveat…"
            #   predicate  "…is **robust** for direction"        → claim wraps the tag
            #
            # A label is recognised by what comes after it starting a fresh sentence;
            # a stamp or predicate is not, and reading forward from either returns the
            # caveat while dropping the claim it was grading. For those, the claim runs
            # from the start of the sentence the tag sits in or closes.
            stop = hits[i + 1].start() if i + 1 < len(hits) else len(para)
            leads = bool(_LABEL_AFTER.match(para, m.end(), stop))
            text = para[m.end():stop] if leads else para[_sentence_start(para, m.start()):stop]

            text = _plain(text).strip().lstrip("-•").strip()
            # The chip already says "robust"; repeating it wastes the one line the
            # rail has. Strip a leading tag word and whatever punctuation joins it on.
            text = re.sub(r"^(Robust|Mixed|Weak[^:.]*)[:.]?\s*[—–-]?\s*", "", text, flags=re.I)
            text = re.sub(r"^[—–:;,.\-]+\s*", "", text).strip()
            if len(text) < 25:              # a bare tag with no claim says nothing
                continue
            key = text[:80].lower()
            if key in seen:                 # several predicates in one paragraph all
                continue                    # point at the same prose; show it once
            seen.add(key)
            tagged.append((0 if leads else 1, {"tag": tag, "text": _cap(text)}))

    tagged.sort(key=lambda t: t[0])
    evidence = [item for _, item in tagged[:max_evidence]]

    return {"thesis": thesis, "evidence": evidence}


_PARA_SPLIT = re.compile(r"\n\s*\n")
# What follows a *label*: a fresh sentence. A comma or a lowercase word means the tag
# is qualifying or stamping a claim rather than introducing one.
_LABEL_AFTER = re.compile(r"\s*[—–-]?\s*[\"“(]?[A-Z0-9]")
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _sentence_start(para: str, pos: int) -> int:
    """Where the sentence containing (or ending just before) `pos` begins."""
    head = para[:pos].rstrip()
    bounds = [b.end() for b in _SENT_BOUNDARY.finditer(head)]
    return bounds[-1] if bounds else 0


def _paragraphs(body: str):
    """Prose blocks with the hard wrapping undone, headings and frontmatter dropped."""
    for block in _PARA_SPLIT.split(body or ""):
        kept = [ln.strip() for ln in block.split("\n")
                if ln.strip() and not ln.lstrip().startswith(("#", "<!--", "---"))]
        if kept:
            yield " ".join(kept)


def _cap(text: str, limit: int = 220) -> str:
    """Trim to a word boundary rather than mid-word."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit)
    return text[:cut if cut > 0 else limit].rstrip(" ,;:—–-") + "…"


def _is_placeholder(raw: str) -> bool:
    return bool(re.fullmatch(r"_[^_]+_[.]?", raw.strip()))


def _plain(text: str) -> str:
    """Markdown down to something a one-line chip can hold."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)   # links → their words
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def verdict_of(body: str) -> str | None:
    """The `## Verdict` line, if it names a sounding we recognise."""
    m = _VERDICT.search(body or "")
    if not m:
        return None
    word = m.group(1).lower()
    return word if word in SOUNDINGS else None


def editor_link(template: str | None, path: Path, vault_relative: str | None = None) -> str | None:
    """Fill an `SHIPYARD_EDITOR_URI` template. One config line, any editor."""
    if not template:
        return None
    return (template
            .replace("{abspath}", str(path))
            .replace("{path}", vault_relative or str(path))
            .replace("{name}", path.name))
