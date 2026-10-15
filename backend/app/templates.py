"""Templates — a saved subtree of problems you can stamp under anything.

Not authored in a separate editor: you build one good chart, save that subtree, and
it becomes reusable. That is what keeps the idea general — the same machinery serves
a web service, a grow cycle and a training block, because a template is only ever
problems and waypoints.

> **A standard says what you must have. A template says where to start.**

`standards.yaml` was deleted in v0.5.0 because conformance was never the point, and a
template is one rename away from being the same thing. So: templates are **never
checked**, nothing is ever "missing" from one, and an instantiated subtree is fully
editable and immediately forgets where it came from. Stamped once, never linked.

They live as YAML files rather than in sqlite. Unlike the chart they are not a record
of your reasoning — they are portable definitions worth copying between machines, and
worth hand-editing.
"""

import re
from pathlib import Path

import yaml

_SLUG = re.compile(r"[^a-z0-9]+")


class TemplateError(ValueError):
    """Rejected template operation."""


def slug(name: str) -> str:
    s = _SLUG.sub("-", (name or "").strip().lower()).strip("-")[:60]
    if not s:
        raise TemplateError("a template needs a name")
    return s


def _clean(nodes: list, depth: int = 0) -> list:
    """Keep only what a template is allowed to carry: a title, an observable, and
    children. No soundings, no repos, no anchors — those are facts about *your* chart,
    not about the shape being reused."""
    if depth > 6:
        raise TemplateError("templates nest at most six deep")
    out = []
    for n in nodes or []:
        title = str(n.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "waypoint": str(n.get("waypoint") or "").strip(),
            "children": _clean(n.get("children"), depth + 1),
        })
    return out


def load(root: Path, name_or_slug: str) -> dict | None:
    p = Path(root) / f"{slug(name_or_slug)}.yaml"
    if not p.is_file():
        return None
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise TemplateError(f"could not read {p.name}: {e}")
    return {
        "slug": p.stem,
        "name": data.get("name") or p.stem,
        "description": data.get("description") or "",
        "problems": _clean(data.get("problems")),
        "document": _clean_doc(data.get("document")),
    }


def listing(root: Path) -> list[dict]:
    out = []
    for p in sorted(Path(root).glob("*.yaml")):
        try:
            t = load(root, p.stem)
        except TemplateError:
            continue
        if t:
            out.append({"slug": t["slug"], "name": t["name"],
                        "description": t["description"], "count": _count(t["problems"]),
                        "document": bool(t["document"])})
    return out


def _clean_doc(doc) -> dict | None:
    if not isinstance(doc, dict):
        return None
    body = str(doc.get("body") or "")
    if not body.strip():
        return None
    return {"filename": str(doc.get("filename") or "{slug}.md"), "body": body}


def render_document(doc: dict, *, title: str, slug_of: str) -> tuple[str, str]:
    """Fill the two placeholders a scaffold is allowed: the problem's title and slug."""
    name = doc["filename"].replace("{slug}", slug_of).replace("{title}", title)
    return name, doc["body"].replace("{title}", title).replace("{slug}", slug_of)


def _count(nodes: list) -> int:
    return sum(1 + _count(n["children"]) for n in nodes)


def save(root: Path, *, name: str, problems: list, description: str = "",
         document: dict | None = None) -> dict:
    """A template carries a shape, a document, or both.

    Some kinds have no useful decomposition and exist only to hand you a page to
    fill in — the development cycle is the case in point: it instantiates once per
    *cycle* rather than per project, so putting its steps in the chart would bury
    the reasoning under process bookkeeping.
    """
    cleaned = _clean(problems)
    doc = _clean_doc(document)
    if not cleaned and not doc:
        raise TemplateError("a template needs at least one problem or a document")
    p = Path(root) / f"{slug(name)}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"name": name.strip(), "description": description.strip(), "problems": cleaned}
    if doc:
        body["document"] = doc
    p.write_text(
        "# A shipyard template: a starting shape, never a standard.\n"
        "# Nothing is ever checked against this, and an instantiated copy forgets it.\n"
        + yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
    return load(root, p.stem)


def delete(root: Path, name_or_slug: str) -> None:
    p = Path(root) / f"{slug(name_or_slug)}.yaml"
    if not p.is_file():
        raise TemplateError(f"no template '{name_or_slug}'")
    p.unlink()


def from_subtree(children_of, root_id: str, depth: int = 0) -> list:
    """Turn a live chart subtree into template shape.

    `children_of(id)` is injected so this stays free of the chart module — the point
    is the shape, and the shape is all it should know about.
    """
    if depth > 6:
        return []
    out = []
    for kid in children_of(root_id):
        out.append({
            "title": kid["title"],
            "waypoint": kid.get("waypoint") or "",
            "children": from_subtree(children_of, kid["id"], depth + 1),
        })
    return out


def instantiate(create, attach_to: str, problems: list) -> list[str]:
    """Stamp a template under a problem.

    `create(title, waypoint, parent_id) -> id` is injected. Children carry the
    template's waypoints, which are its entire payload; a copy with the observables
    stripped would be a list of category names.
    """
    made = []
    for n in problems:
        pid = create(n["title"], n["waypoint"], attach_to)
        made.append(pid)
        made.extend(instantiate(create, pid, n["children"]))
    return made
